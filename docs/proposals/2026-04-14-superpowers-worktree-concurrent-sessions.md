# Proposal — superpowers `using-git-worktrees` skill: document concurrent-session trigger

**Status:** Draft — to submit upstream to superpowers plugin
**Author:** claude-flow session, 2026-04-14
**Target:** `plugins/superpowers/skills/using-git-worktrees/SKILL.md` (exact path pending verification in the superpowers repo)

## Context

The superpowers `using-git-worktrees` skill currently documents worktrees for feature isolation and executing implementation plans. It does not explicitly cover the scenario where **multiple Claude Code sessions** are editing the same repo's working tree simultaneously.

## The problem observed

During a session that shipped PR #24 in claude-flow, the following pattern played out three times before diagnosis:

1. Session A (this session) edits `skills/session-learnings/SKILL.md` in `/Users/summerrae/claude_flow/`.
2. On-disk file verified to contain the edit (grep for marker string returns 1).
3. Between turns, a second Claude Code session (Session B, working on `feat/mutation-gate` in the same repo directory) writes its own view of the file — which is stale relative to Session A's edits — back to disk.
4. Session A's next read sees the file reverted to pre-edit state. The system-reminder fires: *"was modified, either by the user or by a linter."*

From Session A's perspective this is indistinguishable from a file-watcher or a hook reverting edits. It took significant investigation (checking symlinks, git hooks, pre-commit config, fswatch install) to rule out local-machine-level causes. The user supplied the key datum: *"another agent reported: feat/mutation-gate has fully diverged from origin/feat/mutation-gate."* That revealed the concurrent-session overlap.

## The fix that worked

Moved the work to an isolated worktree via `git worktree add ../claude_flow-memory-fix -b fix/memory-consolidation-filter main`. Edits in the worktree survived because Session B had no working tree there. PR shipped on first attempt after the move.

## Proposed addition to `using-git-worktrees`

Add a subsection under "When to use worktrees" (or equivalent):

> **Concurrent Claude sessions on the same repo.** If another Claude session might be editing the same repo working tree — sibling terminal, a background orchestration mid-flight, a `finishing-a-development-branch` agent running, an agent dispatched by another skill — spin up a worktree for the current task *before* making edits.
>
> **Symptom of not doing this:** Edit/Write operations silently overwrite each other with no error. The losing session sees "my edits got reverted" after each of its turn boundaries, without any hook, linter, or file-watcher visibly responsible. Diagnosis is expensive (check symlinks → git hooks → pre-commit config → file watchers → settings → etc.). Prevention is cheap.
>
> **Pattern:**
>
> ```bash
> git worktree add ../<repo>-<task-slug> -b <branch> main
> cd ../<repo>-<task-slug>
> ```
>
> Trade-off: ~2 seconds of setup cost; zero risk of concurrent-write clobber. When another Claude session might be live on the same repo, this isn't optional — it's the cheapest safety net.

## Rationale

- The concurrent-session case is increasingly common as users run background orchestrations, finish-branch agents, and parallel claude-flow dispatches.
- Current `using-git-worktrees` docs focus on "isolate this task from current workspace" — a single-session framing. The multi-session case has the same solution but a different trigger that isn't obvious from the existing text.
- The failure mode (silent clobber of edits, no error, no hook to investigate) is exceptionally expensive to diagnose compared to the trivial cost of prevention.

## How to submit

This file lives at `/Users/summerrae/claude_flow/docs/proposals/`. Propose upstream either via:
1. Open an issue/PR in the superpowers plugin repo linking to this file, or
2. Copy the proposed addition into the superpowers repo's own contribution flow.

Path to the skill in the superpowers plugin needs to be verified before submitting — the session-learnings agent flagged this as uncertain.

## Related

- Memory entry: `concurrent_session_worktree_isolation.md` (written this session)
- Compiled concept: `knowledge/concepts/multi-writer-coordination.md` (created this session)
- claude-flow PR #24: memory consolidation fix + 1-hop expansion (the shipping pipeline that surfaced this)
