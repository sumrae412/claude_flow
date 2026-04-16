"""Unit tests for the adversarial-breaker calibration script.

Tests the pure helper functions (agreement compute, score extraction,
registry update) without dispatching the live LLM. The live dispatch path
is exercised by running `make calibrate-adversarial` against the labeled
corpus, NOT by these unit tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from calibrate_adversarial_breaker import (  # noqa: E402
    CalibrationCase,
    compute_case_agreement,
    compute_overall_agreement,
    extract_judge_scores,
    get_calibration_block,
    load_corpus,
    resolve_persona,
    update_registry,
)

CRITERIA = [
    "input_validation",
    "error_handling",
    "concurrency_safety",
    "data_consistency",
    "failure_modes",
    "test_coverage_gaps",
]


def _scores(*values: int) -> dict[str, int]:
    """Helper to build a 6-criterion score dict from positional args."""
    assert len(values) == 6, "supply one score per criterion"
    return dict(zip(CRITERIA, values))


# -------------------- compute_case_agreement --------------------


def test_perfect_agreement():
    human = _scores(5, 5, 5, 5, 5, 5)
    judge = _scores(5, 5, 5, 5, 5, 5)
    assert compute_case_agreement(human, judge) == 1.0


def test_zero_agreement_when_all_off_by_more_than_tolerance():
    human = _scores(2, 2, 2, 2, 2, 2)
    judge = _scores(10, 10, 10, 10, 10, 10)  # delta=8, way above tolerance=2
    assert compute_case_agreement(human, judge) == 0.0


def test_within_tolerance_counts_as_agreement():
    """delta of exactly 2 (the tolerance boundary) still agrees."""
    human = _scores(5, 5, 5, 5, 5, 5)
    judge = _scores(7, 3, 5, 5, 5, 5)  # 2 entries off by 2, still match
    assert compute_case_agreement(human, judge) == 1.0


def test_outside_tolerance_does_not_count():
    """delta of 3 (one past tolerance) disagrees."""
    human = _scores(5, 5, 5, 5, 5, 5)
    judge = _scores(8, 5, 5, 5, 5, 5)  # one entry off by 3
    assert compute_case_agreement(human, judge) == pytest.approx(5 / 6)


def test_partial_agreement():
    """4 of 6 within tolerance, 2 outside."""
    human = _scores(5, 5, 5, 5, 5, 5)
    judge = _scores(6, 4, 8, 1, 5, 5)  # ok, ok, off, off, ok, ok
    assert compute_case_agreement(human, judge) == pytest.approx(4 / 6)


def test_missing_judge_score_counts_as_disagreement():
    """If the reviewer omitted a criterion entirely, that's NOT silent agreement."""
    human = _scores(5, 5, 5, 5, 5, 5)
    judge = {"input_validation": 5, "error_handling": 5}  # missing 4 criteria
    # 2 of 6 match
    assert compute_case_agreement(human, judge) == pytest.approx(2 / 6)


def test_custom_tolerance():
    human = _scores(5, 5, 5, 5, 5, 5)
    judge = _scores(8, 8, 5, 5, 5, 5)  # 2 entries off by 3
    # tolerance=3 → all within bounds
    assert compute_case_agreement(human, judge, tolerance=3) == 1.0
    # tolerance=2 (default) → 4 of 6 match
    assert compute_case_agreement(human, judge, tolerance=2) == pytest.approx(4 / 6)


def test_empty_human_raises():
    with pytest.raises(ValueError, match="human scores cannot be empty"):
        compute_case_agreement({}, {})


# -------------------- compute_overall_agreement --------------------


def test_overall_is_arithmetic_mean():
    assert compute_overall_agreement([1.0, 0.5, 0.0]) == pytest.approx(0.5)


def test_overall_single_value():
    assert compute_overall_agreement([0.83]) == pytest.approx(0.83)


def test_overall_empty_raises():
    with pytest.raises(ValueError, match="case_agreements cannot be empty"):
        compute_overall_agreement([])


# -------------------- extract_judge_scores --------------------


def test_extract_well_formed_response():
    response = {
        "reviewer": "adversarial-breaker",
        "scores": [
            {"criterion": "input_validation", "score": 7, "break_case": "..."},
            {"criterion": "error_handling", "score": 4, "break_case": "..."},
        ],
    }
    assert extract_judge_scores(response) == {
        "input_validation": 7,
        "error_handling": 4,
    }


def test_extract_missing_scores_key():
    """No scores key at all → empty dict (not a crash)."""
    assert extract_judge_scores({"reviewer": "adversarial-breaker"}) == {}


