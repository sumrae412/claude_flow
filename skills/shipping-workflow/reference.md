# Shipping Workflow — 10-Step Review & Project Customization

Load this when executing Stage 4 (Automated Code Review) of the shipping workflow. It defines the full review process, scoring, and project-level options.

---

## The 10-Step Review Process

### Step 1: Eligibility Check

```bash
gh pr view <PR_NUMBER> --json state,isDraft,author,comments
```

**Stop the review if:**

- PR is closed or merged
- PR is a draft
- PR author is a bot
- PR already has a comment containing "Generated with [" (already reviewed)

### Step 2: Staleness Check

- `git fetch origin main` and `git fetch origin <pr-branch>`
- `gh pr diff <PR_NUMBER> --name-only`
- For each changed file: `git diff origin/main..origin/<pr-branch> -- <file>`

| Diff result | Action |
|-------------|--------|
| Empty diff (identical to main) | Skip (already merged) |
| PR version older than main | Flag as stale |
| Genuinely new code | Include in review |

Check deletions: `git diff --diff-filter=D --name-only origin/main..origin/<pr-branch>`. Flag out-of-scope deletions.

**If all files are already on main or regressive:** Recommend closing the PR; post a comment and stop.

**Why this step matters:** Skipping the staleness check can lead to merge conflicts at Step 10 that are harder to resolve. In one session, main had diverged (same file modified on both branches) and the merge failed. Running Step 2 early surfaces these conflicts before the full review runs, saving significant rework.

### Step 3: Broad Code Review Sweep

- Run code review tool if available (e.g. CodeRabbit: `coderabbit review --plain`).
- Check the diff for **defensive patterns** (see project-level checklists below).

### Step 4: Determine Deep-Dive Triggers

Grep the diff for patterns that warrant deeper analysis (git history or test logic). **Customize per project.**

**Git history triggers (run git history analysis):**

- `d-none`, `display:`, `visibility:`, `opacity:`
- `position:\s*(fixed|absolute|sticky)`, `z-index`
- Lines removed that were recently added

**Test logic triggers (run test analysis):**

- Files in `tests/` modified or added
- Assertion keywords (`assert`, `assertEqual`, `expect`)
- New test functions/classes

### Step 5: Conditional Deep-Dive Analysis

Run 0–2 focused analyses based on Step 4. Can run in parallel.

**If git history triggered:** For each triggered file — `git log --oneline -10 -- <file>`, `git blame <file>` around changed lines. Check removed code intent, layout/positioning conflicts. Score each finding 0–100; report only ≥ 60.

**If test logic triggered:** Read test changes in full. Check assertion correctness, mock patterns, test isolation. Score each finding 0–100; report only ≥ 60.

**Scoring rubric:**

| Score | Meaning |
|-------|---------|
| 0 | False positive (not a real bug) |
| 25 | Might be real, not verified |
| 50 | Real but nitpick |
| 75 | Likely real, impacts functionality |
| 100 | Confirmed, happens frequently |

### Step 6: Merge and Deduplicate Findings

Combine findings from Steps 3–5. Deduplicate by file + line range (overlapping = same issue; keep higher score). If zero issues remain, skip to Step 10 and post a clean review comment.

### Step 7: Re-Check Eligibility

Before making changes: PR still open; no review comment posted since we started.

### Step 8: Fix Issues

For each issue: read flagged code in full context, apply fix. If fix is unclear or risky, skip and leave as comment only. Then:

```bash
git add <fixed-files>
git commit -m "fix: address PR review findings"
```

### Step 9: Run CI (Hard Gate)

Run project CI (e.g. `./scripts/quick_ci.sh`). **Hard gate:** must pass. If failures, fix and re-run; loop up to 3 attempts, then escalate to user.

### Step 9.5: Verify Behavior (not just code)

After CI passes, verify the changed feature actually produces correct output. Reading code and concluding "it looks right" is not evidence — silent error handling (try/except, empty catch) means correct-looking code can fail at runtime.

**What to verify depends on what changed:**

