"""
Tests for registry.py — Bayesian agent registry for claude-flow swarm.

TDD: These tests are written before the implementation. Run first to confirm they
fail with ModuleNotFoundError, then implement registry.py to make them pass.
"""

import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_global_registry(tmp_path):
    """Return path for a temporary global registry file (does not create it)."""
    return tmp_path / "agent-registry.json"


@pytest.fixture
def tmp_project_registry(tmp_path):
    """Return path for a temporary project registry file (does not create it)."""
    project_dir = tmp_path / "project" / ".claude" / "swarm"
    project_dir.mkdir(parents=True)
    return project_dir / "agent-registry.json"


@pytest.fixture
def tmp_events_file(tmp_path):
    """Return path for a temporary registry events JSONL file."""
    return tmp_path / "registry-events.jsonl"


@pytest.fixture
def registry_instance(tmp_path):
    """Create a Registry instance wired to tmp_path directories."""
    from registry import Registry
    global_path = tmp_path / "global" / "agent-registry.json"
    global_path.parent.mkdir(parents=True)
    project_path = tmp_path / "project" / "agent-registry.json"
    project_path.parent.mkdir(parents=True)
    events_path = tmp_path / "registry-events.jsonl"
    return Registry(
        global_registry_path=global_path,
        project_registry_path=project_path,
        events_path=events_path,
    )


# ---------------------------------------------------------------------------
# bayesian_update
# ---------------------------------------------------------------------------

class TestBayesianUpdate:
    def test_success_increments_alpha(self):
        from registry import bayesian_update
        prior = {"alpha": 1.0, "beta": 1.0}
        updated = bayesian_update(prior, success=True)
        assert updated["alpha"] == 2.0
        assert updated["beta"] == 1.0

    def test_failure_increments_beta(self):
        from registry import bayesian_update
        prior = {"alpha": 1.0, "beta": 1.0}
        updated = bayesian_update(prior, success=False)
        assert updated["alpha"] == 1.0
        assert updated["beta"] == 2.0

    def test_does_not_mutate_input(self):
        from registry import bayesian_update
        prior = {"alpha": 3.0, "beta": 2.0}
        original_alpha = prior["alpha"]
        bayesian_update(prior, success=True)
        assert prior["alpha"] == original_alpha

    def test_accumulates_over_multiple_calls(self):
        from registry import bayesian_update
        prior = {"alpha": 1.0, "beta": 1.0}
        prior = bayesian_update(prior, success=True)
        prior = bayesian_update(prior, success=True)
        prior = bayesian_update(prior, success=False)
        assert prior["alpha"] == 3.0
        assert prior["beta"] == 2.0


# ---------------------------------------------------------------------------
# compute_effectiveness
# ---------------------------------------------------------------------------

class TestComputeEffectiveness:
    def test_uniform_prior_is_half(self):
        from registry import compute_effectiveness
        assert compute_effectiveness({"alpha": 1.0, "beta": 1.0}) == pytest.approx(0.5)

    def test_all_successes(self):
        from registry import compute_effectiveness
        # alpha=11, beta=1 → 11/12 ≈ 0.9167
        result = compute_effectiveness({"alpha": 11.0, "beta": 1.0})
        assert result == pytest.approx(11 / 12)

    def test_all_failures(self):
        from registry import compute_effectiveness
        # alpha=1, beta=11 → 1/12 ≈ 0.0833
        result = compute_effectiveness({"alpha": 1.0, "beta": 11.0})
        assert result == pytest.approx(1 / 12)

    def test_formula_alpha_over_sum(self):
        from registry import compute_effectiveness
        result = compute_effectiveness({"alpha": 3.0, "beta": 7.0})
        assert result == pytest.approx(3.0 / 10.0)


# ---------------------------------------------------------------------------
# blend_priors
# ---------------------------------------------------------------------------

