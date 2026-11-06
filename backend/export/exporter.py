"""Export module — generates Markdown files, DOCX, and ZIP bundles.

Exports:
- lesson.md — full lesson content
- references.md / references.csv
- qc1_report.md — factual accuracy audit
- qc2_report.md — instructional quality audit
- Metadata: generation date, model used, version number
"""

import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path

from backend.config import settings
from backend.schemas import (
    LessonRun,
    LessonContent,
    QCReport,
    SourceType,
    IssueSeverity,
)

logger = logging.getLogger(__name__)


# ── Markdown generators ─────────────────────────────────────────────────

def _generate_lesson_md(run: LessonRun) -> str:
    """Generate the full lesson as a Markdown document."""
    if run.current_version is None:
        return "# No lesson content available\n"

    content = run.current_version.content
    lines = []

    # Header
    lines.append(f"# {run.title}\n")
    lines.append(f"**Learning Objective:** {run.objective}\n")
    lines.append(f"**Total Duration:** ~{content.total_minutes:.0f} minutes\n")
    lines.append(f"**Generated:** {run.updated_at.strftime('%Y-%m-%d %H:%M')} | "
                 f"**Model:** {run.model_used} | "
                 f"**Version:** {run.current_version.version}\n")
    lines.append("---\n")

    # Table of contents
    lines.append("## Table of Contents\n")
    for i, section in enumerate(content.sections, 1):
        lines.append(f"{i}. [{section.heading}](#{section.heading.lower().replace(' ', '-')}) "
                     f"({section.est_minutes:.0f} min)")
    if content.knowledge_check:
        lines.append(f"{len(content.sections)+1}. [Knowledge Check](#knowledge-check)")
    if content.references:
        lines.append(f"{len(content.sections)+2}. [References](#references)")
    lines.append("\n---\n")

    # Sections
    for section in content.sections:
        lines.append(f"## {section.heading}")
        lines.append(f"*Type: {section.type.value} | Estimated time: {section.est_minutes:.0f} minutes*\n")
        lines.append(section.body_md)
        lines.append("")

    # Supplementary videos
    if content.videos:
        lines.append("## Supplementary Videos\n")
        for video in content.videos:
            lines.append(f"### 🎥 [{video.title}]({video.url})")
            lines.append(f"- **Channel:** {video.channel}")
            lines.append(f"- **Duration:** {video.watch_minutes:.0f} minutes")
            lines.append(f"- **Why relevant:** {video.why_relevant}")
            lines.append("")

    # Knowledge check
    if content.knowledge_check:
        lines.append("## Knowledge Check\n")
        for i, q in enumerate(content.knowledge_check, 1):
            lines.append(f"### Question {i}\n")
            lines.append(f"**{q.question}**\n")
            for j, opt in enumerate(q.options):
                letter = chr(65 + j)  # A, B, C, D
                lines.append(f"  {letter}. {opt}")
            lines.append("")
            lines.append(f"<details><summary>Show Answer</summary>\n")
            lines.append(f"**Correct Answer:** {q.correct_answer}\n")
            lines.append(f"**Explanation:** {q.explanation}")
            lines.append(f"</details>\n")

    # References
    if content.references:
        lines.append("## References\n")
        for ref in content.references:
            if ref.type == SourceType.BOOK:
                lines.append(f"- **[{ref.source_id}]** 📚 *{ref.title}* — {ref.detail}")
                if ref.url:
                    lines.append(f"  [{ref.url}]({ref.url})")
            elif ref.type == SourceType.VIDEO:
                lines.append(f"- **[{ref.source_id}]** 🎥 [{ref.title}]({ref.url}) — {ref.detail}")
            else:
                lines.append(f"- **[{ref.source_id}]** 🌐 [{ref.title}]({ref.url}) — {ref.detail}")
        lines.append("")

    return "\n".join(lines)


