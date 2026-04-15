# Excalidraw Canvas + Curmudgeon Reviewer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add two additive features to claude-flow — (A) an opt-in Excalidraw canvas for visual UI-mockup round-trip in Phase 4, and (B) a non-Anthropic "curmudgeon" reviewer as a Tier 2 entry in the Phase 6 cascade.

**Architecture:** Two independent deliverables. Curmudgeon ships first (smaller, higher-confidence, unblocks `multi_model_deferred` MEMORY note). Excalidraw canvas ships second (larger, opt-in only). Both follow existing claude-flow patterns — declarative registry, progressive-disclosure skill layout, opt-in flags, graceful degradation when tools are missing.

**Tech Stack:** Bash scripts (curmudgeon runner, excalidraw opener), Markdown skill files, JSON registry edits, shell tests. External: `codex` CLI (optional — graceful skip if absent), VS Code Excalidraw extension (optional — fallback to excalidraw.com).

**Design doc:** `docs/plans/2026-04-15-excalidraw-canvas-curmudgeon-design.md`

**Ruled Out:**
- Local dev server / file watcher — VS Code extension already provides round-trip; maintenance debt
- Phase 3 mockups — requirements are text-first; visual drift catches plan issues, not requirement issues
- Replacing CodeRabbit Tier 1 with curmudgeon — CodeRabbit is dialed in; curmudgeon complements
- OpenAI API billing path — Codex CLI uses existing ChatGPT auth; avoids new billing surface
- Rewriting `reviewer-registry.json` — one-line addition only
- New `$mockups` contract schema — path reference sufficient
- Always-on visual checkpoint — breaks autonomous path for backend-only features
- Replacing existing `plancraft_review.py` (OpenAI API path) — kept for `debate-team` use; curmudgeon is a separate CLI-based path

---

## Pre-flight

**Branch:** Work on a feature branch `feat/excalidraw-curmudgeon` (not main). User has 2 uncommitted files on main (`phase-2-exploration.md`, `phase-4-architecture.md`) — those are unrelated; stash or commit them before branching so they don't bleed into this work.

**Pre-flight step 0:**
```bash
cd /Users/summerrae/claude_flow
git status --short
# If phase-2-exploration.md or phase-4-architecture.md still modified:
#   Ask user whether those changes should be committed or stashed before proceeding.
git checkout -b feat/excalidraw-curmudgeon
```

**Install hints (for user, not blocking):**
- Codex CLI: `npm i -g @openai/codex` (or per OpenAI docs). Without it, curmudgeon logs a warning and skips — it is NOT a failure.
- VS Code Excalidraw extension: `code --install-extension pomdtr.excalidraw-editor`. Without it, `open_excalidraw.sh` falls back to excalidraw.com.

---

## Part I — Curmudgeon Reviewer (smaller, ship first)

### Task 1: Curmudgeon runner script (TDD)
**Type:** value_unit
**Depends on:** none

**Files:**
- Create: `scripts/curmudgeon_review.sh`
- Create: `tests/test_curmudgeon_review.sh`
- Create: `tests/fixtures/curmudgeon/sample-diff.patch`
- Create: `tests/fixtures/curmudgeon/mock-codex` (mock CLI that prints canned JSON to stdout)

**Step 1: Write the failing test**

`tests/test_curmudgeon_review.sh`:
```bash
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
```

`tests/fixtures/curmudgeon/sample-diff.patch`:
```
diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1,3 +1,5 @@
 def foo():
+    try:
+        risky()
+    except:
+        pass
     return 1
```

`tests/fixtures/curmudgeon/mock-codex`:
```bash
#!/usr/bin/env bash
# Mock codex CLI: prints canned curmudgeon JSON regardless of input.
cat <<'JSON'
{"findings":[{"file":"example.py","line":3,"severity":"MEDIUM","title":"Bare except swallows all exceptions","rationale":"Catches BaseException including KeyboardInterrupt; obscures real failures."}]}
JSON
```

**Step 2: Run test to verify it fails**

```bash
chmod +x tests/test_curmudgeon_review.sh
tests/test_curmudgeon_review.sh
```
Expected: FAIL with "No such file or directory: scripts/curmudgeon_review.sh"

**Step 3: Implement the script**

