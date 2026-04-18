#!/usr/bin/env bash
# Trigger: Stop
# Scans memory files modified this session and writes a REVIEW_QUEUE.md listing
# entries that are (a) not linked from MEMORY.md, or (b) missing recommended
# frontmatter fields. Never auto-commits (see: post_commit_hook_message_conflation).
set -uo pipefail

MEMORY_DIR="${MEMORY_DIR:-$HOME/.claude/projects/-Users-summerrae-claude-flow/memory}"
[[ ! -d "$MEMORY_DIR" ]] && exit 0

python3 "$(dirname "$0")/memory-triage-on-stop.py" "$MEMORY_DIR"
exit 0  # always succeed; this is advisory
