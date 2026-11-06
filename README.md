# 🎓 LessonForge — AI-Powered Lesson Creation Tool
### Kalvium AI Research Intern Technical Task

**LessonForge** is an end-to-end educational lesson creation system that accepts a **Lesson Title** and **Learning Objective** as inputs, conducts multi-source automated research (websites, published books, and YouTube videos with transcript analysis), synthesizes structured 45-minute lesson content, and validates the output across two independent Quality Control (QC) layers: **Factual & Research Audit (QC1)** and **Instructional Quality Audit (QC2)**.

Instructors have full review, interactive editing, version control, recommendation application with visual diff inspection, and multi-format export capabilities.

---

## 🏛️ System Architecture

```
                                  ┌───────────────────────────┐
                                  │   Streamlit Web Interface │
                                  │ (Interactive Instructor UI│
                                  └─────────────┬─────────────┘
                                                │ REST API / In-Process
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       BACKEND ENGINE                                        │
│                                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                StepRunner Pipeline Engine                              │  │
│  │   [Pending] ──▶ [Running] ──▶ [Success / Failure with Isolated Error Recovery]         │  │
│  └───────┬──────────────────────┬────────────────────────┬──────────────────────┬────────┘  │
│          │                      │                        │                      │           │
│          ▼                      ▼                        ▼                      ▼           │
│   ┌──────────────┐      ┌──────────────┐         ┌──────────────┐       ┌──────────────┐    │
│   │   Phase 1:   │      │   Phase 2:   │         │   Phase 3:   │       │   Phase 4:   │    │
│   │ Multi-Source │ ───▶ │  45-Min Time │  ────▶  │ QC Layer 1:  │ ────▶ │ QC Layer 2:  │    │
│   │   Research   │      │   Planner &  │         │   Factual    │       │Instructional │    │
│   │   Pipeline   │      │Grounded Write│         │    Audit     │       │    Audit     │    │
│   └──────────────┘      └──────────────┘         └──────────────┘       └──────────────┘    │
│          │                      │                        │                      │           │
│          │                      ▼                        ▼                      ▼           │
│          │             ┌──────────────────┐    ┌─────────────────────────────────────────┐  │
│          │             │  Version Engine  │◀───│ Instructor Review & Fix Application     │  │
│          │             │ (v1, v2, ... vn) │    │ (Accept/Reject Suggestions, Live Diffs) │  │
│          │             └────────┬─────────┘    └─────────────────────────────────────────┘  │
│          │                      │                                                           │
│          │                      ▼                                                           │
│          │             ┌──────────────────┐                                                 │
│          │             │  Export Engine   │ ───▶ [.md, .docx, .csv, QC Reports, .zip]       │
│          │             └──────────────────┘                                                 │
└──────────┼──────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──────────────────────────────┬──────────────────────────────┐
           ▼                              ▼                              ▼
┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│     Web Research     │      │    Books Reference   │      │   YouTube Analysis   │
│  Tavily Search API   │      │ Google Books API &   │      │ YouTube Data API v3  │
│   + Trafilatura      │      │ Open Library Fallback│      │ + Transcript Analysis│
│  (Reliability Scorer)│      │  (Metadata Citation) │      │  (Relevance Scorer)  │
└──────────────────────┘      └──────────────────────┘      └──────────────────────┘
```

---

## 🌟 Core Functional Highlights (Aligned with Task Requirements)

### 1. Multi-Source Grounded Research
- **Web Sources:** Searches authoritative domains (MDN, RFC, universities, official docs) via Tavily Search API. Extracts text using `trafilatura` and calculates an automated **Source Reliability & Relevance Score** (0.0 to 1.0) with justifications.
- **Published Books:** Integrates Google Books API and Open Library fallback for real textbook references (Title, Author, Publication Year, ISBN, Link). *Note: In accordance with copyright standards, books are cited as authoritative reading and metadata is indexed; full copyrighted content is not scraped.*
- **YouTube Educational Videos:** Queries YouTube Data API v3, downloads video transcripts via `youtube-transcript-api`, and calculates an LLM-based instructional relevance score to select top videos matching the 45-minute lesson scope.
- **Source Pack ID Indexing:** Synthesizes all gathered intelligence into an immutable, indexed source pack (`[W1]`, `[B1]`, `[V1]`) that grounds generation and prevents hallucinated citations.