`scripts/curmudgeon_review.sh`:
```bash
#!/usr/bin/env bash
# Curmudgeon reviewer: shells out to local `codex` CLI for a
# non-Anthropic second-opinion review. No API key required — uses
# the user's existing ChatGPT auth via the Codex CLI.
#
# Usage: curmudgeon_review.sh <path-to-diff-file>
# Output: JSON on stdout with {"reviewer":"curmudgeon","findings":[...]}
#         On missing CLI: logs "SKIP" to stderr and exits 0.
set -euo pipefail

DIFF_FILE="${1:?usage: curmudgeon_review.sh <diff-file>}"

if ! command -v codex >/dev/null 2>&1; then
    echo "curmudgeon: codex CLI not found on PATH — SKIPPING review (install: npm i -g @openai/codex)" >&2
    echo '{"reviewer":"curmudgeon","findings":[],"skipped":true,"reason":"codex CLI not installed"}'
    exit 0
fi

PERSONA="You are a curmudgeonly staff engineer reviewing a PR. You have seen every antipattern and you are tired. Focus on: code smells, inconsistencies with existing patterns, places where the diff works but is the wrong abstraction, tests that prove nothing, and suspicious silent-failure modes. Be specific; cite file:line. Do not praise. Do not repeat findings that a conventional linter or CodeRabbit would catch. Output ONLY a single JSON object: {\"findings\":[{\"file\":str,\"line\":int,\"severity\":\"HIGH|MEDIUM|LOW\",\"title\":str,\"rationale\":str}]}."

RAW=$(codex exec --quiet --output-format json "$PERSONA

---
Diff to review:
$(cat "$DIFF_FILE")" 2>/dev/null || echo '{"findings":[]}')

# Validate and normalize output. Malformed → empty findings, not failure.
python3 - <<PY
import json, sys
raw = """$RAW"""
try:
    d = json.loads(raw)
    findings = d.get("findings", []) if isinstance(d, dict) else []
    if not isinstance(findings, list): findings = []
except Exception:
    findings = []
print(json.dumps({"reviewer": "curmudgeon", "findings": findings}))
PY
```

Note: the exact `codex exec` flags depend on the Codex CLI version. If the actual CLI uses different flags (e.g. `--json` instead of `--output-format json`), update them after installing and running `codex --help`. The script structure otherwise stays the same.

**Step 4: Run test to verify it passes**

```bash
chmod +x scripts/curmudgeon_review.sh
tests/test_curmudgeon_review.sh
```
Expected: `OK`

**Step 5: Commit**

```bash
git add scripts/curmudgeon_review.sh tests/test_curmudgeon_review.sh tests/fixtures/curmudgeon/
git commit -m "feat: curmudgeon reviewer runner script with Codex CLI"
```

---

### Task 2: Register curmudgeon in reviewer-registry.json
**Type:** value_unit
**Depends on:** T1 (data — script must exist before registry points at it)

**Files:**
- Modify: `reviewer-registry.json` (add one entry)
- Modify: `tests/` — add/extend a registry-schema test

**Step 1: Write the failing test**

Add to an existing registry test (or create `tests/test_reviewer_registry.py`):
```python
import json, pathlib

def test_curmudgeon_registered():
    r = json.loads(pathlib.Path("reviewer-registry.json").read_text())
    ids = {x["id"] for x in r["reviewers"]}
    assert "curmudgeon-review" in ids, "curmudgeon entry missing"
    curm = next(x for x in r["reviewers"] if x["id"] == "curmudgeon-review")
    assert curm["tier"] == "always"
    assert curm["cascade_tier"] == 2
    assert curm.get("runner") == "codex-cli"
```

**Step 2: Run and verify failure**
```bash
pytest tests/test_reviewer_registry.py::test_curmudgeon_registered -v
```
Expected: FAIL with "curmudgeon entry missing"

**Step 3: Add the registry entry**

Add to `reviewer-registry.json` `reviewers` array (at the end, before closing bracket):
```json
{
  "id": "curmudgeon-review",
  "tier": "always",
  "cascade_tier": 2,
  "runner": "codex-cli",
  "runner_script": "scripts/curmudgeon_review.sh",
  "model": "gpt-5-codex",
  "description": "Non-Anthropic second opinion — code smells, wrong abstractions, lazy tests"
}
```

