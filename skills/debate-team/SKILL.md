---
name: debate-team
description: Unified review skill with auto-tiering — absorbs PlanCraft. Tier 1 (DeepSeek scope check), Tier 2 (DeepSeek + GPT-4o dual critic), Tier 3 (full tri-model debate with Sonnet Generator + Opus Lead). Conditional Haiku Style critic for frontend.
---

# Unified Review — Debate Team

Cross-model adversarial review for plans and code. Three tiers auto-selected by complexity gate. Plans always get full debate (Tier 3). Code reviews scale from scope check to full debate based on file count, schema changes, and security sensitivity.

> **Absorbed PlanCraft:** Scope-check filtering (`OUT_OF_SCOPE` rejection) runs on every DeepSeek call at all tiers. PlanCraft as a standalone skill is archived.

## Setup

- Set **DEEPSEEK_API_KEY** and **OPENAI_API_KEY** in your environment (or a documented secure source). The script reads keys only from the environment; never put keys in plan files, scope files, or logs.
- The debate protocol is **single-user and serial** (one debate at a time). Fixed paths `/tmp/debate_artifact.md` and `/tmp/debate_scope.md` are acceptable; for parallel runs use unique paths (e.g. timestamp or UUID).

## When to Use

- **All plan/architecture reviews** → Tier 3 (full debate, always)
- **Bug fix plans** touching 3+ files or crossing service boundaries → Tier 3
- **Code reviews** with 3+ files or cross-cutting concerns → Tier 2 (dual critic)
- **Simple code reviews** (1-2 files, no schema/security) → Tier 1 (scope check)
- **User says "debate this"** → forces Tier 3
- **User says "quick review"** → forces Tier 1

## When NOT to Use

- User says "skip debate" — bypasses entirely
- Brainstorming phase (stays interactive with user)
- Implementation phase (TDD provides its own feedback loop)

## Team Composition

| Role | Model | Type | When |
|------|-------|------|------|
| Generator | Sonnet (teammate) | Agent Teams | Always |
| Bug-Hunter | DeepSeek (API) | External | Always |
| Architecture | GPT-4o via `--reviewer codex` (API) | External | Code artifacts only |
| Completeness | GPT-4o via `--reviewer codex-docs` (API) | External | Non-code artifacts only |
| Style/UI | Haiku (teammate) | Agent Teams | Frontend changes only |
| Lead/Judge | Opus (you) | Lead | Always |

**GPT-4o role routing:** The artifact type determines which GPT-4o critic role runs (never both):
- **Code artifacts** (touches `app/`, `tests/`, `*.py`, `*.js`, `*.css`, `*.html`) → Architecture critic (`--reviewer codex`): separation of concerns, abstraction quality, pattern consistency.
- **Non-code artifacts** (skills, docs, CLAUDE.md, MEMORY.md, process specs) → Completeness critic (`--reviewer codex-docs`): missing steps, contradictions, stale references, term consistency.

## Protocol

### Step 1: Complexity Gate (Auto-Tiered)

Assess the artifact and select tier:

```
IS_PLAN = artifact path matches docs/plans/*.md OR caller passes --type plan
IS_BUG_FIX_PLAN = IS_PLAN AND artifact describes a bug fix
IS_CODE = artifact touches app/**, tests/**, *.py, *.js, *.css, *.html (code files)
IS_NON_CODE = NOT IS_CODE (skills, docs, CLAUDE.md, MEMORY.md, process specs)
FILE_COUNT = number of files touched/proposed
HAS_SCHEMA = touches models or migrations
HAS_SECURITY = touches auth, tokens, permissions
HAS_FRONTEND = touches templates, CSS, JS
HAS_BACKEND = touches routes, services

Tier 3 (Full Debate) if:
  IS_PLAN
  OR (IS_BUG_FIX_PLAN AND (FILE_COUNT >= 3 OR cross-service))
  OR (HAS_SCHEMA AND HAS_SECURITY)
  OR (HAS_FRONTEND AND HAS_BACKEND)
  OR user says "full debate"

Tier 2 (Dual Critic) if:
  FILE_COUNT >= 3
  OR cross-cutting concerns
  OR external API integration

Tier 1 otherwise (or user says "quick review")
```

