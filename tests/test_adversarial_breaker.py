import json
import sys
from pathlib import Path

REGISTRY = Path(__file__).parent.parent / "reviewer-registry.json"
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_adversarial_breaker_registered():
    data = json.loads(REGISTRY.read_text())
    reviewers = {r["id"]: r for r in data["reviewers"]}
    assert "adversarial-breaker" in reviewers
    r = reviewers["adversarial-breaker"]
    assert r["tier"] == "always"
    assert r["cascade_tier"] == 2
    assert r["score_threshold"] == 7
    assert set(r["scored_criteria"]) == {
        "input_validation",
        "error_handling",
        "concurrency_safety",
        "data_consistency",
        "failure_modes",
        "test_coverage_gaps",
    }
    # Agent-backed (not CLI-backed)
    assert "subagent_type" in r
    assert "runner" not in r


def test_subthreshold_scores_become_blocking_findings():
    """Aggregator logic: for a reviewer with score_threshold=7,
    any score < 7 should produce one blocking finding with the break_case."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    reviewer_output = {
        "reviewer": "adversarial-breaker",
        "scores": [
            {"criterion": "input_validation", "score": 9, "break_case": "N/A"},
            {
                "criterion": "concurrency_safety",
                "score": 3,
                "break_case": "Two concurrent POSTs to /api/book race on slot lock",
            },
        ],
        "findings": [],
    }
    registry_entry = {"score_threshold": 7}

    result = convert_scores_to_findings(reviewer_output, registry_entry)
    assert len(result["findings"]) == 1
    f = result["findings"][0]
    assert f["severity"] == "blocking"
    assert "concurrency_safety" in f["message"]
    assert "3/10" in f["message"]
    assert "Two concurrent POSTs" in f["message"]


def test_boundary_score_equals_threshold_is_not_blocking():
    """score == threshold is a PASS (strict-less-than semantics)."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    out = convert_scores_to_findings(
        {
            "scores": [{"criterion": "x", "score": 7, "break_case": "boundary"}],
            "findings": [],
        },
        {"score_threshold": 7},
    )
    assert out["findings"] == []


def test_boundary_score_one_below_threshold_is_blocking():
    """score == threshold - 1 produces a blocking finding."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    out = convert_scores_to_findings(
        {"scores": [{"criterion": "x", "score": 6, "break_case": "sub"}], "findings": []},
        {"score_threshold": 7},
    )
    assert len(out["findings"]) == 1
    assert out["findings"][0]["severity"] == "blocking"


def test_idempotent_on_reentry():
    """Calling the aggregator twice on the same output must not duplicate findings."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    reviewer_output = {
        "reviewer": "adversarial-breaker",
        "scores": [{"criterion": "error_handling", "score": 2, "break_case": "foo"}],
        "findings": [],
    }
    registry_entry = {"score_threshold": 7}
    first = convert_scores_to_findings(reviewer_output, registry_entry)
    second = convert_scores_to_findings(first, registry_entry)
    assert len(first["findings"]) == 1
    assert len(second["findings"]) == 1  # no duplicate


def test_missing_scores_key_passes_through_without_crash():
    """Malformed reviewer output: no 'scores' key → pass-through, no crash."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    out = convert_scores_to_findings({"findings": []}, {"score_threshold": 7})
    assert out["findings"] == []


def test_scores_not_a_list_passes_through():
    """'scores' is a dict (malformed) → warn and pass through."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    out = convert_scores_to_findings(
        {"scores": {"nope": "wrong-shape"}, "findings": []}, {"score_threshold": 7}
    )
    assert out["findings"] == []


