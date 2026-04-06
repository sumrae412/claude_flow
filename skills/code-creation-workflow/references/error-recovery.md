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
| Scratchpad write fails or is unreadable by Explorer B/C | RETRY | Re-dispatch Explorer A with explicit write instruction; confirm file exists before dispatching dependents |
| Gap-fill explorer returns nothing useful | DEGRADE | Proceed with existing findings; note the gap in architecture context; flag for missed-context audit |
| Registry has no data for current task type | DEGRADE | Fall back to default variant selection and thinking budgets; log dispatches so future sessions benefit |
| Build-state conflict detected between parallel specialists | RETRY | Halt parallel work; merge conflicting state entries manually; re-dispatch affected specialist with resolved state |
| Meta-reviewer identifies systemic pattern across all reviewers | PAUSE | Stop. The pattern indicates a Phase 4 architecture problem, not implementation drift. Re-evaluate before proceeding |
| Collaborative rescue agent also fails | PAUSE | Two failures on same step = structural blocker. Stop, summarize what's been tried, ask user for direction |
| Tier classified as moderate mid-session but task is clearly complex | PAUSE | Re-run complexity classifier with current evidence; upgrade tier before next phase; do not continue on wrong tier |
| available_in_prompt context causes explorer to miss key files | RETRY | Broaden context window or re-dispatch with explicit file list; log miss type in missed-context log |

| Constraint compilation fails (bad CLAUDE.md parse or missing source) | DEGRADE | Skip soft constraints, keep any hard constraints that compiled successfully. Log gap for manual review |
| RAG embedding API fails (OpenAI unavailable) | DEGRADE | Skip RAG context injection — memory-injection still provides PROJECT GOTCHAS. Note "RAG unavailable" in session log |
| Symbolic verifier times out (soft check LLM call hangs) | DEGRADE | Accept agent output unchecked. Log unverified output for post-session review. Hard checks still run (no LLM needed) |
| Federation push fails (Supabase unreachable) | DEGRADE | Local registry unaffected — session data preserved locally. Retry push on next session start |
| Controlled skip degrades session quality (quality drops > 0.2 vs baseline) | RETRY | Immediately dispatch the skipped agent with full context. Record the quality drop as negative evidence for future skips |

**Resolution types:** RETRY = fix and re-run. PAUSE = stop and ask user. DEGRADE = continue with reduced capability.
