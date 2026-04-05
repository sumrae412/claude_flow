#!/usr/bin/env bash
# Trigger: PostToolUse:Write
# After a source file is written, checks whether a companion test file exists.
# Outputs a suggestion (does not block) if no test file is found.
set -e

FILE="${CLAUDE_FILE_PATH:-}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

if [[ -z "$FILE" ]]; then
  exit 0
fi

BASENAME=$(basename "$FILE")
DIRNAME=$(dirname "$FILE")

suggest_test() {
  local suggestion="$1"
  echo "[missing-test-companion] No test file found for $FILE"
  echo "  Suggested: $suggestion"
}

# Python source files
if [[ "$BASENAME" =~ ^(.+)\.py$ ]]; then
  MODULE="${BASH_REMATCH[1]}"

  # Skip if this is already a test file
  if [[ "$BASENAME" =~ ^test_ ]] || [[ "$DIRNAME" =~ /tests(/|$) ]]; then
    exit 0
  fi

  # Check tests/test_<module>.py (project-root relative)
  CANDIDATE="$PROJECT_DIR/tests/test_${MODULE}.py"
  if [[ -f "$CANDIDATE" ]]; then
    exit 0
  fi

  suggest_test "tests/test_${MODULE}.py"
  exit 0
fi

# TypeScript/JavaScript source files
if [[ "$BASENAME" =~ ^(.+)\.(tsx|ts|jsx|js)$ ]]; then
  MODULE="${BASH_REMATCH[1]}"
  EXT="${BASH_REMATCH[2]}"

  # Skip if already a test/spec file
  if [[ "$BASENAME" =~ \.(test|spec)\. ]] || [[ "$DIRNAME" =~ /__tests__(/|$) ]]; then
    exit 0
  fi

  # Check same-dir __tests__/<Module>.test.<ext>
  CANDIDATE_1="$DIRNAME/__tests__/${MODULE}.test.${EXT}"
  # Check same-dir <Module>.test.<ext>
  CANDIDATE_2="$DIRNAME/${MODULE}.test.${EXT}"

  if [[ -f "$CANDIDATE_1" ]] || [[ -f "$CANDIDATE_2" ]]; then
    exit 0
  fi

  # Suggest both options
  REL_DIR="${DIRNAME#$PROJECT_DIR/}"
  suggest_test "${REL_DIR}/__tests__/${MODULE}.test.${EXT} or ${REL_DIR}/${MODULE}.test.${EXT}"
  exit 0
fi

exit 0
