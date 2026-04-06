# Advanced Agent Intelligence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MoE routing, neural-symbolic constraint verification, RAG 2.0 experience retrieval, causal inference, and federated learning to the code-creation-workflow.

**Architecture:** MoE + neural-symbolic as a tight foundation pair (unified dispatch pipeline). RAG 2.0, causal inference, and federated learning as independent composable layers. All build on the existing swarm registry.

**Tech Stack:** Python 3.11+ (scripts), OpenAI API (embeddings), numpy (vectors), httpx (Supabase), Markdown (skill/reference files)

**Design doc:** `docs/plans/2026-04-06-advanced-agent-intelligence-design.md`

---

## Dependency Graph

```
Task 1: MoE Router + Constraint Compiler + Symbolic Verifier (foundation pair)
Task 2: RAG 2.0 embedding pipeline                          ← no deps
Task 3: Causal inference module                              ← depends on Task 1 (uses dispatch pipeline)
Task 4: Federation module                                    ← depends on Task 1 (reads registry)
Task 5: Reference files + SKILL.md update                    ← depends on 1, 2, 3, 4
Task 6: Integration validation                               ← depends on all
```

Parallelizable: Tasks 1 + 2 (independent). Then 3 + 4 (independent). Then 5 → 6.

---

## Task 1: MoE Router + Constraint Compiler + Symbolic Verifier

**Files:**
- Create: `skills/code-creation-workflow/scripts/moe_router.py`
- Create: `skills/code-creation-workflow/scripts/constraint_compiler.py`
- Create: `skills/code-creation-workflow/scripts/symbolic_verifier.py`
- Create: `skills/code-creation-workflow/scripts/test_moe_router.py`
- Create: `skills/code-creation-workflow/scripts/test_constraint_compiler.py`
- Create: `skills/code-creation-workflow/scripts/test_symbolic_verifier.py`

These three form the unified dispatch pipeline. Build them together because they share data structures (constraint sets, expert configs).

### MoE Router

**Step 1: Write tests for moe_router.py**

Test these functions (see design doc Section 1 for exact behavior):
- `ExpertConfig` dataclass: fingerprint_match, explorer_experts, architect_bias, reviewer_priority, thinking_budget_override, constraint_sets
- `find_best_config(task_fingerprint, configs)` — returns config with highest Jaccard similarity, None if all below 0.5
- `merge_config_with_registry(config, registry)` — applies registry priors to config recommendations (skip low-value agents even if config lists them)
- `record_config_outcome(config_id, session_quality, registry)` — updates config's prior based on outcome
- `create_config_from_session(fingerprint, session_data)` — proposes new expert config from a successful session's actual dispatch decisions

**Step 2: Run tests, verify fail**

Run: `cd skills/code-creation-workflow/scripts && python3.11 -m pytest test_moe_router.py -v`

**Step 3: Implement moe_router.py**

Stdlib + import from `registry.py` (already exists). ExpertConfig as a dataclass. Router uses fingerprint_similarity from registry module. Config storage extends the registry JSON (new `expert_configs` key). Keep under 150 lines.

**Step 4: Run tests, verify pass**

### Constraint Compiler

**Step 5: Write tests for constraint_compiler.py**

Test these functions:
- `Constraint` dataclass: id, type (hard|soft), check method, pattern/rule, scope, message, source
- `compile_from_file(filepath, source_name)` — reads a markdown file (CLAUDE.md, defensive skill), extracts rule-like statements, returns list of Constraints. Hard constraints for patterns that can be grep/ast-grep checked, soft for everything else.
- `compile_from_architecture(architecture_decision_text)` — extracts design rules from Phase 4 output
- `compile_from_build_state(build_state)` — extracts consistency constraints from decisions_made and failed_approaches
- `merge_constraint_sets(sets)` — deduplicates by rule content, keeps highest-priority source
- `to_json(constraints)` / `from_json(data)` — serialization

**Step 6: Run tests, verify fail**

Run: `python3.11 -m pytest test_constraint_compiler.py -v`

**Step 7: Implement constraint_compiler.py**

