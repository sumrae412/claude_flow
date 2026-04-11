#!/bin/bash
# Emit a phase-timing event to memory/episodic/phase-events.jsonl
# Usage: emit-phase-event.sh <phase> <tier> <duration_s> <retries> [domain]

set -euo pipefail

PHASE="${1:?phase required}"
TIER="${2:?tier required}"
DURATION="${3:?duration_s required}"
RETRIES="${4:-0}"
DOMAIN="${5:-}"

SESSION_ID="${SESSION_ID:-unknown}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EVENTS_FILE="$REPO_DIR/memory/episodic/phase-events.jsonl"

if [[ -n "$DOMAIN" ]]; then
  DOMAIN_JSON=", \"domain\": \"$DOMAIN\""
else
  DOMAIN_JSON=""
fi

printf '{"ts": "%s", "session_id": "%s", "phase": "%s", "tier": "%s", "duration_s": %s, "retries": %s%s}\n' \
  "$TS" "$SESSION_ID" "$PHASE" "$TIER" "$DURATION" "$RETRIES" "$DOMAIN_JSON" \
  >> "$EVENTS_FILE"
