"""QC Layer 1: Research & Factual Accuracy audit.

Runs as a SEPARATE prompt/call with fresh context, independent of the writer.
Uses an adversarial system prompt to actively find errors.

Checks:
1. Claim extraction and verification against source pack
2. Source audit (reliability + correct citation)
3. Gaps/inconsistencies detection
4. Programmatic checks (URL validation, cited ID existence, video ID validity)
"""

import logging
import re
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import (
    LessonRun,
    QCReport,
    QCIssue,
    IssueSeverity,
    IssueStatus,
    SourceType,
)
from backend.llm import generate

logger = logging.getLogger(__name__)


# ── QC1 LLM output schemas ──────────────────────────────────────────────

class ClaimVerification(BaseModel):
    """Verification result for a single factual claim."""
    claim: str = Field(description="The exact claim from the lesson")
    section_heading: str = Field(description="Which section contains this claim")
    source_id_cited: str = Field(default="", description="Source ID cited for this claim")
    verification: str = Field(description="supported | partially_supported | unsupported | contradicted")
    evidence: str = Field(description="Evidence from the source pack, or 'no evidence found'")
    issue: str = Field(default="", description="Description of the problem, if any")


class QC1Issue(BaseModel):
    """A factual/research issue found during QC1."""
    severity: str = Field(description="high | med | low")
    section_id: str = Field(default="")
    section_heading: str = Field(default="")
    category: str = Field(description="e.g., factual_error, unsupported_claim, weak_source, missing_concept, broken_link")
    description: str
    evidence: str = Field(default="")
    suggested_fix: str = Field(default="")


class FactualAudit(BaseModel):
    """Complete QC1 audit result."""
    score: float = Field(ge=0.0, le=10.0, description="Overall factual accuracy score")
    summary: str = Field(description="Executive summary of the audit findings")
    claims: list[ClaimVerification] = Field(default_factory=list)
    missing_concepts: list[str] = Field(
        default_factory=list,
        description="Key concepts from the objective that are missing from the lesson"
    )
    issues: list[QC1Issue] = Field(default_factory=list)


# ── Programmatic checks ──────────────────────────────────────────────────

def _check_cited_ids(run: LessonRun) -> list[QCIssue]:
    """Verify every cited source ID actually exists in the source pack."""
    issues = []
    if run.source_pack is None or run.current_version is None:
        return issues

    valid_ids = {src.id for src in run.source_pack.all_sources}

    for section in run.current_version.content.sections:
        # Find all [W1], [B2], [V3] style citations
        cited = re.findall(r'\[([WBV]\d+)\]', section.body_md)
        for cid in cited:
            if cid not in valid_ids:
                issues.append(QCIssue(
                    id=f"ISS_CID_{cid}",
                    severity=IssueSeverity.HIGH,
                    section_id=section.id,
                    category="invalid_citation",
                    description=f"Source [{cid}] is cited but does not exist in the source pack.",
                    evidence=f"Section '{section.heading}' references [{cid}]",
                    suggested_fix=f"Remove the [{cid}] citation or replace with a valid source ID.",
                    status=IssueStatus.OPEN,
                ))

    return issues


async def _check_urls(run: LessonRun) -> list[QCIssue]:
    """Verify that source URLs resolve (HTTP 200)."""
    issues = []
    if run.source_pack is None:
        return issues

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for src in run.source_pack.all_sources:
            if not src.url:
                continue
            try:
                response = await client.head(src.url)
                if response.status_code >= 400:
                    issues.append(QCIssue(
                        id=f"ISS_URL_{src.id}",
                        severity=IssueSeverity.MEDIUM,
                        section_id="",
                        category="broken_link",
                        description=f"Source [{src.id}] URL returns HTTP {response.status_code}: {src.url}",
                        evidence=f"HTTP HEAD request returned status {response.status_code}",
                        suggested_fix="Remove this source or replace with a working URL.",
                        status=IssueStatus.OPEN,
                    ))
            except Exception as e:
                issues.append(QCIssue(
                    id=f"ISS_URL_{src.id}",
                    severity=IssueSeverity.LOW,
                    section_id="",
                    category="unreachable_link",
                    description=f"Source [{src.id}] URL could not be reached: {src.url}",
                    evidence=f"Error: {str(e)[:200]}",
                    suggested_fix="Verify this URL is correct and accessible.",
                    status=IssueStatus.OPEN,
                ))

    return issues


def _check_youtube_ids(run: LessonRun) -> list[QCIssue]:
    """Verify YouTube video IDs are valid format."""
    issues = []
    if run.current_version is None:
        return issues

    for video in run.current_version.content.videos:
        vid_id = video.video_id
        # YouTube video IDs are 11 characters, alphanumeric + dash + underscore
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', vid_id):
            issues.append(QCIssue(
                id=f"ISS_VID_{vid_id[:8]}",
                severity=IssueSeverity.MEDIUM,
                section_id="",
                category="invalid_video_id",
                description=f"YouTube video ID '{vid_id}' appears invalid (should be 11 chars).",
                evidence=f"Video: {video.title}",
                suggested_fix="Verify this video ID is correct.",
                status=IssueStatus.OPEN,
            ))

    return issues


# ── Build lesson text for LLM analysis ───────────────────────────────────

