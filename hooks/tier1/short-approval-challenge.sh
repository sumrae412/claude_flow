#!/usr/bin/env bash
# UserPromptSubmit hook: when the user sends a short approval like "ship" / "yes" / "merge",
# inject a reminder to gut-check the last unverified assistant claim.
#
# Reads hook JSON from stdin; Claude Code parses stdout as additional context.
# Exit 0 always — this hook should never block.

set -euo pipefail

input="$(cat)"

# Extract prompt field. Fall back to empty if jq unavailable or field missing.
if command -v jq >/dev/null 2>&1; then
  prompt="$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null || true)"
else
  prompt=""
fi

# Strip whitespace and trailing punctuation, lowercase.
normalized="$(printf '%s' "$prompt" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/[[:punct:]]+$//')"

# Match short approval tokens (single words or two-word variants).
case "$normalized" in
  ship|"ship it"|yes|lgtm|ok|okay|continue|merge|"merge it"|done|go|"go ahead"|approved|proceed|commit|"commit it"|push|"push it")
    cat <<'EOF'
<approval-challenge>
You just sent a short approval. Before Claude proceeds:
- What's the last factual claim Claude made that you're accepting on faith?
  (e.g., "tests pass", "migration ran", "X is fixed", "PR merged")
- If you can name it and you're comfortable, proceed.
- If you can't, ask Claude to show the command + output that proves it before continuing.

Claude: if the previous turn made a completion claim without citing concrete evidence
(command output, file contents, git state), pause and produce that evidence now
before acting on the approval.
</approval-challenge>
EOF
    ;;
  *)
    : # not a short approval — no output, no reminder
    ;;
esac

exit 0
