# Session handoff — 2026-05-29

## Goal

Validate the now-merged Workflow-tool improvements against their **named-unverified empirical claims**, and (optionally) prototype the shipped Workflow-tool templates on a real PR.

## Current state (all SHIPPED + MERGED this session)

Origin: user asked "how can dynamic workflows improve claude_flow?" → a Workflow-tool analysis produced 5 ranked recs → all 5 implemented and merged.

| PR | Repo | What shipped | Merge SHA |
|---|---|---|---|
| [claude_flow#66](https://github.com/sumrae412/claude_flow/pull/66) | claude_flow | pr-reviewer: partial-failure status (`degraded`/`skipped`/`plannedReviewerCount`), per-model provenance via `segments[]` → `reviewer@model` join, `PR_REVIEWER_MAX_REVALIDATE` budget cap | `0b70602` |
| [claude-skills#136](https://github.com/sumrae412/claude-skills/pull/136) | claude-skills | claude-flow skill: `references/workflow-tool-orchestration.md` (Templates A/B), Phase 2 `/deep-research` routing, opt-in pointers in phase-6 + SKILL.md goal-mode | `deaaba5` (`deaaba5` on main) |

- **In-flight:** none. Both branches deleted, local `main` synced on both repos.
- **Untouched:** the two reference templates (A: Phase 6 cascade, B: goal-mode loop) are documented but **never executed** — they're adaptable starting points, not validated scripts.

### Key decision made this session (do not relitigate)
Recs #1/#2 ("port pr-reviewer to a Workflow script") were **re-scoped to an in-place TS refactor** because the Workflow tool runs only inside a Claude Code session — a saved workflow script cannot back `node dist/index.js` in headless CI. Recs #4/#5 shipped as **opt-in docs + templates**, NOT a pipeline rewrite, because the analysis's own antipatterns forbid monolithing the Phase 0–6 pipeline (it would strip the human checkpoints). The validated prose flow remains the default.

## Exact next task (most valuable)

**A/B the two unverified empirical claims that shipped, in priority order:**

1. **Revalidation FP-cut (claude_flow).** PR #66 + CLAUDE.md both mark the deepsec-style revalidate pass's FP reduction on *small PR diffs* as `unverified`. Run `pr-reviewer` on 2–3 real PRs with `PR_REVIEWER_REVALIDATE=1` vs off (use `src/compare.ts` harness if it fits), record FP-cut and added cost. Acceptance: a `docs/decisions/2026-MM-DD-revalidate-verdict.md` with the measured FP-rate delta + a keep/drop recommendation. If it doesn't earn its cost on small diffs, default it off and say so.
2. **`/deep-research` Phase 2 routing (claude-skills).** New routing claims only-the-cited-report-lands-in-context saves tokens vs `/research`. Run one full-path task with an external-research question both ways; record token delta + brief quality. Acceptance: a decision-record row, not a code change.

**Optional follow-up (only if the user asks):** prototype Template A (`references/workflow-tool-orchestration.md`) by saving it to `.claude/workflows/` in a real project and invoking it on a live PR — verify the `agentType` values resolve and the Tier-1 early-exit branch fires. This is exploratory; do not block on it.

## Template / reference PRs
- [claude_flow#66](https://github.com/sumrae412/claude_flow/pull/66) — the refactor pattern (partial-failure as first-class status, provenance-preserving join).
- [claude-skills#136](https://github.com/sumrae412/claude-skills/pull/136) — the opt-in-asset pattern for Workflow-tool orchestration.

## Pre-flight commands (run FIRST on resume)
```bash
cd /Users/summerrae/claude_code/claude_flow         # canonical path — validate with: git -C . rev-parse --show-toplevel
git fetch origin --prune && git status -sb
git branch --show-current && git worktree list      # confirm cwd branch, not a sibling worktree
env -u GH_TOKEN gh pr list --state open
# CR/CI wiring: claude_flow runs CI (claude-review + review). claude-skills has NO review wired — do not block on review feedback there.
env -u GH_TOKEN gh pr view 66 --json reviews,statusCheckRollup
```

## Re-verify on resume (premises that drift)
- **Canonical repo paths:** `/Users/summerrae/claude_code/claude_flow` and `/Users/summerrae/claude_code/claude-skills`. Validate each with `git -C <path> rev-parse --show-toplevel`.
- **Branch + worktree:** both repos should be on `main`, no active worktree for this work.
- **Shared checkout — parallel-session race:** both repos are single-working-directory (no per-session worktrees). Re-check `git branch --show-current` immediately before any commit. A `permission-brief` skill landed in claude-skills from a parallel session this session — expect concurrent writers.

## Architectural invariants to preserve
- claude_flow Pipeline Discipline Rules 5 (model for judgment only), 6 (budgets enforced), 7 (surface conflicts), 12 (fail loud) — the refactor makes these structurally true; don't regress them.
- The 5 hard constraints in `references/workflow-tool-orchestration.md`: human ship gate stays OUTSIDE the workflow; memory-injection first stage; within-session only (run_manifest is durable state); deterministic leaves shell out; research-preview gating is a fallback not a dependency.
- `two_clones_same_repo` / `shadow_path_drift_within_session` (MEMORY) — `git rev-parse --show-toplevel` first turn.

## Gates
- claude_flow pr-reviewer: `npm --prefix agent-sdk/pr-reviewer test` (expect `23 pass`).
- claude-skills claude-flow: `python3.12 -m pytest claude-flow/scripts/test_workflow_assets.py claude-flow/scripts/test_lint_workflow.py -q` (expect `19 passed`) + `python3 claude-flow/scripts/lint_workflow.py` (expect `OK`).

## Ship instructions
The A/B tasks produce **decision records** (`docs/decisions/`), not feature code. Ship each via `/ship`. This is validation work, not pattern-replication — use `/ship`, not `/claude-flow`.

## Mode directive
Auto mode. Surface premise contradictions only.