| Change type | Verification |
|-------------|-------------|
| API endpoint (new or modified) | Call it, check the response contains expected values (not null/empty/zero) |
| Count/aggregation query | Compare the returned numbers against the source data or the UI that consumes them |
| UI data binding | Confirm the UI element renders the endpoint's actual values, not placeholder/default |
| Error handling change | Trigger the error path, confirm it surfaces (not silently swallowed) |
| Filter/query logic | Verify the result set matches the filter criteria — compare against an unfiltered query |

**How to verify:**
- If tests exist that exercise the endpoint/feature end-to-end, CI covers this. Move on.
- If no end-to-end test exists, note it as a gap in the PR comment. For data-layer changes (queries, aggregations, counts), a smoke test that executes the query is strongly recommended before merge.
- After deploy, if the project has a staging/production URL: spot-check the endpoint or page. Check deploy logs for errors (`@level:error`).

**Skip when:** Pure refactors with no behavior change, documentation-only PRs, test-only PRs.

### Step 10: Ship to Main

```bash
git push origin <branch>
git checkout main && git pull origin main
git cherry-pick <fix-commit-sha>
git push origin main
```

**Worktree caveat:** If the review agent runs in a worktree, `git checkout main` will fail with "already used by worktree." Instead, merge via the GitHub API:
```bash
gh api -X PUT repos/{owner}/{repo}/pulls/{number}/merge -f merge_method=squash
```
Then pull main in the parent repo separately if needed.

Post PR comment:

**If issues were found/fixed:**

```markdown
### Code review

Found N issues (M fixed):

1. <description> (<source: CodeRabbit/defensive-patterns/git-history/test-logic>)
   Fixed in commit `<sha>`

2. <description> (<source>)
   Not auto-fixed — <reason>

Generated with [AI Agent]
```

**If zero issues:**

```markdown
### Code review

No issues found. Checked for bugs, project rule compliance, and defensive patterns.

Generated with [AI Agent]
```

---

## False Positive Filters

Do **not** flag:

- Linter/typechecker-catchable issues
- General code quality without project-rule basis
- Intentional functionality changes related to the PR purpose

## Fix-What-You-Find Rule

If you discover a bug during review — even if it was **not introduced by this PR** — flag it and fix it. Pre-existing bugs are still bugs. The same applies to CI failures: if a pre-existing issue causes CI to fail, fix the root cause rather than working around it or ignoring it.

---

## Project-Level: Defensive Patterns (Examples)

Replace with your stack’s anti-patterns.

### JavaScript / HTML / CSS

- Guard clauses that return without user feedback (silent early returns)
- State flags (`_isSending`, `isLoading`) without try-catch-finally to guarantee reset
- Overlay UIs using external toast instead of inline feedback
- Async catch with no user feedback (empty catch or console-only)
- DOM elements used without null-check (`querySelector` result used directly)
- CSS tokens used but not in design system variables
- `style.display` instead of `classList.add/remove`
- Missing cache-busting on changed static assets

### Python

- Silent `except: pass` or `except SomeError: pass` with no logging
- Exception handlers catching fewer types than callee raises
- Data destruction (NULL/DROP) without copying first
- Constants/configs duplicated across files
- Calling private methods from outside owning module
- Types in signatures without matching imports
- `str(e)` or tracebacks leaked in HTTP responses
- `datetime` compared as strings instead of parsed objects

---

## Project-Level: CI and Commands

| Component | Example (Python/FastAPI) | Example (Node/React) |
|-----------|--------------------------|----------------------|
| CI command | `./scripts/quick_ci.sh` | `npm run ci` |
| Test command | `pytest tests/ -v` | `npm test` |
| Lint command | `flake8 app --select=E9,F63,F7,F82` | `eslint --max-warnings=0` |
| Base branch | `main` | `main`, `develop` |

CI gate should cover at least: syntax validation, critical lint, core tests, model/schema validation, template/UI validation. Adapt to the project.

---

## Adapting to Your Framework

| Capability | If available | If not |
|------------|---------------|--------|
| Background agents | Run Stage 4 in background | Run inline |
| Isolated workspaces | Use git worktree for review | Same workspace (avoid conflicts) |
| CodeRabbit CLI | Use for Step 3 sweep | Manual diff review |
| `gh` CLI | Use for PR/comments | Web UI for PR |
| Parallel execution | Run deep-dives in parallel | Sequential |
