"""Apply accepted QC recommendations to the lesson.

Takes all accepted issues from QC1 and QC2, groups them by section,
and uses the LLM to revise each affected section. Creates a new version
with the fixes applied, preserving the original.
"""

import logging
from datetime import datetime

from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import (
    LessonRun,
    LessonContent,
    LessonSection,
    LessonVersion,
    QCIssue,
    IssueStatus,
)
from backend.llm import generate

logger = logging.getLogger(__name__)


# ── LLM output schema for revised section ────────────────────────────────

class RevisedSection(BaseModel):
    """LLM-generated revised section content."""
    heading: str
    body_md: str = Field(description="Complete revised Markdown content")
    changes_made: list[str] = Field(
        default_factory=list,
        description="Summary of each change made"
    )


class RevisedSections(BaseModel):
    """Batch of revised sections."""
    sections: list[RevisedSection]


# ── Diff generation ─────────────────────────────────────────────────────

def _generate_diff(original: str, revised: str) -> str:
    """Generate a simple text diff between original and revised content.

    Returns a human-readable diff showing changes.
    """
    original_lines = original.splitlines()
    revised_lines = revised.splitlines()

    diff_lines = []
    diff_lines.append("```diff")

    # Simple line-by-line comparison
    max_lines = max(len(original_lines), len(revised_lines))

    for i in range(max_lines):
        orig = original_lines[i] if i < len(original_lines) else ""
        rev = revised_lines[i] if i < len(revised_lines) else ""

        if orig == rev:
            diff_lines.append(f"  {orig}")
        else:
            if orig:
                diff_lines.append(f"- {orig}")
            if rev:
                diff_lines.append(f"+ {rev}")

    diff_lines.append("```")
    return "\n".join(diff_lines)


# ── Main apply fixes function ───────────────────────────────────────────

def apply_fixes(run: LessonRun) -> dict:
    """Apply all accepted QC recommendations to the lesson.

    Groups accepted issues by section, sends each section + its issues
    to the LLM for revision, creates a new version with the changes.

    Args:
        run: LessonRun with QC reports and accepted issues.

    Returns:
        Dict with summary of changes, diffs, and new version number.
    """
    if run.current_version is None:
        raise ValueError("No lesson version to apply fixes to.")

    # ── Collect accepted issues from both QC reports ──────────────────
    accepted_issues: list[QCIssue] = []

    if run.qc1_report:
        for issue in run.qc1_report.issues:
            if issue.status == IssueStatus.ACCEPTED:
                accepted_issues.append(issue)

    if run.qc2_report:
        for issue in run.qc2_report.issues:
            if issue.status == IssueStatus.ACCEPTED:
                accepted_issues.append(issue)

    if not accepted_issues:
        return {
            "message": "No accepted issues to apply.",
            "changes": 0,
            "diffs": [],
        }

    logger.info(f"[{run.id}] Applying {len(accepted_issues)} accepted fixes...")

    # ── Group issues by section ──────────────────────────────────────
    section_issues: dict[str, list[QCIssue]] = {}
    general_issues: list[QCIssue] = []

    for issue in accepted_issues:
        if issue.section_id:
            section_issues.setdefault(issue.section_id, []).append(issue)
        else:
            general_issues.append(issue)

    # ── Load prompt ──────────────────────────────────────────────────
    prompt_path = settings.prompts_dir / "apply_fixes.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    # ── Build source context for grounding ───────────────────────────
    source_context = ""
    if run.source_pack:
        source_lines = ["Available sources for fact-checking:\n"]
        for src in run.source_pack.all_sources:
            text_preview = src.extracted_text[:500] if src.extracted_text else src.snippet[:300]
            source_lines.append(f"[{src.id}] {src.title}: {text_preview}\n")
        source_context = "\n".join(source_lines)

    # ── Revise each affected section ─────────────────────────────────
    current_content = run.current_version.content.model_copy(deep=True)
    diffs = []
    changes_made = 0

    for section in current_content.sections:
        issues_for_section = section_issues.get(section.id, [])

        if not issues_for_section:
            continue

        # Build issues description
        issues_desc = "\n".join(
            f"  {i+1}. [{iss.severity.value.upper()}] {iss.category}: {iss.description}\n"
            f"     Evidence: {iss.evidence}\n"
            f"     Suggested fix: {iss.suggested_fix}"
            for i, iss in enumerate(issues_for_section)
        )

        prompt = (
            f"ORIGINAL SECTION:\n"
            f"Heading: {section.heading}\n"
            f"Type: {section.type.value}\n"
            f"Content:\n{section.body_md}\n\n"
            f"{'='*40}\n\n"
            f"ACCEPTED RECOMMENDATIONS TO APPLY:\n"
            f"{issues_desc}\n\n"
            f"{'='*40}\n\n"
            f"{source_context}\n\n"
            f"Revise the section to address ALL the listed recommendations.\n"
            f"Return the complete revised section with a list of changes made."
        )

        try:
            result = generate(
                prompt, RevisedSection,
                system_prompt=system_prompt,
                temperature=0.15,
            )

            # Generate diff
            diff = _generate_diff(section.body_md, result.body_md)
            diffs.append({
                "section_id": section.id,
                "section_heading": section.heading,
                "issues_addressed": len(issues_for_section),
                "changes_made": result.changes_made,
                "diff": diff,
            })

            # Apply the revision
            section.body_md = result.body_md
            changes_made += len(issues_for_section)

            # Mark issues as applied
            for iss in issues_for_section:
                iss.status = IssueStatus.APPLIED

            logger.info(
                f"[{run.id}] Revised section '{section.heading}': "
                f"{len(issues_for_section)} issues, {len(result.changes_made)} changes"
            )

        except Exception as e:
            logger.error(f"[{run.id}] Failed to revise section '{section.heading}': {e}")
            diffs.append({
                "section_id": section.id,
                "section_heading": section.heading,
                "issues_addressed": len(issues_for_section),
                "error": str(e),
            })

    # ── Handle general issues (not tied to a section) ────────────────
    if general_issues:
        general_desc = "\n".join(
            f"  - [{iss.severity.value.upper()}] {iss.category}: {iss.description} "
            f"(Fix: {iss.suggested_fix})"
            for iss in general_issues
        )
        logger.info(
            f"[{run.id}] {len(general_issues)} general issues noted "
            f"(require manual attention):\n{general_desc}"
        )
        for iss in general_issues:
            iss.status = IssueStatus.APPLIED  # Mark as processed

    # ── Create new version ───────────────────────────────────────────
    new_version = LessonVersion(
        version=len(run.versions) + 1,
        content=current_content,
        label=f"After QC fixes ({changes_made} issues addressed)",
    )
    run.versions.append(new_version)

    result = {
        "message": f"Applied fixes: {changes_made} issues addressed across {len(diffs)} sections.",
        "version": new_version.version,
        "changes": changes_made,
        "diffs": diffs,
        "general_issues": [
            {"category": iss.category, "description": iss.description}
            for iss in general_issues
        ],
    }

    logger.info(
        f"[{run.id}] Fixes applied. New version {new_version.version} created. "
        f"{changes_made} issues addressed."
    )

    return result

