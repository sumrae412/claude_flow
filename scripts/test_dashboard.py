#!/usr/bin/env python3
"""Tests for performance dashboard."""
import importlib.util
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "dash", Path(__file__).parent / "dashboard.py"
)
dash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dash)


def test_percentile_basic():
    assert dash.percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert dash.percentile([1, 2, 3, 4, 5], 0.9) == 4.6
    assert dash.percentile([], 0.5) == 0.0
    assert dash.percentile([10], 0.5) == 10


def test_phase_stats_empty():
    stats = dash.phase_stats([])
    for phase in dash.PHASES:
        assert stats[phase]["runs"] == 0
        assert stats[phase]["median_s"] == 0


def test_phase_stats_basic():
    events = [
        {"phase": "exploration", "duration_s": 100, "retries": 0},
        {"phase": "exploration", "duration_s": 200, "retries": 1},
        {"phase": "exploration", "duration_s": 300, "retries": 0},
        {"phase": "architecture", "duration_s": 400, "retries": 0},
    ]
    stats = dash.phase_stats(events)
    assert stats["exploration"]["runs"] == 3
    assert stats["exploration"]["median_s"] == 200
    assert stats["exploration"]["retry_rate"] == 1 / 3
    assert stats["architecture"]["runs"] == 1
    assert stats["architecture"]["median_s"] == 400
    assert stats["discovery"]["runs"] == 0  # no data


def test_filter_by_days():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=45)).isoformat().replace("+00:00", "Z")
    recent = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")
    events = [
        {"ts": old, "phase": "exploration"},
        {"ts": recent, "phase": "exploration"},
    ]
    kept = dash.filter_by_days(events, 30)
    assert len(kept) == 1
    assert kept[0]["ts"] == recent

    # days=0 keeps everything
    assert len(dash.filter_by_days(events, 0)) == 2


def test_domain_retry_rates():
    events = [
        {"domain": "routes", "phase5_retries": 0},
        {"domain": "routes", "phase5_retries": 1},
        {"domain": "migrations", "phase5_retries": 3},
    ]
    rows = dash.domain_retry_rates(events)
    assert rows[0][0] == "migrations"  # highest rate
    assert rows[0][1] == 3.0
    assert rows[1][0] == "routes"
    assert rows[1][1] == 0.5


def test_reviewer_hit_rates():
    variants = {
        "reviewer": {
            "default": {
                "variants": [
                    {"label": "strict", "metrics": {"sessions": 10, "issues_found_sum": 18}},
                    {"label": "lenient", "metrics": {"sessions": 5, "issues_found_sum": 2}},
                    {"label": "empty", "metrics": {"sessions": 0, "issues_found_sum": 0}},
                ]
            }
        }
    }
    rows = dash.reviewer_hit_rates(variants)
    assert rows[0] == ("strict", 1.8)
    assert rows[1] == ("lenient", 0.4)
    assert len(rows) == 2  # empty variant skipped


def test_render_text_has_sections():
    stats = dash.phase_stats([{"phase": "exploration", "duration_s": 100, "retries": 0}])
    text = dash.render_text(stats, [], [], 30, 1)
    assert "Phase Performance" in text
    assert "Top Retry Domains" in text
    assert "Reviewer Hit Rate" in text
    assert "exploration" in text


def test_render_html_well_formed():
    stats = dash.phase_stats([{"phase": "exploration", "duration_s": 100, "retries": 0}])
    html = dash.render_html(stats, [("routes", 0.5, 1, 2)], [("strict", 1.8)], 30, 1)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "<svg" in html
    assert "routes" in html
    assert "strict" in html


def test_bar_svg_dimensions():
    svg = dash.bar_svg(50, 100, width=400, height=14)
    assert 'width="400"' in svg
    assert 'height="14"' in svg
    assert 'width="200"' in svg  # 50/100 * 400 = 200


def test_bar_svg_zero_max():
    svg = dash.bar_svg(10, 0)
    # Should not crash, should render empty bar
    assert "<svg" in svg


if __name__ == "__main__":
    import inspect
    tests = [fn for name, fn in globals().items()
             if name.startswith("test_") and inspect.isfunction(fn)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
        except AssertionError as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
