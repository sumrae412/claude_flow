# Skills Consolidation Plan

## Context

Skills currently live in **three locations** and have drifted:

| Location | Count | Git-tracked | Role |
|---|---|---|---|
| `/Users/summerrae/claude_code/claude-skills/` | 40 | yes (origin `claude-skills.git`) | Intended single source of truth |
| `/Users/summerrae/claude_code/claude_flow/skills/` | 25 | yes (origin `claude_flow.git`) | Duplicates + orchestrator-private skills |
| `/Users/summerrae/.claude/skills/` | 40 | no | Runtime install (copied by `install.sh`) |

**Overlap:** 10 skills are triplicated. 15 skills live only in `claude_flow` (orchestrator core: `claude-flow`, `bug-fix`, `writing-plans`, `executing-plans`, `subagent-driven-development`, `investigator`, `research`, `production-readiness-check`, `prompt-optimization`, `hook-doctor`, `lint-memory`, `session-handoff`, `test-driven-development`, `verification-before-completion`, `excalidraw-canvas`).

**Drift on 10 duplicates** (per Explore agent):
- Identical: `fetch-api-docs`, `finishing-a-development-branch`
- Substantive drift: `coding-best-practices`, `memory-injection`, `session-learnings`, `defensive-backend-flows`, `defensive-ui-flows`, `debate-team`, `smart-exploration`
- Minor drift: `shipping-workflow`

**User intent:** `claude-skills` is the canonical repo. `claude_flow` should pull from it; skills should live in only one place.

**Problem this solves:** Eliminates "which copy do I edit?" confusion, stops edits to one copy from being lost when another copy is installed, and makes skill updates propagate through a single pipeline (`claude-skills` → install).

---

## Approach (confirmed with user)

**Mechanism:** Symlink `~/.claude/skills/` → `~/claude_code/claude-skills/`. Skill edits in the canonical repo go live immediately; no re-install after every edit.

**Scope:** All 4 phases in this session.

**Why symlink over submodule or sibling-checkout-with-install:**
- Skills are edited frequently; the copy-on-install model means every edit needs a reinstall to be active. Symlinks eliminate that step entirely.
- `~/.claude/skills/` path is stable (Claude Code runtime convention).
- Submodule adds git ceremony without payoff — you don't need per-release version pinning for personal tooling.

**Downstream implications:**
- `claude_flow/skills/` directory is deleted outright.
- `claude_flow/install.sh` no longer copies skill files; instead it ensures the symlink exists (create if missing, error if `~/claude_code/claude-skills/` absent).
- `claude_flow/scripts/pattern-detector.py` resolves skill paths via `~/.claude/skills/` (which IS claude-skills via the symlink). Portable across install states.

### Execution in 4 phases

**Phase A — Merge the 10 duplicates into `claude-skills`** (most-current content wins per diff):

