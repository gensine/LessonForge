# Sample Outputs

This directory contains sample outputs from running the two test lessons.

## Test 1: HTTP Requests and Responses

- **Title:** HTTP Requests and Responses
- **Objective:** Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.

Run this test by entering the above title and objective in the Streamlit UI.

### Expected outputs:
- `test1_lesson.md` — Full 45-minute lesson covering GET, POST, status codes
- `test1_qc1_report.md` — Factual accuracy audit against MDN/RFC sources
- `test1_qc2_report.md` — Instructional quality audit with coverage matrix

### Manual fact-check points:
- [ ] GET: retrieve, safe + idempotent, params in URL, shouldn't change server state
- [ ] POST: submit data in body, not idempotent, may create resources
- [ ] 2xx success (200, 201, 204)
- [ ] 4xx client error (400, 401, 403, 404)
- [ ] 5xx server error (500, 502, 503)
- [ ] NOT claimed: "GET can't have a body" (it can, just unusual)
- [ ] NOT claimed: "POST is always secure" (it's not inherently secure)

---

## Test 2: Git Branching and Merging

- **Title:** Git Branching and Merging
- **Objective:** Explain what a branch is and differentiate merge vs rebase.

### Expected outputs:
- `test2_lesson.md` — Full 45-minute lesson covering branches, merge, rebase
- `test2_qc1_report.md` — Factual accuracy audit
- `test2_qc2_report.md` — Instructional quality audit

### Manual fact-check points:
- [ ] Branch = lightweight movable pointer to a commit
- [ ] Merge creates a merge commit (non-fast-forward) or moves pointer (fast-forward)
- [ ] Rebase replays commits on top of another branch
- [ ] Rebase rewrites history — don't rebase shared/public branches
- [ ] NOT claimed: "rebase is always better than merge"
- [ ] NOT claimed: "merge always creates a merge commit"

---

## Verification Checklist (both tests)

- [ ] Total time ≈ 45 min
- [ ] All URLs open and are valid
- [ ] Videos are relevant and exist on YouTube
- [ ] At least 10 claims manually fact-checked against official docs
- [ ] QC1 catches at least one issue
- [ ] QC2 produces a coverage matrix with actionable suggestions
- [ ] Apply recommendation → diff → re-run QC shows improvement
- [ ] Export files (MD, DOCX) open correctly
- [ ] Error simulation: saved work survives a step failure

