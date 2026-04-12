---
name: session-handoff
description: Export current session state for seamless resume in next session. Use at end of sessions, before closing, or when context gets heavy. Writes handoff.md with phase, modified files, blockers, and next steps. Also supports --abandon mode for documenting dead ends and failed approaches.
user-invocable: true
---

# Session Handoff

## When to Invoke

- End of a work session
- User says "save state", "hand off", "continue later", or "wrap up"
- Before closing when mid-feature or mid-plan
- Context window is getting heavy and a fresh session is preferable
- The Stop hook can trigger this automatically when configured

## The Process

### Step 1: Gather State

**Primary source — workflow state file:**

If `.claude/workflow-state.json` exists, read it first. It provides structured data for:
- Current phase and step (replaces guessing from conversation context)
- Phase history with timestamps (replaces manual reconstruction)
- Task summary (replaces re-reading the original request)
- Produced artifacts (replaces checking which docs exist)

Fall back to git/conversation context only for fields not in the state file (e.g., open questions, ruled-out approaches).

Run these commands to collect current session state:

```bash
git branch --show-current
git diff --name-only
git diff --cached --name-only
```

Also check:
- **Phase/step**: If claude-flow is active, identify the current phase and step number from TodoWrite state or recent conversation context
- **Open questions**: Unresolved ambiguities from the conversation (design decisions deferred, unclear requirements)
- **Ruled Out**: Approaches, tools, or paths that were tried and failed or deliberately abandoned — include *why* so the next session doesn't re-explore them
- **Blockers**: Failing tests, missing dependencies, awaiting external input
- **Next steps**: If a plan file exists in `docs/plans/`, read the next 3 incomplete steps

### Step 2: Write handoff.md

Write to `$PROJECT/.claude/handoff.md` (create `.claude/` dir if needed):

```markdown
# Session Handoff
**Date:** YYYY-MM-DD HH:MM
**Branch:** feature/xyz
**Phase:** <from workflow-state.json: current_phase.id (current_phase.name), Step current_phase.step>
**Path:** <from workflow-state.json: current_phase.path>
**Iteration:** <from workflow-state.json: current_phase.iteration / max_iterations>
**Task:** <from workflow-state.json: task_summary>

## Modified files
- `app/services/billing.py` — Added invoice generation service
- `tests/test_billing.py` — Tests for invoice generation

## Ruled Out
- `approach/tool/path` — why it failed or was abandoned

## Open questions
- None

## Blockers
- None

## Next steps
1. Implement webhook handler for payment confirmation
2. Write tests for webhook validation
3. Add error handling for failed payments
```

Notes on content:
- For each modified file, add a short description of what changed (infer from context or `git diff --stat`)
- For "Ruled out", capture any approach or investigation path that hit a dead end — include the reason (e.g., "tried X but it caused Y", "investigated Z but it was unrelated to root cause"). This prevents future sessions from re-exploring dead ends.
- If no plan file exists, derive next steps from conversation context and recent TODOs
- Use "None" explicitly for empty sections — don't omit them

### Step 3: Announce

Tell the user:
- What was saved and where (`$PROJECT/.claude/handoff.md`)
- That the SessionStart hook will surface this automatically at the top of the next session
- Any blockers or open questions they should be aware of before closing

---

## Abandon Mode

When invoked with `--abandon` or when the user says "abandon this", "this didn't work", "scrap this approach", or "dead end":

### Step 1: Gather Abandon Context

Collect the same state as a normal handoff (Step 1 above), plus ask:
- **What was the approach?** (infer from conversation if possible, confirm with user)
- **Why is it being abandoned?** (technical limitation, wrong direction, better approach found, etc.)
- **What was learned?** (insights that should inform future attempts)

### Step 2: Write Abandon Record

Create `$PROJECT/.claude/abandoned/` directory if needed. Write to `$PROJECT/.claude/abandoned/YYYY-MM-DD-<topic>.md`:

```markdown
# Abandoned: <topic>
**Date:** YYYY-MM-DD
**Branch:** feature/xyz (deleted / kept for reference)

## What was attempted
Brief description of the approach and what was built

## Why abandoned
- Reason 1
- Reason 2

## What was learned
- Insight that should inform future attempts
- Technical discovery worth preserving

## Files modified
- `path/to/file.py` — what was changed
```

### Step 3: Clean Up

- If on a feature branch with no commits worth keeping: offer to delete the branch
- If on a feature branch with useful partial work: note it as "kept for reference" in the record
- Remove `.claude/handoff.md` if it exists (the abandon record replaces it)

### Step 4: Announce

Tell the user:
- Abandon record saved to `.claude/abandoned/YYYY-MM-DD-<topic>.md`
- The SessionStart hook will surface this as "previously ruled out" context in future sessions
- Whether the branch was deleted or kept

---

## Next Steps

- **Resuming in a new session?** Open `.claude/handoff.md` — it contains your phase, modified files, blockers, and next steps.
- **Dead end?** Use `/session-handoff --abandon` to archive findings to `.claude/abandoned/` so future sessions avoid re-exploring.
- **Capture lessons before closing?** Use `/session-learnings` to persist insights to memory (auto-committed).
