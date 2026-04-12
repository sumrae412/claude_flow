#!/usr/bin/env bash
# Trigger: PreToolUse:Edit,Write
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
