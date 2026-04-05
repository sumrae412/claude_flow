#!/usr/bin/env bash
# Trigger: PreToolUse:Edit
# Checks the line count of the file being edited.
# Outputs a warning (does not block) if the file exceeds 500 lines.
set -e

FILE="${CLAUDE_FILE_PATH:-}"

if [[ -z "$FILE" ]] || [[ ! -f "$FILE" ]]; then
  exit 0
fi

LINE_COUNT=$(wc -l < "$FILE" 2>/dev/null || echo 0)

if [[ "$LINE_COUNT" -gt 500 ]]; then
  echo "[large-file-warning] $FILE has $LINE_COUNT lines (>500)."
  echo "  Consider splitting into smaller modules before making further edits."
fi

exit 0
