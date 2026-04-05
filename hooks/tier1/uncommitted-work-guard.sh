#!/usr/bin/env bash
# Trigger: PreToolUse:Bash (matcher: git checkout *)
# Warns (does not block) when there are uncommitted changes before a branch switch.
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Run git status inside the project directory
GIT_STATUS=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null || true)

if [[ -n "$GIT_STATUS" ]]; then
  echo "[uncommitted-work-guard] WARNING: You have uncommitted changes:"
  echo "$GIT_STATUS" | head -20
  TOTAL=$(echo "$GIT_STATUS" | wc -l | tr -d ' ')
  if [[ "$TOTAL" -gt 20 ]]; then
    echo "  ... and $((TOTAL - 20)) more file(s)"
  fi
  echo ""
  echo "  Consider committing or stashing before switching branches to avoid conflicts."
fi

exit 0
