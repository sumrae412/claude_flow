# Repository Cleanup Report — 2026-05-08

**Source:** Scheduled task `claudeflow-repo-cleanup` (autonomous run, user not present).
**Repo:** github.com/sumrae412/claude_flow @ `main`
**Previous run:** [docs/cleanup-report-2026-05-07.md](cleanup-report-2026-05-07.md) — overlap noted; this report focuses on **what changed since yesterday** and **what action this run actually took**.

---

## TL;DR

| Area | This run | State now |
|---|---|---|
| Open PRs | 0 to merge | `gh pr list --state open` → `[]` |
| README hook-count tree (line 297-298) | **Fixed** — 15→16, 10→14 | Working-tree diff includes the table fix (already present) + the tree-diagram fix (new). Ready to PR. |
| Stale orphan worktree dirs | **13 still present** — `rm -rf` blocked again by harness sandbox | User must run the manual command in §2. |
| AGENTS.md (untracked) | **Unchanged** | Recommendation in §6 of yesterday's report still stands. |
| `skills/` untracked dirs | **Unchanged** | Recommendation in §5 of yesterday's report still stands. |
| Dead code / debug prints | Re-audited; no change | All `console.log` / `print()` are intentional CLI output. No `FIXME`/`XXX:`. The 30+ `TODO: verify` in `scripts/pricing.py` are required pricing-verification flags (per `pricing_freshness_pre_flight` memory rule). Keep. |
| Unused dependencies | Re-audited; no change | `@anthropic-ai/sdk`, `undici`, `fastmcp` all used. |

---

## 1. Open PRs

```
gh pr list --state open --json number,title  →  []
```

No PRs to merge. Latest merged: PR #54 (`feat(pr-reviewer): opt-in revalidation pass`) on 2026-05-06. Local `main` is at `bdfe062`, even with `origin/main`.

---

## 2. Stale orphan worktree directories — still present

`git worktree list` reports two registered worktrees:
- canonical main checkout
- `.claude/worktrees/wonderful-turing-813fbc` (mtime 2026-05-04 → 4 days old, **not stale**)

The other 13 directories under `.claude/worktrees/` are filesystem-only orphans — git no longer registers them, but the on-disk directories remain. Mtimes range 2026-04-10 to 2026-04-20, so all are >5 days old.

**This run attempted `rm -rf` and was blocked by the harness sandbox** (same outcome as the 2026-05-07 run). Manual command:

```bash
cd /Users/summerrae/claude_code/claude_flow
rm -rf .claude/worktrees/{brave-hermann,epic-carson-473434,laughing-lalande,lucid-roentgen,nervous-dijkstra,nostalgic-lederberg,quirky-bose,quizzical-swirles,sad-hugle,stoic-villani-655fce,upbeat-franklin,vibrant-matsumoto,wonderful-hodgkin}
```

**Keep:** `.claude/worktrees/wonderful-turing-813fbc/` (active, 4 days old).

