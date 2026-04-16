---
name: research
description: Multi-agent research team with staggered waves and confidence-scored synthesis. Standalone skill for deep codebase + external research, also invoked by claude-flow Phase 2 for full/complex tasks.
user-invocable: true
---

# Research

## Overview

Multi-agent research team that explores a question in depth across codebase, git history, external docs, and API references. Produces a confidence-scored research brief.

**Standalone:** `/research "your question here"`
**Integrated:** Called by claude-flow Phase 2 when task path is `full` or `complex`.

**Announce:** "Running research team — classifying task, dispatching researchers, synthesizing findings."

---

## Orchestrator (Inline Executor)

The orchestrator runs inline as the Sonnet executor (not a subagent). It coordinates the full pipeline:

1. Read research request (from user directly or Phase 2 handoff)
2. Classify task using smart-exploration's 9 categories
3. Select 2-4 researchers from the pool based on task type
4. Compose Wave 1 prompts (inject memory-injection gotchas if in workflow context)
5. Dispatch Wave 1 researchers in parallel via Agent tool
6. Read Wave 1 scratchpad entries, run gap detection
7. If gaps found → dispatch Wave 2 gap-fillers (1-2 researchers)
8. Dispatch synthesizer agent
9. Return confidence-scored research brief

### Task Classification

Use smart-exploration's 9 categories to determine researcher mix. Read the task request + any mentioned files/areas to classify:

| Category | Signal |
|----------|--------|
| `endpoint` | API routes, controllers, handlers |
| `ui` | Templates, components, CSS, state |
| `data` | Models, migrations, queries, schema |
| `integration` | External APIs, webhooks, third-party services |
| `refactor` | Restructuring without behavior change |
| `bugfix` | Defect tracing, unexpected behavior |
| `config` | Env vars, infrastructure, deployment |
| `exploration` | Spike, prototype, feasibility |
| `general` | Doesn't fit a specific category |

---

## Researcher Pool

Dynamic assignment — orchestrator picks per-task, not fixed roles.

### Codebase Explorer

**Subagent type:** `Explore`
**Tools:** Glob, Grep, Read, LS
**Focus:** Deep code understanding — file structure, patterns, conventions, architecture layers.

**Prompt template:**
```
Think harder about this research question: [RESEARCH_QUESTION]

Focus area: [FOCUS_DESCRIPTION]

Your role: Codebase Explorer — deep-dive into the codebase to understand how this area works.

Explore systematically:
1. Find the key files and modules related to this question
2. Trace data flow and call chains
3. Document patterns and conventions used
4. Identify constraints and integration points

[MEMORY_INJECTION_BLOCK]

Write your findings in this exact format:

## Codebase Explorer — [FOCUS_DESCRIPTION]
### Findings
- Finding 1 (source: exact/file/path.py:line)
- Finding 2 (source: exact/file/path.py:line)
### Open Questions
- What I couldn't determine...
### Connections
- This relates to [other area] because...

Report in under 500 words. Be specific — file paths, line numbers, function names.
```

### External Researcher

**Subagent type:** `general-purpose`
**Tools:** WebSearch, WebFetch, Skill (for `/fetch-api-docs` if available)
**Focus:** API docs, library references, best practices, prior art outside the codebase.

**Prompt template:**
```
Think harder about this research question: [RESEARCH_QUESTION]

Focus area: [FOCUS_DESCRIPTION]

Your role: External Researcher — find relevant information OUTSIDE the codebase.

Research systematically:
1. Search for official API documentation for any external services involved
2. If a `/fetch-api-docs` skill is available, use it for curated API references
3. Search for best practices, common patterns, and known pitfalls
4. Find prior art — how do other projects solve this?

[MEMORY_INJECTION_BLOCK]

Write your findings in this exact format:

## External Researcher — [FOCUS_DESCRIPTION]
### Findings
- Finding 1 (source: URL or doc reference)
- Finding 2 (source: URL or doc reference)
### Open Questions
- What I couldn't determine...
### Connections
- This relates to [codebase area] because...

Report in under 500 words. Cite sources for every finding.
```

### Integration Mapper

**Subagent type:** `Explore`
**Tools:** Glob, Grep, Read, LS
**Focus:** Data flow across service boundaries, dependency mapping, integration points.

**Prompt template:**
```
Think harder about this research question: [RESEARCH_QUESTION]

Focus area: [FOCUS_DESCRIPTION]

Your role: Integration Mapper — trace how data flows across boundaries in this system.

Map systematically:
1. Identify all service/module boundaries this feature touches
2. Trace data transformations at each boundary (input shape → output shape)
3. Map external dependencies (APIs, databases, queues, caches)
4. Document error propagation — how failures in one layer surface in others

[MEMORY_INJECTION_BLOCK]

Write your findings in this exact format:

## Integration Mapper — [FOCUS_DESCRIPTION]
### Findings
- Finding 1 (source: exact/file/path.py:line)
- Finding 2 (source: exact/file/path.py:line)
### Open Questions
- What I couldn't determine...
### Connections
- [Service A] → [Service B]: [data shape], [error handling]

Report in under 500 words. Be specific about data shapes and error paths.
```

### History Analyst

**Subagent type:** `general-purpose`
**Tools:** Bash (git log, git blame, git show), Read
**Focus:** Why things are the way they are — past decisions, regressions, evolution.

