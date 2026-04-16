#!/usr/bin/env python3
"""Calibrate the adversarial-breaker reviewer against a labeled corpus.

For each case in the corpus, dispatch the live reviewer, then compute
per-criterion agreement against human-labeled ground truth using the
sliding-tolerance formula:

    case_agreement   = (count of criteria where |judge - human| <= 2) / 6
    overall_agreement = mean(case_agreement for case in corpus)

Compare overall_agreement against the registry's `min_agreement` (default
0.7). On pass, update the registry's `last_calibrated` and `last_agreement`
fields in place.

Usage:

    # Dry run (load + dispatch + score, but don't write registry)
    RUN_LIVE_LLM=1 ANTHROPIC_API_KEY=... python scripts/calibrate_adversarial_breaker.py --dry-run

    # Real run (writes registry on pass)
    RUN_LIVE_LLM=1 ANTHROPIC_API_KEY=... python scripts/calibrate_adversarial_breaker.py

    # Or via Make:
    make calibrate-adversarial

Cost: ~20 Sonnet calls at 2000 max_tokens each = ~$0.20 per run. Don't run
on every PR; this is a manual / monthly cadence target.

Exit codes:
  0  agreement >= min_agreement (PASS)
  1  agreement <  min_agreement (FAIL)
  2  infrastructure error (missing persona, dispatch crash, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "tests/fixtures/adversarial_breaker/calibration_corpus"
REGISTRY = REPO_ROOT / "reviewer-registry.json"
DEFAULT_REVIEWER_ID = "adversarial-breaker"
TOLERANCE = 2  # |judge - human| <= TOLERANCE counts as agreement


@dataclass(frozen=True)
class CalibrationCase:
    """One labeled case from the corpus."""

    case_id: str
    primary_criterion: str | None
    diff: str
    expected_scores: dict[str, int]
    rationale: str


def load_corpus(corpus_dir: Path) -> list[CalibrationCase]:
    """Load every case-* subdirectory of corpus_dir into CalibrationCase objects.

    Skips files (README, etc.) and any directory not starting with 'case-'.
    Sorted by case_id for deterministic ordering.
    """
    cases: list[CalibrationCase] = []
    for child in sorted(corpus_dir.iterdir()):
        if not child.is_dir() or not child.name.startswith("case-"):
            continue
        diff_path = child / "diff.patch"
        expected_path = child / "expected.json"
        if not diff_path.exists() or not expected_path.exists():
            raise FileNotFoundError(
                f"case {child.name} is missing diff.patch or expected.json"
            )
        meta = json.loads(expected_path.read_text())
        cases.append(
            CalibrationCase(
                case_id=meta["case_id"],
                primary_criterion=meta.get("primary_criterion"),
                diff=diff_path.read_text(),
                expected_scores=meta["expected_scores"],
                rationale=meta.get("rationale", ""),
            )
        )
    if not cases:
        raise FileNotFoundError(f"no case-* directories under {corpus_dir}")
    return cases


def compute_case_agreement(
    human: dict[str, int], judge: dict[str, int], tolerance: int = TOLERANCE
) -> float:
    """Per-case agreement: fraction of criteria where |judge - human| <= tolerance.

    Pure function — no side effects, no LLM calls. Unit-tested directly.

    Both dicts must have the same set of keys (the 6 scored criteria). If
    judge is missing a criterion the reviewer was supposed to score, that
    criterion counts as disagreement (score 0). This bias is intentional:
    we don't want a reviewer that omits criteria to look like it agrees.
    """
    if not human:
        raise ValueError("human scores cannot be empty")
    matches = 0
    for criterion, human_score in human.items():
        judge_score = judge.get(criterion)
        if judge_score is None:
            continue  # missing → disagreement
        if abs(judge_score - human_score) <= tolerance:
            matches += 1
    return matches / len(human)


def compute_overall_agreement(case_agreements: list[float]) -> float:
    """Overall agreement: arithmetic mean of per-case agreements."""
    if not case_agreements:
        raise ValueError("case_agreements cannot be empty")
    return statistics.fmean(case_agreements)


def extract_judge_scores(response: dict[str, Any]) -> dict[str, int]:
    """Pull {criterion: score} out of the reviewer's JSON envelope.

    Defensive against malformed entries — drops anything missing criterion
    or score, so compute_case_agreement counts those as disagreement.
    """
    scores: dict[str, int] = {}
    for entry in response.get("scores", []) or []:
        crit = entry.get("criterion")
        raw = entry.get("score")
        if crit is None or raw is None:
            continue
        try:
            scores[crit] = int(raw)
        except (ValueError, TypeError):
            continue
    return scores


def resolve_persona(registry_data: dict, reviewer_id: str) -> Path:
    """Resolve the persona file path from the registry entry's
    persona_file + persona_file_root fields."""
    reviewer = next(
        (r for r in registry_data["reviewers"] if r["id"] == reviewer_id), None
    )
    if reviewer is None:
        raise KeyError(f"reviewer {reviewer_id!r} not found in registry")
    persona_rel = reviewer.get("persona_file")
    persona_root = reviewer.get("persona_file_root")
    if persona_rel is None or persona_root is None:
        raise KeyError(
            f"reviewer {reviewer_id!r} is missing persona_file/persona_file_root"
        )
    return Path(os.path.expanduser(persona_root)) / persona_rel


def get_calibration_block(registry_data: dict, reviewer_id: str) -> dict:
    """Return the reviewer's calibration block, raising if absent."""
    for r in registry_data["reviewers"]:
        if r["id"] == reviewer_id:
            calib = r.get("calibration")
            if calib is None:
                raise KeyError(
                    f"reviewer {reviewer_id!r} has no calibration block"
                )
            return calib
    raise KeyError(f"reviewer {reviewer_id!r} not in registry")