**Tier routing:**
- **Tier 1:** Skip to Step 3 (DeepSeek only, no Generator, no GPT-4o, no synthesis). Run DeepSeek Bug-Hunter with `OUT_OF_SCOPE` filtering. Output: Pass/flag list.
- **Tier 2:** Skip to Step 3 (DeepSeek + GPT-4o in parallel, no Generator). Output: Adopt/Reject/Defer per finding via Step 4.
- **Tier 3:** Full protocol — Step 2 (Generator) → Step 3 (all critics) → Step 4 (synthesis) → Step 5 (present).

Announce: "Running debate-team Tier [N] — [reason]."

### Step 2: Generate Proposal

Spawn the **Generator** (Sonnet teammate) with the task context:

```
Use Task tool:
  subagent_type: general-purpose
  model: sonnet
  name: generator
  prompt: [full task context + "Write a complete [plan/code] proposal. Save to /tmp/debate_artifact.md"]
```

Wait for Generator to complete. Read the artifact.

### Step 3: Dispatch Critics (Parallel)

Run ALL applicable critics in parallel (one message, multiple tool calls):

**Always run — DeepSeek Bug-Hunter + GPT-4o (role varies by artifact type, parallel Bash calls):**

```bash
# DeepSeek Bug-Hunter (always)
python3 ~/.claude/scripts/plancraft_review.py \
  --reviewer deepseek \
  --plan-file /tmp/debate_artifact.md \
  --scope-file /tmp/debate_scope.md

# GPT-4o — pick ONE based on IS_CODE / IS_NON_CODE:

# If IS_CODE → Architecture critic (parallel)
python3 ~/.claude/scripts/plancraft_review.py \
  --reviewer codex \
  --plan-file /tmp/debate_artifact.md \
  --scope-file /tmp/debate_scope.md

# If IS_NON_CODE → Completeness/Consistency critic (parallel)
python3 ~/.claude/scripts/plancraft_review.py \
  --reviewer codex-docs \
  --plan-file /tmp/debate_artifact.md \
  --scope-file /tmp/debate_scope.md
```

**Claude Batch Reviewer (Tiers 2-3 only):**

**Prerequisite:** `python3 -c "import anthropic"` succeeds and `ANTHROPIC_API_KEY` is set.

Run in parallel with DeepSeek + GPT-4o:
```bash
python3 ~/.claude/scripts/batch_review.py \
  --mode plan-review \
  --artifact-file /tmp/debate_artifact.md \
  --scope-file /tmp/debate_scope.md \
  --timeout 300
```

If batch completes before synthesis step: merge findings into Step 4.
If batch times out or errors: proceed without (graceful degradation).
User says `"skip batch"`: omit the Claude batch reviewer (keeps DeepSeek + GPT-4o only).

**Conditionally run — Haiku Style/UI (if frontend changes detected):**

Check if artifact references files matching: `*.html`, `*.css`, `*.js`, `templates/**`, `static/css/**`

If yes, spawn Haiku teammate:
```
Use Task tool:
  subagent_type: general-purpose
  model: haiku
  name: style-critic
  prompt: [Style/UI critic prompt from critics/haiku-style-ui.md + the artifact]
```

### Step 4: Synthesize

#### Anti-Sycophancy Protocol

Before classifying findings, the Lead MUST:

1. **Read each critic's output in isolation** — Form a preliminary ADOPT/REJECT per finding BEFORE reading the next critic's output. This prevents anchoring on the first opinion.
2. **Weight lone dissent heavily** — If all critics flag the same issue, that's signal. If only ONE critic flags it, give it EXTRA attention (not less) — lone dissent often catches what groupthink misses.
3. **Challenge your own ADOPTs** — For each ADOPT decision, ask: "Would I still adopt this if no critic had flagged it?" If no, downgrade to DEFER.