Rule extraction from markdown: scan for imperative statements ("must", "always", "never", "do not", "required"). Classify as hard if the rule can be expressed as a file pattern (grep/ast-grep). Soft otherwise. Keep under 150 lines.

**Step 8: Run tests, verify pass**

### Symbolic Verifier

**Step 9: Write tests for symbolic_verifier.py**

Test these functions:
- `run_hard_check(constraint, file_path)` — executes grep/ast-grep/regex check, returns (pass/fail, details)
- `run_soft_check(constraint, code_diff, llm_client)` — sends constraint + diff to LLM, returns (pass/fail, violation_description). Mock the LLM client.
- `verify_output(constraints, changed_files, llm_client)` — runs all applicable constraints against changed files, returns VerificationResult with violations list
- `format_violations_for_retry(violations)` — formats violation list into a prompt block for agent retry

**Step 10: Run tests, verify fail**

Run: `python3.11 -m pytest test_symbolic_verifier.py -v`

**Step 11: Implement symbolic_verifier.py**

Hard checks shell out to grep/ast-grep (subprocess). Soft checks call the LLM with a focused prompt: "Does this code violate: [rule]? Answer YES/NO with the specific violation." Keep under 120 lines.

**Step 12: Run all three test files, verify pass**

Run: `python3.11 -m pytest test_moe_router.py test_constraint_compiler.py test_symbolic_verifier.py -v`

**Step 13: Commit**

```bash
git add skills/code-creation-workflow/scripts/moe_router.py \
       skills/code-creation-workflow/scripts/constraint_compiler.py \
       skills/code-creation-workflow/scripts/symbolic_verifier.py \
       skills/code-creation-workflow/scripts/test_moe_router.py \
       skills/code-creation-workflow/scripts/test_constraint_compiler.py \
       skills/code-creation-workflow/scripts/test_symbolic_verifier.py
git commit -m "feat(intelligence): MoE router, constraint compiler, symbolic verifier with TDD"
```

---

## Task 2: RAG 2.0 Embedding Pipeline

**Files:**
- Create: `skills/code-creation-workflow/scripts/rag.py`
- Create: `skills/code-creation-workflow/scripts/test_rag.py`

**Step 1: Write tests for rag.py**

Test these functions:
- `extract_chunks(exploration_log)` — extracts embeddable text chunks from a session's exploration log. Returns list of `Chunk(text, source_phase, source_type, timestamp, project_fingerprint, outcome_quality)`
- `embed_chunks(chunks, api_key)` — calls OpenAI text-embedding-3-small batch API, returns list of 1536-dim float vectors. Mock the API in tests.
- `VectorStore` class:
  - `__init__(path)` — loads index.json + embeddings.npy from disk, creates empty if missing
  - `add(chunks, vectors)` — appends to store, saves to disk
  - `query(query_vector, top_k=20)` — cosine similarity, returns top-K chunks with scores
  - `size` property — current chunk count
- `rerank(candidates, query_fingerprint, query_phase, current_time)` — applies 5-signal weighted re-ranking (similarity 0.3, fingerprint 0.25, recency 0.2, outcome 0.15, phase 0.1), returns top-5
- `format_for_injection(chunks)` — formats top-5 into a "PRIOR EXPERIENCE" prompt block

**Step 2: Run tests, verify fail**

Run: `python3.11 -m pytest test_rag.py -v`

**Step 3: Implement rag.py**

Dependencies: `openai` (embedding API), `numpy` (vector math). VectorStore saves index.json (metadata) + embeddings.npy (numpy array). Cosine similarity via numpy dot product on normalized vectors. Keep under 200 lines.

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add skills/code-creation-workflow/scripts/rag.py \
       skills/code-creation-workflow/scripts/test_rag.py