def _generate_references_md(run: LessonRun) -> str:
    """Generate a standalone references document."""
    if run.current_version is None:
        return "# No references available\n"

    content = run.current_version.content
    lines = []

    lines.append(f"# References — {run.title}\n")
    lines.append(f"*Generated: {run.updated_at.strftime('%Y-%m-%d %H:%M')}*\n")

    # Group by type
    web_refs = [r for r in content.references if r.type == SourceType.WEB]
    book_refs = [r for r in content.references if r.type == SourceType.BOOK]
    video_refs = [r for r in content.references if r.type == SourceType.VIDEO]

    if web_refs:
        lines.append("## Web Sources\n")
        for ref in web_refs:
            lines.append(f"- **[{ref.source_id}]** [{ref.title}]({ref.url})")
            if ref.detail:
                lines.append(f"  - {ref.detail}")
        lines.append("")

    if book_refs:
        lines.append("## Books\n")
        lines.append("*Note: Books are cited as references only. Content was not scraped (copyright).*\n")
        for ref in book_refs:
            lines.append(f"- **[{ref.source_id}]** *{ref.title}*")
            if ref.detail:
                lines.append(f"  - {ref.detail}")
            if ref.url:
                lines.append(f"  - [View on Google Books]({ref.url})")
        lines.append("")

    if video_refs:
        lines.append("## Videos\n")
        for ref in video_refs:
            lines.append(f"- **[{ref.source_id}]** [{ref.title}]({ref.url})")
            if ref.detail:
                lines.append(f"  - {ref.detail}")
        lines.append("")

    return "\n".join(lines)


def _generate_references_csv(run: LessonRun) -> str:
    """Generate references as CSV."""
    if run.current_version is None:
        return "id,type,title,url,author,detail\n"

    lines = ["id,type,title,url,author,detail"]
    for ref in run.current_version.content.references:
        # Escape commas in fields
        title = ref.title.replace('"', '""')
        detail = ref.detail.replace('"', '""')
        author = ref.author.replace('"', '""')
        lines.append(f'{ref.source_id},{ref.type.value},"{title}",{ref.url},"{author}","{detail}"')

    return "\n".join(lines)


def _generate_qc_report_md(run: LessonRun, layer: int) -> str:
    """Generate a QC report as Markdown."""
    report = run.qc1_report if layer == 1 else run.qc2_report

    if report is None:
        return f"# QC{layer} Report — Not Available\n"

    layer_name = "Factual Accuracy" if layer == 1 else "Instructional Quality"
    lines = []

    lines.append(f"# QC{layer} Report: {layer_name}\n")
    lines.append(f"**Lesson:** {run.title}\n")
    lines.append(f"**Score:** {report.score}/10\n")
    lines.append(f"**Date:** {report.created_at.strftime('%Y-%m-%d %H:%M')}\n")
    lines.append("---\n")

    # Summary
    lines.append("## Summary\n")
    lines.append(report.summary)
    lines.append("")

    # Coverage matrix (QC2 only)
    if layer == 2 and report.coverage_matrix:
        lines.append("## Objective Coverage Matrix\n")
        lines.append("| Objective Component | Covered By Sections | Status |")
        lines.append("|---|---|---|")
        for component, sections in report.coverage_matrix.items():
            status = "✅ Covered" if sections else "❌ Missing"
            sections_str = ", ".join(sections) if sections else "—"
            lines.append(f"| {component} | {sections_str} | {status} |")
        lines.append("")

    # Issues
    if report.issues:
        lines.append("## Issues Found\n")

        # Group by severity
        high = [i for i in report.issues if i.severity == IssueSeverity.HIGH]
        med = [i for i in report.issues if i.severity == IssueSeverity.MEDIUM]
        low = [i for i in report.issues if i.severity == IssueSeverity.LOW]

        if high:
            lines.append(f"### 🔴 High Severity ({len(high)})\n")
            for issue in high:
                lines.append(f"- **[{issue.category}]** {issue.description}")
                if issue.evidence:
                    lines.append(f"  - *Evidence:* {issue.evidence}")
                if issue.suggested_fix:
                    lines.append(f"  - *Fix:* {issue.suggested_fix}")
                lines.append(f"  - *Status:* {issue.status.value}")
                lines.append("")

        if med:
            lines.append(f"### 🟡 Medium Severity ({len(med)})\n")
            for issue in med:
                lines.append(f"- **[{issue.category}]** {issue.description}")
                if issue.evidence:
                    lines.append(f"  - *Evidence:* {issue.evidence}")
                if issue.suggested_fix:
                    lines.append(f"  - *Fix:* {issue.suggested_fix}")
                lines.append(f"  - *Status:* {issue.status.value}")
                lines.append("")

        if low:
            lines.append(f"### 🟢 Low Severity ({len(low)})\n")
            for issue in low:
                lines.append(f"- **[{issue.category}]** {issue.description}")
                if issue.suggested_fix:
                    lines.append(f"  - *Fix:* {issue.suggested_fix}")
                lines.append(f"  - *Status:* {issue.status.value}")
                lines.append("")

        # Summary table
        lines.append("### Issues Summary\n")
        lines.append(f"| Severity | Count | Applied |")
        lines.append(f"|---|---|---|")
        for sev, items in [("High", high), ("Medium", med), ("Low", low)]:
            applied = sum(1 for i in items if i.status.value == "applied")
            lines.append(f"| {sev} | {len(items)} | {applied} |")
        lines.append("")
    else:
        lines.append("## No Issues Found ✅\n")

    return "\n".join(lines)