class TestBlendPriors:
    """
    Design doc: 0.7 project + 0.3 global below 5 dispatches; linear interpolation
    from 5 to 15; pure project at 15+ dispatches.
    """

    def _make_agent(self, alpha, beta, dispatches):
        return {
            "prior": {"alpha": alpha, "beta": beta},
            "dispatches": dispatches,
        }

    def test_below_5_dispatches_is_70_30_blend(self):
        from registry import blend_priors, compute_effectiveness
        project = self._make_agent(alpha=8.0, beta=2.0, dispatches=3)  # eff=0.8
        global_  = self._make_agent(alpha=3.0, beta=7.0, dispatches=50) # eff=0.3
        blended = blend_priors(project, global_)
        expected = 0.7 * (8 / 10) + 0.3 * (3 / 10)
        assert blended == pytest.approx(expected)

    def test_at_0_dispatches_is_70_30_blend(self):
        from registry import blend_priors
        project = self._make_agent(alpha=1.0, beta=1.0, dispatches=0)
        global_  = self._make_agent(alpha=9.0, beta=1.0, dispatches=100)
        blended = blend_priors(project, global_)
        expected = 0.7 * 0.5 + 0.3 * (9 / 10)
        assert blended == pytest.approx(expected)

    def test_at_15_dispatches_is_pure_project(self):
        from registry import blend_priors
        project = self._make_agent(alpha=8.0, beta=2.0, dispatches=15)
        global_  = self._make_agent(alpha=1.0, beta=9.0, dispatches=100)
        blended = blend_priors(project, global_)
        assert blended == pytest.approx(8 / 10)

    def test_above_15_dispatches_is_pure_project(self):
        from registry import blend_priors
        project = self._make_agent(alpha=6.0, beta=4.0, dispatches=30)
        global_  = self._make_agent(alpha=1.0, beta=9.0, dispatches=100)
        blended = blend_priors(project, global_)
        assert blended == pytest.approx(6 / 10)

    def test_at_10_dispatches_is_midpoint_blend(self):
        """At 10 dispatches (midpoint of 5-15), project weight should be 0.85."""
        from registry import blend_priors
        project = self._make_agent(alpha=8.0, beta=2.0, dispatches=10)
        global_  = self._make_agent(alpha=1.0, beta=9.0, dispatches=100)
        blended = blend_priors(project, global_)
        # Linear interp: at 10, t=(10-5)/(15-5)=0.5, weight=0.7+0.5*0.3=0.85
        expected = 0.85 * (8 / 10) + 0.15 * (1 / 10)
        assert blended == pytest.approx(expected)


# ---------------------------------------------------------------------------
# fingerprint_similarity
# ---------------------------------------------------------------------------

class TestFingerprintSimilarity:
    """
    Design doc: Jaccard on flattened tags. Boolean fields become tags like
    "has_migrations=true" or "has_migrations=false". List fields contribute each
    element as a tag. Scalar non-boolean values contribute as "key=value".
    """

    def test_identical_fingerprints_are_1(self):
        from registry import fingerprint_similarity
        fp = {
            "languages": ["python"],
            "frameworks": ["fastapi"],
            "has_migrations": True,
        }
        assert fingerprint_similarity(fp, fp) == pytest.approx(1.0)

    def test_completely_different_fingerprints_are_0(self):
        from registry import fingerprint_similarity
        a = {"languages": ["python"], "has_migrations": True}
        b = {"languages": ["ruby"], "has_migrations": False}
        assert fingerprint_similarity(a, b) == pytest.approx(0.0)

    def test_partial_overlap(self):
        from registry import fingerprint_similarity
        # a tags: {python, fastapi, has_migrations=true}
        # b tags: {python, django, has_migrations=false}
        # intersection: {python} = 1; union: {python, fastapi, has_migrations=true, django, has_migrations=false} = 5
        a = {"languages": ["python"], "frameworks": ["fastapi"], "has_migrations": True}
        b = {"languages": ["python"], "frameworks": ["django"], "has_migrations": False}
        expected = 1 / 5
        assert fingerprint_similarity(a, b) == pytest.approx(expected)

    def test_empty_fingerprints(self):
        from registry import fingerprint_similarity
        # Both empty → 0 / 0 → define as 0.0 (no similarity)
        assert fingerprint_similarity({}, {}) == pytest.approx(0.0)

    def test_scalar_layer_count(self):
        from registry import fingerprint_similarity
        a = {"layer_count": 4}
        b = {"layer_count": 4}
        assert fingerprint_similarity(a, b) == pytest.approx(1.0)

    def test_scalar_layer_count_mismatch(self):
        from registry import fingerprint_similarity
        a = {"layer_count": 4}
        b = {"layer_count": 2}
        assert fingerprint_similarity(a, b) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# apply_decay
