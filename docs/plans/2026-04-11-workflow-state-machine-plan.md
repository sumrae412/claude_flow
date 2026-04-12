# Workflow State Machine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add phase transition governance, cross-session resume, and schema validation to code-creation-workflow.

**Architecture:** JSON state file (`.claude/workflow-state.json`) + hook enforcement (`phase-gate.sh`) + output schemas (`.claude/schemas/`) + skill modifications for state read/write at phase boundaries.

**Tech Stack:** Shell scripts (bash), JSON, jq

---

### Task 1: Create Output Schemas

**Files:**
- Create: `.claude/schemas/exploration-output.json`
- Create: `.claude/schemas/architecture-output.json`
- Create: `.claude/schemas/plan-output.json`
- Create: `.claude/schemas/review-output.json`

**Step 1: Create schemas directory**

```bash
mkdir -p .claude/schemas
```

**Step 2: Write exploration-output.json**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "description": "Phase 2 exploration output — key files, patterns, integration points discovered",
  "type": "object",
  "required": ["key_files", "patterns", "integration_points"],
  "properties": {
    "key_files": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string" },
      "description": "File paths read during exploration with their roles"
    },
    "patterns": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Coding patterns, conventions, and architecture decisions observed"
    },
    "integration_points": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Systems, services, or modules this feature touches"
    },
    "gaps": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Areas needing further investigation"
    },
    "gotchas_from_memory": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Relevant gotchas loaded from MEMORY.md"
    }
  }
}
```

**Step 3: Write architecture-output.json**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "description": "Phase 4 architecture output — approach, files, trade-offs",
  "type": "object",
  "required": ["approach", "files_to_create", "files_to_modify", "trade_offs"],
  "properties": {
    "approach": {
      "type": "string",
      "minLength": 1,
      "description": "Selected architecture approach and rationale"
    },
    "files_to_create": {
      "type": "array",
      "items": { "type": "string" },
      "description": "New file paths to be created"
    },
    "files_to_modify": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Existing file paths to be modified"
    },
    "trade_offs": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string" },
      "description": "Trade-offs considered and rationale for choices"
    }
  }
}
```

**Step 4: Write plan-output.json**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "description": "Phase 4b plan output — implementation steps with dependencies",
  "type": "object",
  "required": ["steps"],
  "properties": {
    "steps": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["description", "files"],
        "properties": {
          "description": { "type": "string" },
          "files": {
            "type": "array",
            "items": { "type": "string" }
          },
          "dependencies": {
            "type": "array",
            "items": { "type": "integer" },
            "description": "Step indices this step depends on (0-indexed)"
          }
        }
      }
    }
  }
}
```

**Step 5: Write review-output.json**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "description": "Phase 6 review output — findings with severity and location",
  "type": "object",
  "required": ["findings"],
  "properties": {
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "finding", "file"],
        "properties": {
          "severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low", "info"]
          },
          "finding": { "type": "string" },
          "file": { "type": "string" },
          "line": { "type": "integer" }
        }
      }
    }
  }
}
```

**Step 6: Commit**

```bash
git add .claude/schemas/
git commit -m "feat: add output schemas for workflow phase validation"
```

---

### Task 2: Create Phase Gate Hook

**Files:**
- Create: `hooks/tier1/phase-gate.sh`

**Step 1: Write the phase-gate.sh script**

The hook reads `.claude/workflow-state.json`, extracts the current phase, and blocks source file edits during non-implementation phases. Exits 0 (allow) or 1 (block).

