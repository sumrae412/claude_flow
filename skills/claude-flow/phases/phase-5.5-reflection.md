# Phase 5.5: Self-Reflection (RARV Reflect)

<!-- Loaded: after Phase 5 | Dropped: after reflection complete -->

Before dispatching expensive reviewers, the executor pauses to self-assess. Inspired by loki-mode's RARV (Reason-Act-Reflect-Verify) cycle — this is the "Reflect" step that sits between implementation (Act) and review (Verify).

---

## The Reflect Checklist

Run through these questions. If any answer is "no" or "unsure", fix before Phase 6:

1. **Plan adherence** — Does the diff match every numbered step in the plan? Any steps skipped or partially done?
2. **Requirement coverage** — Does `$requirements` from Phase 3 have full coverage? Check each resolved edge case.
3. **Pattern consistency** — Does new code follow the patterns discovered in `$exploration`? Any deviations?
4. **Test quality** — Do tests verify behavior (not implementation)? Are edge cases from Phase 3 tested? For Python targets this is confirmed objectively by Phase 5 step 3c (mutation gate); for non-Python targets it remains a manual check.
5. **Obvious issues** — Read the full diff as if seeing it for the first time. Any code smells, missing error handling, or hardcoded values?
6. **Eval contamination check** — Are you evaluating the diff against `$requirements` (the original spec), or against patterns you see in the code itself? The latter is circular validation.

## How to Execute

```
git diff main --stat           # What files changed
git diff main                  # Full diff review
```

Read the diff. For each file changed, mentally trace the happy path AND the error path. Note issues.

## Outcome

- **All clear** → Proceed to Phase 6
- **Issues found** → Fix them. Re-run affected tests. Then proceed.
- **Architectural concern** → Call Opus advisor (Mid-Implementation checkpoint) before proceeding

## Why This Saves Money

A 2-minute self-check catches ~40% of the issues that Tier 1-2 reviewers would find. At ~$0.08-0.40 per review round, catching these early avoids expensive re-review cycles.