# ---------------------------------------------------------------------------

class TestApplyDecay:
    """
    Design doc: multiply alpha and beta by factor, floor each at 1.0.
    Default decay factor: 0.85.
    """

    def test_decay_reduces_values(self):
        from registry import apply_decay
        agent = {"prior": {"alpha": 10.0, "beta": 8.0}}
        decayed = apply_decay(agent, factor=0.85)
        assert decayed["prior"]["alpha"] == pytest.approx(10.0 * 0.85)
        assert decayed["prior"]["beta"] == pytest.approx(8.0 * 0.85)

    def test_decay_floor_at_1(self):
        from registry import apply_decay
        agent = {"prior": {"alpha": 1.0, "beta": 1.0}}
        decayed = apply_decay(agent, factor=0.85)
        assert decayed["prior"]["alpha"] == pytest.approx(1.0)
        assert decayed["prior"]["beta"] == pytest.approx(1.0)

    def test_decay_partial_floor(self):
        from registry import apply_decay
        # alpha=1.0 * 0.85 = 0.85 → floored to 1.0; beta=10.0 * 0.85 = 8.5 → not floored
        agent = {"prior": {"alpha": 1.0, "beta": 10.0}}
        decayed = apply_decay(agent, factor=0.85)
        assert decayed["prior"]["alpha"] == pytest.approx(1.0)
        assert decayed["prior"]["beta"] == pytest.approx(8.5)

    def test_does_not_mutate_input(self):
        from registry import apply_decay
        agent = {"prior": {"alpha": 5.0, "beta": 5.0}}
        apply_decay(agent, factor=0.85)
        assert agent["prior"]["alpha"] == 5.0


# ---------------------------------------------------------------------------
# dispatch_decision
# ---------------------------------------------------------------------------

class TestDispatchDecision:
    """
    Design doc dispatch logic:
      - effectiveness > 0.3                            → DISPATCH
      - effectiveness 0.1–0.3 AND confidence < 10     → DISPATCH (insufficient data)
      - effectiveness < 0.1 AND confidence > 15       → SKIP
      - effectiveness 0.1–0.3 AND confidence > 15     → REDUCED
      - Any remaining ambiguous zone                  → DISPATCH (safe default)
    confidence = alpha + beta (total observations, consistent with Beta distribution)
    """

    def test_high_effectiveness_dispatches(self):
        from registry import dispatch_decision
        assert dispatch_decision(effectiveness=0.8, confidence=20) == "dispatch"

    def test_effectiveness_just_above_0_3_dispatches(self):
        from registry import dispatch_decision
        assert dispatch_decision(effectiveness=0.31, confidence=30) == "dispatch"

    def test_low_effectiveness_high_confidence_skips(self):
        from registry import dispatch_decision
        assert dispatch_decision(effectiveness=0.05, confidence=20) == "skip"

    def test_low_effectiveness_low_confidence_dispatches(self):
        from registry import dispatch_decision
        # effectiveness < 0.1 but confidence ≤ 15 → insufficient data → dispatch
        assert dispatch_decision(effectiveness=0.05, confidence=8) == "dispatch"

    def test_medium_effectiveness_low_confidence_dispatches(self):
        from registry import dispatch_decision
        assert dispatch_decision(effectiveness=0.2, confidence=5) == "dispatch"

    def test_medium_effectiveness_high_confidence_reduced(self):
        from registry import dispatch_decision
        assert dispatch_decision(effectiveness=0.2, confidence=20) == "reduced"

    def test_exactly_at_0_3_effectiveness_dispatches(self):
        from registry import dispatch_decision
        # boundary: 0.3 is NOT > 0.3, falls into medium range with high confidence → reduced
        assert dispatch_decision(effectiveness=0.3, confidence=20) == "reduced"

    def test_exactly_at_0_1_effectiveness_high_confidence_boundary(self):
        from registry import dispatch_decision
        # 0.1 is the lower bound of medium range; confidence > 15 → reduced
        assert dispatch_decision(effectiveness=0.1, confidence=20) == "reduced"

    def test_effectiveness_just_below_0_1_high_confidence_skips(self):
        from registry import dispatch_decision
        assert dispatch_decision(effectiveness=0.09, confidence=20) == "skip"