```bash
#!/usr/bin/env bash
# Trigger: PreToolUse:Edit,Write,Bash
# Reads .claude/workflow-state.json and blocks source file edits
# outside Phase 5 (Implementation). Fail-open if no state file.
set -e

STATE_FILE=".claude/workflow-state.json"

# Fail-open: no state file = no workflow active, allow everything
if [[ ! -f "$STATE_FILE" ]]; then
  exit 0
fi

# Check jq is available; fail-open if not
if ! command -v jq &>/dev/null; then
  exit 0
fi

# Extract current phase and status
PHASE_ID=$(jq -r '.current_phase.id // ""' "$STATE_FILE" 2>/dev/null)
PHASE_NAME=$(jq -r '.current_phase.name // ""' "$STATE_FILE" 2>/dev/null)
PHASE_STATUS=$(jq -r '.current_phase.status // ""' "$STATE_FILE" 2>/dev/null)
STEP=$(jq -r '.current_phase.step // ""' "$STATE_FILE" 2>/dev/null)
STEP_LABEL=$(jq -r '.current_phase.step_label // ""' "$STATE_FILE" 2>/dev/null)

# If phase couldn't be read, fail-open
if [[ -z "$PHASE_ID" ]]; then
  exit 0
fi

# Get the file being edited/written
FILE="${CLAUDE_FILE_PATH:-}"

# No file path = not a file operation (e.g., Bash command), allow
if [[ -z "$FILE" ]]; then
  exit 0
fi

# Define source file patterns (edits blocked outside Phase 5)
is_source_file() {
  local f="$1"
  case "$f" in
    app/*|src/*|lib/*|tests/*|test/*) return 0 ;;
    *.py|*.js|*.ts|*.tsx|*.jsx) return 0 ;;
    *) return 1 ;;
  esac
}

# Always allow non-source files (docs, plans, .claude/*, configs)
if ! is_source_file "$FILE"; then
  exit 0
fi

# Phase 5 (Implementation): allow everything
if [[ "$PHASE_ID" == "phase-5" ]]; then
  exit 0
fi

# Phase 6 with status=fixing: allow (review fix loop)
if [[ "$PHASE_ID" == "phase-6" && "$PHASE_STATUS" == "fixing" ]]; then
  exit 0
fi

# All other phases: block source file edits
STEP_INFO=""
if [[ -n "$STEP" && -n "$STEP_LABEL" ]]; then
  STEP_INFO=", Step $STEP ($STEP_LABEL)"
fi

echo "⚠ Phase gate: You're in $PHASE_ID ($PHASE_NAME). Source file edits are blocked until Phase 5 (Implementation)."
echo ""
echo "Current state: $PHASE_ID${STEP_INFO}"
echo "To advance: Complete the current phase, then transition forward."
exit 1
```

**Step 2: Make executable**

```bash
chmod +x hooks/tier1/phase-gate.sh
```

**Step 3: Verify the script handles missing state file**

```bash
# Should exit 0 (allow) when no state file exists
bash hooks/tier1/phase-gate.sh; echo "exit: $?"
```

Expected: `exit: 0`

**Step 4: Commit**

```bash
git add hooks/tier1/phase-gate.sh
git commit -m "feat: add phase-gate hook for workflow enforcement"
```

---

### Task 3: Create Schema Validation Hook

**Files:**
- Create: `hooks/tier1/validate-phase-output.sh`

**Step 1: Write the validate-phase-output.sh script**

Validates phase artifacts against JSON schemas when workflow-state.json is updated. Fail-open on missing jq or schemas.

