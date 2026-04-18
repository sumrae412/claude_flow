#!/usr/bin/env bats
# Tests for hooks/tier2/pre-edit-lint-gate-js.sh
# Reads PreToolUse JSON on stdin, blocks Edit/Write when resulting file fails eslint.

setup() {
  HOOK="$BATS_TEST_DIRNAME/../pre-edit-lint-gate-js.sh"
  TMPDIR_TEST="$(mktemp -d)"
  export CLAUDE_PROJECT_DIR="$TMPDIR_TEST"
  # ESLint v9+ flat config; v8 legacy eslintConfig in package.json no longer works.
  cat > "$TMPDIR_TEST/package.json" <<EOF
{
  "name": "test",
  "type": "module"
}
EOF
  cat > "$TMPDIR_TEST/eslint.config.js" <<'EOF'
export default [
  {
    rules: {
      "no-unused-vars": "error",
      "no-undef": "error"
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module"
    }
  }
];
EOF
}

teardown() { rm -rf "$TMPDIR_TEST"; }

@test "skips gracefully when eslint is not installed" {
  PATH="/usr/bin:/bin" run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.js","content":"const x = 1;\n"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *'"skipped":true'* ]]
}

@test "allows clean js" {
  if ! command -v eslint >/dev/null 2>&1 && ! npx --no-install eslint --version >/dev/null 2>&1; then
    skip "eslint not available"
  fi
  run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.js","content":"const x = 1; export default x;\n"}}'
  [ "$status" -eq 0 ]
  [[ "$output" != *'"deny":true'* ]]
}

@test "blocks js with eslint errors" {
  if ! command -v eslint >/dev/null 2>&1 && ! npx --no-install eslint --version >/dev/null 2>&1; then
    skip "eslint not available"
  fi
  run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.js","content":"const x = 1;\n"}}'
  [ "$status" -ne 0 ]
  [[ "$output" == *"eslint"* ]]
}

@test "ignores non-js/ts files" {
  run bash "$HOOK" <<< '{"tool_name":"Write","tool_input":{"file_path":"x.md","content":"# hi\n"}}'
  [ "$status" -eq 0 ]
}

@test "skips when tool_name is not Edit or Write" {
  run bash "$HOOK" <<< '{"tool_name":"Bash","tool_input":{"command":"ls"}}'
  [ "$status" -eq 0 ]
}

@test "allows Edit that replaces cleanly" {
  if ! command -v eslint >/dev/null 2>&1 && ! npx --no-install eslint --version >/dev/null 2>&1; then
    skip "eslint not available"
  fi
  FIXTURE="$TMPDIR_TEST/edit_me.js"
  printf 'const x = 1; export default x;\n' > "$FIXTURE"
  JSON=$(jq -n --arg f "$FIXTURE" '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"const x = 1;",new_string:"const x = 2;"}}')
  run bash "$HOOK" <<< "$JSON"
  [ "$status" -eq 0 ]
}

@test "blocks Edit that introduces eslint error" {
  if ! command -v eslint >/dev/null 2>&1 && ! npx --no-install eslint --version >/dev/null 2>&1; then
    skip "eslint not available"
  fi
  FIXTURE="$TMPDIR_TEST/edit_err.js"
  printf 'const x = 1; export default x;\n' > "$FIXTURE"
  JSON=$(jq -n --arg f "$FIXTURE" '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"const x = 1; export default x;","new_string":"const x = 1;"}}')
  run bash "$HOOK" <<< "$JSON"
  [ "$status" -ne 0 ]
}

@test "skips Edit when old_string does not match" {
  if ! command -v eslint >/dev/null 2>&1 && ! npx --no-install eslint --version >/dev/null 2>&1; then
    skip "eslint not available"
  fi
  FIXTURE="$TMPDIR_TEST/edit_nomatch.js"
  printf 'const x = 1;\n' > "$FIXTURE"   # pre-existing errors
  JSON=$(jq -n --arg f "$FIXTURE" '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"NOT_PRESENT",new_string:"also_not"}}')
  run bash "$HOOK" <<< "$JSON"
  [ "$status" -eq 0 ]   # don't block on unrelated pre-existing errors
}
