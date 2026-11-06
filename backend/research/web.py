"""Web search and content extraction module.

Uses Tavily for web search and trafilatura for content extraction.
Includes source reliability scoring via LLM.
"""

import logging
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import Source, SourceType

logger = logging.getLogger(__name__)


# ── Pydantic models for LLM scoring responses ────────────────────────────

class SourceScore(BaseModel):
    """LLM-generated reliability and relevance scores for a source."""
    reliability_score: float = Field(ge=0.0, le=1.0)
    reliability_reason: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    relevance_reason: str


class SourceScores(BaseModel):
    """Batch of source scores."""
    scores: list[SourceScore]


# ── Web search via Tavily ─────────────────────────────────────────────────

async def search_web(queries: list[str], max_results_per_query: int = 4) -> list[dict]:
    """Search the web using Tavily API.

    Args:
        queries: List of search queries.
        max_results_per_query: Max results per query.

    Returns:
        List of result dicts with url, title, snippet, content.
    """
    if not settings.tavily_api_key:
        logger.warning("No Tavily API key configured; skipping web search.")
        return []

    all_results = []
    seen_urls = set()

    for query in queries:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.tavily_api_key,
                        "query": query,
                        "max_results": max_results_per_query,
                        "include_raw_content": True,
                        "search_depth": "advanced",
                    },
                )
                response.raise_for_status()
                data = response.json()

                for result in data.get("results", []):
                    url = result.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append({
                            "url": url,
                            "title": result.get("title", ""),
                            "snippet": result.get("content", "")[:500],
                            "content": result.get("raw_content", result.get("content", ""))[:5000],
                        })

            logger.info(f"Web search '{query}': {len(data.get('results', []))} results")

        except Exception as e:
            logger.error(f"Web search failed for query '{query}': {e}")
            continue

    logger.info(f"Total unique web results: {len(all_results)}")
    return all_results


# ── Content extraction fallback (for URLs without raw content) ────────────

def extract_content(url: str) -> Optional[str]:
    """Extract readable content from a URL using trafilatura."""
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            return None

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        if text:
            return text[:5000]  # Limit to avoid token overflow
        return None

    except Exception as e:
        logger.error(f"Content extraction failed for {url}: {e}")
        return None


# ── Source reliability scoring via LLM ────────────────────────────────────

def score_sources(sources: list[Source], objective: str) -> list[Source]:
    """Score sources for reliability and relevance using the LLM.

    Args:
        sources: List of Source objects to score.
        objective: The lesson learning objective for relevance scoring.

    Returns:
        Same sources with updated reliability and relevance scores.
    """
    if not sources:
        return sources

    from backend.llm import generate

    prompt_path = settings.prompts_dir / "source_scorer.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    # Build sources description for the LLM
    sources_desc = ""
    for i, src in enumerate(sources):
        text_preview = src.extracted_text[:500] if src.extracted_text else src.snippet[:300]
        sources_desc += (
            f"\n--- Source {i+1} ---\n"
            f"Type: {src.type.value}\n"
            f"Title: {src.title}\n"
            f"URL: {src.url}\n"
            f"Snippet: {src.snippet[:300]}\n"
            f"Extracted text (preview): {text_preview}\n"
        )

    prompt = (
        f"Lesson objective: {objective}\n\n"
        f"Score each of the following {len(sources)} sources for reliability and relevance.\n"
        f"Return exactly {len(sources)} scores in the same order.\n"
        f"{sources_desc}"
    )

    try:
        result = generate(prompt, SourceScores, system_prompt=system_prompt, temperature=0.1)

        for i, src in enumerate(sources):
            if i < len(result.scores):
                score = result.scores[i]
                src.reliability_score = score.reliability_score
                src.reliability_reason = score.reliability_reason
                src.relevance_score = score.relevance_score

        logger.info(f"Scored {len(sources)} web sources for reliability and relevance")

    except Exception as e:
        logger.error(f"Source scoring failed: {e}")
        # Assign default scores rather than crashing
        for src in sources:
            src.reliability_score = 0.5
            src.reliability_reason = "Auto-scoring unavailable"
            src.relevance_score = 0.5

    return sources


# ── Build Source objects from search results ──────────────────────────────

def build_web_sources(results: list[dict]) -> list[Source]:
    """Convert raw search results to Source objects.

    Also attempts to extract full content using trafilatura for results
    that lack raw_content from Tavily.
    """
    sources = []
    for i, result in enumerate(results):
        content = result.get("content", "")

        # If content is too short, try extracting with trafilatura
        if len(content) < 200:
            extracted = extract_content(result.get("url", ""))
            if extracted:
                content = extracted

        source = Source(
            id=f"W{i+1}",
            type=SourceType.WEB,
            title=result.get("title", f"Web Source {i+1}"),
            url=result.get("url", ""),
            snippet=result.get("snippet", ""),
            extracted_text=content,
        )
        sources.append(source)

    return sources

