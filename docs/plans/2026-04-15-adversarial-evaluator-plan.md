# Adversarial Evaluator Reviewer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `adversarial-breaker` reviewer to claude-flow's Phase 6 that evaluates diffs with an explicit "break it" framing and per-criterion 1-10 scoring, with sub-threshold scores feeding back into the Phase 5 retry ladder as blocking findings.

**Architecture:** New agent-backed reviewer wired via `reviewer-registry.json` (tier=`always`, cascade_tier=2). Reviewer prompt lives in a persona-file-on-disk (`scripts/adversarial_breaker_persona.txt`) per the `persona_file_stdin_pattern.md` convention. Output is a structured `{"scores":[{criterion, score, break_case}], "findings":[...]}` envelope. Registry declares `score_threshold: 7`; Phase 6 aggregator converts any score below threshold into a blocking finding, which feeds into Phase 5 retry input alongside test failures. No new orchestration infra — composes with existing retry ladder and reviewer cascade.

**Tech Stack:** Markdown (phase prompts), JSON (registry schema), plain text (persona file), Bash (optional test-fixture script).

**Source:** Pattern imported from coleam00/Archon — specifically `.archon/workflows/defaults/archon-adversarial-dev.yaml` (Generator/Evaluator GAN-style loop with 7/10 thresholds). Reframed as a Phase 6 reviewer rather than a replacement orchestrator per `compose_dont_replace.md`.

