"""Research pipeline orchestrator.

Coordinates query planning, web search, book search, YouTube search,
source scoring, and assembles the final source pack.

Handles partial failures gracefully — if one provider fails, continues
with the others and flags warnings.
"""

import logging

from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import LessonRun, SourcePack, Source
from backend.llm import generate

logger = logging.getLogger(__name__)


# ── Query planning schema ────────────────────────────────────────────────

class ResearchPlan(BaseModel):
    """LLM-generated research plan with queries for each source type."""
    web_queries: list[str] = Field(
        min_length=3, max_length=5,
        description="3-5 web search queries targeting official docs and authoritative sources"
    )
    book_queries: list[str] = Field(
        min_length=1, max_length=3,
        description="1-3 book search queries for textbooks on the topic"
    )
    youtube_queries: list[str] = Field(
        min_length=2, max_length=4,
        description="2-4 YouTube search queries for educational videos"
    )
    key_concepts: list[str] = Field(
        min_length=3,
        description="Key concepts the lesson must cover based on the objective"
    )


# ── Query planning ───────────────────────────────────────────────────────

def plan_research(title: str, objective: str) -> ResearchPlan:
    """Use LLM to generate targeted research queries from title + objective.

    Args:
        title: Lesson title.
        objective: Learning objective.

    Returns:
        ResearchPlan with categorized queries and key concepts.
    """
    prompt_path = settings.prompts_dir / "research_planner.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    prompt = (
        f"Lesson Title: {title}\n"
        f"Learning Objective: {objective}\n\n"
        f"Generate a research plan with:\n"
        f"1. 3-5 web search queries that will find official documentation, "
        f"authoritative tutorials, and technical references for this topic. "
        f"Target specific sources like MDN, RFC specs, official docs, etc.\n"
        f"2. 2 book search queries to find relevant textbooks.\n"
        f"3. 2-3 YouTube search queries to find the best educational videos.\n"
        f"4. A list of key concepts that the lesson MUST cover based on the objective "
        f"(e.g., for HTTP: GET, POST, idempotency, 2xx/4xx/5xx status codes).\n\n"
        f"Be specific — avoid overly generic queries like 'HTTP tutorial'. "
        f"Instead use targeted queries like 'HTTP GET vs POST methods MDN documentation'."
    )

    plan = generate(prompt, ResearchPlan, system_prompt=system_prompt, temperature=0.2)
    logger.info(
        f"Research plan: {len(plan.web_queries)} web queries, "
        f"{len(plan.book_queries)} book queries, "
        f"{len(plan.youtube_queries)} YouTube queries, "
        f"{len(plan.key_concepts)} key concepts"
    )
    return plan


# ── Main pipeline execution ──────────────────────────────────────────────

async def execute_research(run: LessonRun) -> None:
    """Execute the full research pipeline for a lesson run.

    Steps:
        1. Query planning (LLM)
        2. Web search + extraction + scoring
        3. Book search
        4. YouTube search + transcript + relevance scoring
        5. Assemble source pack

    Handles partial failures: if one provider fails, continues with others
    and logs warnings.

    Args:
        run: The LessonRun to populate with research data.
    """
    from backend.research.web import search_web, build_web_sources, score_sources
    from backend.research.books import search_books, search_open_library
    from backend.research.youtube import search_youtube, score_videos

    warnings = []

    # ── Step 1: Query planning ────────────────────────────────────────
    logger.info(f"[{run.id}] Planning research queries...")
    try:
        plan = plan_research(run.title, run.objective)
    except Exception as e:
        logger.error(f"Query planning failed: {e}")
        # Fallback: create at least 3 distinct key concepts to guarantee schema compliance
        plan = ResearchPlan(
            web_queries=[
                f"{run.title} tutorial",
                f"{run.title} documentation",
                f"{run.title} explained",
            ],
            book_queries=[run.title],
            youtube_queries=[
                f"{run.title} tutorial",
                f"{run.title} explained",
            ],
            key_concepts=[
                run.title,
                f"{run.title} fundamentals",
                f"{run.title} practical applications",
            ],
        )
        warnings.append(f"Query planning used fallback ({str(e)})")

    # ── Step 2: Web search + scoring ──────────────────────────────────
    logger.info(f"[{run.id}] Running web search ({len(plan.web_queries)} queries)...")
    web_sources = []
    try:
        raw_results = await search_web(plan.web_queries)
        web_sources = build_web_sources(raw_results)

        if web_sources:
            # Score for reliability and relevance
            web_sources = score_sources(web_sources, run.objective)

            # Sort by combined score, keep top 5-6
            web_sources.sort(
                key=lambda s: (s.reliability_score + s.relevance_score) / 2,
                reverse=True,
            )
            web_sources = web_sources[:6]
            logger.info(f"[{run.id}] Kept top {len(web_sources)} web sources after scoring")
        else:
            warnings.append("Web search returned no results")
    except Exception as e:
        logger.error(f"Web search pipeline failed: {e}")
        warnings.append(f"Web search failed: {str(e)}")

    # ── Step 3: Book search ───────────────────────────────────────────
    logger.info(f"[{run.id}] Searching for books ({len(plan.book_queries)} queries)...")
    book_sources = []
    try:
        book_sources = await search_books(plan.book_queries, max_results=3)

        # If Google Books returned too few, try Open Library as fallback
        if len(book_sources) < 2:
            logger.info("Trying Open Library as fallback for books...")
            ol_books = await search_open_library(plan.book_queries, max_results=2)
            # Avoid duplicates by title
            existing_titles = {b.title.lower() for b in book_sources}
            for book in ol_books:
                if book.title.lower() not in existing_titles:
                    book.id = f"B{len(book_sources)+1}"
                    book_sources.append(book)

        logger.info(f"[{run.id}] Found {len(book_sources)} books")
    except Exception as e:
        logger.error(f"Book search failed: {e}")
        warnings.append(f"Book search failed: {str(e)}")

    # ── Step 4: YouTube search + scoring ──────────────────────────────
    logger.info(f"[{run.id}] Searching YouTube ({len(plan.youtube_queries)} queries)...")
    video_sources = []
    try:
        raw_videos = await search_youtube(plan.youtube_queries)

        if raw_videos:
            video_sources = score_videos(raw_videos, run.objective)
            logger.info(f"[{run.id}] Selected {len(video_sources)} videos")
        else:
            warnings.append("YouTube search returned no results")
    except Exception as e:
        logger.error(f"YouTube search failed: {e}")
        warnings.append(f"YouTube search failed: {str(e)}")

    # ── Step 5: Assemble source pack ──────────────────────────────────
    source_pack = SourcePack(
        web_sources=web_sources,
        book_sources=book_sources,
        video_sources=video_sources,
        key_concepts=plan.key_concepts,
        research_warnings=warnings,
    )

    total_sources = len(source_pack.all_sources)
    logger.info(
        f"[{run.id}] Research complete: {total_sources} total sources "
        f"({len(web_sources)} web, {len(book_sources)} books, "
        f"{len(video_sources)} videos), {len(warnings)} warnings"
    )

    if total_sources == 0:
        raise RuntimeError(
            "Research produced zero sources. Check API keys and network connectivity. "
            "Warnings: " + "; ".join(warnings)
        )

    # Save to the run
    run.source_pack = source_pack

