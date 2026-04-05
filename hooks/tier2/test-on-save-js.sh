#!/usr/bin/env bash
# Trigger: PostToolUse:Edit (src/**/*.js, src/**/*.ts, src/**/*.tsx)
# Stack tag: node+jest
# Runs jest --findRelatedTests for the file just edited via npx.
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
  echo "[test-on-save-js] npx not found. Skipping Jest."
  exit 0
fi

echo "[test-on-save-js] Running jest --findRelatedTests on $FILE"
npx jest --findRelatedTests "$FILE" --no-coverage 2>/dev/null | tail -10 || true

exit 0