### 2. Time-Budgeted 45-Minute Lesson Generation
- **Programmatic Time Budgeting:** Allocates time blocks (Intro, Core Concepts, Examples, Hands-on Terminal Activity, Supplementary Video, Knowledge Check, and Summary) targeting exactly **43–47 minutes**.
- **Automated Rebalancing:** Automatically recalculates total minutes and scales section depth proportionally to guarantee feasible delivery.
- **Grounded Content Writer:** Employs low-temperature, grounded generation that requires inline source citations (`[W1]`, `[B1]`) and realistic technical scenarios (real `curl` commands, genuine status codes, and verified workflows).
- **Embedded Assessment:** Formulates 4–6 rigorous multiple-choice questions with explicit answer rationales.

### 3. Dual-Layer Independent Quality Control (QC)
- **QC Layer 1 (Research & Factual Accuracy Audit):**
  - Runs in an isolated execution sandbox using an adversarial auditing prompt.
  - Performs sentence-by-sentence claim extraction and marks claims as `supported`, `partially_supported`, `unsupported`, or `contradicted`.
  - Performs **programmatic validation**: verifies HTTP resolution of all cited URLs, confirms cited source IDs exist in the source pack, and checks 11-character YouTube video ID formats.
- **QC Layer 2 (Instructional Quality Audit):**
  - Audits alignment against Bloom's educational objectives.
  - Constructs an **Objective → Section Coverage Matrix** identifying full, partial, or missing coverage.
  - Recomputes feasibility from word counts (~175 wpm) and evaluates instructional clarity, jargon explanation, and engagement.

### 4. Instructor Workspace: Review, Edit, Apply Fixes & Versioning
- **Full Section Editor:** Inline Markdown editor with instant live-draft caching and rollback.
- **QC Action Center:** Review audit findings with severity badges (`🔴 HIGH`, `🟡 MED`, `🟢 LOW`) and choose to **Accept** or **Reject** recommendations.
- **AI-Powered Fix Application with Diffs:** Instructors can click **Apply Accepted Fixes** to generate targeted improvements, inspect a visual side-by-side **Git-style before/after diff**, and commit.
- **Immutable Version History:** Every generation, manual edit, and fix application creates a new version (`v1`, `v2`, `v3`) with full restore capability. Saved work is never overwritten.
- **QC Verification Loop:** Re-run QC1 and QC2 on revised versions to verify score improvements.

### 5. Multi-Format Export Engine
One-click export generating an organized download bundle:
- `lesson.md` — Complete lesson with formatted Markdown, tables, code blocks, and collapsible assessment answers.
- `lesson.docx` — Microsoft Word formatted document.
- `references.md` & `references.csv` — Full bibliographical audit grouped by source type.
- `qc1_report.md` & `qc2_report.md` — Independent factual and instructional audit reports.
- `metadata.txt` — Run metadata, model parameters, timestamp, and version trail.
- `lesson_<id>.zip` — Compressed bundle containing all artifacts.

---

## 🛠️ Technology Stack & Rationale

| Layer | Technology | Engineering Rationale |
|---|---|---|
| **Backend API** | Python 3.11+, FastAPI, Uvicorn | High-performance asynchronous execution, clean modular API routing, and robust data schema parsing. |
| **Frontend UI** | Streamlit | Rapid interactive prototyping focused on technical functionality, audit inspection, and workflow clarity over decorative UI. |
| **Data Validation** | Pydantic v2 & Pydantic-Settings | Strict type validation, automated schema enforcement, and non-empty input validation. |
| **LLM Interface** | Gemini / OpenAI / Claude Wrapper | Thin unified interface (`llm.py`) with JSON Schema validation and automatic retry with exponential backoff (`tenacity`). |
| **Web Research** | Tavily Search API + Trafilatura | Specialized developer search engine providing high-quality technical extracts and clean markdown parsing. |
| **Video Research**| YouTube Data API v3 + Transcript API | Direct access to video metadata, duration parsing, and transcript extraction for relevance verification. |
| **Database** | SQLite + SQLAlchemy ORM | Zero-configuration local transactional persistence; serializes runs and version trails without data loss. |
| **Testing** | Pytest | Comprehensive test suite covering input validation, DB integrity, error isolation, time budget calculation, and export formats. |

