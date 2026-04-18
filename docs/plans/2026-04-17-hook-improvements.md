# Hook Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a blocking pre-edit lint gate, a memory-entry schema bump (evidence IDs + confidence), and a Stop-hook scaffold for untriaged-memory triage — distilled from the GitHub Copilot CLI "hooks" video and the `codejunkie99/agentic-stack` repo.

**Architecture:** Three independent additions, layered onto the existing `hooks/tier1/` + `hooks/tier2/` registry pattern. P1 is a new opt-in tier-2 PreToolUse hook that blocks `Edit`/`Write` when the resulting file would fail lint — distinct from the existing advisory `lint-on-save-*.sh` PostToolUse hooks. P3 is a non-breaking frontmatter extension validated by the `lint-memory` skill. P2 is a new opt-in tier-2 Stop hook that writes a review queue but **never auto-commits** (per the `post_commit_hook_message_conflation` gotcha).

**Tech Stack:** bash, jq, ruff (Python), eslint (JS/TS), python3 (for YAML-frontmatter parsing in lint-memory). Tests in bats-core where available; plain shell assertions otherwise.

**Sources:**
- Video: Copilot CLI hooks walkthrough (pre-tool-use lint gate, §17:00–19:15)
- Repo: [codejunkie99/agentic-stack](https://github.com/codejunkie99/agentic-stack) `.agent/harness/hooks/*.py`, `adapters/claude-code/settings.json`

**Ruled out:**
- Agentic-stack's `permissions.md` keyword-matcher (brittle 2-keyword heuristic); existing `permissions.deny` in `settings.json` is stricter.
- Mirroring the full episodic→semantic→dream-cycle memory split; claude_flow already has `session-learnings` + `post-commit-learnings.sh` on the commit path. Building a parallel JSONL log would duplicate plumbing.
- Agentic-stack's `on_failure.py` rewrite-flag threshold; the existing retry-loop policy + failure catalog covers this.
- Agentic-stack's `session_start` context injection; `authoring-time-lookups` / `inject_lookups.py` already does repo-fact injection.
- Making the pre-edit lint gate a tier-1 default; too intrusive for unrelated projects. Opt-in via `stack_tags`.

**Non-goals:**
- Refactoring existing `lint-on-save-*.sh` hooks (they remain advisory PostToolUse).
- Retroactive backfill of `evidence:` / `confidence:` fields on existing memory files (they remain optional; linted only when present).

---

## Task 1: Write failing tests for `pre-edit-lint-gate-python`

**Files:**
- Create: `hooks/tier2/tests/pre_edit_lint_gate_python.bats`

**Step 1: Create the test file**

```bash
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
```

**Step 2: Verify the hook file does not yet exist**

Run: `ls /Users/summerrae/claude_code/claude_flow/hooks/tier2/pre-edit-lint-gate-python.sh`
Expected: `No such file or directory`

**Step 3: Run the tests (they should fail because the hook doesn't exist)**

Run: `cd /Users/summerrae/claude_code/claude_flow && bats hooks/tier2/tests/pre_edit_lint_gate_python.bats`
Expected: all tests fail (hook file not found). If `bats` is unavailable, install via `brew install bats-core`.

**Step 4: Commit the failing tests**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add hooks/tier2/tests/pre_edit_lint_gate_python.bats
git commit -m "test: add failing tests for pre-edit-lint-gate-python"
```

---

## Task 2: Implement `pre-edit-lint-gate-python.sh`

**Files:**
- Create: `hooks/tier2/pre-edit-lint-gate-python.sh`

**Step 1: Write the minimal implementation**

```bash
#!/usr/bin/env bash
# Trigger: PreToolUse:Edit|Write (*.py)
# Stack tag: python+ruff
# Blocks the edit/write if the resulting Python content fails `ruff check`.
# Graceful skip envelope when ruff is missing (per optional-dep-gate policy).
set -uo pipefail

INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | jq -r '.tool_name // empty')"
case "$TOOL_NAME" in
  Edit|Write) ;;
  *) exit 0 ;;
