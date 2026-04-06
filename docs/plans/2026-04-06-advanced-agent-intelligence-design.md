# Advanced Agent Intelligence for code-creation-workflow

**Date:** 2026-04-06
**Branch:** feat/advanced-agent-intelligence
**Depends on:** swarm intelligence (merged to main)
**Status:** Design approved, ready for implementation planning

## Problem

The swarm intelligence system dispatches agents based on Bayesian priors and tiered protocols, but agents are still selected statically (registry lookup), validated after the fact (review phases), provided context by keyword matching (memory-injection), optimized by correlation (periodic review), and learned in isolation (per-user only).

## Five enhancements

| Component | What it replaces | What it adds |
|-----------|-----------------|-------------|
| MoE Router | Registry-informed dispatch | Learned expert configurations that bundle model + prompt + budget + constraints per task signature |
| Neural-symbolic | Post-hoc review catching violations | Pre-generation constraint injection + post-generation deterministic verification |
| RAG 2.0 | Keyword-based memory-injection | Semantic retrieval of past experience via embeddings + re-ranking |
| Causal inference | Correlation-based periodic review | Controlled experiments + propensity scoring to measure actual agent impact |
| Federated learning | Per-user isolated learning | Cross-user aggregated priors via Supabase without sharing raw data |

## Architecture: Grouped

**Foundation pair:** MoE Router + Neural-symbolic (tight integration — constraint compiler informs routing, routing informs constraint selection)

**Independent enhancements:** RAG 2.0, Causal inference, Federated learning (each composable, can be enabled/disabled independently)

---

## Section 1: MoE Router + Neural-Symbolic Foundation

### Unified dispatch pipeline

Every agent dispatch flows through:

```
Task → MoE Router → Constraint Compiler → RAG Context Injection
  → Agent Dispatch → Symbolic Verifier → Post-Dispatch Recording
```

### MoE Router

Maps task signature to expert configuration. Expert configs stored in registry:

```json
{
  "expert_configs": {
    "python-api-with-migrations": {
      "fingerprint_match": {"languages": ["python"], "has_migrations": true},
      "explorer_experts": ["endpoint:route-chain", "data:migration-queries"],
      "architect_bias": "separation",
      "reviewer_priority": ["migration-reviewer", "security-reviewer", "async-reviewer"],
      "thinking_budget_override": {"data": "think harder"},
      "constraint_sets": ["defensive-backend", "alembic-safety"]
    }
  }
}
```

**Router logic:**
1. Compute task fingerprint
2. Find expert config with highest fingerprint similarity (Jaccard)
3. If similarity < 0.5: fall back to registry-informed dispatch (current behavior)
4. If match: use config's recommendations for all dispatch decisions this session

**Learning:** After each session, record which config was used and session outcome. Configs with poor outcomes get decayed. Good outcomes get reinforced. Novel fingerprints that produce good results trigger automatic new config creation via session-learnings.

### Constraint Compiler

**Input sources compiled at session start, refreshed on architecture decisions:**

| Source | Constraint type | Example |
|--------|----------------|---------|
| CLAUDE.md | Project rules | "All routes must use auth decorator" |
| Defensive skills | Pattern rules | "No bare except clauses" |
| Architecture decision (Phase 4) | Design rules | "All data access through repository classes" |
| Build-state decisions | Consistency rules | "Use Decimal for amounts (step 1)" |
| MEMORY.md gotchas | Known traps | "phone field is nullable — always check" |
| RAG failed approaches | Experience rules | "Raw SQL bypasses ORM events in this codebase" |

**Output:** Constraint set with `hard` (deterministic check) and `soft` (LLM judgment) assertions:

```json
{
  "constraints": [
    {"id": "c1", "type": "hard", "check": "grep", "pattern": "@auth_required", "scope": "routes/*.py", "message": "All routes must have @auth_required"},
    {"id": "c2", "type": "hard", "check": "ast-grep", "pattern": "except Exception:", "scope": "**/*.py", "message": "No bare Exception catches"},
    {"id": "c3", "type": "soft", "rule": "All data access through repository classes", "source": "architecture-decision"},
    {"id": "c4", "type": "soft", "rule": "Amount fields use Decimal, not float", "source": "build-state-step-1"}
  ]
}
```

### Symbolic Verifier

