# Research Team Architecture — Design Doc

**Date:** 2026-04-11
**Status:** Approved
**Approach:** Staggered Waves + Confidence-Scored Synthesis

## Problem

Phase 2 exploration uses a single Sonnet executor, which produces findings that are:
- **Shallow** (depth) — single pass misses connections between discoveries
- **Narrow** (breadth) — stays inside the codebase; doesn't pull external docs, API references, or prior art
- **Unverified** (quality) — findings feed Phase 4 without confidence signals; architects can't tell solid evidence from assumptions

## Solution

A standalone `/research` skill with a multi-agent research team that also integrates into code-creation-workflow Phase 2 for full/complex tasks.

## Architecture

### Orchestrator (Inline Executor)

Runs as Sonnet executor (not a subagent). Responsibilities:

1. Read research request (from user directly or Phase 2 handoff)
2. Classify task using smart-exploration's 9 categories
3. Select 2-4 researchers from the pool based on task type
4. Compose Wave 1 prompts (with memory-injection gotchas + Context Hub refs)
5. Dispatch Wave 1 in parallel
6. Read Wave 1 scratchpad, run gap detection
7. Dispatch Wave 2 gap-fillers if needed
8. Dispatch synthesizer
9. Return confidence-scored research brief

### Researcher Pool

Dynamic assignment — orchestrator picks per-task, not fixed roles:

| Researcher | Tools | Focus |
|---|---|---|
| **Codebase Explorer** | Glob, Grep, Read, git log/blame | Deep code understanding, patterns, structure |
| **External Researcher** | WebSearch, WebFetch, Context Hub (`/fetch-api-docs`) | API docs, library references, best practices, prior art |
| **Integration Mapper** | Glob, Grep, Read | Data flow across service boundaries, dependency mapping |
| **History Analyst** | git log, blame, PR history | Why things are the way they are, past decisions, regressions |

### Default Researcher Selection by Task Category

| Task Category | Default Researchers |
|---|---|
| endpoint / api | Codebase Explorer, Integration Mapper, External Researcher |
| ui | Codebase Explorer, External Researcher |
| data | Codebase Explorer, History Analyst |
| integration | External Researcher, Integration Mapper, Codebase Explorer |
| refactor | Codebase Explorer, History Analyst |
| bugfix | Codebase Explorer, History Analyst, Integration Mapper |
| config | Codebase Explorer, External Researcher |
| exploration | External Researcher, Codebase Explorer |
| general | Codebase Explorer, External Researcher |

Orchestrator can override defaults based on the specific request.

## Wave Logic

### Wave 1 — Parallel Exploration

2-4 researchers dispatched simultaneously. Each writes to the shared exploration scratchpad in structured format:

```markdown
## [Researcher Role] — [Focus Area]
### Findings
- Finding 1 (source: file/url/commit)
- Finding 2 (source: ...)
### Open Questions
- What I couldn't determine...
### Connections
- This relates to [other area] because...
```

### Gap Detection

After Wave 1, orchestrator reads all scratchpad entries and checks:

1. Open questions that another researcher type could answer
2. Areas referenced by one researcher but not covered by any other
3. Contradictions between findings
4. Low confidence on something critical to the task

If any gap detected → Wave 2. Otherwise → skip to synthesizer.

### Wave 2 — Targeted Gap-Fill

1-2 researchers dispatched with specific prompts referencing Wave 1 findings and the identified gaps. Wave 2 researchers READ the scratchpad before starting.

### Skip Conditions

Fast-path tasks (single-file, well-understood domain) skip research entirely — respects code-creation-workflow's existing fast/lite/full path classification.

## Research Brief (Synthesizer Output)

The synthesizer agent reads all scratchpad entries and produces:

```markdown
# Research Brief: [Topic]

## Key Findings
- Finding (confidence: verified | inferred | assumed)
- ...

## Architecture-Relevant Constraints
- Things the architect must account for

## Open Risks
- Assumptions that couldn't be verified (low confidence)

## Sources
- Files, URLs, commits referenced
```

### Confidence Levels

- **verified** — confirmed in code, docs, or runtime evidence
- **inferred** — reasonable conclusion from multiple sources, not directly confirmed
- **assumed** — couldn't verify; architect should design defensively around this

## Integration Points

### Standalone Invocation

```
/research "How does DocuSeal's webhook verification work and how should we handle retry failures?"
```

User receives the research brief directly. No workflow, no implementation.

### Phase 2 Integration

Code-creation-workflow gains a branch in Phase 2:
- If task path is `full` or `complex` → invoke `/research` skill
- If task path is `lite` or `fast` → keep current single Sonnet executor

The research brief replaces the current exploration output and feeds into Phase 3 (requirements) and Phase 4 (architecture). The Opus advisor checkpoint still happens — it reviews the research brief.

Confidence scores are visible to Phase 4 architects so they know which findings are solid vs. assumed.

### Composed Infrastructure

| Existing Component | How Research Team Uses It |
|---|---|
| **smart-exploration** | Task classification (9 categories) drives researcher selection |
| **memory-injection** | Gotchas injected into researcher prompts |
| **exploration scratchpad** | Shared artifact between Wave 1 and Wave 2 (same format as swarm-protocols) |
| **Context Hub** | External Researcher uses `/fetch-api-docs` for curated API references |
| **investigator** | Bugfix tasks can invoke investigator's evidence matrix pattern |

### What Changes in code-creation-workflow

- Phase 2 gains conditional branch: full/complex → `/research`, else → current path
- Opus advisor reviews research brief instead of raw explorer output
- Research brief confidence scores feed Phase 4 architect prompts

## Ruled Out

- **Replacing Phase 2 entirely** — lite/fast tasks don't need a research team; overkill
- **Hierarchical sub-teams with specialist+verifier pairs** — agent explosion (6-8+ agents), high latency, fights compose-don't-replace principle
- **Flat parallel-only dispatch (no waves)** — researchers can't build on each other's findings; duplicate work, missed connections
- **Running research during Phase 4** — too late; architecture decisions need research inputs, not the reverse
- **Giving researchers write access** — research is read-only; implementation stays in Phase 5
- **MCP tool access for researchers** — risk of side effects, overkill for research; can escalate later if needed
- **Fixed role assignments** — tasks vary too much; a refactor needs different researchers than an integration task
