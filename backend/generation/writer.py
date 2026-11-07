"""Lesson content writer — generates grounded sections from the outline.

Writes each section using only facts from the source pack, generates
knowledge check questions with answers, and assembles the full lesson.
"""

import logging
import uuid
from typing import Optional

from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import (
    LessonRun,
    LessonContent,
    LessonSection,
    LessonVersion,
    VideoEmbed,
    KnowledgeQuestion,
    Reference,
    SectionType,
    SourceType,
)
from backend.llm import generate
from backend.generation.planner import create_outline, LessonOutline, PlannedSection

logger = logging.getLogger(__name__)


# ── Writer output schemas ────────────────────────────────────────────────

class WrittenSection(BaseModel):
    """LLM-generated section content."""
    heading: str
    body_md: str = Field(description="Full Markdown content for this section")
    source_ids_used: list[str] = Field(
        default_factory=list,
        description="Source IDs actually cited in this section"
    )


class WrittenSections(BaseModel):
    """Batch of written sections."""
    sections: list[WrittenSection]


class WrittenQuestion(BaseModel):
    """A single knowledge check question with answer."""
    question: str
    options: list[str] = Field(min_length=4, max_length=4, description="4 multiple-choice options")
    correct_answer: str = Field(description="The correct option text")
    explanation: str = Field(description="Why the correct answer is right")


class WrittenQuestions(BaseModel):
    """LLM-generated knowledge check questions."""
    questions: list[WrittenQuestion]


# ── Source pack text builder ─────────────────────────────────────────────

def _build_source_context(run: LessonRun, source_ids: list[str]) -> str:
    """Build a context string from specific sources for the writer.

    Args:
        run: The lesson run with source_pack.
        source_ids: Which source IDs to include.

    Returns:
        Formatted source context for the LLM prompt.
    """
    if run.source_pack is None:
        return ""

    lines = ["SOURCE PACK (use ONLY these facts, cite by ID):\n"]

    for src in run.source_pack.all_sources:
        if source_ids and src.id not in source_ids:
            continue

        lines.append(f"--- [{src.id}] {src.title} ---")
        lines.append(f"Type: {src.type.value} | URL: {src.url}")

        if src.extracted_text:
            # Limit per-source text to keep prompt manageable
            text = src.extracted_text[:2500]
            lines.append(f"Content:\n{text}")
        elif src.snippet:
            lines.append(f"Snippet: {src.snippet}")

        if src.type == SourceType.BOOK:
            lines.append(f"Author: {src.author} | Year: {src.year}")
            lines.append("(Book cited as reference only — content not scraped)")

        if src.type == SourceType.VIDEO:
            lines.append(f"Channel: {src.channel} | Duration: {src.duration_minutes:.0f} min")
            lines.append(f"Relevance: {src.why_relevant}")

        lines.append("")

    return "\n".join(lines)


def _build_full_source_context(run: LessonRun) -> str:
    """Build context from ALL sources."""
    return _build_source_context(run, [])


# ── Section writer ───────────────────────────────────────────────────────

