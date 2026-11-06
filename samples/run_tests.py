"""Sample test runner — generates lessons for both test cases.

Run this script to generate sample outputs in the /samples directory.
Requires API keys to be configured in .env.

Usage:
    python samples/run_tests.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from backend.db import get_db
from backend.schemas import LessonRun, StepName
from backend.step_runner import StepRunner
from backend.config import settings


# Test cases
TEST_CASES = [
    {
        "title": "HTTP Requests and Responses",
        "objective": "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.",
        "prefix": "test1",
    },
    {
        "title": "Git Branching and Merging",
        "objective": "Explain what a branch is and differentiate merge vs rebase.",
        "prefix": "test2",
    },
]


async def run_test(test_case: dict):
    """Run a full pipeline for a test case."""
    title = test_case["title"]
    objective = test_case["objective"]
    prefix = test_case["prefix"]

    print(f"\n{'='*60}")
    print(f"TEST: {title}")
    print(f"{'='*60}\n")

    db = get_db()

    # Create run
    run = LessonRun(
        title=title,
        objective=objective,
        model_used=f"{settings.llm_provider}/{settings.llm_model}",
    )
    db.save_run(run)
    print(f"Created run: {run.id}")

    runner = StepRunner(run)

    # Step 1: Research
    print("\n[1/4] Running research...")
    try:
        from backend.research.pipeline import execute_research
        await runner.execute(StepName.RESEARCH, execute_research)
        sp = run.source_pack
        if sp:
            print(f"  ✓ {len(sp.web_sources)} web, {len(sp.book_sources)} books, {len(sp.video_sources)} videos")
            print(f"  Key concepts: {', '.join(sp.key_concepts)}")
            if sp.research_warnings:
                for w in sp.research_warnings:
                    print(f"  ⚠ {w}")
    except Exception as e:
        print(f"  ✗ Research failed: {e}")
        return

    # Step 2: Generate
    print("\n[2/4] Generating lesson...")
    try:
        from backend.generation.writer import execute_generation
        await runner.execute(StepName.GENERATE, execute_generation)
        if run.current_version:
            content = run.current_version.content
            total = sum(s.est_minutes for s in content.sections)
            print(f"  ✓ {len(content.sections)} sections, {total:.0f} min")
            print(f"  ✓ {len(content.knowledge_check)} knowledge check questions")
            print(f"  ✓ {len(content.references)} references")
    except Exception as e:
        print(f"  ✗ Generation failed: {e}")
        return

    # Step 3: QC1
    print("\n[3/4] Running QC1 (factual accuracy)...")
    try:
        from backend.qc.qc1_factual import execute_qc1
        await runner.execute(StepName.QC1, execute_qc1)
        if run.qc1_report:
            print(f"  ✓ Score: {run.qc1_report.score}/10")
            print(f"  ✓ Issues: {len(run.qc1_report.issues)}")
    except Exception as e:
        print(f"  ✗ QC1 failed: {e}")

    # Step 4: QC2
    print("\n[4/4] Running QC2 (instructional quality)...")
    try:
        from backend.qc.qc2_instructional import execute_qc2
        await runner.execute(StepName.QC2, execute_qc2)
        if run.qc2_report:
            print(f"  ✓ Score: {run.qc2_report.score}/10")
            print(f"  ✓ Issues: {len(run.qc2_report.issues)}")
            if run.qc2_report.coverage_matrix:
                print(f"  ✓ Coverage matrix: {len(run.qc2_report.coverage_matrix)} components")
    except Exception as e:
        print(f"  ✗ QC2 failed: {e}")

    # Export
    print("\n[Export] Generating output files...")
    try:
        from backend.export.exporter import (
            _generate_lesson_md,
            _generate_qc_report_md,
        )

        samples_dir = project_root / "samples"
        samples_dir.mkdir(exist_ok=True)

        lesson_md = _generate_lesson_md(run)
        (samples_dir / f"{prefix}_lesson.md").write_text(lesson_md, encoding="utf-8")
        print(f"  ✓ {prefix}_lesson.md")

        qc1_md = _generate_qc_report_md(run, layer=1)
        (samples_dir / f"{prefix}_qc1_report.md").write_text(qc1_md, encoding="utf-8")
        print(f"  ✓ {prefix}_qc1_report.md")

        qc2_md = _generate_qc_report_md(run, layer=2)
        (samples_dir / f"{prefix}_qc2_report.md").write_text(qc2_md, encoding="utf-8")
        print(f"  ✓ {prefix}_qc2_report.md")

    except Exception as e:
        print(f"  ✗ Export failed: {e}")

    print(f"\n✅ Test '{title}' complete!\n")


async def main():
    """Run all test cases."""
    print("🎓 LessonForge — Sample Test Runner")
    print(f"LLM: {settings.llm_provider}/{settings.llm_model}")
    print(f"Tavily: {'configured' if settings.tavily_api_key else 'NOT configured'}")
    print(f"YouTube: {'configured' if settings.youtube_api_key else 'NOT configured'}")

    if not settings.llm_api_key:
        print("\n❌ LLM API key not configured! Set LLM_API_KEY in .env")
        sys.exit(1)

    for test_case in TEST_CASES:
        await run_test(test_case)

    print("\n" + "="*60)
    print("All tests complete! Check /samples for output files.")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

