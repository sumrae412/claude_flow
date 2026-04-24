#!/usr/bin/env python3
"""Supervisor dispatcher — pick sub-agents by task shape, using native primitives.

The claude_flow CLAUDE.md forbids external orchestrators (LangGraph / CrewAI
et al). This module is the native-primitives alternative: a small, testable
function that reads `reviewer-registry.json` (or any superset registry),
classifies the caller's task, and returns ranked sub-agent picks with
rationale. The caller — claude-flow Phase 6, or a skill like `dispatcher` —
then fans out via the Agent tool.

Scope is deliberately small:

- No LLM call for the ranking (keep it deterministic + cheap).
- No registry schema change — works against the existing
  `reviewer-registry.json` shape; extra fields on agents are tolerated.
- Reviewer file-pattern matching delegates to the existing
  `select_reviewers.file_matches_patterns` when available; falls back to a
  stdlib re-implementation when invoked outside the claude-skills checkout.

Usage from Python:

    from dispatch import dispatch, classify_task

    picks = dispatch(
        task_description="review this migration for concurrent-write safety",
        file_paths=["alembic/versions/0042_add_column.py"],
        registry_path=Path("reviewer-registry.json"),
    )
    # picks.shape == "review"
    # picks.picks[0].agent_id == "migration-reviewer"

CLI:

    echo "files here" | python scripts/dispatch.py \\
        --task "review a schema migration for concurrent writes" \\
        --registry reviewer-registry.json
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------- Task shape classification ----------

class TaskShape(str, Enum):
    """Coarse task types the supervisor can dispatch for.

    Intentionally small — these are the buckets the existing claude-flow phase
    skills already dispatch into. Extend only when a new phase appears.
    """
    REVIEW = "review"
    EXPLORE = "explore"
    ARCHITECT = "architect"
    FIX = "fix"
    GRADE = "grade"
    UNKNOWN = "unknown"


# Keyword heuristics for task classification. Order matters — first match wins.
# Lowercase, substring match. This is deliberately dumb: a misclassification
# costs one wrong agent suggestion, not a silent failure.
_SHAPE_KEYWORDS: list[tuple[TaskShape, tuple[str, ...]]] = [
    (TaskShape.GRADE, ("grade", "judge", "score the", "rubric")),
    (TaskShape.FIX, ("fix ", "bug", "regression", "stack trace", "error in")),
    (TaskShape.REVIEW, ("review", "audit", "critique", "check this pr", "find issues")),
    (TaskShape.ARCHITECT, ("design", "architect", "plan", "trade-off", "tradeoff")),
    (TaskShape.EXPLORE, ("explore", "find", "locate", "where is", "how does")),
]


def classify_task(description: str) -> TaskShape:
    """Heuristic keyword-based task-shape classifier."""
    low = description.lower()
    for shape, kws in _SHAPE_KEYWORDS:
        if any(kw in low for kw in kws):
            return shape
    return TaskShape.UNKNOWN


# ---------- Registry models ----------

class AgentEntry(BaseModel):
    """One row of reviewer-registry.json.

    We model only the fields dispatch.py reads. Extra fields (calibration,
    persona_file, scored_criteria, ...) are tolerated via `model_config`.
    """
    model_config = {"extra": "allow"}

    id: str
    description: str = ""
    tier: str | None = None           # "always" | "conditional"
    cascade_tier: int | None = None
    subagent_type: str | None = None
    runner: str | None = None         # e.g. "codex-cli"
    model: str | None = None
    file_patterns: list[str] = Field(default_factory=list)
    content_pattern: str | None = None
    threshold: int | None = None
    # Optional first-class strength tag — falls back to description keywords.
    strengths: list[str] = Field(default_factory=list)
    shape: TaskShape | None = None    # optional hint; reviewers default to REVIEW

    @field_validator("tier")
    @classmethod
    def _valid_tier(cls, v: str | None) -> str | None:
        if v is None or v in {"always", "conditional"}:
            return v
        raise ValueError(f"tier must be 'always' or 'conditional', got {v!r}")


class Registry(BaseModel):
    """Loaded reviewer-registry.json. Extra top-level keys tolerated."""
    model_config = {"extra": "allow"}

    reviewers: list[AgentEntry] = Field(default_factory=list)


class DispatchPick(BaseModel):
    """One ranked candidate with rationale."""
    agent_id: str
    subagent_type: str | None
    model: str | None
    cascade_tier: int | None
    confidence: float  # 0.0 – 1.0
    rationale: str


class DispatchResult(BaseModel):
    """Supervisor output: ranked picks for a classified task.

    `dispatch_recommended` captures the honest answer to "is it worth running
    the supervisor here?" — it's True only when the registry offers ≥2
    shape-matching candidates. When False, the caller has a single (or zero)
    reasonable option and should skip the supervisor overhead.
    """
    task_description: str
    shape: TaskShape
    file_paths: list[str]
    picks: list[DispatchPick]
    shape_candidate_count: int = 0
    dispatch_recommended: bool = False


# ---------- Matching helpers ----------

def _file_matches_patterns(file_path: str, patterns: list[str]) -> bool:
    """Glob matching identical to the Phase 6 selector's convention.

    Covers bare patterns, `**/` prefixed patterns, and an implicit `**/`
    prefix for patterns that don't have one. Kept local so dispatch.py has
    no cross-repo import dependency.
    """
    for pat in patterns:
        if fnmatch.fnmatch(file_path, pat):
            return True
        if pat.startswith("**/") and fnmatch.fnmatch(file_path, pat[3:]):
            return True
        if not pat.startswith("**/") and fnmatch.fnmatch(file_path, f"**/{pat}"):
            return True
    return False


def _description_score(task_description: str, agent: AgentEntry) -> float:
    """Overlap score between task keywords and agent description/strengths.

    Tokenizes both sides on non-word chars, counts overlap, divides by the
    agent-side token count. Cheap and deterministic. Agents with empty
    descriptions score 0 from this signal alone (file-match still applies).
    """
    task_tokens = set(re.findall(r"\w+", task_description.lower()))
    agent_text = " ".join([agent.description, *agent.strengths]).lower()
    agent_tokens = set(re.findall(r"\w+", agent_text))
    if not agent_tokens:
        return 0.0
    # Ignore very common words that add noise.
    stopwords = {"the", "a", "an", "and", "or", "of", "for", "in", "to", "on", "is", "this"}
    task_tokens -= stopwords
    agent_tokens -= stopwords
    if not agent_tokens:
        return 0.0
    overlap = task_tokens & agent_tokens
    return len(overlap) / len(agent_tokens)


# ---------- Main dispatch logic ----------

def _agent_matches_shape(agent: AgentEntry, shape: TaskShape) -> bool:
    """Does this agent apply to a task of this shape?

    - Explicit `shape` field wins.
    - Reviewers (tier = always|conditional) default to REVIEW.
    - Anything else without a shape hint is UNKNOWN and always considered.
    """
    if agent.shape is not None:
        return agent.shape == shape or shape == TaskShape.UNKNOWN
    if agent.tier in {"always", "conditional"}:
        return shape in {TaskShape.REVIEW, TaskShape.UNKNOWN}
    return shape == TaskShape.UNKNOWN


def dispatch(
    task_description: str,
    file_paths: list[str] | None = None,
    *,
    registry_path: Path | None = None,
    registry: Registry | None = None,
    top_k: int = 5,
) -> DispatchResult:
    """Pick ranked sub-agents for a task.

    Ranking signal is a sum of:
      - 0.5  if any of the agent's `file_patterns` match any file_path
      - 0.5 * description-overlap score (0-1)
      - +0.1 for `always`-tier reviewers when shape is REVIEW (baseline boost)
      - +0.05 for agents with an explicit shape hint that matches the task
        (so an agent can surface on shape alone, even with a terse description)

    Agents that apply to the shape but score 0 are excluded from `picks`.
    """
    if registry is None:
        if registry_path is None:
            raise ValueError("dispatch() requires registry or registry_path")
        registry = Registry.model_validate_json(registry_path.read_text())
    files = file_paths or []

    shape = classify_task(task_description)

    ranked: list[DispatchPick] = []
    shape_candidates = 0
    for agent in registry.reviewers:
        if not _agent_matches_shape(agent, shape):
            continue
        shape_candidates += 1

        reasons: list[str] = []
        score = 0.0

        if files and agent.file_patterns:
            matched = [f for f in files if _file_matches_patterns(f, agent.file_patterns)]
            if matched:
                score += 0.5
                reasons.append(f"matched {len(matched)}/{len(files)} files by glob")

        desc_score = _description_score(task_description, agent)
        if desc_score > 0:
            score += 0.5 * desc_score
            reasons.append(f"description overlap={desc_score:.2f}")

        if shape == TaskShape.REVIEW and agent.tier == "always":
            score += 0.1
            reasons.append("always-tier reviewer baseline")

        if agent.shape is not None and agent.shape == shape:
            score += 0.05
            reasons.append(f"explicit shape hint={shape.value}")

        if score <= 0.0:
            continue

        ranked.append(DispatchPick(
            agent_id=agent.id,
            subagent_type=agent.subagent_type,
            model=agent.model,
            cascade_tier=agent.cascade_tier,
            confidence=round(min(score, 1.0), 3),
            rationale="; ".join(reasons) or "no signal",
        ))

    ranked.sort(key=lambda p: p.confidence, reverse=True)
    return DispatchResult(
        task_description=task_description,
        shape=shape,
        file_paths=files,
        picks=ranked[:top_k],
        shape_candidate_count=shape_candidates,
        dispatch_recommended=shape_candidates >= 2,
    )


# ---------- CLI ----------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True,
                        help="Natural-language task description.")
    parser.add_argument("--registry", type=Path, default=Path("reviewer-registry.json"),
                        help="Path to registry JSON.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--files-from-stdin", action="store_true",
                        help="Read file paths (one per line) from stdin.")
    parser.add_argument("--require-multiple", action="store_true",
                        help="Exit code 3 if dispatch isn't worthwhile "
                             "(registry has <2 candidates for this shape). "
                             "Lets callers skip the supervisor when there's "
                             "only one reasonable option.")
    parser.add_argument("file_paths", nargs="*")
    args = parser.parse_args()

    files: list[str] = list(args.file_paths)
    if args.files_from_stdin:
        files.extend(p.strip() for p in sys.stdin if p.strip())

    result = dispatch(
        args.task,
        file_paths=files or None,
        registry_path=args.registry,
        top_k=args.top_k,
    )
    json.dump(result.model_dump(mode="json"), sys.stdout, indent=2)
    sys.stdout.write("\n")

    if args.require_multiple and not result.dispatch_recommended:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
