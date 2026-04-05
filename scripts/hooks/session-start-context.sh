#!/usr/bin/env bash
# Session-start hook: output branch state and skill suggestions.
# Fires via .claude/hooks.json SessionStart.
# Output is injected into the conversation context automatically.
# CONSTRAINT: Keep output under 50 lines.
set -e

MEMORY_DIR="$HOME/.claude/projects/-Users-summerrae-courierflow/memory"
SESSION_STATE="$MEMORY_DIR/session-state.md"

# 1. Output session state if available
if [ -f "$SESSION_STATE" ]; then
    echo "=== SESSION CONTEXT ==="
    cat "$SESSION_STATE"
    echo ""
fi

# 2. Suggest skills based on recently touched files
if [ -f "$SESSION_STATE" ]; then
    FILES_LINE=$(grep "^Files touched:" "$SESSION_STATE" 2>/dev/null || echo "")
    SUGGESTIONS=""

    if echo "$FILES_LINE" | grep -qE 'app/models/|alembic/'; then
        SUGGESTIONS="$SUGGESTIONS /courierflow-data"
    fi
    if echo "$FILES_LINE" | grep -qE 'app/templates/|app/static/'; then
        SUGGESTIONS="$SUGGESTIONS /courierflow-ui"
    fi
    if echo "$FILES_LINE" | grep -qE 'app/routes/|app/services/'; then
        SUGGESTIONS="$SUGGESTIONS /courierflow-api"
    fi
    if echo "$FILES_LINE" | grep -qE 'calendar|email|sms|twilio'; then
        SUGGESTIONS="$SUGGESTIONS /courierflow-integrations"
    fi

    if [ -n "$SUGGESTIONS" ]; then
        echo "SKILL SUGGESTIONS (based on recent work):$SUGGESTIONS"
        echo ""
    fi
fi

# 3. Check for pre-compaction context
if [ -f "$SESSION_STATE" ] && grep -q "Pre-Compaction Context" "$SESSION_STATE" 2>/dev/null; then
    echo "NOTE: Pre-compaction context available in session-state.md — review for task continuity."
    echo ""
fi