```bash
#!/usr/bin/env bash
# Trigger: PostToolUse:Write (on .claude/workflow-state.json)
# Validates phase output artifacts against schemas in .claude/schemas/
# Fail-open: missing schema or jq = warn, don't block
set -e

FILE="${CLAUDE_FILE_PATH:-}"

# Only run for workflow-state.json writes
if [[ "$FILE" != *"workflow-state.json" ]]; then
  exit 0
fi

STATE_FILE=".claude/workflow-state.json"
SCHEMA_DIR=".claude/schemas"

if [[ ! -f "$STATE_FILE" ]]; then
  exit 0
fi

# Check jq is available
if ! command -v jq &>/dev/null; then
  echo "[validate-phase-output] WARN: jq not found, schema validation skipped"
  exit 0
fi

# Map phase to schema and artifact path
PHASE_ID=$(jq -r '.current_phase.id // ""' "$STATE_FILE" 2>/dev/null)

case "$PHASE_ID" in
  phase-2)
    SCHEMA_FILE="$SCHEMA_DIR/exploration-output.json"
    ARTIFACT_PATH=".artifacts.exploration_summary"
    ;;
  phase-4)
    SCHEMA_FILE="$SCHEMA_DIR/architecture-output.json"
    ARTIFACT_PATH=".artifacts.architecture_doc"
    ;;
  phase-4b)
    SCHEMA_FILE="$SCHEMA_DIR/plan-output.json"
    ARTIFACT_PATH=".artifacts.implementation_plan"
    ;;
  phase-6)
    SCHEMA_FILE="$SCHEMA_DIR/review-output.json"
    ARTIFACT_PATH=".artifacts.review_findings"
    ;;
  *)
    # No schema for this phase
    exit 0
    ;;
esac

# Fail-open: no schema file
if [[ ! -f "$SCHEMA_FILE" ]]; then
  echo "[validate-phase-output] WARN: Schema $SCHEMA_FILE not found, validation skipped"
  exit 0
fi

# Extract artifact
ARTIFACT=$(jq -r "$ARTIFACT_PATH // \"null\"" "$STATE_FILE" 2>/dev/null)

# Artifact is null = not yet produced, that's fine
if [[ "$ARTIFACT" == "null" ]]; then
  exit 0
fi

# Validate required fields using jq (lightweight, no jsonschema dependency)
REQUIRED_FIELDS=$(jq -r '.required[]?' "$SCHEMA_FILE" 2>/dev/null)
ERRORS=()

for FIELD in $REQUIRED_FIELDS; do
  FIELD_VALUE=$(echo "$ARTIFACT" | jq -r ".$FIELD // \"__MISSING__\"" 2>/dev/null)
  if [[ "$FIELD_VALUE" == "__MISSING__" || "$FIELD_VALUE" == "null" ]]; then
    ERRORS+=("Missing required field: $FIELD")
  fi

  # Check minItems for arrays
  MIN_ITEMS=$(jq -r ".properties.$FIELD.minItems // \"\"" "$SCHEMA_FILE" 2>/dev/null)
  if [[ -n "$MIN_ITEMS" && "$FIELD_VALUE" != "__MISSING__" && "$FIELD_VALUE" != "null" ]]; then
    ACTUAL_LEN=$(echo "$ARTIFACT" | jq -r ".$FIELD | length" 2>/dev/null)
    if [[ "$ACTUAL_LEN" -lt "$MIN_ITEMS" ]]; then
      ERRORS+=("$FIELD has $ACTUAL_LEN items, minimum is $MIN_ITEMS")
    fi
  fi
done

if [[ ${#ERRORS[@]} -gt 0 ]]; then
  echo "⚠ Phase output validation failed for $PHASE_ID:"
  for ERR in "${ERRORS[@]}"; do
    echo "  - $ERR"
  done
  echo ""
  echo "Complete the artifact before advancing to the next phase."
  # Warn but don't block (PostToolUse can't block the write retroactively)
  exit 0
fi

exit 0
```

**Step 2: Make executable**

```bash
chmod +x hooks/tier1/validate-phase-output.sh
```

**Step 3: Commit**

```bash
git add hooks/tier1/validate-phase-output.sh
git commit -m "feat: add schema validation hook for phase outputs"
```

---

### Task 4: Register New Hooks in hook-registry.json

**Files:**
- Modify: `hooks/hook-registry.json`

**Step 1: Add phase-gate and validate-phase-output entries**

Add these two entries to the `hooks` array in `hooks/hook-registry.json`, after the existing `context-rot-detection` entry:

```json
{
  "id": "phase-gate",
  "tier": 1,
  "trigger": "PreToolUse",
  "matcher": ["Edit", "Write"],
  "script": "hooks/tier1/phase-gate.sh",
  "description": "Blocks source file edits outside Phase 5 (Implementation)"
},
{
  "id": "validate-phase-output",
  "tier": 1,
  "trigger": "PostToolUse",
  "matcher": ["Write(.claude/workflow-state.json)"],
  "script": "hooks/tier1/validate-phase-output.sh",
  "description": "Validates phase output artifacts against JSON schemas"
}
```

**Step 2: Verify JSON is valid**

```bash
jq '.' hooks/hook-registry.json > /dev/null && echo "valid" || echo "invalid"
```

Expected: `valid`

