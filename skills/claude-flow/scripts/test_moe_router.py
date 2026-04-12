"""test_moe_router.py — TDD tests for moe_router.py.

Run: /opt/homebrew/bin/python3.11 -m pytest test_moe_router.py -v
"""

import json
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Imports under test (fail until moe_router.py exists)
# ---------------------------------------------------------------------------

from moe_router import (
    ExpertConfig,
    find_best_config,
    merge_config_with_registry,
    record_config_outcome,
    create_config_from_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_registry(tmp_path: Path, agents: dict | None = None) -> Path:
    """Write a minimal registry JSON and return its path."""
    data = {
        "schema_version": 2,
        "agents": agents or {},
        "expert_configs": {},
        "project_fingerprints": {},
        "global_patterns": {},
        "complexity_calibration": {"weights": {}, "history": []},
    }
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data))
    return p


# ---------------------------------------------------------------------------
# ExpertConfig dataclass
# ---------------------------------------------------------------------------

class TestExpertConfig:
    def test_all_fields_present(self):
        cfg = ExpertConfig(
            id="python-api",
            fingerprint_match={"languages": ["python"], "has_migrations": False},
            explorer_experts=["endpoint:route-chain"],
            architect_bias="separation",
            reviewer_priority=["security-reviewer"],
            thinking_budget_override={"data": "think harder"},
            constraint_sets=["defensive-backend"],
        )
        assert cfg.id == "python-api"
        assert cfg.fingerprint_match == {"languages": ["python"], "has_migrations": False}
        assert cfg.explorer_experts == ["endpoint:route-chain"]
        assert cfg.architect_bias == "separation"
        assert cfg.reviewer_priority == ["security-reviewer"]
        assert cfg.thinking_budget_override == {"data": "think harder"}
        assert cfg.constraint_sets == ["defensive-backend"]

    def test_optional_fields_have_defaults(self):
        cfg = ExpertConfig(
            id="minimal",
            fingerprint_match={},
        )
        assert cfg.explorer_experts == []
        assert cfg.architect_bias is None
        assert cfg.reviewer_priority == []
        assert cfg.thinking_budget_override == {}
        assert cfg.constraint_sets == []

    def test_to_dict_round_trip(self):
        cfg = ExpertConfig(
            id="round-trip",
            fingerprint_match={"languages": ["python"]},
            explorer_experts=["x"],
            architect_bias="simplicity",
            reviewer_priority=["r1"],
            thinking_budget_override={},
            constraint_sets=["s1"],
        )
        d = cfg.to_dict()
        assert d["id"] == "round-trip"
        assert d["fingerprint_match"] == {"languages": ["python"]}

    def test_from_dict(self):
        d = {
            "id": "from-dict",
            "fingerprint_match": {"languages": ["ts"]},
            "explorer_experts": ["e1"],
            "architect_bias": None,
            "reviewer_priority": [],
            "thinking_budget_override": {},
            "constraint_sets": [],
        }
        cfg = ExpertConfig.from_dict(d)
        assert cfg.id == "from-dict"
        assert cfg.fingerprint_match == {"languages": ["ts"]}


# ---------------------------------------------------------------------------
# find_best_config
# ---------------------------------------------------------------------------

class TestFindBestConfig:
    def _configs(self) -> list[ExpertConfig]:
        return [
            ExpertConfig(
                id="python-api",
                fingerprint_match={"languages": ["python"], "framework": "fastapi"},
            ),
            ExpertConfig(
                id="js-frontend",
                fingerprint_match={"languages": ["javascript"], "framework": "react"},
            ),
        ]

    def test_returns_best_match_above_threshold(self):
        task_fp = {"languages": ["python"], "framework": "fastapi", "has_auth": True}
        result = find_best_config(task_fp, self._configs())
        assert result is not None
        assert result.id == "python-api"

    def test_returns_none_when_all_below_threshold(self):
        # Completely different fingerprint
        task_fp = {"languages": ["rust"], "framework": "actix"}
        result = find_best_config(task_fp, self._configs())
        assert result is None

    def test_returns_none_for_empty_configs(self):
        assert find_best_config({"languages": ["python"]}, []) is None

    def test_jaccard_below_0_5_returns_none(self):
        # 1 match out of 4 unique tags → Jaccard < 0.5
        task_fp = {"languages": ["python"], "extra1": "a", "extra2": "b", "extra3": "c"}
        configs = [
            ExpertConfig(
                id="small-match",
                fingerprint_match={"languages": ["python"]},
            )
        ]
        result = find_best_config(task_fp, configs)
        # "python" in languages is a single tag; 1 / (4+0) = 0.25 → None
        assert result is None

    def test_exact_match_returns_config(self):
        task_fp = {"languages": ["python"], "framework": "fastapi"}
        configs = [
            ExpertConfig(id="exact", fingerprint_match={"languages": ["python"], "framework": "fastapi"})
        ]
        result = find_best_config(task_fp, configs)
        assert result is not None
        assert result.id == "exact"


# ---------------------------------------------------------------------------
# merge_config_with_registry
# ---------------------------------------------------------------------------