def write_sections(run: LessonRun, outline: LessonOutline) -> list[LessonSection]:
    """Write all lesson sections based on the outline.

    Generates sections in batches to manage context window.

    Args:
        run: LessonRun with source_pack.
        outline: The validated lesson outline.

    Returns:
        List of fully written LessonSection objects.
    """
    prompt_path = settings.prompts_dir / "writer.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    all_sections = []

    # Process sections in small batches (2-3 at a time)
    batch_size = 3
    for i in range(0, len(outline.sections), batch_size):
        batch = outline.sections[i:i + batch_size]

        # Gather all source IDs needed for this batch
        batch_source_ids = []
        for planned in batch:
            batch_source_ids.extend(planned.source_ids)
        batch_source_ids = list(set(batch_source_ids))

        # If no specific sources listed, use all
        if not batch_source_ids:
            source_context = _build_full_source_context(run)
        else:
            source_context = _build_source_context(run, batch_source_ids)

        # Build the sections description
        sections_desc = ""
        for j, planned in enumerate(batch):
            sections_desc += (
                f"\nSection {i+j+1}: {planned.heading}\n"
                f"  Type: {planned.type}\n"
                f"  Time: {planned.est_minutes} minutes\n"
                f"  Key points: {', '.join(planned.key_points) if planned.key_points else 'See description'}\n"
                f"  Description: {planned.description}\n"
                f"  Source IDs to use: {', '.join(planned.source_ids) if planned.source_ids else 'Any relevant'}\n"
            )

        # Build previous sections context for flow
        prev_context = ""
        if all_sections:
            prev_headings = [s.heading for s in all_sections[-3:]]
            prev_context = f"\nPrevious sections covered: {', '.join(prev_headings)}. Maintain flow.\n"

        prompt = (
            f"Lesson Title: {run.title}\n"
            f"Learning Objective: {run.objective}\n\n"
            f"{source_context}\n\n"
            f"{prev_context}"
            f"Write the following {len(batch)} section(s) for this lesson:\n"
            f"{sections_desc}\n\n"
            f"Requirements:\n"
            f"1. Cite source IDs inline like [W1], [B2], [V1]\n"
            f"2. Include concrete examples (code, commands, real scenarios)\n"
            f"3. Define technical terms before using them\n"
            f"4. Use clear, instructional language\n"
            f"5. Each section's word count should match its time allocation "
            f"(~150-200 words per minute of reading)\n"
            f"6. NEVER invent URLs or make up facts not in the source pack\n"
            f"7. Format as clean Markdown with headers, code blocks, lists"
        )

        try:
            result = generate(
                prompt, WrittenSections,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=8192,
            )

            for j, planned in enumerate(batch):
                if j < len(result.sections):
                    written = result.sections[j]
                    section = LessonSection(
                        id=f"SEC{uuid.uuid4().hex[:6]}",
                        heading=written.heading or planned.heading,
                        type=SectionType(planned.type) if planned.type in [t.value for t in SectionType] else SectionType.CONCEPT,
                        body_md=written.body_md,
                        est_minutes=planned.est_minutes,
                        source_ids=written.source_ids_used or planned.source_ids,
                    )
                else:
                    # Fallback if LLM returned fewer sections
                    section = LessonSection(
                        id=f"SEC{uuid.uuid4().hex[:6]}",
                        heading=planned.heading,
                        type=SectionType(planned.type) if planned.type in [t.value for t in SectionType] else SectionType.CONCEPT,
                        body_md=f"## {planned.heading}\n\n{planned.description}\n\n*Content generation incomplete — please edit manually.*",
                        est_minutes=planned.est_minutes,
                        source_ids=planned.source_ids,
                    )

                all_sections.append(section)

            logger.info(f"Wrote sections {i+1}-{i+len(batch)}/{len(outline.sections)}")

        except Exception as e:
            logger.error(f"Section writing failed for batch {i+1}: {e}")
            # Create placeholder sections so the lesson isn't incomplete
            for planned in batch:
                section = LessonSection(
                    id=f"SEC{uuid.uuid4().hex[:6]}",
                    heading=planned.heading,
                    type=SectionType(planned.type) if planned.type in [t.value for t in SectionType] else SectionType.CONCEPT,
                    body_md=f"## {planned.heading}\n\n{planned.description}\n\n> ⚠️ Content generation failed: {str(e)}. Please edit manually or retry.",
                    est_minutes=planned.est_minutes,
                    source_ids=planned.source_ids,
                )
                all_sections.append(section)

    return all_sections


# ── Knowledge check generator ────────────────────────────────────────────

