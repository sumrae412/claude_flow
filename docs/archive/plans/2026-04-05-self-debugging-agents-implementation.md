# Self-Debugging Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add autonomous failure detection, diagnosis, and retry to claude-flow Phases 5-6, backed by a persistent failure catalog and structured event log.

**Architecture:** Inline retry loops in the existing code-creation-workflow, with structured event emission to a JSONL log. A diagnosis subagent handles novel failures. Multi-model validation (plancraft_review.py) gates catalog entries before they're pushed to GitHub.

**Tech Stack:** Markdown (skill files, catalog), JSONL (event log), shell (push hook), Python (plancraft_review.py already exists)

---

### Task 1: Create Failure Catalog Seed File

**Files:**
- Create: `memory/failure-catalog.md`

**Step 1: Write the seed catalog**

```markdown
# Failure Catalog

> Auto-updated by the self-debugging retry loop. Each entry is a known failure
> pattern with a documented fix strategy. Loaded by memory-injection into
> subagent prompts to prevent known mistakes from recurring.
>
> **Format:** Grouped by error_class. Each entry has Pattern, Signal, Fix,
> Confidence (low/medium/high), and Last seen date.
>
> **Confidence scoring:**
> - high — 3+ hits, 0 false positives
> - medium — 1-2 hits
> - low — new entry or has false positives

## syntax_error

_(no entries yet — populated by self-debugging loop)_

## import_missing

_(no entries yet)_

## assertion_mismatch

_(no entries yet)_

## type_error

_(no entries yet)_

## lint_violation

_(no entries yet)_

## missing_pattern

_(no entries yet)_

## architectural_drift

_(no entries yet)_

## regression

_(no entries yet)_
```

**Step 2: Commit**

```bash
git add memory/failure-catalog.md
git commit -m "feat: add failure catalog seed file for self-debugging agents"
```

---

### Task 2: Create Event Log Infrastructure

**Files:**
- Create: `memory/failure-events.jsonl`
- Create: `scripts/emit-failure-event.sh`

**Step 1: Create empty JSONL file**

Create `memory/failure-events.jsonl` as an empty file (events will be appended).

**Step 2: Write the event emission helper script**

```bash
#!/usr/bin/env bash
# emit-failure-event.sh — Append a structured failure/resolution event to the JSONL log.
#
# Usage:
#   emit-failure-event.sh <json-payload>
#
# The payload is a single JSON object. This script adds the timestamp and
# appends it as one line to memory/failure-events.jsonl.

set -euo pipefail

EVENTS_FILE="${CLAUDE_FLOW_DIR:-$(cd "$(dirname "$0")/.." && pwd)}/memory/failure-events.jsonl"
PAYLOAD="$1"

# Inject timestamp
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EVENT=$(echo "$PAYLOAD" | python3 -c "
import sys, json
obj = json.load(sys.stdin)
obj['ts'] = '$TS'
print(json.dumps(obj))
")

echo "$EVENT" >> "$EVENTS_FILE"
```

**Step 3: Make executable and commit**

```bash
chmod +x scripts/emit-failure-event.sh
git add memory/failure-events.jsonl scripts/emit-failure-event.sh
git commit -m "feat: add failure event log and emission script"
```

---

### Task 3: Create the Catalog Push Hook

**Files:**
- Create: `hooks/tier1/failure-catalog-push.sh`
- Modify: `hooks/hook-registry.json`

**Step 1: Write the push hook**

```bash
#!/usr/bin/env bash
# failure-catalog-push.sh — Commit and push failure-catalog.md after novel resolution.
#
# Called by the retry loop after a resolution:novel event adds a new catalog entry.
# Falls back gracefully if remote is unreachable.

set -euo pipefail

REPO_DIR="${CLAUDE_FLOW_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
CATALOG="$REPO_DIR/memory/failure-catalog.md"
EVENTS="$REPO_DIR/memory/failure-events.jsonl"

cd "$REPO_DIR"

# Stage catalog and events
git add "$CATALOG" "$EVENTS"

# Check if there are staged changes
if git diff --cached --quiet; then
  echo "No catalog changes to push."
  exit 0
fi

git commit -m "chore: update failure catalog with new pattern"

# Push with timeout — fall back to local-only if offline
if timeout 10 git push 2>/dev/null; then
  echo "Failure catalog pushed to remote."
else
  echo "WARNING: Could not push to remote. Catalog updated locally only."
  echo "Run 'git push' manually when network is available."
fi
```

