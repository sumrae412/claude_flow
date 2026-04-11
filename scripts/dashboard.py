#!/usr/bin/env python3
from __future__ import annotations
"""Performance dashboard — aggregates phase timings, retry rates, reviewer hit rates.

Reads:
  memory/episodic/phase-events.jsonl       — phase durations + retries
  memory/episodic/exploration-events.jsonl — explorer outcomes
  memory/procedural/prompt-variants.json   — reviewer hit rates

Outputs text report by default. Pass --html PATH to also write an HTML file.
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_DIR = Path(os.environ.get(
    "CLAUDE_FLOW_DIR",
    Path(__file__).resolve().parent.parent,
))
PHASE_EVENTS = REPO_DIR / "memory" / "episodic" / "phase-events.jsonl"
EXPLORER_EVENTS = REPO_DIR / "memory" / "episodic" / "exploration-events.jsonl"
VARIANTS_FILE = REPO_DIR / "memory" / "procedural" / "prompt-variants.json"

PHASES = ["discovery", "exploration", "clarification", "architecture", "implementation", "review"]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def filter_by_days(events: list[dict], days: int) -> list[dict]:
    if not days:
        return events
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    keep = []
    for ev in events:
        ts = ev.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt >= cutoff:
            keep.append(ev)
    return keep


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def phase_stats(events: list[dict]) -> dict[str, dict]:
    """Group by phase, compute runs / median / p90 / retry rate."""
    by_phase: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        phase = ev.get("phase")
        if phase in PHASES:
            by_phase[phase].append(ev)

    stats = {}
    for phase in PHASES:
        evs = by_phase.get(phase, [])
        if not evs:
            stats[phase] = {"runs": 0, "median_s": 0, "p90_s": 0, "retry_rate": 0.0}
            continue
        durs = [float(e.get("duration_s", 0)) for e in evs]
        retries = sum(1 for e in evs if e.get("retries", 0) > 0)
        stats[phase] = {
            "runs": len(evs),
            "median_s": int(percentile(durs, 0.5)),
            "p90_s": int(percentile(durs, 0.9)),
            "retry_rate": retries / len(evs) if evs else 0.0,
        }
    return stats


def domain_retry_rates(explorer_events: list[dict]) -> list[tuple[str, float, int, int]]:
    """Return sorted list of (domain, rate, retries, attempts) by rate desc."""
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "retries": 0})
    for ev in explorer_events:
        dom = ev.get("domain")
        if not dom:
            continue
        stats[dom]["attempts"] += 1
        stats[dom]["retries"] += ev.get("phase5_retries", 0)

    rows = []
    for dom, s in stats.items():
        if s["attempts"] == 0:
            continue
        rate = s["retries"] / s["attempts"]
        rows.append((dom, rate, s["retries"], s["attempts"]))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def reviewer_hit_rates(variants: dict) -> list[tuple[str, float]]:
    """Return (variant_label, issues_per_run) for reviewer variants."""
    rows = []
    reviewer_pool = variants.get("reviewer", {})
    for category, cat_data in reviewer_pool.items():
        for variant in cat_data.get("variants", []):
            m = variant.get("metrics", {})
            sessions = m.get("sessions", 0)
            issues = m.get("issues_found_sum", 0)
            if sessions > 0:
                rows.append((variant.get("label", variant.get("id", "?")), issues / sessions))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------

def render_text(phase_stats_data: dict, domain_rows: list, reviewer_rows: list, days: int, total_sessions: int) -> str:
    lines = []
    window = f"last {days} days" if days else "all time"
    lines.append(f"=== Phase Performance ({window}, {total_sessions} sessions) ===")
    lines.append(f"{'Phase':<16}{'Runs':<6}{'Median':<10}{'p90':<10}{'Retry%':<8}")
    for phase in PHASES:
        s = phase_stats_data[phase]
        lines.append(
            f"{phase:<16}{s['runs']:<6}{str(s['median_s']) + 's':<10}"
            f"{str(s['p90_s']) + 's':<10}{int(s['retry_rate'] * 100)}%"
        )

    lines.append("")
    lines.append("=== Top Retry Domains ===")
    if not domain_rows:
        lines.append("(no data)")
    else:
        for dom, rate, retries, attempts in domain_rows[:5]:
            lines.append(f"{dom:<16}{int(rate * 100)}%  ({retries}/{attempts})")

    lines.append("")
    lines.append("=== Reviewer Hit Rate ===")
    if not reviewer_rows:
        lines.append("(no data)")
    else:
        for label, rate in reviewer_rows:
            lines.append(f"{label:<24}{rate:.1f} issues/run")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML output (minimal inline SVG)
# ---------------------------------------------------------------------------

HTML_STYLE = """
body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; color: #222; }
h1, h2 { margin-top: 2em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { padding: 6px 12px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f8f8f8; font-weight: 600; }
.bar-row { display: flex; align-items: center; margin: 4px 0; }
.bar-label { width: 140px; font-size: 13px; }
.bar-value { width: 60px; text-align: right; font-size: 13px; color: #666; padding-left: 8px; }
svg { display: block; }
"""


def bar_svg(value: float, max_value: float, width: int = 400, height: int = 14, color: str = "#4a90e2") -> str:
    if max_value <= 0:
        bar_w = 0
    else:
        bar_w = int((value / max_value) * width)
    return (
        f'<svg width="{width}" height="{height}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f0f0f0" />'
        f'<rect x="0" y="0" width="{bar_w}" height="{height}" fill="{color}" />'
        f'</svg>'
    )


def render_html(phase_stats_data: dict, domain_rows: list, reviewer_rows: list, days: int, total_sessions: int) -> str:
    window = f"last {days} days" if days else "all time"

    # Phase duration chart
    max_median = max((s["median_s"] for s in phase_stats_data.values()), default=1) or 1
    phase_duration_html = []
    for phase in PHASES:
        s = phase_stats_data[phase]
        phase_duration_html.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{phase}</span>'
            f'{bar_svg(s["median_s"], max_median)}'
            f'<span class="bar-value">{s["median_s"]}s</span>'
            f'</div>'
        )

    # Phase retry chart
    max_retry = max((s["retry_rate"] for s in phase_stats_data.values()), default=1) or 1
    phase_retry_html = []
    for phase in PHASES:
        s = phase_stats_data[phase]
        phase_retry_html.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{phase}</span>'
            f'{bar_svg(s["retry_rate"], max_retry, color="#e25c4a")}'
            f'<span class="bar-value">{int(s["retry_rate"] * 100)}%</span>'
            f'</div>'
        )

    # Domain table
    domain_html = []
    for dom, rate, retries, attempts in domain_rows[:10]:
        domain_html.append(f"<tr><td>{dom}</td><td>{int(rate*100)}%</td><td>{retries}/{attempts}</td></tr>")

    # Reviewer table
    reviewer_html = []
    for label, rate in reviewer_rows:
        reviewer_html.append(f"<tr><td>{label}</td><td>{rate:.2f}</td></tr>")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Claude Flow Performance</title>
<style>{HTML_STYLE}</style></head><body>
<h1>Claude Flow Performance</h1>
<p>{window} &middot; {total_sessions} sessions</p>

<h2>Median Phase Duration</h2>
{''.join(phase_duration_html)}

<h2>Retry Rate by Phase</h2>
{''.join(phase_retry_html)}

<h2>Top Retry Domains</h2>
<table><tr><th>Domain</th><th>Rate</th><th>Retries / Attempts</th></tr>
{''.join(domain_html) or '<tr><td colspan="3">(no data)</td></tr>'}
</table>

<h2>Reviewer Hit Rate</h2>
<table><tr><th>Variant</th><th>Issues per Run</th></tr>
{''.join(reviewer_html) or '<tr><td colspan="2">(no data)</td></tr>'}
</table>
</body></html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_dashboard(days: int = 30) -> tuple[dict, list, list, int]:
    phase_events = filter_by_days(load_jsonl(PHASE_EVENTS), days)
    explorer_events = filter_by_days(load_jsonl(EXPLORER_EVENTS), days)
    variants = json.loads(VARIANTS_FILE.read_text()) if VARIANTS_FILE.exists() else {}

    sessions = {e.get("session_id") for e in phase_events if e.get("session_id")}
    return (
        phase_stats(phase_events),
        domain_retry_rates(explorer_events),
        reviewer_hit_rates(variants),
        len(sessions),
    )


def main():
    parser = argparse.ArgumentParser(description="Claude Flow performance dashboard")
    parser.add_argument("--days", type=int, default=30, help="Rolling window (0 = all time)")
    parser.add_argument("--html", metavar="PATH", help="Also write HTML report to PATH")
    args = parser.parse_args()

    phase_data, domain_data, reviewer_data, sessions = build_dashboard(args.days)

    print(render_text(phase_data, domain_data, reviewer_data, args.days, sessions))

    if args.html:
        html_path = Path(args.html)
        html_path.write_text(render_html(phase_data, domain_data, reviewer_data, args.days, sessions))
        print(f"\nHTML report: {html_path}")


if __name__ == "__main__":
    main()
