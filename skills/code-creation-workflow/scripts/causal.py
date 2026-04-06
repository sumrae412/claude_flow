"""Causal inference: controlled skip, session quality, effect estimation, interventions."""
import json, math, random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def should_controlled_skip(agent_type: str, effectiveness: float, confidence: float,
                            phase_skip_count: int, seed: Optional[int] = None) -> bool:
    """5% skip for MODERATE (0.1–0.3) and LOW (<0.1) agents; never HIGH; never if phase skipped."""
    if effectiveness > 0.3 or phase_skip_count > 0:
        return False
    return random.Random(seed).random() < 0.05


@dataclass
class SessionQuality:
    test_pass_rate: float       # 0–1
    review_severity: float      # 0–1 (higher = worse)
    retry_count: int            # raw; clipped at _MAX_RETRIES
    violation_count: int        # raw; clipped at _MAX_VIOLATIONS
    user_satisfaction: float    # 0–1
    _MAX_RETRIES: int = field(default=5, init=False, repr=False)
    _MAX_VIOLATIONS: int = field(default=10, init=False, repr=False)


def compute_session_quality(m: SessionQuality) -> float:
    """Weighted composite quality in [0,1]: 0.3+0.25+0.2+0.15+0.1."""
    r = min(m.retry_count / m._MAX_RETRIES, 1.0)
    v = min(m.violation_count / m._MAX_VIOLATIONS, 1.0)
    return 0.30*m.test_pass_rate + 0.25*(1-m.review_severity) + 0.20*(1-r) + 0.15*(1-v) + 0.10*m.user_satisfaction


@dataclass
class CausalEffect:
    effect: float; p_value: float; sample_size_with: int; sample_size_without: int; significant: bool


def _mean(xs): return sum(xs) / len(xs)
def _var(xs): m = _mean(xs); return sum((x-m)**2 for x in xs) / (len(xs)-1)


def _ibeta(a, b, x):
    """Regularized incomplete beta I_x(a,b) via Lentz continued fraction."""
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    if x > (a+1)/(a+b+2): return 1.0 - _ibeta(b, a, 1-x)
    lfront = a*math.log(x) + b*math.log(1-x) - math.lgamma(a) - math.lgamma(b) + math.lgamma(a+b)
    front = math.exp(lfront) / a
    f = C = 1e-300; D = 0.0
    for i in range(400):
        m2 = i // 2
        d = (m2*(b-m2)*x / ((a+i-1)*(a+i))) if i % 2 == 0 and i > 0 else (-(a+m2)*(a+b+m2)*x / ((a+i)*(a+i+1))) if i % 2 else 1.0
        if i == 0: d = 1.0
        D = 1/(1+d*D) if abs(1+d*D) > 1e-300 else 1e300
        C = 1+d/C if abs(C) > 1e-300 else 1.0
        delta = C*D; f *= delta
        if i > 0 and abs(delta-1) < 1e-10: return front * f
    return front * f


def _welch_p(a, b):
    n1, n2 = len(a), len(b)
    v1, v2 = _var(a), _var(b)
    se = math.sqrt(v1/n1 + v2/n2)
    if se == 0: return 1.0
    t = abs((_mean(a) - _mean(b)) / se)
    df_n, df_d = (v1/n1+v2/n2)**2, (v1/n1)**2/(n1-1)+(v2/n2)**2/(n2-1)
    df = df_n/df_d if df_d > 0 else 1.0
    return float(_ibeta(df/2, 0.5, df/(df+t*t)))


def compute_causal_effect(with_outcomes: list, without_outcomes: list) -> CausalEffect:
    """Mean difference + manual Welch t-test. Significant if p < 0.1."""
    effect = _mean(with_outcomes) - _mean(without_outcomes)
    p = _welch_p(with_outcomes, without_outcomes)
    return CausalEffect(effect, p, len(with_outcomes), len(without_outcomes), p < 0.1)


def record_intervention(description: str, affected_agents: list, pre_quality: float, registry_path: str) -> None:
    """Append intervention entry to registry JSON."""
    try:
        with open(registry_path) as f: data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): data = {}
    data.setdefault("interventions", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": description, "affected_agents": affected_agents, "pre_quality": pre_quality,
    })
    with open(registry_path, "w") as f: json.dump(data, f, indent=2)


def stratify_by_complexity(agent_outcomes: list, complexity_scores: list) -> dict:
    """Group outcomes by tier: simple (<4), moderate (4–6), complex (7+)."""
    if len(agent_outcomes) != len(complexity_scores):
        raise ValueError(f"Length mismatch: {len(agent_outcomes)} outcomes vs {len(complexity_scores)} scores")
    tiers: dict = {}
    for outcome, score in zip(agent_outcomes, complexity_scores):
        tiers.setdefault("complex" if score >= 7 else "moderate" if score >= 4 else "simple", []).append(outcome)
    return tiers