**Step 2: Make executable**

```bash
chmod +x hooks/tier1/failure-catalog-push.sh
```

**Step 3: Add to hook registry**

Read `hooks/hook-registry.json`, add an entry for the new hook under the tier1 section:

```json
{
  "name": "failure-catalog-push",
  "file": "tier1/failure-catalog-push.sh",
  "trigger": "manual",
  "description": "Commit and push failure catalog after novel failure resolution"
}
```

**Step 4: Commit**

```bash
git add hooks/tier1/failure-catalog-push.sh hooks/hook-registry.json
git commit -m "feat: add failure catalog push hook (tier 1)"
```

---

### Task 4: Add Failure Catalog Domain Mapping to Memory Injection

**Files:**
- Modify: `skills/code-creation-workflow/references/memory-injection.md`

**Step 1: Read the current file**

Read `skills/code-creation-workflow/references/memory-injection.md` to find the domain mapping table.

**Step 2: Add failure catalog domain mapping**

After the existing "Domain → Gotcha Mapping" section, add a new section:

```markdown
## Domain → Failure Catalog Mapping

When dispatching subagents, also load matching failure catalog sections to prevent known-bad approaches.

| Domain | Catalog sections loaded |
|--------|----------------------|
| routes | `missing_pattern`, `assertion_mismatch` |
| services | `import_missing`, `type_error` |
| models | `regression`, `architectural_drift` |
| ui | `lint_violation`, `missing_pattern` |
| testing | `assertion_mismatch`, `regression` |
| `*` (all) | `syntax_error`, `import_missing` |

Injection follows the same template as gotchas:

```
KNOWN FAILURE PATTERNS (from failure catalog — avoid these approaches):
- [Pattern]: [Signal] → [Fix strategy]
- [... max 5 entries, highest confidence first]
```
```

**Step 3: Commit**

```bash
git add skills/code-creation-workflow/references/memory-injection.md
git commit -m "feat: add failure catalog domain mapping to memory-injection"
```

---

### Task 5: Write the Diagnosis Subagent Prompt Template

**Files:**
- Create: `skills/code-creation-workflow/references/diagnosis-subagent.md`

**Step 1: Write the prompt template**

```markdown
# Diagnosis Subagent Prompt Template

> Used by the Phase 5/6 retry loop when a failure doesn't match any known
> catalog pattern (or matches with low confidence).

## Prompt

```
You are a failure diagnosis agent. A plan step failed and the error
doesn't match any known pattern in the failure catalog.

FAILED STEP: [step number and description from plan]
ERROR OUTPUT: [full stderr/stdout from the failed command]
FILES INVOLVED: [list of files touched by this step]
FAILURE CATALOG (partial matches): [entries from the same error_class, if any]
PLAN CONTEXT: [the 2 steps before and after, so you understand intent]

Think harder about this...

1. Classify the error. Use an existing error_class if it fits:
   syntax_error, import_missing, assertion_mismatch, type_error,
   lint_violation, missing_pattern, architectural_drift, regression.
   If none fit, propose a new error_class name (snake_case).

2. Identify root cause — not the symptom, but WHY this happened.
   Trace back: what assumption was wrong? What was missed?

3. Propose fix strategy — specific and actionable. Not "check the code"
   but "add auth decorator to the new route, matching pattern in
   routes/client_routes.py:45".

4. Assess recurrence: is this a one-off typo or a pattern likely to
   repeat in future features?

