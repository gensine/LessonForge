"""QC Layer 2: Instructional Quality audit.

Runs as a SEPARATE prompt/call, independent of both the writer and QC1.
Acts like an instructional designer reviewing the lesson.

Checks:
1. Objective alignment — coverage matrix
2. Clarity & structure — reading level, flow, jargon
3. Examples & applications — concrete, practical, varied
4. Assessment quality — tests the objective, correct answers, difficulty mix
5. Time feasibility — recompute total time from word count
6. Engagement — activity, videos, hook, variety
"""

import logging
import re

from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import (
    LessonRun,
    QCReport,
    QCIssue,
    IssueSeverity,
    IssueStatus,
)
from backend.llm import generate

logger = logging.getLogger(__name__)


# ── QC2 LLM output schemas ──────────────────────────────────────────────

class CriterionScore(BaseModel):
    """Score for a single instructional criterion."""
    criterion: str
    score: int = Field(ge=1, le=5, description="Score 1-5")
    justification: str
    suggestions: list[str] = Field(default_factory=list)


class CoverageEntry(BaseModel):
    """One entry in the objective-to-section coverage matrix."""
    objective_component: str = Field(description="A specific part of the learning objective")
    covered_by_sections: list[str] = Field(default_factory=list, description="Section headings that cover this")
    coverage_level: str = Field(description="full | partial | missing")


class QC2Issue(BaseModel):
    """An instructional quality issue."""
    severity: str = Field(description="high | med | low")
    section_heading: str = Field(default="")
    category: str = Field(
        description="objective_gap, clarity, example_missing, assessment_issue, "
                    "timing_issue, engagement, structure, jargon"
    )
    description: str
    evidence: str = Field(default="")
    suggested_fix: str = Field(default="")


class InstructionalAudit(BaseModel):
    """Complete QC2 audit result."""
    overall_score: float = Field(ge=0.0, le=10.0)
    summary: str
    criterion_scores: list[CriterionScore] = Field(default_factory=list)
    coverage_matrix: list[CoverageEntry] = Field(default_factory=list)
    computed_total_minutes: float = Field(
        default=0.0,
        description="Recomputed lesson time based on word count"
    )
    issues: list[QC2Issue] = Field(default_factory=list)


# ── Programmatic instructional checks ────────────────────────────────────

def _check_time_feasibility(run: LessonRun) -> list[QCIssue]:
    """Recompute total time from word count and flag issues."""
    issues = []
    if run.current_version is None:
        return issues

    total_claimed = 0.0
    total_computed = 0.0

    for section in run.current_version.content.sections:
        word_count = len(section.body_md.split())
        # Reading speed: ~175 wpm for instructional content
        computed_minutes = word_count / 175.0
        total_claimed += section.est_minutes
        total_computed += computed_minutes

        # Flag individual sections that are significantly off
        ratio = computed_minutes / section.est_minutes if section.est_minutes > 0 else 0
        if ratio < 0.5 and section.est_minutes > 2:
            issues.append(QCIssue(
                severity=IssueSeverity.MEDIUM,
                section_id=section.id,
                category="timing_issue",
                description=(
                    f"Section '{section.heading}' claims {section.est_minutes:.0f} min "
                    f"but has only {word_count} words (~{computed_minutes:.1f} min reading). "
                    f"Content may be too thin."
                ),
                evidence=f"Word count: {word_count}, Claimed: {section.est_minutes} min",
                suggested_fix="Add more content or reduce the time allocation.",
                status=IssueStatus.OPEN,
            ))
        elif ratio > 1.8:
            issues.append(QCIssue(
                severity=IssueSeverity.MEDIUM,
                section_id=section.id,
                category="timing_issue",
                description=(
                    f"Section '{section.heading}' claims {section.est_minutes:.0f} min "
                    f"but has {word_count} words (~{computed_minutes:.1f} min reading). "
                    f"Content may be too dense."
                ),
                evidence=f"Word count: {word_count}, Claimed: {section.est_minutes} min",
                suggested_fix="Split the content or increase the time allocation.",
                status=IssueStatus.OPEN,
            ))

    # Check overall total
    if total_computed < 35:
        issues.append(QCIssue(
            severity=IssueSeverity.HIGH,
            section_id="",
            category="timing_issue",
            description=(
                f"Total computed lesson time is ~{total_computed:.0f} min "
                f"(claimed {total_claimed:.0f} min). "
                f"Lesson may be significantly shorter than 45 minutes."
            ),
            evidence=f"Computed: {total_computed:.1f} min, Claimed: {total_claimed:.0f} min",
            suggested_fix="Add more content to reach the 45-minute target.",
            status=IssueStatus.OPEN,
        ))
    elif total_computed > 55:
        issues.append(QCIssue(
            severity=IssueSeverity.HIGH,
            section_id="",
            category="timing_issue",
            description=(
                f"Total computed lesson time is ~{total_computed:.0f} min "
                f"(claimed {total_claimed:.0f} min). "
                f"Lesson may exceed 45 minutes."
            ),
            evidence=f"Computed: {total_computed:.1f} min, Claimed: {total_claimed:.0f} min",
            suggested_fix="Trim content or split into two sessions.",
            status=IssueStatus.OPEN,
        ))

    return issues


