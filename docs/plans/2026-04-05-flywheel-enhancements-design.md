# Flywheel Enhancement Integration

**Created:** 2026-04-05 | **Status:** approved

## Summary

Integrate 10 enhancements from Jeffrey Emanuel's "Agentic Coding Flywheel" methodology into the existing `code-creation-workflow` SKILL.md. All changes are inline (Approach A) — no new reference files.

## Source

The Flywheel methodology emphasizes: exhaustive markdown planning (85% of effort), multi-model plan competition, iterative refinement with convergence detection, self-contained task units ("beads"), and coordinated agent swarms. We adapt these concepts to our single-session subagent model.

## Enhancements

### Cross-Cutting: Compaction Recovery (Model Strategy section)
- Rule: after context compaction, re-read CLAUDE.md, current plan, and active TodoWrite state
- Prevents drift in long sessions where context gets compressed

### Phase 4 Additions

1. **Multi-Model Plan Competition** — Add 3rd architect subagent with contrarian optimization target (e.g., "maximum reuse" or "future extensibility"). Synthesis step blends best of 3 perspectives.

2. **Iterative Plan Refinement Loop** — After plan is written, dispatch fresh subagent to critique in clean context. 2-3 rounds. Uses "overshoot" technique ("find at least 30 issues"). Stop on convergence.

3. **Convergence Detection** — Stop criteria: suggestions mostly cosmetic, no architectural changes, rate of change decelerating.

### Phase 5 Additions

4. **Fresh Eyes Self-Review** — After each major chunk (3+ files), re-read new code for obvious bugs before next step.

5. **Strategic Drift Detection** — Every 5 plan steps or ~30 min, checkpoint: "Do remaining steps still produce the thing we're building?"

6. **Swarm-Adapted Subagent Coordination** — Staggered dispatch, structured marching orders, explicit file claims, work announcement before starting.

### Phase 6 Additions

7. **Overshoot Review Technique** — All reviewer prompts include ambitious target: "find at least 30 issues."

8. **Random Code Exploration** — Agent randomly explores code files, traces execution flows, finds cross-cutting bugs.

9. **UI/UX Polish (Tier 5)** — Dedicated friction/delight/visual quality pass. Separate desktop and mobile prompts.

10. **De-Slopification Pass** — Remove AI writing patterns from generated docs/comments (emdash overuse, filler phrases).

## What Doesn't Change

- Phases 0, 0.5, 1, 2, 3 — unchanged
- All existing agents/skills — additions only, no removals
- Hook templates reference — unchanged

## Implementation Plan

Single file edit: `skills/code-creation-workflow/SKILL.md`. Insert enhancements at their designated phase locations.
