#!/usr/bin/env bash
# Trigger: PostToolUse:Edit (app/**/*.py, src/**/*.py)
# Stack tag: python+pytest
# Derives a test filter keyword from the edited file's module name and runs
# pytest against the tests/ directory using that keyword. Does not block.
# Skips if the file being edited is itself a test file.
set -e

FILE="${CLAUDE_FILE_PATH:-}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"

if [[ -z "$FILE" ]] || [[ ! -f "$FILE" ]]; then
  exit 0
fi

if [[ -z "$PROJECT_DIR" ]] || [[ ! -d "$PROJECT_DIR" ]]; then
  exit 0
fi

# Skip if this is already a test file
BASENAME="$(basename "$FILE")"
if [[ "$BASENAME" == test_* ]] || [[ "$BASENAME" == *_test.py ]]; then
  exit 0
fi

# Derive module name (filename without .py extension)
TESTNAME="${BASENAME%.py}"

if [[ -z "$TESTNAME" ]]; then
  exit 0
fi

cd "$PROJECT_DIR"

if ! command -v pytest >/dev/null 2>&1; then
  echo "[test-on-save-python] pytest not found. Skipping."
  exit 0
fi

if [[ ! -d "tests" ]]; then
  exit 0
fi

echo "[test-on-save-python] Running pytest -k \"$TESTNAME\" (file: $FILE)"
pytest tests/ -k "$TESTNAME" --tb=short -q 2>/dev/null | tail -5 || true

exit 0
