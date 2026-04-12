# Research Team Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone `/research` skill with a multi-agent research team (staggered waves + confidence-scored synthesis) that also integrates into code-creation-workflow Phase 2 for full/complex tasks.

**Architecture:** Orchestrator (inline Sonnet) classifies the task, picks 2-4 researchers from a dynamic pool, dispatches Wave 1 in parallel, runs gap detection, optionally dispatches Wave 2 gap-fillers, then dispatches a synthesizer that produces a confidence-scored research brief. Composes with smart-exploration (task classification), memory-injection (gotcha wiring), and Context Hub (external API docs).

**Tech Stack:** Claude Code skills (SKILL.md markdown), Agent tool for subagent dispatch, existing smart-exploration categories and memory-injection infrastructure.

**Design Doc:** `docs/plans/2026-04-11-research-team-design.md`

---

### Task 1: Create the Research Skill Skeleton

**Files:**
- Create: `skills/research/SKILL.md`

**Step 1: Create the skill directory**

```bash
mkdir -p skills/research
```

**Step 2: Write the SKILL.md frontmatter and overview**

Create `skills/research/SKILL.md` with:

```markdown
---
name: research
description: Multi-agent research team with staggered waves and confidence-scored synthesis. Standalone skill for deep codebase + external research, also invoked by code-creation-workflow Phase 2 for full/complex tasks.
user-invocable: true
---

# Research

## Overview

Multi-agent research team that explores a question in depth across codebase, git history, external docs, and API references. Produces a confidence-scored research brief.

**Standalone:** `/research "your question here"`
**Integrated:** Called by code-creation-workflow Phase 2 when task path is `full` or `complex`.

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
**Tools:** WebSearch, WebFetch, Skill (for `/fetch-api-docs` Context Hub)
**Focus:** API docs, library references, best practices, prior art outside the codebase.

**Prompt template:**
```
Think harder about this research question: [RESEARCH_QUESTION]

Focus area: [FOCUS_DESCRIPTION]

Your role: External Researcher — find relevant information OUTSIDE the codebase.

Research systematically:
1. Search for official API documentation for any external services involved
2. Use the `/fetch-api-docs` skill (Context Hub) for curated API references if available
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
- Same scratchpad format template

### Skip Conditions

When called from code-creation-workflow:
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

## Integration with code-creation-workflow

When called from Phase 2:

1. The workflow passes the task description and path classification
2. Research skill runs the full pipeline (orchestrator → waves → synthesizer)
3. Research brief is returned to the workflow
4. The brief replaces the current exploration output
5. The Opus advisor checkpoint (Step 3 of Phase 2) reviews the research brief
6. Confidence scores are included in the `$exploration` variable that feeds Phases 3-6

When called standalone:

1. User invokes `/research "question"`
2. Orchestrator classifies and dispatches
3. Research brief is displayed directly to the user
4. No workflow integration, no phase transitions
```

**Step 3: Verify the skill file renders correctly**

Read back the file and confirm frontmatter is valid, all sections are present.

**Step 4: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat: add research skill skeleton with orchestrator, researcher pool, wave logic, and synthesizer"
```

---

### Task 2: Register the Research Skill in the Plugin

**Files:**
- Modify: `skills/research/SKILL.md` (already created in Task 1)

The skill is already user-invocable via its frontmatter (`user-invocable: true`). Claude Code discovers skills by scanning the `skills/` directory in the plugin. No additional registration needed in `plugin.json` — the plugin system auto-discovers skill directories.

**Step 1: Verify skill discovery**

Confirm the plugin structure expects skills in `skills/`:

```bash
ls skills/*/SKILL.md | head -5
```

Verify our new skill follows the same pattern as existing ones.

**Step 2: Commit** (if any changes needed)

```bash
git add -A && git commit -m "chore: register research skill in plugin"
```

---

### Task 3: Add the Phase 2 Integration Branch to code-creation-workflow

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md` (around line 492-611, Phase 2 section)

**Step 1: Read the current Phase 2 section**

Read `skills/code-creation-workflow/SKILL.md` lines 492-611 to understand the exact text we need to modify.

**Step 2: Add the research team branch**

After the Phase 2 heading (line 492) and before Step 0 (line 496), insert a routing decision:

```markdown
### Research Team Branch (Full/Complex Path Only)

When the task path is `full` or `complex` (set in Phase 1 Discovery):

