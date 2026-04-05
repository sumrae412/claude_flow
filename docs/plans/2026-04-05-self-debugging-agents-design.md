# Self-Debugging Agents Design

**Created:** 2026-04-05 | **Status:** approved

## Summary

Add self-debugging capabilities to claude-flow: agents that autonomously detect, diagnose, and fix failures, learn from novel failures, and share learned patterns via GitHub. Uses a hybrid architecture — inline retry loops (Approach A) optimized by structured event emission (Approach C) — to get fast value while building the extensibility backbone for future self-improvement capabilities (prompt optimization, performance tracking, code generation self-modification).

## Architecture

Phase retry logic stays inline. Every failure/diagnosis/resolution emits a structured event to a JSONL log. A persistent failure catalog stores known patterns and fix strategies. Novel failures go through multi-model validation before entering the catalog.

```
Phase 5 test fails
  → emit failure:test event (structured payload)
  → inline retry loop:
      1. Load failure catalog (via memory-injection)
      2. Match against known patterns
      3. Known + high confidence → apply fix, emit resolution:known
      4. No match or low confidence → dispatch diagnosis subagent
         → diagnose, fix, emit resolution:novel
         → multi-model review (plancraft_review.py)
         → append to catalog, commit + push to GitHub
      5. Retry (up to 3 attempts, escalating thinking budget)
      6. Exhausted → emit failure:unresolved, surface to user
```

## Components

### 1. Inline Retry Loop

Added to Phases 5 and 6 of `code-creation-workflow/SKILL.md`.

**Phase 5 (Implementation):** Wraps each TDD step. Test fails → retry loop kicks in before moving to next step.

**Phase 6 (Review):** When a reviewer flags a blocking issue, the fix goes through the retry loop instead of a blind edit-and-hope.

**Phases 0-4:** No retry loop — failures here are exploratory, not fixable by retry.

**Retry mechanics:**
- Max 3 attempts per failure
- Thinking budget escalates: original level → one level up → ultrathink
- Each attempt re-runs verification (test, lint, build) after applying fix

### 2. Event Log

File: `memory/failure-events.jsonl` — one JSON line per event.

**Failure event:**
```json
{
  "ts": "2026-04-05T14:32:01Z",
  "session": "abc123",
  "phase": 5,
  "type": "failure:test",
  "step": "3/12",
  "files": ["services/auth.py", "tests/test_auth.py"],
  "error_class": "assertion_mismatch",
  "error_summary": "Expected 401, got 200 — missing auth middleware on new route",
  "attempt": 1,
  "resolution": null
}
```

**Resolution event:**
```json
{
  "ts": "2026-04-05T14:32:45Z",
  "session": "abc123",
  "phase": 5,
  "type": "resolution:novel",
  "step": "3/12",
  "error_class": "assertion_mismatch",
  "root_cause": "New route added without copying auth decorator from adjacent routes",
  "fix_strategy": "Check all route files in diff for missing auth decorators",
  "attempts_used": 1,
  "catalog_entry_added": true
}
```

**Event types:**

| Type | When |
|------|------|
| `failure:test` | Test runner returns non-zero |
| `failure:lint` | Lint/type-check fails |
| `failure:review` | Phase 6 reviewer flags blocking issue |
| `failure:build` | Build/compile error |
| `resolution:known` | Fixed using existing catalog pattern |
| `resolution:novel` | Fixed via diagnosis, new pattern learned |
| `failure:unresolved` | Exhausted retries, surfaced to user |

**Starting error classes** (grow organically as novel failures are diagnosed):
- `syntax_error` — parse failures, typos
- `import_missing` — module not found, circular import
- `assertion_mismatch` — test expects X, got Y
- `type_error` — wrong types passed/returned
- `lint_violation` — style/formatting rules
- `missing_pattern` — forgot defensive pattern (auth, error handling, guard clause)
- `architectural_drift` — implementation diverged from plan
- `regression` — broke something that was working

### 3. Failure Catalog

File: `memory/failure-catalog.md` — loaded by memory-injection alongside gotchas. Committed and pushed to GitHub on novel resolutions.

