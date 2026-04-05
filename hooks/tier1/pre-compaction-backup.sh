#!/usr/bin/env bash
# Trigger: PreCompact
# Before the conversation is compacted, saves a summary snapshot to
# $CLAUDE_PROJECT_DIR/.claude/pre-compaction-<timestamp>.md
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
CLAUDE_DIR="$PROJECT_DIR/.claude"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTFILE="$CLAUDE_DIR/pre-compaction-${TIMESTAMP}.md"

mkdir -p "$CLAUDE_DIR"

{
  echo "# Pre-Compaction Snapshot — $TIMESTAMP"
  echo ""

  # Current branch
  BRANCH=$(git -C "$PROJECT_DIR" branch --show-current 2>/dev/null || echo "unknown")
  echo "## Branch"
  echo "$BRANCH"
  echo ""

  # Recent commits
  echo "## Recent Commits (last 5)"
  git -C "$PROJECT_DIR" log --oneline -5 2>/dev/null || echo "(no git history)"
  echo ""

  # Modified files
  echo "## Git Status"
  git -C "$PROJECT_DIR" status --short 2>/dev/null || echo "(git status unavailable)"
  echo ""

  # Task progress hint
  echo "## Task Progress"
  echo "Check TodoWrite for current task progress."
} > "$OUTFILE"

echo "[pre-compaction-backup] Snapshot saved to: $OUTFILE"
exit 0
