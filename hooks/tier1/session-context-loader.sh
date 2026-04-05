#!/usr/bin/env bash
# Trigger: SessionStart
# Loads session context at startup:
#   1. Outputs handoff.md if it exists (resuming a previous session)
#   2. Reminds to load CLAUDE.md if present
#   3. Reports recent git activity and suggests relevant skills
# Output is capped at ~50 lines to stay concise.
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LINE_BUDGET=50
LINES_USED=0

print_line() {
  if [[ "$LINES_USED" -lt "$LINE_BUDGET" ]]; then
    echo "$1"
    (( LINES_USED++ )) || true
  fi
}

# 1. Handoff file
HANDOFF="$PROJECT_DIR/.claude/handoff.md"
if [[ -f "$HANDOFF" ]]; then
  print_line "=== RESUMING SESSION ==="
  while IFS= read -r line && [[ "$LINES_USED" -lt $((LINE_BUDGET - 5)) ]]; do
    print_line "$line"
  done < "$HANDOFF"
  print_line "=== END HANDOFF ==="
  print_line ""
fi

# 2. CLAUDE.md reminder
if [[ -f "$PROJECT_DIR/CLAUDE.md" ]]; then
  print_line "[session-context-loader] CLAUDE.md found at project root — load it for project conventions."
  print_line ""
fi

# 3. Recent git activity
if git -C "$PROJECT_DIR" rev-parse --git-dir &>/dev/null; then
  BRANCH=$(git -C "$PROJECT_DIR" branch --show-current 2>/dev/null || echo "unknown")
  print_line "[session-context-loader] Branch: $BRANCH"

  # Last 5 commits
  RECENT=$(git -C "$PROJECT_DIR" log --oneline -5 2>/dev/null || true)
  if [[ -n "$RECENT" ]]; then
    print_line "Recent commits:"
    while IFS= read -r line; do
      print_line "  $line"
    done <<< "$RECENT"
  fi

  # Modified files hint
  MODIFIED=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null | head -10 || true)
  if [[ -n "$MODIFIED" ]]; then
    print_line ""
    print_line "Modified files (uncommitted):"
    while IFS= read -r f; do
      print_line "  $f"
    done <<< "$MODIFIED"
  fi

  # Skill suggestions based on recently touched file types
  print_line ""
  HAS_PY=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null | grep -c '\.py$' || true)
  HAS_TS=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null | grep -c '\.[jt]sx\?$' || true)
  HAS_SQL=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null | grep -c '\(\.sql$\|migrations/\)' || true)

  if [[ "$HAS_PY" -gt 0 ]]; then
    print_line "  Tip: Python files modified — consider /lint or test-driven-development skill."
  fi
  if [[ "$HAS_TS" -gt 0 ]]; then
    print_line "  Tip: JS/TS files modified — consider type-check-on-save or frontend-design skill."
  fi
  if [[ "$HAS_SQL" -gt 0 ]]; then
    print_line "  Tip: SQL/migration files modified — consider new-migration skill."
  fi
fi

exit 0
