#!/usr/bin/env bash
# Trigger: PostToolUse:Write (alembic/versions/*.py)
# Stack tag: python+alembic
# Runs `alembic heads` to detect branched migration heads after a new migration
# file is written. Warns if more than one head is found. Does not block.
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"

if [[ -z "$PROJECT_DIR" ]] || [[ ! -d "$PROJECT_DIR" ]]; then
  exit 0
fi

cd "$PROJECT_DIR"

if ! command -v alembic >/dev/null 2>&1; then
  echo "[migration-sequence-check] alembic not found. Skipping."
  exit 0
fi

echo "[migration-sequence-check] Checking alembic heads..."
HEADS_OUTPUT="$(alembic heads 2>&1)" || true
HEAD_COUNT="$(echo "$HEADS_OUTPUT" | grep -c '(head)' 2>/dev/null || echo 0)"

if [[ "$HEAD_COUNT" -gt 1 ]]; then
  echo "[migration-sequence-check] WARNING: Multiple migration heads detected ($HEAD_COUNT heads)."
  echo "  This indicates a branched migration history."
  echo "  Run \`alembic merge heads\` to create a merge migration before deploying."
  echo ""
  echo "$HEADS_OUTPUT"
else
  echo "[migration-sequence-check] Migration heads look good ($HEAD_COUNT head)."
fi

exit 0
