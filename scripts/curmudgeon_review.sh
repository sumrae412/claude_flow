#!/usr/bin/env bash
# Curmudgeon reviewer: shells out to local `codex` CLI for a
# non-Anthropic second-opinion review. No API key required — uses
# the user's existing ChatGPT auth via the Codex CLI.
#
# Usage: curmudgeon_review.sh <path-to-diff-file>
# Output: JSON on stdout with {"reviewer":"curmudgeon","findings":[...]}
#         On missing CLI: logs SKIP message to stderr and exits 0 with
#         a parseable {"reviewer":"curmudgeon","findings":[],"skipped":true}
#         envelope on stdout so callers never have to special-case absence.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PERSONA_FILE="$SCRIPT_DIR/curmudgeon_persona.txt"

DIFF_FILE="${1:?usage: curmudgeon_review.sh <diff-file>}"

if [[ ! -f "$DIFF_FILE" ]]; then
    echo "curmudgeon: diff file not found: $DIFF_FILE" >&2
    echo '{"reviewer":"curmudgeon","findings":[],"skipped":true,"reason":"diff file not found"}'
    exit 0
fi

if [[ ! -f "$PERSONA_FILE" ]]; then
    echo "curmudgeon: persona file not found: $PERSONA_FILE" >&2
    echo '{"reviewer":"curmudgeon","findings":[],"skipped":true,"reason":"persona file not found"}'
    exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
    echo "curmudgeon: codex CLI not found on PATH — SKIPPING review (install: npm i -g @openai/codex)" >&2
    echo '{"reviewer":"curmudgeon","findings":[],"skipped":true,"reason":"codex CLI not installed"}'
    exit 0
fi

# Build the prompt in a temp file to avoid arg-length and quoting issues.
# Persona lives in a separate plain-text file so future edits (contractions,
# quotes, etc.) can't break bash string quoting.
PROMPT_FILE=$(mktemp -t curmudgeon-prompt.XXXXXX)
RAW_FILE=$(mktemp -t curmudgeon-raw.XXXXXX)
trap 'rm -f "$PROMPT_FILE" "$RAW_FILE"' EXIT

{
    cat "$PERSONA_FILE"
    echo ""
    echo "---"
    echo "Diff to review:"
    cat "$DIFF_FILE"
} > "$PROMPT_FILE"

# NOTE: `--quiet --output-format json` and the stdin input mode are both
# placeholder choices that will be verified post-install against
# `codex --help`. The script structure stays the same.
# Passing the prompt via stdin (not argv) avoids macOS ARG_MAX (~128KB)
# truncation on large diffs. `|| echo ...` ensures a codex failure
# degrades to an empty findings list rather than propagating a non-zero
# exit under `set -e`.
RAW=$(codex exec --quiet --output-format json < "$PROMPT_FILE" 2>/dev/null || echo '{"findings":[]}')

# Validate and normalize output. Malformed → empty findings, not failure.
# We read RAW from Python via env var (not embedded via heredoc) so arbitrary
# codex output — including triple-quotes, backticks, or embedded nulls —
# cannot break the shell-to-Python boundary.
RAW="$RAW" python3 - <<'PY'
import json, os
raw = os.environ.get("RAW", "")
try:
    d = json.loads(raw)
    findings = d.get("findings", []) if isinstance(d, dict) else []
    if not isinstance(findings, list):
        findings = []
except Exception:
    findings = []
print(json.dumps({"reviewer": "curmudgeon", "findings": findings}))
PY
