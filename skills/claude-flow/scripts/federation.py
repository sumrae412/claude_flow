"""federation.py — Federated learning: anonymized Supabase prior sync.

Dependencies: httpx (HTTP client, mock in tests). Stdlib: dataclasses.
Imports fingerprint_similarity from registry.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from registry import fingerprint_similarity

_TABLE = "/rest/v1/federated_priors"
_PULL_THRESHOLD = 0.4


@dataclass
class FederationConfig:
    enabled: bool
    push: bool
    pull: bool
    supabase_url: str
    supabase_anon_key: str


def anonymize_contribution(registry: dict, project_fingerprint: dict) -> dict:
    """Extract only safe data: alpha/beta deltas, config performance, calibration weights.

    Explicitly excludes: file paths, task descriptions, project_fingerprints,
    dispatch histories, and any raw session content.
    """
    agent_priors: dict[str, Any] = {
        name: {"alpha": data["prior"].get("alpha", 1.0), "beta": data["prior"].get("beta", 1.0)}
        for name, data in registry.get("agents", {}).items()
        if "prior" in data
    }
    expert_config_performance: dict[str, Any] = {
        cfg: data["performance"]
        for cfg, data in registry.get("expert_configs", {}).items()
        if "performance" in data
    }
    calibration_weights = registry.get("complexity_calibration", {}).get("weights", {})
    return {
        "fingerprint": project_fingerprint,
        "agent_priors": agent_priors,
        "expert_config_performance": expert_config_performance,
        "calibration_weights": calibration_weights,
    }


def push_contribution(contribution: dict, contributor_hash: str, client: Any) -> Any:
    """Upsert anonymized contribution to Supabase via POST with merge-duplicates."""
    payload = {
        "fingerprint": contribution.get("fingerprint", {}),
        "contributions": {
            "agent_priors": contribution.get("agent_priors", {}),
            "calibration_weights": contribution.get("calibration_weights", {}),
        },
        "expert_configs": contribution.get("expert_config_performance", {}),
        "complexity_weights": contribution.get("calibration_weights", {}),
        "contributor_hash": contributor_hash,
        "version": 1,
    }
    headers = {
        "Content-Type": "application/json",
        "Prefer": "return=minimal,resolution=merge-duplicates",
    }
    return client.post(_TABLE, json=payload, headers=headers)


def pull_federated_priors(project_fingerprint: dict, client: Any) -> dict:
    """GET matching contributions from Supabase; return similarity-weighted aggregated priors.

    Only contributions with fingerprint similarity >= 0.4 are included.
    """
    response = client.get(_TABLE)
    if response.status_code != 200:
        return {}
    all_contributions: list[dict] = response.json()
    if not all_contributions:
        return {}

    scored = [
        (fingerprint_similarity(project_fingerprint, c.get("fingerprint", {})), c)
        for c in all_contributions
    ]
    scored = [(s, c) for s, c in scored if s >= _PULL_THRESHOLD]
    if not scored:
        return {}

    total_weight = sum(s for s, _ in scored)
    aggregated_priors: dict[str, dict[str, float]] = {}
    for sim, contrib in scored:
        w = sim / total_weight
        for agent, prior in contrib.get("contributions", {}).get("agent_priors", {}).items():
            if agent not in aggregated_priors:
                aggregated_priors[agent] = {"alpha": 0.0, "beta": 0.0}
            aggregated_priors[agent]["alpha"] += w * prior.get("alpha", 1.0)
            aggregated_priors[agent]["beta"] += w * prior.get("beta", 1.0)
    return {"agent_priors": aggregated_priors}


def blend_federated_with_local(
    local_agent: dict, federated_prior: dict, local_dispatches: int
) -> float:
    """Blend local and federated effectiveness by dispatch count.

    <5 dispatches → 50/50, 5-15 → 70/30, >15 → 90/10 (local always dominates over time).
    """
    lp = local_agent.get("prior", {"alpha": 1.0, "beta": 1.0})
    local_eff = lp["alpha"] / (lp["alpha"] + lp["beta"])
    fed_eff = federated_prior["alpha"] / (federated_prior["alpha"] + federated_prior["beta"])
    if local_dispatches < 5:
        w = 0.50
    elif local_dispatches <= 15:
        w = 0.70
    else:
        w = 0.90
    return w * local_eff + (1.0 - w) * fed_eff


def should_push(session_count: int) -> bool:
    """True when session_count is a non-zero multiple of 5."""
    return session_count > 0 and session_count % 5 == 0


def meets_privacy_threshold(contributions: list[dict]) -> bool:
    """False if fewer than 3 unique contributor_hash values (prevents deanonymization)."""
    return len({c["contributor_hash"] for c in contributions if "contributor_hash" in c}) >= 3