#### Classification

Read all critic outputs. For EACH finding:

| Decision | When |
|----------|------|
| **ADOPT** | Finding is valid, actionable, in-scope |
| **REJECT** | False positive or already addressed |
| **DEFER** | Valid but needs user decision (trade-off, preference, or pre-existing fix that would significantly expand the PR) |

Produce a **Changelog table**:
```
| Source | Finding | Decision | Reasoning |
|--------|---------|----------|-----------|
| DeepSeek | N+1 query in Task 3 | ADOPT | Add .joinedload() |
| GPT-4o | Over-abstracted service layer | REJECT | Matches existing pattern |
| Haiku | Hardcoded font-size | ADOPT | Use var(--ds-text-sm) |
```

### Step 4.5: Devil's Advocate Challenge (Tier 3 Only)

<SKIP-CONDITION>
Skip for Tier 1 and Tier 2 reviews — the cost of an extra agent pass isn't justified for simple reviews.
</SKIP-CONDITION>

For Tier 3 (full debate), challenge the synthesis before presenting to the user. This catches false positives that survived synthesis — style preferences masquerading as bugs, fixes that introduce worse problems, or groupthink where multiple critics echo the same flawed reasoning.

Dispatch a **haiku** agent:

```
Use Task tool:
  subagent_type: general-purpose
  model: haiku
  prompt: |
    You are a devil's advocate reviewer. Your job is to challenge these ADOPT decisions:

    [list of ADOPT findings with reasoning from Step 4]

    For each ADOPT, argue why it might be WRONG:
    - Is this a false positive disguised as a real issue?
    - Does the "fix" introduce worse problems than the original?
    - Is this a style preference masquerading as a bug?
    - Did multiple critics flag this for the same flawed reason (echo, not independent signal)?

    Be adversarial. Only flag findings where you have >70% confidence the ADOPT is wrong.
    Output format: one line per challenged finding with your counter-argument.
    If all ADOPTs are solid, say "No challenges — findings are sound."
```

**Triage devil's advocate output:**
- Challenge is convincing → downgrade ADOPT to DEFER (let user decide)
- Challenge is weak → keep ADOPT (finding survived adversarial review)
- **Max 2 downgrades per round** — prevents wholesale reversal of the synthesis

**Cost:** ~$0.01 per haiku pass. Negligible relative to the Tier 3 cost of ~$0.15-0.35.

### Step 5: Present to User

Show the user:
1. **The final artifact** (with all ADOPT fixes applied)
2. **The Changelog** (adopt/reject/defer with reasoning)
3. **Any DEFER items** that need user decision
4. **Devil's advocate challenges** (if any ADOPTs were downgraded, show the counter-argument)

### Step 6: Auto-Fix Loop (PR Review Only)

If reviewing a PR and CRITICAL findings were adopted:

1. Assign fixes to Generator (Sonnet teammate)
2. Generator commits fixes
3. Re-run critics on updated diff
4. **Max 2 cycles** — if unresolved after 2, escalate to user

## Cost Budget

| Tier | Critics | Cost per round | With Claude batch | Token cap |
|------|---------|---------------|-------------------|-----------|
| 1 (Scope Check) | DeepSeek only | ~$0.03 | ~$0.03 (no batch) | 15,000 |
| 2 (Dual Critic) | DeepSeek + GPT-4o (Architecture OR Completeness) | ~$0.08 | ~$0.13 (+Claude batch) | 15,000 per critic |
| 3 (Full Debate) | DeepSeek + GPT-4o (role-routed) + Haiku (conditional) + Sonnet Generator + Opus Lead | ~$0.15-0.35 | ~$0.22-0.40 (+Claude batch) | 15,000 per external critic |