Return ONLY this JSON (no markdown wrapping):
{
  "error_class": "...",
  "root_cause": "...",
  "fix_strategy": "...",
  "recurrence_likelihood": "high|medium|low",
  "fix_code": "... (the actual edit to apply, if straightforward — omit if complex)"
}
```

## Model Selection

- **Default:** Sonnet (most failures are mechanical)
- **Escalation:** If the first diagnosis doesn't resolve the failure on retry,
  re-dispatch with Opus and `ultrathink` prefix

## Boundaries

- Does NOT rewrite the plan (architectural drift → surface to user)
- Does NOT modify skills (that's session-learnings' job)
- Does NOT retry itself (one diagnosis per attempt, retry loop handles iteration)
```

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/references/diagnosis-subagent.md
git commit -m "feat: add diagnosis subagent prompt template"
```

---

### Task 6: Validate Diagnosis Prompt via Multi-Model Review

**Files:**
- Read: `scripts/plancraft_review.py`
- Read: `skills/code-creation-workflow/references/diagnosis-subagent.md`

**Step 1: Create a temporary scope file**

Write a scope file describing what the diagnosis prompt should and shouldn't do:

```
SCOPE: Diagnosis subagent for the self-debugging retry loop.
MUST: Classify errors accurately, identify root causes, propose actionable fixes, return structured JSON.
MUST NOT: Rewrite plans, modify skills, retry itself, propose vague fixes like "check the code".
CONTEXT: Dispatched when Phase 5/6 failure doesn't match failure catalog. Gets error output, plan step, file list, catalog entries.
```

**Step 2: Run DeepSeek review**

```bash
python3 scripts/plancraft_review.py \
  --reviewer deepseek \
  --plan-file skills/code-creation-workflow/references/diagnosis-subagent.md \
  --scope-file /tmp/diagnosis-scope.txt
```

**Step 3: Run Codex review**

```bash
python3 scripts/plancraft_review.py \
  --reviewer codex \
  --plan-file skills/code-creation-workflow/references/diagnosis-subagent.md \
  --scope-file /tmp/diagnosis-scope.txt
```

**Step 4: Apply any HIGH-priority feedback from reviewers**

Edit `diagnosis-subagent.md` to address findings. Ignore cosmetic suggestions.

**Step 5: Commit**

```bash
git add skills/code-creation-workflow/references/diagnosis-subagent.md
git commit -m "refine: harden diagnosis prompt via multi-model review"
```

---

### Task 7: Add Retry Loop to Phase 5 in SKILL.md

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md` (around line 522, after the existing TDD step execution block)

**Step 1: Read Phase 5 current content**

Read lines 493-560 of SKILL.md to confirm exact insertion point.

**Step 2: Replace the Phase 5 step execution block**

Find the existing "For each plan step:" block (lines ~522-543) and replace it with the retry-wrapped version:

```markdown
For each plan step:

```
1. Write test FIRST (test-driven-development skill)
   - Test the expected behavior, not the implementation
   - Include edge cases identified in Phase 3

2. Implement to make the test pass
   - Follow patterns discovered in Phase 2
   - Apply defensive patterns throughout:
     UI → guard clauses, feedback states, loading/error/success
     Backend → input validation, error handling, no silent swallows

3. Run test → verify green
   If PASS → continue to step 4
   If FAIL → enter RETRY LOOP (see below)

4. Run static analysis on changed files (catch issues early):
   semgrep --config=.semgrep.yml <changed-files>
   ast-grep scan <changed-directory>
   If PASS → continue to step 5
   If FAIL → enter RETRY LOOP for lint_violation

5. Mark TodoWrite item complete
```

### Phase 5 Retry Loop

When a test or static analysis check fails during implementation:

```
RETRY LOOP (max 3 attempts):
  attempt = 1
  thinking_levels = [original_level, one_level_up, "ultrathink"]

  WHILE attempt <= 3 AND failure unresolved:

    1. EMIT failure event:
       Run: scripts/emit-failure-event.sh '{
         "session": "<session-id>",
         "phase": 5,
         "type": "failure:test|failure:lint",
         "step": "<step-number>",
         "files": [<files-touched>],
         "error_class": "<best-guess-class>",
         "error_summary": "<first 200 chars of error output>",
         "attempt": <attempt>,
         "resolution": null
       }'

    2. MATCH against failure catalog:
       - Load catalog entries for matched domains (via memory-injection mapping)
       - Compare error output against each entry's Signal field
       - If match with high/medium confidence:
           → Apply the documented Fix strategy
           → EMIT resolution:known event
       - If no match or low confidence:
           → Dispatch DIAGNOSIS SUBAGENT (see references/diagnosis-subagent.md)
           → Model: sonnet (attempt 1-2), opus (attempt 3)
           → Thinking: thinking_levels[attempt - 1]
           → Apply the returned fix_strategy / fix_code
           → If recurrence_likelihood is medium or high:
               → Draft new catalog entry
               → Run multi-model validation (plancraft_review.py)
               → If approved: append to memory/failure-catalog.md
               → Run: hooks/tier1/failure-catalog-push.sh
           → EMIT resolution:novel event

    3. RE-RUN verification (test or static analysis)
       If PASS → EMIT resolution event, EXIT loop, continue to next step
       If FAIL → increment attempt, CONTINUE loop

  IF attempt > 3:
    EMIT failure:unresolved event
    Surface to user: "Step X failed after 3 attempts. Root cause: [diagnosis].
    Last error: [output]. Manual intervention needed."
    WAIT for user guidance before proceeding.