esac

FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')"
[[ "$FILE_PATH" != *.py ]] && exit 0

if ! command -v ruff >/dev/null 2>&1; then
  echo '{"reviewer":"pre-edit-lint-gate-python","skipped":true,"reason":"ruff not installed"}'
  exit 0
fi

# For Write: content is in tool_input.content.
# For Edit: reconstruct post-edit content by applying new_string to the real file.
CONTENT=""
if [[ "$TOOL_NAME" == "Write" ]]; then
  CONTENT="$(echo "$INPUT" | jq -r '.tool_input.content // empty')"
elif [[ "$TOOL_NAME" == "Edit" ]] && [[ -f "$FILE_PATH" ]]; then
  OLD="$(echo "$INPUT" | jq -r '.tool_input.old_string // empty')"
  NEW="$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')"
  # Use python to do the replacement safely (no shell escaping pitfalls).
  CONTENT="$(OLD="$OLD" NEW="$NEW" FILE="$FILE_PATH" python3 - <<'PY'
import os, sys
src = open(os.environ["FILE"]).read()
sys.stdout.write(src.replace(os.environ["OLD"], os.environ["NEW"], 1))
PY
)"
fi

[[ -z "$CONTENT" ]] && exit 0

TMP="$(mktemp -t preeditlint.XXXXXX).py"
trap 'rm -f "$TMP"' EXIT
printf '%s' "$CONTENT" > "$TMP"

OUTPUT="$(ruff check --no-fix "$TMP" 2>&1 || true)"
if echo "$OUTPUT" | grep -qE "^[A-Z][0-9]+|error:"; then
  echo "[pre-edit-lint-gate-python] BLOCKED: ruff errors in $FILE_PATH"
  echo "$OUTPUT" | head -20
  echo "Fix the lint errors before writing the file."
  exit 2  # exit 2 signals block per Claude Code hook spec
fi
exit 0
```

**Step 2: Make it executable**

Run: `chmod +x /Users/summerrae/claude_code/claude_flow/hooks/tier2/pre-edit-lint-gate-python.sh`
Expected: no output, exit 0.

**Step 3: Run the tests to verify they pass**

Run: `cd /Users/summerrae/claude_code/claude_flow && bats hooks/tier2/tests/pre_edit_lint_gate_python.bats`
Expected: all 5 tests pass (or `skip`ped with reason "ruff not available" if ruff is missing on this machine).

**Step 4: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add hooks/tier2/pre-edit-lint-gate-python.sh
git commit -m "feat(hooks): add blocking pre-edit lint gate for python"
```

---

## Task 3: Register `pre-edit-lint-gate-python` in the hook registry

**Files:**
- Modify: `hooks/hook-registry.json`

**Step 1: Add the registry entry**

Locate the closing `]` of the `"hooks":` array. Before it, insert:

```json
,
{
  "id": "pre-edit-lint-gate-python",
  "tier": 2,
  "trigger": "PreToolUse",
  "matcher": ["Edit", "Write"],
  "script": "hooks/tier2/pre-edit-lint-gate-python.sh",
  "stack_tags": ["python+ruff"],
  "opt_in": true,
  "description": "Blocks Edit/Write on *.py when the resulting content fails `ruff check` — forces fix-before-move-on. Skips when ruff is not installed."
}
```

**Step 2: Validate registry JSON**

Run: `cd /Users/summerrae/claude_code/claude_flow && python3 -c "import json; json.load(open('hooks/hook-registry.json'))"`
Expected: no output, exit 0.

