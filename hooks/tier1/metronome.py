#!/usr/bin/env python3
"""
metronome: Detects shortcut-taking behavior and guides step-by-step execution.

Reads hook input from stdin, checks the last assistant message for
"efficiency" language that signals Claude is about to skip steps
(bulk sed, git checkout to revert, etc.).

Adapted from shinpr/metronome (MIT). Fits claude-flow tier-1 hook pattern.

Design: all error paths exit 0 (allow). Keeping Claude's workflow running
is the hook's primary responsibility; detection is best-effort.
"""

import json
import os
import sys

# Efficiency phrase stems in multiple languages.
# Substring matching is intentional — false positives on negated forms
# like "inefficient" are acceptable because the wording still signals
# efficiency-oriented thinking.
PATTERNS = [
    "efficien",   # English: efficient, efficiently, efficiency
    "効率",       # Japanese: 効率的, 効率化
    "高効",       # Chinese: highly efficient
    "effizien",   # German: effizient, Effizienz
    "efficac",    # French: efficace, efficacement, efficacité
    "eficien",    # Spanish / Portuguese: eficiente, eficiencia
    "효율",       # Korean: 효율적으로, 효율화
    "эффектив",   # Russian: эффективно, эффективность
]

GUIDANCE = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "Slow down.\n\n"
            "Your previous message contained shortcut-taking language. "
            "This is a sign you are about to skip steps.\n\n"
            "Read the current task, execute it one at a time, "
            "verify the result, then move to the next."
        ),
    }
})


def get_last_assistant_text(transcript_path):
    """Return text from the most recent assistant entry that contains text.

    Skips tool_use-only entries and stops at the first user entry,
    so only the current response is considered.
    """
    if not os.path.isfile(transcript_path):
        return ""

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-100:]
    except (OSError, UnicodeDecodeError):
        return ""

    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, TypeError):
            continue

    for entry in reversed(entries):
        entry_type = entry.get("type", "")
        if entry_type == "user":
            break
        if entry_type != "assistant":
            continue
        texts = []
        for block in entry.get("message", {}).get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    texts.append(text)
        if texts:
            return "\n".join(texts)

    return ""


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    transcript_path = hook_input.get("transcript_path", "")
    if not transcript_path:
        sys.exit(0)

    content = get_last_assistant_text(transcript_path)
    if not content:
        sys.exit(0)

    content_lower = content.lower()
    for pattern in PATTERNS:
        if pattern.lower() in content_lower:
            print(GUIDANCE)
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
