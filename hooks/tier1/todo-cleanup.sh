#!/usr/bin/env bash
# Trigger: PostToolUse:Bash (matcher: git commit*)
# After a commit, scans the committed diff for TODO, FIXME, HACK comments.
# Outputs a warning list (does not block).
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

TODOS=$(git -C "$PROJECT_DIR" diff HEAD~1 --diff-filter=ACM -U0 2>/dev/null \
  | grep -E '^\+.*(TODO|FIXME|HACK)' \
  | grep -v '^+++' \
  || true)

if [[ -n "$TODOS" ]]; then
  echo "[todo-cleanup] The following TODO/FIXME/HACK items were introduced in this commit:"
  echo "$TODOS" | sed 's/^\+/  /' | head -30
  COUNT=$(echo "$TODOS" | wc -l | tr -d ' ')
  if [[ "$COUNT" -gt 30 ]]; then
    echo "  ... and $((COUNT - 30)) more"
  fi
  echo ""
  echo "  Consider resolving these before merging or opening a PR."
fi

exit 0