| Skill | Winner | Source path |
|---|---|---|
| `coding-best-practices` | claude_flow | `claude_flow/skills/coding-best-practices/` |
| `memory-injection` | claude_flow (= .claude) | `claude_flow/skills/memory-injection/` |
| `session-learnings` | claude_flow (+ my gitignore gotcha edit) | `claude_flow/skills/session-learnings/` |
| `defensive-backend-flows` | ~/.claude | `~/.claude/skills/defensive-backend-flows/` |
| `defensive-ui-flows` | claude-skills (longest) | **already in place** |
| `debate-team` | .claude (= claude_flow) | `claude_flow/skills/debate-team/` |
| `smart-exploration` | claude_flow (= .claude) | `claude_flow/skills/smart-exploration/` |
| `shipping-workflow` | merge three-way (I'll describe specifically) | see below |
| `fetch-api-docs` | identical — no action | — |
| `finishing-a-development-branch` | identical — no action | — |

**`shipping-workflow` three-way merge** (content-by-content): take `~/.claude` base (has Stage 4.5 auto-merge logic I invoked earlier), add `claude_flow`'s direct-push-to-main exception (my edit from this session), keep `claude-skills` wording where it's been genericized for portability. Write result to `claude-skills/shipping-workflow/SKILL.md`.

Commit in `claude-skills`: "feat: absorb drifted updates from claude_flow + .claude installs".

**Phase B — Move 15 orchestrator-only skills into `claude-skills`**:

`git mv` each from `claude_flow/skills/<name>/` to `claude-skills/<name>/`. Two commits:
1. In `claude_flow`: delete 15 skill dirs (history preserved via the mv step).
2. In `claude-skills`: add 15 new top-level skill dirs.

Before moving, verify none of them reference each other by absolute path that'd break at the new location. (Earlier Explore found one relative cross-skill link in `defensive-ui-flows` pointing at `claude-flow/contracts/mockup-manifest.schema.md` — since both skills move to the same flat layout, the relative path still works.)

**Phase C — Rewire `claude_flow`**:

1. Delete the now-empty `claude_flow/skills/` directory (via `git rm -r skills/`).
2. Edit `claude_flow/install.sh` lines 242-259 — replace the "copy skills" block with a "ensure symlink" block:
   - If `~/.claude/skills` doesn't exist → create symlink to `~/claude_code/claude-skills/`.
   - If `~/.claude/skills` is a regular dir and differs from claude-skills → back it up to `~/.claude/skills.bak.<timestamp>/`, then replace with symlink.
   - If `~/claude_code/claude-skills/` absent → error with clone command.
3. Edit `claude_flow/scripts/pattern-detector.py` — change hardcoded paths from `skills/<name>/SKILL.md` to `~/.claude/skills/<name>/SKILL.md` (expanded via `pathlib.Path.home()`). This works whether the skill is directly in `~/.claude/skills/` or via symlink.
4. Grep for any other `skills/<name>` references in `claude_flow` — update to use the `~/.claude/skills/` convention.
5. Update `claude_flow/README.md` — prerequisite: clone `claude-skills` sibling repo before running `install.sh`.

**Phase D — Create the symlink, verify runtime**:

1. Back up current `~/.claude/skills/` → `~/.claude/skills.bak.<YYYYMMDD>/`.
2. Create symlink: `ln -s /Users/summerrae/claude_code/claude-skills /Users/summerrae/.claude/skills`.
3. Verify: `ls -la ~/.claude/skills/` should show the symlink; `ls ~/.claude/skills/claude-flow/SKILL.md` should resolve.
4. Run `python3 -m pytest scripts/test_*.py -q` in claude_flow — expect 67/67.
5. Optional: after confirming nothing broke, `rm -rf ~/.claude/skills.bak.*`.

---

## Files that change

**In `claude-skills/` (new commits here):**
- 8 drifted `SKILL.md` files (and any `reference.md` siblings) overwritten with merged content
- 15 new top-level skill dirs (moved in from claude_flow)

**In `claude_flow/`:**
- `install.sh` — lines 242-259 edited to point at sibling `claude-skills`
- `scripts/pattern-detector.py` — hardcoded paths updated
- `skills/` — entire directory deleted
- `README.md` — prerequisite note added: "Requires `claude-skills` cloned as sibling directory"

**In `~/.claude/skills/`:**
- Fully replaced by re-running install.sh.

---

## Verification

1. `diff -r /Users/summerrae/claude_code/claude-skills/ /Users/summerrae/.claude/skills/ | head` — should be empty after Phase D, modulo `.git/` noise.
2. `ls /Users/summerrae/claude_code/claude_flow/skills/` — should not exist.
3. `cd /Users/summerrae/claude_code/claude_flow && python3 -m pytest scripts/test_*.py -q` — still 67/67 pass (pattern-detector tests will exercise the new path logic).
4. Run claude-flow itself on a trivial task to confirm skill loading still works. (Quick check: `ls ~/.claude/skills/claude-flow/SKILL.md`.)
5. From the shell, verify `install.sh` prints a clear error if run without the sibling `claude-skills` present.

---

## Risk + rollback

- **Risk:** `pattern-detector.py` callers fail silently if the new path resolution is wrong. Mitigation: run its existing tests (`test_pattern_detector.py`) after Phase C.
- **Risk:** A third-party who installs `claude_flow` without `claude-skills` gets a cryptic failure. Mitigation: `install.sh` probe + friendly message, README prerequisite note.
- **Rollback:** Every phase is a separate commit. Revert-by-commit restores the prior state.

---

## Commit strategy

**`claude-skills` commits (canonical):**
1. Phase A: "feat: absorb drifted updates from claude_flow + .claude installs (merges 10 duplicate skills)"
2. Phase B: "feat: adopt 15 claude_flow orchestrator skills (single source of truth)"

**`claude_flow` commits:**
1. Phase B mirror: "refactor: skills moved to claude-skills repo (deletions only)"
2. Phase C: "refactor: install.sh symlinks ~/.claude/skills/ to claude-skills; drop copy-based install"

All 4 commits use conventional-commit prefixes. Direct-push-to-main per the personal-tooling exception (confirmed last session).

## Clarifications baked in

- **Symlink target:** `/Users/summerrae/claude_code/claude-skills` → `/Users/summerrae/.claude/skills` (absolute path for portability).
- **Backup of current `~/.claude/skills/`:** renamed to `~/.claude/skills.bak.20260416/` before symlink creation; removed after verification.
- **`shipping-workflow` three-way merge rule:** base = `~/.claude/` version (richest Stage 4.5 logic); overlay = my session edit for direct-push exception; apply claude-skills' genericization wording only where it doesn't lose functionality.
- **No PR workflow for this change** — personal-tooling repo, direct-push authorized.
