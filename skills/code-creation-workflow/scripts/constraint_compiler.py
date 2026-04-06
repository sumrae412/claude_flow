"""constraint_compiler.py — Extract and compile constraint sets.

Reads markdown files, architecture decisions, and build-state dicts.
Produces Constraint objects (hard = deterministic check, soft = LLM judgment).
Stdlib only.
"""

import json
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any


# -- Constraint dataclass -----------------------------------------------------

@dataclass
class Constraint:
    id: str
    type: str                     # "hard" | "soft"
    check: str | None = None      # "grep" | "regex" | "ast-grep" (hard only)
    pattern: str | None = None    # grep/regex pattern (hard only)
    rule: str | None = None       # natural-language rule (soft; optional on hard)
    scope: str | None = None      # glob scope (hard only)
    message: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            "id": self.id, "type": self.type, "check": self.check,
            "pattern": self.pattern, "rule": self.rule, "scope": self.scope,
            "message": self.message, "source": self.source,
        }.items() if v is not None}


# -- Serialization ------------------------------------------------------------

def to_json(constraints: list[Constraint]) -> str:
    return json.dumps({"constraints": [c.to_dict() for c in constraints]}, indent=2)


def from_json(data: str) -> list[Constraint]:
    return [
        Constraint(
            id=d["id"], type=d["type"],
            check=d.get("check"), pattern=d.get("pattern"),
            rule=d.get("rule"), scope=d.get("scope"),
            message=d.get("message"), source=d.get("source"),
        )
        for d in json.loads(data).get("constraints", [])
    ]


# -- Rule extraction helpers --------------------------------------------------

_IMPERATIVE_RE = re.compile(
    r"\b(must|always|never|do not|don't|required|shall|should not|ensure)\b",
    re.IGNORECASE,
)


def _is_imperative(line: str) -> bool:
    return bool(_IMPERATIVE_RE.search(line))


def _classify_line(line: str) -> tuple[str, str | None]:
    """Return ('hard'|'soft', grep_pattern|None)."""
    btick = re.search(r"`([^`]+)`", line)
    decorator = re.search(r"(@\w+)", line)
    bare_except = re.search(r"bare\s+except|except\s+Exception", line, re.IGNORECASE)
    if btick:
        return "hard", btick.group(1)
    if decorator:
        return "hard", decorator.group(1)
    if bare_except:
        return "hard", "except Exception"
    return "soft", None


def _make_id() -> str:
    return f"c-{uuid.uuid4().hex[:8]}"


def _line_to_constraint(line: str, source: str) -> Constraint | None:
    line = line.strip().lstrip("-• ").strip()
    if not _is_imperative(line):
        return None
    ctype, pattern = _classify_line(line)
    if ctype == "hard":
        return Constraint(id=_make_id(), type="hard", check="grep",
                          pattern=pattern, rule=line, scope="**/*.py",
                          message=line, source=source)
    return Constraint(id=_make_id(), type="soft", rule=line, source=source)


# -- Public API ---------------------------------------------------------------

def compile_from_file(filepath: str, source_name: str) -> list[Constraint]:
    """Extract constraints from a markdown file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Not found: {filepath}")
    return [c for c in (
        _line_to_constraint(line, source_name)
        for line in open(filepath, encoding="utf-8").read().splitlines()
    ) if c]


def compile_from_architecture(architecture_text: str) -> list[Constraint]:
    """Extract design rules from Phase 4 architecture decision text."""
    if not architecture_text or not architecture_text.strip():
        return []
    return [c for c in (
        _line_to_constraint(line, "architecture-decision")
        for line in architecture_text.splitlines()
    ) if c]


def compile_from_build_state(build_state: dict) -> list[Constraint]:
    """Extract consistency constraints from build-state decisions and failed approaches."""
    results = []
    for step in build_state.get("steps", {}).values():
        for d in step.get("decisions_made", []):
            results.append(Constraint(id=_make_id(), type="soft", rule=d, source="build-state"))
        for f in step.get("failed_approaches", []):
            results.append(Constraint(id=_make_id(), type="soft",
                                      rule=f"AVOID: {f}", source="build-state"))
    return results


def merge_constraint_sets(sets: list[list[Constraint]]) -> list[Constraint]:
    """Deduplicate by rule/pattern content; prefer hard over soft on ties."""
    seen: dict[str, Constraint] = {}
    for lst in sets:
        for c in lst:
            key = (c.pattern or c.rule or "").strip().lower()
            if not key:
                continue
            existing = seen.get(key)
            if existing is None or (c.type == "hard" and existing.type == "soft"):
                seen[key] = c
    return list(seen.values())
