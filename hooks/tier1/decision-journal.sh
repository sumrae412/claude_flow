#!/usr/bin/env bash
# Trigger: PostToolUse (Edit, Write)
# Tracks file edits and periodically reminds Claude to journal design decisions.
# Uses a counter file to persist across tool calls within a session.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
COUNTER_FILE="/tmp/claude-flow-edit-counter-$$"
JOURNAL_INTERVAL=10

# Initialize or increment counter
if [[ -f "$COUNTER_FILE" ]]; then
  COUNT=$(cat "$COUNTER_FILE")
  COUNT=$((COUNT + 1))
else
  COUNT=1
fi
echo "$COUNT" > "$COUNTER_FILE"

# Every N edits, remind to journal decisions
if (( COUNT % JOURNAL_INTERVAL == 0 )); then
  SESSION_LOG="$PROJECT_DIR/.claude/session-log.md"

  # Create session log if it doesn't exist
  if [[ ! -f "$SESSION_LOG" ]]; then
    mkdir -p "$PROJECT_DIR/.claude"
    DATE=$(date +%Y-%m-%d)
    cat > "$SESSION_LOG" <<LOGEOF
# Session Log — $DATE

## Decisions

## Ruled Out
LOGEOF
  fi

  echo "[Decision Journal] $COUNT edits this session. If any design decisions, tradeoffs, or approach changes happened since the last entry, append them to .claude/session-log.md with timestamps."
fi

exit 0
