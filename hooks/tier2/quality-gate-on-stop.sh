#!/usr/bin/env bash
# Trigger: Stop
# Tier: 2 (opt-in via stack_tags match OR .claude/quality-gate.json)
# Purpose: Ambient quality gate — run project test/lint command when Claude
#          declares the turn done. Blocks the Stop event if checks fail,
#          feeding the error back into the same session for Claude to fix.
#
# Pattern: Modeled on the stop-hook → auto-fix loop from John Lindquist's
#          "advanced Claude Code" workflow. Adapted for claude-flow:
#          graceful no-op when no command is configured, auto-detection
#          of common project test runners, non-blocking timeout, JSON
#          output shape understood by the Claude harness.
#
# Command resolution order (first match wins, no fallthrough):
#   1. $CLAUDE_QUALITY_GATE_CMD         — explicit env override
#   2. .claude/quality-gate.json        — { "command": "..." } (project config)
#   3. scripts/quick_ci.sh              — CourierFlow / claude-flow convention
#   4. package.json "scripts.test"      — npm test
#   5. pyproject.toml + pytest          — python -m pytest -q
#   6. Cargo.toml                       — cargo check --quiet
#   7. go.mod                           — go build ./...
#   → none of the above               — exit 0 silently (graceful no-op)
#
# Exit codes:
#   0 — gate passed OR no gate configured (proceed with Stop)
#   2 — gate failed, emit block JSON on stderr (Claude sees this as a
#       retry signal per Stop-hook contract)

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" || exit 0

# Disable switch — users who opt out but can't remove the hook config
if [[ "${CLAUDE_QUALITY_GATE_DISABLED:-}" == "1" ]]; then
  exit 0
fi

# --- 1. Resolve command ---
CMD=""
SOURCE=""

if [[ -n "${CLAUDE_QUALITY_GATE_CMD:-}" ]]; then
  CMD="$CLAUDE_QUALITY_GATE_CMD"
  SOURCE="env CLAUDE_QUALITY_GATE_CMD"
elif [[ -f ".claude/quality-gate.json" ]]; then
  # Extract "command" field without jq dependency
  CMD=$(grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' .claude/quality-gate.json 2>/dev/null \
        | sed 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' | head -1)
  [[ -n "$CMD" ]] && SOURCE=".claude/quality-gate.json"
elif [[ -x "scripts/quick_ci.sh" ]]; then
  CMD="./scripts/quick_ci.sh"
  SOURCE="scripts/quick_ci.sh"
elif [[ -f "package.json" ]] && grep -q '"test"[[:space:]]*:' package.json 2>/dev/null; then
  # Ensure the test script is not the default stub
  if ! grep -q '"test"[[:space:]]*:[[:space:]]*"echo.*no test' package.json 2>/dev/null; then
    CMD="npm test --silent"
    SOURCE="package.json scripts.test"
  fi
elif [[ -f "pyproject.toml" ]] && command -v pytest >/dev/null 2>&1; then
  CMD="python -m pytest -q --no-header -x"
  SOURCE="pyproject.toml + pytest"
elif [[ -f "Cargo.toml" ]] && command -v cargo >/dev/null 2>&1; then
  CMD="cargo check --quiet"
  SOURCE="Cargo.toml"
elif [[ -f "go.mod" ]] && command -v go >/dev/null 2>&1; then
  CMD="go build ./..."
  SOURCE="go.mod"
fi

if [[ -z "$CMD" ]]; then
  # Graceful no-op — no gate configured, no project convention matched
  exit 0
fi

# --- 2. Run with timeout ---
TIMEOUT_SECS="${CLAUDE_QUALITY_GATE_TIMEOUT:-120}"
TMP_OUT=$(mktemp)
trap 'rm -f "$TMP_OUT"' EXIT

echo "[quality-gate-on-stop] Running: $CMD (source: $SOURCE, timeout: ${TIMEOUT_SECS}s)" >&2

# Prefer `timeout` if available; fall back to plain execution on macOS without coreutils
if command -v timeout >/dev/null 2>&1; then
  timeout "${TIMEOUT_SECS}" bash -c "$CMD" >"$TMP_OUT" 2>&1
  STATUS=$?
elif command -v gtimeout >/dev/null 2>&1; then
  gtimeout "${TIMEOUT_SECS}" bash -c "$CMD" >"$TMP_OUT" 2>&1
  STATUS=$?
else
  bash -c "$CMD" >"$TMP_OUT" 2>&1
  STATUS=$?
fi

# --- 3. Interpret result ---
if [[ $STATUS -eq 0 ]]; then
  echo "[quality-gate-on-stop] PASS ($SOURCE)" >&2
  exit 0
fi

if [[ $STATUS -eq 124 ]]; then
  # Timeout — don't block, just warn (turn-end shouldn't hang on slow CI)
  echo "[quality-gate-on-stop] TIMEOUT after ${TIMEOUT_SECS}s — not blocking. Set CLAUDE_QUALITY_GATE_TIMEOUT to increase." >&2
  exit 0
fi

# Failure → emit Stop-hook block JSON on stdout + tail of output on stderr
TAIL_OUT=$(tail -30 "$TMP_OUT" | sed 's/"/\\"/g' | tr '\n' ' ' | cut -c1-2000)

cat <<JSON
{"decision":"block","reason":"Quality gate failed ($SOURCE). Command: $CMD. Last output: $TAIL_OUT"}
JSON

echo "[quality-gate-on-stop] FAIL ($SOURCE, exit $STATUS) — blocking Stop so Claude can fix." >&2
tail -30 "$TMP_OUT" >&2
exit 2
