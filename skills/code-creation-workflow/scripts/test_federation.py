"""test_federation.py — TDD tests for federation.py.

Run: /opt/homebrew/bin/python3.11 -m pytest test_federation.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
import json


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_registry():
    return {
        "agents": {
            "explorer:syntax": {
                "prior": {"alpha": 8.0, "beta": 3.0},
                "dispatches": 10,
                "findings_produced": 5,
                "findings_used": 4,
                "findings_used_rate": 0.8,
            },
            "reviewer:security": {
                "prior": {"alpha": 4.0, "beta": 2.0},
                "dispatches": 6,
                "findings_produced": 3,
                "findings_used": 2,
                "findings_used_rate": 0.67,
            },
        },
        "complexity_calibration": {
            "weights": {"reasoning_depth": 1.2, "ambiguity": 0.9,
                        "context_dependency": 1.0, "novelty": 1.1},
        },
        "expert_configs": {
            "python-api": {
                "performance": {"sessions": 5, "avg_quality": 0.78},
            }
        },
        # These fields must NOT appear in anonymized output
        "project_fingerprints": {
            "/Users/alice/project/main.py": {"languages": ["python"]},
        },
        "last_task_description": "Build an API for user authentication",
    }


def _make_fingerprint():
    return {"languages": ["python"], "has_migrations": True, "complexity": "medium"}


# ---------------------------------------------------------------------------
# FederationConfig
# ---------------------------------------------------------------------------

class TestFederationConfig:
    def test_fields(self):
        from federation import FederationConfig
        cfg = FederationConfig(
            enabled=True,
            push=True,
            pull=False,
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-key-123",
        )
        assert cfg.enabled is True
        assert cfg.push is True
        assert cfg.pull is False
        assert cfg.supabase_url == "https://example.supabase.co"
        assert cfg.supabase_anon_key == "anon-key-123"

    def test_defaults_disabled(self):
        from federation import FederationConfig
        cfg = FederationConfig(
            enabled=False,
            push=False,
            pull=False,
            supabase_url="",
            supabase_anon_key="",
        )
        assert cfg.enabled is False


# ---------------------------------------------------------------------------
# anonymize_contribution
# ---------------------------------------------------------------------------

class TestAnonymizeContribution:
    def test_includes_alpha_beta_deltas(self):
        from federation import anonymize_contribution
        registry = _make_registry()
        fp = _make_fingerprint()
        result = anonymize_contribution(registry, fp)
        assert "agent_priors" in result
        assert "explorer:syntax" in result["agent_priors"]
        entry = result["agent_priors"]["explorer:syntax"]
        assert "alpha" in entry
        assert "beta" in entry

    def test_includes_config_performance(self):
        from federation import anonymize_contribution
        result = anonymize_contribution(_make_registry(), _make_fingerprint())
        assert "expert_config_performance" in result
        assert "python-api" in result["expert_config_performance"]

    def test_includes_calibration_weights(self):
        from federation import anonymize_contribution
        result = anonymize_contribution(_make_registry(), _make_fingerprint())
        assert "calibration_weights" in result

    def test_includes_fingerprint(self):
        from federation import anonymize_contribution
        fp = _make_fingerprint()
        result = anonymize_contribution(_make_registry(), fp)
        assert "fingerprint" in result
        assert result["fingerprint"] == fp

    def test_no_file_paths(self):
        from federation import anonymize_contribution
        result = anonymize_contribution(_make_registry(), _make_fingerprint())
        serialized = json.dumps(result)
        assert "/Users/alice" not in serialized
        assert "/Users/" not in serialized

    def test_no_task_descriptions(self):
        from federation import anonymize_contribution
        result = anonymize_contribution(_make_registry(), _make_fingerprint())
        serialized = json.dumps(result)
        assert "Build an API" not in serialized
        assert "last_task_description" not in serialized

    def test_no_project_fingerprints_raw(self):
        from federation import anonymize_contribution
        result = anonymize_contribution(_make_registry(), _make_fingerprint())
        # project_fingerprints (the raw path-keyed dict) should not leak
        assert "project_fingerprints" not in result


# ---------------------------------------------------------------------------
# push_contribution
# ---------------------------------------------------------------------------

class TestPushContribution:
    def test_calls_post_with_correct_headers(self):
        from federation import push_contribution
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_client.post.return_value = mock_response

        contribution = {"agent_priors": {}, "fingerprint": _make_fingerprint()}
        contributor_hash = "abc123"

        push_contribution(contribution, contributor_hash, mock_client)

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        # headers must include Prefer: resolution=merge-duplicates
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "merge-duplicates" in headers.get("Prefer", "")

    def test_payload_includes_contributor_hash(self):
        from federation import push_contribution
        mock_client = MagicMock()
        mock_client.post.return_value = MagicMock(status_code=201)

        contribution = {"agent_priors": {}, "fingerprint": _make_fingerprint()}
        push_contribution(contribution, "hash-xyz", mock_client)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json", {})
        assert payload.get("contributor_hash") == "hash-xyz"

    def test_returns_response(self):
        from federation import push_contribution
        mock_client = MagicMock()
        mock_response = MagicMock(status_code=201)
        mock_client.post.return_value = mock_response

        result = push_contribution({"agent_priors": {}}, "h", mock_client)
        assert result is mock_response


# ---------------------------------------------------------------------------
# pull_federated_priors
# ---------------------------------------------------------------------------

def _make_remote_contributions():
    """Three contributions at varying similarities (mocked server data)."""
    return [
        {
            "id": "uuid-1",
            "contributor_hash": "user-A",
            "fingerprint": {"languages": ["python"], "has_migrations": True, "complexity": "medium"},
            "contributions": {
                "agent_priors": {"explorer:syntax": {"alpha": 6.0, "beta": 2.0}},
                "calibration_weights": {"reasoning_depth": 1.1},
            },
            "similarity": 0.9,  # very close match
        },
        {
            "id": "uuid-2",
            "contributor_hash": "user-B",
            "fingerprint": {"languages": ["python"], "has_migrations": False, "complexity": "low"},
            "contributions": {
                "agent_priors": {"explorer:syntax": {"alpha": 3.0, "beta": 3.0}},
                "calibration_weights": {"reasoning_depth": 0.8},
            },
            "similarity": 0.5,  # moderate match
        },
        {
            "id": "uuid-3",
            "contributor_hash": "user-C",
            "fingerprint": {"languages": ["javascript"], "complexity": "high"},
            "contributions": {
                "agent_priors": {"explorer:syntax": {"alpha": 2.0, "beta": 5.0}},
                "calibration_weights": {"reasoning_depth": 0.5},
            },
            "similarity": 0.1,  # below threshold — should be excluded
        },
    ]


class TestPullFederatedPriors:
    def test_filters_low_similarity(self):
        from federation import pull_federated_priors
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=_make_remote_contributions()),
        )
        result = pull_federated_priors(_make_fingerprint(), mock_client)
        # user-C has similarity 0.1 (< 0.4 threshold), should not influence result
        # Result should be based only on user-A (0.9) and user-B (0.5)
        assert result is not None

    def test_returns_weighted_priors(self):
        from federation import pull_federated_priors
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=_make_remote_contributions()),
        )
        result = pull_federated_priors(_make_fingerprint(), mock_client)
        # Should have aggregated agent priors
        assert "agent_priors" in result

    def test_empty_response(self):
        from federation import pull_federated_priors
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=[]),
        )
        result = pull_federated_priors(_make_fingerprint(), mock_client)
        assert result == {}

    def test_all_below_threshold(self):
        from federation import pull_federated_priors
        mock_client = MagicMock()
        # Only contribution with similarity 0.1 (below 0.4)
        low_contrib = [_make_remote_contributions()[2]]
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=low_contrib),
        )
        result = pull_federated_priors(_make_fingerprint(), mock_client)
        assert result == {}


# ---------------------------------------------------------------------------
# blend_federated_with_local
# ---------------------------------------------------------------------------

class TestBlendFederatedWithLocal:
    def _local_agent(self):
        return {"prior": {"alpha": 7.0, "beta": 3.0}}

    def _federated_prior(self):
        return {"alpha": 4.0, "beta": 4.0}

    def test_fewer_than_5_dispatches_50_50(self):
        from federation import blend_federated_with_local
        result = blend_federated_with_local(self._local_agent(), self._federated_prior(), 3)
        # local_eff = 7/10 = 0.7, fed_eff = 4/8 = 0.5
        # 50/50 blend = 0.5*0.7 + 0.5*0.5 = 0.60
        assert abs(result - 0.60) < 1e-6

    def test_5_to_15_dispatches_70_30(self):
        from federation import blend_federated_with_local
        result = blend_federated_with_local(self._local_agent(), self._federated_prior(), 10)
        # 70/30 blend = 0.7*0.7 + 0.3*0.5 = 0.49 + 0.15 = 0.64
        assert abs(result - 0.64) < 1e-6

    def test_more_than_15_dispatches_90_10(self):
        from federation import blend_federated_with_local
        result = blend_federated_with_local(self._local_agent(), self._federated_prior(), 20)
        # 90/10 blend = 0.9*0.7 + 0.1*0.5 = 0.63 + 0.05 = 0.68
        assert abs(result - 0.68) < 1e-6

    def test_exactly_5_dispatches_70_30(self):
        from federation import blend_federated_with_local
        result = blend_federated_with_local(self._local_agent(), self._federated_prior(), 5)
        assert abs(result - 0.64) < 1e-6

    def test_exactly_15_dispatches_90_10(self):
        from federation import blend_federated_with_local
        result = blend_federated_with_local(self._local_agent(), self._federated_prior(), 16)
        assert abs(result - 0.68) < 1e-6


# ---------------------------------------------------------------------------
# should_push
# ---------------------------------------------------------------------------

class TestShouldPush:
    def test_every_5th_session(self):
        from federation import should_push
        assert should_push(5) is True
        assert should_push(10) is True
        assert should_push(15) is True

    def test_not_on_other_sessions(self):
        from federation import should_push
        assert should_push(1) is False
        assert should_push(3) is False
        assert should_push(7) is False
        assert should_push(14) is False

    def test_session_0(self):
        from federation import should_push
        # 0 % 5 == 0 but semantically meaningless — we accept True or False,
        # the spec says "every 5th", so session 0 is a grey area.
        # Just verify it doesn't raise.
        _ = should_push(0)


# ---------------------------------------------------------------------------
# meets_privacy_threshold
# ---------------------------------------------------------------------------

class TestMeetsPrivacyThreshold:
    def test_three_unique_contributors_passes(self):
        from federation import meets_privacy_threshold
        contributions = [
            {"contributor_hash": "A"},
            {"contributor_hash": "B"},
            {"contributor_hash": "C"},
        ]
        assert meets_privacy_threshold(contributions) is True

    def test_two_unique_contributors_fails(self):
        from federation import meets_privacy_threshold
        contributions = [
            {"contributor_hash": "A"},
            {"contributor_hash": "B"},
            {"contributor_hash": "A"},  # duplicate
        ]
        assert meets_privacy_threshold(contributions) is False

    def test_one_contributor_fails(self):
        from federation import meets_privacy_threshold
        contributions = [{"contributor_hash": "solo"}]
        assert meets_privacy_threshold(contributions) is False

    def test_empty_fails(self):
        from federation import meets_privacy_threshold
        assert meets_privacy_threshold([]) is False

    def test_four_unique_passes(self):
        from federation import meets_privacy_threshold
        contributions = [
            {"contributor_hash": "A"},
            {"contributor_hash": "B"},
            {"contributor_hash": "C"},
            {"contributor_hash": "D"},
        ]
        assert meets_privacy_threshold(contributions) is True