# ---------------------------------------------------------------------------
# compact_events
# ---------------------------------------------------------------------------

class TestCompactEvents:
    """
    Design doc: read registry + events JSONL, apply events (bayesian_update),
    write updated registry, truncate events file.
    """

    def _write_registry(self, path: Path, agents: dict):
        data = {
            "schema_version": 2,
            "agents": agents,
        }
        path.write_text(json.dumps(data))

    def _write_events(self, path: Path, events: list):
        lines = [json.dumps(e) for e in events]
        path.write_text("\n".join(lines) + ("\n" if lines else ""))

    def test_compact_applies_success_event(self, tmp_path):
        from registry import compact_events
        reg_path = tmp_path / "registry.json"
        ev_path = tmp_path / "events.jsonl"
        self._write_registry(reg_path, {
            "explorer:broad": {"prior": {"alpha": 1.0, "beta": 1.0}, "dispatches": 0,
                               "findings_produced": 0, "findings_used": 0,
                               "findings_used_rate": 0.0, "missed_context_count": 0,
                               "last_dispatched": None, "last_updated": None}
        })
        self._write_events(ev_path, [
            {"agent": "explorer:broad", "success": True, "timestamp": "2026-04-06T00:00:00"}
        ])
        compact_events(reg_path, ev_path)
        result = json.loads(reg_path.read_text())
        assert result["agents"]["explorer:broad"]["prior"]["alpha"] == 2.0
        assert result["agents"]["explorer:broad"]["prior"]["beta"] == 1.0

    def test_compact_applies_failure_event(self, tmp_path):
        from registry import compact_events
        reg_path = tmp_path / "registry.json"
        ev_path = tmp_path / "events.jsonl"
        self._write_registry(reg_path, {
            "reviewer:security": {"prior": {"alpha": 3.0, "beta": 1.0}, "dispatches": 3,
                                  "findings_produced": 2, "findings_used": 2,
                                  "findings_used_rate": 1.0, "missed_context_count": 0,
                                  "last_dispatched": None, "last_updated": None}
        })
        self._write_events(ev_path, [
            {"agent": "reviewer:security", "success": False, "timestamp": "2026-04-06T00:00:00"}
        ])
        compact_events(reg_path, ev_path)
        result = json.loads(reg_path.read_text())
        assert result["agents"]["reviewer:security"]["prior"]["alpha"] == 3.0
        assert result["agents"]["reviewer:security"]["prior"]["beta"] == 2.0

    def test_compact_truncates_events_file(self, tmp_path):
        from registry import compact_events
        reg_path = tmp_path / "registry.json"
        ev_path = tmp_path / "events.jsonl"
        self._write_registry(reg_path, {
            "explorer:broad": {"prior": {"alpha": 1.0, "beta": 1.0}, "dispatches": 0,
                               "findings_produced": 0, "findings_used": 0,
                               "findings_used_rate": 0.0, "missed_context_count": 0,
                               "last_dispatched": None, "last_updated": None}
        })
        self._write_events(ev_path, [
            {"agent": "explorer:broad", "success": True, "timestamp": "2026-04-06T00:00:00"}
        ])
        compact_events(reg_path, ev_path)
        assert ev_path.read_text() == ""

    def test_compact_creates_unknown_agent_entry(self, tmp_path):
        """Event for an agent not yet in registry should create a new entry."""
        from registry import compact_events
        reg_path = tmp_path / "registry.json"
        ev_path = tmp_path / "events.jsonl"
        self._write_registry(reg_path, {})
        self._write_events(ev_path, [
            {"agent": "architect:simplicity", "success": True, "timestamp": "2026-04-06T00:00:00"}
        ])
        compact_events(reg_path, ev_path)
        result = json.loads(reg_path.read_text())
        assert "architect:simplicity" in result["agents"]
        assert result["agents"]["architect:simplicity"]["prior"]["alpha"] == 2.0

    def test_compact_multiple_events_same_agent(self, tmp_path):
        from registry import compact_events
        reg_path = tmp_path / "registry.json"
        ev_path = tmp_path / "events.jsonl"
        self._write_registry(reg_path, {
            "impl:default": {"prior": {"alpha": 1.0, "beta": 1.0}, "dispatches": 0,
                             "findings_produced": 0, "findings_used": 0,
                             "findings_used_rate": 0.0, "missed_context_count": 0,
                             "last_dispatched": None, "last_updated": None}
        })
        self._write_events(ev_path, [
            {"agent": "impl:default", "success": True, "timestamp": "2026-04-06T00:00:00"},
            {"agent": "impl:default", "success": True, "timestamp": "2026-04-06T00:00:01"},
            {"agent": "impl:default", "success": False, "timestamp": "2026-04-06T00:00:02"},
        ])
        compact_events(reg_path, ev_path)
        result = json.loads(reg_path.read_text())
        assert result["agents"]["impl:default"]["prior"]["alpha"] == 3.0
        assert result["agents"]["impl:default"]["prior"]["beta"] == 2.0

    def test_compact_empty_events_is_noop(self, tmp_path):
        from registry import compact_events
        reg_path = tmp_path / "registry.json"
        ev_path = tmp_path / "events.jsonl"
        self._write_registry(reg_path, {
            "explorer:broad": {"prior": {"alpha": 5.0, "beta": 2.0}, "dispatches": 7,
                               "findings_produced": 4, "findings_used": 3,
                               "findings_used_rate": 0.75, "missed_context_count": 0,
                               "last_dispatched": None, "last_updated": None}
        })
        ev_path.write_text("")
        compact_events(reg_path, ev_path)
        result = json.loads(reg_path.read_text())
        assert result["agents"]["explorer:broad"]["prior"]["alpha"] == 5.0


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------

