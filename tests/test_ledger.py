"""Tests for scripts/ledger.py — append, read, summarize, ROI math."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ledger import log_invocation, read_rows, summarize  # noqa: E402


def test_log_invocation_writes_row(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    row = log_invocation(
        caller="test",
        model="claude-opus-4-7",
        wall_time_s=1.5,
        input_tokens=1000,
        output_tokens=500,
        session_id="s1",
        arm="opus_solo",
        case="case_a",
        score=0.75,
        ledger_path=ledger,
    )
    assert row["caller"] == "test"
    assert row["cost_usd"] > 0  # 1k input * $15 + 500 output * $75 per MTok
    assert row["wall_time_s"] == 1.5

    rows = read_rows(ledger)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["score"] == 0.75


def test_log_invocation_appends_not_overwrites(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    for i in range(3):
        log_invocation(
            caller="test",
            model="claude-sonnet-4-6",
            wall_time_s=1.0,
            input_tokens=100,
            output_tokens=50,
            case=f"case_{i}",
            ledger_path=ledger,
        )
    assert len(read_rows(ledger)) == 3


def test_log_invocation_overrides_cost(tmp_path):
    # Caller-provided cost wins over computed cost. Useful when the caller
    # already computed it from a different pricing model.
    ledger = tmp_path / "ledger.jsonl"
    row = log_invocation(
        caller="test",
        model="gpt-4o",
        wall_time_s=0.5,
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.0001,
        ledger_path=ledger,
    )
    assert row["cost_usd"] == 0.0001


def test_log_invocation_unknown_model_logs_zero_cost(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    row = log_invocation(
        caller="test",
        model="unknown-model-xyz",
        wall_time_s=0.5,
        input_tokens=1000,
        output_tokens=500,
        ledger_path=ledger,
    )
    assert row["cost_usd"] == 0.0


def test_summarize_groups_and_computes_roi(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    # Two calls on the same arm, same model, same caller.
    for _ in range(2):
        log_invocation(
            caller="advisor_ab",
            model="claude-opus-4-7",
            wall_time_s=2.0,
            input_tokens=1_000_000,  # $15 input
            output_tokens=0,
            arm="opus_solo",
            score=0.5,
            ledger_path=ledger,
        )
    result = summarize(caller="advisor_ab", ledger_path=ledger)
    assert result["count"] == 2
    groups = result["groups"]
    assert len(groups) == 1
    g = groups[0]
    assert g["arm"] == "opus_solo"
    assert g["count"] == 2
    assert g["mean_score"] == 0.5
    assert g["total_cost_usd"] == 30.0  # 2 * $15
    assert g["mean_cost_usd"] == 15.0
    assert g["roi_score_per_usd"] is not None
    # ROI = mean_score / mean_cost = 0.5 / 15 ≈ 0.0333
    assert 0.03 < g["roi_score_per_usd"] < 0.04


def test_summarize_handles_missing_scores(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    log_invocation(
        caller="x",
        model="claude-opus-4-7",
        wall_time_s=1.0,
        input_tokens=1000,
        output_tokens=500,
        ledger_path=ledger,
    )
    result = summarize(caller="x", ledger_path=ledger)
    g = result["groups"][0]
    assert g["mean_score"] is None
    assert g["roi_score_per_usd"] is None


def test_summarize_filter_by_session(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    log_invocation(caller="c", model="claude-opus-4-7", wall_time_s=1.0,
                   input_tokens=100, output_tokens=50,
                   session_id="run1", ledger_path=ledger)
    log_invocation(caller="c", model="claude-opus-4-7", wall_time_s=1.0,
                   input_tokens=100, output_tokens=50,
                   session_id="run2", ledger_path=ledger)
    assert summarize(session_id="run1", ledger_path=ledger)["count"] == 1


def test_read_rows_tolerates_empty_file(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("")
    assert read_rows(ledger) == []


def test_read_rows_skips_malformed_lines(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"ok": 1}\nnot-json\n{"ok": 2}\n')
    rows = read_rows(ledger)
    assert len(rows) == 2
    assert rows[0]["ok"] == 1 and rows[1]["ok"] == 2


def test_log_records_failure(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    log_invocation(
        caller="x",
        model="claude-opus-4-7",
        wall_time_s=0.1,
        success=False,
        error="RateLimitError: slow down",
        ledger_path=ledger,
    )
    rows = read_rows(ledger)
    assert rows[0]["success"] is False
    assert "RateLimit" in rows[0]["error"]
