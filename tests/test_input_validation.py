"""Tests for input validation and error handling.

Covers:
- Empty/whitespace/too-long inputs → clear error messages
- Pydantic schema validation
- API endpoint validation responses
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.schemas import (
    LessonInput,
    LessonRun,
    LessonSection,
    Source,
    SourcePack,
    QCReport,
    QCIssue,
    LessonVersion,
    LessonContent,
    StepName,
    StepStatus,
    SectionType,
    SourceType,
    IssueSeverity,
    IssueStatus,
)
from pydantic import ValidationError


class TestLessonInput:
    """Test input validation for lesson creation."""

    def test_valid_input(self):
        """Valid title and objective should pass."""
        inp = LessonInput(
            title="HTTP Requests and Responses",
            objective="Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories."
        )
        assert inp.title == "HTTP Requests and Responses"
        assert "GET" in inp.objective

    def test_empty_title_rejected(self):
        """Empty title should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LessonInput(title="", objective="A valid objective that is long enough.")
        assert "title" in str(exc_info.value).lower()

    def test_short_title_rejected(self):
        """Title shorter than 3 chars should be rejected."""
        with pytest.raises(ValidationError):
            LessonInput(title="Hi", objective="A valid objective that is long enough.")

    def test_empty_objective_rejected(self):
        """Empty objective should be rejected."""
        with pytest.raises(ValidationError):
            LessonInput(title="Valid Title", objective="")

    def test_short_objective_rejected(self):
        """Objective shorter than 10 chars should be rejected."""
        with pytest.raises(ValidationError):
            LessonInput(title="Valid Title", objective="Short")

    def test_long_title_rejected(self):
        """Title longer than 200 chars should be rejected."""
        with pytest.raises(ValidationError):
            LessonInput(title="A" * 201, objective="A valid objective that is long enough.")

    def test_long_objective_rejected(self):
        """Objective longer than 1000 chars should be rejected."""
        with pytest.raises(ValidationError):
            LessonInput(title="Valid Title", objective="A" * 1001)

    def test_whitespace_only_title(self):
        """Whitespace-only title should be rejected (min_length applies after no strip)."""
        with pytest.raises(ValidationError):
            LessonInput(title="   ", objective="A valid objective that is long enough.")

    def test_special_characters_in_title(self):
        """Title with special characters should be accepted."""
        inp = LessonInput(
            title="HTTP: GET & POST — A Primer",
            objective="Explain the GET and POST HTTP methods."
        )
        assert "HTTP" in inp.title


class TestLessonRun:
    """Test LessonRun model behavior."""

    def test_create_run(self):
        """Creating a run should initialize all steps as pending."""
        run = LessonRun(title="Test", objective="Test objective for the lesson.")
        assert len(run.steps) == 4
        for step in run.steps:
            assert step.status == StepStatus.PENDING

    def test_get_step(self):
        """Should retrieve the correct step by name."""
        run = LessonRun(title="Test", objective="Test objective for the lesson.")
        step = run.get_step(StepName.RESEARCH)
        assert step is not None
        assert step.name == StepName.RESEARCH

    def test_current_version_empty(self):
        """No versions should return None."""
        run = LessonRun(title="Test", objective="Test objective for the lesson.")
        assert run.current_version is None

    def test_current_version_after_add(self):
        """Should return the latest version after adding one."""
        run = LessonRun(title="Test", objective="Test objective for the lesson.")
        content = LessonContent()
        version = LessonVersion(version=1, content=content, label="Test")
        run.versions.append(version)
        assert run.current_version is not None
        assert run.current_version.version == 1

    def test_version_history_preserved(self):
        """Multiple versions should all be preserved."""
        run = LessonRun(title="Test", objective="Test objective for the lesson.")
        for i in range(5):
            content = LessonContent()
            version = LessonVersion(version=i+1, content=content, label=f"v{i+1}")
            run.versions.append(version)
        assert len(run.versions) == 5
        assert run.current_version.version == 5

    def test_run_serialization(self):
        """Run should serialize and deserialize correctly."""
        run = LessonRun(title="Test", objective="Test objective for the lesson.")
        json_str = run.model_dump_json()
        restored = LessonRun.model_validate_json(json_str)
        assert restored.title == run.title
        assert restored.id == run.id


class TestSourcePack:
    """Test source pack model."""

    def test_all_sources(self):
        """all_sources should combine all source types."""
        pack = SourcePack(
            web_sources=[Source(id="W1", type=SourceType.WEB, title="Web")],
            book_sources=[Source(id="B1", type=SourceType.BOOK, title="Book")],
            video_sources=[Source(id="V1", type=SourceType.VIDEO, title="Video")],
        )
        assert len(pack.all_sources) == 3

    def test_empty_source_pack(self):
        """Empty source pack should work."""
        pack = SourcePack()
        assert len(pack.all_sources) == 0
        assert len(pack.key_concepts) == 0


class TestQCReport:
    """Test QC report model."""

    def test_create_report(self):
        """Should create a valid QC report."""
        report = QCReport(
            layer=1,
            score=7.5,
            summary="Good accuracy with minor issues.",
            issues=[
                QCIssue(
                    severity=IssueSeverity.MEDIUM,
                    category="unsupported_claim",
                    description="A test issue",
                )
            ],
        )
        assert report.layer == 1
        assert len(report.issues) == 1
        assert report.issues[0].status == IssueStatus.OPEN

    def test_issue_status_transitions(self):
        """Issue status should transition correctly."""
        issue = QCIssue(
            severity=IssueSeverity.HIGH,
            category="factual_error",
            description="Test",
        )
        assert issue.status == IssueStatus.OPEN

        issue.status = IssueStatus.ACCEPTED
        assert issue.status == IssueStatus.ACCEPTED

        issue.status = IssueStatus.APPLIED
        assert issue.status == IssueStatus.APPLIED

    def test_score_bounds(self):
        """Score should be between 0 and 10."""
        report = QCReport(layer=1, score=10.0, summary="Perfect")
        assert report.score == 10.0

        with pytest.raises(ValidationError):
            QCReport(layer=1, score=11.0, summary="Too high")

        with pytest.raises(ValidationError):
            QCReport(layer=1, score=-1.0, summary="Negative")

