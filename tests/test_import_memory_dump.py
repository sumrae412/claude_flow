"""Tests for scripts/import_memory_dump.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from import_memory_dump import (  # noqa: E402
    CATEGORY_DECISIONS,
    CATEGORY_GOTCHAS,
    CATEGORY_REJECTED,
    CATEGORY_USER_PREFERENCES,
    build_review_markdown,
    classify_line,
    categorize_lines,
    split_candidate_lines,
    write_import_review,
)


def test_preference_line_maps_to_user_preferences() -> None:
    line: str = "Prefer concise responses with direct answers."
    assert classify_line(line) == CATEGORY_USER_PREFERENCES


def test_compact_preference_line_maps_to_user_preferences() -> None:
    line: str = "Prefer concise responses."
    assert classify_line(line) == CATEGORY_USER_PREFERENCES


def test_decision_line_maps_to_decisions() -> None:
    line: str = "Decision: use local markdown over Notion."
    assert classify_line(line) == CATEGORY_DECISIONS


def test_gotcha_line_maps_to_recurring_gotchas() -> None:
    line: str = "Gotcha: do not auto-promote imported memory."
    assert classify_line(line) == CATEGORY_GOTCHAS


def test_short_vague_line_maps_to_rejected() -> None:
    assert classify_line("Important.") == CATEGORY_REJECTED


def test_generated_markdown_has_expected_headings() -> None:
    lines: list[str] = split_candidate_lines(
        """
        # Export
        - Prefer concise responses.
        - Decision: use local markdown over Notion.
        - Gotcha: avoid auto-promotion.
        - The repo uses hooks for memory triage.
        - Today only.
        """,
    )
    categorized: dict[str, list[str]] = categorize_lines(lines)
    markdown: str = build_review_markdown(Path("imported.md"), categorized)

    assert "# Import Review" in markdown
    assert "## Project Facts" in markdown
    assert "## User Preferences" in markdown
    assert "## Decisions" in markdown
    assert "## Recurring Gotchas" in markdown
    assert "## Rejected / Too Vague / Task-Specific" in markdown
    assert "- [ ] Prefer concise responses." in markdown


def test_existing_output_not_overwritten_without_force(tmp_path: Path) -> None:
    source: Path = tmp_path / "dump.md"
    output: Path = tmp_path / "memory" / "IMPORT_REVIEW.md"
    source.write_text("Prefer short answers.\n", encoding="utf-8")
    output.parent.mkdir()
    output.write_text("existing", encoding="utf-8")

    try:
        write_import_review(source, output, tmp_path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")

    assert output.read_text(encoding="utf-8") == "existing"


def test_script_does_not_create_or_modify_memory_md(tmp_path: Path) -> None:
    source: Path = tmp_path / "dump.md"
    memory_md: Path = tmp_path / "memory" / "MEMORY.md"
    source.write_text("Prefer durable memory review.\n", encoding="utf-8")
    memory_md.parent.mkdir()
    memory_md.write_text("canonical", encoding="utf-8")

    write_import_review(
        source=source,
        output=tmp_path / "memory" / "IMPORT_REVIEW.md",
        project_root=tmp_path,
    )

    assert memory_md.read_text(encoding="utf-8") == "canonical"
