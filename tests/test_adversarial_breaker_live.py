"""Live adversarial-breaker test — opt-in, dispatches the real LLM.

Skipped by default. Set `RUN_LIVE_LLM=1` to enable. Requires
ANTHROPIC_API_KEY in the environment and the `anthropic` package installed.

What this validates that the replay test in test_adversarial_breaker.py does NOT:
- The persona file actually elicits the contracted JSON shape from the model.
- The model with this persona catches the planted concurrency bug.
- Score scale + criterion names match what the registry expects.

When this test runs successfully, it overwrites
`tests/fixtures/adversarial_breaker/recorded_response.json` with the live
response. The replay test then asserts against a real-LLM-authored fixture
on subsequent runs in CI.

Limitation: this calls the Anthropic API directly. The Phase 6 production
path dispatches via the Task tool with `subagent_type=general-purpose`,
which routes through Claude Code's internal subagent runner. Behavior
should be substantially the same (same model + same system prompt + same
user message), but a future hardening pass could replace this with a
shell-out to the real dispatcher once it lives in importable code.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

LIVE = os.environ.get("RUN_LIVE_LLM") == "1"
SKIP_REASON = "set RUN_LIVE_LLM=1 to dispatch real LLM (requires ANTHROPIC_API_KEY)"
MODEL = os.environ.get("ADVERSARIAL_BREAKER_MODEL", "claude-sonnet-4-5-20250929")

REPO_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = Path(__file__).parent / "fixtures/adversarial_breaker"

# Persona file lives in the claude-skills repo (post-aed5f39 single-source-of-truth
# refactor). Resolve via the ~/.claude/skills symlink so the test works on any
# dev machine where claude-skills is installed at the canonical location.
# The registry entry's persona_file + persona_file_root mirror this resolution.
PERSONA = (
    Path.home() / ".claude/skills/claude-flow/scripts/adversarial_breaker_persona.txt"
)


def _extract_json(text: str) -> str:
    """The persona instructs 'no prose outside JSON', but be defensive about
    the rare case where the model wraps the response in markdown fences."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    # Otherwise, take the largest top-level brace span.
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first : last + 1]
    return text


def _dispatch_via_anthropic_api(persona: str, diff: str) -> dict:
    """Direct API call. Approximates Phase 6 dispatch (same model + same
    system prompt). See module docstring for the limitation."""
    from anthropic import Anthropic  # imported lazily so the module loads in CI even without the SDK

    client = Anthropic()  # uses ANTHROPIC_API_KEY
    user_msg = (
        "Review the following unified diff against the criteria in your "
        "instructions. Emit only the JSON envelope, nothing else.\n\n"
        f"```diff\n{diff}\n```"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=persona,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text
    return json.loads(_extract_json(raw))


@pytest.mark.skipif(not LIVE, reason=SKIP_REASON)
def test_breaker_live_catches_planted_concurrency_bug():
    """Run the real reviewer against the planted-bug fixture, validate the
    contract bounds, and refresh recorded_response.json with the response."""
    assert PERSONA.exists(), f"persona file missing: {PERSONA}"
    diff = (FIXTURE_DIR / "buggy_diff.patch").read_text()
    expected = json.loads((FIXTURE_DIR / "expected_scores.json").read_text())
    persona = PERSONA.read_text()

    result = _dispatch_via_anthropic_api(persona, diff)

    # Contract: shape
    assert result.get("reviewer") == "adversarial-breaker", result
    assert isinstance(result.get("scores"), list), result
    assert len(result["scores"]) == 6, "expected all 6 scored criteria"
    expected_criteria = {
        "input_validation",
        "error_handling",
        "concurrency_safety",
        "data_consistency",
        "failure_modes",
        "test_coverage_gaps",
    }
    actual_criteria = {s["criterion"] for s in result["scores"]}
    assert actual_criteria == expected_criteria, (
        f"criterion drift — registry vs response: "
        f"missing={expected_criteria - actual_criteria}, "
        f"extra={actual_criteria - expected_criteria}"
    )
    for s in result["scores"]:
        assert isinstance(s["score"], int), f"non-int score: {s}"
        assert 1 <= s["score"] <= 10, f"score out of 1-10 range: {s}"

    # Contract: capability
    below = {s["criterion"] for s in result["scores"] if s["score"] < 7}
    for c in expected["must_score_below_threshold"]:
        assert c in below, f"reviewer missed {c} break case (scored {[s for s in result['scores'] if s['criterion']==c]})"

    all_text = " ".join(s["break_case"].lower() for s in result["scores"])
    synonyms = expected["must_find_break_case_mentioning_any_of"]
    assert any(kw in all_text for kw in synonyms), (
        f"no break_case mentions any of {synonyms}; full text: {all_text!r}"
    )

    # Refresh the cached recording so future replays match real behavior.
    # _meta carries provenance the replay test ignores but humans care about.
    result["_meta"] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": MODEL,
        "persona_path": "claude-flow/scripts/adversarial_breaker_persona.txt",
        "source": "test_adversarial_breaker_live.py",
    }
    (FIXTURE_DIR / "recorded_response.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