def generate_knowledge_check(run: LessonRun, outline: LessonOutline) -> list[KnowledgeQuestion]:
    """Generate knowledge check questions based on the lesson content.

    Args:
        run: LessonRun with source_pack.
        outline: Lesson outline with planned questions.

    Returns:
        List of KnowledgeQuestion objects.
    """
    source_context = _build_full_source_context(run)

    # Build question topics from the outline
    question_topics = ""
    if outline.knowledge_questions:
        for q in outline.knowledge_questions:
            question_topics += f"  - {q.question_topic} ({q.difficulty}) — tests: {q.tests_concept}\n"
    else:
        question_topics = "  - Generate 4-6 questions covering the key concepts\n"

    prompt = (
        f"Lesson Title: {run.title}\n"
        f"Learning Objective: {run.objective}\n"
        f"Key Concepts: {', '.join(run.source_pack.key_concepts) if run.source_pack else 'N/A'}\n\n"
        f"{source_context}\n\n"
        f"Generate 4-6 multiple-choice knowledge check questions.\n\n"
        f"Planned question topics:\n{question_topics}\n\n"
        f"Requirements:\n"
        f"1. Each question must have exactly 4 options (A, B, C, D)\n"
        f"2. Questions must directly test the learning objective\n"
        f"3. Include a mix of difficulty levels (easy, medium, hard)\n"
        f"4. Correct answers must be factually accurate per the source pack\n"
        f"5. Explanations should reference why the answer is correct\n"
        f"6. Avoid trick questions — test understanding, not memorization\n"
        f"7. Include at least one question that tests application/scenario"
    )

    system_prompt = (
        "You are an educational assessment designer. Create fair, clear multiple-choice "
        "questions that test genuine understanding of the learning objective."
    )

    try:
        result = generate(
            prompt, WrittenQuestions,
            system_prompt=system_prompt,
            temperature=0.2,
        )

        questions = []
        for wq in result.questions:
            questions.append(KnowledgeQuestion(
                question=wq.question,
                options=wq.options,
                correct_answer=wq.correct_answer,
                explanation=wq.explanation,
            ))

        logger.info(f"Generated {len(questions)} knowledge check questions")
        return questions

    except Exception as e:
        logger.error(f"Knowledge check generation failed: {e}")
        return [
            KnowledgeQuestion(
                question="[Knowledge check generation failed — please add questions manually]",
                options=["A", "B", "C", "D"],
                correct_answer="A",
                explanation="Auto-generation failed. Please create questions manually.",
            )
        ]


# ── Reference builder ────────────────────────────────────────────────────

def build_references(run: LessonRun, sections: list[LessonSection]) -> list[Reference]:
    """Build reference list from sources actually used in sections.

    Only includes sources that were cited by at least one section.
    """
    if run.source_pack is None:
        return []

    # Collect all cited source IDs
    cited_ids = set()
    for section in sections:
        cited_ids.update(section.source_ids)

    # Also check body text for inline citations like [W1], [B2]
    import re
    for section in sections:
        found = re.findall(r'\[([WBV]\d+)\]', section.body_md)
        cited_ids.update(found)

    # Build reference entries
    references = []
    for src in run.source_pack.all_sources:
        if src.id in cited_ids or not cited_ids:
            ref = Reference(
                source_id=src.id,
                type=src.type,
                title=src.title,
                url=src.url,
                author=src.author or src.channel,
                detail=_reference_detail(src),
            )
            references.append(ref)

    logger.info(f"Built {len(references)} references from {len(cited_ids)} cited sources")
    return references


def _reference_detail(src) -> str:
    """Build a detail string for a reference entry."""
    if src.type == SourceType.BOOK:
        parts = [src.author]
        if src.year:
            parts.append(f"({src.year})")
        if src.isbn:
            parts.append(f"ISBN: {src.isbn}")
        return " ".join(parts)
    elif src.type == SourceType.VIDEO:
        return f"YouTube — {src.channel} ({src.duration_minutes:.0f} min)"
    else:
        return f"Reliability: {src.reliability_score:.1f}/1.0"