```

**Token budget escalation during retries:**

| Attempt | Thinking Budget | Model |
|---------|----------------|-------|
| 1 | Same as original step | sonnet |
| 2 | One level up from original | sonnet |
| 3 | `ultrathink` | opus |
```

**Step 3: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: add self-debugging retry loop to Phase 5"
```

---

### Task 8: Add Retry Loop to Phase 6 in SKILL.md

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md` (around line 742, after "Merge & fix" line)

**Step 1: Read Phase 6 merge & fix section**

Read lines 740-750 of SKILL.md to confirm exact insertion point.

**Step 2: Insert retry loop after the merge & fix instruction**

After the existing "fix HIGH+ issues" line, add:

```markdown
### Phase 6 Retry Loop

When fixing a review finding, use the same retry loop as Phase 5. Review fixes are especially prone to introducing new issues — the retry loop catches cascading failures.

```
For each HIGH+ review finding to fix:

  1. Apply fix
  2. Run affected tests + static analysis
  3. If PASS → mark finding resolved, continue
  4. If FAIL → enter RETRY LOOP (same as Phase 5, but with):
     - type: "failure:review"
     - Include the original review finding in the diagnosis context
     - Diagnosis subagent gets both the review comment AND the error output

  After all findings fixed:
  5. Re-run FULL test suite (not just affected tests)
  6. If new failures → these are regressions from fixes
     Enter RETRY LOOP with error_class "regression"
```

**Step 3: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: add self-debugging retry loop to Phase 6"
```

---

### Task 9: Update Session-Learnings to Consume Failure Events

**Files:**
- Modify: `skills/session-learnings/SKILL.md`

**Step 1: Read current session-learnings SKILL.md**

Read the file to find the "Session Context" compilation template and the background agent prompt.

**Step 2: Add failure events to session context compilation**

In the "Step 1: Compile Session Context" section, add a new bullet:

```markdown
- Failure events: [read memory/failure-events.jsonl for this session's events —
  count by type, note any failure:unresolved, list novel patterns added to catalog]
```

**Step 3: Add failure event analysis to the background agent prompt**

In the background agent prompt (Step 2), add after the "## Reflection Questions" section:

```markdown
## Failure Event Analysis (REQUIRED when failure-events.jsonl has entries)

Read memory/failure-events.jsonl and analyze:

10. **Pattern frequency:** Which error_classes appear most? Should any become
    a defensive pattern in the relevant skill (e.g., defensive-backend-flows)?
    Threshold: 5+ occurrences across sessions → propose skill promotion.

11. **Catalog health:** Are there catalog entries that haven't been hit in
    30+ days? Flag them for review (may be stale or too specific).

12. **Unresolved failures:** Any failure:unresolved events? These represent
    gaps in the self-debugging system. Propose: new catalog entry with
    the manual resolution the user applied, OR a skill update to prevent
    the failure class entirely.
```

**Step 4: Commit**

```bash
git add skills/session-learnings/SKILL.md
git commit -m "feat: wire failure events into session-learnings analysis"
```

---

### Task 10: Update install.sh to Include New Files

**Files:**
- Modify: `install.sh`

**Step 1: Read install.sh**

Read the file to find where skills, scripts, and hooks are copied.

**Step 2: Add new files to install targets**

Add these to the appropriate copy sections:

- `memory/failure-catalog.md` → copied to target project's memory dir (or `~/.claude/memory/`)
- `memory/failure-events.jsonl` → created empty at target location if not exists
- `scripts/emit-failure-event.sh` → copied to `~/.claude/scripts/`
- `hooks/tier1/failure-catalog-push.sh` → copied to `~/.claude/hooks/tier1/`
- `skills/code-creation-workflow/references/diagnosis-subagent.md` → copied with skill

**Step 3: Commit**

```bash
git add install.sh
git commit -m "feat: add self-debugging files to install script"
```

