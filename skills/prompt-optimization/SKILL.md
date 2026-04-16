---
name: prompt-optimization
description: Analyze prompt performance across explorers, architects, and reviewers. Promote winners, generate challengers. Triggered by session-learnings or manually.
user-invocable: true
---

# Prompt Optimization

## Overview

Closed-loop optimization for subagent prompts across three agent types:

- **Explorers** (Phase 2) — A/B tested using F1 scores (precision + recall of discovered files)
- **Architects** (Phase 4) — Tracked by selection rate, plan convergence speed, and review issue count
- **Reviewers** (Phase 6) — Tracked by true positive rate and signal-to-noise ratio

Each agent type has its own variant pool, event log, and scoring model. The goal: prompts get measurably better over time across the entire workflow.

**Invoke:** After session-learnings, or manually with `/prompt-optimization`.

---

## When This Skill Triggers

1. **Automatic:** session-learnings detects exploration events in `memory/episodic/exploration-events.jsonl` for the current session
2. **Manual:** User runs `/prompt-optimization` to review performance data

---

## The Process

### Step 1: Update Metrics

Run the tracker to recompute all variant metrics from event history across all agent types:

```bash
python3 ~/.claude/scripts/prompt-tracker.py update-metrics
```

### Step 2: Generate Report

```bash
# Full report (all agent types)
python3 ~/.claude/scripts/prompt-tracker.py report

# Or filter to a specific type
python3 ~/.claude/scripts/prompt-tracker.py report explorer
python3 ~/.claude/scripts/prompt-tracker.py report architect
python3 ~/.claude/scripts/prompt-tracker.py report reviewer
```

Present the report to the user. Key things to highlight:

**Explorers:** Which variants have highest F1, promotion readiness, most commonly missed files
**Architects:** Which optimization target users prefer (selection rate), convergence speed, resulting code quality
**Reviewers:** Which review style finds more real issues (true positive rate) vs noise (false positives)

### Step 3: Check for Promotions (CI-Aware)

Promotions now use **statistical confidence intervals** instead of raw score gaps. A variant wins only when the evidence is significant — not just when it's ahead on average.

```bash
# Run CI-aware promotion check
python3 scripts/stat-eval.py promote <agent_type> <category>

# Also check behavioral consistency and flakiness
python3 scripts/stat-eval.py consistency <agent_type> <category>
python3 scripts/stat-eval.py flakiness <agent_type> <category>
```

**Promotion criteria (any of):**
1. Winner's CI lower bound exceeds challenger's CI upper bound (CI dominance)
2. Both variants have 10+ sessions AND chi-squared p-value < 0.05 AND winner mean > challenger mean

**Block promotion if:**
- Either variant has behavioral consistency < 0.5 (unstable — investigate first)
- Winner has flakiness > 0.6 (unreliable — run more sessions)
- Regression detected against baseline (`stat-eval.py regression`)

If promoted:
1. Update `current_best_A` / `current_best_B` in prompt-variants.json
2. Update `prompt-library.md` with the winning prompt text
3. Announce: "Promoted {variant_id} as best for {category}/{role} (mean: {score}, CI: [{lo}, {hi}])"

### Step 3.5: Trace-Sample Error Analysis (Before Drafting Challengers)

Aggregate metrics tell you *which* variant lost, not *why*. Before synthesizing a challenger, do a brief manual review so the challenger is grounded in actual failure modes rather than the winner's surface differences.

```bash
# Sample 20 traces (or all, if fewer) from the losing variant's event log
python3 ~/.claude/scripts/prompt-tracker.py sample-traces \
    <agent_type> <variant_id> --n 20
```

