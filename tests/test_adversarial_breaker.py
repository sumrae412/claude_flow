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
