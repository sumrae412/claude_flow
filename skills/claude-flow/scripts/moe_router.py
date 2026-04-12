"""moe_router.py — Mixture-of-Experts router for claude-flow.

Maps task fingerprints to learned expert configurations. Stdlib + registry.py only.
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from registry import fingerprint_similarity, compute_effectiveness, bayesian_update


# ---------------------------------------------------------------------------
# ExpertConfig dataclass
# ---------------------------------------------------------------------------

@dataclass
class ExpertConfig:
    id: str
    fingerprint_match: dict = field(default_factory=dict)
    explorer_experts: list[str] = field(default_factory=list)
    architect_bias: str | None = None
    reviewer_priority: list[str] = field(default_factory=list)
    thinking_budget_override: dict = field(default_factory=dict)
    constraint_sets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint_match": self.fingerprint_match,
            "explorer_experts": self.explorer_experts,
            "architect_bias": self.architect_bias,
            "reviewer_priority": self.reviewer_priority,
            "thinking_budget_override": self.thinking_budget_override,
            "constraint_sets": self.constraint_sets,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ExpertConfig":
        return cls(
            id=d["id"],
            fingerprint_match=d.get("fingerprint_match", {}),
            explorer_experts=d.get("explorer_experts", []),
            architect_bias=d.get("architect_bias"),
            reviewer_priority=d.get("reviewer_priority", []),
            thinking_budget_override=d.get("thinking_budget_override", {}),
            constraint_sets=d.get("constraint_sets", []),
        )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.5


def find_best_config(task_fingerprint: dict, configs: list[ExpertConfig]) -> ExpertConfig | None:
    """Return config with highest Jaccard similarity; None if all < 0.5."""
    best, best_score = None, 0.0
    for cfg in configs:
        score = fingerprint_similarity(task_fingerprint, cfg.fingerprint_match)
        if score > best_score:
            best, best_score = cfg, score
    return best if best_score >= SIMILARITY_THRESHOLD else None


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

_SKIP_THRESHOLD = 0.10  # effectiveness at or below 0.10 → skip
_MIN_DISPATCHES = 15     # require this many dispatches before skipping


def _should_skip(agent: str, reg_agents: dict) -> bool:
    """True if agent has enough data and poor effectiveness."""
    a = reg_agents.get(agent)
    if a is None:
        return False
    if a.get("dispatches", 0) < _MIN_DISPATCHES:
        return False
    eff = compute_effectiveness(a["prior"])
    return eff <= _SKIP_THRESHOLD


def merge_config_with_registry(config: ExpertConfig, registry_path: Path) -> ExpertConfig:
    """Return copy of config with low-value agents pruned using registry priors."""
    data = json.loads(Path(registry_path).read_text())
    agents = data.get("agents", {})

    filtered_explorers = [a for a in config.explorer_experts if not _should_skip(a, agents)]
    filtered_reviewers = [a for a in config.reviewer_priority if not _should_skip(a, agents)]

    from dataclasses import replace
    return replace(config,
                   explorer_experts=filtered_explorers,
                   reviewer_priority=filtered_reviewers)


def record_config_outcome(config_id: str, session_quality: float,
                          registry_path: Path) -> None:
    """Update config's Bayesian prior based on session quality (>= 0.6 = success)."""
    path = Path(registry_path)
    data = json.loads(path.read_text())
    configs = data.setdefault("expert_configs", {})
    if config_id not in configs:
        configs[config_id] = {"alpha": 1.0, "beta": 1.0, "uses": 0}

    prior = {"alpha": configs[config_id]["alpha"], "beta": configs[config_id]["beta"]}
    updated = bayesian_update(prior, success=(session_quality >= 0.6))
    configs[config_id]["alpha"] = updated["alpha"]
    configs[config_id]["beta"] = updated["beta"]
    configs[config_id]["uses"] = configs[config_id].get("uses", 0) + 1
    path.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Config creation
# ---------------------------------------------------------------------------

def create_config_from_session(fingerprint: dict, session_data: dict) -> ExpertConfig:
    """Propose a new ExpertConfig from a successful session's actual dispatch decisions."""
    config_id = session_data.get("config_id") or f"auto-{uuid.uuid4().hex[:8]}"
    return ExpertConfig(
        id=config_id,
        fingerprint_match=fingerprint,
        explorer_experts=session_data.get("explorer_agents", []),
        architect_bias=session_data.get("architect_bias"),
        reviewer_priority=session_data.get("reviewer_agents", []),
        thinking_budget_override=session_data.get("thinking_overrides", {}),
        constraint_sets=session_data.get("constraint_sets_used", []),
    )
