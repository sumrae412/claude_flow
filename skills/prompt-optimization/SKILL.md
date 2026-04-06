---
name: prompt-optimization
description: Analyze exploration prompt performance, promote winners, and generate challenger variants. Triggered by session-learnings after sessions that used Phase 2 exploration.
user-invocable: true
---

# Prompt Optimization

## Overview

Closed-loop optimization for Phase 2 explorer prompts. Compares A/B variants using F1 scores (precision + recall), promotes winners, and generates challenger prompts for losers. The goal: exploration prompts get measurably better over time.

**Invoke:** After session-learnings, or manually with `/prompt-optimization`.

---

## When This Skill Triggers

1. **Automatic:** session-learnings detects exploration events in `memory/exploration-events.jsonl` for the current session
2. **Manual:** User runs `/prompt-optimization` to review performance data

---

## The Process

### Step 1: Update Metrics

Run the tracker to recompute all variant metrics from event history:

```bash
python3 ~/.claude/scripts/prompt-tracker.py update-metrics
```

### Step 2: Generate Report

```bash
python3 ~/.claude/scripts/prompt-tracker.py report
```

Present the report to the user. Key things to highlight:
- Which variants are winning per category
- Whether any variants are ready for promotion (10+ sessions, F1 gap > 0.05)
- Most commonly missed files (indicates prompt blind spots)

### Step 3: Check for Promotions

For each category where both variants of a role have 10+ sessions:

1. Compare avg F1 scores
2. If gap > 0.05: the higher scorer wins
3. Update `current_best_A` / `current_best_B` in prompt-variants.json
4. Update `prompt-library.md` with the winning prompt text
5. Announce: "Promoted {variant_id} as best for {category}/{role} (F1: {score})"

### Step 4: Generate Challengers (User Approval Required)

For each losing variant:

1. Analyze its miss patterns — what files does it consistently miss?
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
| `memory/prompt-variants.json` | Variant definitions + aggregate metrics |
| `memory/exploration-events.jsonl` | Raw per-session outcome data |
| `scripts/prompt-tracker.py` | CLI for selection, recording, metrics, reporting |

---

## Score Definitions

```
precision = files_found_and_used / files_found        (less noise)
recall    = files_found_and_used / total_files_needed  (fewer misses)
f1        = harmonic mean of precision and recall
score     = f1 * (1 - retry_rate)                      (penalize bad exploration)
```

**Good exploration:** High precision (found files were useful) AND high recall (didn't miss critical files). The F1 score balances both.

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

- **smart-exploration** calls `prompt-tracker.py select` before dispatching explorers
- **code-creation-workflow** records files_found after Phase 2, files_used after Phase 5
- **session-learnings** triggers this skill when exploration events exist
- **MCP server** exposes `get_prompt_performance` tool for on-demand reporting
