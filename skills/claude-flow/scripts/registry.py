"""registry.py — Bayesian agent registry for claude-flow swarm.

Stdlib only: json, os, pathlib, datetime, math.
"""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _blank_agent() -> dict[str, Any]:
    return {
        "prior": {"alpha": 1.0, "beta": 1.0},
        "dispatches": 0,
        "findings_produced": 0,
        "findings_used": 0,
        "findings_used_rate": 0.0,
        "missed_context_count": 0,
        "last_dispatched": None,
        "last_updated": None,
    }


def _blank_registry() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "agents": {},
        "complexity_calibration": {
            "weights": {"reasoning_depth": 1.0, "ambiguity": 1.0,
                        "context_dependency": 1.0, "novelty": 1.0},
            "history": [],
        },
        "global_patterns": {
            "architecture_preferences": {"simplicity": 0.33, "separation": 0.33, "reuse": 0.33}
        },
        "project_fingerprints": {},
    }


# ---------------------------------------------------------------------------
# Bayesian core
# ---------------------------------------------------------------------------

def bayesian_update(prior: dict, success: bool) -> dict:
    """Increment alpha (success) or beta (failure). Does not mutate input."""
    updated = {"alpha": prior["alpha"], "beta": prior["beta"]}
    if success:
        updated["alpha"] += 1.0
    else:
        updated["beta"] += 1.0
    return updated


def compute_effectiveness(prior: dict) -> float:
    """Beta distribution mean: alpha / (alpha + beta)."""
    return prior["alpha"] / (prior["alpha"] + prior["beta"])


def blend_priors(project_agent: dict, global_agent: dict) -> float:
    """Blend project + global effectiveness.

    <5 dispatches: 0.70 project + 0.30 global
    >=15 dispatches: pure project
    5-15: linear interpolation
    """
    d = project_agent.get("dispatches", 0)
    p = compute_effectiveness(project_agent["prior"])
    g = compute_effectiveness(global_agent["prior"])
    if d < 5:
        w = 0.70
    elif d >= 15:
        w = 1.00
    else:
        w = 0.70 + ((d - 5) / 10) * 0.30
    return w * p + (1.0 - w) * g


# ---------------------------------------------------------------------------
# Fingerprint similarity
# ---------------------------------------------------------------------------

def _flatten(fp: dict) -> set:
    """Flatten fingerprint dict to string tag set for Jaccard comparison."""
    tags: set[str] = set()
    for k, v in fp.items():
        if isinstance(v, list):
            tags.update(str(x) for x in v)
        elif isinstance(v, bool):
            tags.add(f"{k}={'true' if v else 'false'}")
        else:
            tags.add(f"{k}={v}")
    return tags


def fingerprint_similarity(a: dict, b: dict) -> float:
    """Jaccard similarity on flattened fingerprint tag sets. Empty → 0.0."""
    ta, tb = _flatten(a), _flatten(b)
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# Decay
# ---------------------------------------------------------------------------

def apply_decay(agent: dict, factor: float = 0.85) -> dict:
    """Multiply alpha/beta by factor, floor at 1.0. Does not mutate input."""
    result = copy.deepcopy(agent)
    result["prior"]["alpha"] = max(1.0, agent["prior"]["alpha"] * factor)
    result["prior"]["beta"] = max(1.0, agent["prior"]["beta"] * factor)
    return result


# ---------------------------------------------------------------------------
# Dispatch decision
# ---------------------------------------------------------------------------

def dispatch_decision(effectiveness: float, confidence: float) -> str:
    """Return 'dispatch', 'skip', or 'reduced'.

    >0.3                           → dispatch
    0.1–0.3 and conf <=15          → dispatch  (insufficient data)
    <0.1 and conf >15              → skip
    0.1–0.3 and conf >15           → reduced
    all other cases                → dispatch  (safe default)
    """
    if effectiveness > 0.3:
        return "dispatch"
    if effectiveness < 0.1:
        return "skip" if confidence > 15 else "dispatch"
    # 0.1 <= effectiveness <= 0.3
    return "reduced" if confidence > 15 else "dispatch"


# ---------------------------------------------------------------------------
# Event compaction
# ---------------------------------------------------------------------------

def compact_events(registry_path: Path, events_path: Path) -> None:
    """Apply events JSONL to registry, then truncate the events file."""
    data = json.loads(registry_path.read_text())
    agents = data.setdefault("agents", {})

    events_text = events_path.read_text() if events_path.exists() else ""
    for line in events_text.splitlines():
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        key = ev["agent"]
        if key not in agents:
            agents[key] = _blank_agent()
        agents[key]["prior"] = bayesian_update(agents[key]["prior"], ev["success"])

    registry_path.write_text(json.dumps(data, indent=2))
    events_path.write_text("")


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------

class Registry:
    """Two-tier (global + project) Bayesian agent registry."""

    def __init__(self, global_registry_path: Path,
                 project_registry_path: Path, events_path: Path) -> None:
        self.global_path = Path(global_registry_path)
        self.project_path = Path(project_registry_path)
        self.events_path = Path(events_path)
        self._init_file(self.global_path)
        self._init_file(self.project_path)

    def _init_file(self, path: Path) -> None:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_blank_registry(), indent=2))

    def record_event(self, agent: str, success: bool, **extra) -> None:
        """Append event to JSONL (append-mode, POSIX atomic for small writes)."""
        event = {"agent": agent, "success": success,
                 "timestamp": datetime.now(timezone.utc).isoformat(), **extra}
        with open(self.events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def compact(self) -> None:
        """Compact events into project registry and truncate events file."""
        compact_events(self.project_path, self.events_path)

    def get_effectiveness(self, agent: str) -> float:
        """Return blended effectiveness; falls back to global, then uniform 0.5."""
        g_agents = json.loads(self.global_path.read_text()).get("agents", {})
        p_agents = json.loads(self.project_path.read_text()).get("agents", {})
        ga, pa = g_agents.get(agent), p_agents.get(agent)
        if pa is not None and ga is not None:
            return blend_priors(pa, ga)
        if ga is not None:
            return compute_effectiveness(ga["prior"])
        if pa is not None:
            return compute_effectiveness(pa["prior"])
        return 0.5  # uniform prior mean