**Step 3: Commit**

```bash
git add hooks/hook-registry.json
git commit -m "feat: register phase-gate and validate-phase-output hooks"
```

---

### Task 5: Add State File Management to code-creation-workflow SKILL.md

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md`

This is the largest task — adding state file read/write instructions at phase boundaries. The skill already describes phases; we add state management at each transition point.

**Step 1: Add State Management section after the Model Strategy section (before Phase 0)**

Insert after the `## Model Strategy: Executor/Advisor` section (around line 103), before `## Phase 0: Context Loading`:

```markdown
---

## Workflow State Machine

The workflow tracks its state in `.claude/workflow-state.json` for phase governance and cross-session resume.

### State File Operations

**Initialize** (Phase 0, after context loading):
```bash
# Write initial state — replace TASK_SUMMARY with actual task
cat > .claude/workflow-state.json << 'STATEEOF'
{
  "schema_version": 1,
  "workflow_id": "code-creation-workflow",
  "session_id": "SESSION_TIMESTAMP",
  "status": "running",
  "started_at": "SESSION_TIMESTAMP",
  "current_phase": {
    "id": "phase-0",
    "name": "Context Loading",
    "path": null,
    "status": "running",
    "started_at": "SESSION_TIMESTAMP",
    "step": 1,
    "step_label": "Load project identity",
    "agents_spawned": 0,
    "agents_completed": 0,
    "agents_failed": 0,
    "iteration": 1,
    "max_iterations": 1
  },
  "phase_history": [],
  "iterations": { "phase-0": 1 },
  "task_summary": "TASK_SUMMARY",
  "artifacts": {
    "exploration_summary": null,
    "architecture_doc": null,
    "implementation_plan": null,
    "review_findings": null
  }
}
STATEEOF
```

**Transition** (at each phase boundary):
```bash
# Use jq to transition phases — example: Phase 2 → Phase 3
jq '
  .phase_history += [{
    id: .current_phase.id,
    name: .current_phase.name,
    status: "completed",
    started_at: .current_phase.started_at,
    completed_at: now | todate,
    iteration: .current_phase.iteration,
    results: {}
  }] |
  .current_phase = {
    id: "phase-3",
    name: "Clarification",
    path: .current_phase.path,
    status: "running",
    started_at: (now | todate),
    step: 1,
    step_label: "Resolve ambiguities",
    agents_spawned: 0,
    agents_completed: 0,
    agents_failed: 0,
    iteration: 1,
    max_iterations: 1
  } |
  .iterations["phase-3"] = 1
' .claude/workflow-state.json > .claude/workflow-state.tmp && mv .claude/workflow-state.tmp .claude/workflow-state.json
```

**Update step** (within a phase):
```bash
jq '.current_phase.step = 3 | .current_phase.step_label = "Pattern mapping"' \
  .claude/workflow-state.json > .claude/workflow-state.tmp && \
  mv .claude/workflow-state.tmp .claude/workflow-state.json
```

**Complete** (workflow done):
```bash
jq '.status = "completed"' .claude/workflow-state.json > .claude/workflow-state.tmp && \
  mv .claude/workflow-state.tmp .claude/workflow-state.json
```

### Cross-Session Resume

At the very start of Phase 0 (before Step 1), check for existing state:

```
IF .claude/workflow-state.json exists:
  1. Read state file
  2. Check started_at — if >48 hours ago, ask user:
     "Found workflow state from N days ago. Resume or start fresh?"
  3. If resume: output resume message with phase/step/artifacts status,
     skip to the in-progress phase
  4. If start fresh: archive to .claude/workflow-state.archived.json,
     proceed normally
ELSE:
  Proceed with normal Phase 0
