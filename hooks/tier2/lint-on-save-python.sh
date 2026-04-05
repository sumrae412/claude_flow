#!/usr/bin/env bash
# Trigger: PostToolUse:Edit (*.py)
# Stack tag: python+ruff or python+flake8
# Detects the project linter (ruff preferred, falls back to flake8) and runs it
# against the file just edited. Outputs up to 10 lines of results. Does not block.
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

# Prefer ruff if [tool.ruff] section is present in pyproject.toml
if [[ -f "pyproject.toml" ]] && grep -q '^\[tool\.ruff\]' pyproject.toml 2>/dev/null; then
  if command -v ruff >/dev/null 2>&1; then
    echo "[lint-on-save-python] Running ruff on $FILE"
    ruff check --fix "$FILE" 2>&1 | tail -10 || true
    exit 0
  fi
fi

# Fall back to flake8 if available
if command -v flake8 >/dev/null 2>&1; then
  echo "[lint-on-save-python] Running flake8 on $FILE"
  flake8 "$FILE" 2>&1 | tail -10 || true
  exit 0
fi

echo "[lint-on-save-python] No supported linter found (ruff or flake8). Skipping."
exit 0
