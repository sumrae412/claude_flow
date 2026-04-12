# Constraint Sources

> How the Constraint Compiler extracts rules from each source. See `dispatch-pipeline.md` for where constraints fit in the pipeline.

---

## Extraction by Source

| Source | When Compiled | Extraction Method | Example Constraint |
|--------|--------------|-------------------|-------------------|
| CLAUDE.md | Session start | Scan for imperative statements (must, always, never, required) | "All routes must use auth decorator" |
| Defensive skills | Session start | Extract pattern rules from loaded defensive skill | "No bare except clauses" |
| Architecture decisions (Phase 4) | After user chooses | Parse chosen architecture's rules and assumptions | "All data access through repository classes" |
| Build-state decisions | After each Phase 5 step | Extract from `decisions_made` and `patterns_used` | "Use Decimal for amounts" |
| MEMORY.md gotchas | Session start + refresh | Scan gotcha entries for warnings and traps | "phone field is nullable -- always check" |
| RAG failed approaches | On RAG retrieval | Promote retrieved failed approaches to soft constraints | "Raw SQL bypasses ORM events in this codebase" |

---

## Hard vs Soft Classification

| Classification | Criteria | Check Method | Cost |
|---------------|----------|-------------|------|
| **Hard** | Rule expressible as a file pattern (grep, ast-grep, regex) | Deterministic subprocess | Zero LLM cost |
| **Soft** | Rule requires judgment or context to evaluate | Single focused LLM call per constraint | ~100 tokens per check |

**Decision rule:** If you can write a grep/regex/ast-grep pattern that reliably detects the violation, classify as hard. Everything else is soft.

**Examples:**

| Rule | Type | Check |
|------|------|-------|
| "All routes must have @auth_required" | Hard | `grep -L "@auth_required" routes/*.py` |
| "No bare Exception catches" | Hard | `ast-grep -p "except Exception:"` |
| "All data access through repository classes" | Soft | LLM judgment on code diff |
| "Amount fields use Decimal, not float" | Soft | LLM judgment (naming alone is ambiguous) |

---

## Promotion Protocol

Recurring soft constraint violations get promoted to hard checks:

1. Track violation count per soft constraint across sessions
2. At 5+ violations for the same soft constraint: flag for promotion
3. Attempt to write a grep/ast-grep pattern that catches the violation
4. If pattern achievable: promote to hard constraint (update constraint set)
5. If pattern not achievable: inject the soft constraint into agent system prompts instead (pre-generation prevention)

**Promotion is one-way.** Hard constraints are never demoted to soft. If a hard check produces false positives, fix the pattern or remove the constraint entirely.
