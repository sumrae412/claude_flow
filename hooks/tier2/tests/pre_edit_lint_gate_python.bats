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

@test "allows Edit that replaces cleanly" {
  if ! command -v ruff >/dev/null; then skip "ruff not available"; fi
  FIXTURE="$TMPDIR_TEST/edit_me.py"
  echo "x = 1" > "$FIXTURE"
  JSON=$(jq -n --arg f "$FIXTURE" '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"x = 1",new_string:"x = 2"}}')
  run bash "$HOOK" <<< "$JSON"
  [ "$status" -eq 0 ]
}

@test "blocks Edit that introduces ruff error" {
  if ! command -v ruff >/dev/null; then skip "ruff not available"; fi
  FIXTURE="$TMPDIR_TEST/edit_err.py"
  echo "x = 1" > "$FIXTURE"
  JSON=$(jq -n --arg f "$FIXTURE" '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"x = 1",new_string:"import os\nimport os"}}')
  run bash "$HOOK" <<< "$JSON"
  [ "$status" -ne 0 ]
}

@test "skips Edit when old_string does not match" {
  if ! command -v ruff >/dev/null; then skip "ruff not available"; fi
  FIXTURE="$TMPDIR_TEST/edit_nomatch.py"
  printf "import os\nimport os\n" > "$FIXTURE"   # pre-existing errors
  JSON=$(jq -n --arg f "$FIXTURE" '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"NOT_PRESENT",new_string:"also_not"}}')
  run bash "$HOOK" <<< "$JSON"
  [ "$status" -eq 0 ]   # don't block on unrelated pre-existing errors
}