def test_score_entry_missing_fields_is_skipped():
    """A score entry missing 'score' or 'criterion' is skipped, not fatal."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    reviewer_output = {
        "scores": [
            {"criterion": "a"},  # no score
            {"score": 2},  # no criterion
            {"criterion": "b", "score": 2, "break_case": "legit"},  # valid
        ],
        "findings": [],
    }
    out = convert_scores_to_findings(reviewer_output, {"score_threshold": 7})
    assert len(out["findings"]) == 1
    assert out["findings"][0]["criterion"] == "b"


def test_string_score_is_coerced():
    """Persona may emit '3' instead of 3; aggregator tolerates."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    out = convert_scores_to_findings(
        {"scores": [{"criterion": "x", "score": "3", "break_case": "str"}], "findings": []},
        {"score_threshold": 7},
    )
    assert len(out["findings"]) == 1


def test_non_numeric_score_is_skipped():
    """A score that can't be coerced to int is skipped, not fatal."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    out = convert_scores_to_findings(
        {
            "scores": [
                {"criterion": "bad", "score": "unknown", "break_case": "foo"},
                {"criterion": "good", "score": 2, "break_case": "bar"},
            ],
            "findings": [],
        },
        {"score_threshold": 7},
    )
    assert len(out["findings"]) == 1
    assert out["findings"][0]["criterion"] == "good"


def test_missing_score_threshold_passes_through():
    """Registry entry without score_threshold (binary reviewer) passes through."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    reviewer_output = {
        "scores": [{"criterion": "x", "score": 1, "break_case": "low"}],
        "findings": [{"severity": "high", "message": "pre-existing"}],
    }
    out = convert_scores_to_findings(reviewer_output, {})
    # Scores NOT converted; pre-existing findings preserved.
    assert len(out["findings"]) == 1
    assert out["findings"][0]["severity"] == "high"


def test_cli_entrypoint(tmp_path):
    """The --reviewer / --registry CLI matches the phase-6-quality.md docs."""
    import subprocess
    import sys

    reviewer_file = tmp_path / "reviewer.json"
    reviewer_file.write_text(
        json.dumps(
            {
                "reviewer": "adversarial-breaker",
                "scores": [
                    {"criterion": "error_handling", "score": 2, "break_case": "raise leaks"}
                ],
                "findings": [],
            }
        )
    )
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(
        json.dumps(
            {
                "reviewers": [
                    {"id": "adversarial-breaker", "score_threshold": 7}
                ]
            }
        )
    )

    script = REPO_ROOT / "scripts" / "aggregate_reviewer_findings.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--reviewer",
            str(reviewer_file),
            "--registry",
            str(registry_file),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert len(out["findings"]) == 1
    assert out["findings"][0]["severity"] == "blocking"
    assert "error_handling" in out["findings"][0]["message"]


def test_breaker_catches_planted_concurrency_bug():
    """Golden fixture: the reviewer must score concurrency_safety below threshold
    on a diff with a known race condition, and mention the triggering concept.

    Uses a pre-recorded LLM response to stay deterministic in CI. Regenerate
    recorded_response.json manually when the persona prompt changes.
    """
    fixture_dir = Path(__file__).parent / "fixtures/adversarial_breaker"
    # Ensure fixture inputs exist even if we don't re-dispatch the LLM in CI.
    assert (fixture_dir / "buggy_diff.patch").exists()
    expected = json.loads((fixture_dir / "expected_scores.json").read_text())

    recorded = fixture_dir / "recorded_response.json"
    assert recorded.exists(), (
        "recorded_response.json missing — regenerate by dispatching the "
        "adversarial-breaker against buggy_diff.patch and saving stdout."
    )
    result = json.loads(recorded.read_text())

    below = {s["criterion"] for s in result["scores"] if s["score"] < 7}
    for c in expected["must_score_below_threshold"]:
        assert c in below, f"reviewer missed {c} break case"

    all_text = " ".join(s["break_case"].lower() for s in result["scores"])
    synonyms = expected["must_find_break_case_mentioning_any_of"]
    assert any(kw in all_text for kw in synonyms), (
        f"no break_case mentions any of {synonyms}; full text: {all_text!r}"
    )
