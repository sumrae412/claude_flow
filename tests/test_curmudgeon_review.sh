#!/usr/bin/env bash
# Test curmudgeon_review.sh: mocked CLI produces parseable JSON;
# missing CLI exits 0 with warning (graceful skip).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIX="$REPO_ROOT/tests/fixtures/curmudgeon"

fail() { echo "FAIL: $1"; exit 1; }

# Case 1: codex present (via mock) → structured JSON output
export PATH="$FIX:$PATH"
chmod +x "$FIX/mock-codex"
ln -sf "$FIX/mock-codex" "$FIX/codex"
out=$("$REPO_ROOT/scripts/curmudgeon_review.sh" "$FIX/sample-diff.patch")
echo "$out" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); \
  assert 'findings' in d, 'missing findings key'; \
  assert isinstance(d['findings'], list), 'findings must be list'; \
  assert d.get('reviewer') == 'curmudgeon', 'reviewer must be curmudgeon'"
rm -f "$FIX/codex"

# Case 2: codex missing → exit 0 with "skipped" marker on stderr
PATH_NO_CODEX="$(echo "$PATH" | tr ':' '\n' | grep -v "$FIX" | paste -sd: -)"
out2=$(PATH="$PATH_NO_CODEX" "$REPO_ROOT/scripts/curmudgeon_review.sh" "$FIX/sample-diff.patch" 2>&1 >/dev/null || true)
echo "$out2" | grep -qi "skip\|not installed\|not found" || fail "missing CLI should log skip"

echo "OK"