git commit -m "feat(intelligence): RAG 2.0 embedding pipeline with vector store and re-ranking"
```

---

## Task 3: Causal Inference Module

**Files:**
- Create: `skills/code-creation-workflow/scripts/causal.py`
- Create: `skills/code-creation-workflow/scripts/test_causal.py`

**Step 1: Write tests for causal.py**

Test these functions:
- `should_controlled_skip(agent_type, effectiveness, confidence, phase_skip_count)` — returns True for 5% of calls when agent is MODERATE/LOW, never for HIGH, never if phase already has a controlled skip. Use a seeded random for deterministic tests.
- `SessionQuality` dataclass: test_pass_rate, review_severity, retry_count, violation_count, user_satisfaction
- `compute_session_quality(metrics)` — weighted composite (0.3, 0.25, 0.2, 0.15, 0.1)
- `compute_causal_effect(with_outcomes, without_outcomes)` — mean difference + t-test p-value. Returns `CausalEffect(effect, p_value, sample_size_with, sample_size_without, significant)`
- `record_intervention(description, affected_agents, pre_quality, registry)` — appends intervention entry
- `stratify_by_complexity(agent_outcomes, complexity_scores)` — groups outcomes by complexity tier, returns per-tier effectiveness

**Step 2: Run tests, verify fail**

Run: `python3.11 -m pytest test_causal.py -v`

**Step 3: Implement causal.py**

Stdlib only (math, random, statistics). T-test implemented manually (no scipy dependency — we only need a basic two-sample test). Keep under 120 lines.

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add skills/code-creation-workflow/scripts/causal.py \
       skills/code-creation-workflow/scripts/test_causal.py
git commit -m "feat(intelligence): causal inference with controlled skip and propensity scoring"
```

---

## Task 4: Federation Module

**Files:**
- Create: `skills/code-creation-workflow/scripts/federation.py`
- Create: `skills/code-creation-workflow/scripts/test_federation.py`

**Step 1: Write tests for federation.py**

Test these functions:
- `FederationConfig` dataclass: enabled, push, pull, supabase_url, supabase_anon_key
- `anonymize_contribution(registry, project_fingerprint)` — extracts only safe data (alpha/beta deltas, config performance, calibration weights). Verify: no file paths, task descriptions, or project content in output.
- `push_contribution(contribution, contributor_hash, client)` — upserts to Supabase. Mock the HTTP client.
- `pull_federated_priors(project_fingerprint, client)` — queries matching fingerprints, returns weighted aggregated priors. Test with multiple mock contributions at varying similarity.
- `blend_federated_with_local(local_agent, federated_prior, local_dispatches)` — applies blending ratios (50/50 at <5, 70/30 at 5-15, 90/10 at >15 dispatches)
- `should_push(session_count)` — True every 5th session
- `meets_privacy_threshold(fingerprint_contributions)` — False if fewer than 3 unique contributors for a fingerprint

**Step 2: Run tests, verify fail**

Run: `python3.11 -m pytest test_federation.py -v`

**Step 3: Implement federation.py**

Dependencies: `httpx` (Supabase REST). Reuse the hash_api_key pattern from ToneGuard's sync.py. Push is POST with `Prefer: resolution=merge-duplicates`. Pull is GET with fingerprint filter. Keep under 150 lines.

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add skills/code-creation-workflow/scripts/federation.py \
       skills/code-creation-workflow/scripts/test_federation.py
