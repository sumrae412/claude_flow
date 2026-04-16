"""Reviewer registry schema + early-exit placement checks.

Phase 6's early-exit (phase-6-quality.md §5-Tier Cascading Review, step 4)
skips Tiers 2-4 when Tier 1 returns no HIGH+ findings. Any reviewer whose
cost should be avoided on clean diffs must therefore sit at Tier ≥ 2.
"""
import importlib.util
import json
import pathlib
import sys


def _claude_skills_root():
    """Locate the claude-skills checkout — sibling dir preferred, runtime symlink fallback."""
    for candidate in (
        pathlib.Path("../claude-skills"),
        pathlib.Path.home() / ".claude/skills",
    ):
        if (candidate / "claude-flow/scripts/select_reviewers.py").exists():
            return candidate
    raise RuntimeError(
        "claude-skills not found; clone it at ../claude-skills or run claude_flow/install.sh"
    )


def _load_selector():
    """Import select_reviewers.py as a module without needing an __init__.py."""
    selector_path = _claude_skills_root() / "claude-flow/scripts/select_reviewers.py"
    spec = importlib.util.spec_from_file_location("select_reviewers", selector_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["select_reviewers"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_curmudgeon_registered():
    r = json.loads(pathlib.Path("reviewer-registry.json").read_text())
    ids = {x["id"] for x in r["reviewers"]}
    assert "curmudgeon-review" in ids, "curmudgeon entry missing"
    curm = next(x for x in r["reviewers"] if x["id"] == "curmudgeon-review")
    assert curm["tier"] == "always"
    assert curm["cascade_tier"] == 2
    assert curm.get("runner") == "codex-cli"


def test_curmudgeon_lands_in_tier_2_bucket(tmp_path):
    """Selector's by_tier output must place curmudgeon in Tier 2, not Tier 1.

    The orchestrator's early-exit (skip Tiers 2-4 on clean Tier 1) excludes
    reviewers by their cascade_tier bucket, not by name. So the behavioral
    guarantee lives in the selector output: curmudgeon must be in by_tier['2'].
    """
    selector = _load_selector()
    registry = json.loads(pathlib.Path("reviewer-registry.json").read_text())
    # Empty file list — exercises the "always" tier only, which is what
    # matters for curmudgeon (registered as always).
    result = selector.select(registry, file_paths=[], diff_dir=tmp_path)

    assert "2" in result["by_tier"], "no Tier 2 bucket in selector output"
    assert "curmudgeon-review" in result["by_tier"]["2"], (
        "curmudgeon must be in Tier 2 bucket so early-exit skips it on clean diffs"
    )
    assert "curmudgeon-review" not in result["by_tier"].get("1", []), (
        "curmudgeon must NOT be in Tier 1 — that bucket is reserved for the "
        "broad first-pass sweep that enables early-exit"
    )


def test_all_always_reviewers_have_cascade_tier():
    """Guard against future registry entries that omit cascade_tier and land
    in an un-early-exit-able '?' bucket."""
    r = json.loads(pathlib.Path("reviewer-registry.json").read_text())
    for reviewer in r["reviewers"]:
        if reviewer.get("tier") == "always":
            assert "cascade_tier" in reviewer, (
                f"reviewer {reviewer['id']} is 'always' tier but has no "
                f"cascade_tier — will land in '?' bucket and defeat early-exit"
            )
            assert isinstance(reviewer["cascade_tier"], int), (
                f"reviewer {reviewer['id']} cascade_tier must be int, got "
                f"{type(reviewer['cascade_tier']).__name__}"
            )
