# Decision — PR-Reviewer Revalidation Pass (FP-cut) Verdict

**Date:** 2026-05-29
**Status:** Decided
**Validates:** the `unverified` empirical claim shipped in [claude_flow#66](https://github.com/sumrae412/claude_flow/pull/66) and recorded in `CLAUDE.md` ("Empirical FP-cut on small PR diffs is unverified — A/B against your repo before relying on it").
**Harness:** [`agent-sdk/pr-reviewer/src/compare-revalidate.ts`](../../agent-sdk/pr-reviewer/src/compare-revalidate.ts)

## Decision

**Keep `PR_REVIEWER_REVALIDATE` OFF by default — confirmed.** The shipped default is correct.

Specifically:
- **Never enable on small diffs** (≤~50 lines, combined-reviewer path). FP-cut is thin (0–2 low-severity drops) at the *worst* cost ratio (4.6–5.5× review input).
- **It earns its cost on large / noisy / high-recall runs** — there it removed genuinely inflated findings, including a **false CRITICAL** and **four false HIGH** security findings. The existing CLAUDE.md guidance ("most useful when primary is high-recall/low-precision") holds and extends from the NVIDIA ensemble to the multi-reviewer Anthropic path on noisy files.
- **Before promoting it past opt-in, fix the caching** (see Follow-up #1). The current structure makes it 4.6–9.9× the review cost, not the documented "doubles cost."

## Evidence

A/B over 5 real claude_flow PRs, run 2026-05-29 on the production-default provider (**Anthropic `claude-sonnet-4-20250514`**, aggressive overshoot prompts). The harness runs the review pass **once**, then treats the post-dedup list as the OFF arm and `revalidateFindings(deduped)` as the ON arm — isolating the filter from review-pass run-to-run variance (which is large: a repeat #60 review produced 73 findings vs 47).

| PR | diff lines | reviewer path | OFF findings | revalidated | dropped (FP) | unverified (budget cap) | revalidate cost ratio¹ |
|---|---:|---|---:|---:|---:|---:|---:|
| #63 | 43 | combined | 5 | 5 | 0 | 0 | 5.46× |
| #45 | 44 | combined | 4 | 4 | 0 | 0 | 4.59× |
| #57 | 39 | combined | 5 | 5 | **2** | 0 | 5.51× |
| #60 | 203 | multi (3) | 47 | 30 | **4** | 17 | 9.90× |
| #66 | 558 | multi (6) | 67 | 30 | **7** | 37 | 9.90× |

¹ revalidate input tokens ÷ review input tokens.

### Drop accuracy: 13/13 correct, zero real bugs removed

Every dropped finding was hand-judged against the diff. All 13 were legitimate false positives or factually-wrong findings. **No real issue was dropped**, and the one genuine HIGH on #66 (`SEVERITY_ORDER` maintainability) was correctly kept.

High-value drops (the case for the feature):
- **#66 `cleanup-audit.sh:89` — false CRITICAL "command injection via grep patterns."** Patterns are hardcoded (`FIXME|XXX|HACK`), no user input. Correctly dropped.
- **#66 — 4 false HIGH** security findings (path traversal, arbitrary file read, conditional-failure) on a script with hardcoded literal paths and intentional `|| echo -1` fallbacks. Correctly dropped.
- **#66 `coverage.test.ts` "unused import"** — the import IS used as a return type. Factually wrong; correctly dropped.
- **#57 `CLAUDE.md:84` "2026 date is a typo, should be 2024"** — the date is on an unmodified line and 2026 is correct (repo date). Correctly dropped.

Low-value drops (the case against, on small diffs): #45 and #63 dropped nothing; #57 dropped 2 LOW/NITPICK doc-opinion findings. On small diffs the severity triage already de-emphasizes these, so the FP-cut adds little.

### Cost: the "doubles cost" claim is understated — actual 4.6–9.9×

`cache-read = 0` and `cache-create = 0` on **every** call in both arms. Root cause, confirmed by reading [`revalidate.ts`](../../agent-sdk/pr-reviewer/src/revalidate.ts):
- The **diff** (the large payload) is in the **user message**, which is never cached.
- The cached **system prompt** (`REVALIDATE_SYSTEM`, ~200 tokens) is **below the 1024-token cache floor**, so `cache_control` silently no-ops (see CLAUDE.md "Known Gotchas").

So each of N per-finding calls re-sends the full diff at full uncached input price. Cost scales as N × diff-tokens, which:
- on **small diffs** is *worse* than 2× (4.6–5.5×), because the OFF-arm review is a single cheap combined call that revalidate's N calls dwarf;
- on **large diffs** is ~9.9×, bounded only because the `PR_REVIEWER_MAX_REVALIDATE=30` cap stops the bleed (17 and 37 findings went unverified on #60/#66 — working as designed, severity-prioritized, and the high-value drops all fell inside the revalidated top-30).

### Cross-check: DeepSeek-chat (single model, soft prompts)

An earlier pass on `deepseek-chat` (via the OpenAI-compatible NVIDIA client) showed the same shape — drops accurate, cost 1.67–6.83× — but thinner finding sets (DeepSeek fired only 1 of 6 reviewers on #66). The Anthropic Sonnet numbers above supersede it as the production-faithful measurement; DeepSeek is retained only as a calibration sanity check.

## Limitations

- n=5 PRs, single review run per PR. Drop *accuracy* is robust (hand-judged, unanimous); drop *rate* is sample-specific.
- Three of five PRs are docs/script-heavy; the two code-heavy PRs (#60/#66 share `cleanup-audit.sh`) drove most drops, so the "noisy security reviewer" pattern is somewhat correlated to one file.
- Cost ratios are input-token only (revalidate output is one line — negligible). Dollar cost not computed; the ratio is the decision-relevant figure.

## Follow-ups

1. **Cache the diff before promoting revalidate past opt-in.** Move the diff into a ≥1024-token `cache_control` block shared across the N per-finding calls → ~90% input discount on the repeated diff (Anthropic). This flips the cost from 4.6–9.9× toward ~1× + small per-finding overhead and is the single change that would make "default on for large diffs" defensible. Until then, opt-in only.
2. **Update CLAUDE.md.** Replace "doubles cost across the findings list" with "4.6–9.9× review input on the current structure (diff re-sent uncached per finding); cacheable down to ~1× — see [`docs/decisions/2026-05-29-revalidate-verdict.md`](2026-05-29-revalidate-verdict.md)." Replace the "Empirical FP-cut … is unverified" line with a pointer to this record.
