"""SQLite database layer using SQLAlchemy for persistence.

Stores lesson runs as JSON blobs in SQLite. Each run is a single row
with the full LessonRun model serialized. Versions are stored inline.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, String, Text, DateTime, create_engine, Integer
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.schemas import LessonRun, LessonRunSummary


logger = logging.getLogger(__name__)

# ── SQLAlchemy models ─────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class LessonRunRow(Base):
    """SQLite row storing a full lesson run as JSON."""
    __tablename__ = "lesson_runs"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    objective = Column(Text, nullable=False)
    data_json = Column(Text, nullable=False)  # Full LessonRun as JSON
    version_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Database manager ──────────────────────────────────────────────────────

class Database:
    """Manages SQLite database operations for lesson runs."""

    def __init__(self, db_path: str = "lesson_creator.db"):
        db_file = Path(db_path).resolve()
        self.engine = create_engine(f"sqlite:///{db_file}", echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info(f"Database initialized at {db_file}")

    def _get_session(self) -> Session:
        return self.SessionLocal()

    def save_run(self, run: LessonRun) -> None:
        """Save or update a lesson run."""
        run.updated_at = datetime.utcnow()
        data_json = run.model_dump_json()

        with self._get_session() as session:
            existing = session.get(LessonRunRow, run.id)
            if existing:
                existing.title = run.title
                existing.objective = run.objective
                existing.data_json = data_json
                existing.version_count = len(run.versions)
                existing.updated_at = run.updated_at
            else:
                row = LessonRunRow(
                    id=run.id,
                    title=run.title,
                    objective=run.objective,
                    data_json=data_json,
                    version_count=len(run.versions),
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                )
                session.add(row)
            session.commit()
            logger.info(f"Saved lesson run {run.id}")

    def get_run(self, run_id: str) -> Optional[LessonRun]:
        """Retrieve a lesson run by ID."""
        with self._get_session() as session:
            row = session.get(LessonRunRow, run_id)
            if row is None:
                return None
            return LessonRun.model_validate_json(row.data_json)

    def list_runs(self) -> list[LessonRunSummary]:
        """List all lesson runs (summary view)."""
        with self._get_session() as session:
            rows = session.query(LessonRunRow).order_by(
                LessonRunRow.updated_at.desc()
            ).all()

            summaries = []
            for row in rows:
                run = LessonRun.model_validate_json(row.data_json)
                step_statuses = {
                    step.name.value: step.status.value for step in run.steps
                }
                summaries.append(LessonRunSummary(
                    id=run.id,
                    title=run.title,
                    objective=run.objective,
                    status=run.status,
                    step_statuses=step_statuses,
                    version_count=len(run.versions),
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                ))
            return summaries

    def delete_run(self, run_id: str) -> bool:
        """Delete a lesson run."""
        with self._get_session() as session:
            row = session.get(LessonRunRow, run_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.info(f"Deleted lesson run {run_id}")
            return True


# ── Singleton database instance ───────────────────────────────────────────

_db: Optional[Database] = None


def get_db() -> Database:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db