class TestMergeConfigWithRegistry:
    def test_skips_low_value_agents_from_reviewer_priority(self, tmp_path):
        reg_path = _make_registry(tmp_path, agents={
            "dead-reviewer": {"prior": {"alpha": 1.0, "beta": 10.0}, "dispatches": 20},
            "good-reviewer": {"prior": {"alpha": 9.0, "beta": 1.0}, "dispatches": 20},
        })
        cfg = ExpertConfig(
            id="test",
            fingerprint_match={},
            reviewer_priority=["dead-reviewer", "good-reviewer"],
        )
        merged = merge_config_with_registry(cfg, reg_path)
        assert "dead-reviewer" not in merged.reviewer_priority
        assert "good-reviewer" in merged.reviewer_priority

    def test_skips_low_value_agents_from_explorer_experts(self, tmp_path):
        reg_path = _make_registry(tmp_path, agents={
            "useless-explorer": {"prior": {"alpha": 1.0, "beta": 9.0}, "dispatches": 20},
            "great-explorer": {"prior": {"alpha": 8.0, "beta": 2.0}, "dispatches": 20},
        })
        cfg = ExpertConfig(
            id="test",
            fingerprint_match={},
            explorer_experts=["useless-explorer", "great-explorer"],
        )
        merged = merge_config_with_registry(cfg, reg_path)
        assert "useless-explorer" not in merged.explorer_experts
        assert "great-explorer" in merged.explorer_experts

    def test_preserves_agents_with_insufficient_data(self, tmp_path):
        # Low dispatches → not enough data, keep agent
        reg_path = _make_registry(tmp_path, agents={
            "new-agent": {"prior": {"alpha": 1.0, "beta": 3.0}, "dispatches": 3},
        })
        cfg = ExpertConfig(
            id="test",
            fingerprint_match={},
            reviewer_priority=["new-agent"],
        )
        merged = merge_config_with_registry(cfg, reg_path)
        assert "new-agent" in merged.reviewer_priority

    def test_unknown_agents_kept(self, tmp_path):
        reg_path = _make_registry(tmp_path)
        cfg = ExpertConfig(
            id="test",
            fingerprint_match={},
            reviewer_priority=["unknown-agent"],
        )
        merged = merge_config_with_registry(cfg, reg_path)
        assert "unknown-agent" in merged.reviewer_priority


# ---------------------------------------------------------------------------
# record_config_outcome
# ---------------------------------------------------------------------------

class TestRecordConfigOutcome:
    def test_good_outcome_increases_alpha(self, tmp_path):
        reg_path = _make_registry(tmp_path)
        # Pre-seed a config prior
        data = json.loads(reg_path.read_text())
        data["expert_configs"]["test-config"] = {"alpha": 2.0, "beta": 1.0, "uses": 0}
        reg_path.write_text(json.dumps(data))

        record_config_outcome("test-config", session_quality=0.9, registry_path=reg_path)

        updated = json.loads(reg_path.read_text())
        cfg_prior = updated["expert_configs"]["test-config"]
        assert cfg_prior["alpha"] > 2.0

    def test_poor_outcome_increases_beta(self, tmp_path):
        reg_path = _make_registry(tmp_path)
        data = json.loads(reg_path.read_text())
        data["expert_configs"]["bad-config"] = {"alpha": 1.0, "beta": 1.0, "uses": 0}
        reg_path.write_text(json.dumps(data))

        record_config_outcome("bad-config", session_quality=0.2, registry_path=reg_path)

        updated = json.loads(reg_path.read_text())
        cfg_prior = updated["expert_configs"]["bad-config"]
        assert cfg_prior["beta"] > 1.0

    def test_creates_entry_if_missing(self, tmp_path):
        reg_path = _make_registry(tmp_path)
        record_config_outcome("new-config", session_quality=0.7, registry_path=reg_path)
        data = json.loads(reg_path.read_text())
        assert "new-config" in data["expert_configs"]


# ---------------------------------------------------------------------------
# create_config_from_session
# ---------------------------------------------------------------------------

class TestCreateConfigFromSession:
    def test_returns_expert_config(self):
        fingerprint = {"languages": ["python"], "framework": "django"}
        session_data = {
            "explorer_agents": ["endpoint:route-chain", "data:queries"],
            "architect_bias": "separation",
            "reviewer_agents": ["security-reviewer"],
            "thinking_overrides": {"data": "think harder"},
            "constraint_sets_used": ["defensive-backend"],
        }
        cfg = create_config_from_session(fingerprint, session_data)
        assert isinstance(cfg, ExpertConfig)
        assert cfg.fingerprint_match == fingerprint
        assert "endpoint:route-chain" in cfg.explorer_experts
        assert cfg.architect_bias == "separation"
        assert "security-reviewer" in cfg.reviewer_priority

    def test_id_is_auto_generated(self):
        cfg = create_config_from_session({"languages": ["python"]}, {})
        assert cfg.id is not None
        assert len(cfg.id) > 0

    def test_minimal_session_data(self):
        cfg = create_config_from_session({}, {})
        assert isinstance(cfg, ExpertConfig)
        assert cfg.explorer_experts == []
