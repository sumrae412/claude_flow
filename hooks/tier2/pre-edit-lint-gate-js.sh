#!/usr/bin/env bash
# Trigger: PreToolUse:Edit|Write (*.js|*.jsx|*.ts|*.tsx)
# Stack tag: js+eslint, ts+eslint
# Blocks the edit/write if the resulting JS/TS content fails `eslint`.
# Graceful skip envelope when eslint is missing (per optional-dep-gate policy).
set -uo pipefail

INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | jq -r '.tool_name // empty')"
case "$TOOL_NAME" in
  Edit|Write) ;;
  *) exit 0 ;;
esac

FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')"
shopt -s nocasematch
case "$FILE_PATH" in
  *.js|*.jsx|*.ts|*.tsx) ;;
  *) shopt -u nocasematch; exit 0 ;;
esac
shopt -u nocasematch

# eslint discovery: prefer PATH, fall back to npx --no-install for node_modules/.bin.
ESLINT_CMD=""
if command -v eslint >/dev/null 2>&1; then
  ESLINT_CMD="eslint"
elif command -v npx >/dev/null 2>&1 && npx --no-install eslint --version >/dev/null 2>&1; then
  ESLINT_CMD="npx --no-install eslint"
else
  echo '{"reviewer":"pre-edit-lint-gate-js","skipped":true,"reason":"eslint not installed"}'
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
old = os.environ["OLD"]
if old and old not in src:
    sys.exit(0)  # Edit will fail at tool-call time; avoid blocking on unrelated errors
sys.stdout.write(src.replace(old, os.environ["NEW"], 1))
PY
)"
fi

[[ -z "$CONTENT" ]] && exit 0

# Pick extension matching real file so eslint applies language-specific rules.
EXT="js"
shopt -s nocasematch
case "$FILE_PATH" in
  *.jsx) EXT="jsx" ;;
  *.ts)  EXT="ts"  ;;
  *.tsx) EXT="tsx" ;;
  *)     EXT="js"  ;;
esac
shopt -u nocasematch

# ESLint v9+ searches for eslint.config.js upward from the linted file, not cwd.
# So the tempfile must live inside CLAUDE_PROJECT_DIR for project config to apply.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
TMPD=""
trap '[[ -n "$TMPD" ]] && rm -rf "$TMPD"' EXIT
TMPD="$(mktemp -d "$PROJECT_DIR/.preeditlintjs.XXXXXX" 2>/dev/null || mktemp -d -t preeditlintjs.XXXXXX)"
TMP="$TMPD/x.$EXT"
printf '%s' "$CONTENT" > "$TMP"

cd "$PROJECT_DIR" 2>/dev/null || true
OUTPUT="$($ESLINT_CMD "$TMP" 2>&1)"
RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[pre-edit-lint-gate-js] BLOCKED: eslint errors in $FILE_PATH"
  echo "$OUTPUT" | head -20
  echo "Fix the lint errors before writing the file."
  exit 2
fi
exit 0