def test_extract_skips_malformed_entries():
    """Entries missing criterion or score are dropped, not coerced."""
    response = {
        "scores": [
            {"criterion": "input_validation", "score": 7},
            {"criterion": "error_handling"},  # no score
            {"score": 5},  # no criterion
            {"criterion": "concurrency_safety", "score": 8},
        ]
    }
    assert extract_judge_scores(response) == {
        "input_validation": 7,
        "concurrency_safety": 8,
    }


def test_extract_coerces_string_score_to_int():
    """Some models emit '7' instead of 7. Coerce gracefully."""
    response = {"scores": [{"criterion": "input_validation", "score": "7"}]}
    assert extract_judge_scores(response) == {"input_validation": 7}


def test_extract_drops_non_numeric_score():
    response = {"scores": [{"criterion": "input_validation", "score": "high"}]}
    assert extract_judge_scores(response) == {}


def test_extract_handles_null_scores():
    """scores: null shouldn't crash."""
    assert extract_judge_scores({"scores": None}) == {}


# -------------------- load_corpus --------------------


def test_load_corpus_skips_non_case_dirs(tmp_path):
    """Files and non-case-* directories are ignored."""
    (tmp_path / "README.md").write_text("# header")
    (tmp_path / "not_a_case").mkdir()
    (tmp_path / "not_a_case" / "diff.patch").write_text("")
    case_dir = tmp_path / "case-01-test"
    case_dir.mkdir()
    (case_dir / "diff.patch").write_text("diff --git a/x b/x\n")
    (case_dir / "expected.json").write_text(
        json.dumps({
            "case_id": "case-01-test",
            "primary_criterion": "input_validation",
            "expected_scores": _scores(3, 7, 7, 7, 7, 7),
            "rationale": "test",
        })
    )
    cases = load_corpus(tmp_path)
    assert len(cases) == 1
    assert cases[0].case_id == "case-01-test"
    assert cases[0].primary_criterion == "input_validation"
    assert cases[0].expected_scores["input_validation"] == 3


def test_load_corpus_sorts_by_case_id(tmp_path):
    """Cases are returned in deterministic alphabetic order."""
    for case_id in ["case-03-c", "case-01-a", "case-02-b"]:
        d = tmp_path / case_id
        d.mkdir()
        (d / "diff.patch").write_text("")
        (d / "expected.json").write_text(
            json.dumps({
                "case_id": case_id,
                "primary_criterion": None,
                "expected_scores": _scores(7, 7, 7, 7, 7, 7),
                "rationale": "",
            })
        )
    cases = load_corpus(tmp_path)
    assert [c.case_id for c in cases] == ["case-01-a", "case-02-b", "case-03-c"]


def test_load_corpus_missing_files_raises(tmp_path):
    """A case-* dir missing diff.patch or expected.json is a hard error."""
    bad = tmp_path / "case-01-incomplete"
    bad.mkdir()
    (bad / "diff.patch").write_text("")  # but no expected.json
    with pytest.raises(FileNotFoundError, match="missing"):
        load_corpus(tmp_path)


def test_load_corpus_empty_dir_raises(tmp_path):
    """Empty corpus is suspect — fail loudly so calibration can't run on nothing."""
    with pytest.raises(FileNotFoundError, match="no case-"):
        load_corpus(tmp_path)


# -------------------- resolve_persona --------------------


def test_resolve_persona_combines_root_and_relative():
    data = {
        "reviewers": [
            {
                "id": "adversarial-breaker",
                "persona_file": "claude-flow/scripts/persona.txt",
                "persona_file_root": "/tmp/skills",
            }
        ]
    }
    assert resolve_persona(data, "adversarial-breaker") == Path(
        "/tmp/skills/claude-flow/scripts/persona.txt"
    )


def test_resolve_persona_expands_tilde():
    data = {
        "reviewers": [
            {
                "id": "adversarial-breaker",
                "persona_file": "claude-flow/scripts/persona.txt",
                "persona_file_root": "~/.claude/skills",
            }
        ]
    }
    resolved = resolve_persona(data, "adversarial-breaker")
    # Tilde must be expanded to the real home dir (not literal ~)
    assert "~" not in str(resolved)
    assert resolved.is_absolute()


def test_resolve_persona_missing_reviewer_raises():
    data = {"reviewers": []}
    with pytest.raises(KeyError, match="not found in registry"):
        resolve_persona(data, "missing-id")


def test_resolve_persona_missing_fields_raises():
    data = {
        "reviewers": [{"id": "adversarial-breaker"}]  # no persona_file
    }
    with pytest.raises(KeyError, match="missing persona_file"):
        resolve_persona(data, "adversarial-breaker")


# -------------------- get_calibration_block --------------------


def test_get_calibration_block_returns_block():
    data = {
        "reviewers": [
            {
                "id": "adversarial-breaker",
                "calibration": {"min_agreement": 0.7, "sample_size": 20},
            }
        ]
    }
    calib = get_calibration_block(data, "adversarial-breaker")
    assert calib["min_agreement"] == 0.7


