"""Streamlit frontend for the Kalvium Lesson Creator.

Provides a complete UI for:
- Creating lessons with validated input
- Running the research → generate → QC pipeline
- Viewing research sources with reliability scores
- Previewing the lesson (Markdown → HTML)
- QC report panels with Accept/Reject per issue
- Section editing with version history
- Applying fixes with diff view
- Exporting the lesson bundle
"""

import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from backend.config import settings
from backend.db import get_db
from backend.schemas import (
    LessonRun,
    LessonInput,
    StepName,
    StepStatus,
    IssueStatus,
    IssueSeverity,
    LessonSection,
    LessonVersion,
    SectionType,
)

# ── Page config ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="LessonForge — AI Lesson Creator",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────

st.markdown("""
<style>
    .stApp { max-width: 1400px; margin: 0 auto; }
    .step-success { color: #28a745; font-weight: bold; }
    .step-failed { color: #dc3545; font-weight: bold; }
    .step-running { color: #ffc107; font-weight: bold; }
    .step-pending { color: #6c757d; }
    .severity-high { background-color: #f8d7da; padding: 4px 8px; border-radius: 4px; }
    .severity-med { background-color: #fff3cd; padding: 4px 8px; border-radius: 4px; }
    .severity-low { background-color: #d1ecf1; padding: 4px 8px; border-radius: 4px; }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Session state init ───────────────────────────────────────────────────

if "current_run_id" not in st.session_state:
    st.session_state.current_run_id = None
if "editing_section" not in st.session_state:
    st.session_state.editing_section = None


# ── Helper functions ─────────────────────────────────────────────────────

def get_run() -> LessonRun | None:
    """Get the current lesson run from the database."""
    if st.session_state.current_run_id is None:
        return None
    db = get_db()
    return db.get_run(st.session_state.current_run_id)


def save_run(run: LessonRun):
    """Save the current lesson run."""
    db = get_db()
    db.save_run(run)


def step_icon(status: StepStatus) -> str:
    """Get an icon for a step status."""
    icons = {
        StepStatus.PENDING: "⬜",
        StepStatus.RUNNING: "🔄",
        StepStatus.SUCCESS: "✅",
        StepStatus.FAILED: "❌",
    }
    return icons.get(status, "⬜")


def severity_badge(severity: IssueSeverity) -> str:
    """Get a colored badge for issue severity."""
    badges = {
        IssueSeverity.HIGH: "🔴 HIGH",
        IssueSeverity.MEDIUM: "🟡 MED",
        IssueSeverity.LOW: "🟢 LOW",
    }
    return badges.get(severity, "⚪ ?")


# ── Sidebar ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🎓 LessonForge")
    st.caption("AI-Powered Lesson Creator")
    st.divider()

    # List existing lessons
    st.subheader("📚 Your Lessons")
    db = get_db()
    runs = db.list_runs()

    if runs:
        for run_summary in runs:
            step_icons = " ".join(
                step_icon(StepStatus(s)) for s in run_summary.step_statuses.values()
            )
            label = f"{run_summary.title[:30]}... " if len(run_summary.title) > 30 else run_summary.title
            if st.button(
                f"{label} {step_icons}",
                key=f"run_{run_summary.id}",
                use_container_width=True,
            ):
                st.session_state.current_run_id = run_summary.id
                st.rerun()
    else:
        st.info("No lessons yet. Create one below!")

    st.divider()

    # Config info
    with st.expander("⚙️ Configuration"):
        st.text(f"LLM: {settings.llm_provider}/{settings.llm_model}")
        st.text(f"Tavily: {'✅' if settings.tavily_api_key else '❌'}")
        st.text(f"YouTube: {'✅' if settings.youtube_api_key else '❌'}")
        st.text(f"Books: {'✅' if settings.google_books_api_key else '🟡 (no key)'}")


# ── Main content ─────────────────────────────────────────────────────────

run = get_run()

if run is None:
    # ── CREATE NEW LESSON ────────────────────────────────────────────
    st.header("🎓 Create a New Lesson")
    st.markdown(
        "Enter a **lesson title** and **learning objective** to start. "
        "The AI will research, generate, and quality-check a 45-minute lesson."
    )

    with st.form("create_lesson"):
        title = st.text_input(
            "Lesson Title",
            placeholder="e.g., HTTP Requests and Responses",
            max_chars=200,
        )
        objective = st.text_area(
            "Learning Objective",
            placeholder="e.g., Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.",
            max_chars=1000,
            height=100,
        )
        submitted = st.form_submit_button("🚀 Create Lesson", use_container_width=True)

        if submitted:
            # Validate
            title = title.strip()
            objective = objective.strip()

            if not title or len(title) < 3:
                st.error("❌ Title must be at least 3 characters long.")
            elif not objective or len(objective) < 10:
                st.error("❌ Objective must be at least 10 characters long.")
            else:
                new_run = LessonRun(
                    title=title,
                    objective=objective,
                    model_used=f"{settings.llm_provider}/{settings.llm_model}",
                )
                save_run(new_run)
                st.session_state.current_run_id = new_run.id
                st.success(f"✅ Lesson '{title}' created!")
                st.rerun()

    # Quick start examples
    st.divider()
    st.subheader("💡 Quick Start Examples")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Test 1: HTTP Requests**")
        st.caption("Title: HTTP Requests and Responses")
        st.caption("Objective: Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.")

    with col2:
        st.markdown("**Test 2: Git Branching**")
        st.caption("Title: Git Branching and Merging")
        st.caption("Objective: Explain what a branch is and differentiate merge vs rebase.")

else:
    # ── LESSON WORKSPACE ─────────────────────────────────────────────
    st.header(f"📝 {run.title}")
    st.caption(f"Objective: {run.objective}")

    # Pipeline progress bar
    st.subheader("Pipeline Progress")
    cols = st.columns(4)
    step_names = ["Research", "Generate", "QC1 Factual", "QC2 Instructional"]

    for i, (step_info, name) in enumerate(zip(run.steps, step_names)):
        with cols[i]:
            icon = step_icon(step_info.status)
            st.markdown(f"### {icon} {name}")
            if step_info.status == StepStatus.SUCCESS and step_info.completed_at and step_info.started_at:
                elapsed = (step_info.completed_at - step_info.started_at).total_seconds()
                st.caption(f"✓ {elapsed:.0f}s")
            elif step_info.status == StepStatus.FAILED:
                st.caption(f"❌ {step_info.error_message[:50]}")

    st.divider()

    # ── ACTION BUTTONS ───────────────────────────────────────────────
    tab_pipeline, tab_sources, tab_lesson, tab_qc, tab_edit, tab_export = st.tabs([
        "🔧 Pipeline", "🔍 Sources", "📖 Lesson", "📋 QC Reports", "✏️ Editor", "📦 Export"
    ])

    # ── PIPELINE TAB ─────────────────────────────────────────────────
    with tab_pipeline:
        st.subheader("Run Pipeline Steps")

        col1, col2 = st.columns(2)

        with col1:
            # Research
            research_step = run.get_step(StepName.RESEARCH)
            research_disabled = research_step and research_step.status == StepStatus.RUNNING

            if st.button(
                "🔍 Run Research" if not (research_step and research_step.status == StepStatus.SUCCESS) else "🔄 Re-run Research",
                disabled=research_disabled,
                use_container_width=True,
            ):
                with st.spinner("Researching... (web, books, YouTube)"):
                    try:
                        import asyncio
                        from backend.research.pipeline import execute_research
                        from backend.step_runner import StepRunner

                        runner = StepRunner(run)
                        asyncio.run(runner.execute(StepName.RESEARCH, execute_research))
                        st.success("✅ Research complete!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Research failed: {str(e)}")
                        st.button("🔄 Retry Research", key="retry_research")

            # Generate
            gen_step = run.get_step(StepName.GENERATE)
            gen_ready = research_step and research_step.status == StepStatus.SUCCESS

            if st.button(
                "📝 Generate Lesson" if not (gen_step and gen_step.status == StepStatus.SUCCESS) else "🔄 Re-generate",
                disabled=not gen_ready,
                use_container_width=True,
            ):
                if len(run.versions) > 0:
                    st.info("ℹ️ Regenerating creates a new version draft without overwriting your saved edits.")
                with st.spinner("Generating 45-minute lesson..."):
                    try:
                        import asyncio
                        from backend.generation.writer import execute_generation
                        from backend.step_runner import StepRunner

                        runner = StepRunner(run)
                        asyncio.run(runner.execute(StepName.GENERATE, execute_generation))
                        st.success("✅ Lesson generated as a new version!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Generation failed: {str(e)}")

        with col2:
            # QC1
            qc1_step = run.get_step(StepName.QC1)
            qc1_ready = gen_step and gen_step.status == StepStatus.SUCCESS

            if st.button(
                "🔬 Run QC1 (Factual)",
                disabled=not qc1_ready,
                use_container_width=True,
            ):
                with st.spinner("Running factual accuracy audit..."):
                    try:
                        import asyncio
                        from backend.qc.qc1_factual import execute_qc1
                        from backend.step_runner import StepRunner

                        runner = StepRunner(run)
                        asyncio.run(runner.execute(StepName.QC1, execute_qc1))
                        st.success("✅ QC1 complete!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ QC1 failed: {str(e)}")

            # QC2
            qc2_step = run.get_step(StepName.QC2)

            if st.button(
                "📐 Run QC2 (Instructional)",
                disabled=not qc1_ready,
                use_container_width=True,
            ):
                with st.spinner("Running instructional quality audit..."):
                    try:
                        import asyncio
                        from backend.qc.qc2_instructional import execute_qc2
                        from backend.step_runner import StepRunner

                        runner = StepRunner(run)
                        asyncio.run(runner.execute(StepName.QC2, execute_qc2))
                        st.success("✅ QC2 complete!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ QC2 failed: {str(e)}")

        # Error log
        if run.error_log:
            with st.expander("🔴 Error Log"):
                for err in run.error_log:
                    st.text(err)

    # ── SOURCES TAB ──────────────────────────────────────────────────
    with tab_sources:
        if run.source_pack:
            sp = run.source_pack

            if sp.research_warnings:
                for warning in sp.research_warnings:
                    st.warning(f"⚠️ {warning}")

            st.subheader(f"Key Concepts ({len(sp.key_concepts)})")
            st.markdown(" • ".join(f"**{c}**" for c in sp.key_concepts))

            st.divider()

            # Web sources
            st.subheader(f"🌐 Web Sources ({len(sp.web_sources)})")
            for src in sp.web_sources:
                with st.expander(f"[{src.id}] {src.title} — ⭐ {src.reliability_score:.1f} / 🎯 {src.relevance_score:.1f}"):
                    st.markdown(f"**URL:** [{src.url}]({src.url})")
                    st.markdown(f"**Reliability:** {src.reliability_score:.2f} — {src.reliability_reason}")
                    st.markdown(f"**Relevance:** {src.relevance_score:.2f}")
                    if src.snippet:
                        st.markdown(f"**Snippet:** {src.snippet[:300]}")
                    if src.extracted_text:
                        st.text_area(
                            "Extracted Text",
                            src.extracted_text[:1000],
                            height=150,
                            key=f"src_{src.id}",
                            disabled=True,
                        )

            # Book sources
            st.subheader(f"📚 Books ({len(sp.book_sources)})")
            for src in sp.book_sources:
                with st.expander(f"[{src.id}] {src.title} by {src.author}"):
                    st.markdown(f"**Author:** {src.author}")
                    st.markdown(f"**Year:** {src.year}")
                    if src.isbn:
                        st.markdown(f"**ISBN:** {src.isbn}")
                    if src.url:
                        st.markdown(f"**Link:** [{src.url}]({src.url})")
                    st.info("📝 Books are cited as references only. Content is not scraped (copyright).")

            # Video sources
            st.subheader(f"🎥 Videos ({len(sp.video_sources)})")
            for src in sp.video_sources:
                with st.expander(f"[{src.id}] {src.title} — {src.duration_minutes:.0f} min"):
                    st.markdown(f"**Channel:** {src.channel}")
                    st.markdown(f"**Duration:** {src.duration_minutes:.0f} minutes")
                    st.markdown(f"**Relevance:** {src.relevance_score:.2f} — {src.why_relevant}")
                    st.markdown(f"**URL:** [{src.url}]({src.url})")
        else:
            st.info("Run the Research step first to see sources.")

    # ── LESSON PREVIEW TAB ───────────────────────────────────────────
    with tab_lesson:
        if run.current_version:
            content = run.current_version.content

            # Version selector
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown(
                    f"**Version {run.current_version.version}** — "
                    f"*{run.current_version.label}* — "
                    f"{run.current_version.created_at.strftime('%H:%M:%S')}"
                )
            with col2:
                st.metric("Total Time", f"{content.total_minutes:.0f} min")
            with col3:
                st.metric("Sections", len(content.sections))

            st.divider()

            # Sections
            for section in content.sections:
                with st.expander(
                    f"{'📖' if section.type.value == 'intro' else '💡' if section.type.value == 'concept' else '🔧' if section.type.value == 'activity' else '📝'} "
                    f"{section.heading} ({section.est_minutes:.0f} min)",
                    expanded=False,
                ):
                    st.markdown(section.body_md)
                    if section.source_ids:
                        st.caption(f"Sources: {', '.join(section.source_ids)}")

            # Videos
            if content.videos:
                st.subheader("🎥 Supplementary Videos")
                for video in content.videos:
                    st.markdown(
                        f"**[{video.title}]({video.url})** by {video.channel} "
                        f"({video.watch_minutes:.0f} min) — {video.why_relevant}"
                    )

            # Knowledge check
            if content.knowledge_check:
                st.subheader("❓ Knowledge Check")
                for i, q in enumerate(content.knowledge_check, 1):
                    with st.expander(f"Q{i}: {q.question[:80]}..."):
                        st.markdown(f"**{q.question}**")
                        for j, opt in enumerate(q.options):
                            letter = chr(65 + j)
                            is_correct = opt == q.correct_answer
                            marker = "✅" if is_correct else "⬜"
                            st.markdown(f"{marker} **{letter}.** {opt}")
                        st.success(f"**Explanation:** {q.explanation}")

            # References
            if content.references:
                st.subheader("📚 References")
                for ref in content.references:
                    st.markdown(f"- **[{ref.source_id}]** {ref.title} — [{ref.url}]({ref.url})")
        else:
            st.info("Generate the lesson first to preview it.")

    # ── QC REPORTS TAB ───────────────────────────────────────────────
    with tab_qc:
        qc_tab1, qc_tab2 = st.tabs(["🔬 QC1: Factual Accuracy", "📐 QC2: Instructional Quality"])

        with qc_tab1:
            if run.qc1_report:
                report = run.qc1_report

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Score", f"{report.score}/10")
                with col2:
                    st.metric("Issues", len(report.issues))
                with col3:
                    high_count = sum(1 for i in report.issues if i.severity == IssueSeverity.HIGH)
                    st.metric("High Severity", high_count)

                st.markdown(f"**Summary:** {report.summary}")
                st.divider()

                if report.issues:
                    for issue in report.issues:
                        badge = severity_badge(issue.severity)
                        with st.expander(f"{badge} [{issue.category}] {issue.description[:80]}"):
                            st.markdown(f"**Category:** {issue.category}")
                            st.markdown(f"**Description:** {issue.description}")
                            if issue.evidence:
                                st.markdown(f"**Evidence:** {issue.evidence}")
                            if issue.suggested_fix:
                                st.info(f"💡 **Suggested Fix:** {issue.suggested_fix}")

                            # Accept/Reject buttons
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                if st.button("✅ Accept", key=f"qc1_accept_{issue.id}"):
                                    issue.status = IssueStatus.ACCEPTED
                                    save_run(run)
                                    st.rerun()
                            with col2:
                                if st.button("❌ Reject", key=f"qc1_reject_{issue.id}"):
                                    issue.status = IssueStatus.REJECTED
                                    save_run(run)
                                    st.rerun()
                            with col3:
                                st.markdown(f"Status: **{issue.status.value}**")
                else:
                    st.success("No issues found! 🎉")
            else:
                st.info("Run QC1 to see the factual accuracy report.")

        with qc_tab2:
            if run.qc2_report:
                report = run.qc2_report

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Score", f"{report.score}/10")
                with col2:
                    st.metric("Issues", len(report.issues))
                with col3:
                    high_count = sum(1 for i in report.issues if i.severity == IssueSeverity.HIGH)
                    st.metric("High Severity", high_count)

                st.markdown(f"**Summary:** {report.summary}")

                # Coverage matrix
                if report.coverage_matrix:
                    st.divider()
                    st.subheader("📋 Objective Coverage Matrix")
                    for component, sections in report.coverage_matrix.items():
                        if sections:
                            st.markdown(f"✅ **{component}** → {', '.join(sections)}")
                        else:
                            st.markdown(f"❌ **{component}** → *Not covered*")

                st.divider()

                if report.issues:
                    for issue in report.issues:
                        badge = severity_badge(issue.severity)
                        with st.expander(f"{badge} [{issue.category}] {issue.description[:80]}"):
                            st.markdown(f"**Category:** {issue.category}")
                            st.markdown(f"**Description:** {issue.description}")
                            if issue.evidence:
                                st.markdown(f"**Evidence:** {issue.evidence}")
                            if issue.suggested_fix:
                                st.info(f"💡 **Suggested Fix:** {issue.suggested_fix}")

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                if st.button("✅ Accept", key=f"qc2_accept_{issue.id}"):
                                    issue.status = IssueStatus.ACCEPTED
                                    save_run(run)
                                    st.rerun()
                            with col2:
                                if st.button("❌ Reject", key=f"qc2_reject_{issue.id}"):
                                    issue.status = IssueStatus.REJECTED
                                    save_run(run)
                                    st.rerun()
                            with col3:
                                st.markdown(f"Status: **{issue.status.value}**")
                else:
                    st.success("No issues found! 🎉")
            else:
                st.info("Run QC2 to see the instructional quality report.")

        # Re-run QC options if recommendations were applied
        if any(v.label.startswith("After QC fixes") for v in run.versions):
            st.divider()
            st.info("💡 You have applied fixes to this lesson! You can re-run QC to verify improved scores.")
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                if st.button("🔄 Re-run QC1 (Verify Fixes)", use_container_width=True):
                    with st.spinner("Re-auditing factual accuracy on updated version..."):
                        try:
                            import asyncio
                            from backend.qc.qc1_factual import execute_qc1
                            from backend.step_runner import StepRunner
                            runner = StepRunner(run)
                            asyncio.run(runner.execute(StepName.QC1, execute_qc1))
                            st.success("✅ QC1 re-audit complete!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ QC1 re-audit failed: {str(e)}")
            with col_r2:
                if st.button("🔄 Re-run QC2 (Verify Fixes)", use_container_width=True):
                    with st.spinner("Re-auditing instructional quality on updated version..."):
                        try:
                            import asyncio
                            from backend.qc.qc2_instructional import execute_qc2
                            from backend.step_runner import StepRunner
                            runner = StepRunner(run)
                            asyncio.run(runner.execute(StepName.QC2, execute_qc2))
                            st.success("✅ QC2 re-audit complete!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ QC2 re-audit failed: {str(e)}")

        # Apply fixes button
        st.divider()
        accepted_count = 0
        if run.qc1_report:
            accepted_count += sum(1 for i in run.qc1_report.issues if i.status == IssueStatus.ACCEPTED)
        if run.qc2_report:
            accepted_count += sum(1 for i in run.qc2_report.issues if i.status == IssueStatus.ACCEPTED)

        if accepted_count > 0:
            st.info(f"**{accepted_count} accepted issues** ready to apply.")
            if st.button("🔧 Apply Accepted Fixes", use_container_width=True):
                with st.spinner("Applying fixes..."):
                    try:
                        from backend.qc.apply import apply_fixes
                        result = apply_fixes(run)
                        save_run(run)

                        st.success(f"✅ {result['message']}")

                        # Show diffs
                        if result.get("diffs"):
                            st.subheader("📝 Changes Made")
                            for diff_info in result["diffs"]:
                                with st.expander(f"Section: {diff_info.get('section_heading', 'Unknown')}"):
                                    if "error" in diff_info:
                                        st.error(f"Failed: {diff_info['error']}")
                                    else:
                                        if diff_info.get("changes_made"):
                                            for change in diff_info["changes_made"]:
                                                st.markdown(f"- {change}")
                                        if diff_info.get("diff"):
                                            st.code(diff_info["diff"], language="diff")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to apply fixes: {str(e)}")

    # ── EDITOR TAB ───────────────────────────────────────────────────
    with tab_edit:
        if run.current_version:
            content = run.current_version.content

            # Version history
            st.subheader("📜 Version History")
            for v in reversed(run.versions):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    is_current = v.version == run.current_version.version
                    marker = "👉 " if is_current else ""
                    st.markdown(
                        f"{marker}**v{v.version}** — {v.label} — "
                        f"{v.created_at.strftime('%H:%M:%S')}"
                    )
                with col2:
                    st.caption(f"{len(v.content.sections)} sections")
                with col3:
                    if not is_current:
                        if st.button("Restore", key=f"restore_v{v.version}"):
                            restored = LessonVersion(
                                version=len(run.versions) + 1,
                                content=v.content.model_copy(deep=True),
                                label=f"Restored from v{v.version}",
                            )
                            run.versions.append(restored)
                            save_run(run)
                            st.success(f"Restored v{v.version} as v{restored.version}")
                            st.rerun()

            st.divider()

            # Section editor
            st.subheader("✏️ Edit Sections")
            st.caption("Auto-drafting keeps changes in memory until saved. Saving automatically creates a new immutable version snapshot.")

            # Track draft edits in session_state for autosave feel
            if f"drafts_{run.id}" not in st.session_state:
                st.session_state[f"drafts_{run.id}"] = {}

            for section in content.sections:
                with st.expander(f"Edit: {section.heading} ({section.type.value}, {section.est_minutes:.0f} min)"):
                    default_heading = st.session_state[f"drafts_{run.id}"].get(f"h_{section.id}", section.heading)
                    default_body = st.session_state[f"drafts_{run.id}"].get(f"b_{section.id}", section.body_md)

                    new_heading = st.text_input(
                        "Heading",
                        value=default_heading,
                        key=f"edit_heading_{section.id}",
                    )
                    new_body = st.text_area(
                        "Content (Markdown)",
                        value=default_body,
                        height=300,
                        key=f"edit_body_{section.id}",
                    )
                    # Cache in session state as draft
                    st.session_state[f"drafts_{run.id}"][f"h_{section.id}"] = new_heading
                    st.session_state[f"drafts_{run.id}"][f"b_{section.id}"] = new_body

                    new_minutes = st.number_input(
                        "Estimated Minutes",
                        value=float(section.est_minutes),
                        min_value=1.0,
                        max_value=20.0,
                        step=0.5,
                        key=f"edit_min_{section.id}",
                    )

                    col_save, col_discard = st.columns([1, 1])
                    with col_save:
                        if st.button("💾 Save Section as New Version", key=f"save_{section.id}", use_container_width=True):
                            # Create new version with the edit
                            new_content = run.current_version.content.model_copy(deep=True)
                            for s in new_content.sections:
                                if s.id == section.id:
                                    s.heading = new_heading
                                    s.body_md = new_body
                                    s.est_minutes = new_minutes
                                    break

                            new_content.total_minutes = sum(s.est_minutes for s in new_content.sections)

                            new_version = LessonVersion(
                                version=len(run.versions) + 1,
                                content=new_content,
                                label=f"Manual edit: {new_heading}",
                            )
                            run.versions.append(new_version)
                            save_run(run)
                            # Clear draft
                            st.session_state[f"drafts_{run.id}"].pop(f"h_{section.id}", None)
                            st.session_state[f"drafts_{run.id}"].pop(f"b_{section.id}", None)
                            st.success(f"✅ Saved as version {new_version.version}")
                            st.rerun()

                    with col_discard:
                        if st.button("🔄 Reset to Current Version", key=f"discard_{section.id}", use_container_width=True):
                            st.session_state[f"drafts_{run.id}"].pop(f"h_{section.id}", None)
                            st.session_state[f"drafts_{run.id}"].pop(f"b_{section.id}", None)
                            st.rerun()
        else:
            st.info("Generate the lesson first to edit sections.")

    # ── EXPORT TAB ───────────────────────────────────────────────────
    with tab_export:
        if run.current_version:
            st.subheader("📦 Export Lesson Bundle")
            st.markdown(
                "Export includes:\n"
                "- `lesson.md` — Full lesson content\n"
                "- `lesson.docx` — Word document\n"
                "- `references.md` + `references.csv` — Source references\n"
                "- `qc1_report.md` — Factual accuracy report\n"
                "- `qc2_report.md` — Instructional quality report\n"
                "- `metadata.txt` — Generation metadata\n"
                "- All bundled into a **ZIP file**"
            )

            if st.button("📦 Export All", use_container_width=True):
                with st.spinner("Generating export bundle..."):
                    try:
                        from backend.export.exporter import export_bundle
                        result = export_bundle(run)

                        st.success(f"✅ {result['message']}")

                        # Provide download buttons for each file
                        export_dir = settings.exports_dir / run.id
                        for file_info in result["files"]:
                            file_path = export_dir / file_info["name"]
                            if file_path.exists():
                                with open(file_path, "rb") as f:
                                    st.download_button(
                                        f"📥 Download {file_info['name']}",
                                        data=f.read(),
                                        file_name=file_info["name"],
                                        key=f"dl_{file_info['name']}",
                                    )

                        # ZIP download
                        zip_path = settings.exports_dir / result["zip_file"]
                        if zip_path.exists():
                            with open(zip_path, "rb") as f:
                                st.download_button(
                                    "📥 Download Complete ZIP Bundle",
                                    data=f.read(),
                                    file_name=result["zip_file"],
                                    mime="application/zip",
                                    key="dl_zip",
                                    use_container_width=True,
                                )

                    except Exception as e:
                        st.error(f"❌ Export failed: {str(e)}")

            # Quick preview of export content
            st.divider()
            with st.expander("👁️ Preview Export Content"):
                from backend.export.exporter import _generate_lesson_md
                preview_md = _generate_lesson_md(run)
                st.markdown(preview_md[:3000])
                if len(preview_md) > 3000:
                    st.caption(f"... ({len(preview_md)} total characters)")
        else:
            st.info("Generate the lesson first to export.")

    # ── Delete button ────────────────────────────────────────────────
    st.divider()
    with st.expander("🗑️ Danger Zone"):
        if st.button("Delete this lesson", type="secondary"):
            db = get_db()
            db.delete_run(run.id)
            st.session_state.current_run_id = None
            st.success("Lesson deleted.")
            st.rerun()