For each sampled trace, write ONE sentence about the earliest observable failure (the "open coding" pass — see Hamel Husain's error-analysis workflow for the technique). Stop at the first error per trace; downstream errors are usually consequences, not causes.

Aggregate the notes into error categories (3-7 buckets). Count each bucket. The top 2-3 buckets are the challenger's target — everything else is noise.

**When to skip:** If the loser has < 10 sessions, skip this step and just use aggregate metrics — there isn't enough signal to warrant manual review.

**Why it matters:** Aggregate F1 gives a correct answer to the wrong question. A challenger that only copies the winner's surface structure will often regress on cases the winner also handles poorly. Counting beats vibes.

### Step 4: Generate Challengers (User Approval Required)

For each losing variant:

1. Analyze its miss patterns — what files does it consistently miss? (Use the Step 3.5 bucket counts; they give you the concrete failure modes.)
2. Analyze the winning variant — what does it do differently?
3. Draft a challenger prompt that addresses the loser's blind spots while keeping its unique strengths
4. Present the challenger to the user for approval

**Challenger generation prompt:**

```
This explorer prompt scored avg F1={loser_f1} over {sessions} sessions.
The winning prompt scored avg F1={winner_f1}.

LOSING PROMPT:
{loser_prompt}

WINNING PROMPT:
{winner_prompt}

COMMONLY MISSED FILES BY LOSER:
{missed_files_list}

TOP FAILURE BUCKETS FROM TRACE-SAMPLING (Step 3.5):
{bucket_counts}  # e.g. "schema-miss: 7, wrong-file-scope: 5, no-test-context: 3"

Rewrite the losing prompt to better discover these file types.
Keep the same exploration scope and thinking budget.
The rewrite should be a single paragraph instruction.
Return ONLY the rewritten prompt text, nothing else.
```

5. If user approves: create new variant in prompt-variants.json, deactivate the old loser

### Step 5: Summary

Output:
- Promotions made (if any)
- Challengers proposed (if any)
- Next milestone: "Need N more sessions for {category} to reach significance"

---

## Data Files

| File | Purpose |
|------|---------|
| `memory/procedural/prompt-variants.json` | Variant definitions + aggregate metrics (all agent types) |
| `memory/episodic/exploration-events.jsonl` | Explorer outcome data (Phase 2 → Phase 5) |
| `memory/episodic/architect-events.jsonl` | Architect outcome data (Phase 4 → Phase 6) |
| `memory/episodic/reviewer-events.jsonl` | Reviewer outcome data (Phase 6) |
| `scripts/prompt-tracker.py` | CLI for selection, recording, metrics, reporting |
| `scripts/stat-eval.py` | Statistical analysis: CIs, consistency, regression, calibration, flakiness |

---

## Score Definitions

### Explorers

```
precision = files_found_and_used / files_found        (less noise)
recall    = files_found_and_used / total_files_needed  (fewer misses)
f1        = harmonic mean of precision and recall
score     = f1 * (1 - retry_rate)                      (penalize bad exploration)
```

**Good exploration:** High precision (found files were useful) AND high recall (didn't miss critical files). The F1 score balances both.

### Architects

```
selection   = 1.0 if user chose this proposal, 0.0 otherwise
convergence = 1.0 - (refinement_rounds / 3.0)         (fewer rounds = better)
quality     = 1.0 - critical_penalty - total_penalty   (fewer review issues = better)
score       = (selection * 0.4) + (quality * 0.35) + (convergence * 0.25)
```

**Good architecture:** Users choose it, the plan converges quickly, and Phase 6 review finds few critical issues.

### Reviewers

```
true_positive_rate = issues_fixed / issues_found       (found real problems)
signal_to_noise    = (found - false_positives) / found (not just noise)
score              = true_positive_rate * signal_to_noise
```

**Good review:** High signal — issues found are real and worth fixing, not noise that wastes time.

---

## Promotion Thresholds

| Condition | Threshold |
|-----------|-----------|
| Minimum sessions per variant | 10 |
| F1 gap required for promotion | 0.05 |
| Maximum active variants per role | 2 |
| Challenger generation | Requires user approval |

---

## Integration

- **smart-exploration** calls `prompt-tracker.py select explorer <category> <role>` before dispatching explorers
- **claude-flow** Phase 2: selects explorer variants, records files_found
- **claude-flow** Phase 4: selects architect variants, records user choice
- **claude-flow** Phase 5: records files_used_in_impl for explorer scoring
- **claude-flow** Phase 6: records reviewer outcomes (issues found/fixed/dismissed), architect quality signal
- **session-learnings** triggers this skill when any event files have new entries
- **MCP server** exposes `get_prompt_performance` tool (accepts optional `agent_type` filter)

---

## Next Steps

- **Need more data for variant scoring?** Run `/claude-flow` on a real task — it auto-records explorer, architect, and reviewer performance events.
- **Want to see current standings?** Check `~/.claude/memory/prompt-variants.json` for variant win rates and F1 scores.
- **Ready to promote a winner?** Re-run `/prompt-optimization` after 10+ sessions per variant to trigger automatic promotion.
