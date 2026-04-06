# MoE Expert Configs

> Expert configs bundle model + prompt + budget + constraints per task signature. Stored in registry under `expert_configs` key.

---

## Config Format

```json
{
  "config_id": "python-api-with-migrations",
  "fingerprint_match": {"languages": ["python"], "has_migrations": true},
  "explorer_experts": ["endpoint:route-chain", "data:migration-queries"],
  "architect_bias": "separation",
  "reviewer_priority": ["migration-reviewer", "security-reviewer", "async-reviewer"],
  "thinking_budget_override": {"data": "think harder"},
  "constraint_sets": ["defensive-backend", "alembic-safety"],
  "prior": {"alpha": 2, "beta": 1},
  "created_from": "session_2026-04-06T14:00:00Z"
}
```

| Field | Description |
|-------|-------------|
| `fingerprint_match` | Keys/values to match against project fingerprint |
| `explorer_experts` | Explorer variants to prefer (Phase 2) |
| `architect_bias` | Default architecture optimization target (Phase 4) |
| `reviewer_priority` | Reviewer dispatch order (Phase 6) |
| `thinking_budget_override` | Per-domain budget overrides |
| `constraint_sets` | Named constraint sets to load |
| `prior` | Bayesian prior — decayed on poor outcomes, reinforced on good |

---

## Matching

1. Compute Jaccard similarity between task fingerprint and each config's `fingerprint_match`
2. Highest similarity config wins
3. Threshold: similarity >= 0.5 to use config; below 0.5 falls back to registry-informed dispatch

---

## Learning Lifecycle

| Event | Action |
|-------|--------|
| Good session outcome (quality > 0.7) | `alpha += 1` on used config |
| Poor session outcome (quality < 0.4) | `beta += 1` on used config |
| Novel fingerprint + good outcome | Auto-create new config from session's actual dispatch decisions |
| Config prior drops below 0.3 expected value | Mark inactive (still queryable, not auto-selected) |

---

## Federation Sharing

1. Top-performing configs (expected value > 0.6, 5+ sessions) are candidates for push
2. Pushed as part of federated contribution (anonymized — no file paths or task descriptions)
3. Pulled configs start with low-confidence prior (`alpha=2, beta=1`) until local evidence confirms

---

## Starter Configs

**python-api:** `{"fingerprint_match": {"languages": ["python"], "has_external_apis": true}, "explorer_experts": ["endpoint:route-chain", "data:service-layer"], "architect_bias": "separation", "reviewer_priority": ["security-reviewer", "async-reviewer"], "constraint_sets": ["defensive-backend"]}`

**python-api-with-migrations:** `{"fingerprint_match": {"languages": ["python"], "has_migrations": true}, "explorer_experts": ["endpoint:route-chain", "data:migration-queries"], "architect_bias": "separation", "reviewer_priority": ["migration-reviewer", "security-reviewer"], "thinking_budget_override": {"data": "think harder"}, "constraint_sets": ["defensive-backend", "alembic-safety"]}`

**js-frontend:** `{"fingerprint_match": {"languages": ["javascript"], "layer_count": 2}, "explorer_experts": ["ui:component-tree", "ui:state-flow"], "architect_bias": "simplicity", "reviewer_priority": ["async-reviewer"], "constraint_sets": ["defensive-ui"]}`

**fullstack:** `{"fingerprint_match": {"languages": ["python", "javascript"], "layer_count": 4}, "explorer_experts": ["endpoint:route-chain", "ui:component-tree", "data:service-layer"], "architect_bias": "separation", "reviewer_priority": ["security-reviewer", "async-reviewer", "migration-reviewer"], "thinking_budget_override": {"data": "think harder", "routes": "think harder"}, "constraint_sets": ["defensive-backend", "defensive-ui"]}`
