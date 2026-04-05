#!/usr/bin/env python3
"""PlanCraft Review Script — Direct API calls to DeepSeek and OpenAI.

Replaces the MCP server approach with a standalone script that Claude
calls via Bash. Supports two reviewers:
  - deepseek: Security, architecture, completeness, scope adherence
  - codex: Code efficiency, patterns, maintainability, scope adherence

Usage:
    python3 ~/.claude/scripts/plancraft_review.py \
        --reviewer deepseek \
        --plan-file /path/to/plan.md \
        --scope-file /path/to/scope.txt

    python3 ~/.claude/scripts/plancraft_review.py \
        --reviewer codex \
        --plan-file /path/to/plan.md \
        --scope-file /path/to/scope.txt

Environment variables:
    DEEPSEEK_API_KEY  — Required for --reviewer deepseek
    OPENAI_API_KEY    — Required for --reviewer codex

Output: JSON to stdout with keys:
    recommendations, model, token_usage, error (if any)
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print(json.dumps({
        "error": "httpx not installed. Run: pip install httpx",
        "recommendations": "",
        "model": "",
        "token_usage": {},
    }))
    sys.exit(1)


# --- Reviewer Configurations ---

REVIEWERS = {
    "deepseek": {
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "temperature": 0.3,
        "env_key": "DEEPSEEK_API_KEY",
        "system_prompt": (
            "You are an expert software architect reviewing an "
            "implementation plan.\n\n"
            "Focus on:\n"
            "1. SECURITY: Authentication, authorization, input "
            "validation, secrets management, injection risks\n"
            "2. ARCHITECTURE: Design patterns, separation of "
            "concerns, scalability, maintainability\n"
            "3. COMPLETENESS: Error handling, edge cases, "
            "logging, rollback strategies\n"
            "4. SCOPE ADHERENCE: Flag any recommendations that "
            "would expand beyond the defined scope\n\n"
            "For each finding, provide:\n"
            "- Category (Security/Architecture/Completeness/"
            "Scope)\n"
            "- Severity (Critical/Important/Suggestion)\n"
            "- Specific, actionable recommendation\n"
            "- Whether it stays within the defined scope "
            "(IN_SCOPE or OUT_OF_SCOPE)\n\n"
            "Format as a numbered list. Be concrete - reference "
            "specific parts of the plan."
        ),
    },
    "codex": {
        "api_url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
        "temperature": 0.2,
        "env_key": "OPENAI_API_KEY",
        "system_prompt": (
            "You are a senior software engineer reviewing an "
            "implementation plan for code quality and "
            "efficiency.\n\n"
            "Focus on:\n"
            "1. CODE EFFICIENCY: Query patterns, caching "
            "opportunities, async handling, algorithm choices\n"
            "2. PATTERNS: Design patterns, DRY violations, "
            "abstraction quality, naming\n"
            "3. MAINTAINABILITY: Readability, testability, "
            "documentation needs, future-proofing\n"
            "4. SCOPE ADHERENCE: Flag any recommendations that "
            "would expand beyond the defined scope\n\n"
            "For each finding, provide:\n"
            "- Category (Efficiency/Patterns/Maintainability/"
            "Scope)\n"
            "- Severity (Critical/Important/Suggestion)\n"
            "- Specific, actionable recommendation with code "
            "examples where helpful\n"
            "- Whether it stays within the defined scope "
            "(IN_SCOPE or OUT_OF_SCOPE)\n\n"
            "Format as a numbered list. Be concrete - reference "
            "specific parts of the plan."
        ),
    },
}

MAX_RETRIES = 1
TIMEOUT_SECONDS = 60

# Shell config files to source if API keys are missing
SHELL_CONFIGS = [
    "~/.zshrc",
    "~/.bash_profile",
    "~/.bashrc",
    "~/.zprofile",
]


def _load_keys_from_shell() -> None:
    """Source shell config files to load API keys.

    When running inside Claude Code, environment variables
    from the user's shell profile may not be inherited.
    This function sources common shell config files and
    extracts DEEPSEEK_API_KEY and OPENAI_API_KEY.
    """
    import subprocess

    for config_file in SHELL_CONFIGS:
        path = os.path.expanduser(config_file)
        if not os.path.exists(path):
            continue
        try:
            result = subprocess.run(
                [
                    "bash", "-c",
                    f"source {path} 2>/dev/null && "
                    f"echo \"DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY\" && "
                    f"echo \"OPENAI_API_KEY=$OPENAI_API_KEY\"",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                continue
            for line in result.stdout.strip().split("\n"):
                if "=" in line:
                    key, _, value = line.partition("=")
                    if value and key in (
                        "DEEPSEEK_API_KEY",
                        "OPENAI_API_KEY",
                    ):
                        os.environ.setdefault(key, value)
        except (subprocess.TimeoutExpired, OSError):
            continue


def call_reviewer(
    reviewer_name: str,
    plan_text: str,
    scope_definition: str,
) -> dict:
    """Call a reviewer API and return structured results.

    Args:
        reviewer_name: 'deepseek' or 'codex'
        plan_text: The full implementation plan text.
        scope_definition: In-scope/out-of-scope boundaries.

    Returns:
        Dict with recommendations, model, token_usage, error.
    """
    config = REVIEWERS[reviewer_name]
    api_key = os.environ.get(config["env_key"], "")

    if not api_key:
        return {
            "error": (
                f"{config['env_key']} not set. "
                f"Export it in your shell profile."
            ),
            "recommendations": "",
            "model": config["model"],
            "token_usage": {},
        }

    user_message = (
        f"SCOPE DEFINITION:\n{scope_definition}\n\n"
        f"IMPLEMENTATION PLAN:\n{plan_text}\n\n"
        "Provide your numbered recommendations."
    )

    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": user_message},
        ],
        "temperature": config["temperature"],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                resp = client.post(
                    config["api_url"],
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            return {
                "recommendations": content,
                "model": data.get("model", config["model"]),
                "token_usage": {
                    "prompt_tokens": usage.get(
                        "prompt_tokens", 0
                    ),
                    "completion_tokens": usage.get(
                        "completion_tokens", 0
                    ),
                    "total_tokens": usage.get(
                        "total_tokens", 0
                    ),
                },
            }
        except (httpx.HTTPError, KeyError) as e:
            if attempt < MAX_RETRIES:
                continue
            return {
                "error": (
                    f"{reviewer_name} API failed after "
                    f"{MAX_RETRIES + 1} attempts: {str(e)}"
                ),
                "recommendations": "",
                "model": config["model"],
                "token_usage": {},
            }

    # Should never reach here, but satisfy type checker
    return {
        "error": "Unexpected state",
        "recommendations": "",
        "model": config["model"],
        "token_usage": {},
    }


def main() -> None:
    """Parse args and run the requested reviewer."""
    parser = argparse.ArgumentParser(
        description="PlanCraft AI Reviewer"
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        choices=["deepseek", "codex"],
        help="Which reviewer to use",
    )
    parser.add_argument(
        "--plan-file",
        required=True,
        help="Path to the plan text file",
    )
    parser.add_argument(
        "--scope-file",
        required=True,
        help="Path to the scope definition file",
    )
    args = parser.parse_args()

    plan_path = Path(args.plan_file).expanduser()
    scope_path = Path(args.scope_file).expanduser()

    if not plan_path.exists():
        print(json.dumps({
            "error": f"Plan file not found: {plan_path}",
            "recommendations": "",
            "model": "",
            "token_usage": {},
        }))
        sys.exit(1)

    if not scope_path.exists():
        print(json.dumps({
            "error": f"Scope file not found: {scope_path}",
            "recommendations": "",
            "model": "",
            "token_usage": {},
        }))
        sys.exit(1)

    # Load API keys from shell config if not in environment
    _load_keys_from_shell()

    plan_text = plan_path.read_text(encoding="utf-8")
    scope_definition = scope_path.read_text(encoding="utf-8")

    result = call_reviewer(
        args.reviewer, plan_text, scope_definition
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