```

### Transition Map

Only these transitions are valid. The phase-gate hook enforces this by blocking source file edits outside Phase 5.

| From | To | Condition |
|------|----|-----------|
| phase-0 → phase-0.5 | No hooks.json exists |
| phase-0 → phase-1 | hooks.json exists (skip bootstrap) |
| phase-0.5 → phase-1 | Always |
| phase-1 → EXIT | Fast path selected |
| phase-1 → phase-2 | Full or lite path |
| phase-1 → phase-5 | Clone or plan path |
| phase-2 → phase-3 | Always |
| phase-3 → phase-4 | Always |
| phase-4 → phase-4b | Always |
| phase-4b → phase-4d | Full path only |
| phase-4b → phase-5 | Lite path (skip skeletons) |
| phase-4d → phase-5 | Always |
| phase-5 → phase-5 | Retry: tests/lint failed, iteration < 3 |
| phase-5 → phase-6 | Tests + lint pass |
| phase-6 → phase-5 | High/critical review findings, iteration < 2 |
| phase-6 → COMPLETE | No high/critical findings |

### Iteration Limits

| Phase | Max | On Exceeded |
|-------|-----|-------------|
| phase-5 | 3 | Surface to user |
| phase-6 | 2 | Ship with known issues |
| All others | 1 | Forward only |
```

**Step 2: Add resume check to Phase 0, Step 1**

In Phase 0 (around line 107), before "### Step 1: Load Project Identity", add:

```markdown
### Step 0: Check for Existing Workflow State

Before loading any context, check if a prior session's workflow is in progress:

1. Read `.claude/workflow-state.json`
2. If found and `status == "running"`:
   - Check `started_at` age. If >48 hours, ask user to resume or start fresh.
   - Output resume message:
     ```
     Resuming workflow: "<task_summary>"
     <current_phase.name> was in progress — Step <step> (<step_label>)
     Path: <path>
     Completed phases: [list from phase_history]
     Artifacts: [which are null vs populated]
     ```
   - Skip to the in-progress phase.
3. If found and `status == "completed"`: archive and start fresh.
4. If not found: proceed normally (initialize state after Step 6).
```

**Step 3: Add state transitions at each phase boundary**

At every `---` phase boundary in the SKILL.md (between Phase N end and Phase N+1 start), add a line:

```markdown
**State transition:** Update `.claude/workflow-state.json` — move current phase to `phase_history`, set `current_phase` to the next phase.
```

This is a one-line instruction at each of these locations:
- End of Phase 0 (before Phase 0.5 or Phase 1)
- End of Phase 0.5 (before Phase 1)
- End of Phase 1 (before Phase 2 or branching)
- End of Phase 2 (before Phase 3)
- End of Phase 3 (before Phase 4)
- End of Phase 4 (before Phase 4b)
- End of Phase 4b (before Phase 4d or Phase 5)
- End of Phase 4d (before Phase 5)
- End of Phase 5 (before Phase 6 or retry)
- End of Phase 6 (before COMPLETE or fix loop)

**Step 4: Add artifact writes at phase completion**

At the end of Phase 2, add:
```markdown
**Artifact:** Write exploration summary to `.claude/workflow-state.json` field `artifacts.exploration_summary` with `key_files`, `patterns`, `integration_points`, `gaps`, `gotchas_from_memory`.
```

At the end of Phase 4, add:
```markdown
**Artifact:** Write architecture to `.claude/workflow-state.json` field `artifacts.architecture_doc` with `approach`, `files_to_create`, `files_to_modify`, `trade_offs`.
```

At the end of Phase 4b, add:
```markdown
**Artifact:** Write plan to `.claude/workflow-state.json` field `artifacts.implementation_plan` with `steps` array (each with `description`, `files`, `dependencies`).
```

At the end of Phase 6, add:
```markdown
**Artifact:** Write review findings to `.claude/workflow-state.json` field `artifacts.review_findings` with `findings` array (each with `severity`, `finding`, `file`).
```

**Step 5: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: add workflow state machine to code-creation-workflow"
```

---

### Task 6: Update session-handoff Skill to Read State File

**Files:**
- Modify: `skills/session-handoff/SKILL.md`

**Step 1: Add state file as canonical source**

In `### Step 1: Gather State`, add at the top (before the git commands):

```markdown
**Primary source — workflow state file:**

If `.claude/workflow-state.json` exists, read it first. It provides structured data for:
- Current phase and step (replaces guessing from conversation context)
- Phase history with timestamps (replaces manual reconstruction)
- Task summary (replaces re-reading the original request)
- Produced artifacts (replaces checking which docs exist)

Fall back to git/conversation context only for fields not in the state file (e.g., open questions, ruled-out approaches).
```

