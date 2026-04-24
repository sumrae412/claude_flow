"""Regression tests: ledger wiring into adversarial_dispatch + plancraft_review.

Each dispatch/review path MUST write a ledger row on both success and
failure. These tests mock the outbound HTTP/SDK call and verify the
downstream ledger side-effect.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _isolate_ledger(tmp_path, monkeypatch):
    """Re-home the ledger under tmp_path and flush any cached imports."""
    monkeypatch.setenv("CLAUDE_FLOW_DIR", str(tmp_path))
    for mod in ("ledger", "adversarial_dispatch", "plancraft_review", "llm_judge"):
        sys.modules.pop(mod, None)


# ---------- adversarial_dispatch ----------

def _fake_anthropic_response(
    raw_text: str,
    input_tokens=500,
    output_tokens=300,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
):
    block = mock.Mock()
    block.type = "text"
    block.text = raw_text
    usage = mock.Mock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = cache_read_input_tokens
    usage.cache_creation_input_tokens = cache_creation_input_tokens
    resp = mock.Mock()
    resp.content = [block]
    resp.usage = usage
    return resp


def test_adversarial_dispatch_logs_success_to_ledger(tmp_path, monkeypatch):
    _isolate_ledger(tmp_path, monkeypatch)

    verdict = json.dumps({
        "overall": 8,
        "criteria": {"input_validation": 8, "error_handling": 7,
                     "concurrency_safety": 9, "data_consistency": 8,
                     "failure_modes": 8, "test_coverage_gaps": 7},
    })
    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = _fake_anthropic_response(verdict)
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from adversarial_dispatch import dispatch_via_anthropic_api  # noqa: E402
        result = dispatch_via_anthropic_api(
            persona="you are an adversarial reviewer",
            diff="--- a\n+++ b\n",
            session_id="calibration_run_1",
            case="case_42",
        )

    assert result["overall"] == 8

    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["caller"] == "adversarial_breaker"
    assert row["session_id"] == "calibration_run_1"
    assert row["case"] == "case_42"
    assert row["success"] is True
    assert row["input_tokens"] == 500
    assert row["output_tokens"] == 300
    assert row["wall_time_s"] >= 0.0


def test_adversarial_dispatch_logs_failure_and_raises(tmp_path, monkeypatch):
    _isolate_ledger(tmp_path, monkeypatch)
    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.side_effect = RuntimeError("429 rate limited")
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from adversarial_dispatch import dispatch_via_anthropic_api  # noqa: E402
        with pytest.raises(RuntimeError, match="rate limited"):
            dispatch_via_anthropic_api(
                persona="p", diff="d", session_id="s1", case="c1",
            )

    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert "rate limited" in rows[0]["error"]


# ---------- plancraft_review ----------

def _fake_httpx_response(json_body: dict):
    resp = mock.Mock()
    resp.raise_for_status = mock.Mock()
    resp.json = mock.Mock(return_value=json_body)
    return resp


def test_plancraft_review_logs_success_to_ledger(tmp_path, monkeypatch):
    _isolate_ledger(tmp_path, monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    import plancraft_review  # noqa: E402
    api_body = {
        "choices": [{"message": {"content": "1. Security issue: ..."}}],
        "model": "deepseek-chat",
        "usage": {"prompt_tokens": 1200, "completion_tokens": 400, "total_tokens": 1600},
    }
    fake_client = mock.MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.return_value = _fake_httpx_response(api_body)

    with mock.patch.object(plancraft_review.httpx, "Client", return_value=fake_client):
        result = plancraft_review.call_reviewer(
            "deepseek", plan_text="plan body", scope_definition="scope body",
        )

    assert "Security issue" in result["recommendations"]
    assert result["token_usage"]["prompt_tokens"] == 1200

    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert len(rows) == 1
    assert rows[0]["caller"] == "plancraft_deepseek"
    assert rows[0]["model"] == "deepseek-chat"
    assert rows[0]["input_tokens"] == 1200
    assert rows[0]["output_tokens"] == 400
    assert rows[0]["success"] is True


def test_plancraft_review_logs_failure_to_ledger(tmp_path, monkeypatch):
    _isolate_ledger(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import httpx as _httpx
    import plancraft_review  # noqa: E402

    fake_client = mock.MagicMock()
    fake_client.__enter__.return_value = fake_client
    # Trigger retry path: both attempts fail.
    fake_client.post.side_effect = _httpx.HTTPError("connection refused")

    with mock.patch.object(plancraft_review.httpx, "Client", return_value=fake_client):
        result = plancraft_review.call_reviewer(
            "codex", plan_text="plan body", scope_definition="scope body",
        )

    assert "error" in result
    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    # At least one failure row; the retry writes one on final failure.
    assert any(r["caller"] == "plancraft_codex" and r["success"] is False for r in rows)


# ---------- run_ab.py --judge flag ----------

def test_run_ab_with_judge_flag_produces_judged_output(tmp_path):
    """`--judge --dry-run` on run_ab.py must run both passes in one command."""
    import subprocess

    eval_dir = Path(__file__).resolve().parents[1] / "evals" / "advisor_tool_ab"
    out_path = tmp_path / "results.json"
    subprocess.run(
        [sys.executable, str(eval_dir / "run_ab.py"),
         "--cases-dir", str(eval_dir / "cases"),
         "--out", str(out_path),
         "--dry-run", "--judge"],
        check=True,
    )

    data = json.loads(out_path.read_text())
    assert "judge_aggregate" in data, "--judge flag did not trigger judge pass"
    assert set(data["judge_aggregate"].keys()) == set(data["arms"])
    # Every row has a judge block.
    assert all("judge" in r for r in data["per_case"])
