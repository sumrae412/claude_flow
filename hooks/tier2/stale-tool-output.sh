#!/usr/bin/env bash
# Trigger: PostToolUse:Read|Grep|Glob
# Tier 2 — opt-in via stack detection (any stack with file-read-heavy workflows)
#
# Counts Read/Grep/Glob tool invocations per session. Unlike context-rot-detection
# (which counts UNIQUE files), this counts TOTAL operations — detects the "re-read
# the same 3 files 20 times" pattern common in long Phase 5/6 loops, where stale
# duplicate tool results accumulate even though unique-file count stays modest.
#
# Insight source: vercel-labs/open-agents context-management/aggressive-compaction-helpers.ts
# — they compact old tool inputs/outputs in place, keeping only recent calls expanded.
# Claude Code's harness owns the message list, so we can't compact surgically — this
# hook just nudges awareness when stale-duplicate pressure is likely high.
#
# DO NOT use `set -e` — filesystem failures on /tmp are benign and should not block
# the tool call. (See memory: hook_set_e_gotcha.md)

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
SESSION_ID="${CLAUDE_SESSION_ID:-default}"
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"

if [[ -z "$PROJECT_DIR" ]] || [[ ! -d "$PROJECT_DIR" ]]; then
  exit 0
fi

# Session-scoped counter file
TRACKER_DIR="/tmp/claude-stale-tool-output"
mkdir -p "$TRACKER_DIR" 2>/dev/null || exit 0
TRACKER_FILE="$TRACKER_DIR/$SESSION_ID.count"

# Only count read-family tools; Edit/Write/Bash excluded because their outputs
# are either intentional state changes (Edit/Write) or inherently one-shot (Bash).
case "$TOOL_NAME" in
  Read|Grep|Glob) ;;
  *) exit 0 ;;
esac

# Increment count (tolerate concurrent-write races by appending then counting)
echo "1" >> "$TRACKER_FILE" 2>/dev/null || exit 0
COUNT=$(wc -l < "$TRACKER_FILE" 2>/dev/null | tr -d ' ')
[[ -z "$COUNT" ]] && exit 0

# Thresholds (configurable via env)
# Defaults sized for Phase 5/6: typical clean run is 15-25 Read/Grep ops; 40+ is
# the signal that stale-duplicate pressure is dominating context.
WARN_THRESHOLD="${STALE_TOOL_WARN_THRESHOLD:-40}"
CRITICAL_THRESHOLD="${STALE_TOOL_CRITICAL_THRESHOLD:-70}"

# Fire the warning once per threshold crossing, not every tool call after.
MARKER_DIR="$TRACKER_DIR/markers"
mkdir -p "$MARKER_DIR" 2>/dev/null || exit 0

if [[ "$COUNT" -ge "$CRITICAL_THRESHOLD" ]] && [[ ! -f "$MARKER_DIR/$SESSION_ID.critical" ]]; then
  touch "$MARKER_DIR/$SESSION_ID.critical" 2>/dev/null || true
  echo ""
  echo "[stale-tool-output] ⚠️  CRITICAL: $COUNT Read/Grep/Glob operations this session."
  echo "    Claude Code doesn't surgically compact stale tool outputs — they accumulate"
  echo "    in context even when you re-read the same files. Recommended actions:"
  echo "    1. Summarize current state (phase, decisions, active files) to a handoff doc"
  echo "    2. Start a fresh session and /session-handoff resume"
  echo "    3. Or run /compact if the conversation still fits"
  echo "    4. Reset counter: rm $TRACKER_FILE $MARKER_DIR/$SESSION_ID.*"
  echo ""
elif [[ "$COUNT" -ge "$WARN_THRESHOLD" ]] && [[ ! -f "$MARKER_DIR/$SESSION_ID.warn" ]]; then
  touch "$MARKER_DIR/$SESSION_ID.warn" 2>/dev/null || true
  echo ""
  echo "[stale-tool-output] 🔶 WARNING: $COUNT Read/Grep/Glob operations this session."
  echo "    Stale duplicate tool results likely accumulating. Consider summarizing"
  echo "    progress and compacting before hitting context limits."
  echo ""
fi

exit 0
