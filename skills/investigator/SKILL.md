---
name: investigator
description: Structured problem investigation that collects evidence without proposing solutions. Use when debugging, diagnosing unexpected behavior, or when a Phase 5 TDD cycle hits failures that aren't immediately obvious. Outputs an evidence matrix — the caller decides what to do with it.
user-invocable: true
---

# Investigator

## Purpose

Collect and organize evidence about a problem **without proposing solutions**. This separation matters because jumping to fixes before evidence is gathered leads to fix-retry loops — especially for complex bugs where the first hypothesis is usually wrong.

**What this skill does:** Systematically gathers facts from 6 source types, compares working vs. broken implementations, and outputs a structured evidence matrix.

**What this skill does NOT do:** Diagnose root causes, propose fixes, or prioritize hypotheses. The caller (user or workflow) owns that.

**Announce:** "Running investigator — collecting evidence across code, git, config, deps, docs, and external sources."

---

## When to Use

- Bug report or unexpected behavior — before jumping to a fix
- Phase 5 TDD failure that isn't immediately obvious (test fails and the reason isn't clear from the error message alone)
- Production incident — gather facts before the postmortem
- "It works in staging but not in prod" — systematic comparison needed
- Any time you catch yourself guessing at a fix without evidence

## Input

The caller provides:
- **Problem description:** What's happening vs. what should happen
- **Affected area:** File paths, endpoints, or feature area (if known)
- **Optional investigation focus:** Specific angles to prioritize (e.g., "check if the migration ran", "compare with the working endpoint")

If the input is unclear, adopt the most reasonable interpretation and note: "Investigation target: interpreted as [X]"

---

## Investigation Workflow

### Step 1: Classify the Problem

Determine the problem type — this shapes the investigation strategy:

| Type | Signal | Strategy |
|------|--------|----------|
| **Change failure** | "It broke after X" / recent deploy / recent merge | Diff-centric: compare before vs. after the change |
| **New discovery** | "This has never worked" / "I just noticed X" | Breadth-first: map the current state without a baseline |
| **Regression** | "This used to work, now it doesn't" (no clear change) | Timeline-centric: binary search git history for the breaking commit |
| **Environment gap** | "Works locally, fails in [staging/prod]" | Environment-centric: diff configs, versions, data |

### Step 2: Collect Evidence from 6 Source Types

For each source type below, perform the **minimum investigation actions**. Record findings even when empty ("Checked [source], no relevant findings"). Empty results are evidence too — they rule out categories.

#### Source 1: Code

```
- Read files directly related to the problem
- Grep for error messages, function names, class names from the problem report
- Trace the call chain: entry point → handler → service → model
- Note: parameter types, return types, error handling patterns
```

#### Source 2: Git History

```
- git log --oneline -20 <affected files>
- For change failures: git diff <working-commit>..<broken-commit> -- <affected files>
- For regressions: git log --all --oneline --since="2 weeks ago" -- <affected files>
- Note: who changed what, when, and the commit message (intent)
```

#### Source 3: Dependencies

```
- Check package manifest (requirements.txt, package.json, pyproject.toml)
  for the libraries involved in the problem area
- If version mismatch suspected: check changelog/release notes for breaking changes
- Check lock file for transitive dependency version changes
```

#### Source 4: Configuration

```
- Read config files in the affected area (.env, settings, YAML configs)
- Grep for relevant config keys across the project
- For environment gaps: diff configs between environments
- Note: any config values that look wrong, missing, or different from docs
```

#### Source 5: Design Docs and Plans

```
- Glob for plans/PRP-*.md, docs/plans/*.md related to the affected area
- Check MEMORY.md for gotchas related to this domain
- Read any design docs that describe the intended behavior
- Note: does the current behavior match what the design docs specify?
```

#### Source 6: External Documentation

```
- Search official docs for the primary technology involved
- If error message is present: search for the exact error message
- Check version-specific docs (current version, not latest)
- Note: any documented gotchas, known issues, or migration guides
```

### Step 3: Comparison Analysis

If a working reference exists (working endpoint, working environment, prior working commit), diff it against the broken version:

```
Compare:
- Call order / execution flow
- Initialization / setup steps
- Configuration values
- Data shapes (input/output)
- Error handling patterns
- Dependency versions

Note every difference — even ones that seem irrelevant. The caller filters.
```

If no working reference exists, note that — it means the evidence matrix will rely on documentation and code analysis rather than comparison.

### Step 4: Assemble Evidence Matrix

Format findings as a structured matrix:

```markdown
## Evidence Matrix: [Problem Description]

**Problem type:** [change failure | new discovery | regression | environment gap]
**Affected area:** [file paths / endpoints / feature]
**Investigation date:** [date]

### Factual Observations

| # | Source | Finding | Confidence |
|---|--------|---------|------------|
| 1 | Code | [observation] | high/medium/low |
| 2 | Git | [observation] | high/medium/low |
| ... | ... | ... | ... |

### Comparison Analysis (if applicable)

| Aspect | Working | Broken | Different? |
|--------|---------|--------|------------|
| [aspect] | [value] | [value] | yes/no |

### Sources Checked With No Findings

- [source]: checked [what], found nothing relevant

### Open Questions

- [question that couldn't be answered from available sources]
```

**Confidence levels:**
- **High:** Directly observed in code, logs, or git diff
- **Medium:** Inferred from documentation or pattern analysis
- **Low:** Based on external docs or indirect evidence

---

## Integration with claude-flow

When Phase 5 TDD hits an unexpected failure:

```
Test fails → error message isn't self-explanatory
        │
        ▼
  Instead of immediately retrying or guessing a fix:
  1. Run /investigator with the test failure as input
  2. Review the evidence matrix
  3. THEN propose and implement a fix based on evidence
```

This prevents the "try random fixes until tests pass" anti-pattern that wastes tokens and can introduce new bugs.

---

## Output Scope

This skill outputs **evidence and observations only**. It does NOT output:
- Root cause analysis
- Fix recommendations
- Priority rankings of hypotheses
- "I think the problem is X" statements

The evidence matrix is the deliverable. What happens next is the caller's decision.

---

## Next Steps

- **Ready to fix the bug?** Use `/bug-fix` — it consumes the evidence matrix and runs Reproduce → Diagnose → Fix → Verify.
- **Evidence reveals a missing feature?** Use `/claude-flow` to build it through the full 6-phase pipeline.
- **Need to capture what you learned?** Use `/session-learnings` to persist findings to memory before ending the session.