Runs after each agent produces code:
- Hard constraints: deterministic (grep, ast-grep, regex). Instant, zero-cost.
- Soft constraints: one lightweight LLM call per soft constraint. "Does this code violate: [rule]? YES/NO with specific violation."
- If violations: agent retries with violations in prompt (max 2 retries)
- If clean: output accepted

**Feedback loops:**
- Violation rate feeds MoE router (configs producing many violations get deprioritized)
- Recurring violations (5+ times) get promoted from post-hoc check to agent system prompt
- Violation patterns feed constraint compiler (new hard checks created for repeated soft violations)

---

## Section 2: RAG 2.0 — Experience Retrieval

### What gets embedded

| Source | Chunk unit |
|--------|-----------|
| Exploration findings | Per-explorer patterns_found + gaps |
| Failed approaches | Per-step failed_approaches entry |
| Agent discoveries | completed_with_discovery signals |
| Review patterns | Meta-reviewer patterns_escalated |
| Build-state decisions | Per-step decisions_made |
| Review-to-exploration feedback | Feedback entries |

### Vector store

Local file-based at `~/.claude/swarm/vectors/` (global) and `.claude/swarm/vectors/` (project):

```
index.json        # Metadata: chunk_id, text, source, fingerprint, timestamp, outcome
embeddings.npy    # Float32 vectors, 1536-dim (text-embedding-3-small)
```

Numpy cosine similarity on flat array — sufficient at scale of hundreds to low thousands of chunks.

### Re-ranking pipeline

Top-20 by cosine similarity → re-rank to top-5:

| Signal | Weight | Logic |
|--------|--------|-------|
| Semantic similarity | 0.3 | Cosine score |
| Project fingerprint match | 0.25 | Jaccard similarity |
| Recency | 0.2 | Exponential decay (week=1.0, month=0.5, older=0.2) |
| Outcome quality | 0.15 | Source session's quality score |
| Source phase match | 0.1 | Same-phase chunks weighted higher |

No LLM call for re-ranking — all signals computable from metadata.

### Integration

Agent prompts receive three context blocks:
1. PROJECT GOTCHAS (memory-injection — curated, always included)
2. PRIOR EXPERIENCE (RAG 2.0 — retrieved, task-specific)
3. CONSTRAINTS (neural-symbolic — compiled rules)

RAG feeds constraint compiler: retrieved failed approaches can be promoted to soft constraints.

### Write pipeline (session end)

1. Extract embeddable chunks from exploration-log
2. Batch embed via OpenAI text-embedding-3-small ($0.00004/session)
3. Append to index.json + embeddings.npy
4. Retention: 90 days full vectors, then delete (insights already in registry)

---

## Section 3: Causal Inference

### Mechanism 1: Controlled skip experiments

5% of dispatches for MODERATE and LOW value agents are randomly skipped. Records session outcome without that agent for comparison.

**Rules:**
- Never skip HIGH value agents
- Max 1 controlled skip per phase per session
- After 20 controlled skips per agent: compute causal effect estimate
- `controlled_skip` is a distinct registry event type

**Causal effect:**
```
causal_effect = avg_quality_with_agent - avg_quality_without_agent
p < 0.1 → proven causal value
p ≈ neutral → agent is noise, safe to permanent-skip
p < 0 → agent hurts (deprioritize)
```

**Session quality metric:**

| Signal | Weight |
|--------|--------|
| Test pass rate (first attempt) | 0.3 |
| Review finding severity (inverse) | 0.25 |
| Retry count (inverse) | 0.2 |
| Constraint violations (inverse) | 0.15 |
| User satisfaction (accept rate) | 0.1 |

### Mechanism 2: Propensity scoring

Agent effectiveness compared per complexity stratum, not raw. A reviewer finding 0 issues on a simple task means nothing. Finding 0 on a complex task is informative.

Feeds MoE router: expert configs can specify "only include agent X when complexity > threshold."

### Mechanism 3: Intervention analysis

When prompts/protocols change, record an intervention entry in registry. Track pre/post session quality with interrupted time-series. Session-learnings auto-records intervention entries when skill changes are made.

```json
{
  "interventions": [
    {
      "timestamp": "...",
      "description": "Updated security-reviewer prompt",
      "affected_agents": ["security-reviewer"],
      "pre_quality": 0.72,
      "post_quality": 0.81,
      "sessions_since": 8,
      "estimated_effect": 0.09,
      "confidence": "moderate"
    }
  ]
}
```

