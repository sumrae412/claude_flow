#!/usr/bin/env bash
# Trigger: PreToolUse:Edit|Write (*.py)
# Stack tag: python+ruff
# Blocks the edit/write if the resulting Python content fails `ruff check`.
# Graceful skip envelope when ruff is missing (per optional-dep-gate policy).
set -uo pipefail

INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | jq -r '.tool_name // empty')"
case "$TOOL_NAME" in
  Edit|Write) ;;
  *) exit 0 ;;
esac

FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')"
[[ "$FILE_PATH" != *.py ]] && exit 0

if ! command -v ruff >/dev/null 2>&1; then
  echo '{"reviewer":"pre-edit-lint-gate-python","skipped":true,"reason":"ruff not installed"}'
  exit 0
fi

# For Write: content is in tool_input.content.
# For Edit: reconstruct post-edit content by applying new_string to the real file.
CONTENT=""
if [[ "$TOOL_NAME" == "Write" ]]; then
  CONTENT="$(echo "$INPUT" | jq -r '.tool_input.content // empty')"
elif [[ "$TOOL_NAME" == "Edit" ]] && [[ -f "$FILE_PATH" ]]; then
  OLD="$(echo "$INPUT" | jq -r '.tool_input.old_string // empty')"
  NEW="$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')"
  # Use python to do the replacement safely (no shell escaping pitfalls).
  CONTENT="$(OLD="$OLD" NEW="$NEW" FILE="$FILE_PATH" python3 - <<'PY'
import os, sys
src = open(os.environ["FILE"]).read()
sys.stdout.write(src.replace(os.environ["OLD"], os.environ["NEW"], 1))
PY
)"
fi

[[ -z "$CONTENT" ]] && exit 0

TMP=""
trap '[[ -n "$TMP" ]] && rm -f "$TMP"' EXIT
TMP="$(mktemp -t preeditlint.XXXXXX).py"
printf '%s' "$CONTENT" > "$TMP"

OUTPUT="$(ruff check --no-fix "$TMP" 2>&1 || true)"
if echo "$OUTPUT" | grep -qE "^[A-Z][0-9]+|error:"; then
  echo "[pre-edit-lint-gate-python] BLOCKED: ruff errors in $FILE_PATH"
  echo "$OUTPUT" | head -20
  echo "Fix the lint errors before writing the file."
  exit 2
fi
exit 0
