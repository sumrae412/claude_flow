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
  echo ""

  # Workflow phase (from workflow-state.json if it exists)
  WORKFLOW_STATE="$CLAUDE_DIR/workflow-state.json"
  if [[ -f "$WORKFLOW_STATE" ]]; then
    echo "## Workflow Phase"
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "
import json, sys
try:
    d = json.load(open('$WORKFLOW_STATE'))
    cp = d.get('current_phase', {})
    if isinstance(cp, dict):
        print(f\"Phase: {cp.get('id', 'unknown')} ({cp.get('name', '')}) — Step {cp.get('step', '?')} ({cp.get('step_label', '')})\")
        print(f\"Path: {cp.get('path', 'not set')} | Iteration: {cp.get('iteration', '?')}/{cp.get('max_iterations', '?')}\")
    else:
        print(f'Phase: {cp}')
    print(f\"Task: {d.get('task_summary', 'unknown')}\")

except Exception:
    print('(unable to parse workflow-state.json)')
" 2>/dev/null
    else
      grep -o '"current_phase"[^,]*' "$WORKFLOW_STATE" 2>/dev/null || echo "(no phase data)"
    fi
    echo ""
  fi

  # Recent decisions (from session-log.md)
  SESSION_LOG="$CLAUDE_DIR/session-log.md"
  if [[ -f "$SESSION_LOG" ]]; then
    echo "## Recent Decisions"
    tail -15 "$SESSION_LOG" 2>/dev/null
    echo ""
  fi

  # Detailed modified files
  echo "## Modified Files (Detail)"
  git -C "$PROJECT_DIR" diff --stat HEAD 2>/dev/null || echo "(no uncommitted changes)"
  echo ""

  # Active plan reference
  PLAN_DIR="$PROJECT_DIR/docs/plans"
  if [[ -d "$PLAN_DIR" ]]; then
    LATEST_PLAN=$(ls -t "$PLAN_DIR"/*.md 2>/dev/null | head -1)
    if [[ -n "$LATEST_PLAN" ]]; then
      echo "## Active Plan"
      echo "File: $LATEST_PLAN"
      head -5 "$LATEST_PLAN" 2>/dev/null
      echo ""
    fi
  fi

  # Resume instructions
  echo "## Resume Instructions"
  echo "Auto-generated before context compaction."
  echo "Load this file and the active plan to resume work."
} > "$OUTFILE"

# Clean up old checkpoints (keep last 3)
ls -t "$CLAUDE_DIR"/pre-compaction-*.md 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null || true

echo "[pre-compaction-backup] Snapshot saved to: $OUTFILE"
exit 0
