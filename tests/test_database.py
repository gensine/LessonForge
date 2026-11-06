"""Tests for the database layer.

Covers:
- Save and retrieve lesson runs
- List runs
- Delete runs
- Data persistence across operations
- Version preservation
"""

import pytest
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import Database
from backend.schemas import (
    LessonRun,
    LessonContent,
    LessonVersion,
    LessonSection,
    SectionType,
)


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database = Database(db_path)
    yield database

    # Cleanup
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def sample_run():
    """Create a sample lesson run."""
    return LessonRun(
        title="HTTP Requests and Responses",
        objective="Explain GET and POST methods.",
        model_used="gemini/gemini-2.0-flash",
    )


class TestDatabase:
    """Test database operations."""

    def test_save_and_retrieve(self, db, sample_run):
        """Should save and retrieve a run correctly."""
        db.save_run(sample_run)
        retrieved = db.get_run(sample_run.id)

        assert retrieved is not None
        assert retrieved.id == sample_run.id
        assert retrieved.title == sample_run.title
        assert retrieved.objective == sample_run.objective

    def test_update_run(self, db, sample_run):
        """Should update an existing run."""
        db.save_run(sample_run)
        sample_run.title = "Updated Title"
        db.save_run(sample_run)

        retrieved = db.get_run(sample_run.id)
        assert retrieved.title == "Updated Title"

    def test_list_runs(self, db):
        """Should list all runs."""
        for i in range(3):
            run = LessonRun(
                title=f"Lesson {i}",
                objective=f"Objective for lesson {i} testing.",
            )
            db.save_run(run)

        runs = db.list_runs()
        assert len(runs) == 3

    def test_delete_run(self, db, sample_run):
        """Should delete a run."""
        db.save_run(sample_run)
        assert db.delete_run(sample_run.id) is True
        assert db.get_run(sample_run.id) is None

    def test_delete_nonexistent(self, db):
        """Should return False for nonexistent run."""
        assert db.delete_run("nonexistent") is False

    def test_get_nonexistent(self, db):
        """Should return None for nonexistent run."""
        assert db.get_run("nonexistent") is None

    def test_version_preservation(self, db, sample_run):
        """Versions should be preserved across saves."""
        content = LessonContent(
            sections=[
                LessonSection(
                    heading="Test Section",
                    type=SectionType.CONCEPT,
                    body_md="Test content",
                    est_minutes=5.0,
                )
            ],
            total_minutes=5.0,
        )

        # Add multiple versions
        for i in range(3):
            version = LessonVersion(
                version=i + 1,
                content=content,
                label=f"Version {i + 1}",
            )
            sample_run.versions.append(version)

        db.save_run(sample_run)
        retrieved = db.get_run(sample_run.id)

        assert len(retrieved.versions) == 3
        assert retrieved.current_version.version == 3

    def test_data_integrity(self, db, sample_run):
        """Complex data should survive serialization roundtrip."""
        from backend.schemas import SourcePack, Source, SourceType

        sample_run.source_pack = SourcePack(
            web_sources=[
                Source(
                    id="W1",
                    type=SourceType.WEB,
                    title="MDN Web Docs",
                    url="https://developer.mozilla.org",
                    reliability_score=0.95,
                )
            ],
            key_concepts=["GET", "POST", "status codes"],
        )

        db.save_run(sample_run)
        retrieved = db.get_run(sample_run.id)

        assert retrieved.source_pack is not None
        assert len(retrieved.source_pack.web_sources) == 1
        assert retrieved.source_pack.web_sources[0].reliability_score == 0.95
        assert "GET" in retrieved.source_pack.key_concepts

