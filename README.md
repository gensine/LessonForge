# 🎓 LessonForge — AI-Powered Lesson Creator

> **Input** (Lesson Title + Learning Objective) → **Research** (web, books, YouTube) → **Generate** 45-min lesson → **QC1** (factual audit) → **QC2** (instructional audit) → **Review/Edit/Apply fixes** → **Preview** → **Export**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40-red.svg)](https://streamlit.io)

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                        │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ ┌────────┐  │
│  │  Input   │ │ Pipeline │ │ Preview│ │  QC  │ │ Export │  │
│  │  Form    │ │ Controls │ │  View  │ │Review│ │  View  │  │
│  └─────────┘ └──────────┘ └────────┘ └──────┘ └────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ API calls
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend                           │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Pipeline (Step Runner)                    │   │
│  │                                                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌─────┐  ┌─────┐       │   │
│  │  │ Research  │→│ Generate │→│ QC1 │→│ QC2 │       │   │
│  │  │ Pipeline  │  │ (Planner │  │Fact.│  │Inst.│       │   │
│  │  │          │  │ + Writer)│  │Audit│  │Audit│       │   │
│  │  └──────────┘  └──────────┘  └─────┘  └─────┘       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │
│  │ LLM     │  │ SQLite   │  │ Apply    │  │ Export    │   │
│  │ Wrapper  │  │ Database │  │ Fixes    │  │ (MD/DOCX) │   │
│  └─────────┘  └──────────┘  └──────────┘  └───────────┘   │
└──────────────────────────────────────────────────────────────┘
         │              │              │
   ┌─────▼─────┐  ┌────▼────┐  ┌─────▼──────┐
   │ Gemini /  │  │ Tavily  │  │ YouTube    │
   │ OpenAI /  │  │ Search  │  │ Data API   │
   │ Claude    │  │ API     │  │ + Transcripts│
   └───────────┘  └─────────┘  └────────────┘
```

## 🔧 Tech Stack

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Python + FastAPI | Strong AI/LLM ecosystem, async support, clean REST API |
| **Frontend** | Streamlit | Fastest to build; task values functionality > visual polish |
| **LLM** | Gemini / OpenAI / Claude (swappable) | Thin wrapper with structured JSON output; swap via `.env` |
| **Web Research** | Tavily API | Returns clean URLs + snippets + raw content in one call |
| **Content Extraction** | trafilatura | Reliable text extraction from web pages |
| **YouTube** | YouTube Data API v3 + youtube-transcript-api | Find videos + pull transcripts for relevance verification |
| **Books** | Google Books API + Open Library | Real book metadata (cited, not scraped — copyright) |
| **Database** | SQLite (via SQLAlchemy) | Persist drafts, edits, QC reports, version history |
| **Export** | Markdown + python-docx | Lesson, references, QC reports as MD and DOCX |

## 🚀 Setup

### Prerequisites
- Python 3.11+
- API keys (see below)

### Installation

```bash
# Clone the repository
git clone https://github.com/gensine/LessonForge.git
cd LessonForge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your API keys
```

### API Keys

| Key | Where to get it | Required? |
|---|---|---|
| `LLM_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) / [OpenAI](https://platform.openai.com/api-keys) / [Anthropic](https://console.anthropic.com/) | ✅ Yes |
| `TAVILY_API_KEY` | [Tavily](https://tavily.com/) (free tier available) | ✅ Yes |
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) | ✅ Yes |
| `GOOGLE_BOOKS_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) | ❌ Optional |

### Running

```bash
# Start the Streamlit UI (recommended)
streamlit run app.py

# Or start the FastAPI backend only
python -m backend.main
# API available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

## 📋 How to Use

1. **Create a lesson** — Enter a title and learning objective
2. **Run Research** — AI searches web, books, and YouTube; scores source reliability
3. **Generate Lesson** — Creates a 45-minute lesson grounded in research sources
4. **Run QC1** — Factual accuracy audit (claim verification, URL checks, source audit)
5. **Run QC2** — Instructional quality audit (objective coverage matrix, timing, engagement)
6. **Review & Edit** — Accept/reject QC recommendations, edit sections manually
7. **Apply Fixes** — LLM applies accepted fixes with before/after diffs
8. **Export** — Download lesson, references, and QC reports as MD/DOCX/ZIP

## 🧪 Test Lessons

### Test 1: HTTP Requests and Responses
- **Title:** HTTP Requests and Responses
- **Objective:** Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.

### Test 2: Git Branching and Merging
- **Title:** Git Branching and Merging
- **Objective:** Explain what a branch is and differentiate merge vs rebase.

## 🎯 Design Decisions

1. **Grounded generation** — The writer only uses facts from the source pack and must cite source IDs. No hallucinated links or facts from LLM memory.

2. **Independent QC layers** — QC1 (factual) and QC2 (instructional) run with separate prompts, fresh context, and adversarial instructions. They don't share state with the writer.

3. **Versioning** — Every save/edit/fix creates a new version. Nothing is ever overwritten. Users can restore any previous version.

4. **No-hallucinated-links rule** — URLs only come from actual search results. The LLM is never allowed to generate reference links from memory.

5. **Swappable LLM** — One thin wrapper (`llm.py`) supports Gemini, OpenAI, and Claude. Change provider in `.env` without code changes.

6. **Graceful partial failures** — If YouTube fails, web+books still work. Each pipeline step is independent and retryable.

7. **45-minute enforcement** — The planner validates total time (43-47 min), auto-rebalances via LLM, and falls back to proportional scaling.

8. **Books cited, not scraped** — Book content is never downloaded (copyright). Books appear as recommended reading with proper citations.

## ⚠️ Limitations

- **Books are cited, not scraped** — Book content isn't available for grounding; only metadata and descriptions are used
- **Transcripts unavailable for some videos** — Some YouTube videos have no transcript; relevance is scored from title + description only
- **LLM accuracy** — While QC1 catches many factual errors, LLM-based verification isn't perfect. Manual fact-checking is recommended
- **Rate limits** — Free-tier API keys may hit rate limits with multiple consecutive runs
- **No PDF export** — WeasyPrint requires system dependencies; DOCX export is provided instead

## 🙏 Acknowledgements

### APIs & Services
- [Google Gemini API](https://ai.google.dev/) — LLM provider
- [Tavily](https://tavily.com/) — Web search API
- [YouTube Data API v3](https://developers.google.com/youtube/v3) — Video search
- [Google Books API](https://developers.google.com/books) — Book metadata

### Libraries
- [FastAPI](https://fastapi.tiangolo.com/) — Backend framework
- [Streamlit](https://streamlit.io/) — Frontend framework
- [SQLAlchemy](https://www.sqlalchemy.org/) — Database ORM
- [Pydantic](https://docs.pydantic.dev/) — Data validation
- [trafilatura](https://trafilatura.readthedocs.io/) — Web content extraction
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) — YouTube transcripts
- [python-docx](https://python-docx.readthedocs.io/) — DOCX generation
- [tenacity](https://tenacity.readthedocs.io/) — Retry logic
- [httpx](https://www.python-httpx.org/) — Async HTTP client

### AI Tools
- Built with assistance from AI coding tools