def _check_section_structure(run: LessonRun) -> list[QCIssue]:
    """Check for structural issues in the lesson."""
    issues = []
    if run.current_version is None:
        return issues

    content = run.current_version.content
    section_types = [s.type.value for s in content.sections]

    # Check for required section types
    if "intro" not in section_types:
        issues.append(QCIssue(
            severity=IssueSeverity.MEDIUM,
            section_id="",
            category="structure",
            description="Lesson is missing an introduction/hook section.",
            suggested_fix="Add an intro section with a hook and objective statement.",
            status=IssueStatus.OPEN,
        ))

    if "summary" not in section_types:
        issues.append(QCIssue(
            severity=IssueSeverity.MEDIUM,
            section_id="",
            category="structure",
            description="Lesson is missing a summary/conclusion section.",
            suggested_fix="Add a summary section with key takeaways and next steps.",
            status=IssueStatus.OPEN,
        ))

    if "activity" not in section_types:
        issues.append(QCIssue(
            severity=IssueSeverity.MEDIUM,
            section_id="",
            category="engagement",
            description="Lesson has no hands-on activity section.",
            suggested_fix="Add a practical activity for learners to apply the concepts.",
            status=IssueStatus.OPEN,
        ))

    # Check knowledge check
    if not content.knowledge_check:
        issues.append(QCIssue(
            severity=IssueSeverity.HIGH,
            section_id="",
            category="assessment_issue",
            description="Lesson has no knowledge check questions.",
            suggested_fix="Add 4-6 multiple-choice questions testing the learning objective.",
            status=IssueStatus.OPEN,
        ))
    elif len(content.knowledge_check) < 4:
        issues.append(QCIssue(
            severity=IssueSeverity.LOW,
            section_id="",
            category="assessment_issue",
            description=f"Only {len(content.knowledge_check)} knowledge check questions. Recommend 4-6.",
            suggested_fix="Add more questions for better objective coverage.",
            status=IssueStatus.OPEN,
        ))

    # Check videos
    if not content.videos:
        issues.append(QCIssue(
            severity=IssueSeverity.LOW,
            section_id="",
            category="engagement",
            description="No supplementary videos included in the lesson.",
            suggested_fix="Add 1-2 relevant video resources.",
            status=IssueStatus.OPEN,
        ))

    # Check references
    if not content.references:
        issues.append(QCIssue(
            severity=IssueSeverity.MEDIUM,
            section_id="",
            category="structure",
            description="Lesson has no references section.",
            suggested_fix="Add references to cite the sources used.",
            status=IssueStatus.OPEN,
        ))

    return issues


# ── Build lesson text for LLM analysis ───────────────────────────────────

def _build_lesson_text_for_qc2(run: LessonRun) -> str:
    """Build the full lesson text for QC2 analysis."""
    if run.current_version is None:
        return ""

    content = run.current_version.content
    lines = []

    for section in content.sections:
        word_count = len(section.body_md.split())
        lines.append(
            f"## {section.heading}\n"
            f"Type: {section.type.value} | Time: {section.est_minutes} min | "
            f"Words: {word_count}\n"
        )
        lines.append(section.body_md)
        lines.append("")

    if content.knowledge_check:
        lines.append("## Knowledge Check\n")
        for i, q in enumerate(content.knowledge_check, 1):
            lines.append(f"**Q{i}:** {q.question}")
            for j, opt in enumerate(q.options):
                marker = "✓" if opt == q.correct_answer else " "
                lines.append(f"  [{marker}] {opt}")
            lines.append(f"  **Explanation:** {q.explanation}\n")

    if content.videos:
        lines.append("## Supplementary Videos\n")
        for v in content.videos:
            lines.append(
                f"- [{v.title}]({v.url}) by {v.channel} "
                f"({v.watch_minutes:.0f} min) — {v.why_relevant}"
            )
        lines.append("")

    if content.references:
        lines.append("## References\n")
        for ref in content.references:
            lines.append(f"- [{ref.source_id}] {ref.title} — {ref.url}")
        lines.append("")

    total_words = sum(len(s.body_md.split()) for s in content.sections)
    total_claimed = sum(s.est_minutes for s in content.sections)
    lines.append(f"\n--- Total: {len(content.sections)} sections, {total_words} words, {total_claimed:.0f} claimed minutes ---")

    return "\n".join(lines)


# ── Main QC2 executor ───────────────────────────────────────────────────