---

### Task 11: Update README with Self-Debugging Documentation

**Files:**
- Modify: `README.md`

**Step 1: Read README.md**

Read to find the "What's included" section.

**Step 2: Add self-debugging section**

After the "Bundled skills" subsection, add:

```markdown
### Self-debugging agents

Autonomous failure detection, diagnosis, and retry for Phases 5-6. When a test, lint check, or review fix fails:

1. The retry loop classifies the error against the **failure catalog** (`memory/failure-catalog.md`)
2. Known patterns are fixed automatically using documented strategies
3. Novel failures dispatch a **diagnosis subagent** that identifies root cause and proposes a fix
4. New patterns are validated via multi-model review (DeepSeek + Codex) before being added to the catalog
5. The catalog is pushed to GitHub so all users benefit from accumulated patterns
6. All events are logged to `memory/failure-events.jsonl` for trend analysis

Fully autonomous — user only sees failures that survive 3 retry attempts.

**Scripts:**
- `scripts/emit-failure-event.sh` — Append structured events to the JSONL log
- `hooks/tier1/failure-catalog-push.sh` — Auto-commit and push catalog updates
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add self-debugging agents section to README"
```

---

### Task 12: End-to-End Smoke Test

**Files:**
- Read: all files created/modified in Tasks 1-11

**Step 1: Verify all files exist**

```bash
ls -la memory/failure-catalog.md
ls -la memory/failure-events.jsonl
ls -la scripts/emit-failure-event.sh
ls -la hooks/tier1/failure-catalog-push.sh
ls -la skills/code-creation-workflow/references/diagnosis-subagent.md
```

**Step 2: Test event emission**

```bash
./scripts/emit-failure-event.sh '{"session":"smoke-test","phase":5,"type":"failure:test","step":"1/1","files":["test.py"],"error_class":"syntax_error","error_summary":"SyntaxError: unexpected EOF","attempt":1,"resolution":null}'
cat memory/failure-events.jsonl
```

Expected: One JSON line with a `ts` field added.

**Step 3: Test push hook (dry run)**

```bash
# Verify the hook detects no changes when catalog hasn't changed
./hooks/tier1/failure-catalog-push.sh
```

Expected: "No catalog changes to push."

**Step 4: Verify SKILL.md has retry loop sections**

```bash
grep -n "RETRY LOOP" skills/code-creation-workflow/SKILL.md
grep -n "Phase 5 Retry Loop" skills/code-creation-workflow/SKILL.md
grep -n "Phase 6 Retry Loop" skills/code-creation-workflow/SKILL.md
```

Expected: Matches at the insertion points from Tasks 7 and 8.

**Step 5: Verify memory-injection has catalog mapping**

```bash
grep -n "Failure Catalog Mapping" skills/code-creation-workflow/references/memory-injection.md
```

Expected: Match at the new section.

**Step 6: Clean up smoke test event**

```bash
> memory/failure-events.jsonl
git add memory/failure-events.jsonl
git commit -m "test: verify self-debugging smoke test passes, clean up"
```

---

## Task Summary

| Task | Component | Files | Estimated Complexity |
|------|-----------|-------|---------------------|
| 1 | Failure catalog seed | 1 create | Simple |
| 2 | Event log + emission script | 2 create | Simple |
| 3 | Catalog push hook | 1 create, 1 modify | Simple |
| 4 | Memory injection mapping | 1 modify | Simple |
| 5 | Diagnosis subagent prompt | 1 create | Medium |
| 6 | Multi-model prompt validation | 0 (uses existing script) | Medium |
| 7 | Phase 5 retry loop | 1 modify (SKILL.md) | Medium |
| 8 | Phase 6 retry loop | 1 modify (SKILL.md) | Medium |
| 9 | Session-learnings integration | 1 modify | Simple |
| 10 | Install script update | 1 modify | Simple |
| 11 | README documentation | 1 modify | Simple |
| 12 | End-to-end smoke test | 0 (verification only) | Simple |

**Total: 12 tasks, 6 new files, 5 modified files**

**Independent tasks (can be parallelized):** Tasks 1-5 have no dependencies on each other. Task 6 depends on Task 5. Tasks 7-8 depend on Task 5. Task 9 depends on Task 2. Tasks 10-11 depend on all prior tasks. Task 12 depends on everything.
