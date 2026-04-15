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

DIFF_FILE="${1:?usage: curmudgeon_review.sh <diff-file>}"

if [[ ! -f "$DIFF_FILE" ]]; then
    echo "curmudgeon: diff file not found: $DIFF_FILE" >&2
    echo '{"reviewer":"curmudgeon","findings":[],"skipped":true,"reason":"diff file not found"}'
    exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
    echo "curmudgeon: codex CLI not found on PATH — SKIPPING review (install: npm i -g @openai/codex)" >&2
    echo '{"reviewer":"curmudgeon","findings":[],"skipped":true,"reason":"codex CLI not installed"}'
    exit 0
fi

PERSONA='You are a curmudgeonly staff engineer reviewing a PR. You have seen every antipattern and you are tired. Focus on: code smells, inconsistencies with existing patterns, places where the diff works but is the wrong abstraction, tests that prove nothing, and suspicious silent-failure modes. Be specific; cite file:line. Do not praise. Do not repeat findings that a conventional linter or CodeRabbit would catch. Output ONLY a single JSON object: {"findings":[{"file":str,"line":int,"severity":"HIGH|MEDIUM|LOW","title":str,"rationale":str}]}.'

# Build the prompt in a temp file to avoid arg-length and quoting issues.
PROMPT_FILE=$(mktemp -t curmudgeon-prompt.XXXXXX)
RAW_FILE=$(mktemp -t curmudgeon-raw.XXXXXX)
trap 'rm -f "$PROMPT_FILE" "$RAW_FILE"' EXIT

{
    printf '%s\n\n---\nDiff to review:\n' "$PERSONA"
    cat "$DIFF_FILE"
} >"$PROMPT_FILE"

# NOTE: the exact `codex exec` flags depend on the Codex CLI version
# (e.g. `--json` vs `--output-format json`). Adjust after installing
# Codex CLI locally and running `codex --help`. The script structure
# stays the same. `|| true` ensures a codex failure degrades to an empty
# findings list rather than propagating a non-zero exit under `set -e`.
codex exec --quiet --output-format json "$(cat "$PROMPT_FILE")" >"$RAW_FILE" 2>/dev/null || echo '{"findings":[]}' >"$RAW_FILE"

# Validate and normalize output. Malformed → empty findings, not failure.
# We read RAW_FILE from Python (not embed via heredoc) so arbitrary
# codex output — including triple-quotes, backticks, or embedded nulls —
# cannot break the shell-to-Python boundary.
RAW_FILE="$RAW_FILE" python3 - <<'PY'
import json, os, sys
raw_path = os.environ["RAW_FILE"]
try:
    with open(raw_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    d = json.loads(raw)
    findings = d.get("findings", []) if isinstance(d, dict) else []
    if not isinstance(findings, list):
        findings = []
except Exception:
    findings = []
print(json.dumps({"reviewer": "curmudgeon", "findings": findings}))
PY