**Prompt template:**
```
Think harder about this research question: [RESEARCH_QUESTION]

Focus area: [FOCUS_DESCRIPTION]

Your role: History Analyst — understand WHY the code is structured this way.

READ-ONLY CONSTRAINT — you have Bash access, but ONLY for git history inspection. The allowed commands are a closed set:

- `git log` (any flags)
- `git blame` (any flags)
- `git show` (any flags)
- `git diff` (read-only diffs between refs, files, or working tree)
- `git rev-parse` (any flags)
- `git rev-list` (any flags)

**Every other command is forbidden.** This is a pure allowlist — if a command is not on the list above, do not run it. That includes (non-exhaustively): any git command that mutates state (checkout, reset, rebase, commit, push, pull, stash, merge, cherry-pick, restore, switch, tag, branch -d, worktree); any filesystem mutation (rm, mv, cp, mkdir, touch, chmod); any package or env mutation (npm/pip/bun/yarn/brew install, pip uninstall, npm run, make); any shell metaprogramming that could obscure intent (eval, source, exec).

If you need information that would require a forbidden command, report it as an open question in your findings instead of running the command.

(Rationale: belt-and-suspenders with subagent_type scoping — defense in depth. Other researchers use the Explore subagent type, which is inherently read-only; History Analyst needs Bash for git, which opens the destructive-command vector. A pure allowlist is more robust than an enumerated denylist — a denylist is only as complete as the author's imagination.)

Investigate systematically:
1. git log for the key files — who changed them, when, and why (read commit messages)
2. git blame on critical sections — when was this pattern introduced?
3. Look for reverted commits, fixup commits, or "fix:" messages that signal past problems
4. Check for PR references in commit messages — read PR descriptions for design rationale

[MEMORY_INJECTION_BLOCK]

Write your findings in this exact format:

## History Analyst — [FOCUS_DESCRIPTION]
### Findings
- Finding 1 (source: commit abc1234 — "commit message excerpt")
- Finding 2 (source: PR #N — rationale)
### Open Questions
- What I couldn't determine...
### Connections
- This decision was made because [historical context]

Report in under 500 words. Cite specific commits and PRs.
```

---

## Default Researcher Selection

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

The orchestrator MAY override defaults when the specific research question clearly needs a different mix.

---

## Wave Logic

### Wave 1 — Parallel Dispatch

Dispatch all selected researchers simultaneously using the Agent tool. Each researcher gets:
- The research question
- Their specific focus area (derived from task classification)
- Memory-injection block (if in workflow context)
- The scratchpad format template

### Gap Detection (Orchestrator)

After all Wave 1 agents return, the orchestrator reads their outputs and checks:

1. **Unanswered questions:** Are there open questions from one researcher that another researcher type could answer?
2. **Uncovered areas:** Did a researcher reference a system/area that no other researcher explored?
3. **Contradictions:** Do any findings from different researchers conflict?
4. **Critical unknowns:** Is there a low-confidence finding on something critical to the research question?

**Decision:**
- If ANY gap detected → dispatch Wave 2 with 1-2 targeted researchers and specific gap-fill prompts
- If NO gaps → skip to synthesizer

### Wave 2 — Targeted Gap-Fill

Wave 2 researchers receive:
- The original research question
- ALL Wave 1 findings (full scratchpad)
- Specific gap-fill instructions: "Wave 1 found X but couldn't determine Y. Your job is to answer Y."
- The same output format as Wave 1 researchers (Findings / Open Questions / Connections sections defined in each researcher's prompt template above)

### Skip Conditions

When called from claude-flow:
- `fast` or `lite` path → skip research entirely (use current single-executor exploration)
- `full` or `complex` path → run research team

When called standalone:
- Always run (user explicitly asked for research)

---

## Synthesizer

**Subagent type:** `general-purpose`
**Model:** `sonnet`

The synthesizer reads ALL scratchpad entries (Wave 1 + Wave 2 if applicable) and produces the research brief.

**Prompt template:**
```
Think harder about synthesizing these research findings.

Research question: [RESEARCH_QUESTION]

## All Research Findings:
[FULL SCRATCHPAD — all Wave 1 + Wave 2 entries concatenated]

Your job: Synthesize these findings into a unified research brief. For EVERY finding:
- Cross-reference across researchers — do multiple sources confirm it?
- Assign a confidence level:
  - **verified**: confirmed in code AND docs/tests, or by multiple independent researchers
  - **inferred**: reasonable conclusion from evidence, but not directly confirmed
  - **assumed**: couldn't verify; flag for defensive design
- Identify contradictions and resolve them (or flag as unresolved)
- Extract architecture-relevant constraints

Output format:

# Research Brief: [TOPIC]

## Key Findings
- [Finding] (confidence: verified|inferred|assumed) — [1-line evidence summary]
- ...

## Architecture-Relevant Constraints
- [Constraint the architect must account for]
- ...

## Open Risks
- [Assumption that couldn't be verified] (confidence: assumed)
- ...

## Sources
- [file/url/commit references organized by topic]

Be ruthless about confidence scoring. "Verified" means MULTIPLE sources confirm it. When in doubt, downgrade to "inferred" or "assumed".
```

---

## Integration with claude-flow

When called from Phase 2:

1. The workflow passes the task description and path classification
2. Research skill runs its full pipeline (classify → Wave 1 → gap detection → Wave 2 → synthesize)
3. Research brief is returned to the workflow
4. The brief replaces the current exploration output
5. The Opus advisor checkpoint (Step 3 of Phase 2) reviews the research brief
6. Confidence scores are included in the `$exploration` variable that feeds Phases 3-6

When called standalone:

1. User invokes `/research "question"`
2. Orchestrator classifies and dispatches
3. Research brief is displayed directly to the user
4. No workflow integration, no phase transitions

---

## Next Steps

- **Ready to build from findings?** Use `/claude-flow` to run the full implementation pipeline (research feeds Phase 3 automatically).
- **Need to capture a dead end?** Use `/session-handoff --abandon` to document what didn't work before moving on.
- **Want to verify assumptions?** If `/fetch-api-docs` is available, use it to pull authoritative API docs for any external service referenced in findings.
