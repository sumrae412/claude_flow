#!/usr/bin/env bash
# Trigger: PostToolUse:Edit (*.py, *.js, *.ts, *.css, *.html)
# Scans edited files for known gotcha anti-patterns defined in gotcha-rules.json.
# Warnings only — does not block edits.

FILE="${CLAUDE_FILE_PATH:-$1}"
if [[ -z "$FILE" ]] || [[ ! -f "$FILE" ]]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RULES_FILE="$SCRIPT_DIR/gotcha-rules.json"

if [[ ! -f "$RULES_FILE" ]]; then
  exit 0
fi

FOUND=0

# Get file extension for matching
FILENAME=$(basename "$FILE")

# Use python3 to parse rules JSON and match against file
if command -v python3 >/dev/null 2>&1; then
  MATCHES=$(python3 -c "
import json, re, fnmatch, sys

rules_file = '$RULES_FILE'
target_file = '$FILE'
filename = '$FILENAME'

try:
    with open(rules_file) as f:
        data = json.load(f)
except Exception:
    sys.exit(0)

with open(target_file) as f:
    lines = f.readlines()

hits = []
for rule in data.get('rules', []):
    # Check if file matches any glob
    if not any(fnmatch.fnmatch(filename, g) for g in rule.get('file_globs', [])):
        continue

    pattern = rule['pattern']
    severity = rule.get('severity', 'warning').upper()
    message = rule.get('message', 'Gotcha detected')
    rule_id = rule.get('id', 'unknown')

    for i, line in enumerate(lines, 1):
        if re.search(pattern, line):
            hits.append(f'  line {i}: [{severity}] {rule_id} — {message}')

if hits:
    print('[gotcha-detector] Found issues in ' + filename + ':')
    for h in hits:
        print(h)
" 2>/dev/null)

  if [[ -n "$MATCHES" ]]; then
    echo "$MATCHES"
    FOUND=1
  fi
else
  # Fallback: hardcoded checks when python3 is unavailable
  case "$FILE" in
    *.py)
      if grep -n 'datetime\.utcnow()' "$FILE" 2>/dev/null; then
        echo "[gotcha-detector] WARNING: datetime.utcnow() is deprecated. Use datetime.now(timezone.utc)."
        FOUND=1
      fi
      if grep -n '\.cast(String)' "$FILE" 2>/dev/null; then
        echo "[gotcha-detector] WARNING: .cast(String) kills indexes on enum columns."
        FOUND=1
      fi
      if grep -nE 'is_primary[^_c]|is_primary$' "$FILE" 2>/dev/null; then
        echo "[gotcha-detector] WARNING: Use is_primary_contact, not is_primary."
        FOUND=1
      fi
      ;;
    *.css|*.html)
      if grep -n 'overflow:\s*hidden' "$FILE" 2>/dev/null; then
        echo "[gotcha-detector] CAUTION: overflow:hidden may clip flex/grid children. Use overflow:clip."
        FOUND=1
      fi
      ;;
    *.js|*.ts)
      if grep -n '\.innerHTML\s*=' "$FILE" 2>/dev/null; then
        echo "[gotcha-detector] WARNING: Use DOM API instead of innerHTML."
        FOUND=1
      fi
      ;;
  esac
fi

if [[ "$FOUND" -gt 0 ]]; then
  echo "[gotcha-detector] See MEMORY.md for full gotcha context. Rules: $RULES_FILE"
fi

exit 0