**Step 3: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add hooks/hook-registry.json
git commit -m "feat(hooks): register pre-edit-lint-gate-python as opt-in tier 2"
```

---

## Task 4: Write failing tests for `pre-edit-lint-gate-js`

**Files:**
- Create: `hooks/tier2/tests/pre_edit_lint_gate_js.bats`

**Step 1: Write the test file**

Mirror the structure of `pre_edit_lint_gate_python.bats`. Substitute `ruff` → `eslint`, `pyproject.toml` → `package.json`, `.py` → `.js`. Matchers for block cases: unused import, `eqeqeq`. Include a fifth test: `@test "ignores .py files"`.

**Step 2: Run tests to confirm they fail**

Run: `cd /Users/summerrae/claude_code/claude_flow && bats hooks/tier2/tests/pre_edit_lint_gate_js.bats`
Expected: all tests fail (hook does not exist).

**Step 3: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add hooks/tier2/tests/pre_edit_lint_gate_js.bats
git commit -m "test: add failing tests for pre-edit-lint-gate-js"
```

---

## Task 5: Implement `pre-edit-lint-gate-js.sh`

**Files:**
- Create: `hooks/tier2/pre-edit-lint-gate-js.sh`

**Step 1: Adapt the Python version**

Copy `pre-edit-lint-gate-python.sh` as a starting point. Change:
- Extension check: `*.js|*.jsx|*.ts|*.tsx`
- Tool detection: `command -v eslint` or `npx --no-install eslint`
- Lint command: `eslint --no-eslintrc --stdin --stdin-filename="$FILE_PATH" < "$TMP"` (pipe content through stdin so eslint doesn't need a file on disk)
- Block detection: `grep -qE "error"` on eslint output

**Step 2: chmod + run tests**

```bash
chmod +x /Users/summerrae/claude_code/claude_flow/hooks/tier2/pre-edit-lint-gate-js.sh
cd /Users/summerrae/claude_code/claude_flow && bats hooks/tier2/tests/pre_edit_lint_gate_js.bats
```
Expected: all tests pass (or skip with "eslint not available").

**Step 3: Register in `hooks/hook-registry.json`**

Same shape as Task 3. `id: "pre-edit-lint-gate-js"`, `stack_tags: ["js+eslint", "ts+eslint"]`, `opt_in: true`.

**Step 4: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add hooks/tier2/pre-edit-lint-gate-js.sh hooks/hook-registry.json
git commit -m "feat(hooks): add blocking pre-edit lint gate for js/ts"
```

---

## Task 6: Add `evidence` + `confidence` fields to memory-entry schema

**Files:**
- Modify: `~/.claude/skills/lint-memory/SKILL.md` (canonical: `/Users/summerrae/claude_code/claude-skills/lint-memory/SKILL.md`)
- Create: `/Users/summerrae/claude_code/claude_flow/docs/conventions/memory-entry-schema.md` (if `docs/conventions/` does not exist, create it)

**Step 1: Read current lint-memory SKILL.md to find the frontmatter validation section**

Run: `grep -n "frontmatter\|description:\|name:" ~/.claude/skills/lint-memory/SKILL.md | head -20`
Expected: lines identifying the section that validates YAML frontmatter keys.

**Step 2: Extend the validator to accept two new optional fields**

Add (as an optional-field rule, not required):

```yaml
# Optional fields — validated only when present:
evidence: [ep-001, lesson-2026-04-12]   # list of IDs or relative links
confidence: 0.9                         # float in [0.0, 1.0]
```

Validation rules (to add to SKILL.md):
- `evidence`: if present, must be a list of strings, each non-empty.
- `confidence`: if present, must be a number in [0.0, 1.0].
- Neither is required. Absence is not a warning.

**Step 3: Write the convention doc**

Content of `docs/conventions/memory-entry-schema.md`:

```markdown
# Memory Entry Schema

## Required frontmatter

- `name`: short identifier
- `description`: one-line purpose
- `type`: one of `user | feedback | project | reference`

## Optional frontmatter (added 2026-04-17)

- `evidence`: list of IDs or paths to the episodes/lessons this entry builds on.
  Use when the entry is derived from specific prior memory; omit otherwise.
- `confidence`: float in [0.0, 1.0].
  - Success-derived lessons: default 0.5 (may be overridden).
  - Failure-derived lessons (gotchas, corrections): default 0.9.
  Rationale: failures carry higher signal than successes (agentic-stack/.agent/harness/hooks/on_failure.py).

## Example

    ---
    name: post_commit_hook_message_conflation
    description: Tier-1 hook swept staged files into its own auto-commit
    type: feedback
    evidence:
      - commit:a1b2c3d
      - ep-2026-04-13-hook-incident
    confidence: 0.95
    ---

    [body]
```

**Step 4: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add docs/conventions/memory-entry-schema.md
git commit -m "docs: add evidence + confidence fields to memory-entry schema"

cd /Users/summerrae/claude_code/claude-skills
git add lint-memory/SKILL.md
git commit -m "feat(lint-memory): validate optional evidence + confidence fields"
```

(Two repos, two commits — lint-memory lives in `claude-skills` per the symlink convention.)

---

## Task 7: Scaffold the Stop-hook untriaged-memory triage

**Files:**
- Create: `hooks/tier2/memory-triage-on-stop.sh`
- Create: `hooks/tier2/memory-triage-on-stop.py` (helper)

**Step 1: Write the shell wrapper**

```bash
#!/usr/bin/env bash
# Trigger: Stop
# Scans memory files modified this session and writes a REVIEW_QUEUE.md listing
# entries that are (a) not linked from MEMORY.md, or (b) missing recommended
# frontmatter fields. Never auto-commits (see: post_commit_hook_message_conflation).
set -uo pipefail

MEMORY_DIR="$HOME/.claude/projects/-Users-summerrae-claude-flow/memory"
[[ ! -d "$MEMORY_DIR" ]] && exit 0

python3 "$(dirname "$0")/memory-triage-on-stop.py" "$MEMORY_DIR"
exit 0  # always succeed; this is advisory
```

**Step 2: Write the Python helper**

```python
#!/usr/bin/env python3
"""Scan MEMORY_DIR for entries not indexed in MEMORY.md; write REVIEW_QUEUE.md.

Mechanical only — no clustering, no subjective promotion decisions.
Writes to $MEMORY_DIR/REVIEW_QUEUE.md. Does NOT modify MEMORY.md or commit.
"""
import sys, pathlib, datetime

memory_dir = pathlib.Path(sys.argv[1])
index = memory_dir / "MEMORY.md"
queue = memory_dir / "REVIEW_QUEUE.md"

if not index.exists():
    sys.exit(0)

indexed = index.read_text()
unindexed = []
for md in sorted(memory_dir.glob("*.md")):
    if md.name in ("MEMORY.md", "REVIEW_QUEUE.md"):
        continue
    if md.name not in indexed:
        unindexed.append(md.name)

if not unindexed:
    queue.write_text(
        f"# Review Queue\n\n_Last scanned: {datetime.datetime.now().isoformat()}_\n\nAll memory files indexed.\n"
    )
    sys.exit(0)

lines = [
    "# Review Queue",
    "",
    f"_Last scanned: {datetime.datetime.now().isoformat()}_",
    "",
    "## Memory files not linked from MEMORY.md",
    "",
]
lines.extend(f"- [ ] `{name}`" for name in unindexed)
lines.append("")
lines.append("_Review each entry; add a one-line pointer to MEMORY.md or delete if stale._")
queue.write_text("\n".join(lines))
```

**Step 3: chmod + smoke-test**

```bash
chmod +x /Users/summerrae/claude_code/claude_flow/hooks/tier2/memory-triage-on-stop.sh
bash /Users/summerrae/claude_code/claude_flow/hooks/tier2/memory-triage-on-stop.sh
cat ~/.claude/projects/-Users-summerrae-claude-flow/memory/REVIEW_QUEUE.md | head
```
Expected: a REVIEW_QUEUE.md file exists; either empty-state message or a checklist of un-indexed files.

**Step 4: Register in `hooks/hook-registry.json`**

```json
,
{
  "id": "memory-triage-on-stop",
  "tier": 2,
  "trigger": "Stop",
  "matcher": ["*"],
  "script": "hooks/tier2/memory-triage-on-stop.sh",
  "opt_in": true,
  "description": "On session Stop, writes REVIEW_QUEUE.md listing memory files not indexed in MEMORY.md. Advisory only — never auto-commits."
}
```

**Step 5: Validate registry JSON**

Run: `python3 -c "import json; json.load(open('hooks/hook-registry.json'))"`
Expected: exit 0.

**Step 6: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add hooks/tier2/memory-triage-on-stop.sh hooks/tier2/memory-triage-on-stop.py hooks/hook-registry.json
git commit -m "feat(hooks): add Stop-hook memory triage (scaffold, advisory-only)"
```

---

## Task 8: Cross-link the new memory fields into `skills/lint-memory`

**Files:**
- Modify: `~/.claude/skills/lint-memory/SKILL.md` (canonical: `/Users/summerrae/claude_code/claude-skills/lint-memory/SKILL.md`)

**Step 1: Add a `## Related` footer pointing to the convention doc**

Append:

```markdown
## Related

- [Memory Entry Schema](https://github.com/summerela/claude_flow/blob/main/docs/conventions/memory-entry-schema.md) — canonical definition of optional `evidence` + `confidence` fields.
```

**Step 2: Commit**

```bash
cd /Users/summerrae/claude_code/claude-skills
git add lint-memory/SKILL.md
git commit -m "docs(lint-memory): link to canonical memory-entry-schema"
```

---

## Task 9: Write a single-entry MEMORY pointer for the new plan

**Files:**
- Create: `~/.claude/projects/-Users-summerrae-claude-flow/memory/hook_improvements_2026_04_17.md`
- Modify: `~/.claude/projects/-Users-summerrae-claude-flow/memory/MEMORY.md`

**Step 1: Write the memory file**

```markdown
---
name: hook_improvements_2026_04_17
description: Pre-edit lint gate + memory schema bump + Stop-hook triage scaffold shipped 2026-04-17
type: project
evidence:
  - docs/plans/2026-04-17-hook-improvements.md
confidence: 0.7
---

Plan shipped from Copilot-CLI-hooks video + agentic-stack review. See plan doc for scope + ruled-out.

**Why:** Pre-edit lint gate is the "force fix before move-on" pattern the video identifies;
memory schema bump enables evidence tracking; Stop-hook triage closes the loop for new memory files.

**How to apply:** If touching hooks/hook-registry.json, check the tier-2 opt-in pattern here.
If touching MEMORY.md entries, remember evidence + confidence are now optional-validated fields.
```

**Step 2: Add one-line pointer to MEMORY.md**

Append:
```
- [Hook Improvements 2026-04-17](hook_improvements_2026_04_17.md) — pre-edit lint gate, memory schema bump, Stop-hook triage scaffold
```

**Step 3: Commit (in plans repo only; memory is untracked)**

```bash
cd /Users/summerrae/claude_code/claude_flow
# memory dir is untracked — no commit needed
```

---

## Verification

After all tasks complete:

1. `cd /Users/summerrae/claude_code/claude_flow && bats hooks/tier2/tests/` — all tests pass or skip with clear reason.
2. `python3 -c "import json; json.load(open('hooks/hook-registry.json'))"` — registry is valid.
3. `bash hooks/tier2/memory-triage-on-stop.sh && cat ~/.claude/projects/-Users-summerrae-claude-flow/memory/REVIEW_QUEUE.md` — review queue file is written.
4. `./scripts/quick_ci.sh` — passes (per ship gate).
5. Manually enable `pre-edit-lint-gate-python` in local settings by copying the registry entry into `.claude/settings.json`; attempt an `Edit` that introduces a ruff error — the edit is blocked.

## Execution Handoff

Plan complete and saved to [docs/plans/2026-04-17-hook-improvements.md](docs/plans/2026-04-17-hook-improvements.md). Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Parallel Session (separate)** — Open a new session with `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
