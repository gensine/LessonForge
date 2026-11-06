"""Tests for the export module."""

import pytest
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.schemas import (
    LessonRun,
    LessonContent,
    LessonVersion,
    LessonSection,
    VideoEmbed,
    KnowledgeQuestion,
    Reference,
    QCReport,
    QCIssue,
    SectionType,
    SourceType,
    IssueSeverity,
)
from backend.export.exporter import (
    _generate_lesson_md,
    _generate_references_md,
    _generate_references_csv,
    _generate_qc_report_md,
)


@pytest.fixture
def sample_run():
    """Create a complete sample run for export testing."""
    run = LessonRun(
        title="HTTP Requests and Responses",
        objective="Explain GET and POST methods.",
        model_used="gemini/gemini-2.0-flash",
    )

    content = LessonContent(
        sections=[
            LessonSection(
                id="SEC1",
                heading="Introduction to HTTP",
                type=SectionType.INTRO,
                body_md="HTTP is the foundation of web communication. [W1]",
                est_minutes=3,
                source_ids=["W1"],
            ),
            LessonSection(
                id="SEC2",
                heading="GET Method",
                type=SectionType.CONCEPT,
                body_md="GET retrieves data from a server. [W1] [W2]",
                est_minutes=8,
                source_ids=["W1", "W2"],
            ),
        ],
        videos=[
            VideoEmbed(
                video_id="dQw4w9WgXcQ",
                title="HTTP Explained",
                url="https://youtube.com/watch?v=dQw4w9WgXcQ",
                channel="TechChannel",
                why_relevant="Covers HTTP basics",
                watch_minutes=5,
            )
        ],
        knowledge_check=[
            KnowledgeQuestion(
                question="What does GET do?",
                options=["Retrieves data", "Sends data", "Deletes data", "Updates data"],
                correct_answer="Retrieves data",
                explanation="GET requests retrieve resources from the server.",
            )
        ],
        references=[
            Reference(
                source_id="W1",
                type=SourceType.WEB,
                title="MDN HTTP",
                url="https://developer.mozilla.org/en-US/docs/Web/HTTP",
                detail="Reliability: 0.95",
            ),
            Reference(
                source_id="B1",
                type=SourceType.BOOK,
                title="HTTP: The Definitive Guide",
                url="https://books.google.com/...",
                author="David Gourley",
                detail="David Gourley (2002) ISBN: 1565925092",
            ),
        ],
        total_minutes=11,
    )

    run.versions.append(LessonVersion(version=1, content=content, label="AI Draft"))

    run.qc1_report = QCReport(
        layer=1,
        score=8.0,
        summary="Good accuracy overall.",
        issues=[
            QCIssue(
                severity=IssueSeverity.MEDIUM,
                category="unsupported_claim",
                description="Minor unsupported claim.",
                suggested_fix="Add source citation.",
            )
        ],
    )

    run.qc2_report = QCReport(
        layer=2,
        score=7.5,
        summary="Good instructional quality.",
        issues=[],
        coverage_matrix={
            "Explain GET": ["GET Method"],
            "Explain POST": [],
        },
    )

    return run


class TestLessonExport:
    """Test lesson markdown generation."""

    def test_lesson_md_contains_title(self, sample_run):
        md = _generate_lesson_md(sample_run)
        assert "HTTP Requests and Responses" in md

    def test_lesson_md_contains_sections(self, sample_run):
        md = _generate_lesson_md(sample_run)
        assert "Introduction to HTTP" in md
        assert "GET Method" in md

    def test_lesson_md_contains_knowledge_check(self, sample_run):
        md = _generate_lesson_md(sample_run)
        assert "Knowledge Check" in md
        assert "What does GET do?" in md

    def test_lesson_md_contains_references(self, sample_run):
        md = _generate_lesson_md(sample_run)
        assert "References" in md
        assert "MDN HTTP" in md

    def test_lesson_md_contains_videos(self, sample_run):
        md = _generate_lesson_md(sample_run)
        assert "HTTP Explained" in md

    def test_lesson_md_contains_metadata(self, sample_run):
        md = _generate_lesson_md(sample_run)
        assert "gemini" in md.lower()
        assert "Version" in md


class TestReferencesExport:
    """Test references export."""

    def test_references_md_groups_by_type(self, sample_run):
        md = _generate_references_md(sample_run)
        assert "Web Sources" in md
        assert "Books" in md

    def test_references_csv_format(self, sample_run):
        csv = _generate_references_csv(sample_run)
        lines = csv.strip().split("\n")
        assert lines[0] == "id,type,title,url,author,detail"
        assert len(lines) >= 2  # Header + at least 1 row

    def test_books_marked_as_reference_only(self, sample_run):
        md = _generate_references_md(sample_run)
        assert "not scraped" in md.lower() or "reference only" in md.lower()


class TestQCReportExport:
    """Test QC report export."""

    def test_qc1_report_has_score(self, sample_run):
        md = _generate_qc_report_md(sample_run, layer=1)
        assert "8" in md
        assert "10" in md

    def test_qc1_report_has_issues(self, sample_run):
        md = _generate_qc_report_md(sample_run, layer=1)
        assert "unsupported_claim" in md

    def test_qc2_report_has_coverage_matrix(self, sample_run):
        md = _generate_qc_report_md(sample_run, layer=2)
        assert "Coverage Matrix" in md
        assert "Explain GET" in md

    def test_qc2_report_shows_missing_coverage(self, sample_run):
        md = _generate_qc_report_md(sample_run, layer=2)
        assert "Missing" in md or "❌" in md

    def test_missing_qc_report(self, sample_run):
        sample_run.qc1_report = None
        md = _generate_qc_report_md(sample_run, layer=1)
        assert "Not Available" in md


class TestNoContent:
    """Test export with missing content."""

    def test_lesson_md_no_version(self):
        run = LessonRun(title="Empty", objective="No content yet")
        md = _generate_lesson_md(run)
        assert "No lesson content" in md

    def test_references_md_no_version(self):
        run = LessonRun(title="Empty", objective="No content yet")
        md = _generate_references_md(run)
        assert "No references" in md

