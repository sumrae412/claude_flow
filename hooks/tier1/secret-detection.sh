#!/usr/bin/env bash
# Trigger: PreToolUse:Edit,Write
# Scans the file being written/edited for common secret patterns.
# Exits 1 (BLOCK) if a secret is detected. Skips allowlisted file types.
set -e

FILE="${CLAUDE_FILE_PATH:-}"

if [[ -z "$FILE" ]]; then
  exit 0
fi

# Allowlist: example files, markdown, test/fixture/mock files
if [[ "$FILE" =~ \.(example|md|MD)$ ]] || \
   [[ "$FILE" =~ (test|fixture|mock|spec) ]]; then
  exit 0
fi

if [[ ! -f "$FILE" ]]; then
  exit 0
fi

PATTERNS=(
  'sk_live_[a-zA-Z0-9]+'
  'sk_test_[a-zA-Z0-9]+'
  'AKIA[0-9A-Z]{16}'
  'ghp_[a-zA-Z0-9]{36}'
  'password\s*=\s*"[^"]{8,}"'
  'Authorization:\s*Bearer\s+[a-zA-Z0-9._\-]+'
  'AWS_SECRET_ACCESS_KEY\s*=\s*[^\s]+'
  'aws_secret_access_key\s*=\s*[^\s]+'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
)

FOUND=()
for PATTERN in "${PATTERNS[@]}"; do
  if grep -Eq "$PATTERN" "$FILE" 2>/dev/null; then
    FOUND+=("$PATTERN")
  fi
done

if [[ ${#FOUND[@]} -gt 0 ]]; then
  echo "[secret-detection] BLOCKED: Potential secret(s) detected in $FILE"
  for P in "${FOUND[@]}"; do
    echo "  - Pattern matched: $P"
  done
  echo "  Remove secrets before writing. Use environment variables or a secrets manager."
  exit 1
fi

exit 0