**Ruled Out:**
- **Full Generator/Evaluator state-machine workflow mode** (Archon's native shape) — duplicates Phase 5 retry + Phase 4 quality gate; violates `compose_dont_replace.md`. The adversarial framing is the valuable part; the sprint-state-machine wrapper is not.
- **Mid-Phase-5 adversarial injection between iter-N and iter-(N+1)** — more invasive than needed; Phase 6 already runs post-diff and its blockers already feed Phase 5 retries. Reuse that loop instead of adding a new one.
- **CLI-backed reviewer (like curmudgeon-review)** — persona framing is the value, not cross-model dissent; no reason to add a new external CLI dependency. Agent-backed (Sonnet subagent) is sufficient.
- **Binary pass/fail** — loses the graduated signal that makes the pattern interesting. 1-10 scores enable differentiated response (5-6 → iter-2 fix; 1-4 → iter-3 cross-model escalation).

---

## Files Touched (entire feature)

Cache (runtime) + repo (git) per the "Dual-location skills" gotcha in CLAUDE.md:

- Create: `~/.claude/skills/claude-flow/scripts/adversarial_breaker_persona.txt` (+ sync to repo)
- Modify: `~/.claude/plugins/cache/.../reviewer-registry.json` (+ sync to repo `/Users/summerrae/claude_code/claude_flow/reviewer-registry.json`)
- Modify: `~/.claude/skills/claude-flow/phases/phase-6-quality.md` (+ sync to repo)
- Modify: `~/.claude/skills/claude-flow/phases/phase-5-implementation.md` (+ sync to repo)
- Modify: `~/.claude/skills/claude-flow/references/reviewer-registry-schema.md` (+ sync to repo)
- Create: `/Users/summerrae/claude_code/claude_flow/tests/fixtures/adversarial_breaker/buggy_diff.patch` — golden fixture
- Create: `/Users/summerrae/claude_code/claude_flow/tests/test_adversarial_breaker.py` — schema + aggregator unit tests

**Coordination note:** `reviewer-registry.json` has uncommitted edits on `main` as of plan draft time (2026-04-15). Rebase on those edits before starting T2 to avoid merge conflicts.

---

## Task 1: Persona file + registry schema docs
**Type:** shared_prerequisite
**Depends on:** none

**Files:**
- Create: `~/.claude/skills/claude-flow/scripts/adversarial_breaker_persona.txt`
- Modify: `~/.claude/skills/claude-flow/references/reviewer-registry-schema.md`
- Verify: repo copies via `diff` after sync

**Step 1: Write the persona file**

Create `adversarial_breaker_persona.txt` with this content:

```text
You are an ADVERSARIAL EVALUATOR. Your job is NOT to find bugs — other reviewers already do that.
Your job is to BREAK the code. Assume the author was confident. Assume the tests pass. Now ask:
"What input, timing, or environment would make this fail in production?"

For each criterion below, produce:
  - score (integer 1-10): 10 = unbreakable, 7 = good enough to ship, 4 = likely breaks under load, 1 = breaks trivially
  - break_case (string, max 200 chars): the EXACT concrete scenario that would trigger the failure,
                                        with the specific input/sequence/condition. No generic advice.

Criteria (score all six):
  1. input_validation       — malformed/hostile/edge-case inputs
  2. error_handling         — exceptions, network failures, partial writes
  3. concurrency_safety     — races, double-submits, stale reads, deadlocks
  4. data_consistency       — invariants, transactional boundaries, sync gaps
  5. failure_modes          — what happens when a dependency is down/slow/wrong
  6. test_coverage_gaps     — paths the tests LOOK like they cover but actually don't

Also emit standard findings[] for specific bugs you uncover (file:line + fix suggestion),
same shape as other reviewers.

Output STRICT JSON:
{
  "reviewer": "adversarial-breaker",
  "scores": [{"criterion": "...", "score": N, "break_case": "..."}, ...],
  "findings": [{"severity": "...", "file": "...", "line": N, "message": "...", "fix": "..."}, ...]
}

No prose outside the JSON. No markdown. No preamble.
```

**Step 2: Extend schema docs**

In `reviewer-registry-schema.md`, add a section documenting the new optional fields:

```markdown
## Scored Reviewers (v1.1+)

Reviewers that emit per-criterion numeric scores set:

- `score_threshold` (integer 1-10): scores strictly below this become blocking findings
- `scored_criteria` (array of strings): canonical criterion names the reviewer scores

The Phase 6 aggregator (phase-6-quality.md) reads these fields, iterates the reviewer's
`scores[]` output, and synthesizes one blocking finding per sub-threshold score in the form:
`Adversarial score {N}/10 on {criterion}: {break_case}`.

Sub-threshold findings flow into Phase 5 retry input same as test failures.
```

**Step 3: Verify and sync to repo**

```bash
cat ~/.claude/skills/claude-flow/scripts/adversarial_breaker_persona.txt | wc -l
# Expected: ~35 lines

cp ~/.claude/skills/claude-flow/scripts/adversarial_breaker_persona.txt \
   /Users/summerrae/claude_code/claude_flow/skills/claude-flow/scripts/adversarial_breaker_persona.txt
cp ~/.claude/skills/claude-flow/references/reviewer-registry-schema.md \
   /Users/summerrae/claude_code/claude_flow/skills/claude-flow/references/reviewer-registry-schema.md

diff ~/.claude/skills/claude-flow/scripts/adversarial_breaker_persona.txt \
     /Users/summerrae/claude_code/claude_flow/skills/claude-flow/scripts/adversarial_breaker_persona.txt
# Expected: no output (files identical)
```

**Step 4: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add skills/claude-flow/scripts/adversarial_breaker_persona.txt \
        skills/claude-flow/references/reviewer-registry-schema.md
git commit -m "feat(adversarial): add breaker persona + scored-reviewer schema"
```

---

## Task 2: Registry entry + schema unit test
**Type:** value_unit
**Depends on:** T1 (data — uses schema from T1)

**Files:**
- Modify: `~/.claude/plugins/cache/.../reviewer-registry.json` (find exact cache path with `find ~/.claude/plugins/cache -name reviewer-registry.json`)
- Modify: `/Users/summerrae/claude_code/claude_flow/reviewer-registry.json`
- Create: `/Users/summerrae/claude_code/claude_flow/tests/test_adversarial_breaker.py`

**Step 1: Write the failing test**

```python
# tests/test_adversarial_breaker.py
import json
from pathlib import Path

REGISTRY = Path(__file__).parent.parent / "reviewer-registry.json"

def test_adversarial_breaker_registered():
    data = json.loads(REGISTRY.read_text())
    reviewers = {r["id"]: r for r in data["reviewers"]}
    assert "adversarial-breaker" in reviewers
    r = reviewers["adversarial-breaker"]
    assert r["tier"] == "always"
    assert r["cascade_tier"] == 2
    assert r["score_threshold"] == 7
    assert set(r["scored_criteria"]) == {
        "input_validation", "error_handling", "concurrency_safety",
        "data_consistency", "failure_modes", "test_coverage_gaps",
    }
    # Agent-backed (not CLI-backed)
    assert "subagent_type" in r
    assert "runner" not in r
```

**Step 2: Run it to verify it fails**

```bash
cd /Users/summerrae/claude_code/claude_flow
pytest tests/test_adversarial_breaker.py::test_adversarial_breaker_registered -v
```
Expected: FAIL — `"adversarial-breaker" in reviewers` is False.

**Step 3: Add the registry entry**

Add this block to `reviewer-registry.json` inside the `reviewers[]` array (placement: after `curmudgeon-review`, before the first `conditional` reviewer):

```json
{
  "id": "adversarial-breaker",
  "tier": "always",
  "cascade_tier": 2,
  "subagent_type": "general-purpose",
  "model": "sonnet",
  "description": "Adversarial evaluator — scores diff 1-10 on 6 break-criteria. Sub-threshold scores become blocking findings that feed Phase 5 retries.",
  "persona_file": "skills/claude-flow/scripts/adversarial_breaker_persona.txt",
  "score_threshold": 7,
  "scored_criteria": [
    "input_validation",
    "error_handling",
    "concurrency_safety",
    "data_consistency",
    "failure_modes",
    "test_coverage_gaps"
  ],
  "calibration": {
    "verdict_type": "scored",
    "min_agreement": 0.7,
    "sample_size": 20,
    "last_calibrated": null,
    "last_agreement": null,
    "note": "Scored reviewer — agreement = (|judge_score - human_score| <= 2) / n"
  }
}
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_adversarial_breaker.py::test_adversarial_breaker_registered -v
```
Expected: PASS.

**Step 5: Sync cache + commit**

```bash
CACHE=$(find ~/.claude/plugins/cache -name reviewer-registry.json | head -1)
cp /Users/summerrae/claude_code/claude_flow/reviewer-registry.json "$CACHE"
diff /Users/summerrae/claude_code/claude_flow/reviewer-registry.json "$CACHE"
# Expected: no output

cd /Users/summerrae/claude_code/claude_flow
git add reviewer-registry.json tests/test_adversarial_breaker.py
git commit -m "feat(adversarial): register breaker reviewer in registry"
```

---

## Task 3: Phase 6 aggregator — score → findings conversion
**Type:** value_unit
**Depends on:** T2 (data — reads registry fields added in T2)

**Files:**
- Modify: `~/.claude/skills/claude-flow/phases/phase-6-quality.md`
- Modify: `/Users/summerrae/claude_code/claude_flow/tests/test_adversarial_breaker.py` (add aggregator test)

**Step 1: Write the failing test**

Append to `tests/test_adversarial_breaker.py`:

```python
def test_subthreshold_scores_become_blocking_findings():
    """Aggregator logic: for a reviewer with score_threshold=7,
    any score < 7 should produce one blocking finding with the break_case."""
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings

    reviewer_output = {
        "reviewer": "adversarial-breaker",
        "scores": [
            {"criterion": "input_validation", "score": 9, "break_case": "N/A"},
            {"criterion": "concurrency_safety", "score": 3,
             "break_case": "Two concurrent POSTs to /api/book race on slot lock"},
        ],
        "findings": [],
    }
    registry_entry = {"score_threshold": 7}

    result = convert_scores_to_findings(reviewer_output, registry_entry)
    assert len(result["findings"]) == 1
    f = result["findings"][0]
    assert f["severity"] == "blocking"
    assert "concurrency_safety" in f["message"]
    assert "3/10" in f["message"]
    assert "Two concurrent POSTs" in f["message"]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_adversarial_breaker.py::test_subthreshold_scores_become_blocking_findings -v
```
Expected: FAIL — `scripts.aggregate_reviewer_findings` module not found.

**Step 3: Create the aggregator helper**

Create `/Users/summerrae/claude_code/claude_flow/scripts/aggregate_reviewer_findings.py`:

```python
"""Convert scored-reviewer output into standard blocking findings.

Phase 6 runs this after each scored reviewer completes. Registry entries
with score_threshold trigger the conversion; plain binary reviewers skip it.
"""

def convert_scores_to_findings(reviewer_output: dict, registry_entry: dict) -> dict:
    threshold = registry_entry.get("score_threshold")
    if threshold is None:
        return reviewer_output  # not a scored reviewer

    findings = list(reviewer_output.get("findings", []))
    for score_entry in reviewer_output.get("scores", []):
        if score_entry["score"] < threshold:
            findings.append({
                "severity": "blocking",
                "file": "<adversarial>",
                "line": 0,
                "message": (
                    f"Adversarial score {score_entry['score']}/10 "
                    f"on {score_entry['criterion']}: {score_entry['break_case']}"
                ),
                "fix": "Address the break case above; target score >= {}".format(threshold),
            })
    return {**reviewer_output, "findings": findings}
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_adversarial_breaker.py -v
```
Expected: 2 passed.

**Step 5: Update phase-6-quality.md**

Find the Phase 6 aggregation section (where reviewer outputs are combined). Add this instruction block:

```markdown
### Scored-Reviewer Aggregation

After each reviewer completes, if its registry entry has `score_threshold`, run:

    python scripts/aggregate_reviewer_findings.py --reviewer <output.json> --registry reviewer-registry.json

The script converts every sub-threshold score into a blocking finding of the form
`Adversarial score {N}/10 on {criterion}: {break_case}`. Aggregated findings join
the main findings[] pool and flow to Phase 5 retries on any blocking verdict.
```

**Step 6: Sync + commit**

```bash
cp ~/.claude/skills/claude-flow/phases/phase-6-quality.md \
   /Users/summerrae/claude_code/claude_flow/skills/claude-flow/phases/phase-6-quality.md
cd /Users/summerrae/claude_code/claude_flow
git add skills/claude-flow/phases/phase-6-quality.md \
        scripts/aggregate_reviewer_findings.py \
        tests/test_adversarial_breaker.py
git commit -m "feat(adversarial): score→finding aggregator for Phase 6"
```

---

## Task 4: Phase 5 retry input — include adversarial blockers
**Type:** value_unit
**Depends on:** T3 (data — consumes findings shape from T3)

**Files:**
- Modify: `~/.claude/skills/claude-flow/phases/phase-5-implementation.md`

**Step 1: Read current retry ladder**

```bash
grep -A 20 "retry ladder" ~/.claude/skills/claude-flow/phases/phase-5-implementation.md
```
Expected: state-transition block citing iter 1/2/3.

**Step 2: Add adversarial-blocker input to retry ladder**

In the retry-ladder section (around the `**State transition:**` block), add a bullet:

```markdown
**Retry inputs (iter N+1 receives all applicable):**
- Test failures from iter N (pytest output, failing assertions)
- Lint failures from iter N (ruff/eslint output)
- **Adversarial blockers from Phase 6** (sub-threshold scored findings) — formatted as
  `{criterion}: {break_case}` entries in the iter-N+1 prompt under a "Break cases to address" section
- Explain-before-fix analysis from iter-1 (if transitioning to iter-2)
```

**Step 3: Add corresponding instruction to the iter-N+1 prompt template**

In the prompt template section, add:

```markdown
## Break Cases to Address (from adversarial evaluator)

If present, the following break cases were scored below 7/10 in the prior iteration:

{adversarial_blockers}

Address each break case in this iteration. A break case is a SPECIFIC concrete scenario —
reproduce it mentally, then patch the code so it no longer breaks.
```

**Step 4: Sync + commit**

```bash
cp ~/.claude/skills/claude-flow/phases/phase-5-implementation.md \
   /Users/summerrae/claude_code/claude_flow/skills/claude-flow/phases/phase-5-implementation.md
cd /Users/summerrae/claude_code/claude_flow
git add skills/claude-flow/phases/phase-5-implementation.md
git commit -m "feat(adversarial): wire Phase 5 retry input to adversarial blockers"
```

---

## Task 5: Golden-fixture integration test
**Type:** value_unit
**Depends on:** T1–T4 (data)

**Files:**
- Create: `/Users/summerrae/claude_code/claude_flow/tests/fixtures/adversarial_breaker/buggy_diff.patch`
- Create: `/Users/summerrae/claude_code/claude_flow/tests/fixtures/adversarial_breaker/expected_scores.json`
- Modify: `/Users/summerrae/claude_code/claude_flow/tests/test_adversarial_breaker.py`

**Step 1: Create the known-buggy fixture**

`buggy_diff.patch` — a small diff with a clear concurrency bug (e.g., TOCTOU on a file lock or a read-modify-write without transaction). Keep it under 30 lines so the test is fast and deterministic.

**Step 2: Create expected-scores anchor**

`expected_scores.json` — minimum bounds the adversarial reviewer should hit for this fixture:

```json
{
  "must_score_below_threshold": ["concurrency_safety"],
  "must_find_break_case_mentioning": ["race", "lock", "concurrent"]
}
```

(Bounds — not exact match — because LLM output varies. The test asserts the reviewer *identifies* the planted bug, not that it produces a specific score.)

**Step 3: Write the failing test**

```python
def test_breaker_catches_planted_concurrency_bug():
    """Golden fixture: the reviewer must score concurrency_safety below threshold
    on a diff with a known race condition, and mention the triggering concept."""
    import json, subprocess
    from pathlib import Path

    fixture_dir = Path(__file__).parent / "fixtures/adversarial_breaker"
    diff = (fixture_dir / "buggy_diff.patch").read_text()
    expected = json.loads((fixture_dir / "expected_scores.json").read_text())

    # Dispatch the reviewer (mock for CI; real run for manual verification).
    # In CI, use a pre-recorded response fixture to avoid LLM flakiness:
    recorded = fixture_dir / "recorded_response.json"
    if recorded.exists():
        result = json.loads(recorded.read_text())
    else:
        result = _dispatch_reviewer(diff)  # helper invokes Task tool

    below = {s["criterion"] for s in result["scores"] if s["score"] < 7}
    for c in expected["must_score_below_threshold"]:
        assert c in below, f"reviewer missed {c} break case"

    all_text = " ".join(s["break_case"].lower() for s in result["scores"])
    for keyword in expected["must_find_break_case_mentioning"]:
        assert keyword in all_text, f"no break_case mentions '{keyword}'"
```

**Step 4: Record an LLM response for CI stability**

Run the reviewer manually once against the fixture; save the output to `recorded_response.json`. This makes the test deterministic in CI while still verifying the contract.

**Step 5: Run test to verify it passes**

```bash
pytest tests/test_adversarial_breaker.py -v
```
Expected: 3 passed.

**Step 6: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add tests/fixtures/adversarial_breaker/ tests/test_adversarial_breaker.py
git commit -m "test(adversarial): golden fixture — race-condition detection"
```

---

## Post-Implementation: Update MEMORY + CLAUDE.md

**Optional final commit (after tasks 1-5 pass and the pattern is proven on one real PR):**

- Create `~/.claude/projects/-Users-summerrae-claude-flow/memory/adversarial_breaker_reviewer.md` — component memory entry linking the pattern to `compose_dont_replace.md`, `graceful_skip_envelope.md`, and the Archon source.
- Add one-liner to `MEMORY.md` index.
- (No CLAUDE.md change needed — the reviewer is auto-registered via `reviewer-registry.json`, no user-facing surface.)

---

## Verification Commands

After all tasks complete:

```bash
cd /Users/summerrae/claude_code/claude_flow

# Tests
pytest tests/test_adversarial_breaker.py -v
# Expected: 3 passed

# Registry parses + includes new entry
python -c "import json; d = json.load(open('reviewer-registry.json')); \
  r = [x for x in d['reviewers'] if x['id']=='adversarial-breaker'][0]; \
  print('OK', r['score_threshold'], len(r['scored_criteria']))"
# Expected: OK 7 6

# Lint
ruff check scripts/aggregate_reviewer_findings.py tests/test_adversarial_breaker.py
# Expected: All checks passed
```

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-04-15-adversarial-evaluator-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Parallel Session (separate)** — Open a new session in a worktree with `superpowers:executing-plans`, batch execution with checkpoints.

Recommend **option 2** given uncommitted edits on `main` — worktree isolation avoids clashing with the in-flight changes to `reviewer-registry.json` and `phase-5-implementation.md`. Rebase the worktree on those commits once they land.

Which approach?
