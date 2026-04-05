#!/usr/bin/env bash
# Trigger: PreToolUse:Bash (matcher filters to dangerous git commands)
# Blocks dangerous git operations: push --force, push -f, reset --hard,
# checkout ., clean -fd.
# The hook matcher already filters to matching commands; this script
# explains why the action is blocked and exits 1.
set -e

CMD="${CLAUDE_COMMAND:-<unknown command>}"

echo "[dangerous-git-ops] BLOCKED: Refusing to run: $CMD"
echo ""
echo "  This command is potentially destructive and has been blocked by policy."
echo "  Dangerous operations intercepted:"
echo "    - git push --force / git push -f  (rewrites remote history)"
echo "    - git reset --hard               (discards local changes permanently)"
echo "    - git checkout .                 (discards all working-tree changes)"
echo "    - git clean -fd                  (deletes untracked files/dirs)"
echo ""
echo "  If you are certain, run the command manually in your terminal."

exit 1
