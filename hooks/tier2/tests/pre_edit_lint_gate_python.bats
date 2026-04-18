#!/usr/bin/env bats
# Tests for hooks/tier2/pre-edit-lint-gate-python.sh
# Reads PreToolUse JSON on stdin, blocks Edit/Write when resulting file fails ruff.

setup() {
  HOOK="$BATS_TEST_DIRNAME/../pre-edit-lint-gate-python.sh"
  TMPDIR_TEST="$(mktemp -d)"
  export CLAUDE_PROJECT_DIR="$TMPDIR_TEST"
  cat > "$TMPDIR_TEST/pyproject.toml" <<EOF
[tool.ruff]
line-length = 100
EOF
}

teardown() { rm -rf "$TMPDIR_TEST"; }

@test "skips gracefully when ruff is not installed" {
  PATH="/usr/bin:/bin" run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.py","content":"x=1\n"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *'"skipped":true'* ]]
}

@test "allows clean python" {
  if ! command -v ruff >/dev/null; then skip "ruff not available"; fi
  run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.py","content":"x = 1\n"}}'
  [ "$status" -eq 0 ]
  [[ "$output" != *'"deny":true'* ]]
}

@test "blocks python with ruff errors" {
  if ! command -v ruff >/dev/null; then skip "ruff not available"; fi
  run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.py","content":"import os\nimport os\n"}}'
  [ "$status" -ne 0 ]
  [[ "$output" == *"ruff"* ]]
}

@test "ignores non-python files" {
  run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.md","content":"# hi\n"}}'
  [ "$status" -eq 0 ]
}

@test "skips when tool_name is not Edit or Write" {
  run bash "$HOOK" <<< '{"tool_name":"Bash","tool_input":{"command":"ls"}}'
  [ "$status" -eq 0 ]
}
