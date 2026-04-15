#!/usr/bin/env python3
"""Phase 3 question audit — flag which clarifying questions could be answered
by a deterministic script lookup instead of asking the user.

Principle (Brian Lovin, Notion):
    "Anytime the AI asks you to do something, before responding, try your
    best to see if you could teach the AI to answer that question for itself."

Usage:
    echo '["Q1?", "Q2?"]' | python audit_phase3_questions.py --json

Input: JSON array of question strings on stdin.
Output: JSON with `questions[]` (each flagged `self_answerable` + `suggested_lookup`)
        and `summary` counts.

Heuristics are conservative — false negatives are preferred over false positives.
A question wrongly flagged self-answerable would skip user input and risk a
wrong assumption; a question wrongly NOT flagged just costs one extra Q&A turn.

Exit codes:
    0 — audit complete
    2 — invalid JSON on stdin
"""
from __future__ import annotations
import argparse
import json
import re
import sys


# Patterns that match questions a script could answer deterministically.
# Format: (regex, suggested_lookup)
LOOKUP_PATTERNS = [
    (r"\b(does|is there)\b.*\b(file|module|directory|folder)\b",
     "ls/glob the filesystem"),
    (r"\b(exist|exists)\b.*\b(file|path|module)\b",
     "ls/glob the filesystem"),
    # Path-like token + "exist" (catches "Does foo/bar.py exist?")
    (r"\b(does|is)\b.*[/\\]\S+\s+exist",
     "ls/glob the filesystem"),
    (r"\b(does|is)\b.*\.\w{1,4}\b.*\bexist",
     "ls/glob the filesystem"),
    (r"\bwhat (are the |is the )?column(s)?\b",
     "grep SQLAlchemy Column defs or run inject_lookups.py --scope step"),
    (r"\bwhat.*\bmodel\b.*\bfield(s)?\b",
     "grep model definitions or run inject_lookups.py --scope step"),
    (r"\bwhat (are the |is the )?route(s)?\b",
     "grep @router/@app decorators or run inject_lookups.py --scope plan"),
    (r"\b(current |existing )?(alembic|migration) (head|revision|version)\b",
     "run `alembic heads`"),
    (r"\bwhat.*\bimport(s)?\b.*\b(from|in|available)\b",
     "grep from/import statements in target files"),
    (r"\bwhat.*\bcomponent(s)?\b.*\b(export|defined|available)\b",
     "grep export statements or run inject_lookups.py --scope step"),
    (r"\bwhich.*\bbranch\b",
     "run `git branch --show-current`"),
    (r"\bis\b.*\binstalled\b",
     "check package.json / requirements.txt / pip list"),
    (r"\bwhat.*\bport\b.*\b(server|dev|running)\b",
     "check .claude/launch.json or package.json scripts"),
    (r"\b(do|does) .*\btest(s)?\b.*\b(exist|cover)\b",
     "glob tests/ for matching files"),
    (r"\bwhat.*\bcss class(es)?\b",
     "grep CSS selectors or run inject_lookups.py --scope step"),
    (r"\bwhat version.*\b(installed|available|used)\b",
     "check lockfile or `pip show` / `npm list`"),
]

# Anti-patterns: questions that LOOK like lookups but are actually user intent.
# If any of these match, the question is NOT self-answerable regardless of
# other pattern matches — intent always wins.
INTENT_PATTERNS = [
    r"\bshould\b",
    r"\bdo you want\b",
    r"\bwhat do you (want|prefer|think|expect)\b",
    r"\bhow should (we|it|this)\b",
    r"\bwhich (design|approach|option|strategy)\b",
    r"\bedge case\b.*\bhandle\b",
    r"\b(error|success|empty) (message|state)\b.*\bsay\b",
    r"\bwhat.*\blook like\b",  # design preference
    r"\bprefer\b",
]


def classify(question: str) -> dict:
    q_lower = question.lower()

    # Intent check comes FIRST — user intent questions are never self-answerable
    for pat in INTENT_PATTERNS:
        if re.search(pat, q_lower):
            return {
                "question": question,
                "self_answerable": False,
                "suggested_lookup": None,
                "reason": "user intent — requires human decision",
            }

    # Lookup pattern check
    for pat, lookup in LOOKUP_PATTERNS:
        if re.search(pat, q_lower):
            return {
                "question": question,
                "self_answerable": True,
                "suggested_lookup": lookup,
                "reason": "matches deterministic lookup pattern",
            }

    return {
        "question": question,
        "self_answerable": False,
        "suggested_lookup": None,
        "reason": "no deterministic lookup pattern matched",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        questions = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"invalid JSON on stdin: {e}"}), file=sys.stderr)
        return 2

    if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
        print(json.dumps({"error": "expected JSON array of question strings"}), file=sys.stderr)
        return 2

    classified = [classify(q) for q in questions]
    n_self = sum(1 for q in classified if q["self_answerable"])
    out = {
        "questions": classified,
        "summary": {
            "total": len(classified),
            "self_answerable": n_self,
            "user_facing": len(classified) - n_self,
        },
    }
    if args.json:
        print(json.dumps(out))
    else:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
