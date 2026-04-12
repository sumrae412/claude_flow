"""Tests for causal.py — written first (TDD). Run before implementing."""
import json
import os
import tempfile
import pytest


# ---------------------------------------------------------------------------
# should_controlled_skip
# ---------------------------------------------------------------------------

def test_skip_never_for_high_value():
    from causal import should_controlled_skip
    # HIGH effectiveness (>0.3): never skip, regardless of seed
    for i in range(200):
        assert should_controlled_skip("reviewer", 0.5, 0.9, 0, seed=i) is False
    assert should_controlled_skip("reviewer", 0.31, 0.8, 0, seed=42) is False


def test_skip_never_when_phase_already_skipped():
    from causal import should_controlled_skip
    # Even MODERATE/LOW agents: no skip if phase_skip_count > 0
    results = [
        should_controlled_skip("explorer", 0.2, 0.6, 1, seed=i) for i in range(200)
    ]
    assert all(r is False for r in results)


def test_skip_approximately_5pct_for_moderate():
    from causal import should_controlled_skip
    # MODERATE: effectiveness 0.1–0.3
    results = [should_controlled_skip("explorer", 0.2, 0.6, 0, seed=i) for i in range(1000)]
    rate = sum(results) / len(results)
    assert 0.03 <= rate <= 0.08, f"Expected ~5%, got {rate:.2%}"


def test_skip_approximately_5pct_for_low():
    from causal import should_controlled_skip
    # LOW: effectiveness < 0.1
    results = [should_controlled_skip("explorer", 0.05, 0.4, 0, seed=i) for i in range(1000)]
    rate = sum(results) / len(results)
    assert 0.03 <= rate <= 0.08, f"Expected ~5%, got {rate:.2%}"


def test_skip_deterministic_with_seed():
    from causal import should_controlled_skip
    a = should_controlled_skip("explorer", 0.2, 0.6, 0, seed=99)
    b = should_controlled_skip("explorer", 0.2, 0.6, 0, seed=99)
    assert a == b


def test_skip_boundary_exactly_03_is_high():
    from causal import should_controlled_skip
    # effectiveness exactly 0.3 is NOT high (>0.3 required), so skips allowed
    results = [should_controlled_skip("explorer", 0.3, 0.6, 0, seed=i) for i in range(1000)]
    rate = sum(results) / len(results)
    assert 0.03 <= rate <= 0.08


# ---------------------------------------------------------------------------
# SessionQuality + compute_session_quality
# ---------------------------------------------------------------------------

def test_session_quality_dataclass():
    from causal import SessionQuality
    sq = SessionQuality(
        test_pass_rate=1.0,
        review_severity=0.0,
        retry_count=0,
        violation_count=0,
        user_satisfaction=1.0,
    )
    assert sq.test_pass_rate == 1.0


def test_compute_session_quality_perfect():
    from causal import SessionQuality, compute_session_quality
    sq = SessionQuality(
        test_pass_rate=1.0,
        review_severity=0.0,
        retry_count=0,
        violation_count=0,
        user_satisfaction=1.0,
    )
    score = compute_session_quality(sq)
    assert abs(score - 1.0) < 1e-9


def test_compute_session_quality_zero():
    from causal import SessionQuality, compute_session_quality
    # retry_count_normalized=1, violation_count_normalized=1 → all terms 0
    sq = SessionQuality(
        test_pass_rate=0.0,
        review_severity=1.0,
        retry_count=5,       # >= _MAX_RETRIES (5) → normalized to 1.0
        violation_count=10,  # >= _MAX_VIOLATIONS (10) → normalized to 1.0
        user_satisfaction=0.0,
    )
    score = compute_session_quality(sq)
    assert abs(score - 0.0) < 1e-9


def test_compute_session_quality_weights():
    from causal import SessionQuality, compute_session_quality
    # Only test_pass_rate=1, everything else worst → contributes 0.3
    sq = SessionQuality(
        test_pass_rate=1.0,
        review_severity=1.0,
        retry_count=5,       # >= _MAX_RETRIES → normalized to 1.0
        violation_count=10,  # >= _MAX_VIOLATIONS → normalized to 1.0
        user_satisfaction=0.0,
    )
    score = compute_session_quality(sq)
    assert abs(score - 0.30) < 1e-9


def test_compute_session_quality_mid():
    from causal import SessionQuality, compute_session_quality
    sq = SessionQuality(
        test_pass_rate=0.8,
        review_severity=0.2,
        retry_count=0,
        violation_count=0,
        user_satisfaction=0.9,
    )
    # 0.3*0.8 + 0.25*(1-0.2) + 0.2*1.0 + 0.15*1.0 + 0.1*0.9
    expected = 0.3*0.8 + 0.25*0.8 + 0.2*1.0 + 0.15*1.0 + 0.1*0.9
    score = compute_session_quality(sq)
    assert abs(score - expected) < 1e-9


# ---------------------------------------------------------------------------
# CausalEffect + compute_causal_effect
# ---------------------------------------------------------------------------

def test_causal_effect_dataclass():
    from causal import CausalEffect
    ce = CausalEffect(effect=0.1, p_value=0.05, sample_size_with=20,
                      sample_size_without=20, significant=True)
    assert ce.significant is True


