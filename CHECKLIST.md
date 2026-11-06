# 📋 Pre-Submission Checklist

Use this checklist before submitting your final deliverables.

## Repository
- [ ] Repo is **public** on GitHub
- [ ] No API keys committed (check `git log --all -p | grep -i "api_key"`)
- [ ] `.env.example` exists with placeholder values
- [ ] `.gitignore` excludes `.env`, `*.db`, `__pycache__/`, `venv/`
- [ ] `README.md` has setup instructions, architecture, design decisions

## Fresh Clone Test
- [ ] `git clone` on a clean machine
- [ ] `python -m venv venv && pip install -r requirements.txt` works
- [ ] Copy `.env.example` to `.env`, add real API keys
- [ ] `streamlit run app.py` starts without errors
- [ ] `python -m pytest tests/` all tests pass

## Functionality
- [ ] Empty input → clear error message (not a crash)
- [ ] Create lesson → research → generate → QC1 → QC2 pipeline works
- [ ] Research shows sources with reliability scores
- [ ] Lesson has ~45 minutes total time
- [ ] Knowledge check has 4-6 questions with correct answers
- [ ] References only contain real URLs from search results
- [ ] QC1 report shows claims, verification status, issues
- [ ] QC2 report shows coverage matrix + instructional issues
- [ ] Accept/reject QC issues works
- [ ] Apply fixes creates a new version with diff
- [ ] Version history shows all versions, can restore
- [ ] Section editor saves and creates new version
- [ ] Export generates MD, DOCX, QC reports, ZIP bundle
- [ ] Download buttons work

## Error Handling
- [ ] Empty/whitespace title → "Title must be at least 3 characters"
- [ ] Empty/short objective → "Objective must be at least 10 characters"
- [ ] LLM API failure → retry with backoff → fail with Retry button
- [ ] Search API failure → partial results + warning (not a crash)
- [ ] YouTube failure → lesson still generates with web+book sources
- [ ] Saved versions/edits survive a failed step
- [ ] Each failed step can be retried independently
- [ ] Error log captures all failures with timestamps

## Sample Outputs
- [ ] `samples/test1_lesson.md` — HTTP Requests test
- [ ] `samples/test1_qc1_report.md`
- [ ] `samples/test1_qc2_report.md`
- [ ] `samples/test2_lesson.md` — Git Branching test
- [ ] `samples/test2_qc1_report.md`
- [ ] `samples/test2_qc2_report.md`

## Manual Fact-Check (Test 1: HTTP)
- [ ] GET is described as safe and idempotent
- [ ] POST is described as not idempotent
- [ ] 200, 201, 204 correctly categorized as 2xx (success)
- [ ] 400, 401, 403, 404 correctly categorized as 4xx (client error)
- [ ] 500, 502, 503 correctly categorized as 5xx (server error)
- [ ] Does NOT claim "GET can't have a body"
- [ ] Does NOT claim "POST is always secure"
- [ ] At least 10 claims verified against MDN / RFC 9110

## Demo Video
- [ ] 5-8 minutes, 1080p
- [ ] Shows: input → research → generate → QC → edit → apply → export
- [ ] Shows error handling (empty input, failure recovery)
- [ ] Explains design decisions (grounded generation, independent QC, versioning)
- [ ] Video link is accessible (not private)

## Acknowledgements
- [ ] All APIs, libraries, and AI tools credited in README
- [ ] No plagiarized code or uncredited sources

