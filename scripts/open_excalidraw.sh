#!/usr/bin/env bash
# Open a .excalidraw file for editing.
# Prefers VS Code Excalidraw extension; falls back to excalidraw.com.
# --dry-run: print the chosen open command without executing.
set -euo pipefail

DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
FILE="${1:?usage: open_excalidraw.sh [--dry-run] <file.excalidraw>}"

if [ ! -f "$FILE" ]; then
    echo "error: $FILE not found" >&2
    exit 1
fi

if command -v code >/dev/null 2>&1; then
    CMD=(code "$FILE")
    echo "Opening in VS Code (Excalidraw extension if installed): ${CMD[*]}"
    [ $DRY -eq 1 ] || "${CMD[@]}"
else
    echo "VS Code not on PATH."
    echo "Open this file at https://excalidraw.com/ (File → Open): $FILE"
    echo "Or install: code --install-extension pomdtr.excalidraw-editor"
fi