async def execute_qc2(run: LessonRun) -> None:
    """Execute QC Layer 2: Instructional Quality audit.

    Runs independently with a separate instructional designer prompt.

    Args:
        run: LessonRun with at least one version of the lesson.
    """
    if run.current_version is None:
        raise ValueError("No lesson version found. Generate the lesson first.")

    logger.info(f"[{run.id}] Starting QC2: Instructional Quality audit...")

    # ── Programmatic checks ──────────────────────────────────────────
    programmatic_issues = []

    time_issues = _check_time_feasibility(run)
    programmatic_issues.extend(time_issues)
    logger.info(f"[{run.id}] Time feasibility: {len(time_issues)} issues")

    structure_issues = _check_section_structure(run)
    programmatic_issues.extend(structure_issues)
    logger.info(f"[{run.id}] Structure check: {len(structure_issues)} issues")

    # ── LLM-based instructional audit ────────────────────────────────
    prompt_path = settings.prompts_dir / "qc2_instructional.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    lesson_text = _build_lesson_text_for_qc2(run)

    prompt = (
        f"LESSON TO EVALUATE:\n"
        f"Title: {run.title}\n"
        f"Learning Objective: {run.objective}\n\n"
        f"{lesson_text}\n\n"
        f"{'='*60}\n\n"
        f"Perform a comprehensive instructional quality audit:\n\n"
        f"1. **Objective Alignment**: Break the objective into components and map each "
        f"to the sections that cover it. Build a coverage matrix.\n"
        f"   Objective: \"{run.objective}\"\n\n"
        f"2. **Clarity & Structure**: Evaluate reading level, logical flow, "
        f"jargon handling, heading structure.\n\n"
        f"3. **Examples & Applications**: Does every concept have a concrete example? "
        f"Are examples practical and varied?\n\n"
        f"4. **Assessment Quality**: Do the knowledge check questions test the objective? "
        f"Are answers correct? Is there a difficulty mix?\n\n"
        f"5. **Time Feasibility**: Recompute time from word counts (~175 wpm). "
        f"Is the total near 45 minutes?\n\n"
        f"6. **Engagement**: Is there a hook? An activity? Are videos tied to content?\n\n"
        f"Score each criterion 1-5, give an overall score 0-10, and list all issues."
    )

    try:
        audit = generate(
            prompt, InstructionalAudit,
            system_prompt=system_prompt,
            temperature=0.15,
            max_tokens=8192,
        )
        logger.info(
            f"[{run.id}] QC2 LLM audit: score={audit.overall_score}, "
            f"{len(audit.criterion_scores)} criteria, {len(audit.issues)} issues"
        )
    except Exception as e:
        logger.error(f"[{run.id}] QC2 LLM audit failed: {e}")
        audit = InstructionalAudit(
            overall_score=5.0,
            summary=f"LLM audit could not be completed: {str(e)}. Programmatic checks were run.",
            criterion_scores=[],
            coverage_matrix=[],
            issues=[],
        )

    # ── Convert LLM issues to QCIssue objects ────────────────────────
    llm_issues = []
    section_id_map = {}
    if run.current_version:
        section_id_map = {
            s.heading.lower(): s.id for s in run.current_version.content.sections
        }

    for llm_issue in audit.issues:
        # Map section heading to ID
        sec_id = ""
        if llm_issue.section_heading:
            sec_id = section_id_map.get(llm_issue.section_heading.lower(), "")

        severity_map = {"high": IssueSeverity.HIGH, "med": IssueSeverity.MEDIUM, "low": IssueSeverity.LOW}
        severity = severity_map.get(llm_issue.severity.lower(), IssueSeverity.MEDIUM)

        issue = QCIssue(
            severity=severity,
            section_id=sec_id,
            category=llm_issue.category,
            description=llm_issue.description,
            evidence=llm_issue.evidence,
            suggested_fix=llm_issue.suggested_fix,
            status=IssueStatus.OPEN,
        )
        llm_issues.append(issue)

    # ── Combine all issues ───────────────────────────────────────────
    all_issues = programmatic_issues + llm_issues

    # ── Build coverage matrix dict ───────────────────────────────────
    coverage_dict = {}
    for entry in audit.coverage_matrix:
        coverage_dict[entry.objective_component] = entry.covered_by_sections
        if entry.coverage_level == "missing":
            # Add an issue for missing coverage
            all_issues.append(QCIssue(
                severity=IssueSeverity.HIGH,
                section_id="",
                category="objective_gap",
                description=f"Objective component '{entry.objective_component}' is not covered by any section.",
                evidence=f"Coverage level: {entry.coverage_level}",
                suggested_fix=f"Add content covering '{entry.objective_component}'.",
                status=IssueStatus.OPEN,
            ))

    # Build the QC report
    report = QCReport(
        layer=2,
        score=audit.overall_score,
        summary=audit.summary,
        issues=all_issues,
        coverage_matrix=coverage_dict,
    )

    run.qc2_report = report

    logger.info(
        f"[{run.id}] QC2 complete: score={report.score}/10, "
        f"{len(all_issues)} total issues "
        f"({len(programmatic_issues)} programmatic, {len(llm_issues)} LLM-detected), "
        f"coverage matrix: {len(coverage_dict)} objective components"
    )
