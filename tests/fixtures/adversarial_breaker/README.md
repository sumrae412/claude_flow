# adversarial-breaker fixtures

Golden fixture for the Phase 6 adversarial-breaker reviewer.

## Files

| File | Role | Provenance |
|---|---|---|
| `buggy_diff.patch` | Planted-bug input — TOCTOU race in a booking service | Hand-authored |
| `expected_scores.json` | Contract bounds the reviewer must hit — criterion below threshold + ANY-OF keyword set in break_case (semantic synonyms for the planted bug, not literal substrings) | Hand-authored |
| `recorded_response.json` | Cached LLM response — what the replay test asserts against | See `_meta.source` field |

## Two tests, two reliability levels

**`tests/test_adversarial_breaker.py::test_breaker_catches_planted_concurrency_bug`** (always-on)
- Reads `recorded_response.json` and asserts the contract bounds.
- Deterministic, fast, no API key needed.
- **Only as trustworthy as `recorded_response.json` itself** — see `_meta.source`.
  - `"synthetic-stub"` → tautological. Validates wiring, not capability.
  - `"test_adversarial_breaker_live.py"` → captured from a real LLM dispatch.

**`tests/test_adversarial_breaker_live.py::test_breaker_live_catches_planted_concurrency_bug`** (opt-in)
- Dispatches the real model with the persona file as system prompt.
- Asserts the same contract bounds against the live response.
- On success, **overwrites `recorded_response.json` with the captured response and `_meta` set to `"test_adversarial_breaker_live.py"`**.
- Requires `RUN_LIVE_LLM=1` and `ANTHROPIC_API_KEY`.

## Refresh the recording

```bash
make record-adversarial-fixture
# or:
RUN_LIVE_LLM=1 pytest tests/test_adversarial_breaker_live.py -v
```

After running, commit the updated `recorded_response.json`. The `_meta.recorded_at` and `_meta.model` fields document when and against which model the recording was captured.

## When to refresh

- After editing `skills/claude-flow/scripts/adversarial_breaker_persona.txt` — persona changes invalidate the recording.
- After bumping the model alias in `reviewer-registry.json` (currently `sonnet`) — different models score differently.
- Periodically as drift insurance (suggested: monthly, or weekly via a scheduled CI job — see `.github/workflows/` if/when wired up).
- Whenever the live test fails — investigate first; the failure may be a real capability regression rather than drift.

## Keyword-bounds gotcha

`expected_scores.json` uses `must_find_break_case_mentioning_any_of` (OR semantics, not AND) with a richer synonym set. An earlier draft used AND-semantics on three literal keywords (`["race", "lock", "concurrent"]`) — the synthetic stub satisfied it because I'd authored both the stub and the bounds with the same vocabulary. The first live LLM dispatch failed on that AND check because Sonnet caught the bug perfectly but said "two POST requests" instead of the literal word "concurrent". When extending this fixture or adding new ones, calibrate keyword bounds against real LLM output, not against synthetic stubs you wrote yourself.

## What this fixture does NOT validate

- Behavior on diffs other than the planted concurrency bug. The right home for broad capability validation is the `calibration` block in the registry entry — a labeled corpus of 20+ diffs with human-scored ground truth, agreement = `(|judge − human| ≤ 2) / n`. Treat this single fixture as a smoke test, not as calibration.
- The Phase 6 dispatch path. The live test calls the Anthropic API directly; production routes through the Task tool. Behavior should be substantially the same (same model + same system prompt + same user message), but a future hardening pass could swap the dispatch to the real Phase 6 runner once it lives in importable code.
