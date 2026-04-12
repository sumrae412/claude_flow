# Design: Token Efficiency Overhaul for code-creation-workflow

**Created:** 2026-04-11 | **Status:** approved

## Problem

The `code-creation-workflow` SKILL.md is a 1,845-line monolith (~24K tokens) loaded in full every session — even fast-path single-file edits. Combined with verbose advisor prompt templates, unstructured phase handoffs, and up to 13 separate Phase 6 reviewer dispatches, the workflow consumes far more tokens than necessary.

## Goals

1. Reduce always-loaded context from ~24K to ~2.5K tokens (90% reduction)
2. Reduce runtime token usage: smaller advisor prompts, fewer reviewer dispatches, compact phase handoffs
3. Maintain all existing quality gates, paths, and review tiers
4. Each phase file independently maintainable

## Non-Goals

- Changing the phase structure itself (Phases 0-6 stay)
- Removing any review tier or quality gate
- Changing the executor/advisor model strategy

## Design

### 1. Progressive Disclosure — Split SKILL.md into Phase Files

**New structure:**

```
skills/code-creation-workflow/
├── SKILL.md                      # Thin router (~2.5K tokens)
├── phases/
│   ├── phase-0-context.md        # Context loading + hooks bootstrap (~2K)
│   ├── phase-1-discovery.md      # Path triage logic (~1.5K)
│   ├── phase-2-exploration.md    # Executor explores + advisor checkpoint (~2.5K)
│   ├── phase-3-requirements.md   # Clarification + quality gate + $requirements (~2K)
│   ├── phase-4-architecture.md   # Competing options + advisor + plan (~3K)
│   ├── phase-4c-verification.md  # Plan verification + coverage mapping (~1.5K)
│   ├── phase-4d-skeletons.md     # Test skeleton generation (~1K)
│   ├── phase-5-implementation.md # TDD + defensive + parallel dispatch + context mgmt (~3K)
│   ├── phase-5.5-reflection.md   # RARV self-check (~1K)
│   └── phase-6-quality.md        # Cascading review + finish + retrospective (~3K)
├── contracts/
│   ├── exploration.schema.md     # $exploration shape
│   ├── requirements.schema.md    # $requirements shape
│   ├── plan.schema.md            # $plan shape
│   └── diff.schema.md            # $diff shape
├── references/                   # Existing, lazy-loaded by phases that need them
└── scripts/                      # Unchanged
```

**Loading behavior:**
- Always loaded: `SKILL.md` (router) + `contracts/*.schema.md` (~3.3K total)
- Phase files loaded on entry, dropped after phase transition
- Reference files lazy-loaded only when their phase needs them
- Path-specific loading:
  - Fast: router + phase-0 + phase-1 = ~5K, then exit
  - Lite: router + phases 0, 1, 2, 3, 4(inline), 5, 6 = ~10K peak
  - Full: router + all phases sequentially = ~16K peak (never all at once)

### 2. Structured Phase Contracts

Each phase output defined as a compact schema that serves as both documentation and runtime handoff format.

**$exploration** (Phase 2 → Phases 3, 4, advisors):
```yaml
key_files:
  - path: string
    role: string          # 1-line role
patterns:
  - name: string
    example_file: string
integration_points:
  - system: string
    interface: string
concerns: string[]
confidence: verified | inferred | assumed
```

**$requirements** (Phase 3 → Phases 4, 4c, 5, 6):
```yaml
stories:
  - role: string
    want: string
    benefit: string
acceptance_criteria:
  - id: AC-N
    when: string
    if: string            # optional
    then: string
scope:
  in: string[]
  out: string[]
edge_cases:
  - case: string
    resolution: string
```

**$plan** (Phase 4b → Phases 4c, 4d, 5, 6):
```yaml
steps:
  - id: N
    description: string
    files: string[]
    type: value_unit | shared_prerequisite | adr
    depends_on: [{step: N, type: data | build | knowledge}]
    test_requirements: string
    status: pending | complete
```

**$diff** (Phase 5 → Phase 6):
```yaml
files_changed: string[]
insertions: number
deletions: number
git_diff: string          # full diff (unavoidable)
```

Contracts persist across phase drops. When `phase-2-exploration.md` is unloaded, `$exploration` carries forward at ~100-200 tokens instead of ~2.5K of phase instructions.

### 3. Advisor Prompt Compression

Replace verbose templates (~350 tokens each) with structured input referencing contracts.

**Phase file stores** (~30 tokens):
```
### Advisor: Exploration Review
Dispatch Opus with $exploration + question:
"What's missing from this exploration before I move to requirements?"
```

