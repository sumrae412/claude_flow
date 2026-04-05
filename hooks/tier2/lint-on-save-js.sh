#!/usr/bin/env bash
# Trigger: PostToolUse:Edit (*.js, *.ts, *.jsx, *.tsx)
# Stack tag: node+eslint
# Runs eslint --fix on the file just edited via npx.
# Outputs up to 10 lines of results. Does not block.
set -e

FILE="${CLAUDE_FILE_PATH:-}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"

if [[ -z "$FILE" ]] || [[ ! -f "$FILE" ]]; then
  exit 0
fi

if [[ -z "$PROJECT_DIR" ]] || [[ ! -d "$PROJECT_DIR" ]]; then
  exit 0
fi

cd "$PROJECT_DIR"

if ! command -v npx >/dev/null 2>&1; then
  echo "[lint-on-save-js] npx not found. Skipping ESLint."
  exit 0
fi

echo "[lint-on-save-js] Running eslint --fix on $FILE"
npx eslint --fix "$FILE" 2>&1 | tail -10 || true

exit 0
