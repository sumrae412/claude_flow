# Handoff prompt — Token Efficiency Phase 2

> Paste the content below this line into a new Claude Code session. It is self-contained — do not include this header.

---

Continue implementation of the Token Efficiency Phase 2 plan.

## Plan location

Read first: `/Users/summerrae/claude_code/claude_flow/docs/plans/2026-04-18-token-efficiency-phase-2.md`

That file is the authoritative spec — 5 items, sequenced, each with claude-flow path + phase-by-phase breakdown + ruled-out alternatives. Do not re-derive the plan; execute it.

## Current state (2026-04-18, end of prior session)

- **Plan written, not committed.** The file above exists as untracked in `/Users/summerrae/claude_code/claude_flow/` working tree.
- **Nothing from the plan implemented yet.** All 5 items are pending.
- **Phase 1 work already shipped** in the prior session: brevity skill, `--lite` flags on heavyweight orchestrators, progressive-disclosure audit script, `/clear` guidance, prompt-caching via system/user split in `agent-sdk/pr-reviewer`. Session-learnings MEMORY entries live in commit `fc8e694` of `sumrae412/claude-config`. Skill cross-references applied in `sumrae412/claude-skills#37` (merged `2de5fad`).

## Execution order

Strict sequential. Do not start item N+1 before item N is shipped or deferred with a documented reason.

1. **Item 1 — MEMORY.md trim** (FAST PATH). Single biggest win; MEMORY.md is actively truncating mid-session. Ship this first.
2. **Items 2.a–2.h — 8 progressive-disclosure refactors** (LITE PATH × 8). Ship largest first (production-readiness-check at 494 lines). One PR per skill; do not bundle.
3. **Item 3 — Tool-result auto-clearing hook** (FULL WORKFLOW). Dedicated session. Needs Phase 2 exploration of Claude Code harness semantics for clearing.
4. **Item 4 — Prompt-variant optimization on hot subagent prompts** (LITE PATH). Uses existing `prompt-tracker.py` infra.
5. **Item 5 — Haiku for Phase 1 triage** (LITE PATH). Requires 20-fixture regression test.

## Canonical paths (critical)

- **claude_flow (scripts, docs, plans):** `/Users/summerrae/claude_code/claude_flow/` — NOT `/Users/summerrae/claude_flow/` (that's a shadow clone; nearly empty). MEMORY entry `two_clones_same_repo.md` and `shadow_path_drift_within_session.md`.
- **claude-skills (all skill SKILL.md files):** `/Users/summerrae/claude_code/claude-skills/` — canonical. `~/.claude/skills` is a symlink into this repo; edits there ARE edits to the canonical repo and must be committed + pushed from there.
- **Memory repo:** `~/.claude/projects/-Users-summerrae-claude-flow/memory/` — remote is `sumrae412/claude-config`.
- **Verify cwd every turn:** `cd /Users/summerrae/claude_code/claude_flow && git rev-parse --show-toplevel` before any Bash action. Shadow drift can appear mid-session.

## Invocation pattern per item

For each item, invoke `/claude-flow <task description>` with the path pre-stated. claude-flow will auto-route via its Phase 1 triage; the plan already specifies the expected path for each item as a sanity check. If triage picks a different path, STOP and reconcile before proceeding — the plan's path choice is deliberate.

Example for Item 1:
```
/claude-flow trim MEMORY.md index entries. Each one-line pointer ≤150 chars. Target: full file ≤24,400 bytes. Single commit direct to claude-config main.
```

## Tooling conventions

- **Commits / pushes to claude_flow:** direct push to main is authorized (per-session preference in MEMORY `direct_push_main_personal_repo.md`). Confirm once at session start.
- **Commits to claude-skills:** feature branch → PR → merge. PRs can self-merge (`gh pr merge --squash --delete-branch`); user owns the repo.
- **session-learnings:** invoke after each item's commit cluster. Do not batch across items — the learnings are per-item.
- **gh CLI path:** `/opt/homebrew/bin/gh` (not on default PATH on this machine).
- **Always stage explicit files** — never `git add .` or `git add -A` in the memory repo (would catch secrets; also the `projects/` gitignore rule forces `-f` on new files).

## Gotchas (will bite)

- **Post-commit hook conflation:** a tier-1 hook auto-commits `.gitignore`; if you stage files alongside, they get swept into its commit under the wrong message. After ANY commit run `git show HEAD --stat`. Chain stage+commit+verify in one Bash call. MEMORY `post_commit_hook_message_conflation.md`.
- **Pre-commit auto-fixers** (ruff-format, prettier, eof-fixer) modify files mid-commit and abort. Re-`git add` and re-commit on first abort. Pre-empt with `ruff format .` before first commit attempt.
- **Bash cwd resets after chained cd in worktree:** `cd /repo && git push` leaves shell cwd on the worktree path afterward. Prepend `cd` to every chain OR use `gh --repo <owner>/<repo>` to bypass cwd inference.
- **Progressive-disclosure split pattern:** use `sed -n 'M,Np' src/SKILL.md > references/<name>.md` to extract byte ranges without loading the monolithic file into context. Pattern validated on defensive-ui-flows (1245 → 82-line router) in PR #22.
- **MEMORY.md entries need `## Related` footer** when genuine relationships exist. See `related_footer_convention.md`. Do not force-link.

## Success criteria

Plan-level success = 3 of 5 items shipped. Below that means Phase 2 stalled — invoke `/cleanup` to audit half-shipped state before starting Phase 3.

Per-item verification is in the plan. Do not skip the verification step — Items 3, 4, 5 all claim token savings that must be measured, not asserted.

## Next concrete action

1. Commit the plan file to `claude_flow` main (direct push OK per preference): `/Users/summerrae/claude_code/claude_flow/docs/plans/2026-04-18-token-efficiency-phase-2.md` + this handoff file.
2. Start Item 1 (MEMORY.md trim) with the invocation above.

Ask before doing anything destructive (memory-repo reset, skill deletions, etc.). Auto-approval does NOT cover those.