---

## 🚀 Quick Start & Setup Guide

### 1. Prerequisites
- Python 3.11 or higher
- Git

### 2. Clone Repository
```bash
git clone https://github.com/gensine/LessonForge.git
cd LessonForge
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Populate your API keys in `.env`:
```ini
LLM_PROVIDER=gemini                    # Options: gemini, openai, claude
LLM_API_KEY=your-api-key-here
LLM_MODEL=gemini-2.0-flash

TAVILY_API_KEY=your-tavily-api-key     # Required for automated web research
YOUTUBE_API_KEY=your-youtube-api-key   # Required for YouTube video retrieval
GOOGLE_BOOKS_API_KEY=                  # Optional (Open Library is used as fallback)
```

### 4. Automated Startup Scripts
- **Windows:** Double-click or run `run.bat`
- **macOS / Linux:** Run `chmod +x run.sh && ./run.sh`

*Alternatively, start manually:*
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate       # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch Application
streamlit run app.py
```
Open **http://localhost:8501** in your browser.

---

## 🧪 Automated Testing

LessonForge includes a full unit and integration test suite:
```bash
python -m pytest tests/
```
**Test Coverage (66 tests passed):**
- `test_input_validation.py`: Tests boundary conditions, whitespace enforcement, and character constraints.
- `test_database.py`: Tests SQLite CRUD, JSON serialization roundtrips, and version history preservation.
- `test_error_handling.py`: Tests retry resilience, timeout handling, non-destructive step failures, and missing-key fallbacks.
- `test_planner.py`: Tests 45-minute time enforcement (43–47 min window) and proportional time-rebalancing logic.
- `test_export.py`: Validates Markdown, DOCX, CSV, and QC report generation.

---

## 📂 Verification & Sample Deliverables

Pre-generated outputs for the two required test scenarios are available in the [`/samples`](./samples) directory:

### Test Case 1 (Official Required Benchmark)
- **Title:** `HTTP Requests and Responses`
- **Objective:** `Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.`
- **Deliverables:**
  - Full Lesson Content: [`samples/test1_lesson.md`](./samples/test1_lesson.md)
  - Factual Accuracy Report: [`samples/test1_qc1_report.md`](./samples/test1_qc1_report.md)
  - Instructional Quality Report: [`samples/test1_qc2_report.md`](./samples/test1_qc2_report.md)

### Test Case 2 (Technical Workflow Comparison)
- **Title:** `Git Branching and Merging`
- **Objective:** `Explain what a branch is and differentiate merge vs rebase.`
- **Deliverables:**
  - Full Lesson Content: [`samples/test2_lesson.md`](./samples/test2_lesson.md)
  - Factual Accuracy Report: [`samples/test2_qc1_report.md`](./samples/test2_qc1_report.md)
  - Instructional Quality Report: [`samples/test2_qc2_report.md`](./samples/test2_qc2_report.md)

---

## 🎯 Key Design & Engineering Decisions

1. **Independent Verification Pipelines:** QC Layer 1 (Factual) and QC Layer 2 (Instructional) run with separate execution prompts and distinct system contexts from the Generation Writer to prevent confirmation bias.
2. **Zero-Hallucination Citation Policy:** References can only be generated from items physically present in the indexed research source pack. URLs cannot be generated from memory.
3. **Defensive Error Isolation:** Each pipeline step (`research`, `generate`, `qc1`, `qc2`) executes inside an isolated wrapper. If an external service fails, the error is captured, previous data is preserved, and the failed step can be retried alone.
4. **Non-Destructive Version Tree:** Re-running generation or applying corrections creates a new immutable version snapshot, ensuring instructors never lose custom changes.
5. **Copyright Compliance:** Respecting publication intellectual property, book APIs are used exclusively for bibliographical discovery and metadata referencing; raw copyrighted books are never scraped.

---

## 📜 Acknowledgements & External Resources

- **Standards:** RFC 9110 (HTTP Semantics), MDN Web Docs by Mozilla, *Pro Git* by Scott Chacon.
- **APIs:** Tavily Search API, Google Books API, Open Library API, YouTube Data API v3.
- **Open Source Libraries:** FastAPI, Streamlit, SQLAlchemy, Pydantic, Trafilatura, YouTube Transcript API, Python-Docx, Tenacity, Pytest.