**Step 4: Verify pass**
```bash
pytest tests/test_reviewer_registry.py::test_curmudgeon_registered -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add reviewer-registry.json tests/test_reviewer_registry.py
git commit -m "feat: register curmudgeon-review in reviewer-registry"
```

---

### Task 3: Wire curmudgeon into Phase 6 dispatch prose
**Type:** value_unit
**Depends on:** T2 (knowledge — registry entry must exist)

**Files:**
- Modify: `skills/claude-flow/phases/phase-6-quality.md`

**Step 1:** Read `phase-6-quality.md` and locate the reviewer-dispatch section (look for where other Tier 2 reviewers like `silent-failure-hunter`, `security-reviewer` are referenced).

**Step 2:** Add a paragraph/bullet describing curmudgeon — its persona, its runner script, and its graceful-skip behavior. Reference `scripts/curmudgeon_review.sh`. Match the existing prose style for other reviewers.

**Step 3:** Verify the prose is consistent with the registry entry — no claims about behavior the script doesn't implement.

**Step 4: Commit**
```bash
git add skills/claude-flow/phases/phase-6-quality.md
git commit -m "docs: describe curmudgeon reviewer in Phase 6 dispatch"
```

---

### Task 4: Verify end-to-end — early-exit respect
**Type:** value_unit
**Depends on:** T2

Goal: confirm curmudgeon is NOT dispatched on a clean diff (CodeRabbit finds no HIGH+). This preserves MEMORY `early_exit_cascades`.

**Files:**
- Modify: `scripts/select_reviewers.py` (if reviewer selection lives there — grep to confirm)
- Modify: tests for reviewer selection

**Step 1:** `grep -rn "cascade_tier" skills/ scripts/` to find where Tier 2 is gated on Tier 1 findings.

**Step 2:** Write a test that mocks CodeRabbit output as empty → assert the selected reviewer list excludes all Tier 2 entries including `curmudgeon-review`.

**Step 3:** Run → verify PASS (no code change should be needed if early-exit logic is generic; if curmudgeon requires a special case, that is a red flag — fix by making the gating generic).

**Step 4: Commit**
```bash
git add -u  # only if changes were needed
git commit -m "test: verify curmudgeon respects Tier 1 early-exit"
```

---

## Part II — Excalidraw Canvas (opt-in)

### Task 5: Excalidraw opener script (TDD)
**Type:** value_unit
**Depends on:** none (parallelizable with Part I)

**Files:**
- Create: `scripts/open_excalidraw.sh`
- Create: `tests/test_open_excalidraw.sh`
- Create: `tests/fixtures/excalidraw/simple.excalidraw`

**Step 1: Write the failing test**

`tests/fixtures/excalidraw/simple.excalidraw` — minimal valid excalidraw file:
```json
{"type":"excalidraw","version":2,"source":"https://excalidraw.com","elements":[{"type":"rectangle","x":0,"y":0,"width":100,"height":50,"id":"a","strokeColor":"#000","backgroundColor":"transparent","fillStyle":"solid"}],"appState":{"viewBackgroundColor":"#fff"},"files":{}}
```

`tests/test_open_excalidraw.sh`:
```bash
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
```

**Step 2: Run to verify failure** → "No such file: scripts/open_excalidraw.sh"

**Step 3: Implement**

`scripts/open_excalidraw.sh`:
```bash
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
```

**Step 4: Verify pass**
```bash
chmod +x scripts/open_excalidraw.sh tests/test_open_excalidraw.sh
tests/test_open_excalidraw.sh
```
Expected: `OK`

**Step 5: Commit**
```bash
git add scripts/open_excalidraw.sh tests/test_open_excalidraw.sh tests/fixtures/excalidraw/
git commit -m "feat: excalidraw opener script with VS Code + excalidraw.com fallback"
```

---

### Task 6: excalidraw-canvas skill scaffold
**Type:** shared_prerequisite (the schema + prompts are used by T7 and T8)
**Depends on:** none

**Files:**
- Create: `skills/excalidraw-canvas/SKILL.md`
- Create: `skills/excalidraw-canvas/references/excalidraw-schema.md`
- Create: `skills/excalidraw-canvas/references/mockup-prompts.md`