---

## Section 4: Federated Learning

### What gets shared (anonymized)

Fingerprint contributions: per-agent alpha/beta deltas, expert config performance, complexity calibration weights. No file paths, task descriptions, code, or project content.

### Supabase schema

New table in ToneGuard's Supabase project:

```sql
CREATE TABLE federated_priors (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  fingerprint JSONB NOT NULL,
  contributions JSONB NOT NULL,
  expert_configs JSONB DEFAULT '{}',
  complexity_weights JSONB DEFAULT '{}',
  contributor_hash TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_federated_fingerprint ON federated_priors USING GIN (fingerprint);
```

No user-scoped RLS — intentionally shared. Minimum 3 contributors per fingerprint before serving priors (prevents small-population deanonymization).

### Push (every 5th session)

Compute fingerprint contribution from session deltas → anonymize → upsert to Supabase.

### Pull (session start)

Query matching fingerprints (similarity > 0.4) → weight by similarity × sample size → blend into local registry:
- Local < 5 dispatches: 50/50 local/federated
- Local 5-15: 70/30
- Local > 15: 90/10

Local always dominates as data accumulates. Federated priors inform starting points, not override experience.

### Expert config sharing

Top-performing expert configs for matching fingerprints pulled and added to MoE router as low-confidence candidates (alpha=2, beta=1) until local evidence confirms or rejects.

### Opt-in, off by default

```json
{ "federation": { "enabled": true, "push": true, "pull": true } }
```

---

## Section 5: Integration

### Unified dispatch pipeline

```
Task → MoE Router → Constraint Compiler → RAG Context Injection
  → Agent Dispatch → Symbolic Verifier → Post-Dispatch Recording
```

### Phase activation matrix

| Phase | MoE | Constraints | RAG | Causal | Federated |
|-------|-----|-------------|-----|--------|-----------|
| 0 Context | — | — | — | — | Pull priors |
| 1 Classify | — | — | Informs scoring | — | Calibration weights |
| 2 Explore | Select experts | — | Past findings | Controlled skip | — |
| 4 Architect | Select bias | Architecture constraints | Past decisions | Controlled skip | — |
| 5 Implement | Select budgets | Full constraint set + verify | Failed approaches | Controlled skip | — |
| 6 Review | Select priority | Verify findings | Past patterns | Controlled skip | — |
| End | — | — | Embed chunks | Record quality | Push deltas |

### Component data flows

- MoE Router reads registry (local + federated) and RAG experience
- Constraint Compiler reads CLAUDE.md, defensive skills, architecture decisions, build-state, RAG failed approaches
- RAG reads/writes vector store, feeds MoE and Constraint Compiler
- Symbolic Verifier reads constraint set, feeds MoE (violation rates) and Constraint Compiler (promotion)
- Causal reads/writes registry controlled_skip data, feeds dispatch decisions
- Federated reads/writes Supabase, feeds registry initial priors and MoE expert configs

### New files

| File | Location | Purpose |
|------|----------|---------|
| `constraint-compiler.py` | `scripts/` | Extract rules → produce assertion sets |
| `symbolic-verifier.py` | `scripts/` | Run hard+soft checks on agent output |
| `moe-router.py` | `scripts/` | Map task signature → expert config |
| `rag.py` | `scripts/` | Embed, store, retrieve, re-rank |
| `causal.py` | `scripts/` | Controlled skip, effect estimation |
| `federation.py` | `scripts/` | Push/pull anonymized priors to Supabase |
| `test_*.py` | `scripts/` | TDD tests for each module |
| `swarm-integration.md` | `references/` | Component interaction protocol |
| `moe-expert-configs.md` | `references/` | Expert config format and management |
| `constraint-sources.md` | `references/` | Constraint extraction from each source |

### Dependencies

| Package | Used by | Purpose |
|---------|---------|---------|
| `openai` | RAG 2.0 | text-embedding-3-small |
| `numpy` | RAG 2.0 | Vector storage + cosine similarity |
| `httpx` | Federation | Supabase REST (async) |

`openai` and `httpx` already in ToneGuard deps. `numpy` is the only new dependency.
