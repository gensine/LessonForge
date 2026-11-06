"""FastAPI application with all API routes for the Lesson Creator."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.db import get_db
from backend.schemas import (
    LessonInput,
    LessonRun,
    LessonRunSummary,
    LessonContent,
    LessonSection,
    LessonVersion,
    QCReport,
    QCIssue,
    StepName,
    StepStatus,
    IssueStatus,
    ErrorResponse,
)
from backend.step_runner import StepRunner

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.logs_dir / "app.log"),
    ],
)
logger = logging.getLogger(__name__)


# ── App lifecycle ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    logger.info("Starting Lesson Creator API...")
    get_db()  # Initialize DB
    logger.info("Database ready.")
    yield
    logger.info("Shutting down Lesson Creator API.")


# ── FastAPI app ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Kalvium Lesson Creator",
    description="AI-powered lesson creation tool with research, generation, and quality checks",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
    }


# ── Lesson CRUD ───────────────────────────────────────────────────────────

@app.post("/api/lessons", response_model=LessonRun)
async def create_lesson(input_data: LessonInput):
    """Create a new lesson run with validated input."""
    # Additional validation beyond Pydantic
    title = input_data.title.strip()
    objective = input_data.objective.strip()

    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be empty or whitespace only.")
    if not objective:
        raise HTTPException(status_code=422, detail="Objective cannot be empty or whitespace only.")

    run = LessonRun(
        title=title,
        objective=objective,
        model_used=f"{settings.llm_provider}/{settings.llm_model}",
    )

    db = get_db()
    db.save_run(run)
    logger.info(f"Created lesson run {run.id}: '{title}'")
    return run


@app.get("/api/lessons", response_model=list[LessonRunSummary])
async def list_lessons():
    """List all lesson runs."""
    db = get_db()
    return db.list_runs()


@app.get("/api/lessons/{run_id}", response_model=LessonRun)
async def get_lesson(run_id: str):
    """Get a specific lesson run with all data."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Lesson run '{run_id}' not found.")
    return run


@app.delete("/api/lessons/{run_id}")
async def delete_lesson(run_id: str):
    """Delete a lesson run."""
    db = get_db()
    if not db.delete_run(run_id):
        raise HTTPException(status_code=404, detail=f"Lesson run '{run_id}' not found.")
    return {"message": f"Lesson run '{run_id}' deleted."}


# ── Pipeline execution ────────────────────────────────────────────────────

@app.post("/api/lessons/{run_id}/research")
async def run_research(run_id: str):
    """Execute the research step for a lesson."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    try:
        from backend.research.pipeline import execute_research
        runner = StepRunner(run)
        await runner.execute(StepName.RESEARCH, execute_research)
        return db.get_run(run_id)
    except Exception as e:
        logger.error(f"Research failed: {e}")
        raise HTTPException(status_code=500, detail=f"Research step failed: {str(e)}")


@app.post("/api/lessons/{run_id}/generate")
async def run_generate(run_id: str):
    """Execute the lesson generation step."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    research_step = run.get_step(StepName.RESEARCH)
    if research_step is None or research_step.status != StepStatus.SUCCESS:
        raise HTTPException(status_code=400, detail="Research must complete before generation.")

    try:
        from backend.generation.writer import execute_generation
        runner = StepRunner(run)
        await runner.execute(StepName.GENERATE, execute_generation)
        return db.get_run(run_id)
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generation step failed: {str(e)}")


@app.post("/api/lessons/{run_id}/qc1")
async def run_qc1(run_id: str):
    """Execute QC Layer 1 (factual accuracy)."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    gen_step = run.get_step(StepName.GENERATE)
    if gen_step is None or gen_step.status != StepStatus.SUCCESS:
        raise HTTPException(status_code=400, detail="Generation must complete before QC1.")

    try:
        from backend.qc.qc1_factual import execute_qc1
        runner = StepRunner(run)
        await runner.execute(StepName.QC1, execute_qc1)
        return db.get_run(run_id)
    except Exception as e:
        logger.error(f"QC1 failed: {e}")
        raise HTTPException(status_code=500, detail=f"QC1 step failed: {str(e)}")


@app.post("/api/lessons/{run_id}/qc2")
async def run_qc2(run_id: str):
    """Execute QC Layer 2 (instructional quality)."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    gen_step = run.get_step(StepName.GENERATE)
    if gen_step is None or gen_step.status != StepStatus.SUCCESS:
        raise HTTPException(status_code=400, detail="Generation must complete before QC2.")

    try:
        from backend.qc.qc2_instructional import execute_qc2
        runner = StepRunner(run)
        await runner.execute(StepName.QC2, execute_qc2)
        return db.get_run(run_id)
    except Exception as e:
        logger.error(f"QC2 failed: {e}")
        raise HTTPException(status_code=500, detail=f"QC2 step failed: {str(e)}")


