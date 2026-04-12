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

# 1b. Compaction checkpoint (most recent, if exists)
COMPACTION_LATEST=$(ls -t "$PROJECT_DIR/.claude"/pre-compaction-*.md 2>/dev/null | head -1)
if [[ -n "$COMPACTION_LATEST" ]]; then
  print_line "=== POST-COMPACTION CHECKPOINT ==="
  print_line "Source: $COMPACTION_LATEST"
  # Extract key sections (Workflow Phase, Resume Instructions)
  PHASE_LINE=$(grep -A2 '^## Workflow Phase' "$COMPACTION_LATEST" 2>/dev/null | grep -v '^## ' | grep -v '^--$' | head -2)
  if [[ -n "$PHASE_LINE" ]]; then
    while IFS= read -r line; do
      print_line "  $line"
    done <<< "$PHASE_LINE"
  fi
  RESUME_LINE=$(grep -A2 '^## Resume Instructions' "$COMPACTION_LATEST" 2>/dev/null | grep -v '^## ' | grep -v '^--$' | head -2)
  if [[ -n "$RESUME_LINE" ]]; then
    while IFS= read -r line; do
      print_line "  $line"
    done <<< "$RESUME_LINE"
  fi
  print_line "=== END CHECKPOINT ==="
  print_line ""
fi

# 2. Session log (mid-session decision journal)
SESSION_LOG="$PROJECT_DIR/.claude/session-log.md"
if [[ -f "$SESSION_LOG" ]]; then
  print_line "=== PREVIOUS SESSION LOG ==="
  # Show last 10 lines (most recent decisions)
  tail -10 "$SESSION_LOG" 2>/dev/null | while IFS= read -r line && [[ "$LINES_USED" -lt $((LINE_BUDGET - 10)) ]]; do
    print_line "$line"
  done
  print_line "=== END SESSION LOG ==="
  print_line ""
fi

# 3. Abandoned approaches (ruled-out context)
ABANDONED_DIR="$PROJECT_DIR/.claude/abandoned"
if [[ -d "$ABANDONED_DIR" ]]; then
  # Show most recent 3 abandoned records (by filename sort = date order)
  ABANDONED_FILES=$(ls -1 "$ABANDONED_DIR"/*.md 2>/dev/null | tail -3)
  if [[ -n "$ABANDONED_FILES" ]]; then
    print_line "=== PREVIOUSLY RULED OUT ==="
    while IFS= read -r afile; do
      # Extract title and why-abandoned from each file
      TITLE=$(head -1 "$afile" 2>/dev/null | sed 's/^# //')
      WHY=$(sed -n '/^## Why abandoned/,/^## /p' "$afile" 2>/dev/null | grep '^- ' | head -2)
      print_line "  $TITLE"
      if [[ -n "$WHY" ]]; then
        while IFS= read -r reason; do
          print_line "    $reason"
        done <<< "$WHY"
      fi
    done <<< "$ABANDONED_FILES"
    print_line "=== END RULED OUT ==="
    print_line ""
  fi
fi

# 4. CLAUDE.md reminder
if [[ -f "$PROJECT_DIR/CLAUDE.md" ]]; then
  print_line "[session-context-loader] CLAUDE.md found at project root — load it for project conventions."
  print_line ""
fi

# 5. Recent git activity
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