# ── DOCX generation ─────────────────────────────────────────────────────

def _generate_lesson_docx(run: LessonRun, output_path: Path) -> bool:
    """Generate the lesson as a DOCX file."""
    try:
        from docx import Document
        from docx.shared import Pt, Inches

        doc = Document()

        # Title
        doc.add_heading(run.title, level=0)
        doc.add_paragraph(f"Learning Objective: {run.objective}")
        doc.add_paragraph(
            f"Duration: ~{run.current_version.content.total_minutes:.0f} min | "
            f"Model: {run.model_used} | "
            f"Version: {run.current_version.version} | "
            f"Generated: {run.updated_at.strftime('%Y-%m-%d')}"
        )
        doc.add_page_break()

        content = run.current_version.content

        # Sections
        for section in content.sections:
            doc.add_heading(section.heading, level=1)
            p = doc.add_paragraph(
                f"[{section.type.value} — {section.est_minutes:.0f} min]"
            )
            p.style = doc.styles['Subtitle'] if 'Subtitle' in [s.name for s in doc.styles] else None

            # Add body text (simplified — strips markdown formatting)
            for line in section.body_md.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('### '):
                    doc.add_heading(line[4:], level=3)
                elif line.startswith('## '):
                    doc.add_heading(line[3:], level=2)
                elif line.startswith('- '):
                    doc.add_paragraph(line[2:], style='List Bullet')
                elif line.startswith('```'):
                    continue  # Skip code block markers
                else:
                    doc.add_paragraph(line)

        # Knowledge check
        if content.knowledge_check:
            doc.add_page_break()
            doc.add_heading("Knowledge Check", level=1)
            for i, q in enumerate(content.knowledge_check, 1):
                doc.add_heading(f"Question {i}", level=2)
                doc.add_paragraph(q.question)
                for j, opt in enumerate(q.options):
                    letter = chr(65 + j)
                    doc.add_paragraph(f"{letter}. {opt}", style='List Bullet')
                doc.add_paragraph(f"Answer: {q.correct_answer}")
                doc.add_paragraph(f"Explanation: {q.explanation}")

        # References
        if content.references:
            doc.add_page_break()
            doc.add_heading("References", level=1)
            for ref in content.references:
                doc.add_paragraph(
                    f"[{ref.source_id}] {ref.title} — {ref.url}",
                    style='List Bullet'
                )

        doc.save(str(output_path))
        logger.info(f"DOCX saved: {output_path}")
        return True

    except ImportError:
        logger.warning("python-docx not installed; skipping DOCX export")
        return False
    except Exception as e:
        logger.error(f"DOCX generation failed: {e}")
        return False


