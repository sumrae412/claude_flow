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
    assert len(data["per_case"]) == 12, (
        f"expected 12 rows (4 cases x 3 arms), got {len(data['per_case'])}"
    )
    for arm in data["arms"]:
        arm_rows = [r for r in data["per_case"] if r["arm"] == arm]
        assert len(arm_rows) == 4, f"expected 4 rows for {arm}, got {len(arm_rows)}"
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
    assert len(data["per_case"]) == 60, (
        f"expected 60 rows (4 cases x 3 arms x 5 trials), got {len(data['per_case'])}"
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


def test_live_path_sends_cache_control_and_captures_cache_fields(tmp_path, monkeypatch):
    """Verify cache_control is on the system block and cache fields land in extras.

    Mocks Anthropic client. First call writes cache; second call reads cache.
    Asserts:
      - `system` kwarg is a list with a `cache_control` breakpoint
      - `cache_read_input_tokens` from the 2nd response flows into ledger extras
    """
    # Re-home ledger under tmp_path so we can read what run_ab wrote.
    monkeypatch.setenv("CLAUDE_FLOW_DIR", str(tmp_path))
    # Flush cached modules so ledger picks up the env var.
    for mod in ("ledger", "run_ab"):
        sys.modules.pop(mod, None)

    eval_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(eval_dir))
    sys.path.insert(0, str(eval_dir.parents[1] / "scripts"))

    # First response = cache write; second = cache read.
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

    # Every create() call carried the system cache breakpoint.
    for call_kwargs in [c.kwargs for c in fake_client.beta.messages.create.call_args_list]:
        assert isinstance(call_kwargs["system"], list)
        assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert "CONTEXT:" not in call_kwargs["system"][0]["text"], \
            "system preamble must not include per-call CONTEXT — caching would miss"

    # Second row captured the cache-read signal.
    assert row2["usage"]["cache_read_input_tokens"] == 400
    assert row1["usage"]["cache_creation_input_tokens"] == 400

    # Ledger extras preserve the cache fields.
    from ledger import read_rows  # noqa: E402
    rows = read_rows()
    assert len(rows) == 2
    assert rows[0]["extras"].get("executor_cache_creation_input_tokens") == 400
    assert rows[1]["extras"].get("executor_cache_read_input_tokens") == 400


def test_split_prompt_for_caching_separates_at_context_marker():
    """Preamble has no CONTEXT; suffix starts with CONTEXT:."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_ab import split_prompt_for_caching  # noqa: E402

    template = "Instructions here.\n\nCONTEXT:\n{context}\n\nQUESTION:\n{question}\n"
    preamble, suffix = split_prompt_for_caching(template)
    assert "CONTEXT:" not in preamble
    assert suffix.startswith("CONTEXT:")
    assert "{context}" in suffix and "{question}" in suffix


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
