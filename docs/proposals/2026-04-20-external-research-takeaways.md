# External research takeaways — 2026-04-20

> **Status:** Proposal. Three discrete ideas from a 2026-04-20 pass over external Claude Code / LLM tooling. Each has its own "adopt / defer / reject" recommendation. Not a commitment to ship.

**Scope:** LSP plugin hooks, `token-optimizer-mcp` comparison, interview-skill pattern. Skipped from the same pass: the Moonshot PrfaaS paper (serving infra, not applicable), two founder-story Notion pages (not actionable), three X/Twitter links (unfetched by user request).

---

## 1. LSP plugin hooks — **recommend: spike, not adopt wholesale**

**Source:** <https://code.claude.com/docs/en/plugins-reference> — Plugins now support LSP servers via `.lsp.json`. Available: `pyright-lsp`, `typescript-lsp`, `rust-lsp`.

**Why it's interesting for claude_flow:**
The tier-1 hooks we ship today (`secret-detection`, `large-file-warning`, `build-before-commit`, `pre-edit-lint-gate-js`) are script-based — they grep files or shell out to formatters. An LSP server would let Claude see **real diagnostics** (type errors, unresolved imports, unused symbols) after every `Edit`/`Write`, pre-commit, as first-class context instead of "wait for the next build to fail."

**Candidate hook/plugin additions:**

| Idea | Trigger | Value |
|---|---|---|
| `pyright-lsp-gate` (tier 2, Python) | `PostToolUse: Edit\|Write` on `*.py` | Block on unresolved imports or type-errors introduced by this edit — catches the class of bug that gets past our existing `pre-edit-lint-gate-js` equivalent |
| `ts-lsp-gate` (tier 2, TypeScript) | same | TypeScript equivalent; dedup with the existing `pre-edit-lint-gate-js` (it's ad-hoc today) |
| `rust-lsp-gate` (tier 2, Rust) | same | New capability — no Rust gate today |

**Integration question:** Should this be a **plugin** (clean install path, versioning, user scope) or an extension to `hook-registry.json` (aligns with current platform model)? Plugin is probably correct — LSP binaries require user install anyway, so we can't bundle them, and the plugin marketplace handles that UX.

**Concrete next step (if we pursue):**
Write a `docs/plans/...-lsp-plugin-spike.md` that:
1. Stands up a minimal `claude-flow-lsp` plugin with `pyright-lsp` wired to CourierFlow.
2. Measures: does Claude actually use the diagnostics surface, or ignore it? (This is the real risk — LSP output is verbose; may worsen context rather than improve it.)
3. Decides go/no-go on the tier-2 gates above.

**Risks:**
- LSP diagnostics are noisy. May need an `advisory-only` pre-filter (same pattern as `Stop-hook memory triage`).
- Duplicates effort with existing `pre-edit-lint-gate-js` — consolidate, don't add alongside.
- Marketplace plugins we don't author can't be pinned in `install.sh`.

**Recommendation:** Low-priority spike. Not ahead of finishing Token Efficiency Phase 2. File this as a future-quarter idea.

---

## 2. `token-optimizer-mcp` — **recommend: reject (duplicates our work)**

**Source:** <https://github.com/ooples/token-optimizer-mcp>. Claims "95%+ token reduction through caching, compression, and smart tool intelligence."

**Relationship to our Phase 1 + Phase 2 work:**

| What `token-optimizer-mcp` claims | What we already shipped |
|---|---|
| Prompt caching | Phase 1 PR #43 — system/user split in `agent-sdk/pr-reviewer` with explicit cache breakpoints |
| Compression | Phase 2 item 1 (MEMORY.md trim) + items 2.a–2.h (progressive-disclosure audit) |
| "Smart tool intelligence" | Our brevity tooling + `--lite` flags on heavyweight orchestrators |

**Assessment:**
- The "95%+ reduction" headline is unfalsifiable without published benchmarks — the README is CI/release plumbing, no numbers. (WebFetch on the repo turned up 31 releases but no feature docs.)
- Everything it claims to do, we have scoped or shipped already, and ours is measured against real session traffic.
- Adding a third-party MCP for this increases surface area and creates a hidden dependency on someone else's compression heuristics.

**The one thing worth stealing:**
If their source shows a clever **progressive-disclosure heuristic** we missed, cherry-pick the idea — don't adopt the MCP.

**Recommendation:** Reject. Keep Phase 2 on our own track. Worth a 20-minute `src/` skim by whoever lands Phase 2 item 3 (tool-result auto-clearing hook) in case there's a specific trick we can lift. No integration.

---

## 3. Interview-skill pattern — **recommend: adopt, targeted**

**Source:** <https://github.com/olelehmann100kMRR/interview-skill> — A "run first on any creation task" gating skill with a 4-step methodology: (1) identify asset type, (2) expand full spec, (3) interview for gaps with **recommended answers not blank questions**, (4) synthesize into approved blueprint before handoff.

**Relationship to our existing skills:**
- `brainstorming` / `discover` / `user-stories` / `writing-plans` all cover adjacent ground.
- The distinguishing features of interview-skill worth pulling in:
  1. **Recommended answers, not blank questions.** ("Which auth — Auth0, Clerk, or roll our own? (Recommend: Clerk)" beats "Which auth provider?") — reduces cognitive load.
  2. **Batch questions.** Ask 3-5 at once, grouped, instead of sequential back-and-forth.
  3. **Pre-interview cut.** Validate the spec first; drop questions whose answers are inferable.
  4. **"Ambitious about scope"** — interview skill explicitly pushes back against scope creep during interview rather than accommodating every branch.

**Where this fits in claude_flow:**
- `brainstorming` (from superpowers) is already our gating skill pre-creation. It's good but doesn't enforce the "recommended answers" rule.
- **Concrete proposed change:** Add a **reference doc** `skills/code-creation-workflow/references/interview-patterns.md` codifying the four rules above. Phase 3 (requirements gathering) explicitly references it.

**Why not clone the whole skill:**
We already have the gating layer. A 400-line SKILL.md from another author creates drift and a second source of truth. A one-page reference we own is cheaper.

**Recommendation:** Adopt — write the one-page reference, wire Phase 3 to read it. Low effort, directly attacks the "agent asks vague blank questions" failure mode I've seen on past claude-flow runs.

---

## What's next

Pick any / none. If multiple, sequence:
1. **Interview-patterns reference** — small, self-contained, highest impact-per-effort.
2. **`token-optimizer-mcp` src skim** — 20 min during Phase 2 item 3.
3. **LSP spike** — after Phase 2 closes.
