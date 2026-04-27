#!/usr/bin/env python3
"""Create, list, and diff read-only memory archives."""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import difflib
import filecmp
import shutil
import sys
from pathlib import Path

INCLUDED_SUFFIXES: tuple[str, ...] = (".md", ".json", ".jsonl")
DERIVED_NAMES: frozenset[str] = frozenset(
    {"IMPORT_REVIEW.md", "REVIEW_QUEUE.md"},
)


@dataclasses.dataclass(frozen=True)
class ArchiveInfo:
    """Summary of one memory archive directory."""

    archive_id: str
    path: Path
    file_count: int
    total_bytes: int


def _is_under_symlink(path: Path, base: Path) -> bool:
    relative: Path = path.relative_to(base)
    current: Path = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _is_derived(path: Path, memory_dir: Path) -> bool:
    relative: Path = path.relative_to(memory_dir)
    if path.name in DERIVED_NAMES:
        return True
    return bool(relative.parts and relative.parts[0] == "knowledge")


def iter_memory_files(
    memory_dir: Path,
    include_derived: bool = False,
) -> list[Path]:
    """Return archive-eligible memory files without following symlinks."""
    files: list[Path] = []
    if not memory_dir.exists():
        return files
    for path in memory_dir.rglob("*"):
        if not path.is_file():
            continue
        if _is_under_symlink(path, memory_dir):
            continue
        if path.suffix not in INCLUDED_SUFFIXES:
            continue
        if not include_derived and _is_derived(path, memory_dir):
            continue
        files.append(path)
    return sorted(
        files,
        key=lambda item: item.relative_to(memory_dir).as_posix(),
    )


def _default_archive_id() -> str:
    return datetime.datetime.now(
        datetime.timezone.utc,
    ).strftime("%Y-%m-%dT%H%M%SZ")


def create_archive(
    memory_dir: Path,
    archive_root: Path,
    archive_id: str | None = None,
    include_derived: bool = False,
) -> Path:
    """Copy eligible memory files into a timestamped archive directory."""
    selected_id: str = archive_id or _default_archive_id()
    archive_dir: Path = archive_root / selected_id
    if archive_dir.exists():
        raise FileExistsError(f"Archive already exists: {archive_dir}")
    archive_dir.mkdir(parents=True)
    for source in iter_memory_files(memory_dir, include_derived):
        relative: Path = source.relative_to(memory_dir)
        target: Path = archive_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return archive_dir


def list_archives(archive_root: Path) -> list[ArchiveInfo]:
    """Return archive summaries sorted by archive ID."""
    if not archive_root.exists():
        return []
    archives: list[ArchiveInfo] = []
    for path in sorted(archive_root.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or path.is_symlink():
            continue
        files: list[Path] = [
            child for child in path.rglob("*")
            if child.is_file() and not _is_under_symlink(child, path)
        ]
        total_bytes: int = sum(child.stat().st_size for child in files)
        archives.append(
            ArchiveInfo(
                archive_id=path.name,
                path=path,
                file_count=len(files),
                total_bytes=total_bytes,
            ),
        )
    return archives


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _relative_file_set(left: Path, right: Path) -> list[Path]:
    files: set[Path] = set()
    for root in (left, right):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if _is_under_symlink(path, root):
                continue
            if path.suffix not in INCLUDED_SUFFIXES:
                continue
            if _is_derived(path, root):
                continue
            files.add(path.relative_to(root))
    return sorted(files, key=lambda item: item.as_posix())


def diff_archive(memory_dir: Path, archive_dir: Path) -> str:
    """Return a unified diff from archive contents to current memory."""
    chunks: list[str] = []
    for relative in _relative_file_set(archive_dir, memory_dir):
        archived: Path = archive_dir / relative
        current: Path = memory_dir / relative
        if archived.exists() and current.exists() and filecmp.cmp(
            archived,
            current,
            shallow=False,
        ):
            continue
        diff_lines: list[str] = list(
            difflib.unified_diff(
                _read_lines(archived),
                _read_lines(current),
                fromfile=f"archive/{relative.as_posix()}",
                tofile=f"current/{relative.as_posix()}",
            ),
        )
        chunks.extend(diff_lines)
    return "".join(chunks)


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--memory-dir", type=Path, default=Path("memory"))
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path(".claude/memory-archives"),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Read-only memory archive operations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    _add_common_paths(create_parser)
    create_parser.add_argument("--archive-id")
    create_parser.add_argument("--include-derived", action="store_true")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path(".claude/memory-archives"),
    )

    diff_parser = subparsers.add_parser("diff")
    diff_parser.add_argument("archive_id")
    _add_common_paths(diff_parser)
    return parser.parse_args(argv)


def _run_create(args: argparse.Namespace) -> int:
    try:
        archive_dir: Path = create_archive(
            memory_dir=args.memory_dir,
            archive_root=args.archive_root,
            archive_id=args.archive_id,
            include_derived=args.include_derived,
        )
    except (FileExistsError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Created {archive_dir}")
    return 0


def _run_list(args: argparse.Namespace) -> int:
    archives: list[ArchiveInfo] = list_archives(args.archive_root)
    if not archives:
        print(f"No memory archives found in {args.archive_root}.")
        return 0
    for archive in archives:
        print(
            f"{archive.archive_id}\t"
            f"{archive.file_count} files\t"
            f"{archive.total_bytes} bytes",
        )
    return 0


def _run_diff(args: argparse.Namespace) -> int:
    archive_dir: Path = args.archive_root / args.archive_id
    if not archive_dir.is_dir():
        print(f"error: archive not found: {archive_dir}", file=sys.stderr)
        return 2
    diff: str = diff_archive(args.memory_dir, archive_dir)
    if diff:
        print(diff, end="")
        return 1
    print("No differences.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args: argparse.Namespace = parse_args(argv)
    if args.command == "create":
        return _run_create(args)
    if args.command == "list":
        return _run_list(args)
    if args.command == "diff":
        return _run_diff(args)
    print(f"error: unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
