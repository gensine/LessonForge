"""Pydantic models for the entire application data model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────

class StepName(str, Enum):
    RESEARCH = "research"
    GENERATE = "generate"
    QC1 = "qc1"
    QC2 = "qc2"
    DONE = "done"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class SourceType(str, Enum):
    WEB = "web"
    BOOK = "book"
    VIDEO = "video"


class SectionType(str, Enum):
    INTRO = "intro"
    CONCEPT = "concept"
    EXAMPLE = "example"
    ACTIVITY = "activity"
    KNOWLEDGE_CHECK = "knowledge_check"
    SUMMARY = "summary"


class IssueSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "med"
    LOW = "low"


class IssueStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


# ── Input schemas ──────────────────────────────────────────────────────────

class LessonInput(BaseModel):
    """User input to create a new lesson."""
    title: str = Field(..., min_length=3, max_length=200, description="Lesson title")
    objective: str = Field(..., min_length=10, max_length=1000, description="Learning objective")

    @field_validator("title")
    @classmethod
    def validate_title_not_whitespace(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters.")
        return trimmed

    @field_validator("objective")
    @classmethod
    def validate_objective_not_whitespace(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 10:
            raise ValueError("Objective must contain at least 10 non-whitespace characters.")
        return trimmed


# ── Source models ──────────────────────────────────────────────────────────

class Source(BaseModel):
    """A research source (web page, book, or video)."""
    id: str = Field(default_factory=lambda: f"S{uuid.uuid4().hex[:6]}")
    type: SourceType
    title: str
    url: str = ""
    author: str = ""
    snippet: str = ""
    extracted_text: str = ""
    reliability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reliability_reason: str = ""
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    used_in_sections: list[str] = Field(default_factory=list)
    # Video-specific
    channel: str = ""
    duration_minutes: float = 0.0
    why_relevant: str = ""
    # Book-specific
    year: str = ""
    isbn: str = ""


class SourcePack(BaseModel):
    """Combined research output with all sources."""
    web_sources: list[Source] = Field(default_factory=list)
    book_sources: list[Source] = Field(default_factory=list)
    video_sources: list[Source] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    research_warnings: list[str] = Field(default_factory=list)

    @property
    def all_sources(self) -> list[Source]:
        return self.web_sources + self.book_sources + self.video_sources


# ── Lesson content models ─────────────────────────────────────────────────

class LessonSection(BaseModel):
    """A single section of the lesson."""
    id: str = Field(default_factory=lambda: f"SEC{uuid.uuid4().hex[:6]}")
    heading: str
    type: SectionType
    body_md: str
    est_minutes: float = Field(ge=0, le=45)
    source_ids: list[str] = Field(default_factory=list)


class VideoEmbed(BaseModel):
    """A recommended video for the lesson."""
    video_id: str
    title: str
    url: str
    channel: str = ""
    why_relevant: str = ""
    watch_minutes: float = 0.0


class KnowledgeQuestion(BaseModel):
    """A knowledge check question."""
    question: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str
    explanation: str


class Reference(BaseModel):
    """A reference entry for the lesson."""
    source_id: str
    type: SourceType
    title: str
    url: str = ""
    author: str = ""
    detail: str = ""


class LessonContent(BaseModel):
    """The full lesson content."""
    sections: list[LessonSection] = Field(default_factory=list)
    videos: list[VideoEmbed] = Field(default_factory=list)
    knowledge_check: list[KnowledgeQuestion] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    total_minutes: float = 0.0


# ── QC models ─────────────────────────────────────────────────────────────

class QCIssue(BaseModel):
    """A single issue found during quality check."""
    id: str = Field(default_factory=lambda: f"ISS{uuid.uuid4().hex[:6]}")
    severity: IssueSeverity
    section_id: str = ""
    category: str
    description: str
    evidence: str = ""
    suggested_fix: str = ""
    status: IssueStatus = IssueStatus.OPEN


class QCReport(BaseModel):
    """Quality check report (for either QC1 or QC2)."""
    layer: int = Field(ge=1, le=2)
    score: float = Field(ge=0.0, le=10.0)
    summary: str
    issues: list[QCIssue] = Field(default_factory=list)
    # QC2-specific
    coverage_matrix: dict[str, list[str]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Lesson run (top-level) ────────────────────────────────────────────────

class StepInfo(BaseModel):
    """Status of a single pipeline step."""
    name: StepName
    status: StepStatus = StepStatus.PENDING
    error_message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class LessonVersion(BaseModel):
    """A versioned snapshot of lesson content."""
    version: int
    content: LessonContent
    label: str = ""  # e.g., "AI Draft", "After QC1 fixes", "Manual edit"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LessonRun(BaseModel):
    """Top-level lesson creation run."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    objective: str
    status: StepName = StepName.RESEARCH
    steps: list[StepInfo] = Field(default_factory=lambda: [
        StepInfo(name=StepName.RESEARCH),
        StepInfo(name=StepName.GENERATE),
        StepInfo(name=StepName.QC1),
        StepInfo(name=StepName.QC2),
    ])
    source_pack: Optional[SourcePack] = None
    versions: list[LessonVersion] = Field(default_factory=list)
    qc1_report: Optional[QCReport] = None
    qc2_report: Optional[QCReport] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_used: str = ""
    error_log: list[str] = Field(default_factory=list)

    @property
    def current_version(self) -> Optional[LessonVersion]:
        return self.versions[-1] if self.versions else None

    def get_step(self, name: StepName) -> Optional[StepInfo]:
        for step in self.steps:
            if step.name == name:
                return step
        return None


# ── API response models ───────────────────────────────────────────────────

class LessonRunSummary(BaseModel):
    """Summary of a lesson run for list views."""
    id: str
    title: str
    objective: str
    status: StepName
    step_statuses: dict[str, str] = Field(default_factory=dict)
    version_count: int = 0
    created_at: datetime
    updated_at: datetime


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: str = ""
    retry_allowed: bool = False