# ── ZIP bundle ───────────────────────────────────────────────────────────

def export_bundle(run: LessonRun) -> dict:
    """Export the complete lesson bundle as individual files and a ZIP.

    Creates:
    - lesson.md
    - lesson.docx (if python-docx available)
    - references.md
    - references.csv
    - qc1_report.md
    - qc2_report.md
    - metadata.txt
    - All bundled into a ZIP

    Args:
        run: LessonRun with lesson content and QC reports.

    Returns:
        Dict with file paths and download info.
    """
    if run.current_version is None:
        raise ValueError("No lesson content to export.")

    # Create export directory for this run
    export_dir = settings.exports_dir / run.id
    export_dir.mkdir(parents=True, exist_ok=True)

    files_created = []

    # 1. Lesson Markdown
    lesson_md = _generate_lesson_md(run)
    lesson_md_path = export_dir / "lesson.md"
    lesson_md_path.write_text(lesson_md, encoding="utf-8")
    files_created.append(("lesson.md", str(lesson_md_path)))

    # 2. Lesson DOCX
    lesson_docx_path = export_dir / "lesson.docx"
    if _generate_lesson_docx(run, lesson_docx_path):
        files_created.append(("lesson.docx", str(lesson_docx_path)))

    # 3. References Markdown
    refs_md = _generate_references_md(run)
    refs_md_path = export_dir / "references.md"
    refs_md_path.write_text(refs_md, encoding="utf-8")
    files_created.append(("references.md", str(refs_md_path)))

    # 4. References CSV
    refs_csv = _generate_references_csv(run)
    refs_csv_path = export_dir / "references.csv"
    refs_csv_path.write_text(refs_csv, encoding="utf-8")
    files_created.append(("references.csv", str(refs_csv_path)))

    # 5. QC1 Report
    qc1_md = _generate_qc_report_md(run, layer=1)
    qc1_path = export_dir / "qc1_report.md"
    qc1_path.write_text(qc1_md, encoding="utf-8")
    files_created.append(("qc1_report.md", str(qc1_path)))

    # 6. QC2 Report
    qc2_md = _generate_qc_report_md(run, layer=2)
    qc2_path = export_dir / "qc2_report.md"
    qc2_path.write_text(qc2_md, encoding="utf-8")
    files_created.append(("qc2_report.md", str(qc2_path)))

    # 7. Metadata
    metadata = (
        f"Lesson Creator Export\n"
        f"{'='*40}\n"
        f"Title: {run.title}\n"
        f"Objective: {run.objective}\n"
        f"Run ID: {run.id}\n"
        f"Version: {run.current_version.version}\n"
        f"Version Label: {run.current_version.label}\n"
        f"Model Used: {run.model_used}\n"
        f"Created: {run.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Total Versions: {len(run.versions)}\n"
        f"QC1 Score: {run.qc1_report.score if run.qc1_report else 'N/A'}/10\n"
        f"QC2 Score: {run.qc2_report.score if run.qc2_report else 'N/A'}/10\n"
    )
    meta_path = export_dir / "metadata.txt"
    meta_path.write_text(metadata, encoding="utf-8")
    files_created.append(("metadata.txt", str(meta_path)))

    # 8. Create ZIP bundle
    zip_filename = f"lesson_{run.id}.zip"
    zip_path = settings.exports_dir / zip_filename

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, filepath in files_created:
            zf.write(filepath, name)

    logger.info(
        f"Export complete: {len(files_created)} files + ZIP at {zip_path}"
    )

    return {
        "message": f"Export complete: {len(files_created)} files generated.",
        "zip_file": zip_filename,
        "zip_download_url": f"/api/exports/{zip_filename}",
        "files": [
            {
                "name": name,
                "download_url": f"/api/exports/{run.id}/{name}",
            }
            for name, _ in files_created
        ],
    }
