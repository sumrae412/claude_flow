#!/usr/bin/env bash
# Trigger: PreToolUse:Bash (matcher: git commit*)
# Detects the project's lint tool and runs it before allowing a commit.
# Blocks (exit 1) if the linter reports errors.
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

LINTER=""
LINT_CMD=""

# Detect ruff via pyproject.toml
if [[ -f "$PROJECT_DIR/pyproject.toml" ]] && grep -q '\[tool\.ruff\]' "$PROJECT_DIR/pyproject.toml" 2>/dev/null; then
  LINTER="ruff"
  LINT_CMD="ruff check ."
fi

# Detect ESLint via package.json (only if ruff not already selected)
if [[ -z "$LINTER" ]] && [[ -f "$PROJECT_DIR/package.json" ]]; then
  LINTER="eslint"
  LINT_CMD="npx eslint . --quiet"
fi

# Nothing to run
if [[ -z "$LINTER" ]]; then
  exit 0
fi

echo "[build-before-commit] Running $LINTER before commit..."

cd "$PROJECT_DIR"
if ! $LINT_CMD 2>&1; then
  echo ""
  echo "[build-before-commit] BLOCKED: $LINTER reported errors. Fix them before committing."
  exit 1
fi

echo "[build-before-commit] $LINTER passed."
exit 0