**Format:**
```markdown
# Failure Catalog

## assertion_mismatch
### missing-auth-decorator
- **Pattern:** New route added without auth decorator
- **Signal:** Test expects 401, gets 200 on protected endpoint
- **Fix:** Check all route files in diff for missing auth decorators, copy from adjacent routes
- **Confidence:** high (3 hits, 0 false positives)
- **Last seen:** 2026-04-05
```

**Confidence scoring:**
- `high` — 3+ hits, 0 false positives
- `medium` — 1-2 hits
- `low` — new entry or has false positives

### 4. Diagnosis Subagent

Dispatched on novel failures (no catalog match or low confidence match).

**Prompt:**
```
You are a failure diagnosis agent. A plan step failed and the error
doesn't match any known pattern in the failure catalog.

FAILED STEP: [step number and description from plan]
ERROR OUTPUT: [full stderr/stdout from the failed command]
FILES INVOLVED: [list of files touched by this step]
FAILURE CATALOG: [current catalog entries for this error_class, if any partial matches]
PLAN CONTEXT: [the 2 steps before and after, so you understand intent]

Think harder about this...

1. Classify the error (use existing error_class if it fits, or propose a new one)
2. Identify root cause (not the symptom — WHY did this happen?)
3. Propose fix strategy (specific, actionable — not "check the code")
4. Assess: is this a one-off or a pattern likely to recur?

Return structured JSON:
{
  "error_class": "...",
  "root_cause": "...",
  "fix_strategy": "...",
  "recurrence_likelihood": "high|medium|low",
  "fix_code": "... (the actual edit to make, if straightforward)"
}
```

**Model:** Sonnet for speed. Escalates to Opus if first diagnosis doesn't resolve on retry.

**Boundaries:** Does not rewrite plans, modify skills, or retry itself. One diagnosis per attempt; the retry loop handles iteration.

### 5. Multi-Model Validation

Before a novel catalog entry is persisted, it goes through `plancraft_review.py`:

- **DeepSeek:** "Would this fix strategy produce false positives? What edge cases would it miss?"
- **Codex:** "Is the error_class taxonomy correct? Does the fix_strategy conflict with existing catalog entries?"

If reviewers flag issues → refine entry, re-review (1 round max).
If reviewers approve → append to catalog, commit, push.

The diagnosis prompt itself is also reviewed via multi-model validation during initial implementation.

### 6. Catalog Push Hook

File: `hooks/post-retry-push.sh` — new Tier 1 hook.

Triggered after catalog update. Verifies remote is reachable and push succeeded. Falls back to local-only if offline.

## Integration with Existing Systems

**memory-injection** — No changes to the skill. Failure catalog gets a new domain mapping:

| Domain | Catalog sections loaded |
|--------|----------------------|
| `routes` | `missing_pattern`, `assertion_mismatch` |
| `services` | `import_missing`, `type_error` |
| `models` | `regression`, `architectural_drift` |
| `templates` | `lint_violation`, `missing_pattern` |
| `tests` | `assertion_mismatch`, `regression` |
| `*` (all) | `syntax_error`, `import_missing` |

**session-learnings** — New data source. Reads `failure-events.jsonl` to:
- Spot cross-session patterns ("this error_class keeps recurring")
- Flag catalog entries with decaying confidence (not hit in 30+ days)
- Propose promotions: catalog entry with 5+ hits → defensive pattern in relevant skill

**code-creation-workflow** — Three insertion points:
1. Phase 5: wrap TDD step execution in retry loop
2. Phase 6: wrap review-fix cycle in retry loop
3. Post-phase-6: commit + push catalog if changed

**hooks** — One new Tier 1 hook: `post-retry-push.sh`

## What Stays Untouched

- Phases 0-4 (no retry logic)
- All existing skills, hooks, MCP server
- The install script (new files go in `memory/` and `hooks/`, already in the install path)

## Autonomy Model

Fully autonomous retry for all failure types. User only sees failures that survive 3 attempts.

## Future Extensibility

The event log (`failure-events.jsonl`) is the foundation for the other three self-improvement capabilities:
- **Automated prompt optimization** — analyze which prompts produce fewer failures, auto-tune
- **Performance-driven learning** — track time/tokens per phase, adjust agent count and model choice
- **Code generation self-modification** — catalog entries with 5+ hits get promoted to skill-level defensive patterns automatically

These can all subscribe to the same event stream without modifying the retry loop.