**Suggestion (carried over from §8.5 of yesterday's report):** extend the Tier 1 `worktree-cleanup` hook to scan for orphan directories whose `.git` pointer is broken AND mtime >5 days, since the current hook only handles git-registered worktrees. This loop closure would prevent the same accumulation next month.

---

## 3. README.md update — applied this run

Working-tree changes now include both:
1. The hook-count **table** fix (15→16 / 10→14) — was already in the working tree at session start.
2. The hook-count **tree-diagram** fix (lines 297-298, same numbers) — applied this run.

Both fixes will land in a single PR opened by this run. Diff stat:

```
README.md | 26 +++++++++++++++++++-------
1 file changed, 19 insertions(+), 7 deletions(-)
```

---

## 4. Stale local branches

Same 22 branches as yesterday's report (no merges since). Recommendation unchanged: prune the 19 with `[behind]` / `[gone]` upstream, verify the 3 with `[ahead]` first. See `docs/cleanup-report-2026-05-07.md` §4 for the exact command block. **This run took no destructive branch action.**

---

## 5. Untracked `skills/` directory

Unchanged from yesterday. Three untracked SKILL files violate the canonical-skills-location policy (`feedback_skills_canonical_location` memory rule):

- `skills/context-engineering/SKILL.md` — local copy; canonical exists with `phases/` subdir absent here. **Delete local.**
- `skills/deprecation-and-migration/SKILL.md` — local copy; canonical exists. **Delete local.**
- `skills/source-driven-development/SKILL.md` — **not in canonical**. Either move to canonical or confirm abandoned.

Suggested `.gitignore` addition (so this stops showing up as untracked):

```gitignore
# Local skill scratch — canonical is /Users/summerrae/claude_code/claude-skills/
skills/
```

---

## 6. Untracked `AGENTS.md`

Unchanged from yesterday. 103-line Codex-CLI variant of CLAUDE.md, drifted (missing NVIDIA gotchas, External SDD Framework Coverage section, advisor-tool block, etc.).

**Recommended:** symlink to keep it in sync.

```bash
cd /Users/summerrae/claude_code/claude_flow
ln -sf CLAUDE.md AGENTS.md
git add AGENTS.md
```

Most Codex/Claude tooling treats both files as plain text, so a symlink is functionally equivalent and eliminates drift.

---

## 7. Dead code, debug prints, dependencies — re-audit

Re-ran the same scans as yesterday on current source. No change.

### Dead code
None identified. Pipeline modules in `agent-sdk/pr-reviewer/src/` (index, review, model-client, triage, reviewers, compare, github, revalidate) are tightly coupled — every file is consumed.

### Debug output
- **42 `console.log`/`console.error` calls** in `agent-sdk/pr-reviewer/src/` — all intentional CLI output for `node dist/index.js`. **Keep.**
- **135 `print()` calls** in `scripts/*.py` — all intentional CLI output for user-run scripts. **Keep.**

### TODO / FIXME markers
- 0 `FIXME` / `XXX:` markers found.
- 30+ `TODO: verify` markers in `scripts/pricing.py` — these are **required pricing-verification flags** per the `pricing_freshness_pre_flight` memory rule. They mark rates that must be re-verified against provider pricing pages before any cost eval. **Do NOT remove** — removing these is a guardrail bypass, not a cleanup.
- All other "todo" matches are skill-name literals (`todo-cleanup.sh`) or schema field names. **Keep.**

### Unused dependencies
- `agent-sdk/pr-reviewer/package.json`:
  - `@anthropic-ai/sdk` — used in `src/model-client.ts:1` (Anthropic provider).
  - `undici` (devDep) — used in `src/model-client.ts:2` for the extended-headersTimeout dispatcher (per CLAUDE.md NVIDIA gotcha).
  - `typescript`, `@types/node` — build deps.
- `mcp/claude-flow-server/requirements.txt`:
  - `fastmcp>=2.0.0` — used in `server.py:9`.

All used. Nothing to remove.

### Redundant files / generated artifacts
None checked in. No `dist/`, `__pycache__/`, `node_modules/`, `.bak`, `.orig`, `.swp`.

---

## 8. Refactoring suggestions (low-risk)

Identical to yesterday's §8 — no new issues surfaced this run. Rolled forward verbatim:

1. **Symlink AGENTS.md → CLAUDE.md** (eliminates drift).
2. **Add `skills/` to `.gitignore`** (enforces canonical-location policy via tooling).
3. **Reconcile README hook counts** — done this run.
4. **`npm run clean` script** in `agent-sdk/pr-reviewer/package.json` to remove `dist/`.
5. **Extend `worktree-cleanup` hook** to also delete filesystem orphans (broken `.git` pointer + >5-day mtime) — would have prevented the 13-orphan accumulation.

---

## 9. What this run did vs. did not do

**Did:**
- Verified canonical path (`/Users/summerrae/claude_code/claude_flow`).
- Re-ran `git fetch --prune origin`; local `main` is even with `origin/main` (no fast-forward needed).
- Confirmed 0 open PRs.
- **Applied the README tree-diagram hook-count fix** (lines 297-298).
- Re-audited dead code, debug prints, dependencies — confirmed yesterday's report is still accurate.
- Wrote this report.
- Will commit + push and open a PR with the combined README fix and both cleanup reports.

**Did NOT (held / blocked):**
- `rm -rf` on stale worktree directories — harness sandbox blocked, same as yesterday. Manual command in §2.
- `git branch -D` on stale local branches — destructive, not explicitly authorized by task wording.
- Touch the untracked `skills/` directory or `AGENTS.md` — recommendations, not authorized actions.
- Merge any PR — none exist.

---

*End of report.*
