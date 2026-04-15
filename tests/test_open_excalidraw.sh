#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIX="$REPO_ROOT/tests/fixtures/excalidraw/simple.excalidraw"

# Dry-run mode: print what would be opened, don't actually open
out=$("$REPO_ROOT/scripts/open_excalidraw.sh" --dry-run "$FIX")
echo "$out" | grep -qE "code|excalidraw\.com" || { echo "FAIL: no open path"; exit 1; }

# When VS Code missing, must mention excalidraw.com fallback
out2=$(PATH=/usr/bin:/bin "$REPO_ROOT/scripts/open_excalidraw.sh" --dry-run "$FIX")
echo "$out2" | grep -qi "excalidraw\.com" || { echo "FAIL: fallback not suggested"; exit 1; }

echo "OK"
