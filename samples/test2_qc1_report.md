# QC Layer 1 Report: Research & Factual Accuracy Audit

**Target:** Git Branching and Merging  
**Overall Factual Score:** 9.7 / 10.0  
**Audit Status:** APPROVED (PASS)  

---

## 1. Executive Summary
The lesson content demonstrates exceptional factual accuracy verified against the authoritative reference *Pro Git* by Scott Chacon. It avoids common falsehoods (such as claiming a branch is a full folder copy or that rebase preserves original commit hashes).

---

## 2. Claim-Level Verification Matrix

| Claim Extracted from Lesson | Source Grounding | Status | Evidence / Notes |
|---|---|---|---|
| A branch is a movable 41-byte pointer to a commit | *Pro Git* Chapter 3.1 | ✅ Supported | "A branch in Git is simply a lightweight movable pointer to one of these commits." |
| Merge produces a synthetic commit with 2 parents | *Pro Git* Chapter 3.2 | ✅ Supported | Three-way merges create a new merge commit. |
| Rebase replaces commits with new hashes | Atlassian Git Tutorials | ✅ Supported | Diffs are reapplied on top of destination, altering parentage and SHA. |
| The Golden Rule of Rebasing (never rebase public work) | *Pro Git* Chapter 3.6 | ✅ Supported | Essential industry standard rule accurately quoted and warned. |

---

## 3. URL & Integrity Verification
- `https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging` → HTTP 200 OK
- `https://www.atlassian.com/git/tutorials/merging-vs-rebasing` → HTTP 200 OK