**Dispatched prompt** (~150-250 tokens):
```
Review this exploration for [feature]:
[paste $exploration contract]
What's missing? What should I investigate deeper?
```

All 5 checkpoints follow the same pattern:

| Checkpoint | Input | Question |
|---|---|---|
| Exploration Review | $exploration | "What's missing before requirements?" |
| Architecture Critique | $exploration + 2 options summary | "Blind spots? Trade-offs underweighted?" |
| Plan Stress-Test | $plan + $requirements | "Logic errors, missing edges, scope creep?" |
| Mid-Implementation | $plan step N context | "Which pattern at this decision point?" |
| Strategic Pre-Review | $diff + $requirements | "Does this fulfill the original requirements?" |

Extended thinking instruction added for Phase 4 and 4b checkpoints only.

**Savings:** ~40% smaller per Opus call, ~2K freed from SKILL.md templates.

### 4. Phase 6 Reviewer Consolidation

**Tier 2 merge (3 → 2 agents):**

| New Agent | Combines | Rationale |
|---|---|---|
| `safety-reviewer` (sonnet) | silent-failure-hunter + security-reviewer | Both analyze error/failure paths, same diff traversal |
| `test-coverage-analyzer` (sonnet) | unchanged | Structurally different analysis |

**Payload slimming (all tiers):**

| Today | Proposed |
|---|---|
| Full $requirements prose | Only acceptance_criteria array (~40% smaller) |
| Full $plan | Only step_id + files_touched list (~70% smaller) |
| Verbose role prompt | 2-line role + checklist reference |
| Full git diff | Unchanged (required) |

**Conditional skips:**
- Code simplifier: skip for diffs under 100 lines (avoids unnecessary Opus call)
- Tier 3 reviewers: enforce existing skip when same reviewer ran in Phase 5

### 5. SKILL.md Router Content

**Stays in router (~2.5K tokens):**
1. Frontmatter + 3-line overview
2. Model assignments table (6 rows)
3. Path decision tree (compressed flowchart)
4. Phase transition map (from→to→condition table)
5. Phase output contracts summary (1 line per contract, pointing to contracts/)
6. Phase loading instructions
7. Quick reference table (6 rows)
8. Common mistakes (compressed to ~15 critical rows)

**Moves out:**

| Content | Destination | Tokens freed |
|---|---|---|
| Workflow state machine (JSON, jq) | phase-0-context.md | ~3K |
| Phase 0 steps | phase-0-context.md | ~2K |
| Phase 1 artifact table | phase-1-discovery.md | ~500 |
| Phase 2-6 instructions | phases/phase-*.md | ~14K |
| Advisor prompt templates | Compressed into phase files | ~2K |
| Context management strategy | phase-5-implementation.md | ~1.5K |
| Failure taxonomy | references/failure-taxonomy.md | ~800 |
| Agent/skill reference tables | references/agent-registry.md | ~1K |

## Token Impact Summary

| Change | Savings |
|---|---|
| SKILL.md split (monolith → router + phases) | 24K → 2.5K always-loaded (90%) |
| Structured contracts replace prose | ~50% smaller phase-to-phase payloads |
| Advisor prompt compression | ~40% smaller per Opus call |
| Tier 2 consolidation (3→2) | 1 fewer Sonnet dispatch + slimmer payloads |
| Code simplifier conditional skip | Skip Opus call on small diffs |
| Failure taxonomy + agent tables lazy-loaded | ~1.8K freed from router |

**End-to-end by path:**
- Fast path: ~4K total (was ~24K) — 83% reduction
- Lite path: ~10K peak (was ~24K) — 58% reduction
- Full path: ~16K peak sequential (was ~24K) — 33% reduction + runtime savings

## Ruled Out

- **Removing advisor checkpoints entirely** — Considered dropping the optional ones (Mid-Implementation, Strategic Pre-Review) but they catch real issues in full-path runs. Keeping as optional is the right call.
- **Merging all Tier 2 into a single agent** — test-coverage-analyzer does structurally different work (test file analysis vs code path analysis). Merging it would degrade quality.
- **Dynamic phase loading via scripts** — Considered a Python script that reads workflow state and returns which phase file to load. Too clever; the executor can read phase files directly. The skill file already tells it when to load each phase.
- **Removing the failure taxonomy** — It feeds session-learnings for workflow self-improvement. Worth the ~800 tokens when loaded in Phase 6.
- **Splitting reference files further** — The existing references are already reasonably scoped. Splitting them would add management overhead for marginal gains.