def _build_lesson_text(run: LessonRun) -> str:
    """Build the full lesson text for QC analysis."""
    if run.current_version is None:
        return ""

    content = run.current_version.content
    lines = []

    for section in content.sections:
        lines.append(f"## {section.heading} ({section.type.value}, {section.est_minutes} min)")
        lines.append(section.body_md)
        lines.append(f"[Source IDs: {', '.join(section.source_ids)}]")
        lines.append("")

    if content.knowledge_check:
        lines.append("## Knowledge Check")
        for i, q in enumerate(content.knowledge_check, 1):
            lines.append(f"Q{i}: {q.question}")
            for opt in q.options:
                lines.append(f"  - {opt}")
            lines.append(f"  Correct: {q.correct_answer}")
            lines.append(f"  Explanation: {q.explanation}")
            lines.append("")

    return "\n".join(lines)


def _build_source_pack_text(run: LessonRun) -> str:
    """Build source pack text for QC cross-referencing."""
    if run.source_pack is None:
        return ""

    lines = ["SOURCE PACK FOR VERIFICATION:\n"]

    for src in run.source_pack.all_sources:
        lines.append(f"--- [{src.id}] {src.title} ---")
        lines.append(f"Type: {src.type.value} | URL: {src.url}")
        lines.append(f"Reliability: {src.reliability_score:.1f} — {src.reliability_reason}")

        if src.extracted_text:
            lines.append(f"Content:\n{src.extracted_text[:2000]}")
        elif src.snippet:
            lines.append(f"Snippet: {src.snippet}")

        lines.append("")

    return "\n".join(lines)


# ── Main QC1 executor ───────────────────────────────────────────────────

async def execute_qc1(run: LessonRun) -> None:
    """Execute QC Layer 1: Research & Factual Accuracy audit.

    Runs independently from the writer with a fresh, adversarial prompt.

    Args:
        run: LessonRun with at least one version of the lesson.
    """
    if run.current_version is None:
        raise ValueError("No lesson version found. Generate the lesson first.")

    logger.info(f"[{run.id}] Starting QC1: Factual Accuracy audit...")

    # ── Programmatic checks (no LLM needed) ──────────────────────────
    programmatic_issues = []

    # Check cited source IDs exist
    cid_issues = _check_cited_ids(run)
    programmatic_issues.extend(cid_issues)
    logger.info(f"[{run.id}] Citation check: {len(cid_issues)} issues")

    # Check URLs resolve
    try:
        url_issues = await _check_urls(run)
        programmatic_issues.extend(url_issues)
        logger.info(f"[{run.id}] URL check: {len(url_issues)} issues")
    except Exception as e:
        logger.warning(f"[{run.id}] URL validation skipped: {e}")

    # Check YouTube video IDs
    vid_issues = _check_youtube_ids(run)
    programmatic_issues.extend(vid_issues)
    logger.info(f"[{run.id}] Video ID check: {len(vid_issues)} issues")

    # ── LLM-based factual audit ──────────────────────────────────────
    prompt_path = settings.prompts_dir / "qc1_factual.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    lesson_text = _build_lesson_text(run)
    source_text = _build_source_pack_text(run)

    prompt = (
        f"LESSON TO AUDIT:\n"
        f"Title: {run.title}\n"
        f"Objective: {run.objective}\n"
        f"Key concepts: {', '.join(run.source_pack.key_concepts) if run.source_pack else 'N/A'}\n\n"
        f"{lesson_text}\n\n"
        f"{'='*60}\n\n"
        f"{source_text}\n\n"
        f"{'='*60}\n\n"
        f"Perform a thorough factual accuracy audit:\n"
        f"1. Extract and verify every factual claim against the source pack\n"
        f"2. Check if cited sources actually support the claims made\n"
        f"3. Identify any missing key concepts from the objective\n"
        f"4. Flag weak sources used for critical claims\n"
        f"5. Find conflicting statements across sections\n"
        f"6. Score overall accuracy 0-10\n\n"
        f"Be adversarial — try to find errors. Quote exact sentences."
    )

    try:
        audit = generate(
            prompt, FactualAudit,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=8192,
        )
        logger.info(
            f"[{run.id}] QC1 LLM audit: score={audit.score}, "
            f"{len(audit.claims)} claims, {len(audit.issues)} issues"
        )
    except Exception as e:
        logger.error(f"[{run.id}] QC1 LLM audit failed: {e}")
        audit = FactualAudit(
            score=5.0,
            summary=f"LLM audit could not be completed: {str(e)}. Programmatic checks were run.",
            claims=[],
            missing_concepts=[],
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
        # Map section heading to section ID
        sec_id = llm_issue.section_id or llm_issue.section_heading
        if llm_issue.section_heading:
            sec_id = section_id_map.get(llm_issue.section_heading.lower(), sec_id)

        # Map severity string to enum
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

    # Add missing concept issues
    for concept in audit.missing_concepts:
        llm_issues.append(QCIssue(
            severity=IssueSeverity.HIGH,
            section_id="",
            category="missing_concept",
            description=f"Key concept '{concept}' from the objective is not covered in the lesson.",
            evidence=f"Objective: {run.objective}",
            suggested_fix=f"Add a section or expand an existing section to cover '{concept}'.",
            status=IssueStatus.OPEN,
        ))

    # ── Combine all issues ───────────────────────────────────────────
    all_issues = programmatic_issues + llm_issues

    # Build the QC report
    report = QCReport(
        layer=1,
        score=audit.score,
        summary=audit.summary,
        issues=all_issues,
    )

    run.qc1_report = report

    logger.info(
        f"[{run.id}] QC1 complete: score={report.score}/10, "
        f"{len(all_issues)} total issues "
        f"({len(programmatic_issues)} programmatic, {len(llm_issues)} LLM-detected)"
    )