**Step 2: Update the handoff.md template**

Replace the `**Phase:**` line in the template with:

```markdown
**Phase:** <from workflow-state.json: current_phase.id (current_phase.name), Step current_phase.step of total>
**Path:** <from workflow-state.json: current_phase.path>
**Iteration:** <from workflow-state.json: current_phase.iteration / max_iterations>
**Task:** <from workflow-state.json: task_summary>
```

**Step 3: Commit**

```bash
git add skills/session-handoff/SKILL.md
git commit -m "feat: session-handoff reads workflow-state.json as canonical source"
```

---

### Task 7: Add workflow-state.json to .gitignore

**Files:**
- Modify or create: `.gitignore` (at project root)

**Step 1: Add gitignore entry**

Add to `.gitignore`:

```
# Workflow state (ephemeral, session-scoped)
.claude/workflow-state.json
.claude/workflow-state.tmp
.claude/workflow-state.archived.json
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore workflow state files"
```

---

### Task 8: Integration Test — End-to-End Validation

**Files:** None (manual verification)

**Step 1: Verify phase-gate blocks correctly**

Create a test state file with Phase 2 active:

```bash
mkdir -p .claude
cat > .claude/workflow-state.json << 'EOF'
{
  "schema_version": 1,
  "workflow_id": "code-creation-workflow",
  "session_id": "test",
  "status": "running",
  "started_at": "2026-04-11T10:00:00Z",
  "current_phase": {
    "id": "phase-2",
    "name": "Exploration",
    "path": "full",
    "status": "running",
    "started_at": "2026-04-11T10:00:00Z",
    "step": 1,
    "step_label": "Prior knowledge check",
    "agents_spawned": 0,
    "agents_completed": 0,
    "agents_failed": 0,
    "iteration": 1,
    "max_iterations": 1
  },
  "phase_history": [],
  "iterations": { "phase-2": 1 },
  "task_summary": "Test workflow",
  "artifacts": {
    "exploration_summary": null,
    "architecture_doc": null,
    "implementation_plan": null,
    "review_findings": null
  }
}
EOF
```

Test the hook:

```bash
# Should BLOCK (source file during Phase 2)
CLAUDE_FILE_PATH="app/services/test.py" bash hooks/tier1/phase-gate.sh
echo "exit: $?"
# Expected: exit: 1 with warning message

# Should ALLOW (docs file during Phase 2)
CLAUDE_FILE_PATH="docs/plans/test.md" bash hooks/tier1/phase-gate.sh
echo "exit: $?"
# Expected: exit: 0
```

**Step 2: Verify Phase 5 allows everything**

```bash
jq '.current_phase.id = "phase-5" | .current_phase.name = "Implementation"' \
  .claude/workflow-state.json > .claude/workflow-state.tmp && \
  mv .claude/workflow-state.tmp .claude/workflow-state.json

CLAUDE_FILE_PATH="app/services/test.py" bash hooks/tier1/phase-gate.sh
echo "exit: $?"
# Expected: exit: 0
```

**Step 3: Verify fail-open with no state file**

```bash
rm .claude/workflow-state.json
CLAUDE_FILE_PATH="app/services/test.py" bash hooks/tier1/phase-gate.sh
echo "exit: $?"
# Expected: exit: 0
```

**Step 4: Clean up test state file**

```bash
rm -f .claude/workflow-state.json .claude/workflow-state.tmp
```

**Step 5: Final commit with all changes**

```bash
git add -A
git commit -m "feat: workflow state machine — phase governance, resume, schema validation

Adds 5 components:
- .claude/schemas/ — JSON schemas for phase output validation
- hooks/tier1/phase-gate.sh — blocks source edits outside Phase 5
- hooks/tier1/validate-phase-output.sh — validates artifacts against schemas
- code-creation-workflow state management at phase boundaries
- session-handoff reads workflow-state.json as canonical source

Adapted from claude-workflow's WorkflowStateManager patterns."
```
