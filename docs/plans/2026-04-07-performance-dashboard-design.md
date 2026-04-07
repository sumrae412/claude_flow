# Performance Dashboard

**Date:** 2026-04-07
**Status:** Approved

## Problem

No visibility into Claude Flow performance over time. Phase durations, retry rates, and reviewer effectiveness exist implicitly in events but are never aggregated or surfaced. Hard to tell if improvements (auto-tuning, prompt optimization) are actually making things better.

## Goal

Track phase durations, retry rates, and reviewer hit rates; provide a text + optional HTML dashboard showing per-phase medians, p90, and trends.

## Design

### 1. Phase timing events — `memory/phase-events.jsonl`

Append-only JSONL. One line per phase completion:

```json
{"ts": "2026-04-07T12:34:56Z", "session_id": "abc123", "phase": "exploration", "tier": "moderate", "duration_s": 127, "retries": 0, "domain": "routes"}
```

Fields:
- `ts` — ISO 8601 timestamp (phase end)
- `session_id` — correlates with other event files
- `phase` — discovery | exploration | clarification | architecture | implementation | review
- `tier` — simple | moderate | complex
- `duration_s` — integer seconds
- `retries` — retry count within this phase
- `domain` — optional task domain (for per-domain rollups)

### 2. Emitter — `scripts/emit-phase-event.sh`

Shell wrapper so SKILL.md can call it easily:

```bash
scripts/emit-phase-event.sh <phase> <tier> <duration_s> <retries> [domain]
```

Appends a JSON line to `memory/phase-events.jsonl`. Uses `date -u +%Y-%m-%dT%H:%M:%SZ` and `$SESSION_ID` env var (falls back to `unknown`).

### 3. Aggregator — `scripts/dashboard.py`

Single Python file, stdlib only. CLI:

```bash
python3 scripts/dashboard.py [--days N] [--html PATH]
```

Reads:
- `memory/phase-events.jsonl` — for duration stats
- `memory/exploration-events.jsonl` — for retry rates, domain rollups
- `memory/prompt-variants.json` — for reviewer hit rates (existing field: `issues_found_sum`)

Computes per-phase:
- `runs` — count of events in window
- `median_s`, `p90_s` — duration percentiles
- `retry_rate` — retries / runs

Per-domain (top 5 by retry rate):
- `retries / attempts` from existing `retry_rates_by_domain`

Per-reviewer-type:
- `hit_rate` = `issues_found_sum / sessions` for each reviewer variant

### 4. Text output (default)

```
=== Phase Performance (last 30 days, 42 sessions) ===
Phase           Runs  Median  p90    Retry%
discovery       42    8s      15s    0%
exploration     42    95s     210s   12%
clarification   42    30s     60s    0%
architecture    42    180s    340s   5%
implementation  42    420s    900s   14%
review          42    60s     120s   8%

=== Top Retry Domains ===
migrations  75%  (3/4)
auth        50%  (5/10)
routes      12%  (5/42)

=== Reviewer Hit Rate ===
spec         1.8 issues/run
defensive    0.4 issues/run
security     0.2 issues/run
```

### 5. HTML output (`--html` flag)

Writes single self-contained HTML file with inline SVG bar charts. No JS frameworks, no network requests. Opens in any browser.

Sections:
- Per-phase median duration bar chart
- Per-phase retry rate bar chart
- Time-series (last 30 days): median duration per day per phase
- Top 5 retry domains
- Reviewer hit rates

Uses simple SVG `<rect>` elements. Deliberately minimal — the point is to see trends, not make something beautiful.

### 6. SKILL.md wiring

Add a brief "Phase timing" note in SKILL.md explaining that each phase should call:
```bash
scripts/emit-phase-event.sh <phase> $TIER $DURATION $RETRIES $DOMAIN
```
at phase completion. Not enforced — if it's skipped, the dashboard just shows fewer data points.

## Non-goals

- Persistent web server / live dashboard
- External TSDB (Prometheus, Grafana, etc.)
- Alerting / thresholds
- Authentication / multi-user
- Editable filters in the HTML output
- Historical comparison ("last week vs this week") — trends chart shows it visually

## Implementation sketch

1. `scripts/emit-phase-event.sh` — 15 lines of shell
2. `scripts/dashboard.py` — ~250 lines: load events, compute stats, render text, optional HTML
3. `scripts/test_dashboard.py` — fixtures + assertions for stats math, text output, HTML well-formedness
4. `skills/code-creation-workflow/SKILL.md` — one short section documenting the emit-phase-event.sh helper
5. `memory/phase-events.jsonl` — new empty file, gitignored initially (populate per-session)

## Trade-offs considered

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| Text + optional HTML (chosen) | Zero deps, terminal + visual | HTML charts are basic | **Chosen** |
| Plotly / matplotlib | Polished | New deps | Rejected |
| Grafana + TSDB | Real dashboards | Massive overkill | Rejected |
| Text only | Simplest | No trend visualization | Rejected |