1. **Invoke `/research` skill** with the task description as the research question
2. The research skill runs its full pipeline (classify → Wave 1 → gap detection → Wave 2 → synthesize)
3. **Receive the research brief** — this replaces the exploration output from Steps 1-2
4. **Skip to Step 3** (Advisor Checkpoint) — the Opus advisor reviews the research brief instead of raw exploration findings
5. The research brief's confidence scores are included in the `$exploration` variable

When the task path is `lite` or `fast`, the current single-executor exploration (Steps 0-2 below) runs unchanged.

> **Why branch here:** Research adds depth, breadth, and quality verification — but costs 3-6 agent round-trips. Lite/fast tasks don't need this overhead. The branch respects the existing path classification without replacing what works for simpler tasks.
```

**Step 3: Update the Advisor Checkpoint prompt (Step 3, ~line 587)**

Modify the advisor prompt template to handle research brief input. Add a conditional note:

```markdown
**If research brief was produced (full/complex path):**
Replace the "Key files read" and "Patterns discovered" sections with:
- The full research brief (Key Findings with confidence scores)
- Architecture-Relevant Constraints
- Open Risks

The advisor should pay special attention to "assumed" confidence findings and flag any that need resolution before Phase 4.
```

**Step 4: Update the `$exploration` variable documentation (~line 1099)**

Find the artifacts table row for `$exploration` and update to note that it may contain confidence-scored findings:

```markdown
| Phase 2 | `$exploration` | Key file paths + roles, patterns discovered, integration points, concerns. For full/complex tasks: confidence-scored research brief with verified/inferred/assumed findings. | Phases 3, 4, advisor prompts |
```

**Step 5: Run a basic validation**

```bash
# Verify SKILL.md is valid markdown (no broken formatting)
head -5 skills/code-creation-workflow/SKILL.md
# Verify the research branch text is present
grep -n "Research Team Branch" skills/code-creation-workflow/SKILL.md
```

**Step 6: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: integrate research team into code-creation-workflow Phase 2 for full/complex tasks"
```

---

### Task 4: Update the Transition Map and State Machine

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md` (transition map ~line 212, state machine section ~line 105)

**Step 1: Read the transition map**

Read `skills/code-creation-workflow/SKILL.md` lines 210-240 for the current transition map.

**Step 2: Add research sub-phase to Phase 2**

The research team runs within Phase 2 (not a separate phase), so the transition map doesn't need new phase entries. But we should update the step tracking to reflect research team progress.

Add to the step label documentation (or create it if not present):

```markdown
### Phase 2 Step Labels

| Step | Label (standard path) | Label (research team path) |
|------|----------------------|---------------------------|
| 1 | Prior knowledge check | Prior knowledge check |
| 2 | Compressed codebase context | Task classification |
| 3 | Executor explores directly | Wave 1 dispatch |
| 4 | Advisor checkpoint | Gap detection |
| 5 | — | Wave 2 dispatch (if needed) |
| 6 | — | Synthesis |
| 7 | — | Advisor checkpoint |
```

**Step 3: Update workflow-state.json agent tracking**

When the research team is active, the state file should track agent counts:
- `agents_spawned`: incremented per researcher dispatched
- `agents_completed`: incremented per researcher that returns
- `agents_failed`: incremented per researcher that errors

This is already supported by the existing state schema — no schema changes needed. Just note in the SKILL.md that the orchestrator should update these counts.

**Step 4: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: add research team step labels to Phase 2 state tracking"
```

---

### Task 5: Write Tests — Validate Skill Structure and Prompts

**Files:**
- Create: `tests/skills/test_research_skill.sh`

**Step 1: Write validation tests**

Create a shell script that validates the research skill:

