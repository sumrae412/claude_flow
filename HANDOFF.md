# Handoff: Adversarial Evaluator Plan Execution

## Status (2026-04-16, post-execution)

Plan executed and shipped. The execution surfaced one structural surprise that's now resolved:

- While the worktree was active, `claude_flow/main` accepted commit `aed5f39` ("skills moved to claude-skills repo (single source of truth)"). The plan's "Dual-location skills" pattern (item 3 below) is **obsolete** — skills now live in the standalone `claude-skills` repo, with `~/.claude/skills` symlinked there. The worktree's `skills/claude-flow/*` modifications could not land in this repo as-is.
- Resolution: the skill-side files (persona + 3 phase/ref docs) shipped via a companion PR in `claude-skills` — **PR #15 in claude-skills**. This PR (claude_flow #38) carries only the data + script + test side: `reviewer-registry.json`, `scripts/aggregate_reviewer_findings.py`, `tests/`, fixture, `Makefile`.
- Cross-repo path resolution: the registry entry uses `persona_file` + new `persona_file_root` (`~/.claude/skills`) so the dispatcher resolves the path under the claude-skills tree. The live test mirrors this resolution.

The narrative below is preserved for archival. Items 1 and 2 are still accurate; item 3 is historical.

## Start here

Open a new Claude session with cwd = this worktree, then invoke `superpowers:executing-plans` and point it at:

    docs/plans/2026-04-15-adversarial-evaluator-plan.md

## Repo state (verified 2026-04-16)

- **Worktree:** `/Users/summerrae/claude_code/claude_flow/.worktrees/adversarial-evaluator`
- **Branch:** `feat/adversarial-evaluator`, based on `main` @ `eb43c33`
- **Baseline tests:** `pytest tests/test_reviewer_registry.py -q` → 3 passed
- **Main origin:** pushed through `eb43c33` before branching. No merge debt.

## Known repo quirks (hit during setup — don't relearn them)

1. **Stale staged index from prior sessions.** There is NO pre-commit hook on this repo (I verified: no `.pre-commit-config.yaml`, no `.git/hooks/pre-commit`, no `core.hooksPath`). The footgun is plain git semantics: prior sessions can leave changes in the index unstaged-but-committable, and a subsequent `git add <new-file>` APPENDS to that stale set. `git commit` then ships everything staged, not just what you just added. Mitigation (from MEMORY `two_clones_same_repo.md`):
   - Before every commit, run `git diff --cached --stat` and verify ONLY the files you meant to commit are listed.
   - If the staged set is wider than intended: `git restore --staged <unrelated-paths>` or `git reset HEAD` first.
   - Worktree isolation reduces risk — this worktree's index starts clean, so the failure mode is less likely here than on main. Still, run the `--cached --stat` check before every commit as muscle memory.

2. **Main has 5 unstaged files** that did NOT come along to this worktree (worktree = clean HEAD checkout):
   - `README.md`, `install.sh`, `scripts/pattern-detector.py`, `tests/skills/test_research_skill.sh`, `tests/test_reviewer_registry.py`
   Those are pre-existing WIP on main. Do not touch them from this branch.

3. **Dual-location skills** per CLAUDE.md: every skill file the plan modifies lives in BOTH
   - `~/.claude/skills/claude-flow/` (runtime plugin cache)
   - `skills/claude-flow/` (this repo)
   Each task's Step "Sync cache → repo" (or vice-versa) is load-bearing. Don't skip it.

## Plan summary (5 tasks, TDD throughout)

1. **T1** (`shared_prerequisite`): Write `scripts/adversarial_breaker_persona.txt` + extend `references/reviewer-registry-schema.md`.
2. **T2** (`value_unit`, depends T1): Register `adversarial-breaker` in `reviewer-registry.json`; first test — schema assertions.
3. **T3** (depends T2): Create `scripts/aggregate_reviewer_findings.py` + update `phases/phase-6-quality.md`; second test — sub-threshold → blocking finding.
4. **T4** (depends T3): Update `phases/phase-5-implementation.md` retry ladder to pull adversarial blockers into iter-N+1 prompts.
5. **T5** (depends T1–T4): Golden fixture — planted race-condition diff; recorded LLM response for CI determinism.

Full details + exact code in `docs/plans/2026-04-15-adversarial-evaluator-plan.md`. The plan's "Ruled Out" section documents why we didn't port Archon's full Generator/Evaluator state machine, CLI-backed reviewer variant, mid-Phase-5 injection, or binary pass/fail.

## Coordination note on `reviewer-registry.json`

When the plan was drafted, `reviewer-registry.json` had uncommitted edits on `main`. Those landed between draft and execution (commits `d93ff5d`, `d8930e3`, `e5bb92e`, `7b8fe0b`). T2's registry entry slots cleanly after `curmudgeon-review` and before the first `conditional` reviewer — no rebase needed.

## Execution hygiene

- Each task ends with a commit on `feat/adversarial-evaluator`. Do not rebase or squash until all 5 tasks land and the final reviewer pass is clean.
- After T5, run the plan's Verification Commands section (pytest + JSON validation + ruff).
- Then invoke `superpowers:finishing-a-development-branch` (or `/cleanup`) for merge decision.

## If execution is interrupted

- `git log feat/adversarial-evaluator ^main --oneline` shows what tasks have landed.
- Match commit count to plan task count (expect one commit per task minimum, more if spec-review cycles iterate).
- Resume by re-invoking `superpowers:executing-plans` pointed at the plan; skip already-done tasks.

## Post-T5: live test + recording lifecycle (added after initial execution)

T5 ships a hand-authored `recorded_response.json` to bootstrap the replay test, but a synthetic recording makes the test a tautology. The follow-up commit adds the missing capability layer:

- **`tests/test_adversarial_breaker_live.py`** — opt-in (`RUN_LIVE_LLM=1`) test that dispatches the real Anthropic API with the persona file as system prompt, asserts the same contract bounds, and writes the response back to `recorded_response.json` with provenance metadata.
- **`Makefile` target** — `make record-adversarial-fixture` is the canonical refresh command.
- **`tests/fixtures/adversarial_breaker/README.md`** — explains the two-test pattern, when to refresh, and what the fixture does NOT validate (calibration is the proper home for broad capability checks).
- **`recorded_response.json` carries `_meta.source`** — `"synthetic-stub"` (current state, do not trust as a capability check) vs. `"test_adversarial_breaker_live.py"` (real LLM recording). Replace before relying on the replay test for capability claims.

**First live recording should happen before the branch merges to main.** Run `make record-adversarial-fixture`, verify scores look sane, commit the refreshed file. After that, the replay test in CI is real.

Not yet implemented (deferred to a follow-up branch):
- Scheduled GitHub Actions workflow that runs the live test weekly and opens a drift-detection PR if `recorded_response.json` changes.
- Calibration loop for the `calibration` block on the registry entry — labeled corpus of ≥20 diffs, agreement scoring.
