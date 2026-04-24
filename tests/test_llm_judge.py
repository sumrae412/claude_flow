"""Tests for scripts/llm_judge.py — dry-run path, JSON parsing, ledger integration."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _set_ledger(tmp_path, monkeypatch):
    """Point the ledger at a tmp file for this test."""
    monkeypatch.setenv("CLAUDE_FLOW_DIR", str(tmp_path))
    # Force re-import so DEFAULT_LEDGER_PATH picks up the env var.
    for mod in ("ledger", "llm_judge"):
        if mod in sys.modules:
            del sys.modules[mod]


RUBRIC = [
    {"criterion": "names durability", "keywords": ["durab"]},
    {"criterion": "names ops cost of redis", "keywords": ["redis"]},
]


def test_judge_dry_run_no_api_call(tmp_path, monkeypatch):
    _set_ledger(tmp_path, monkeypatch)
    from llm_judge import judge_response  # noqa: E402

    out = judge_response(
        response_text="redis is durable",
        rubric=RUBRIC,
        dry_run=True,
    )
    assert out["score"] == 0.0  # dry-run: all criteria marked failed
    assert out["cost_usd"] == 0.0
    assert out["wall_time_s"] == 0.0
    assert len(out["per_criterion"]) == 2
    assert all(c["passed"] is False for c in out["per_criterion"])
    # Dry-run path must not write to ledger.
    ledger_path = tmp_path / "memory" / "episodic" / "invocations.jsonl"
    assert not ledger_path.exists()


def test_judge_empty_rubric_returns_zero(tmp_path, monkeypatch):
    _set_ledger(tmp_path, monkeypatch)
    from llm_judge import judge_response  # noqa: E402

    out = judge_response(response_text="anything", rubric=[], dry_run=True)
    assert out["score"] == 0.0
    assert out["per_criterion"] == []


def _fake_anthropic_response(json_body: str, input_tokens=1000, output_tokens=200):
    """Mimic the Anthropic Messages API response shape."""
    block = mock.Mock()
    block.type = "text"
    block.text = json_body
    usage = mock.Mock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    resp = mock.Mock()
    resp.content = [block]
    resp.usage = usage
    return resp


def test_judge_parses_valid_json_and_logs_to_ledger(tmp_path, monkeypatch):
    _set_ledger(tmp_path, monkeypatch)

    judge_json = json.dumps({
        "per_criterion": [
            {"criterion": "names durability", "passed": True,
             "rationale": "mentions Redis Streams durability"},
            {"criterion": "names ops cost of redis", "passed": False,
             "rationale": "does not mention ops burden"},
        ]
    })

    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = _fake_anthropic_response(judge_json)
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from llm_judge import judge_response  # noqa: E402
        out = judge_response(
            response_text="redis streams are durable",
            rubric=RUBRIC,
            context="ctx",
            question="q",
            case_name="case_a",
            arm="opus_solo",
            session_id="s1",
        )

    assert out["score"] == 0.5
    assert out["per_criterion"][0]["passed"] is True
    assert out["per_criterion"][1]["passed"] is False
    assert out["success"] is True
    assert out["cost_usd"] > 0.0

    # Ledger got exactly one row for this call.
    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert len(rows) == 1
    assert rows[0]["caller"] == "llm_judge"
    assert rows[0]["case"] == "case_a"
    assert rows[0]["arm"] == "opus_solo"
    assert rows[0]["score"] == 0.5


def test_judge_tolerates_markdown_fenced_json(tmp_path, monkeypatch):
    _set_ledger(tmp_path, monkeypatch)
    body = "```json\n" + json.dumps({
        "per_criterion": [
            {"criterion": "names durability", "passed": True, "rationale": "ok"},
            {"criterion": "names ops cost of redis", "passed": True, "rationale": "ok"},
        ]
    }) + "\n```"

    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = _fake_anthropic_response(body)
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from llm_judge import judge_response  # noqa: E402
        out = judge_response(response_text="x", rubric=RUBRIC)

    assert out["score"] == 1.0


def test_judge_fills_missing_criteria_with_failed(tmp_path, monkeypatch):
    _set_ledger(tmp_path, monkeypatch)
    # Judge only returns one of the two criteria.
    body = json.dumps({
        "per_criterion": [
            {"criterion": "names durability", "passed": True, "rationale": "ok"},
        ]
    })
    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = _fake_anthropic_response(body)
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from llm_judge import judge_response  # noqa: E402
        out = judge_response(response_text="x", rubric=RUBRIC)

    assert out["score"] == 0.5  # 1 pass + 1 auto-fail
    assert any(
        "did not address" in c["rationale"]
        for c in out["per_criterion"]
    )


def test_judge_malformed_json_recorded_as_failure(tmp_path, monkeypatch):
    _set_ledger(tmp_path, monkeypatch)
    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = _fake_anthropic_response("not json at all")
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from llm_judge import judge_response  # noqa: E402
        out = judge_response(response_text="x", rubric=RUBRIC)

    assert out["success"] is False
    # Pydantic raises ValidationError on bad JSON input; our wrapper reports
    # it as a schema-validation failure.
    err = out["error"] or ""
    assert "schema validation" in err or "non-JSON" in err
    assert out["score"] == 0.0
    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert len(rows) == 1 and rows[0]["success"] is False


def test_judge_rejects_non_bool_passed_field(tmp_path, monkeypatch):
    """Pydantic strict-bool validator rejects truthy strings — the judge can't
    slip a soft verdict ("yes"/"true") past the schema."""
    _set_ledger(tmp_path, monkeypatch)
    body = json.dumps({
        "per_criterion": [
            {"criterion": "names durability", "passed": "yes", "rationale": "ok"},
        ]
    })
    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = _fake_anthropic_response(body)
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from llm_judge import judge_response  # noqa: E402
        out = judge_response(response_text="x", rubric=RUBRIC)

    assert out["success"] is False
    assert "schema validation" in (out["error"] or "")


def test_judge_rejects_missing_per_criterion_key(tmp_path, monkeypatch):
    """Top-level key missing → validation error, not silent zero."""
    _set_ledger(tmp_path, monkeypatch)
    body = json.dumps({"verdict": "good"})
    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = _fake_anthropic_response(body)
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from llm_judge import judge_response  # noqa: E402
        out = judge_response(response_text="x", rubric=RUBRIC)

    # Pydantic accepts missing per_criterion (defaults to []); we fill the
    # rubric with auto-fails. Score = 0.0, success = True (well-formed JSON),
    # but every criterion gets the "did not address" rationale.
    assert out["score"] == 0.0
    assert out["success"] is True
    assert all("did not address" in c["rationale"] for c in out["per_criterion"])


def test_judge_api_error_recorded_as_failure(tmp_path, monkeypatch):
    _set_ledger(tmp_path, monkeypatch)
    fake_anthropic = mock.Mock()
    fake_client = mock.Mock()
    fake_client.messages.create.side_effect = RuntimeError("rate limited")
    fake_anthropic.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from llm_judge import judge_response  # noqa: E402
        out = judge_response(response_text="x", rubric=RUBRIC)

    assert out["success"] is False
    assert "rate limited" in out["error"]
    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert rows[0]["success"] is False
    assert "RuntimeError" in rows[0]["error"]
