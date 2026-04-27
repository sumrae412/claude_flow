"""Tests for scripts/memory_archive.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from memory_archive import (  # noqa: E402
    create_archive,
    diff_archive,
    iter_memory_files,
    list_archives,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_archive_creates_expected_directory_and_copies_files(
    tmp_path: Path,
) -> None:
    memory_dir: Path = tmp_path / "memory"
    archive_root: Path = tmp_path / "archives"
    _write(memory_dir / "MEMORY.md", "index\n")
    _write(memory_dir / "semantic" / "facts.md", "facts\n")
    _write(memory_dir / "episodic" / "events.jsonl", "{}\n")

    archive_dir: Path = create_archive(
        memory_dir,
        archive_root,
        archive_id="2026-04-27T181500Z",
    )

    assert archive_dir == archive_root / "2026-04-27T181500Z"
    assert (archive_dir / "MEMORY.md").read_text(encoding="utf-8") == "index\n"
    assert (archive_dir / "semantic" / "facts.md").exists()
    assert (archive_dir / "episodic" / "events.jsonl").exists()


def test_review_artifacts_are_excluded_by_default(tmp_path: Path) -> None:
    memory_dir: Path = tmp_path / "memory"
    _write(memory_dir / "MEMORY.md", "index\n")
    _write(memory_dir / "IMPORT_REVIEW.md", "review\n")
    _write(memory_dir / "REVIEW_QUEUE.md", "queue\n")

    names: list[str] = [
        path.relative_to(memory_dir).as_posix()
        for path in iter_memory_files(memory_dir)
    ]

    assert names == ["MEMORY.md"]


def test_derived_knowledge_files_are_excluded_by_default(
    tmp_path: Path,
) -> None:
    memory_dir: Path = tmp_path / "memory"
    _write(memory_dir / "MEMORY.md", "index\n")
    _write(memory_dir / "knowledge" / "article.md", "derived\n")

    names: list[str] = [
        path.relative_to(memory_dir).as_posix()
        for path in iter_memory_files(memory_dir)
    ]

    assert names == ["MEMORY.md"]


def test_include_derived_includes_knowledge_files(tmp_path: Path) -> None:
    memory_dir: Path = tmp_path / "memory"
    _write(memory_dir / "MEMORY.md", "index\n")
    _write(memory_dir / "knowledge" / "article.md", "derived\n")

    names: list[str] = [
        path.relative_to(memory_dir).as_posix()
        for path in iter_memory_files(memory_dir, include_derived=True)
    ]

    assert names == ["MEMORY.md", "knowledge/article.md"]


def test_list_returns_archives_sorted_by_id(tmp_path: Path) -> None:
    archive_root: Path = tmp_path / "archives"
    _write(archive_root / "b" / "MEMORY.md", "b\n")
    _write(archive_root / "a" / "MEMORY.md", "a\n")

    archive_ids: list[str] = [
        archive.archive_id for archive in list_archives(archive_root)
    ]

    assert archive_ids == ["a", "b"]


def test_diff_reports_changed_added_and_removed_files(tmp_path: Path) -> None:
    memory_dir: Path = tmp_path / "memory"
    archive_dir: Path = tmp_path / "archives" / "old"
    _write(archive_dir / "changed.md", "old\n")
    _write(memory_dir / "changed.md", "new\n")
    _write(memory_dir / "added.md", "added\n")
    _write(archive_dir / "removed.md", "removed\n")

    diff: str = diff_archive(memory_dir, archive_dir)

    assert "--- archive/changed.md" in diff
    assert "+++ current/changed.md" in diff
    assert "+new\n" in diff
    assert "--- archive/added.md" in diff
    assert "+++ current/added.md" in diff
    assert "--- archive/removed.md" in diff
    assert "+++ current/removed.md" in diff


def test_diff_command_does_not_modify_current_memory(tmp_path: Path) -> None:
    memory_dir: Path = tmp_path / "memory"
    archive_dir: Path = tmp_path / "archives" / "old"
    current_file: Path = memory_dir / "MEMORY.md"
    _write(archive_dir / "MEMORY.md", "old\n")
    _write(current_file, "current\n")

    diff_archive(memory_dir, archive_dir)

    assert current_file.read_text(encoding="utf-8") == "current\n"


def test_diff_ignores_current_review_artifacts(tmp_path: Path) -> None:
    memory_dir: Path = tmp_path / "memory"
    archive_dir: Path = tmp_path / "archives" / "old"
    _write(archive_dir / "MEMORY.md", "index\n")
    _write(memory_dir / "MEMORY.md", "index\n")
    _write(memory_dir / "IMPORT_REVIEW.md", "review\n")
    _write(memory_dir / "REVIEW_QUEUE.md", "queue\n")
    _write(memory_dir / "knowledge" / "article.md", "derived\n")

    assert diff_archive(memory_dir, archive_dir) == ""
