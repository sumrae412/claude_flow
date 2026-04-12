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
