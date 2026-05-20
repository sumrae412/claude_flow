# Scheduled-task rules

Constraints the weekly `claudeflow-repo-cleanup` task must follow. Factored out of the task's inline prompt so the prompt stays small and the rules are PR-reviewable.

The task runs autonomously (user not present), so rules here favor safety over speed.

---

## Cross-cutting (applies to both repos)

- **No destructive ops without explicit task wording.** No `git worktree remove --force`, `git branch -D`, `git push --delete`, `rm -rf`, force-push, or amending pushed commits unless the run prompt names that specific action.
- **No commits, no pushes, no PRs.** Reports land in the working tree; the user batches them into doc PRs on their own schedule.
- **Verify canonical path before any write.** `git rev-parse --show-toplevel` must match the expected path (see CLAUDE.md "Multi-Clone Gotcha"). Shadow clones at sibling paths must be ignored.
- **Fail loud.** If a phase is skipped or partially complete, surface it in the final report — never claim "done" if one repo errored or timed out.
- **Token-economy discipline.** Parallelize independent tool calls in the same turn; never chain when batch is possible. Reuse data collected in earlier steps — don't re-run the same `git`/`gh` query.

## Part 1 — claude_flow audit rules

- **Gate first.** Run `./scripts/cleanup-audit.sh` and inspect `has_delta`. If false, write a one-line "no delta since last report" note appended to the latest `docs/cleanup-report-*.md` and skip the full report.
- **Hold dirty worktrees.** Any worktree with uncommitted changes is held, regardless of age. Surface a preservation script in the report (the user runs it manually).
- **Hold clean stale worktrees.** Don't delete clean worktrees automatically either — surface them with a "safe to remove" annotation and let the user decide.
- **Trust pricing.py TODOs.** `# TODO: verify` markers in `scripts/pricing.py` are intentional guardrails per CLAUDE.md `pricing_freshness_pre_flight`. Never flag them as stale.
- **No claude_flow PR auto-merge.** Open PRs in this repo need human review. List them with status; do not merge.

## Part 2 — CourierFlow PR cleanup rules

- **Never force-merge PRs with failing checks.**
- **Never close PRs without user approval.** Stale PRs (>14 days idle, especially `claude/*` automation branches) get a comment, not closure.
- **Always use `--delete-branch` when merging** — keeps `origin` clean and avoids the merged-remote-branch backlog.
- **Work from the main checkout** (`/Users/summerrae/courierflow`), not a worktree.
- **Run `./scripts/quick_ci.sh` after any conflict resolution.** If conflicts are ambiguous or risky, skip and comment — don't guess.
- **Subagent review for unreviewed PRs only.** Use a Haiku-tier subagent with a 3-call budget; tools limited to Grep/Glob/Read.
- **Branch cleanup uses only data collected earlier.** Don't re-fetch — work from the `git branch -vv` + merged-PR list captured in step 1 of Part 2.
