---
name: session-handoff
description: Export current session state for seamless resume in next session. Use at end of sessions, before closing, or when context gets heavy. Writes handoff.md with phase, modified files, blockers, and next steps.
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

Run these commands to collect current session state:

```bash
git branch --show-current
git diff --name-only
git diff --cached --name-only
```

Also check:
- **Phase/step**: If code-creation-workflow is active, identify the current phase and step number from TodoWrite state or recent conversation context
- **Open questions**: Unresolved ambiguities from the conversation (design decisions deferred, unclear requirements)
- **Ruled out**: Approaches, tools, or paths that were tried and failed or deliberately abandoned — include *why* so the next session doesn't re-explore them
- **Blockers**: Failing tests, missing dependencies, awaiting external input
- **Next steps**: If a plan file exists in `docs/plans/`, read the next 3 incomplete steps

### Step 2: Write handoff.md

Write to `$PROJECT/.claude/handoff.md` (create `.claude/` dir if needed):

```markdown
# Session Handoff
**Date:** YYYY-MM-DD HH:MM
**Branch:** feature/xyz
**Phase:** 5 (Implementation), Step 7 of 12

## Modified files
- `app/services/billing.py` — Added invoice generation service
- `tests/test_billing.py` — Tests for invoice generation

## Ruled out
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
