# Self-Modification Engine

**Date:** 2026-04-07
**Status:** Approved

## Problem

Recurring patterns (same bug type, same correction, same high-retry domain) should translate into skill updates automatically. Today this only happens when the user manually runs `session-learnings` and approves each proposal inline. No mechanism accumulates evidence across sessions to surface patterns that only appear in aggregate.

## Goal

Auto-detect recurring patterns across accumulated event data and queue skill-update proposals for manual review. Never auto-apply.

## Trust model

**Auto-propose, manual approve.** Detector is deterministic and auditable. LLM content generation happens on demand via a `draft` command, separate from detection. User applies/rejects via CLI. Every apply backs up the target file for trivial revert.

## Architecture

### 1. Pattern detector — `scripts/pattern-detector.py`

Scans event files and emits proposals to `memory/proposed-skill-updates.jsonl`.

**Triggers:**

| Trigger | Signal | Threshold | Target |
|---------|--------|-----------|--------|
| `repeated_failure` | `failure-events.jsonl` error_class count | ≥3 across ≥3 sessions | Defensive skill (mapped by domain) |
| `repeated_correction` | session-learnings user-correction topics | ≥3 occurrences | Relevant skill (topic-mapped) |
| `high_retry_domain` | `exploration-events.jsonl` per-domain retry rate | >50% over ≥5 attempts | `code-creation-workflow` |
| `dead_pattern` | Pattern cited in skill, 0 hits in events | 30 days no matches | Flag (don't auto-remove) |

**Confidence scoring:** 0-1 based on evidence strength (occurrence count, session diversity, time span).

**Dedup:** Before creating a proposal, check if a pending or applied proposal already covers the same evidence fingerprint.

### 2. Proposal queue — `memory/proposed-skill-updates.jsonl`

Append-only JSONL. One proposal per line:

```json
{
  "id": "prop-2026-04-07-001",
  "detected_at": "2026-04-07T17:30:00Z",
  "trigger": "repeated_failure",
  "evidence": {
    "error_class": "async_in_sync_context",
    "occurrences": 4,
    "sessions": ["abc", "def", "ghi", "jkl"]
  },
  "proposed_action": "add_defensive_pattern",
  "target_file": "skills/defensive-backend-flows/SKILL.md",
  "content_stub": "Async call inside sync function — hit 4x across 4 sessions",
  "content": null,
  "confidence": 0.8,
  "status": "pending",
  "applied_at": null,
  "rejected_at": null,
  "reject_reason": null,
  "evidence_fingerprint": "repeated_failure:async_in_sync_context"
}
```

**Status lifecycle:** `pending` → (`drafted`) → `applied` or `rejected`

`content` is `null` until `draft` is run. `content_stub` is a short auto-generated summary for the detector output.

### 3. Review CLI — `scripts/review-proposals.py`

```bash
python3 scripts/review-proposals.py list                   # pending proposals only
python3 scripts/review-proposals.py list --all             # include applied/rejected
python3 scripts/review-proposals.py show <id>              # full proposal
python3 scripts/review-proposals.py draft <id>             # mark as draft-ready (user fills content manually or via subagent)
python3 scripts/review-proposals.py set-content <id> <file>  # load content from a file
python3 scripts/review-proposals.py apply <id>             # apply + backup target + mark applied
python3 scripts/review-proposals.py reject <id> "<reason>" # mark rejected
python3 scripts/review-proposals.py stats                  # counts by status/trigger
```

**Apply behavior:**
1. Backup target file to `memory/skill-backups/<timestamp>-<basename>`
2. Append `content` to target file
3. Mark proposal `status: applied`, `applied_at: <ts>`

### 4. Detector invocation

New file: `scripts/run-pattern-detection.sh` — calls the detector with sensible defaults, intended to be run after session-learnings or on a schedule.

```bash
scripts/run-pattern-detection.sh                  # scan all events, append new proposals
```

Skill documentation in `skills/code-creation-workflow/SKILL.md` mentions running it periodically.

## Non-goals

- Never auto-apply proposals
- No LLM content generation inside the detector (only `content_stub` auto-filled)
- No cross-skill coordination (one proposal = one target file)
- No automatic weekly digest / email
- No scheduled runner (user invokes manually or wires their own cron)
- No semantic diffs / arbitrary skill edits — append-only or flagged-for-review

## Safety rails

- **Deterministic detector** — pure function over event data, no LLM
- **Backups on apply** — every apply writes a copy to `memory/skill-backups/`
- **Deduplication** — `evidence_fingerprint` prevents proposal spam
- **Rejection memory** — rejected proposals stay in the queue as "previously rejected"; future detections with the same fingerprint reference it instead of creating a duplicate
- **Confidence floor** — proposals with confidence <0.3 are emitted but marked low-confidence in `list` output

## Implementation sketch

1. `scripts/pattern-detector.py` — ~250 lines: load events, run 4 trigger checks, emit proposals
2. `scripts/review-proposals.py` — ~200 lines: JSONL read/write, backup, apply, reject, stats
3. `scripts/run-pattern-detection.sh` — thin wrapper
4. `scripts/test_pattern_detector.py` — fixture event files + assertions
5. `scripts/test_review_proposals.py` — queue lifecycle tests
6. `memory/proposed-skill-updates.jsonl` — empty initial file
7. `memory/skill-backups/` — gitignored directory
8. `skills/code-creation-workflow/SKILL.md` — brief mention of the pattern detector

## Trade-offs considered

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| **Detector + queue + CLI (chosen)** | Deterministic, auditable, user-gated | Two-step workflow | **Chosen** |
| Single LLM agent writes proposals | Simpler | Can't audit detection separately from content | Rejected |
| Auto-apply + git revert | Visible in git history | Risky — skills corruption hard to detect | Rejected |
| Weekly auto-PR on GitHub | Reviewable as diff | Noisy, requires GitHub access | Rejected |