def test_get_calibration_block_missing_block_raises():
    data = {"reviewers": [{"id": "adversarial-breaker"}]}
    with pytest.raises(KeyError, match="no calibration block"):
        get_calibration_block(data, "adversarial-breaker")


# -------------------- update_registry --------------------


def test_update_registry_writes_calibration_fields(tmp_path):
    """update_registry should set last_calibrated + last_agreement and
    leave other fields (including other reviewers) untouched."""
    registry = tmp_path / "reviewer-registry.json"
    original = {
        "version": "1.1",
        "description": "test registry",
        "reviewers": [
            {
                "id": "other-reviewer",
                "tier": "always",
                "description": "should not be touched",
            },
            {
                "id": "adversarial-breaker",
                "tier": "always",
                "score_threshold": 7,
                "calibration": {
                    "verdict_type": "scored",
                    "min_agreement": 0.7,
                    "sample_size": 20,
                    "last_calibrated": None,
                    "last_agreement": None,
                    "note": "Scored reviewer",
                },
            },
        ],
    }
    registry.write_text(json.dumps(original, indent=2) + "\n")

    update_registry(registry, "adversarial-breaker", 0.8333, "2026-04-16")

    after = json.loads(registry.read_text())
    # other reviewer untouched
    assert after["reviewers"][0] == original["reviewers"][0]
    # target reviewer updated
    breaker = after["reviewers"][1]
    assert breaker["calibration"]["last_calibrated"] == "2026-04-16"
    assert breaker["calibration"]["last_agreement"] == 0.8333
    # other calibration fields preserved
    assert breaker["calibration"]["min_agreement"] == 0.7
    assert breaker["calibration"]["verdict_type"] == "scored"
    assert breaker["calibration"]["note"] == "Scored reviewer"
    # top-level fields preserved
    assert after["version"] == "1.1"
    assert after["description"] == "test registry"


def test_update_registry_rounds_long_floats(tmp_path):
    """last_agreement rounded to 4 decimals — keeps the file readable."""
    registry = tmp_path / "reviewer-registry.json"
    registry.write_text(json.dumps({
        "reviewers": [{"id": "x", "calibration": {}}]
    }))
    update_registry(registry, "x", 0.83333333333, "2026-04-16")
    after = json.loads(registry.read_text())
    assert after["reviewers"][0]["calibration"]["last_agreement"] == 0.8333


def test_update_registry_preserves_trailing_newline(tmp_path):
    """Trailing newline is significant for JSON style consistency."""
    registry = tmp_path / "reviewer-registry.json"
    registry.write_text(json.dumps({
        "reviewers": [{"id": "x", "calibration": {}}]
    }))
    update_registry(registry, "x", 0.5, "2026-04-16")
    assert registry.read_text().endswith("\n")


def test_update_registry_missing_reviewer_raises(tmp_path):
    registry = tmp_path / "reviewer-registry.json"
    registry.write_text(json.dumps({"reviewers": []}))
    with pytest.raises(KeyError, match="not in registry"):
        update_registry(registry, "missing-id", 0.5, "2026-04-16")


# -------------------- corpus integration sanity --------------------


def test_real_corpus_loads_with_20_cases():
    """The shipped corpus should always load cleanly with 20 cases.
    Guards against accidental deletion or schema drift."""
    corpus = REPO_ROOT / "tests/fixtures/adversarial_breaker/calibration_corpus"
    cases = load_corpus(corpus)
    assert len(cases) == 20

    # Every case must score all 6 criteria, scores in 1-10 range
    for case in cases:
        assert set(case.expected_scores.keys()) == set(CRITERIA), (
            f"{case.case_id}: missing or extra criteria in expected_scores"
        )
        for crit, score in case.expected_scores.items():
            assert 1 <= score <= 10, f"{case.case_id}: {crit}={score} out of range"

    # Coverage discipline: at least 3 cases per criterion + at least 2 clean
    by_primary: dict[str | None, int] = {}
    for case in cases:
        by_primary[case.primary_criterion] = by_primary.get(case.primary_criterion, 0) + 1
    for crit in CRITERIA:
        assert by_primary.get(crit, 0) >= 3, (
            f"only {by_primary.get(crit, 0)} cases target {crit}; need >=3 for coverage"
        )
    assert by_primary.get(None, 0) >= 2, "need at least 2 clean cases"


def test_real_registry_has_calibration_block():
    """Guard: schema docs and script assume the calibration block exists."""
    registry_path = REPO_ROOT / "reviewer-registry.json"
    data = json.loads(registry_path.read_text())
    calib = get_calibration_block(data, "adversarial-breaker")
    assert calib["verdict_type"] == "scored"
    assert calib["min_agreement"] == 0.7
