# Unified Dispatch Pipeline

> Every agent dispatch flows through this pipeline. Components degrade independently — partial pipeline is always better than no pipeline.

---

## Pipeline Stages

```
Task → MoE Router → Constraint Compiler → RAG Context Injection
  → Agent Dispatch → Symbolic Verifier → Post-Dispatch Recording
```

| Stage | Input | Output | Can Skip? |
|-------|-------|--------|-----------|
| 1. MoE Router | Task fingerprint + registry | Expert config (or default) | Yes — falls back to registry-informed dispatch |
| 2. Constraint Compiler | CLAUDE.md, skills, architecture, build-state, MEMORY.md, RAG | Constraint set (hard + soft) | Yes — no constraints injected |
| 3. RAG Context Injection | Query vector + vector store | Top-5 experience chunks | Yes — memory-injection still runs |
| 4. Agent Dispatch | Config + constraints + RAG context | Agent prompt + response | No — core dispatch |
| 5. Symbolic Verifier | Agent output + constraint set | Pass / violations list | Yes — output accepted unchecked |
| 6. Recording | Dispatch result + quality signals | Registry events + RAG chunks | Yes — no learning this session |

---

## Phase Activation Matrix

| Phase | MoE Router | Constraint Compiler | RAG Injection | Causal Skip | Symbolic Verifier | Federation |
|-------|-----------|-------------------|--------------|-------------|------------------|-----------|
| 0 Context | -- | Init from CLAUDE.md + skills | -- | -- | -- | Pull priors |
| 1 Classify | -- | -- | Informs scoring | -- | -- | Calibration weights |
| 2 Explore | Select explorer experts | -- | Past findings | 5% MODERATE/LOW | -- | -- |
| 4 Architect | Select bias | Add architecture constraints | Past decisions | 5% MODERATE/LOW | -- | -- |
| 5 Implement | Select thinking budgets | Full set + verify after each agent | Failed approaches | 5% MODERATE/LOW | Active (hard + soft) | -- |
| 6 Review | Select reviewer priority | Verify reviewer findings | Past review patterns | 5% MODERATE/LOW | Active (hard only) | -- |
| Session End | -- | -- | Write chunks | Record quality metric | -- | Push deltas (every 5th) |

---

## Component Data Flows

1. **MoE Router** reads: registry (local + federated), RAG experience, task fingerprint
2. **Constraint Compiler** reads: CLAUDE.md, defensive skills, architecture decisions, build-state, MEMORY.md, RAG failed approaches
3. **RAG** reads/writes: vector store. Feeds: MoE (experience context), Constraint Compiler (failed approaches as soft constraints)
4. **Symbolic Verifier** reads: constraint set. Feeds: MoE (violation rates decay configs), Constraint Compiler (recurring soft violations promoted to hard)
5. **Causal** reads/writes: registry controlled_skip data. Feeds: dispatch decisions (skip/include)
6. **Federation** reads/writes: Supabase. Feeds: registry initial priors, MoE expert configs

---

## Retry on Verification Failure

1. Verifier returns violations list
2. Format violations into retry prompt block (`format_violations_for_retry`)
3. Re-dispatch agent with violations appended (max 2 retries)
4. If still failing after 2 retries: accept output, log violations for review

---

## Scripts

| Script | Purpose |
|--------|---------|
| `moe_router.py` | Fingerprint matching, config selection, config learning |
| `constraint_compiler.py` | Rule extraction, constraint set assembly |
| `symbolic_verifier.py` | Hard checks (grep/ast-grep) + soft checks (LLM) |
| `rag.py` | Embed, store, retrieve, re-rank experience |
| `causal.py` | Controlled skip, quality metric, effect estimation |
| `federation.py` | Anonymized push/pull to Supabase |
