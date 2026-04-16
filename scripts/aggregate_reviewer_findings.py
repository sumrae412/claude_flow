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
                "fix": f"Address the break case above; target score >= {threshold}",
            })
    return {**reviewer_output, "findings": findings}
