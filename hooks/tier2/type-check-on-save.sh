#!/usr/bin/env bash
# Trigger: PostToolUse:Edit (*.ts, *.tsx)
# Stack tag: node+typescript
# Runs `tsc --noEmit` to surface type errors after a TypeScript file is edited.
# Outputs up to 15 lines of results. Does not block.
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"

if [[ -z "$PROJECT_DIR" ]] || [[ ! -d "$PROJECT_DIR" ]]; then
  exit 0
fi

cd "$PROJECT_DIR"

if ! command -v npx >/dev/null 2>&1; then
  echo "[type-check-on-save] npx not found. Skipping TypeScript check."
  exit 0
fi

# Require a tsconfig to be present
if [[ ! -f "tsconfig.json" ]]; then
  exit 0
fi

echo "[type-check-on-save] Running tsc --noEmit..."
npx tsc --noEmit --pretty 2>&1 | tail -15 || true

exit 0
