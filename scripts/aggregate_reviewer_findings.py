"""Convert scored-reviewer output into standard blocking findings.

Phase 6 runs this after each scored reviewer completes. Registry entries
with score_threshold trigger the conversion; plain binary reviewers skip it.

Defensive posture: this function processes LLM-generated JSON whose shape
is controlled by persona-prompted models. Tolerate malformed output rather
than crashing Phase 6 — but LOG every skip so operators can diagnose why a
reviewer didn't block.

Usage:
    # Library:
    from scripts.aggregate_reviewer_findings import convert_scores_to_findings
    result = convert_scores_to_findings(reviewer_output, registry_entry)

    # CLI (for phase-6 integration):
    python scripts/aggregate_reviewer_findings.py \
        --reviewer path/to/reviewer-output.json \
        --registry reviewer-registry.json \
        --reviewer-id adversarial-breaker
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("aggregate_reviewer_findings")


_MARKER = "adversarial-breaker-aggregator"


def convert_scores_to_findings(reviewer_output: dict, registry_entry: dict) -> dict:
    """Append one blocking finding per sub-threshold score.

    Idempotent: findings already marked with ``source == _MARKER`` for a
    given criterion are skipped on re-entry, so calling the function twice
    on the same (output, entry) pair does not duplicate findings.

    Returns the reviewer_output dict with ``findings`` expanded. Non-scored
    reviewers (no ``score_threshold`` key) pass through unchanged.

    Malformed LLM output is tolerated: missing fields, wrong types, or
    non-numeric scores result in a skipped entry + WARNING log, never a
    crash. Missing ``scores`` key → pass-through with a warning.
    """
    reviewer_id = reviewer_output.get("reviewer", "<unknown>")

    threshold = registry_entry.get("score_threshold")
    if threshold is None:
        # Not a scored reviewer — nothing to aggregate. Debug-level; common.
        log.debug("aggregator: %s has no score_threshold; passing through", reviewer_id)
        return reviewer_output

    # Strict-less-than semantics: score == threshold is NOT blocking.
    try:
        threshold = int(threshold)
    except (TypeError, ValueError):
        log.warning(
            "aggregator: %s score_threshold=%r is not an integer; skipping conversion",
            reviewer_id,
            threshold,
        )
        return reviewer_output

    findings = list(reviewer_output.get("findings", []))

    # Idempotency: track criteria already converted by this aggregator on a
    # prior run. Re-entry should not produce duplicate blocking findings.
    already_aggregated = {
        f.get("criterion")
        for f in findings
        if isinstance(f, dict)
        and f.get("source") == _MARKER
        and f.get("criterion")
    }

    scores = reviewer_output.get("scores")
    if scores is None:
        log.warning(
            "aggregator: %s output missing 'scores' key; no adversarial findings generated",
            reviewer_id,
        )
        return {**reviewer_output, "findings": findings}
    if not isinstance(scores, list):
        log.warning(
            "aggregator: %s 'scores' is %s, expected list; skipping conversion",
            reviewer_id,
            type(scores).__name__,
        )
        return {**reviewer_output, "findings": findings}

    added = 0
    for i, score_entry in enumerate(scores):
        if not isinstance(score_entry, dict):
            log.warning(
                "aggregator: %s scores[%d] is %s, expected dict; skipping entry",
                reviewer_id,
                i,
                type(score_entry).__name__,
            )
            continue

        score = score_entry.get("score")
        criterion = score_entry.get("criterion")
        break_case = score_entry.get("break_case", "<no break_case provided>")

        if criterion is None:
            log.warning(
                "aggregator: %s scores[%d] missing 'criterion'; skipping entry",
                reviewer_id,
                i,
            )
            continue

        # Coerce score to int; tolerate string digits; skip non-numeric.
        try:
            score_int = int(score)
        except (TypeError, ValueError):
            log.warning(
                "aggregator: %s scores[%d] (criterion=%s) score=%r is not an integer; skipping",
                reviewer_id,
                i,
                criterion,
                score,
            )
            continue

        if score_int >= threshold:
            continue

        if criterion in already_aggregated:
            log.debug(
                "aggregator: %s criterion=%s already aggregated; skipping duplicate",
                reviewer_id,
                criterion,
            )
            continue

        findings.append(
            {
                "source": _MARKER,
                "criterion": criterion,
                "severity": "blocking",
                # Surface criterion in `file` so Phase 5 retry can group by axis.
                "file": f"<adversarial:{criterion}>",
                "line": 0,
                "message": (
                    f"Adversarial score {score_int}/10 "
                    f"on {criterion}: {break_case}"
                ),
                "fix": f"Address the break case above; target score >= {threshold}",
            }
        )
        already_aggregated.add(criterion)
        added += 1

    if added:
        log.info(
            "aggregator: %s added %d blocking finding(s) from sub-threshold scores",
            reviewer_id,
            added,
        )

    return {**reviewer_output, "findings": findings}


def _lookup_registry_entry(registry: dict, reviewer_id: str) -> dict:
    for entry in registry.get("reviewers", []):
        if entry.get("id") == reviewer_id:
            return entry
    raise KeyError(f"reviewer_id={reviewer_id!r} not found in registry")


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert scored-reviewer JSON output into standard blocking "
            "findings. Reads reviewer output and registry from JSON files; "
            "writes merged findings JSON to stdout."
        )
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        type=Path,
        help="Path to reviewer output JSON (contains scores[] and findings[]).",
    )
    parser.add_argument(
        "--registry",
        required=True,
        type=Path,
        help="Path to reviewer-registry.json.",
    )
    parser.add_argument(
        "--reviewer-id",
        help=(
            "Reviewer id to look up in the registry. Defaults to "
            "reviewer_output['reviewer']."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Increase logging verbosity (-v info, -vv debug).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=[logging.WARNING, logging.INFO, logging.DEBUG][min(args.verbose, 2)],
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        reviewer_output = json.loads(args.reviewer.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.error("failed to load reviewer output from %s: %s", args.reviewer, e)
        return 2

    try:
        registry = json.loads(args.registry.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.error("failed to load registry from %s: %s", args.registry, e)
        return 2

    reviewer_id = args.reviewer_id or reviewer_output.get("reviewer")
    if not reviewer_id:
        log.error(
            "cannot determine reviewer id; pass --reviewer-id or include "
            "'reviewer' key in the reviewer output"
        )
        return 2

    try:
        registry_entry = _lookup_registry_entry(registry, reviewer_id)
    except KeyError as e:
        log.error("%s", e)
        return 2

    result = convert_scores_to_findings(reviewer_output, registry_entry)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
