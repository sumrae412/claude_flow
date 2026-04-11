# Memory System — 3-Tier Architecture

Inspired by cognitive science's memory types, adapted for agentic workflows.

## Episodic (What Happened)

Raw interaction traces — timestamped events from specific sessions.

- `exploration-events.jsonl` — Explorer outcomes by domain
- `failure-events.jsonl` — Categorized failures with session context
- `phase-events.jsonl` — Phase timings and retry counts

**Retention:** Rolling 30-day window. Old events feed pattern detector then archive.

## Semantic (What We Learned)

Generalized patterns extracted from episodic data — session-independent knowledge.

- `failure-catalog.md` — Known failure patterns with fix strategies
- `pattern-library.md` — Cross-session patterns (e.g., "this codebase always needs X when Y")

**Retention:** Permanent until invalidated by code changes.

## Procedural (How To Do Things)

Learned optimizations for workflow execution.

- `prompt-variants.json` — A/B tested prompt variants with metrics
- `proposed-skill-updates.jsonl` — Pending skill improvements from pattern detector

**Retention:** Permanent. Evolves through proposal review cycle.

## Data Flow

```
Episodic events → Pattern Detector → Semantic patterns
                                   → Procedural proposals
```

Scripts that consume these files:
- `scripts/pattern-detector.py` reads `episodic/failure-events.jsonl` → writes `procedural/proposed-skill-updates.jsonl`
- `scripts/dashboard.py` reads all `episodic/*.jsonl` + `procedural/prompt-variants.json`
- `scripts/review-proposals.py` reads/writes `procedural/proposed-skill-updates.jsonl`
