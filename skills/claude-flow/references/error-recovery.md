# Error Recovery

| Situation | Resolution | Action |
|-----------|------------|--------|
| Explorer returns poor results | RETRY | Re-dispatch with narrower prompt, or explore manually |
| Explorer times out | RETRY | Re-dispatch with narrower scope (single concern) |
| Both architectures rejected | PAUSE | Ask user what's missing, re-run with new constraints |
| Only one viable architecture (3+ files or cross-cutting) | PAUSE | Present with trade-offs, ask if user wants a second option |
| Tests fail during implementation | RETRY | Fix immediately — do not proceed to next step. Use scientific method: hypothesis → minimal test → verify. |
| Tests fail 3+ times on same step | PAUSE | **3-Strike Rule.** Stop. Question the Phase 4 architecture, not the code. Ask user: design wrong or test wrong? |
| Reviewer finds critical issue | RETRY | Fix before finishing, re-run verification |
| Reviewer finds pre-existing bug | RETRY | Fix it (fix-what-you-find). Log as pre-existing in commit |
| CI fails after fix | RETRY | Check `git status` between attempts (ruff may modify files). Re-run up to 3 attempts. Same error twice → escalate immediately |
| CI passes locally, fails in PR | PAUSE | Check env-specific issues. Fix root cause, don't `--no-verify` |
| User wants to stop | PAUSE | Summarize: phase, what's done, what remains, next step to resume |
| Wrong architecture chosen | RETRY | Revert uncommitted work, re-architect with new constraints |
| debate-team API fails | DEGRADE | Continue with available reviewers. Note gap. If all fail → "unreviewed" |
| Subagent produces conflicting results | DEGRADE | Evaluate each finding against codebase evidence. ADOPT only verified |
| Context window pressure | DEGRADE | Compress completed phases into structured summary; keep plan + current step |
| Plan references missing files | RETRY | Grep for actual paths before assuming the plan is wrong |
| Batch review times out or fails | DEGRADE | Proceed with subagent reviewers only. Note "batch unavailable" in deduplication. No blocking |

**Resolution types:** RETRY = fix and re-run. PAUSE = stop and ask user. DEGRADE = continue with reduced capability.