def update_registry(
    registry_path: Path,
    reviewer_id: str,
    agreement: float,
    today_iso: str,
) -> None:
    """Update the reviewer's calibration block with last_calibrated and
    last_agreement, preserving all other fields. Writes back with indent=2
    + trailing newline to match the existing file's formatting.
    """
    data = json.loads(registry_path.read_text())
    for r in data["reviewers"]:
        if r["id"] == reviewer_id:
            calib = r.setdefault("calibration", {})
            calib["last_calibrated"] = today_iso
            calib["last_agreement"] = round(agreement, 4)
            break
    else:
        raise KeyError(f"reviewer {reviewer_id!r} not in registry")
    registry_path.write_text(json.dumps(data, indent=2) + "\n")


def _print_case_breakdown(
    case: CalibrationCase, judge_scores: dict[str, int], agreement: float
) -> None:
    """Pretty-print one case's per-criterion comparison."""
    primary_marker = (
        f" (primary: {case.primary_criterion})" if case.primary_criterion else " (clean)"
    )
    print(f"\n  {case.case_id}{primary_marker}")
    print(f"    case agreement: {agreement:.2%}")
    print("    criterion              human  judge  delta  match?")
    print("    --------------------- ------ ------ ------ ------")
    for crit, human in case.expected_scores.items():
        judge = judge_scores.get(crit)
        if judge is None:
            print(f"    {crit:<22} {human:>5}    -      -    MISSING")
            continue
        delta = abs(judge - human)
        match = "yes" if delta <= TOLERANCE else "NO"
        print(f"    {crit:<22} {human:>5}  {judge:>5}  {delta:>5}  {match}")


def run_calibration(
    registry_path: Path,
    corpus_dir: Path,
    reviewer_id: str,
    dry_run: bool,
) -> tuple[float, bool]:
    """Top-level orchestration. Returns (overall_agreement, passed)."""
    if os.environ.get("RUN_LIVE_LLM") != "1":
        print(
            "ERROR: set RUN_LIVE_LLM=1 to dispatch real LLM calls "
            "(this script makes ~20 paid Anthropic API requests).",
            file=sys.stderr,
        )
        sys.exit(2)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(2)

    registry_data = json.loads(registry_path.read_text())
    persona_path = resolve_persona(registry_data, reviewer_id)
    if not persona_path.exists():
        print(f"ERROR: persona file not found at {persona_path}", file=sys.stderr)
        sys.exit(2)
    persona = persona_path.read_text()
    calib = get_calibration_block(registry_data, reviewer_id)
    min_agreement = float(calib.get("min_agreement", 0.7))

    cases = load_corpus(corpus_dir)
    print(f"Loaded {len(cases)} cases from {corpus_dir}")
    print(f"Persona: {persona_path}")
    print(f"Reviewer: {reviewer_id}  (min_agreement: {min_agreement})")
    print(f"Mode: {'DRY RUN — registry not updated' if dry_run else 'LIVE — registry will be updated on pass'}")
    print("\nDispatching cases...")

    # Lazy-import dispatch helper so unit tests can import this module
    # without requiring the anthropic SDK.
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from adversarial_dispatch import dispatch_via_anthropic_api

    case_agreements: list[float] = []
    for case in cases:
        try:
            response = dispatch_via_anthropic_api(persona, case.diff)
        except Exception as e:
            print(
                f"\nERROR dispatching {case.case_id}: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            sys.exit(2)
        judge_scores = extract_judge_scores(response)
        agreement = compute_case_agreement(case.expected_scores, judge_scores)
        case_agreements.append(agreement)
        _print_case_breakdown(case, judge_scores, agreement)

    overall = compute_overall_agreement(case_agreements)
    passed = overall >= min_agreement

    print("\n" + "=" * 60)
    print(f"  Overall agreement: {overall:.2%}  (threshold: {min_agreement:.0%})")
    print(f"  Verdict: {'PASS' if passed else 'FAIL'}")
    print("=" * 60)

    if not dry_run and passed:
        today = date.today().isoformat()
        update_registry(registry_path, reviewer_id, overall, today)
        print(f"\nRegistry updated: last_calibrated={today}, last_agreement={overall:.4f}")
    elif not dry_run and not passed:
        print(
            "\nRegistry NOT updated — agreement below threshold. "
            "Investigate the per-case breakdown above before recording a "
            "fail value into the registry."
        )

    return overall, passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)
    parser.add_argument("--reviewer-id", default=DEFAULT_REVIEWER_ID)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dispatch + score but don't write the registry.",
    )
    args = parser.parse_args()

    _, passed = run_calibration(
        registry_path=args.registry,
        corpus_dir=args.corpus_dir,
        reviewer_id=args.reviewer_id,
        dry_run=args.dry_run,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
