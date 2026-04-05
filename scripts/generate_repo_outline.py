#!/usr/bin/env python3
"""
Generate a concise repository outline using tree-sitter AST parsing.

This script extracts function/class signatures WITHOUT implementation bodies,
producing a token-efficient codebase map for AI context.

Usage:
    python scripts/generate_repo_outline.py                    # Full repo
    python scripts/generate_repo_outline.py app/services/      # Specific dir
    python scripts/generate_repo_outline.py --max-depth 2      # Limit nesting
    python scripts/generate_repo_outline.py --output outline.md # Save to file

Exit codes:
    0 = Success
    1 = Error (missing dependencies, invalid path)
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Color codes for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
NC = "\033[0m"  # No Color


def check_dependencies() -> bool:
    """Check if tree-sitter dependencies are installed."""
    try:
        import tree_sitter_python  # noqa: F401
        from tree_sitter import Language, Parser  # noqa: F401

        return True
    except ImportError:
        print(f"{YELLOW}⚠️  tree-sitter not installed. Run:{NC}")
        print("   pip install tree-sitter tree-sitter-python")
        return False


def get_parser():
    """Create a tree-sitter parser for Python."""
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    PY_LANGUAGE = Language(tspython.language())
    parser = Parser(PY_LANGUAGE)
    return parser


def extract_signature(node, source: bytes) -> str:
    """Extract function/method signature without body."""
    # Get the function name
    name_node = node.child_by_field_name("name")
    name = name_node.text.decode() if name_node else "?"

    # Get parameters
    params_node = node.child_by_field_name("parameters")
    params = params_node.text.decode() if params_node else "()"

    # Get return type annotation if present
    return_type = node.child_by_field_name("return_type")
    return_annotation = ""
    if return_type:
        return_annotation = f" -> {return_type.text.decode()}"

    # Check for async
    is_async = any(
        child.type == "async" or source[child.start_byte : child.end_byte] == b"async"
        for child in node.children
        if child.end_byte <= (name_node.start_byte if name_node else 0)
    )

    prefix = "async def" if is_async else "def"
    return f"{prefix} {name}{params}{return_annotation}"


def extract_class_signature(node, source: bytes) -> str:
    """Extract class signature with bases."""
    name_node = node.child_by_field_name("name")
    name = name_node.text.decode() if name_node else "?"

    # Get base classes if present
    for child in node.children:
        if child.type == "argument_list":
            bases_text = child.text.decode()
            return f"class {name}{bases_text}"

    return f"class {name}"


def _handle_decorated(child, source: bytes, indent: str, depth: int, max_depth: int) -> list[str]:
    """Handle decorated functions/classes."""
    results = []
    decorators = []
    definition = None

    for deco_child in child.children:
        if deco_child.type == "decorator":
            decorators.append(f"{indent}{deco_child.text.decode().strip()}")
        elif deco_child.type == "function_definition":
            definition = extract_signature(deco_child, source)
        elif deco_child.type == "class_definition":
            definition = extract_class_signature(deco_child, source) + ":"

    if definition:
        results.extend(decorators)
        results.append(f"{indent}{definition}")
        # If it's a decorated class, extract methods
        for deco_child in child.children:
            if deco_child.type == "class_definition":
                body = deco_child.child_by_field_name("body")
                if body:
                    results.extend(extract_definitions(body, source, depth + 1, max_depth))

    return results


def extract_definitions(node, source: bytes, depth: int = 0, max_depth: int = 10) -> list[str]:
    """Recursively extract function and class definitions."""
    if depth > max_depth:
        return []

    results = []
    indent = "    " * depth

    for child in node.children:
        if child.type == "function_definition":
            results.append(f"{indent}{extract_signature(child, source)}")

        elif child.type == "class_definition":
            results.append(f"{indent}{extract_class_signature(child, source)}:")
            body = child.child_by_field_name("body")
            if body:
                results.extend(extract_definitions(body, source, depth + 1, max_depth))

        elif child.type == "decorated_definition":
            results.extend(_handle_decorated(child, source, indent, depth, max_depth))

    return results


def process_file(filepath: Path, parser, max_depth: int) -> tuple[str, list[str]]:
    """Process a single Python file and return its outline."""
    try:
        source = filepath.read_bytes()
        tree = parser.parse(source)
        definitions = extract_definitions(tree.root_node, source, max_depth=max_depth)
        return str(filepath), definitions
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to process %s: %s", filepath, e)
        return str(filepath), ["# Error parsing file"]


def generate_outline(
    path: Path, max_depth: int = 10, exclude_patterns: Optional[list[str]] = None
) -> dict[str, list[str]]:
    """Generate outline for all Python files in path."""
    if exclude_patterns is None:
        exclude_patterns = [
            "__pycache__",
            ".git",
            "venv",
            ".venv",
            "_archived",
            "alembic/versions",
            ".claude/worktrees",
            "node_modules",
        ]

    parser = get_parser()
    outlines = {}

    if path.is_file():
        files = [path] if path.suffix == ".py" else []
    else:
        files = list(path.rglob("*.py"))

    # Filter excluded patterns
    filtered_files = []
    for f in files:
        skip = False
        for pattern in exclude_patterns:
            if pattern in str(f):
                skip = True
                break
        if not skip:
            filtered_files.append(f)

    for filepath in sorted(filtered_files):
        rel_path, definitions = process_file(filepath, parser, max_depth)
        if definitions:  # Only include files with definitions
            outlines[rel_path] = definitions

    return outlines


def format_output(outlines: dict[str, list[str]], base_path: Path) -> str:
    """Format outlines as markdown."""
    lines = ["# Repository Outline", ""]
    lines.append(f"Generated from: `{base_path}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    for filepath, definitions in outlines.items():
        # Make path relative if possible
        try:
            rel_path = Path(filepath).relative_to(base_path)
        except ValueError:
            rel_path = filepath

        lines.append(f"## `{rel_path}`")
        lines.append("```python")
        lines.extend(definitions)
        lines.append("```")
        lines.append("")

    # Summary stats
    total_files = len(outlines)
    total_defs = sum(len(defs) for defs in outlines.values())
    lines.append("---")
    lines.append(f"**Summary:** {total_files} files, {total_defs} definitions")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate a token-efficient repository outline using tree-sitter")
    parser.add_argument("path", nargs="?", default="app", help="Path to analyze (default: app/)")
    parser.add_argument(
        "--max-depth", type=int, default=10, help="Maximum nesting depth for class methods (default: 10)"
    )
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--compact", action="store_true", help="Compact output without markdown formatting")

    args = parser.parse_args()

    # Check dependencies
    if not check_dependencies():
        return 1

    # Resolve path
    target_path = Path(args.path)
    if not target_path.exists():
        print(f"{YELLOW}⚠️  Path not found: {target_path}{NC}")
        return 1

    print(f"{BLUE}📝 Generating repo outline for: {target_path}{NC}")

    # Generate outlines
    outlines = generate_outline(target_path, max_depth=args.max_depth)

    if not outlines:
        print(f"{YELLOW}⚠️  No Python files found{NC}")
        return 0

    # Format output
    if args.compact:
        output_lines = []
        for filepath, definitions in outlines.items():
            output_lines.append(f"# {filepath}")
            output_lines.extend(definitions)
            output_lines.append("")
        output = "\n".join(output_lines)
    else:
        output = format_output(outlines, target_path)

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"{GREEN}✅ Outline saved to: {args.output}{NC}")
    else:
        print(output)

    # Stats
    total_files = len(outlines)
    total_defs = sum(len(defs) for defs in outlines.values())
    print(f"\n{GREEN}✅ Processed {total_files} files, {total_defs} definitions{NC}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
