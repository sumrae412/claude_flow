"""Tests for scripts/dispatch.py — task classification + ranked agent picks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dispatch import (  # noqa: E402
    AgentEntry,
    Registry,
    TaskShape,
    classify_task,
    dispatch,
)


# --- classify_task ---

@pytest.mark.parametrize("description, expected", [
    ("review this PR for security issues", TaskShape.REVIEW),
    ("audit the migration safety", TaskShape.REVIEW),
    ("fix the bug in the login flow", TaskShape.FIX),
    ("design the event bus trade-offs", TaskShape.ARCHITECT),
    ("where is the session handler defined", TaskShape.EXPLORE),
    ("grade these responses against the rubric", TaskShape.GRADE),
    ("hello world", TaskShape.UNKNOWN),
])
def test_classify_task_heuristics(description, expected):
    assert classify_task(description) == expected


def test_classify_is_case_insensitive():
    assert classify_task("REVIEW THIS CODE") == TaskShape.REVIEW


# --- Registry model ---

def test_registry_tolerates_extra_fields():
    # The real reviewer-registry.json carries fields like calibration,
    # persona_file, scored_criteria. AgentEntry must not reject them.
    raw = {
        "reviewers": [{
            "id": "adversarial-breaker",
            "description": "adversarial evaluator",
            "tier": "always",
            "cascade_tier": 2,
            "subagent_type": "general-purpose",
            "model": "sonnet",
            "calibration": {"min_agreement": 0.7},
            "scored_criteria": ["input_validation"],
            "persona_file": "some/path",
        }]
    }
    reg = Registry.model_validate(raw)
    assert len(reg.reviewers) == 1
    assert reg.reviewers[0].id == "adversarial-breaker"


def test_agent_entry_rejects_invalid_tier():
    with pytest.raises(Exception):  # pydantic ValidationError
        AgentEntry(id="x", tier="bogus")


# --- dispatch ---

def _mk_registry(*entries: dict) -> Registry:
    return Registry.model_validate({"reviewers": list(entries)})


def test_dispatch_file_pattern_match_ranks_migration_reviewer_for_migration_task():
    reg = _mk_registry(
        {"id": "migration-reviewer", "tier": "conditional", "cascade_tier": 3,
         "subagent_type": "migration-reviewer", "model": "sonnet",
         "description": "Alembic migration safety checks",
         "file_patterns": ["alembic/**/*.py", "**/migrations/**/*.py"]},
        {"id": "coderabbit", "tier": "always", "cascade_tier": 1,
         "subagent_type": "coderabbit:code-reviewer", "model": "sonnet",
         "description": "first-pass bugs and logic errors"},
    )
    result = dispatch(
        "review this migration for concurrent-write safety",
        file_paths=["alembic/versions/0042_add_column.py"],
        registry=reg,
    )
    assert result.shape == TaskShape.REVIEW
    assert len(result.picks) >= 2
    # Migration reviewer should win on file-pattern match.
    assert result.picks[0].agent_id == "migration-reviewer"
    assert "matched" in result.picks[0].rationale


def test_dispatch_excludes_reviewers_for_explore_shape():
    reg = _mk_registry(
        {"id": "coderabbit", "tier": "always", "cascade_tier": 1,
         "subagent_type": "coderabbit:code-reviewer", "model": "sonnet",
         "description": "first-pass bugs"},
    )
    result = dispatch("explore where the auth handler lives", registry=reg)
    assert result.shape == TaskShape.EXPLORE
    # Reviewers don't default into EXPLORE — picks should be empty.
    assert result.picks == []


def test_dispatch_respects_explicit_shape_hint():
    # An agent with an explicit `shape: explore` applies to EXPLORE tasks even
    # though it has no reviewer tier.
    reg = _mk_registry(
        {"id": "repo-explorer", "description": "search and map a codebase",
         "subagent_type": "feature-dev:code-explorer", "model": "sonnet",
         "shape": "explore"},
    )
    result = dispatch("explore the authentication module", registry=reg)
    assert result.shape == TaskShape.EXPLORE
    assert len(result.picks) == 1
    assert result.picks[0].agent_id == "repo-explorer"


def test_dispatch_ranks_by_description_overlap_when_no_file_match():
    reg = _mk_registry(
        {"id": "security-reviewer", "tier": "always", "cascade_tier": 2,
         "subagent_type": "security-reviewer", "model": "sonnet",
         "description": "Auth, data exposure, injection, OWASP"},
        {"id": "async-reviewer", "tier": "conditional", "cascade_tier": 3,
         "subagent_type": "async-reviewer", "model": "sonnet",
         "description": "Blocking calls and async anti-patterns",
         "file_patterns": ["**/*.py"], "content_pattern": "async def"},
    )
    result = dispatch("review this PR for injection vulnerabilities", registry=reg)
    assert result.picks[0].agent_id == "security-reviewer"


def test_dispatch_drops_zero_score_agents():
    reg = _mk_registry(
        {"id": "irrelevant", "tier": "conditional", "cascade_tier": 3,
         "subagent_type": "x", "model": "sonnet",
         "description": "totally unrelated topic xyzzy",
         "file_patterns": ["**/this-never-matches/**"]},
    )
    # No file paths, no description overlap → zero score → dropped.
    result = dispatch("review this PR", registry=reg)
    assert all(p.agent_id != "irrelevant" for p in result.picks)


def test_dispatch_always_tier_baseline_boost():
    # Always-tier reviewers get a small baseline so they appear even when
    # neither files nor description overlap. Avoids the "empty picks" trap
    # on generic review tasks.
    reg = _mk_registry(
        {"id": "coderabbit", "tier": "always", "cascade_tier": 1,
         "subagent_type": "coderabbit:code-reviewer", "model": "sonnet",
         "description": "broad first-pass sweep"},
    )
    result = dispatch("review the diff", registry=reg)
    assert len(result.picks) == 1
    assert result.picks[0].agent_id == "coderabbit"
    assert result.picks[0].confidence > 0


def test_dispatch_top_k_limits_results():
    entries = [
        {"id": f"r{i}", "tier": "always", "cascade_tier": 2,
         "subagent_type": f"r{i}", "model": "sonnet",
         "description": f"reviewer {i} with generic review scope"}
        for i in range(6)
    ]
    reg = _mk_registry(*entries)
    result = dispatch("review code", registry=reg, top_k=3)
    assert len(result.picks) == 3


# --- Auto-activation gate ---

def test_dispatch_not_recommended_with_single_candidate():
    """When the registry has only one shape-matching candidate, dispatch is
    not worthwhile — the caller should skip the supervisor and use the one
    available agent directly."""
    reg = _mk_registry(
        {"id": "only-one", "tier": "always", "cascade_tier": 1,
         "subagent_type": "only-one", "model": "sonnet",
         "description": "sole reviewer"},
    )
    result = dispatch("review the diff", registry=reg)
    assert result.shape_candidate_count == 1
    assert result.dispatch_recommended is False


def test_dispatch_recommended_with_two_or_more_candidates():
    reg = _mk_registry(
        {"id": "a", "tier": "always", "cascade_tier": 2,
         "subagent_type": "a", "model": "sonnet", "description": "reviewer A"},
        {"id": "b", "tier": "always", "cascade_tier": 2,
         "subagent_type": "b", "model": "sonnet", "description": "reviewer B"},
    )
    result = dispatch("review the diff", registry=reg)
    assert result.shape_candidate_count == 2
    assert result.dispatch_recommended is True


def test_dispatch_not_recommended_when_no_shape_match():
    """Reviewers don't apply to EXPLORE tasks → zero candidates → not
    recommended. Guards the caller against dispatching into an empty set."""
    reg = _mk_registry(
        {"id": "r", "tier": "always", "cascade_tier": 1,
         "subagent_type": "r", "model": "sonnet", "description": "reviewer"},
    )
    result = dispatch("explore the auth module", registry=reg)
    assert result.shape_candidate_count == 0
    assert result.dispatch_recommended is False


def test_dispatch_cli_require_multiple_exits_3_on_single(tmp_path):
    """CLI contract: --require-multiple yields exit code 3 when the registry
    has <2 candidates. Phase 2/4 can wire this in a shell conditional to
    skip dispatch entirely when there's nothing to choose among."""
    import subprocess

    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps({
        "reviewers": [{
            "id": "only-one", "tier": "always", "cascade_tier": 1,
            "subagent_type": "only-one", "model": "sonnet",
            "description": "sole reviewer",
        }]
    }))
    script = Path(__file__).resolve().parents[1] / "scripts" / "dispatch.py"
    proc = subprocess.run(
        [sys.executable, str(script),
         "--task", "review the diff",
         "--registry", str(reg_path),
         "--require-multiple"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 3, f"expected exit 3, got {proc.returncode}"
    out = json.loads(proc.stdout)
    assert out["dispatch_recommended"] is False


# --- Integration with the real reviewer-registry.json ---

def test_dispatch_against_real_registry_for_migration_file():
    """Sanity check: the shipped registry picks migration-reviewer for a
    migration task on an alembic file."""
    registry_path = Path(__file__).resolve().parents[1] / "reviewer-registry.json"
    assert registry_path.exists(), "reviewer-registry.json missing"
    result = dispatch(
        "audit this Alembic migration for concurrent-write safety",
        file_paths=["alembic/versions/0042_add_column.py"],
        registry_path=registry_path,
    )
    ids = [p.agent_id for p in result.picks]
    assert "migration-reviewer" in ids
    assert result.picks[0].agent_id == "migration-reviewer"


# --- CLI ---

def test_dispatch_cli_emits_json(tmp_path):
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps({
        "reviewers": [{
            "id": "coderabbit", "tier": "always", "cascade_tier": 1,
            "subagent_type": "coderabbit:code-reviewer", "model": "sonnet",
            "description": "broad first-pass sweep",
        }]
    }))
    script = Path(__file__).resolve().parents[1] / "scripts" / "dispatch.py"
    proc = subprocess.run(
        [sys.executable, str(script),
         "--task", "review the diff",
         "--registry", str(reg_path),
         "--top-k", "1"],
        check=True, capture_output=True, text=True,
    )
    out = json.loads(proc.stdout)
    assert out["shape"] == "review"
    assert out["picks"][0]["agent_id"] == "coderabbit"
