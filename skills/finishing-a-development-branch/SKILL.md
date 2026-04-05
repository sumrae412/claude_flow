---
name: finishing-a-development-branch
description: ARCHIVED — Use /cleanup instead. Branch cleanup, worktree teardown, session-learnings, and config/skills repo sync are now handled by the cleanup skill.
---

# ARCHIVED

This skill has been replaced by `/cleanup`, which adds:
- `ExitWorktree` tool integration (instead of manual `git worktree remove`)
- Config/skills/memory repo sync after session-learnings
- Smarter state detection (worktree vs regular branch)

Use `/cleanup` instead.
