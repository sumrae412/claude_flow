# Token Efficiency Phase 2 — Implementation Plan

> **For Claude:** Each of the 5 items below is a separate `/claude-flow` invocation. Ship sequentially, not in parallel (most touch the same repo root). Use the claude-flow path listed for each. Items 2.a–2.h are 8 sibling invocations following the same template.

**Goal:** Follow-up wins from the [2026-04-18 token-efficiency phase 1](https://github.com/sumrae412/claude-skills/pull/36). Phase 1 shipped the brevity skill, `--lite` flags on heavyweight orchestrators, the progressive-disclosure audit script, `/clear` guidance, and prompt-caching via system/user split in `agent-sdk/pr-reviewer`. Phase 2 closes the remaining levers in rank order of impact-per-effort.

**Scoping principle:** Each item is independently shippable. Do not bundle. A broken item-3 should not block item-1.

**Non-goals for this plan:**
- Building a cross-session token-budget UI / dashboard (deferred — no evidence it's the bottleneck).
- Rewriting the agent-sdk pr-reviewer for batch API (orthogonal; covered by its own Agent SDK optimization track).
- Migrating Opus advisors to Sonnet (Phase 1 already tiered where sensible; further tier-downs without measurement = vanity optimization).

---

## Sequencing

Ship in this order. Rationale in each item's section.

| Order | Item | Path | Rough size | Blocker risk |
|-------|------|------|-----------|--------------|
| 1 | MEMORY.md trim | FAST | 1 file | None (pure edit) |
| 2.a–2.h | 8 progressive-disclosure refactors | LITE × 8 | 8 PRs | Phase content must be extracted cleanly |
| 3 | Tool-result auto-clearing hook | FULL | ~4 files | Hook trigger semantics need exploration |
| 4 | Prompt-variant optimization on hot subagent prompts | LITE | 2-3 files | Needs traffic to calibrate |
| 5 | Haiku for Phase 1 triage | LITE | 1 file + regression check | Requires A/B with Sonnet on path decisions |

Items 1 and 2.a–2.h are pure mechanical wins and can be shipped the same day. Item 3 is the biggest structural change and should have a dedicated session. Items 4–5 need evaluation infra and should land after item 3 clears.

---

## Item 1 — MEMORY.md trim

**Path:** FAST PATH (single file, no schema, no endpoints, no new logic)

**Invocation:** `/claude-flow trim MEMORY.md index entries to one line ≤150 chars each`

**Problem:** `MEMORY.md` is 31.8KB against a 24.4KB limit. The overflow is silently truncated mid-session — this session already shows the warning. Every session using claude-flow pays the full 24.4KB in resident context and still loses tail entries to truncation.

**Scope:**
- File: `~/.claude/projects/-Users-summerrae-claude-flow/memory/MEMORY.md`
- Action: Rewrite index entries that exceed ~150 chars. Many current entries open with a title-equivalent phrase then restate ("Reviewer Registry — `reviewer-registry.json` drives Phase 6 reviewer selection.") — trim to the hook clause only.

**Phase-by-phase:**
- **Phase 0:** Skip — no hooks.json changes, no project context needed beyond this plan.
- **Phase 1:** Auto-route to FAST.
- **Implementation (FAST step):**
  1. Read MEMORY.md, identify entries >200 chars.
  2. For each, rewrite the one-line pointer to ≤150 chars. Keep the target filename unchanged.
  3. Verify byte count against 24,400 with `wc -c`.
- **Test:** None (markdown edit). Regression check: reload a fresh session and confirm no truncation warning on MEMORY.md.
- **Commit:** directly to memory repo (`sumrae412/claude-config` per prior commits). Single commit.

**Verification:** MEMORY.md byte count under 24,400 AND all topic-file links resolve (`ls` each target).

**Ruled out:**
- **Splitting MEMORY.md into multiple indexes** — MEMORY.md is loaded whole at session start; splitting requires harness changes we don't control.
- **Moving long entries into a separate appendix file** — the content lives in the topic files already; the index just needs to be shorter.
- **Auto-compressing via LLM** — trim quality matters (wrong hook → lost retrievability). Human judgment on each entry.

---

## Item 2.a–2.h — 8 progressive-disclosure refactors

**Path:** LITE PATH, one per skill (8 separate invocations).

**Invocation template:** `/claude-flow refactor <skill-name> to progressive disclosure (router SKILL.md + phases/ + references/)`

**Problem:** `scripts/progressive_disclosure_audit.py` (Phase 1) flagged 8 SKILL.md files above the 300-line CANDIDATE threshold. Each one loads fully into context whenever the skill fires, even if only one section is needed.

**Targets (ranked by line count — ship largest first for biggest wins):**

| Order | Skill | Lines | Token-estimate resident today |
|-------|-------|-------|------------------------------|
| 2.a | production-readiness-check | 494 | ~4.5K |
| 2.b | session-learnings | 408 | ~3.7K |
| 2.c | user-stories | 388 | ~3.5K |
| 2.d | cleanup | 379 | ~3.4K |
| 2.e | research | 350 | ~3.2K |
| 2.f | playwright-test | 345 | ~3.1K |
| 2.g | debate-team | 313 | ~2.8K |
| 2.h | sc-marketing-scripts | 308 | ~2.8K |

**Pattern (per skill, reused template):**

Follows the validated pattern from `defensive-ui-flows` (PR #22, 1245 → 82-line router + references/patterns.md) and `defensive-backend-flows`. Reference in CLAUDE.md §Plugin Cache / Skills Management.

- **Phase 0:** Skip.
- **Phase 1:** Auto-route to LITE.
- **Phase 2 (exploration):** Identify natural split boundaries in the SKILL.md — sections that are rarely co-read (e.g. "how to use" vs "error recovery" vs "full examples"). Confirm the skill's entry triggers and output contract.
- **Phase 3 (requirements):** $requirements = "router ≤150 lines, phase/reference files lazy-loaded, no behavior change for consumers."
- **Phase 4 (architecture + plan):** Plan enumerates exact section → file extractions using `sed -n 'M,Np' SKILL.md > references/<name>.md` (per CLAUDE.md gotcha: do not load monolithic SKILL.md into context during the split).
- **Phase 5 (implementation):**
  1. Create `phases/` and `references/` subdirs.
  2. Run `sed` extraction per the plan.
  3. Rewrite SKILL.md as router with "load X.md when Y condition" pointers.
  4. Re-run `progressive_disclosure_audit.py` to confirm the skill no longer appears as a candidate.
  5. Run any test fixtures the skill already has.
- **Phase 6:** Tier-1 CodeRabbit; skip Tier 2+ if clean.

**Verification (per skill):**
- Router SKILL.md under 150 lines (target) or under 2K tokens (hard limit).
- `grep` for any cross-reference to moved content elsewhere in the repo — broken links mean we didn't update callers.
- Manual invocation of the skill on a trivial task to confirm lazy-load triggers fire.

**Ruled out:**
- **Bundling all 8 into one PR** — reviewer fatigue, conflict risk, harder to revert if one refactor is wrong.
- **Auto-generated router via script** — the router is the skill's thinking layer; needs human judgment about what loads when. An LLM draft is OK, but not a deterministic script.
- **Splitting skills under 300 lines** — audit threshold is CANDIDATE=300. Below that, the overhead of split navigation isn't worth the resident-token savings.

---

## Item 3 — Tool-result auto-clearing hook

**Path:** FULL WORKFLOW (new hook, new registry entry, new semantics — needs exploration)

**Invocation:** `/claude-flow add a tier-2 hook that clears large tool results from context after they are consumed at phase transitions`

**Problem:** Long sessions accumulate tool-result payloads (grep outputs, file reads, web fetches) that remain in context after the information has already been distilled into a phase contract. Auto-compaction fires at ~80% — too late for sessions that do many tool calls. CLAUDE.md §Common Mistakes already lists: "Letting context grow unbounded | Tool-result clearing at ~50K, compaction at ~80%."

**Scope (preliminary — Phase 2 exploration will refine):**
- New file: `hooks/tier2/clear-stale-tool-results.sh`
- Modify: `hooks/hook-registry.json` — new entry with `stack_tags: ["*"]`, opt-in.
- Modify: `skills/claude-flow/phases/phase-N-*.md` — emit a "phase complete, prior tool results can be cleared" signal at phase transitions.
- New file: `hooks/tier2/tests/clear_stale_tool_results.bats`

**Phase-by-phase:**
- **Phase 0:** Load context engineering + hook-related skills.
- **Phase 1:** FULL (novel hook semantics, needs architecture discussion).
- **Phase 2 (exploration):**
  - How does Claude Code surface tool-result clearing? Investigate the harness; is there a programmatic API, or does it only happen via auto-compaction?
  - What signal defines "consumed"? Options: phase-transition stdin JSON, explicit sentinel in an output contract, token-threshold trigger.
  - Do other skills' hooks already touch this? Check `hooks/tier1/` and the existing `post-commit-learnings.sh` / `decision-journal-hook.sh` for clearing patterns.
- **Phase 3 (requirements):** Acceptance criterion — on a 10-step synthetic run, resident tool-result tokens at step 10 are ≤ tokens at step 5.
- **Phase 4 (architecture):**
  - **Option A:** Clear on PostToolUse after size threshold — simple but naive (clears things still in use).
  - **Option B:** Clear at phase-transition signal — requires phase files to emit the signal, but precise.
  - **Option C:** Hybrid — threshold-triggered clearing that honors a "keep" list populated by the current phase.
  - Opus advisor should weigh these; do not pick without Phase 4b stress-test.
- **Phase 5 (implementation):** TDD — write failing bats test first; implement hook; wire into registry; update phase files to emit the signal.
- **Phase 6:** Full cascade — this is new infra, warrants security + safety review (a broken clear-hook could drop in-flight state).

**Verification:**
- Synthetic 10-step session: resident-tool-result tokens monitored by inserting a `/context` check.
- Regression: existing Phase 5 tests in claude-flow pass unchanged.
- No-op on single-phase runs (FAST/LITE) — hook must not fire when there's no phase transition.

**Ruled out:**
- **Always-on tier-1 hook** — too aggressive; would clear tool results mid-phase when the agent still needs them.
- **Post-commit clearing** — too coarse; phases span many commits or none.
- **Relying on Claude Code's `/compact` mechanism** — that's an 80%-threshold emergency release valve, not preventive clearing. It also nukes useful context alongside stale results.

---

## Item 4 — Prompt-variant optimization on hot subagent prompts

**Path:** LITE PATH (uses existing `prompt-tracker.py` and `prompt-optimization` skill infra)

**Invocation:** `/claude-flow identify top-5 subagent prompts by dispatch frequency, generate challenger variants, run A/B via prompt-tracker`

**Problem:** Reviewer system prompts, Phase 5 implementer briefs, and advisor prompts are invoked thousands of times across sessions. Each has compounding token cost. Phase 1 already compressed advisor prompts (MEMORY `advisor_prompt_compression.md`); the same treatment should apply to hot subagent prompts — but with data, not vibes.

**Scope:**
- Read: `memory/episodic/exploration-events.jsonl`, any `dispatch-events.jsonl` if present, or instrument if absent.
- Modify: `skills/<skill>/references/*-prompt.md` for the top-5 hot prompts identified.
- Write: `docs/audits/2026-04-XX-hot-prompt-variants.md` with the before/after token counts and the A/B F1 deltas.

**Phase-by-phase:**
- **Phase 0:** Load `prompt-optimization` and `session-learnings` skills (they own the eval infra).
- **Phase 1:** LITE.
- **Phase 2 (exploration):**
  - Run `python3 ~/.claude/scripts/prompt-tracker.py report` — identify top-N prompts by volume.
  - If the tracker isn't already instrumenting subagent dispatches, Phase 2 turns into a prereq: add dispatch-event logging first (this bumps to FULL). Verify before proceeding.
- **Phase 3:** $requirements = "for each of top-5, generate 2 challenger variants; A/B against baseline for 10+ dispatches each; promote only if F1 gap > 0.05 at budget ≤ baseline."
- **Phase 4 (architecture):** Variants live as peer files in `references/prompts/<prompt-name>/{baseline,challenger-a,challenger-b}.md`. Tracker reads the active variant from registry.
- **Phase 5:** Invoke `prompt-optimization` skill per hot prompt; commit variants; run tracker; let data accumulate.
- **Phase 6:** Skip Phase 6 review for the variant files themselves (they're prompt text, not code). Do run a spot-check on 3 real dispatches per variant.

**Verification:**
- `prompt-tracker.py report` shows 2+ variants per top-5 prompt after 10 sessions.
- At least 1 variant promoted with measurable token saving AND no F1 regression.
- Fallback: if no variant beats baseline after 2 weeks, revert — no half-shipped state.

**Ruled out:**
- **Blanket LLM compression of all prompts** — high risk of silent quality regression; MEMORY `score_band_persona_calibration_coupling.md` shows prompt wording matters more than length.
- **Optimizing before measuring volume** — vanity engineering; compress prompts that fire once a week and gain nothing.
- **Auto-promoting challengers** — promotion is a judgment call; tracker proposes, human decides.

---

## Item 5 — Haiku for Phase 1 triage

**Path:** LITE PATH (single phase file, single model swap, + A/B regression check)

**Invocation:** `/claude-flow swap Phase 1 discovery to haiku and regression-test path-decision agreement vs sonnet`

**Problem:** Phase 1 is a decision tree (is this a bug? is it 1-2 files? does a plan exist?). Sonnet on a decision tree is overkill. Haiku is ~10× cheaper at ~3× faster latency on routing tasks. But: Phase 1's path decision gates the entire workflow — a wrong pick on this step wastes far more than the model-cost savings.

**Scope:**
- Modify: `skills/claude-flow/phases/phase-1-discovery.md` — change model frontmatter/assignment to haiku.
- Modify: `skills/claude-flow/SKILL.md` Quick Reference table — update Phase 1 model column.
- New file: `tests/phase1-triage-regression/` — 20 fixture tasks with known correct paths; run both sonnet and haiku, compare.
- Modify: `scripts/` — helper to run the regression on demand.

**Phase-by-phase:**
- **Phase 0:** Skip — targeted single-phase change.
- **Phase 1:** LITE.
- **Phase 2 (exploration):** Read phase-1-discovery.md in full. Inventory every decision gate (bug? fast? clone? plan? lite? explore? full? audit?) and the signals each uses. Confirm haiku can evaluate each — any gate requiring subtle codebase reasoning is a red flag.
- **Phase 3:** $requirements = "haiku Phase 1 matches sonnet's path decision on ≥19/20 fixture tasks, otherwise revert."
- **Phase 4 (architecture):** Single-option — the decision is a model swap, not an architectural choice. Skip the 2-options rule; note explicitly in the plan.
- **Phase 5:**
  1. Write 20 fixture tasks covering all 8 triage paths (bug, fast, clone, plan, lite, explore, full, audit).
  2. Create regression runner: for each fixture, dispatch both models, capture path decision.
  3. Run the regression. If ≥19/20 match, proceed. Otherwise STOP — document which paths haiku misses and abort the swap.
  4. Update phase-1-discovery.md model assignment.
  5. Update claude-flow SKILL.md Quick Reference.
- **Phase 6:** Skip haiku lightweight review (that'd be ironic here). Run the regression runner as the review step.

**Verification:**
- Regression: ≥19/20 agreement with sonnet on the fixture set.
- Live canary: 10 real claude-flow invocations, compare user's ex-post judgment of path correctness.
- Cost-saving: measured against Phase 1 token spend over prior 30 days.

**Ruled out:**
- **Haiku for Phase 2 exploration** — exploration needs codebase reasoning, not decision-tree traversal. Keep Sonnet.
- **Haiku for Phase 6 haiku reviewers** — already haiku, no change needed.
- **Skipping the regression test** — "Phase 1 is just routing" sounds safe until a botched path routes a bug-fix into the 30-minute FULL workflow. The regression is cheap; the regression failure is expensive.

---

## Cross-cutting constraints

- **One repo at a time.** These plans touch at minimum three repos (claude-skills, claude-config memory, claude_flow docs/scripts). Do not start a second item while another has uncommitted state in any of those.
- **Two-clones drift awareness.** CLAUDE.md §Known Gotchas — canonical repo is `/Users/summerrae/claude_code/claude_flow/`. Start every session with `git rev-parse --show-toplevel` check.
- **Measure before promoting.** Items 3, 4, and 5 all claim token savings. Each requires a before/after measurement in its Phase 6 verification step. No item ships unless the claim is measured, not asserted.
- **Memory updates via session-learnings.** Each shipped item should produce at least one MEMORY entry (the pattern, the gotcha, or both). Invoke `session-learnings` per commit cluster, not per plan.

---

## Success criteria (plan-level)

Phase 2 is complete when:
1. MEMORY.md is under 24.4KB (item 1).
2. ≥5 of 8 audit-flagged skills are refactored (items 2.a–2.h); remaining 3 have justified deferrals documented in MEMORY.
3. Tool-result clearing hook ships or is deliberately deferred with measurement evidence (item 3).
4. At least 1 hot subagent prompt has a data-backed promoted variant (item 4).
5. Phase 1 triage runs on haiku OR haiku is ruled out with regression data (item 5).

Anything less than 3-of-5 means Phase 2 stalled — invoke `/cleanup` to audit the half-shipped state before starting Phase 3.
