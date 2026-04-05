#!/usr/bin/env bash
# Pre-compaction hook: save session context before context window compacts.
# Fires via .claude/hooks.json PreCompact.
# Reads hook input from stdin (JSON with trigger, session_id, transcript_path).
# CONSTRAINT: Must complete in <5s.
set -e

MEMORY_DIR="$HOME/.claude/projects/-Users-summerrae-courierflow/memory"
SESSION_STATE="$MEMORY_DIR/session-state.md"

# Verify jq is available (fallback to python3 if not)
if command -v jq &>/dev/null; then
    JSON_PARSER="jq"
else
    JSON_PARSER="python3"
fi

# Read hook input
INPUT=$(cat)
if [ "$JSON_PARSER" = "jq" ]; then
    TRIGGER=$(echo "$INPUT" | jq -r '.trigger // "unknown"')
    TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // ""')
else
    TRIGGER=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trigger','unknown'))" 2>/dev/null || echo "unknown")
    TRANSCRIPT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || echo "")
fi

# Gather git state (fast operations only)
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
COMMITS_AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "?")
RECENT_FILES=$(git diff --name-only origin/main..HEAD 2>/dev/null | head -20 | tr '\n' ', ' | sed 's/,$//')

# Extract last 5 user messages from transcript (lightweight parsing)
# Reads only last 50 lines for speed. Filters out system messages and sensitive data.
RECENT_MESSAGES=""
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    RECENT_MESSAGES=$(tail -50 "$TRANSCRIPT" | \
        python3 -c "
import sys, json, re
messages = []
# Pattern to detect sensitive data
sensitive_re = re.compile(r'(api[_-]?key|token|password|secret|credential)', re.I)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
        if obj.get('role') == 'human':
            content = obj.get('content', '')
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part['text'][:200]
                        if not text.startswith('<system') and not sensitive_re.search(text):
                            messages.append(text)
            elif isinstance(content, str):
                if not content.startswith('<system') and not sensitive_re.search(content):
                    messages.append(content[:200])
    except (json.JSONDecodeError, KeyError):
        pass
for m in messages[-5:]:
    print(f'- {m}')
" 2>/dev/null || echo "- (transcript parsing failed)")
fi

# Write pre-compaction context
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Remove any previous pre-compaction section (keep only latest)
if [ -f "$SESSION_STATE" ]; then
    # Use temp file for cross-platform compat (avoids macOS sed -i '' issue)
    TMPFILE=$(mktemp)
    sed '/^## Pre-Compaction Context/,$d' "$SESSION_STATE" > "$TMPFILE"
    mv "$TMPFILE" "$SESSION_STATE"
fi

# Ensure base session state exists
if [ ! -f "$SESSION_STATE" ]; then
    cat > "$SESSION_STATE" << BASE_EOF
# Session State
Last updated: $TIMESTAMP
Branch: $BRANCH
Commits ahead of main: $COMMITS_AHEAD
BASE_EOF
fi

# Append pre-compaction context
cat >> "$SESSION_STATE" << COMPACT_EOF

## Pre-Compaction Context
Saved: $TIMESTAMP ($TRIGGER compaction)
Branch: $BRANCH ($COMMITS_AHEAD commits ahead)
Files changed this session: $RECENT_FILES

Recent user messages:
$RECENT_MESSAGES
COMPACT_EOF

echo "Pre-compaction context saved to session-state.md"
