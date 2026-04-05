#!/usr/bin/env bash
# Post-commit hook: detect what changed and tell Claude to update memory files.
# Fires via .claude/hooks.json PostToolUse matcher Bash(*git commit*)
#
# This script analyzes the committed files and outputs structured instructions
# for Claude to update the relevant memory files. Claude reads the output
# and acts on it in the conversation.
set -e

MEMORY_DIR="$HOME/.claude/projects/-Users-summerrae-courierflow/memory"
COMMITS_AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "?")

# Get files changed in the last commit
CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || echo "")

if [ -z "$CHANGED_FILES" ]; then
    exit 0
fi

# Categorize changes
HAS_MODEL_CHANGES=false
HAS_ROUTE_CHANGES=false
HAS_SERVICE_CHANGES=false
HAS_TEMPLATE_CHANGES=false
HAS_SCHEMA_CHANGES=false
HAS_CONFIG_CHANGES=false
HAS_MIGRATION_CHANGES=false

while IFS= read -r file; do
    case "$file" in
        app/models/*.py)     HAS_MODEL_CHANGES=true ;;
        app/routes/*.py)     HAS_ROUTE_CHANGES=true ;;
        app/services/*.py)   HAS_SERVICE_CHANGES=true ;;
        app/templates/*)     HAS_TEMPLATE_CHANGES=true ;;
        app/schemas/*.py)    HAS_SCHEMA_CHANGES=true ;;
        app/config.py|app/database/*|app/exceptions.py) HAS_CONFIG_CHANGES=true ;;
        alembic/versions/*)  HAS_MIGRATION_CHANGES=true ;;
    esac
done <<< "$CHANGED_FILES"

# Build update instructions for Claude
UPDATES_NEEDED=false
UPDATE_TARGETS=""

if $HAS_MODEL_CHANGES; then
    UPDATES_NEEDED=true
    UPDATE_TARGETS="$UPDATE_TARGETS models.md(models changed)"
fi
if $HAS_ROUTE_CHANGES || $HAS_SERVICE_CHANGES; then
    UPDATES_NEEDED=true
    UPDATE_TARGETS="$UPDATE_TARGETS file-map.md(routes/services changed)"
fi
if $HAS_SCHEMA_CHANGES; then
    UPDATES_NEEDED=true
    UPDATE_TARGETS="$UPDATE_TARGETS file-map.md(schemas changed)"
fi
if $HAS_CONFIG_CHANGES; then
    UPDATES_NEEDED=true
    UPDATE_TARGETS="$UPDATE_TARGETS patterns.md(config/infra changed)"
fi
if $HAS_MIGRATION_CHANGES; then
    UPDATES_NEEDED=true
    UPDATE_TARGETS="$UPDATE_TARGETS models.md(migration added)"
fi

echo ""
echo "POST-COMMIT MEMORY UPDATE ($COMMITS_AHEAD commit(s) ahead of main)"

if $UPDATES_NEEDED; then
    echo "MEMORY-UPDATE-NEEDED: Files changed that affect memory:"
    echo "  Changed:$UPDATE_TARGETS"
    echo "  Memory dir: $MEMORY_DIR"
    echo ""
    echo "ACTION REQUIRED: Review the changed files and update the affected"
    echo "memory files so future sessions have accurate context."
fi

# Write session-state.md for cross-session continuity
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
LAST_COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
LAST_COMMIT_MSG=$(git log -1 --pretty=%s 2>/dev/null || echo "unknown")
CHANGED_LIST=$(echo "$CHANGED_FILES" | tr '\n' ', ' | sed 's/,$//')
CHANGED_LIST=${CHANGED_LIST:-none}

cat > "$MEMORY_DIR/session-state.md" << STATE_EOF
# Session State
Last updated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Branch: $BRANCH
Last commit: $LAST_COMMIT_HASH — $LAST_COMMIT_MSG
Files touched: $CHANGED_LIST
Commits ahead of main: $COMMITS_AHEAD
STATE_EOF

# Always trigger session-learnings for significant work
if [ "$COMMITS_AHEAD" != "?" ] && [ "$COMMITS_AHEAD" -ge 2 ]; then
    echo ""
    echo "SESSION-LEARNINGS: $COMMITS_AHEAD commits ahead of main."
    echo "Run the session-learnings skill to capture patterns, corrections,"
    echo "and gotchas from this session. Compile session context first:"
    echo "  - User corrections during this session"
    echo "  - Bugs investigated and root causes found"
    echo "  - New patterns or conventions established"
    echo "  - Gotchas encountered (hook blocks, API quirks, workarounds)"
fi
echo ""
