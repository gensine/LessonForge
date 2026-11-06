"""Lesson outline planner with 45-minute time budget enforcement.

Creates a structured lesson outline based on the source pack, then validates
and auto-rebalances timing to stay within 43-47 minutes.
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import LessonRun, SourcePack, SectionType
from backend.llm import generate

logger = logging.getLogger(__name__)


# ── Planner output schemas ───────────────────────────────────────────────

class PlannedSection(BaseModel):
    """A section in the lesson outline."""
    heading: str
    type: str = Field(description="One of: intro, concept, example, activity, knowledge_check, summary")
    est_minutes: float = Field(ge=1, le=15)
    description: str = Field(description="Brief description of what this section covers")
    source_ids: list[str] = Field(default_factory=list, description="Source IDs to ground this section on")
    key_points: list[str] = Field(default_factory=list, description="Key points to cover")


class PlannedVideo(BaseModel):
    """A video to embed in the lesson."""
    source_id: str
    suggested_placement: str = Field(description="After which section heading to place this video")
    watch_minutes: float = Field(ge=0, le=10)


class PlannedQuestion(BaseModel):
    """A knowledge check question outline."""
    question_topic: str
    difficulty: str = Field(description="easy, medium, or hard")
    tests_concept: str = Field(description="Which key concept this question tests")


class LessonOutline(BaseModel):
    """Complete lesson outline with time budget."""
    sections: list[PlannedSection]
    videos: list[PlannedVideo] = Field(default_factory=list)
    knowledge_questions: list[PlannedQuestion] = Field(default_factory=list)
    total_minutes: float


# ── Source pack summarizer ───────────────────────────────────────────────

def _summarize_source_pack(source_pack: SourcePack) -> str:
    """Create a concise summary of the source pack for the planner prompt."""
    lines = ["Available sources:\n"]

    for src in source_pack.web_sources:
        lines.append(
            f"  [{src.id}] (web) {src.title} — {src.snippet[:150]}"
            f" [reliability: {src.reliability_score:.1f}]"
        )

    for src in source_pack.book_sources:
        lines.append(
            f"  [{src.id}] (book) \"{src.title}\" by {src.author} ({src.year})"
            f" — {src.snippet[:150]}"
        )

    for src in source_pack.video_sources:
        lines.append(
            f"  [{src.id}] (video) \"{src.title}\" by {src.channel}"
            f" ({src.duration_minutes:.0f} min) — {src.why_relevant}"
        )

    lines.append(f"\nKey concepts to cover: {', '.join(source_pack.key_concepts)}")

    return "\n".join(lines)


# ── Time budget validation and rebalancing ───────────────────────────────

def _validate_time_budget(outline: LessonOutline) -> tuple[bool, str]:
    """Check if the outline's time budget is within 43-47 minutes.

    Returns:
        (is_valid, message)
    """
    total = sum(s.est_minutes for s in outline.sections)
    outline.total_minutes = total

    if 43 <= total <= 47:
        return True, f"Time budget OK: {total:.0f} minutes"

    if total < 43:
        return False, f"Lesson too short ({total:.0f} min). Need 43-47 minutes."
    else:
        return False, f"Lesson too long ({total:.0f} min). Need 43-47 minutes."


def _rebalance_outline(outline: LessonOutline, run: LessonRun) -> LessonOutline:
    """Ask the LLM to rebalance the outline to fit 43-47 minutes."""
    total = sum(s.est_minutes for s in outline.sections)

    sections_desc = "\n".join(
        f"  - {s.heading} ({s.type}): {s.est_minutes} min"
        for s in outline.sections
    )

    prompt = (
        f"The following lesson outline totals {total:.0f} minutes, "
        f"but it must be between 43-47 minutes.\n\n"
        f"Current sections:\n{sections_desc}\n\n"
        f"Lesson title: {run.title}\n"
        f"Objective: {run.objective}\n\n"
        f"Rebalance the time allocations so the total is between 43-47 minutes. "
        f"Keep all sections but adjust their est_minutes. "
        f"Prioritize concept sections and activities. "
        f"Do not remove any section — only change the minutes."
    )

    system_prompt = "You are a lesson time planner. Adjust section times to hit 45 minutes total."

    try:
        rebalanced = generate(
            prompt, LessonOutline,
            system_prompt=system_prompt,
            temperature=0.1,
        )
        new_total = sum(s.est_minutes for s in rebalanced.sections)
        logger.info(f"Rebalanced outline: {total:.0f} → {new_total:.0f} minutes")
        return rebalanced
    except Exception as e:
        logger.error(f"Rebalancing failed: {e}")
        # Manual fallback: scale proportionally
        return _proportional_scale(outline)


def _proportional_scale(outline: LessonOutline) -> LessonOutline:
    """Proportionally scale section times to hit 45 minutes."""
    total = sum(s.est_minutes for s in outline.sections)
    if total == 0:
        return outline

    scale_factor = 45.0 / total

    for section in outline.sections:
        section.est_minutes = round(section.est_minutes * scale_factor, 1)
        # Enforce minimum 1 minute per section
        section.est_minutes = max(1.0, section.est_minutes)

    outline.total_minutes = sum(s.est_minutes for s in outline.sections)
    logger.info(f"Proportionally scaled outline to {outline.total_minutes:.0f} minutes")
    return outline


# ── Main planner function ────────────────────────────────────────────────

def create_outline(run: LessonRun) -> LessonOutline:
    """Create a time-budgeted lesson outline from the source pack.

    Args:
        run: LessonRun with source_pack populated.

    Returns:
        Validated LessonOutline with 43-47 minute total.

    Raises:
        ValueError: If source_pack is not available.
        RuntimeError: If outline cannot be generated after retries.
    """
    if run.source_pack is None:
        raise ValueError("Source pack is required for outline planning. Run research first.")

    prompt_path = settings.prompts_dir / "planner.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    source_summary = _summarize_source_pack(run.source_pack)

    prompt = (
        f"Lesson Title: {run.title}\n"
        f"Learning Objective: {run.objective}\n\n"
        f"{source_summary}\n\n"
        f"Create a detailed lesson outline for a 45-minute session.\n\n"
        f"Requirements:\n"
        f"1. Total time MUST be between 43-47 minutes\n"
        f"2. Cover ALL key concepts listed above\n"
        f"3. Include sections of these types: intro, concept (at least 2-3), "
        f"example, activity, knowledge_check, summary\n"
        f"4. Each concept section must reference which source IDs it uses\n"
        f"5. Include 4-6 knowledge check questions that directly test the objective\n"
        f"6. Suggest where to embed the available videos\n"
        f"7. Follow a logical progression from simple to complex\n\n"
        f"Example time budget:\n"
        f"  Hook/intro + objective: 3 min\n"
        f"  Core concept 1 (explanation + example): 8 min\n"
        f"  Core concept 2 (explanation + example): 8 min\n"
        f"  Core concept 3 / comparison: 7 min\n"
        f"  Hands-on activity: 8 min\n"
        f"  Video (supplementary): 5 min\n"
        f"  Knowledge check (4-6 Qs): 4 min\n"
        f"  Summary + next steps: 2 min\n"
        f"  Total: 45 min"
    )

    outline = generate(prompt, LessonOutline, system_prompt=system_prompt, temperature=0.3)

    # Validate time budget
    is_valid, msg = _validate_time_budget(outline)
    logger.info(f"Initial outline: {msg}")

    if not is_valid:
        # Try rebalancing once
        outline = _rebalance_outline(outline, run)
        is_valid, msg = _validate_time_budget(outline)
        logger.info(f"After rebalance: {msg}")

        if not is_valid:
            # Last resort: proportional scale
            outline = _proportional_scale(outline)
            logger.info(f"After proportional scale: {outline.total_minutes:.0f} min")

    # Validate section types
    valid_types = {t.value for t in SectionType}
    for section in outline.sections:
        if section.type not in valid_types:
            section.type = "concept"  # Default fallback

    logger.info(
        f"Outline finalized: {len(outline.sections)} sections, "
        f"{outline.total_minutes:.0f} minutes, "
        f"{len(outline.knowledge_questions)} questions planned"
    )

    return outline
