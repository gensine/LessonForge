"""Unified LLM wrapper with structured JSON output, retry, and multi-provider support.

Supports Gemini, OpenAI, and Claude behind a single interface.
Forces JSON output, validates against a Pydantic schema, retries on failure.
"""

import json
import logging
import time
from typing import Type, TypeVar, Optional

from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from backend.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ── Custom exceptions ─────────────────────────────────────────────────────

class LLMError(Exception):
    """Base error for LLM operations."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timed out."""
    pass


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded."""
    pass


class LLMResponseError(LLMError):
    """LLM returned invalid or unparseable response."""
    pass


# ── Provider implementations ──────────────────────────────────────────────

def _call_gemini(prompt: str, system_prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Google Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=settings.llm_api_key)

    model = genai.GenerativeModel(
        model_name=settings.llm_model,
        system_instruction=system_prompt if system_prompt else None,
        generation_config=genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        ),
    )

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        error_str = str(e).lower()
        if "rate" in error_str or "quota" in error_str or "429" in error_str:
            raise LLMRateLimitError(f"Gemini rate limit: {e}")
        if "timeout" in error_str or "deadline" in error_str:
            raise LLMTimeoutError(f"Gemini timeout: {e}")
        raise LLMError(f"Gemini error: {e}")


def _call_openai(prompt: str, system_prompt: str, temperature: float, max_tokens: int) -> str:
    """Call OpenAI API."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.llm_api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except Exception as e:
        error_str = str(e).lower()
        if "rate" in error_str or "429" in error_str:
            raise LLMRateLimitError(f"OpenAI rate limit: {e}")
        if "timeout" in error_str:
            raise LLMTimeoutError(f"OpenAI timeout: {e}")
        raise LLMError(f"OpenAI error: {e}")


def _call_claude(prompt: str, system_prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.llm_api_key)

    try:
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            system=system_prompt if system_prompt else "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return response.content[0].text
    except Exception as e:
        error_str = str(e).lower()
        if "rate" in error_str or "429" in error_str:
            raise LLMRateLimitError(f"Claude rate limit: {e}")
        if "timeout" in error_str:
            raise LLMTimeoutError(f"Claude timeout: {e}")
        raise LLMError(f"Claude error: {e}")


# ── Provider dispatch ─────────────────────────────────────────────────────

_PROVIDERS = {
    "gemini": _call_gemini,
    "openai": _call_openai,
    "claude": _call_claude,
}


def _get_provider():
    """Get the configured LLM provider function."""
    provider = settings.llm_provider.lower()
    if provider not in _PROVIDERS:
        raise LLMError(
            f"Unknown LLM provider '{provider}'. "
            f"Supported: {', '.join(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider]


# ── JSON extraction helper ────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()

    # Remove markdown code block wrappers
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


# ── Main public API ───────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((LLMRateLimitError, LLMTimeoutError, LLMResponseError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def generate(
    prompt: str,
    schema: Type[T],
    system_prompt: str = "",
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> T:
    """Generate structured output from the LLM.

    Args:
        prompt: The user prompt including the task and any context.
        schema: A Pydantic model class. The LLM response is parsed and validated
                against this schema.
        system_prompt: Optional system-level instructions.
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
        max_tokens: Maximum output tokens.

    Returns:
        An instance of the schema class, validated.

    Raises:
        LLMError: On unrecoverable LLM errors.
        LLMResponseError: If JSON parsing/validation fails after retries.
        LLMRateLimitError: If rate limit persists after retries.
        LLMTimeoutError: If timeout persists after retries.
    """
    provider_fn = _get_provider()

    # Build schema instruction for the prompt
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    full_prompt = (
        f"{prompt}\n\n"
        f"IMPORTANT: Respond ONLY with valid JSON matching this schema:\n"
        f"```json\n{schema_json}\n```\n"
        f"No extra text, no markdown, just the JSON object."
    )

    logger.info(f"LLM call: provider={settings.llm_provider}, model={settings.llm_model}, "
                f"schema={schema.__name__}, temp={temperature}")

    start_time = time.time()

    # Call the provider
    raw_response = provider_fn(full_prompt, system_prompt, temperature, max_tokens)
    elapsed = time.time() - start_time
    logger.info(f"LLM response received in {elapsed:.1f}s ({len(raw_response)} chars)")

    # Parse JSON
    try:
        json_text = _extract_json(raw_response)
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nRaw response:\n{raw_response[:500]}")
        raise LLMResponseError(f"LLM returned invalid JSON: {e}")

    # Validate against Pydantic schema
    try:
        result = schema.model_validate(data)
        logger.info(f"Successfully parsed and validated {schema.__name__}")
        return result
    except ValidationError as e:
        logger.error(f"Schema validation error: {e}\nData:\n{json.dumps(data, indent=2)[:500]}")
        raise LLMResponseError(f"LLM response doesn't match schema: {e}")


def generate_text(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Generate raw text from the LLM (no schema validation).

    Useful for free-form text generation like section writing.
    """
    provider_fn = _get_provider()

    logger.info(f"LLM text call: provider={settings.llm_provider}, model={settings.llm_model}")

    start_time = time.time()
    raw_response = provider_fn(prompt, system_prompt, temperature, max_tokens)
    elapsed = time.time() - start_time
    logger.info(f"LLM text response in {elapsed:.1f}s ({len(raw_response)} chars)")

    return raw_response

