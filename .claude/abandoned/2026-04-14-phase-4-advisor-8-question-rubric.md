# Abandoned: Phase 4 Advisor 8-Question Rubric

**Date:** 2026-04-14
**Source:** vercel-labs/open-agents plan-mode skill (external-repo-analysis session, finding #4 of 7)

## What Was Attempted
Add an 8-question critique rubric to `skills/claude-flow/phases/phase-4-architecture.md` Step 2 (Architecture Critique advisor prompt). The rubric enumerated questions for the Opus advisor to answer against `$requirements` and `$exploration` (requirements alignment, unstated assumptions, scope calibration, boundary clarity, failure modes, complexity justification, dependency minimality, simpler-path check).

## Why Abandoned
Conflicts with `advisor_prompt_compression.md`: **"Advisor (Opus) call prompts should be a contract reference + 1-line question, not verbose templates."** The 8-question rubric is exactly the verbose template the pattern rules out. The current advisor prompt (`"Given $exploration and $requirements, critique this architecture."`) relies on Opus judgment — the compression pattern observed same-quality guidance at fraction of token cost.

Secondary reason: Phase 4c structured coverage mapping + Phase 5 stress-test already cover requirement-to-task traceability and scope-boundary validation. The 8 questions largely duplicate downstream deterministic checks.

## Do Not Re-Propose
Future sessions reading memory should skip re-proposing this rubric. If advisor critique quality resurfaces as a pain point, look at: (a) `$exploration` quality (upstream fix), (b) Phase 4c coverage-mapping gaps, or (c) Phase 5 stress-test rigor — not at stuffing a rubric into Phase 4 Step 2.

## Generalization
When a finding from an external repo contradicts an explicit MEMORY.md pattern, default to the memory pattern. External findings need to earn their place against existing rules. This record is also a data point for `external_repo_analysis_pattern.md`: a finding can be well-founded in the source repo and still fail the "compose with our tools" filter.

## References
- `advisor_prompt_compression.md`
- `external_repo_analysis_pattern.md` (worked example 3 — this session)
- `abandoned_approaches_pipeline.md`
