"""symbolic_verifier.py — Run hard (deterministic) and soft (LLM) constraint checks.

Hard checks use subprocess grep/regex. Soft checks use a mock-able LLM client.
Stdlib only (+ constraint_compiler import).
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

from constraint_compiler import Constraint


# -- VerificationResult -------------------------------------------------------

@dataclass
class VerificationResult:
    passed: bool
    violations: list[dict] = field(default_factory=list)
    checked: int = 0


# -- Hard checks --------------------------------------------------------------

def run_hard_check(constraint: Constraint, file_path: str) -> tuple[bool, str]:
    """Run grep/regex check. Returns (passed, details)."""
    if not os.path.exists(file_path):
        return False, f"File not found: {file_path}"
    pattern = constraint.pattern or ""
    check = (constraint.check or "grep").lower()
    try:
        if check == "regex":
            text = open(file_path, encoding="utf-8").read()
            m = re.search(pattern, text)
            if m:
                return True, f"Pattern matched at position {m.start()}"
            return False, f"Pattern '{pattern}' not found in {file_path}"
        elif check in ("grep", "ast-grep"):
            result = subprocess.run(
                ["grep", "-n", pattern, file_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, f"Pattern '{pattern}' not found in {file_path}"
        else:
            return False, f"Unknown check type: {check}"
    except subprocess.TimeoutExpired:
        return False, "Check timed out"
    except Exception as exc:  # noqa: BLE001
        return False, f"Check error: {exc}"


# -- Soft checks --------------------------------------------------------------

def run_soft_check(constraint: Constraint, code_diff: str,
                   llm_client: Any) -> tuple[bool, str]:
    """Run LLM soft check. Returns (passed, violation_description).

    llm_client must expose .check(prompt: str) -> str.
    Response starting with 'YES' → violation (fail).
    """
    rule = constraint.rule or constraint.message or "(no rule)"
    prompt = (
        f"Does this code violate the following rule?\n"
        f"Rule: {rule}\n\n"
        f"Code:\n{code_diff}\n\n"
        f"Answer YES (with specific violation) or NO."
    )
    response = llm_client.check(prompt)
    if response.strip().upper().startswith("YES"):
        return False, response.strip()
    return True, ""


# -- Full verification pipeline -----------------------------------------------

def verify_output(constraints: list[Constraint], changed_files: list[str],
                  llm_client: Any) -> VerificationResult:
    """Run all constraints against changed files. Returns VerificationResult."""
    violations: list[dict] = []
    checked = 0
    for constraint in constraints:
        if constraint.type == "hard":
            for file_path in changed_files:
                checked += 1
                passed, details = run_hard_check(constraint, file_path)
                if not passed:
                    violations.append({"id": constraint.id, "type": "hard",
                                       "message": constraint.message or details,
                                       "file": file_path, "details": details})
        elif constraint.type == "soft":
            combined = "\n".join(
                open(f, encoding="utf-8").read()
                for f in changed_files if os.path.exists(f)
            )
            checked += 1
            passed, desc = run_soft_check(constraint, combined, llm_client)
            if not passed:
                violations.append({"id": constraint.id, "type": "soft",
                                   "message": constraint.rule or constraint.message or "",
                                   "file": ", ".join(changed_files), "details": desc})
    return VerificationResult(passed=len(violations) == 0,
                              violations=violations, checked=checked)


# -- Retry prompt formatting --------------------------------------------------

def format_violations_for_retry(violations: list[dict]) -> str:
    """Format violation list into a prompt block for agent retry."""
    if not violations:
        return "No constraint violations found."
    lines = ["CONSTRAINT VIOLATIONS — Fix all of the following before resubmitting:", ""]
    for i, v in enumerate(violations, 1):
        lines.append(f"{i}. [{v.get('type','?').upper()}] {v.get('id','?')}: {v.get('message','')}")
        if v.get("file"):
            lines.append(f"   File: {v['file']}")
        if v.get("details") and v.get("details") != v.get("message"):
            lines.append(f"   Detail: {v['details']}")
        lines.append("")
    lines.append("Revise the code to satisfy every constraint listed above.")
    return "\n".join(lines)