class TestRegistryInit:
    def test_init_creates_global_registry_file(self, registry_instance, tmp_path):
        global_path = tmp_path / "global" / "agent-registry.json"
        assert global_path.exists()

    def test_init_creates_project_registry_file(self, registry_instance, tmp_path):
        project_path = tmp_path / "project" / "agent-registry.json"
        assert project_path.exists()

    def test_init_global_has_schema_version(self, registry_instance, tmp_path):
        global_path = tmp_path / "global" / "agent-registry.json"
        data = json.loads(global_path.read_text())
        assert data.get("schema_version") == 2

    def test_init_global_has_agents_key(self, registry_instance, tmp_path):
        global_path = tmp_path / "global" / "agent-registry.json"
        data = json.loads(global_path.read_text())
        assert "agents" in data

    def test_init_does_not_overwrite_existing_registry(self, tmp_path):
        from registry import Registry
        global_path = tmp_path / "global" / "agent-registry.json"
        global_path.parent.mkdir(parents=True)
        existing = {"schema_version": 2, "agents": {"existing:agent": {"prior": {"alpha": 5.0, "beta": 2.0}, "dispatches": 7, "findings_produced": 4, "findings_used": 3, "findings_used_rate": 0.75, "missed_context_count": 0, "last_dispatched": None, "last_updated": None}}}
        global_path.write_text(json.dumps(existing))

        project_path = tmp_path / "project" / "agent-registry.json"
        project_path.parent.mkdir(parents=True)
        events_path = tmp_path / "events.jsonl"

        Registry(
            global_registry_path=global_path,
            project_registry_path=project_path,
            events_path=events_path,
        )
        data = json.loads(global_path.read_text())
        assert "existing:agent" in data["agents"]


