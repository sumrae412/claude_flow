# Audit Path Subflows

Reference for the audit path (Phase 1 triage option — see `audit_path.md` memory). Loaded on-demand when `$audit_scope` is populated and the user's intent is read-only assessment.

---

## Subflow A: Noisy-Signal Ingestion → Prioritized Checklist

**When to use:** The audit input is a log, CI output, or test run with many small findings (lint warnings, noisy test output, accessibility violations, type errors) and the goal is to turn that firehose into a ranked action list.

**Source:** Zach Kogan's (LaunchDarkly) tech-debt reduction workflow.

### Process

1. **Capture the noisy output** to a single file:

   ```bash
   yarn test 2>&1 | tee audit-inputs/test-noise.log
   # or
   ruff check app/ 2>&1 | tee audit-inputs/lint-noise.log
   # or
   yarn a11y 2>&1 | tee audit-inputs/a11y-noise.log
   ```

2. **Dispatch an analyst subagent** (Sonnet, general-purpose) with:

   - Input: the captured log (path only — let the subagent read it)
   - Prompt shape:

     ```
     Analyze this log file. Categorize findings by type and severity
     (CRITICAL / HIGH / MEDIUM / LOW). For each category, count occurrences
     and list the most common offenders (file:line). Output ONLY a markdown
     checklist, grouped by category, ordered by severity then frequency.
     Do NOT propose fixes — this is the audit pass.
     ```

3. **Write output** to `docs/audits/<YYYY-MM-DD>-<topic>-checklist.md`. Each line is a discrete, addressable task:

   ```markdown
   ## CRITICAL
   - [ ] `app/routes/auth.py:142` — silent except, swallows `KeyError` (3 occurrences across file)

   ## HIGH
   - [ ] `app/services/sync.py:88` — N+1 query pattern in `sync_contacts` loop
   ```

4. **Stop here.** The audit path is read-only. Fixes happen in a separate `/claude-flow` invocation where individual checklist items become $requirements.

### Why separate capture from analysis

Piping `yarn test` output directly to the subagent wastes context on retry-able tool output. Capturing to a file first means:

- Re-runs are free (subagent re-reads the file).
- The log is a durable artifact for the audit report.
- Tool-result clearing (Phase 5 Strategy 1) doesn't drop the evidence.

### Why the "no fixes in this pass" constraint matters

Analysts who propose fixes inline lose prioritization discipline. The audit deliverable is a ranked list of problems. Solutions are a later phase's problem — and often one fix resolves multiple checklist items, which you only see after the whole list is written.

---

## Subflow B: (reserved — codebase-health snapshot)

Future subflow for full-tree audits (complexity, cyclomatic scores, dependency graph). Not yet wired.

---

## Related

- `audit_path.md` (memory) — Phase 1 8th triage path, scope → assessment → report flow
- `batch_similar_agents.md` (memory) — fan-out sizing for multi-file audits
- `n_per_entity_fanout.md` (memory) — one-reviewer-per-file for large `$audit_scope.file_count`