# ── Section editing ───────────────────────────────────────────────────────

@app.put("/api/lessons/{run_id}/sections/{section_id}")
async def update_section(run_id: str, section_id: str, section: LessonSection):
    """Update a specific section and create a new version."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    current = run.current_version
    if current is None:
        raise HTTPException(status_code=400, detail="No lesson version exists yet.")

    # Find and update the section in the current content
    new_content = current.content.model_copy(deep=True)
    found = False
    for i, sec in enumerate(new_content.sections):
        if sec.id == section_id:
            new_content.sections[i] = section
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found.")

    # Create new version
    new_version = LessonVersion(
        version=len(run.versions) + 1,
        content=new_content,
        label="Manual edit",
    )
    run.versions.append(new_version)
    db.save_run(run)

    return {"message": "Section updated", "version": new_version.version}


# ── QC issue management ──────────────────────────────────────────────────

@app.put("/api/lessons/{run_id}/qc/{layer}/issues/{issue_id}")
async def update_issue_status(
    run_id: str, layer: int, issue_id: str, status: IssueStatus
):
    """Accept or reject a QC issue."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    report = run.qc1_report if layer == 1 else run.qc2_report
    if report is None:
        raise HTTPException(status_code=400, detail=f"QC{layer} report not found.")

    for issue in report.issues:
        if issue.id == issue_id:
            issue.status = status
            db.save_run(run)
            return {"message": f"Issue {issue_id} status updated to {status.value}"}

    raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found.")


@app.post("/api/lessons/{run_id}/apply-fixes")
async def apply_accepted_fixes(run_id: str):
    """Apply all accepted QC recommendations using the LLM."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    try:
        from backend.qc.apply import apply_fixes
        result = apply_fixes(run)
        db.save_run(run)
        return result
    except Exception as e:
        logger.error(f"Apply fixes failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to apply fixes: {str(e)}")


# ── Version management ────────────────────────────────────────────────────

@app.get("/api/lessons/{run_id}/versions")
async def list_versions(run_id: str):
    """List all versions of a lesson."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    return [
        {
            "version": v.version,
            "label": v.label,
            "created_at": v.created_at,
            "section_count": len(v.content.sections),
            "total_minutes": sum(s.est_minutes for s in v.content.sections),
        }
        for v in run.versions
    ]


@app.post("/api/lessons/{run_id}/versions/{version_num}/restore")
async def restore_version(run_id: str, version_num: int):
    """Restore a previous version (creates a new version from it)."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    target = None
    for v in run.versions:
        if v.version == version_num:
            target = v
            break

    if target is None:
        raise HTTPException(status_code=404, detail=f"Version {version_num} not found.")

    restored = LessonVersion(
        version=len(run.versions) + 1,
        content=target.content.model_copy(deep=True),
        label=f"Restored from v{version_num}",
    )
    run.versions.append(restored)
    db.save_run(run)

    return {"message": f"Restored version {version_num} as v{restored.version}"}


# ── Export ────────────────────────────────────────────────────────────────

@app.post("/api/lessons/{run_id}/export")
async def export_lesson(run_id: str):
    """Export the lesson as a bundle (Markdown + reports)."""
    db = get_db()
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lesson run not found.")

    try:
        from backend.export.exporter import export_bundle
        result = export_bundle(run)
        return result
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@app.get("/api/exports/{filename}")
async def download_export(filename: str):
    """Download an exported file."""
    filepath = settings.exports_dir / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Export file not found.")
    return FileResponse(filepath, filename=filename)


# ── Run the app ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

