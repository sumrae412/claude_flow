#!/usr/bin/env bash
# emit-failure-event.sh — Append a structured failure/resolution event to the JSONL log.
#
# Usage:
#   emit-failure-event.sh <json-payload>
#
# The payload is a single JSON object. This script adds the timestamp and
# appends it as one line to memory/failure-events.jsonl.

set -euo pipefail

EVENTS_FILE="${CLAUDE_FLOW_DIR:-$(cd "$(dirname "$0")/.." && pwd)}/memory/failure-events.jsonl"
PAYLOAD="$1"

# Inject timestamp
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EVENT=$(echo "$PAYLOAD" | python3 -c "
import sys, json
obj = json.load(sys.stdin)
obj['ts'] = '$TS'
print(json.dumps(obj))
")

echo "$EVENT" >> "$EVENTS_FILE"
