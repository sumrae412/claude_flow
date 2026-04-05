---
name: update-defensive-backend
description: Use when adding a new bug or pattern to the defensive-backend-flows skill, or when the user says to update it
---

# Update Defensive Backend Flows Skill

## Quick Steps

1. **Add the bug** to `~/.claude/skills/defensive-backend-flows/evidence.md` using the template at the top
2. **Decide:** Does this fit an existing rule (1-5) or need a new rule?
3. **RED test:** Run the pressure scenario prompt as a subagent WITHOUT the skill → document if the bug reproduces
4. **Update SKILL.md** if needed (new rule, stronger wording, new red flag)
5. **GREEN test:** Run same prompt WITH the skill injected → verify the fix
6. **Log results** in evidence.md under the test results section

## When to Skip RED/GREEN

- If the bug fits an existing rule exactly and you just want to log it → skip testing, just add to evidence.md
- If you're adding a new rule → RED/GREEN is mandatory

## Files

| File | What to Edit |
|------|-------------|
| `~/.claude/skills/defensive-backend-flows/evidence.md` | Add bug + test results |
| `~/.claude/skills/defensive-backend-flows/test-scenarios.md` | Add pressure scenario |
| `~/.claude/skills/defensive-backend-flows/SKILL.md` | Add/update rules (only if needed) |

## RED Test Template

```
Task tool → subagent_type: general-purpose, model: haiku
Prompt: [paste pressure scenario prompt from test-scenarios.md]
DO NOT include the skill content.
```

## GREEN Test Template

```
Task tool → subagent_type: general-purpose, model: haiku
Prompt:
  "You follow the defensive-backend-flows checklist:
   [paste the 5 rules summary from SKILL.md]
   ---
   [paste pressure scenario prompt]"
```
