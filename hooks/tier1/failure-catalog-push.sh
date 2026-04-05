#!/usr/bin/env bash
# failure-catalog-push.sh — Commit and push failure-catalog.md after novel resolution.
#
# Called by the retry loop after a resolution:novel event adds a new catalog entry.
# Falls back gracefully if remote is unreachable.

set -euo pipefail

REPO_DIR="${CLAUDE_FLOW_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
CATALOG="$REPO_DIR/memory/failure-catalog.md"
EVENTS="$REPO_DIR/memory/failure-events.jsonl"

cd "$REPO_DIR"

# Stage catalog and events
git add "$CATALOG" "$EVENTS"

# Check if there are staged changes
if git diff --cached --quiet; then
  echo "No catalog changes to push."
  exit 0
fi

git commit -m "chore: update failure catalog with new pattern"

# Push with timeout — fall back to local-only if offline
if timeout 10 git push 2>/dev/null; then
  echo "Failure catalog pushed to remote."
else
  echo "WARNING: Could not push to remote. Catalog updated locally only."
  echo "Run 'git push' manually when network is available."
fi
