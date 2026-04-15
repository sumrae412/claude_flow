# Reviewer Registry Schema

Reference documentation for `reviewer-registry.json` — the declarative config that drives Phase 6's cascading review. This file is for documentation; the runtime parser is `skills/claude-flow/scripts/select_reviewers.py`.

## Top-level shape

```json
{
  "version": "1.0",
  "description": "...",
  "reviewers": [ { ...entry... }, ... ]
}
```

## Entry shape

Two flavors of entry coexist: **agent-dispatched** (the default — a subagent runs the review) and **CLI-backed** (a shell script runs the review, useful for non-Anthropic models or external tools).

### Common fields (all entries)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique identifier, kebab-case. Used in logs and as the reviewer reference in Phase 6 output. |
| `tier` | `"always"` \| `"conditional"` | yes | `always`: runs every review pass. `conditional`: runs only if `file_patterns` match the diff. |
| `cascade_tier` | integer | yes | Phase 6 dispatch bucket (1-5). **Tier 1 is reserved for the broad first-pass sweep (CodeRabbit) that enables early-exit. New `always` reviewers go at Tier ≥ 2.** |
| `description` | string | yes | One-line summary for humans. |
| `model` | string | no | Model identifier for observability. Not runtime-consumed for CLI-backed entries. |

### Agent-dispatched fields

Use when the reviewer is a Claude subagent invoked via the Task tool.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `subagent_type` | string | yes | Agent type passed to the Task tool (e.g. `coderabbit:code-reviewer`, `security-reviewer`). |
| `file_patterns` | `[string]` | if `tier == "conditional"` | Glob patterns (e.g. `alembic/**/*.py`). |
| `content_pattern` | string | no | Regex for file contents; combined with `threshold` to require N matches. |
| `threshold` | integer | no | Minimum `content_pattern` match count to trigger the reviewer. Default `0`. |

### CLI-backed fields

Use when the reviewer is a shell script that shells out to an external tool (non-Anthropic model, linter, security scanner). Established by `curmudgeon-review` in this schema.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `runner` | string | yes | Runner kind, used for dispatch routing (`"codex-cli"` today; future: `"gemini-cli"`, `"semgrep-cli"`, etc.). |
| `runner_script` | string (repo-relative path) | yes | Path to the script Phase 6 invokes with the diff file as `$1`. |

The runner script's contract:

1. **Input:** a single argv — the path to a unified-diff file.
2. **Output (stdout):** a single JSON object `{"reviewer": "<id>", "findings": [{"file":str, "line":int, "severity":"HIGH"|"MEDIUM"|"LOW", "title":str, "rationale":str}, ...]}`.
3. **Graceful skip:** if the external CLI or a required input is missing, emit the **skip envelope** on stdout and exit 0:
   ```json
   {"reviewer": "<id>", "findings": [], "skipped": true, "reason": "<one-line explanation>"}
   ```
   Do NOT exit non-zero; Phase 6 treats non-zero as a real failure.
4. **Stderr:** human-readable warnings (e.g. "curmudgeon: codex CLI not found"). Not parsed by Phase 6.

### Skip envelope: canonical branches

Reference implementation (`scripts/curmudgeon_review.sh`) emits skip envelopes from three branches:

| Branch | Reason string | When |
|---|---|---|
| Missing external CLI | `"<cli> CLI not installed"` | `command -v <cli>` fails |
| Missing input file | `"diff file not found"` | `[ ! -f "$1" ]` |
| Malformed external output | `"malformed output from <cli>"` | External emits non-JSON or unexpected shape |

Future CLI-backed runners should emit the envelope from the same three branches at minimum.

## Early-exit invariant

Phase 6 cascades Tier 1 → Tier 2-4 with an early-exit gate: **if Tier 1 (CodeRabbit) returns no HIGH+ findings, Tiers 2-4 are skipped entirely**. Any `always` reviewer whose cost should be avoided on clean diffs must therefore be at `cascade_tier >= 2`. The test `tests/test_reviewer_registry.py::test_all_always_reviewers_have_cascade_tier` guards against future entries that omit `cascade_tier` and land in an un-early-exit-able bucket.

## Adding a new reviewer

1. Pick an `id` (kebab-case, domain prefix if extending a family).
2. Decide agent-dispatched vs CLI-backed (default to agent-dispatched; CLI-backed only when the reviewer is not a Claude agent — non-Anthropic models, external linters, security scanners).
3. For CLI-backed: author the runner script per the contract above. Test missing-CLI, missing-input, and happy paths. See `scripts/curmudgeon_review.sh` and `tests/test_curmudgeon_review.sh` for the reference.
4. Add the entry to `reviewer-registry.json`. Default `cascade_tier: 2` unless there's a specific reason otherwise.
5. Extend `tests/test_reviewer_registry.py` with an assertion that the new entry is registered + lands in the expected `by_tier` bucket.
6. Document in `phase-6-quality.md`'s Default Reviewers table.

## See also

- `reviewer-registry.json` (canonical config at repo root)
- `skills/claude-flow/scripts/select_reviewers.py` (runtime parser)
- `skills/claude-flow/phases/phase-6-quality.md` (dispatch behavior)
- `scripts/curmudgeon_review.sh` (CLI-backed reference implementation)