git commit -m "feat(intelligence): federated learning with anonymized Supabase sync"
```

---

## Task 5: Reference Files + SKILL.md Update

**Files:**
- Create: `skills/code-creation-workflow/references/dispatch-pipeline.md`
- Create: `skills/code-creation-workflow/references/moe-expert-configs.md`
- Create: `skills/code-creation-workflow/references/constraint-sources.md`
- Modify: `skills/code-creation-workflow/SKILL.md`
- Modify: `skills/code-creation-workflow/references/swarm-schemas.md`
- Modify: `skills/code-creation-workflow/references/error-recovery.md`
- Modify: `skills/code-creation-workflow/references/common-mistakes.md`

### Reference files

**Step 1: Write dispatch-pipeline.md**

The unified dispatch pipeline protocol: MoE Router → Constraint Compiler → RAG Injection → Dispatch → Symbolic Verifier → Recording. Phase activation matrix. Component data flows. All from design doc Section 5.

**Step 2: Write moe-expert-configs.md**

Expert config JSON format. How configs are matched, created, learned, and shared via federation. Default starter configs for common fingerprints (python-api, python-api-with-migrations, js-frontend, fullstack). From design doc Section 1.

**Step 3: Write constraint-sources.md**

How constraints are extracted from each source (CLAUDE.md, defensive skills, architecture decisions, build-state, MEMORY.md, RAG failed approaches). Hard vs soft classification rules. Promotion protocol (recurring soft violations → hard checks). From design doc Section 1.

### Schema updates

**Step 4: Update swarm-schemas.md**

Add schemas for:
- Expert config (in registry)
- Constraint set (compiler output)
- Vector store (index.json format)
- Federated contribution
- Intervention entry
- Session quality metric
- Causal effect estimate

### SKILL.md update

**Step 5: Single pass through SKILL.md**

Add the unified dispatch pipeline as a new section after "Swarm Tiers" (before Phase 1). Every phase's dispatch instructions now reference the pipeline:

- Phase 0: add federation pull + constraint compiler init
- Phase 2: dispatch through pipeline (MoE selects explorer experts, RAG injects past findings)
- Phase 4: dispatch through pipeline (MoE selects architect bias, constraints from architecture fed back to compiler)
- Phase 5: dispatch through pipeline (full constraint verification active, causal controlled skip, build-state feeds constraints)
- Phase 6: dispatch through pipeline (MoE selects reviewer priority, causal controlled skip)
- Session end: RAG write pipeline, federation push (if 5th session), intervention recording

Update Quick Reference tables: add new agents (constraint verifier is implicit, not a separate agent), new scripts, new dependencies.

### Supporting file updates

**Step 6: Update error-recovery.md**

Add rows for: constraint compilation fails (DEGRADE — skip soft constraints, keep hard), RAG embedding API fails (DEGRADE — skip RAG context, memory-injection still works), symbolic verifier times out (DEGRADE — accept output, log for review), federation push fails (DEGRADE — local registry unaffected), causal controlled skip degrades quality (RETRY — immediately dispatch the skipped agent).

**Step 7: Update common-mistakes.md**

Add rows for: skipping symbolic verification "to save time", embedding every field not just experiential data, running controlled skip on HIGH value agents, federation without opt-in, ignoring constraint violations "because the test passes."

**Step 8: Commit**

```bash
git add skills/code-creation-workflow/references/dispatch-pipeline.md \
       skills/code-creation-workflow/references/moe-expert-configs.md \
       skills/code-creation-workflow/references/constraint-sources.md \
       skills/code-creation-workflow/references/swarm-schemas.md \
       skills/code-creation-workflow/references/error-recovery.md \
       skills/code-creation-workflow/references/common-mistakes.md \
       skills/code-creation-workflow/SKILL.md
git commit -m "feat(intelligence): dispatch pipeline docs, SKILL.md update, schema extensions"
```

---

## Task 6: Integration Validation

**Step 1: Run full test suite**

```bash
cd skills/code-creation-workflow/scripts
python3.11 -m pytest test_registry.py test_moe_router.py test_constraint_compiler.py \
  test_symbolic_verifier.py test_rag.py test_causal.py test_federation.py -v
```

Expected: All pass.

**Step 2: Cross-module integration test**

Write and run a focused integration test that exercises the full dispatch pipeline:

```bash
python3.11 -m pytest test_integration.py -v
```

Test: create a registry → init MoE router with a test config → compile constraints from a test CLAUDE.md → create a test vector store with 5 chunks → simulate a dispatch decision (including causal controlled skip logic) → verify all components produce valid output and the pipeline data flows correctly.

**Step 3: Structural validation**

Verify all cross-references in SKILL.md resolve:

```bash
grep -o 'references/[a-z-]*\.md' skills/code-creation-workflow/SKILL.md | sort -u | while read f; do
  test -f "skills/code-creation-workflow/$f" && echo "OK: $f" || echo "MISSING: $f"
done
```

**Step 4: Import validation**

Verify all scripts can import each other without circular dependencies:

```bash
python3.11 -c "from registry import Registry; from moe_router import find_best_config; from constraint_compiler import compile_from_file; from symbolic_verifier import verify_output; from rag import VectorStore; from causal import should_controlled_skip; from federation import anonymize_contribution; print('All imports OK')"
```

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "test(intelligence): integration validation and cross-module tests"
```