**Step 1:** Create `skills/excalidraw-canvas/SKILL.md` — thin router (≤1.5K tokens). Frontmatter:
```yaml
---
name: excalidraw-canvas
description: Use when user wants visual UI mockups or architecture diagrams with round-trip editing. Generates .excalidraw files Claude can write and the user can edit in VS Code or excalidraw.com. Invoked standalone via /excalidraw-canvas or by claude-flow Phase 4 when --visual flag is set.
---
```

Body: when to use, one-way vs round-trip, file locations (`docs/design/<feature>/`), how to trigger the opener script, lazy-loaded references:
- `references/excalidraw-schema.md` — load when writing `.excalidraw` JSON
- `references/mockup-prompts.md` — load when generating mockups from `$plan`

**Step 2:** Create `references/excalidraw-schema.md` — compact subset schema (only: rectangle, ellipse, text, arrow, line, groupIds, strokeColor, backgroundColor). Include one valid minimal-file example and one richer mockup example (login screen with 3-4 shapes).

**Step 3:** Create `references/mockup-prompts.md` — prompts for (a) generating initial mockups from `$plan` + `$requirements`, (b) detecting drift between the generated mockup and the user-edited version, (c) generating `$plan` delta when drift found.

**Step 4:** Verify: all three files exist, SKILL.md frontmatter parses (run `python3 -c "import yaml; yaml.safe_load(open('skills/excalidraw-canvas/SKILL.md').read().split('---')[1])"`).

**Step 5: Commit**
```bash
git add skills/excalidraw-canvas/
git commit -m "feat: excalidraw-canvas skill scaffold (router + schema + prompts)"
```

---

### Task 7: Integrate `--visual` into Phase 4 architecture
**Type:** value_unit
**Depends on:** T5 (opener script), T6 (skill scaffold)

**Files:**
- Modify: `skills/claude-flow/phases/phase-4-architecture.md`
- Modify: `skills/claude-flow/SKILL.md` (document `--visual` flag)

**Warning:** `phase-4-architecture.md` has uncommitted changes on main. Confirm those were either committed or stashed in pre-flight. This task's edits must merge with whatever changes landed there, not overwrite them.

**Step 1:** Read `phase-4-architecture.md` end-to-end to understand current Phase 4 structure.

**Step 2:** Add a new **guarded** step near the end of Phase 4 (after `$plan` is drafted, before handoff to Phase 5):
- Guard: only run if `--visual` flag set OR task description contains "UI mockup" / "visual review" signals
- Substeps:
  1. Load `skills/excalidraw-canvas` skill
  2. Generate `.excalidraw` mockup(s) to `docs/design/<feature>/mockups/` from `$plan` + `$requirements`
  3. Print `scripts/open_excalidraw.sh <file>` command
  4. Pause: prompt user to edit and reply "continue"
  5. Re-read edited files; if drift detected, update `$plan` delta inline
  6. Always emit `docs/design/<feature>/architecture.excalidraw` (one-way) if `$plan` has a diagrams section, regardless of flag

**Step 3:** Update `skills/claude-flow/SKILL.md` — document `--visual` in the flag reference table.

**Step 4:** Verify phase-4 file still parses as valid markdown and the guarded step is cleanly additive (not rewriting existing steps).

**Step 5: Commit**
```bash
git add skills/claude-flow/phases/phase-4-architecture.md skills/claude-flow/SKILL.md
git commit -m "feat: Phase 4 --visual flag emits excalidraw mockups"
```

---

### Task 8: Phase 5 reads mockups for UI tasks
**Type:** value_unit
**Depends on:** T7 (knowledge — Phase 4 must emit files)

**Files:**
- Modify: `skills/claude-flow/phases/phase-5-implementation.md`

**Step 1:** Read current Phase 5 step that lists context sources for implementer subagents.

**Step 2:** Add instruction: "For tasks touching UI files (patterns: `*.tsx`, `*.jsx`, `*.html`, `*.css`, `app/templates/*`), if `docs/design/<feature>/mockups/*.excalidraw` exists, include those files in the implementer's context alongside `$plan`."

**Step 3:** Verify instruction matches file-pattern conventions used elsewhere in claude-flow.

**Step 4: Commit**
```bash
git add skills/claude-flow/phases/phase-5-implementation.md
git commit -m "feat: Phase 5 includes mockup files as context for UI tasks"
```

---

### Task 9: Surface new skill in project-level CLAUDE.md
**Type:** value_unit
**Depends on:** T6