```bash
#!/bin/bash
# tests/skills/test_research_skill.sh
# Validates the research skill structure and prompt templates

set -euo pipefail

SKILL_FILE="skills/research/SKILL.md"
ERRORS=0

echo "=== Research Skill Validation ==="

# Test 1: Skill file exists
if [ ! -f "$SKILL_FILE" ]; then
    echo "FAIL: $SKILL_FILE not found"
    ERRORS=$((ERRORS + 1))
else
    echo "PASS: Skill file exists"
fi

# Test 2: Frontmatter is valid
if head -1 "$SKILL_FILE" | grep -q "^---"; then
    echo "PASS: Frontmatter starts correctly"
else
    echo "FAIL: Missing frontmatter delimiter"
    ERRORS=$((ERRORS + 1))
fi

# Test 3: user-invocable is true
if grep -q "user-invocable: true" "$SKILL_FILE"; then
    echo "PASS: Skill is user-invocable"
else
    echo "FAIL: Skill must be user-invocable"
    ERRORS=$((ERRORS + 1))
fi

# Test 4: All 4 researcher types are defined
for researcher in "Codebase Explorer" "External Researcher" "Integration Mapper" "History Analyst"; do
    if grep -q "### $researcher" "$SKILL_FILE"; then
        echo "PASS: $researcher section found"
    else
        echo "FAIL: Missing $researcher section"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 5: Prompt templates contain required placeholders
for placeholder in "RESEARCH_QUESTION" "FOCUS_DESCRIPTION" "MEMORY_INJECTION_BLOCK"; do
    if grep -q "\[$placeholder\]" "$SKILL_FILE"; then
        echo "PASS: Placeholder [$placeholder] found in prompts"
    else
        echo "FAIL: Missing placeholder [$placeholder]"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 6: Scratchpad format is documented
if grep -q "### Findings" "$SKILL_FILE" && grep -q "### Open Questions" "$SKILL_FILE" && grep -q "### Connections" "$SKILL_FILE"; then
    echo "PASS: Scratchpad format documented"
else
    echo "FAIL: Incomplete scratchpad format"
    ERRORS=$((ERRORS + 1))
fi

# Test 7: Research brief format is documented
for section in "Key Findings" "Architecture-Relevant Constraints" "Open Risks" "Sources"; do
    if grep -q "## $section" "$SKILL_FILE"; then
        echo "PASS: Research brief section '$section' found"
    else
        echo "FAIL: Missing research brief section '$section'"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 8: Confidence levels are all defined
for level in "verified" "inferred" "assumed"; do
    if grep -q "**$level**" "$SKILL_FILE" || grep -q "\*\*$level\*\*" "$SKILL_FILE"; then
        echo "PASS: Confidence level '$level' defined"
    else
        echo "FAIL: Missing confidence level '$level'"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 9: Default researcher selection table exists
if grep -q "Default Researcher Selection" "$SKILL_FILE"; then
    echo "PASS: Default selection table found"
else
    echo "FAIL: Missing default researcher selection table"
    ERRORS=$((ERRORS + 1))
fi

# Test 10: Gap detection criteria documented
if grep -q "Gap Detection" "$SKILL_FILE"; then
    echo "PASS: Gap detection section found"
else
    echo "FAIL: Missing gap detection section"
    ERRORS=$((ERRORS + 1))
fi

# Test 11: Phase 2 integration documented
if grep -q "code-creation-workflow" "$SKILL_FILE"; then
    echo "PASS: Phase 2 integration documented"
else
    echo "FAIL: Missing Phase 2 integration docs"
    ERRORS=$((ERRORS + 1))
fi

# Test 12: Research Team Branch exists in code-creation-workflow
WORKFLOW_FILE="skills/code-creation-workflow/SKILL.md"
if grep -q "Research Team Branch" "$WORKFLOW_FILE"; then
    echo "PASS: Research Team Branch in code-creation-workflow"
else
    echo "FAIL: Missing Research Team Branch in code-creation-workflow"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=== Results: $((12 - ERRORS))/12 passed ==="
if [ $ERRORS -gt 0 ]; then
    echo "FAIL: $ERRORS test(s) failed"
    exit 1
else
    echo "ALL TESTS PASSED"
fi
```

**Step 2: Run the tests to verify they fail (TDD — skill doesn't exist yet if running fresh)**

```bash
chmod +x tests/skills/test_research_skill.sh
bash tests/skills/test_research_skill.sh
```

Expected: Tests that check skill file existence will fail if run before Task 1. After Task 1-4 are complete, all 12 should pass.

**Step 3: Commit**

```bash
mkdir -p tests/skills
git add tests/skills/test_research_skill.sh
git commit -m "test: add research skill structure validation tests"
```

---

### Task 6: Update README and Documentation

**Files:**
- Modify: `README.md` (skills table section)

**Step 1: Read the README skills section**

Find the skills listing in README.md.

**Step 2: Add research skill entry**

Add to the skills table:

```markdown
| `/research` | Multi-agent research team — staggered waves + confidence-scored synthesis. Deep codebase + external research. |
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add research skill to README"
```

---

### Task 7: Run Full Validation and Final Commit

**Step 1: Run the research skill tests**

```bash
bash tests/skills/test_research_skill.sh
```

Expected: ALL TESTS PASSED

**Step 2: Run any existing CI/validation**

```bash
# If quick_ci.sh exists in this repo
[ -f scripts/quick_ci.sh ] && bash scripts/quick_ci.sh || echo "No CI script found"
```

**Step 3: Verify git status is clean**

```bash
git status
git log --oneline -5
```

Expected: 5-6 commits covering Tasks 1-6, clean working tree.
