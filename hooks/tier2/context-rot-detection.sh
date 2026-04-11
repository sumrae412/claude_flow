#!/usr/bin/env bash
# Trigger: PostToolUse:Read|Edit|Write|Grep|Glob
# Tier 2 — opt-in via stack detection
# Tracks unique files touched in the session. When the count exceeds a
# threshold without a compaction or summary, warns about context rot.
# Uses a lightweight temp file per session to accumulate file paths.
set -e

FILE="${CLAUDE_FILE_PATH:-}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
SESSION_ID="${CLAUDE_SESSION_ID:-default}"

if [[ -z "$PROJECT_DIR" ]] || [[ ! -d "$PROJECT_DIR" ]]; then
  exit 0
fi

# Session-scoped tracker file
TRACKER_DIR="/tmp/claude-context-rot"
mkdir -p "$TRACKER_DIR"
TRACKER_FILE="$TRACKER_DIR/$SESSION_ID.files"

# Record the file if we have one
if [[ -n "$FILE" ]] && [[ -f "$FILE" ]]; then
  # Store relative path to reduce noise
  REL_PATH="${FILE#"$PROJECT_DIR"/}"
  echo "$REL_PATH" >> "$TRACKER_FILE"
fi

# Count unique files touched
if [[ ! -f "$TRACKER_FILE" ]]; then
  exit 0
fi

UNIQUE_COUNT=$(sort -u "$TRACKER_FILE" | wc -l | tr -d ' ')

# Thresholds (configurable via env)
WARN_THRESHOLD="${CONTEXT_ROT_WARN_THRESHOLD:-20}"
CRITICAL_THRESHOLD="${CONTEXT_ROT_CRITICAL_THRESHOLD:-35}"

if [[ "$UNIQUE_COUNT" -ge "$CRITICAL_THRESHOLD" ]]; then
  echo ""
  echo "[context-rot-detection] ⚠️  CRITICAL: $UNIQUE_COUNT unique files touched this session without compaction."
  echo "    Context is likely degraded. Recommended actions:"
  echo "    1. Write a summary of current state (what's done, what remains)"
  echo "    2. Run /compact or start a fresh session with handoff.md"
  echo "    3. Reset tracker: rm $TRACKER_FILE"
  echo ""
elif [[ "$UNIQUE_COUNT" -ge "$WARN_THRESHOLD" ]]; then
  echo ""
  echo "[context-rot-detection] 🔶 WARNING: $UNIQUE_COUNT unique files touched this session."
  echo "    Consider summarizing progress and compacting context soon."
  echo "    To reset after compaction: rm $TRACKER_FILE"
  echo ""
fi

exit 0