Claude batch adds ~$0.05 per round (2 Sonnet reviews at 50% batch discount).
Net cost increase per round is modest; provides a third independent model perspective.

- Max per feature (3 full debate rounds): ~$1.20
- Tier 1 drops GPT-4o entirely — acceptable for 1-2 file changes
- GPT-4o cost is the same regardless of role (Architecture vs Completeness) — the routing only changes the prompt, not the model or token cap

## Critic Calibration (Eval-Driven Tuning)

Over multiple debate rounds, track critic accuracy to calibrate prompts. This applies the Claude Cookbook's [Building Evals](https://platform.claude.com/cookbook/misc-building-evals) and [Tool Evaluation](https://platform.claude.com/cookbook/tool-evaluation-tool-evaluation) patterns to reviewer agents.

### Tracking Critic Signal Quality

After each debate round, the Lead (Opus) already classifies findings as ADOPT/REJECT/DEFER. This classification **is the eval signal** — no separate evaluation infrastructure needed.

```
Per critic, track over time:
  - ADOPT rate: % of findings accepted as valid
  - REJECT rate: % of findings dismissed as false positives
  - DEFER rate: % of findings needing user judgment

Healthy critic: >60% ADOPT, <25% REJECT
Noisy critic:   <40% ADOPT, >40% REJECT → needs prompt tuning
Silent critic:  Rarely produces findings → may not be adding value
```

### When to Tune a Critic Prompt

| Signal | Action |
|--------|--------|
| REJECT rate >40% over 5+ rounds | Critic is generating noise. Review its prompt for over-broad patterns. Add "Only flag if you are >80% confident this is a real issue" constraint. |
| Same false positive type recurring | Add an explicit exclusion to the critic prompt: "Do NOT flag [pattern] — this is an accepted convention in this codebase." |
| Missing real issues (caught later) | Critic is under-sensitive. Add the missed pattern to the critic's checklist with an example. |
| ADOPT rate <30% | Consider demoting critic to conditional-only (skip for simple reviews) or replacing with a more targeted prompt. |

### Grading Method Priority (from Building Evals recipe)

For automated calibration:
1. **Code-based grading** (preferred) — If the finding references a specific code pattern, grep for it. If the pattern doesn't exist in the diff, it's a false positive. Zero cost.
2. **Lead-based grading** (current) — Opus Lead's ADOPT/REJECT is the grading function. Already implemented in Step 4 synthesis.
3. **User grading** (gold standard) — When user overrides Lead's ADOPT/REJECT decision, that's the highest-quality signal. Capture it in session-learnings.

### Calibration Cadence

Don't tune after every round. Aggregate over 5+ debate rounds, then:
1. Compute ADOPT/REJECT rates per critic
2. Identify the noisiest critic (highest REJECT rate)
3. Review its last 5 REJECTed findings — what pattern do they share?
4. Make ONE prompt change (following claude-flow's one-change principle)
5. Run 3+ rounds with the new prompt to verify improvement

This is the evaluator-optimizer loop applied to the debate team's own critics.

## Debugging

- If a critic run fails: re-run the same `plancraft_review.py` command with the same `--plan-file` and `--scope-file`, then inspect the JSON output. The `error` key (if present) explains the failure (e.g. missing API key, API timeout).
- If a batch review fails: re-run `batch_review.py` with the same `--artifact-file` and `--scope-file`. Check the JSON `error` key. Common causes: `anthropic` not installed, `ANTHROPIC_API_KEY` not set (check shell profile sourcing), batch timeout (increase `--timeout`).

## Extending: Adding New Critics

1. Create `debate-team/critics/<name>.md` following the frontmatter schema
2. Set `activation: always` or `activation: conditional` with `triggers`
3. The registry auto-discovers new files — no code changes needed

Full architecture: see CourierFlow repo `docs/plans/2026-03-07-tri-model-debate-team-design.md` (if present).