**Files:**
- Modify: `CLAUDE.md` (user's global, at `~/.claude/CLAUDE.md`) OR project-level if this repo has its own — check first

**Step 1:** Check whether claude_flow has a local `CLAUDE.md` (`ls CLAUDE.md` at repo root). If yes, edit that. If no, defer — user can add to their global `CLAUDE.md` manually; do not edit `~/.claude/CLAUDE.md` from this plan (out of repo scope).

**Step 2:** If local `CLAUDE.md` exists, add to the Domain Skills table:
| Task | Skill |
| UI mockups, visual diagrams | `/excalidraw-canvas` |

**Step 3: Commit** (only if local `CLAUDE.md` was edited)
```bash
git add CLAUDE.md
git commit -m "docs: reference excalidraw-canvas skill in CLAUDE.md"
```

---

## Part III — Finalization

### Task 10: Run full test suite + quick_ci.sh gate
**Type:** value_unit
**Depends on:** T1–T9

**Step 1:** Run all new tests:
```bash
pytest tests/test_reviewer_registry.py -v
tests/test_curmudgeon_review.sh
tests/test_open_excalidraw.sh
```
Expected: all PASS.

**Step 2:** Run the repo-level CI gate:
```bash
./scripts/quick_ci.sh
```
Expected: PASS. If it fails on pre-existing issues unrelated to this branch, follow CLAUDE.md boundary #7 (fix-what-you-find) or log deferred items with justification.

**Step 3:** If anything fails, fix it before proceeding to PR.

**Step 4:** No commit — this is a verification task.

---

### Task 11: PR prep
**Type:** value_unit
**Depends on:** T10

**Step 1:** `git log main..HEAD --oneline` — confirm commits tell a coherent story.

**Step 2:** Push branch: `git push -u origin feat/excalidraw-curmudgeon`.

**Step 3:** Open PR referencing the design doc:
```bash
gh pr create --title "feat: excalidraw canvas + curmudgeon reviewer" --body "$(cat <<'EOF'
## Summary
- Add opt-in Excalidraw canvas for UI mockup round-trip in Phase 4 (`--visual` flag)
- Add non-Anthropic "curmudgeon" reviewer as Tier 2 entry in reviewer-registry.json
- Both features gracefully skip when their external tools (`codex` CLI, VS Code Excalidraw extension) are missing

Inspired by CJ Hess's How-I-AI episode; uses Excalidraw instead of Flowy.

Design: `docs/plans/2026-04-15-excalidraw-canvas-curmudgeon-design.md`

## Test plan
- [ ] `tests/test_curmudgeon_review.sh` passes (mock CLI + missing CLI both green)
- [ ] `tests/test_open_excalidraw.sh` passes (VS Code + fallback paths)
- [ ] `pytest tests/test_reviewer_registry.py` passes (curmudgeon entry present, Tier 2)
- [ ] `./scripts/quick_ci.sh` passes
- [ ] Manual: `/claude-flow --visual "add demo page"` emits `.excalidraw` files and pauses
- [ ] Manual: Phase 6 on a dirty diff dispatches curmudgeon alongside other Tier 2 reviewers
- [ ] Manual: Phase 6 on a clean diff does NOT dispatch curmudgeon (early-exit preserved)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 4:** Link the PR to the design doc and the `multi_model_deferred` MEMORY entry it resolves.

---

## Task Graph (parallelizable opportunities)

```
Part I (Curmudgeon):    T1 → T2 → T3, T4  (T3 and T4 parallelizable after T2)
Part II (Excalidraw):   T5, T6  (parallel)  → T7 → T8
                                              → T9 (parallel with T8)
Finalization:           T10 → T11
```

Parts I and II are fully parallelizable — no dependencies between them. If using subagent-driven development, dispatch T1+T5 concurrently, T2+T6 concurrently, etc.

---

## Execution Handoff

**Plan complete and saved to `docs/plans/2026-04-15-excalidraw-canvas-curmudgeon-plan.md`. Two execution options:**

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for this plan since Parts I and II parallelize cleanly (dispatch 2 at a time).

**2. Parallel Session (separate)** — Open a new session in a worktree and use `superpowers:executing-plans` for batched checkpoint-style execution. Better if you want to keep this session's context small.

**Which approach?**
