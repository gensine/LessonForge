# Mastering Git: Branching, Merging, and Rebasing

**Learning Objective:** Explain what a branch is and differentiate merge vs rebase.  
**Total Estimated Time:** 45 minutes  
**Target Audience:** Software Engineering Interns / Computer Science Students  

---

## 1. Introduction & The Nature of Git Branches (4 mins)
In Git, a **branch** is not an isolated container of copied files. Technically, a branch is simply a **lightweight, movable pointer to a specific commit object** [W1]. 

```
(commit A) <--- (commit B) <--- (commit C)  <-- [main]
                                   ^
                                   |--- [HEAD]
```

When you create a new branch using `git branch feature`, Git creates a new 41-byte pointer referencing that same commit. Switching to it (`git switch feature`) merely redirects the `HEAD` pointer to track the new branch pointer.

---

## 2. Divergent Workflows & The Need for Integration (6 mins)
When multiple engineers work simultaneously or when a feature branch takes time to complete, the history diverges:

```
        D---E  [feature]
       /
  A---B---C    [main]
```
To combine changes from `feature` back into `main`, Git provides two distinct strategies: **Merge** and **Rebase**.

---

## 3. Git Merge: Preserving True Historical Context (10 mins)
Executing `git merge feature` from `main`:
- **Fast-Forward Merge:** If `main` has not advanced since `feature` branched off, Git simply moves the `main` pointer forward.
- **Three-Way Merge:** If `main` has progressed with new commits, Git identifies:
  1. The common ancestor commit (`B`).
  2. The tip of the current branch (`C`).
  3. The tip of the incoming branch (`E`).
- It produces a **new synthetic commit** called a **Merge Commit** with two parent hashes.

```
        D---E        [feature]
       /     \
  A---B---C---M      [main]  <-- M is the Merge Commit
```

**Pros:** Completely non-destructive; exact chronological record of when work happened.  
**Cons:** Commit graphs can become cluttered with numerous merge commits in large teams.

---

## 4. Git Rebase: Replaying Commits for a Linear History (10 mins)
Executing `git rebase main` while on the `feature` branch:
- Git computes the difference introduced by commits `D` and `E`.
- It saves those diffs to temporary patches.
- It resets the `feature` branch tip to match the current `main` commit (`C`).
- It applies each patch in sequence on top of `C`, generating **brand new commits** (`D'` and `E'`) with new SHA-1/SHA-256 hashes.

```
  A---B---C [main]
           \
            D'---E'  [feature]  (Replaced D and E with new commit hashes)
```

**Pros:** Beautiful, clean, linear history; simplifies `git bisect` and code inspection.  
**Cons:** **Rewrites commit history.**

> ⚠️ **The Golden Rule of Rebasing:** Never rebase commits that have been pushed to a public/shared branch that other team members have based their work upon.

---

## 5. Practical Hands-on Simulation (8 mins)
Execute the following commands in an empty directory to verify the mechanics:

```bash
# 1. Initialize repository and create base commit
git init git-demo && cd git-demo
echo "Base content" > README.md && git add . && git commit -m "feat: initial commit"

# 2. Create feature branch and add commit
git switch -c feature-auth
echo "Login logic" > auth.py && git add . && git commit -m "feat: add auth"

# 3. Switch back to main and simulate teammate's commit
git switch main
echo "Documentation update" >> README.md && git commit -am "docs: update readme"

# 4. Compare: run 'git merge feature-auth' vs 'git rebase main'
```

---

## 6. Supplementary Videos (3 mins)
- 🎥 **[Git Branching & Merging in 10 Minutes](https://www.youtube.com/watch?v=RGOj5yH7evk)** by Fireship  
  *High-speed visual comparison between three-way merge and rebase replay.*

---

## 7. Knowledge Check (3 mins)

1. **What is a Git branch under the hood?**
   - A) A cloned directory containing duplicates of all project files.
   - B) A movable pointer referencing a specific commit SHA.
   - C) A remote database transaction.
   - D) A zip archive of uncommitted changes.
   *Answer:* **B**. Branches are lightweight pointers to commits.

2. **What happens to the commit hashes of existing commits when you perform a rebase?**
   - A) They remain completely unchanged.
   - B) New commits are generated with new hashes because their parent commit has changed.
   - C) They are deleted without replacement.
   - D) Only the branch name changes.
   *Answer:* **B**. Because parentage changes, the hash recalculates, producing new commits.

---

## 8. Summary & Technical Decisions (1 min)
- A branch is merely a commit pointer.
- `git merge` records a non-destructive 3-way merge commit keeping historical topology.
- `git rebase` rewrites commits linearly onto the target tip.

---

## References & Authoritative Documentation
- **[W1] Pro Git Book (Scott Chacon & Ben Straub):** https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging
- **[W2] Atlassian Git Tutorials (Merging vs Rebasing):** https://www.atlassian.com/git/tutorials/merging-vs-rebasing