# ── Time validation ──────────────────────────────────────────────────────

def _validate_word_count(sections: list[LessonSection]) -> list[str]:
    """Validate word counts match time allocations.

    Reading pace: ~150-200 wpm for instructional content.
    """
    warnings = []
    for section in sections:
        word_count = len(section.body_md.split())
        expected_min = int(section.est_minutes * 100)   # Conservative lower bound
        expected_max = int(section.est_minutes * 250)    # Upper bound

        if word_count < expected_min and section.est_minutes > 2:
            warnings.append(
                f"Section '{section.heading}' has {word_count} words for "
                f"{section.est_minutes} min — may be too short "
                f"(expected ~{expected_min}-{expected_max} words)"
            )
        elif word_count > expected_max:
            warnings.append(
                f"Section '{section.heading}' has {word_count} words for "
                f"{section.est_minutes} min — may be too long "
                f"(expected ~{expected_min}-{expected_max} words)"
            )

    return warnings


# ── Main generation executor ─────────────────────────────────────────────

async def execute_generation(run: LessonRun) -> None:
    """Execute the full lesson generation pipeline.

    Steps:
        1. Create time-budgeted outline
        2. Write sections grounded on sources
        3. Generate knowledge check questions
        4. Build reference list
        5. Assemble and validate
        6. Save as version 1

    Args:
        run: LessonRun with source_pack populated.
    """
    if run.source_pack is None:
        raise ValueError("Research must complete before generation. No source pack found.")

    logger.info(f"[{run.id}] Starting lesson generation for '{run.title}'")

    # Step 1: Create outline
    logger.info(f"[{run.id}] Creating lesson outline...")
    outline = create_outline(run)
    logger.info(
        f"[{run.id}] Outline: {len(outline.sections)} sections, "
        f"{outline.total_minutes:.0f} minutes"
    )

    # Step 2: Write sections
    logger.info(f"[{run.id}] Writing lesson sections...")
    sections = write_sections(run, outline)
    logger.info(f"[{run.id}] Wrote {len(sections)} sections")

    # Step 3: Generate knowledge check
    logger.info(f"[{run.id}] Generating knowledge check questions...")
    questions = generate_knowledge_check(run, outline)
    logger.info(f"[{run.id}] Generated {len(questions)} questions")

    # Step 4: Build references
    logger.info(f"[{run.id}] Building reference list...")
    references = build_references(run, sections)

    # Step 5: Build video embeds from source pack
    video_embeds = []
    if run.source_pack and run.source_pack.video_sources:
        for vid_src in run.source_pack.video_sources:
            embed = VideoEmbed(
                video_id=vid_src.url.split("v=")[-1] if "v=" in vid_src.url else vid_src.id,
                title=vid_src.title,
                url=vid_src.url,
                channel=vid_src.channel,
                why_relevant=vid_src.why_relevant,
                watch_minutes=vid_src.duration_minutes,
            )
            video_embeds.append(embed)

    # Step 6: Assemble lesson content
    total_minutes = sum(s.est_minutes for s in sections)

    content = LessonContent(
        sections=sections,
        videos=video_embeds,
        knowledge_check=questions,
        references=references,
        total_minutes=total_minutes,
    )

    # Validate word counts
    word_warnings = _validate_word_count(sections)
    for warning in word_warnings:
        logger.warning(f"[{run.id}] {warning}")

    # Step 7: Save as version 1 (AI Draft)
    version = LessonVersion(
        version=len(run.versions) + 1,
        content=content,
        label="AI Draft",
    )
    run.versions.append(version)

    logger.info(
        f"[{run.id}] Generation complete! "
        f"Sections: {len(sections)}, "
        f"Questions: {len(questions)}, "
        f"Videos: {len(video_embeds)}, "
        f"References: {len(references)}, "
        f"Total: {total_minutes:.0f} min, "
        f"Saved as version {version.version}"
    )