def test_compute_causal_effect_significant():
    from causal import compute_causal_effect
    # Two clearly separated distributions
    with_outcomes = [0.9, 0.85, 0.88, 0.92, 0.87, 0.91, 0.86, 0.89, 0.9, 0.88]
    without_outcomes = [0.5, 0.52, 0.49, 0.51, 0.53, 0.48, 0.5, 0.51, 0.52, 0.5]
    result = compute_causal_effect(with_outcomes, without_outcomes)
    assert result.effect > 0.3
    assert result.p_value < 0.1
    assert result.significant is True
    assert result.sample_size_with == 10
    assert result.sample_size_without == 10


def test_compute_causal_effect_not_significant():
    from causal import compute_causal_effect
    # Indistinguishable distributions
    import random
    rng = random.Random(7)
    with_outcomes = [0.5 + rng.uniform(-0.01, 0.01) for _ in range(20)]
    without_outcomes = [0.5 + rng.uniform(-0.01, 0.01) for _ in range(20)]
    result = compute_causal_effect(with_outcomes, without_outcomes)
    assert result.significant is False


def test_compute_causal_effect_negative():
    from causal import compute_causal_effect
    # Agent hurts quality
    with_outcomes = [0.4, 0.42, 0.39, 0.41, 0.4, 0.38, 0.42, 0.4, 0.41, 0.39]
    without_outcomes = [0.8, 0.79, 0.82, 0.81, 0.8, 0.78, 0.81, 0.82, 0.8, 0.79]
    result = compute_causal_effect(with_outcomes, without_outcomes)
    assert result.effect < 0
    assert result.significant is True


# ---------------------------------------------------------------------------
# record_intervention
# ---------------------------------------------------------------------------

def test_record_intervention_creates_entry():
    from causal import record_intervention
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = os.path.join(tmpdir, "registry.json")
        record_intervention(
            description="Updated security-reviewer prompt",
            affected_agents=["security-reviewer"],
            pre_quality=0.72,
            registry_path=registry_path,
        )
        with open(registry_path) as f:
            data = json.load(f)
        assert "interventions" in data
        assert len(data["interventions"]) == 1
        entry = data["interventions"][0]
        assert entry["description"] == "Updated security-reviewer prompt"
        assert entry["affected_agents"] == ["security-reviewer"]
        assert entry["pre_quality"] == 0.72
        assert "timestamp" in entry


def test_record_intervention_appends():
    from causal import record_intervention
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = os.path.join(tmpdir, "registry.json")
        record_intervention("First", ["agent-a"], 0.6, registry_path)
        record_intervention("Second", ["agent-b"], 0.7, registry_path)
        with open(registry_path) as f:
            data = json.load(f)
        assert len(data["interventions"]) == 2
        assert data["interventions"][1]["description"] == "Second"


def test_record_intervention_existing_registry():
    from causal import record_intervention
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = os.path.join(tmpdir, "registry.json")
        # Pre-populate registry with other data
        with open(registry_path, "w") as f:
            json.dump({"agents": {"reviewer": {"alpha": 5, "beta": 2}}}, f)
        record_intervention("Patch", ["reviewer"], 0.8, registry_path)
        with open(registry_path) as f:
            data = json.load(f)
        # Existing keys preserved
        assert "agents" in data
        assert len(data["interventions"]) == 1


# ---------------------------------------------------------------------------
# stratify_by_complexity
# ---------------------------------------------------------------------------

def test_stratify_returns_tiers():
    from causal import stratify_by_complexity
    outcomes = [
        {"agent": "reviewer", "quality": 0.8},
        {"agent": "reviewer", "quality": 0.7},
        {"agent": "reviewer", "quality": 0.9},
        {"agent": "reviewer", "quality": 0.6},
        {"agent": "reviewer", "quality": 0.95},
    ]
    scores = [3, 5, 7, 4, 8]
    result = stratify_by_complexity(outcomes, scores)
    # score 3 → simple (< 4), score 4 → moderate? Let's check design doc:
    # design: 4-6=moderate, 7+=complex; <4 = simple (not explicitly stated but implied)
    assert "moderate" in result
    assert "complex" in result


def test_stratify_moderate_tier():
    from causal import stratify_by_complexity
    outcomes = [{"quality": 0.8}, {"quality": 0.7}, {"quality": 0.6}]
    scores = [4, 5, 6]  # all moderate
    result = stratify_by_complexity(outcomes, scores)
    assert "moderate" in result
    assert len(result["moderate"]) == 3
    assert result["moderate"][0]["quality"] == 0.8


def test_stratify_complex_tier():
    from causal import stratify_by_complexity
    outcomes = [{"quality": 0.9}, {"quality": 0.85}]
    scores = [7, 9]  # all complex
    result = stratify_by_complexity(outcomes, scores)
    assert "complex" in result
    assert len(result["complex"]) == 2


def test_stratify_simple_tier():
    from causal import stratify_by_complexity
    outcomes = [{"quality": 0.5}]
    scores = [2]  # simple (< 4)
    result = stratify_by_complexity(outcomes, scores)
    assert "simple" in result
    assert len(result["simple"]) == 1


def test_stratify_mixed():
    from causal import stratify_by_complexity
    outcomes = [{"q": 0.5}, {"q": 0.6}, {"q": 0.7}, {"q": 0.8}]
    scores = [2, 5, 7, 9]
    result = stratify_by_complexity(outcomes, scores)
    assert len(result.get("simple", [])) == 1
    assert len(result.get("moderate", [])) == 1
    assert len(result.get("complex", [])) == 2


def test_stratify_length_mismatch_raises():
    from causal import stratify_by_complexity
    with pytest.raises(ValueError):
        stratify_by_complexity([{"q": 0.5}], [1, 2])
