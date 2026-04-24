import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

def test_run_ab_produces_three_arm_results(tmp_path):
    out = tmp_path / "results.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "run_ab.py"),
         "--cases-dir", str(Path(__file__).parent / "cases"),
         "--out", str(out), "--dry-run"],
        check=True,
    )
    data = json.loads(out.read_text())
    assert set(data["arms"]) == {"sonnet_solo", "sonnet_advisor_tool", "opus_solo"}
    # 5 cases (phase2, phase3, phase4, phase5, phase6) × 3 arms = 15 rows.
    # phase3 was added 2026-04-24 for the sonnet-vs-opus downgrade eval.
    assert len(data["per_case"]) == 15, (
        f"expected 15 rows (5 cases x 3 arms), got {len(data['per_case'])}"
    )
    for arm in data["arms"]:
        arm_rows = [r for r in data["per_case"] if r["arm"] == arm]
        assert len(arm_rows) == 5, f"expected 5 rows for {arm}, got {len(arm_rows)}"
        assert arm in data["aggregate"], f"{arm} missing from aggregate"


def test_run_ab_trials_multiplies_rows(tmp_path):
    """`--trials 5` produces 5x the rows, each tagged with trial_index."""
    out = tmp_path / "results.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "run_ab.py"),
         "--cases-dir", str(Path(__file__).parent / "cases"),
         "--out", str(out), "--dry-run", "--trials", "5"],
        check=True,
    )
    data = json.loads(out.read_text())
    assert data["trials"] == 5
    assert len(data["per_case"]) == 75, (
        f"expected 75 rows (5 cases x 3 arms x 5 trials), got {len(data['per_case'])}"
    )
    trial_indices = {r["trial_index"] for r in data["per_case"]}
    assert trial_indices == {0, 1, 2, 3, 4}


def _fake_usage(input_tokens=500, output_tokens=300,
                cache_read_input_tokens=0, cache_creation_input_tokens=0):
    u = mock.Mock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.cache_read_input_tokens = cache_read_input_tokens
    u.cache_creation_input_tokens = cache_creation_input_tokens
    u.iterations = []
    return u


def _fake_resp(text="done", usage=None):
    block = mock.Mock()
    block.type = "text"
    block.text = text
    r = mock.Mock()
    r.content = [block]
    r.usage = usage if usage is not None else _fake_usage()
    return r


def test_live_path_captures_cache_fields_from_response(tmp_path, monkeypatch):
    """Cache-field plumbing: when the API returns non-zero cache tokens,
    the values must propagate to ledger extras. Caching itself is not wired
    (prompts below Anthropic's 1024-token minimum); this test exercises the
    passthrough so the wiring flips on cleanly when prompts grow."""
    monkeypatch.setenv("CLAUDE_FLOW_DIR", str(tmp_path))
    for mod in ("ledger", "run_ab"):
        sys.modules.pop(mod, None)

    eval_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(eval_dir))
    sys.path.insert(0, str(eval_dir.parents[1] / "scripts"))

    resp_write = _fake_resp("first", _fake_usage(
        input_tokens=50, cache_creation_input_tokens=400))
    resp_read = _fake_resp("second", _fake_usage(
        input_tokens=50, cache_read_input_tokens=400))

    fake_client = mock.Mock()
    fake_client.beta.messages.create.side_effect = [resp_write, resp_read]
    fake_anthropic_mod = mock.Mock()
    fake_anthropic_mod.Anthropic.return_value = fake_client

    with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic_mod}):
        import run_ab  # noqa: E402

        case = {
            "name": "test_case",
            "context": "ctx",
            "question": "q",
            "rubric": [{"criterion": "c", "keywords": ["done", "first", "second"]}],
        }
        prompts_dir = eval_dir / "prompts"
        row1 = run_ab.run_live_case(case, "sonnet_solo", prompts_dir, session_id="t")
        row2 = run_ab.run_live_case(case, "sonnet_solo", prompts_dir, session_id="t")

    assert row1["usage"]["cache_creation_input_tokens"] == 400
    assert row2["usage"]["cache_read_input_tokens"] == 400

    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert len(rows) == 2
    assert rows[0]["extras"].get("executor_cache_creation_input_tokens") == 400
    assert rows[1]["extras"].get("executor_cache_read_input_tokens") == 400


def test_run_ab_rejects_zero_trials(tmp_path):
    """--trials 0 is nonsensical; exit with non-zero and a clear message."""
    out = tmp_path / "results.json"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "run_ab.py"),
         "--cases-dir", str(Path(__file__).parent / "cases"),
         "--out", str(out), "--dry-run", "--trials", "0"],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "trials" in proc.stderr