class TestRegistryRecordEvent:
    def test_record_event_appends_to_jsonl(self, registry_instance, tmp_path):
        events_path = tmp_path / "registry-events.jsonl"
        registry_instance.record_event("explorer:broad", success=True)
        lines = [l for l in events_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["agent"] == "explorer:broad"
        assert event["success"] is True

    def test_record_event_has_timestamp(self, registry_instance, tmp_path):
        events_path = tmp_path / "registry-events.jsonl"
        registry_instance.record_event("explorer:broad", success=True)
        lines = [l for l in events_path.read_text().splitlines() if l.strip()]
        event = json.loads(lines[0])
        assert "timestamp" in event

    def test_record_multiple_events_appends(self, registry_instance, tmp_path):
        events_path = tmp_path / "registry-events.jsonl"
        registry_instance.record_event("explorer:broad", success=True)
        registry_instance.record_event("reviewer:security", success=False)
        lines = [l for l in events_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2


class TestRegistryCompact:
    def test_compact_applies_events_to_project_registry(self, registry_instance, tmp_path):
        # Seed project registry with a known agent
        project_path = tmp_path / "project" / "agent-registry.json"
        project_data = {
            "schema_version": 2,
            "agents": {
                "explorer:broad": {
                    "prior": {"alpha": 1.0, "beta": 1.0}, "dispatches": 0,
                    "findings_produced": 0, "findings_used": 0,
                    "findings_used_rate": 0.0, "missed_context_count": 0,
                    "last_dispatched": None, "last_updated": None,
                }
            }
        }
        project_path.write_text(json.dumps(project_data))

        registry_instance.record_event("explorer:broad", success=True)
        registry_instance.compact()

        result = json.loads(project_path.read_text())
        assert result["agents"]["explorer:broad"]["prior"]["alpha"] == 2.0

    def test_compact_truncates_events_file(self, registry_instance, tmp_path):
        events_path = tmp_path / "registry-events.jsonl"
        registry_instance.record_event("explorer:broad", success=True)
        registry_instance.compact()
        assert events_path.read_text() == ""


class TestRegistryGetEffectiveness:
    def test_get_effectiveness_blends_project_and_global(self, tmp_path):
        from registry import Registry
        global_path = tmp_path / "global" / "agent-registry.json"
        global_path.parent.mkdir(parents=True)
        project_path = tmp_path / "project" / "agent-registry.json"
        project_path.parent.mkdir(parents=True)
        events_path = tmp_path / "events.jsonl"

        global_data = {
            "schema_version": 2,
            "agents": {
                "explorer:broad": {
                    "prior": {"alpha": 3.0, "beta": 7.0}, "dispatches": 50,
                    "findings_produced": 0, "findings_used": 0, "findings_used_rate": 0.0,
                    "missed_context_count": 0, "last_dispatched": None, "last_updated": None,
                }
            }
        }
        project_data = {
            "schema_version": 2,
            "agents": {
                "explorer:broad": {
                    "prior": {"alpha": 8.0, "beta": 2.0}, "dispatches": 3,
                    "findings_produced": 0, "findings_used": 0, "findings_used_rate": 0.0,
                    "missed_context_count": 0, "last_dispatched": None, "last_updated": None,
                }
            }
        }
        global_path.write_text(json.dumps(global_data))
        project_path.write_text(json.dumps(project_data))

        reg = Registry(
            global_registry_path=global_path,
            project_registry_path=project_path,
            events_path=events_path,
        )
        effectiveness = reg.get_effectiveness("explorer:broad")
        # Project dispatches=3 < 5 → 0.7 * (8/10) + 0.3 * (3/10) = 0.56 + 0.09 = 0.65
        assert effectiveness == pytest.approx(0.65)

    def test_get_effectiveness_uses_global_only_when_no_project_entry(self, tmp_path):
        from registry import Registry
        global_path = tmp_path / "global" / "agent-registry.json"
        global_path.parent.mkdir(parents=True)
        project_path = tmp_path / "project" / "agent-registry.json"
        project_path.parent.mkdir(parents=True)
        events_path = tmp_path / "events.jsonl"

        global_data = {
            "schema_version": 2,
            "agents": {
                "reviewer:security": {
                    "prior": {"alpha": 4.0, "beta": 1.0}, "dispatches": 50,
                    "findings_produced": 0, "findings_used": 0, "findings_used_rate": 0.0,
                    "missed_context_count": 0, "last_dispatched": None, "last_updated": None,
                }
            }
        }
        project_data = {"schema_version": 2, "agents": {}}
        global_path.write_text(json.dumps(global_data))
        project_path.write_text(json.dumps(project_data))

        reg = Registry(
            global_registry_path=global_path,
            project_registry_path=project_path,
            events_path=events_path,
        )
        effectiveness = reg.get_effectiveness("reviewer:security")
        # No project entry → use global only → 4/5 = 0.8
        assert effectiveness == pytest.approx(0.8)

    def test_get_effectiveness_returns_0_5_for_unknown_agent(self, registry_instance):
        # Unknown agent → uniform prior → 0.5
        assert registry_instance.get_effectiveness("unknown:agent") == pytest.approx(0.5)
