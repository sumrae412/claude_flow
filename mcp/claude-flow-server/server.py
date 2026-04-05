#!/usr/bin/env python3
"""Claude Flow MCP Server — workflow state and memory access."""

import json
import os
import subprocess
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("claude-flow")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def find_project_dir() -> Path | None:
    """Return the project root directory.

    Resolution order:
    1. CLAUDE_PROJECT_DIR env var
    2. Walk up from cwd looking for a .git directory
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p

    current = Path.cwd()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate

    return None


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("claude-flow://handoff")
def get_handoff() -> str:
    """Current session handoff state."""
    project = find_project_dir()
    if project is None:
        return "No project directory found."

    handoff = project / ".claude" / "handoff.md"
    if handoff.exists():
        return handoff.read_text(encoding="utf-8")
    return "No handoff file found."


@mcp.resource("claude-flow://plan")
def get_plan() -> str:
    """Most recent implementation plan."""
    project = find_project_dir()
    if project is None:
        return "No project directory found."

    plans_dir = project / "docs" / "plans"
    if not plans_dir.is_dir():
        return "No plans directory found."

    # Find .md files with a YYYY-MM-DD prefix and return the most recent
    md_files = sorted(plans_dir.glob("*.md"), key=lambda p: p.name, reverse=True)
    if not md_files:
        return "No plan files found."

    return md_files[0].read_text(encoding="utf-8")


@mcp.resource("claude-flow://memory")
def get_memory() -> str:
    """Project memory / context."""
    project = find_project_dir()
    if project is None:
        return "No project directory found."

    candidates = [
        project / ".claude" / "memory" / "MEMORY.md",
        project / "MEMORY.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    return "No MEMORY.md found."


@mcp.resource("claude-flow://hooks")
def get_hooks() -> str:
    """Hook registry status table."""
    registry_path = Path.home() / ".claude" / "hooks" / "claude-flow" / "hook-registry.json"
    if not registry_path.exists():
        return "Hook registry not found at ~/.claude/hooks/claude-flow/hook-registry.json"

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"Failed to parse hook registry: {exc}"

    hooks_dir = registry_path.parent
    hooks = registry if isinstance(registry, list) else registry.get("hooks", [])

    lines = ["Hook Status Table", "=" * 60, ""]
    lines.append(f"{'ID':<30} {'STATUS':<10} {'SCRIPT'}")
    lines.append("-" * 60)

    for hook in hooks:
        hook_id = hook.get("id", "unknown")
        script_name = hook.get("script", "")
        script_path = hooks_dir / script_name if script_name else None

        if script_path and script_path.exists() and os.access(script_path, os.X_OK):
            status = "ok"
            detail = str(script_path)
        elif script_path and script_path.exists():
            status = "not-exec"
            detail = f"{script_path} (not executable)"
        elif script_name:
            status = "broken"
            detail = f"{hooks_dir / script_name} (not found)"
        else:
            status = "broken"
            detail = "no script specified"

        lines.append(f"{hook_id:<30} {status:<10} {detail}")

    return "\n".join(lines)


@mcp.resource("claude-flow://sessions")
def get_sessions() -> str:
    """Recent session history from git log of handoff.md."""
    project = find_project_dir()
    if project is None:
        return "No project directory found."

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5", "--", ".claude/handoff.md"],
            capture_output=True,
            text=True,
            cwd=str(project),
        )
        output = result.stdout.strip()
        if output:
            return output
        return "No session history."
    except FileNotFoundError:
        return "git not available."


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_workflow_state() -> str:
    """Return a JSON snapshot of current workflow state."""
    project = find_project_dir()
    state: dict = {
        "branch": None,
        "phase": None,
        "plan": None,
        "plan_tasks_completed": None,
        "plan_tasks_total": None,
        "modified_files": [],
        "blockers": [],
    }

    # Git branch
    try:
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project) if project else None,
        )
        state["branch"] = branch_result.stdout.strip() or None
    except FileNotFoundError:
        pass

    # Modified files from git status
    try:
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(project) if project else None,
        )
        modified = []
        for line in status_result.stdout.splitlines():
            if line.strip():
                # Format: XY filename
                modified.append(line[3:].strip())
        state["modified_files"] = modified
    except FileNotFoundError:
        pass

    # Parse handoff.md for phase/blockers
    if project:
        handoff_path = project / ".claude" / "handoff.md"
        if handoff_path.exists():
            handoff_text = handoff_path.read_text(encoding="utf-8")
            for line in handoff_text.splitlines():
                line_lower = line.lower()
                if "phase" in line_lower or "step" in line_lower:
                    stripped = line.strip().lstrip("#").strip()
                    if stripped and state["phase"] is None:
                        state["phase"] = stripped
                if "blocker" in line_lower and ":" in line:
                    blocker = line.split(":", 1)[1].strip()
                    if blocker and blocker.lower() not in ("none", "none.", ""):
                        state["blockers"].append(blocker)

        # Most recent plan
        plans_dir = project / "docs" / "plans"
        if plans_dir.is_dir():
            md_files = sorted(plans_dir.glob("*.md"), key=lambda p: p.name, reverse=True)
            if md_files:
                plan_path = md_files[0]
                state["plan"] = str(plan_path.relative_to(project))

                # Count tasks: lines with "- [ ]" or "- [x]"
                plan_text = plan_path.read_text(encoding="utf-8")
                total = plan_text.count("- [ ]") + plan_text.count("- [x]") + plan_text.count("- [X]")
                completed = plan_text.count("- [x]") + plan_text.count("- [X]")
                if total > 0:
                    state["plan_tasks_total"] = total
                    state["plan_tasks_completed"] = completed

    return json.dumps(state, indent=2)


@mcp.tool()
def search_memory(query: str) -> str:
    """Search all memory .md files for the given query string (case-insensitive)."""
    project = find_project_dir()
    if project is None:
        return "No project directory found."

    search_dirs = [
        project / ".claude" / "memory",
        project,  # for top-level MEMORY.md
    ]

    results: list[str] = []

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue

        # For the project root, only look at MEMORY.md to avoid scanning all files
        if search_dir == project:
            md_files = [project / "MEMORY.md"]
        else:
            md_files = list(search_dir.glob("**/*.md"))

        for md_file in md_files:
            if not md_file.exists():
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue

            matches = []
            for lineno, line in enumerate(text.splitlines(), start=1):
                if query.lower() in line.lower():
                    matches.append(f"  {lineno}: {line}")

            if matches:
                results.append(f"### {md_file}")
                results.extend(matches)
                results.append("")

    if results:
        return "\n".join(results)
    return f'No matches found for "{query}".'


@mcp.tool()
def run_hook_doctor() -> str:
    """Check hook registry and return a JSON health report."""
    registry_path = Path.home() / ".claude" / "hooks" / "claude-flow" / "hook-registry.json"

    if not registry_path.exists():
        return json.dumps(
            {"error": "hook-registry.json not found", "hooks": [], "summary": {"ok": 0, "broken": 0, "warning": 0}},
            indent=2,
        )

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Failed to parse registry: {exc}"}, indent=2)

    hooks_dir = registry_path.parent
    raw_hooks = registry if isinstance(registry, list) else registry.get("hooks", [])

    report_hooks = []
    summary = {"ok": 0, "broken": 0, "warning": 0}

    for hook in raw_hooks:
        hook_id = hook.get("id", "unknown")
        script_name = hook.get("script", "")
        script_path = hooks_dir / script_name if script_name else None

        entry: dict = {"id": hook_id}

        if script_path and script_path.exists() and os.access(script_path, os.X_OK):
            entry["status"] = "ok"
            entry["path"] = str(script_path)
            summary["ok"] += 1
        elif script_path and script_path.exists():
            entry["status"] = "warning"
            entry["path"] = str(script_path)
            entry["reason"] = "script exists but is not executable"
            summary["warning"] += 1
        else:
            entry["status"] = "broken"
            entry["reason"] = "script not found" if script_name else "no script specified"
            if script_path:
                entry["path"] = str(script_path)
            summary["broken"] += 1

        report_hooks.append(entry)

    return json.dumps({"hooks": report_hooks, "summary": summary}, indent=2)


@mcp.tool()
def get_exploration_prompts(task_type: str) -> str:
    """Return exploration prompts for the given task type from the smart-exploration skill.

    task_type: one of endpoint, ui, data, integration, refactor, bugfix, config, general
    """
    prompt_library = (
        Path.home() / ".claude" / "skills" / "smart-exploration" / "prompt-library.md"
    )

    valid_types = {"endpoint", "ui", "data", "integration", "refactor", "bugfix", "config", "general"}
    task_type_lower = task_type.lower().strip()

    if not prompt_library.exists():
        return f"Prompt library not found at {prompt_library}"

    text = prompt_library.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the section for this task_type. Sections are identified by headings
    # that contain the task_type name (case-insensitive).
    section_lines: list[str] = []
    in_section = False
    section_level = 0

    for line in lines:
        # Detect a heading
        if line.startswith("#"):
            heading_text = line.lstrip("#").strip().lower()
            current_level = len(line) - len(line.lstrip("#"))

            if task_type_lower in heading_text:
                in_section = True
                section_level = current_level
                section_lines.append(line)
                continue

            if in_section:
                # End section when we hit a heading at the same or higher level
                if current_level <= section_level:
                    break
                section_lines.append(line)
            continue

        if in_section:
            section_lines.append(line)

    if section_lines:
        return "\n".join(section_lines)

    # Fallback: return note about valid types
    hint = f"task_type '{task_type}' not found in prompt library.\nValid types: {', '.join(sorted(valid_types))}"
    return hint


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
