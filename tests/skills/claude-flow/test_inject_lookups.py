"""Tests for inject_lookups.py — each detector graceful-skips when inapplicable."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).parents[3] / "skills" / "claude-flow" / "scripts" / "inject_lookups.py"


def run(args, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
        capture_output=True, text=True, cwd=cwd, timeout=30,
    )


def test_output_shape():
    with tempfile.TemporaryDirectory() as d:
        result = run(["--scope", "plan", "--files", "foo.py"], cwd=d)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "lookups" in data
        assert "skipped_detectors" in data
        assert "scope" in data
        assert isinstance(data["lookups"], dict)
        assert isinstance(data["skipped_detectors"], list)


def test_graceful_skip_on_empty_project():
    with tempfile.TemporaryDirectory() as d:
        result = run(["--scope", "plan", "--files", "random.py"], cwd=d)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["scope"] == "plan"
        # Both plan detectors should skip gracefully on empty project
        assert len(data["skipped_detectors"]) == len(data["lookups"]) + 2


def test_sqlalchemy_columns_detects_real_cols():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        models_dir = root / "app" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "client.py").write_text(
            "from sqlalchemy import Column, Integer, String\n"
            "class Client:\n"
            "    id = Column(Integer)\n"
            "    email = Column(String)\n"
            "    is_primary_contact = Column(Integer)\n"
        )
        result = run(
            ["--scope", "step", "--files", "app/models/client.py"],
            cwd=str(root),
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "sqlalchemy_columns" in data["lookups"]
        output = data["lookups"]["sqlalchemy_columns"]
        assert "is_primary_contact" in output
        assert "email" in output


def test_css_classes_extracted():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "static.css").write_text(
            ".tl-group { color: red; }\n"
            ".tl-group-header, .foo-bar { display: flex; }\n"
            ".nested:hover { opacity: 0.5; }\n"
        )
        result = run(
            ["--scope", "step", "--files", "static.css"],
            cwd=str(root),
        )
        data = json.loads(result.stdout)
        assert "css_classes" in data["lookups"]
        output = data["lookups"]["css_classes"]
        assert "tl-group" in output
        assert "foo-bar" in output
        assert "nested" in output


def test_react_components_extracted():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "App.tsx").write_text(
            "export function Header() { return null }\n"
            "export const Button = () => null\n"
            "export default function App() { return null }\n"
        )
        result = run(
            ["--scope", "step", "--files", "App.tsx"],
            cwd=str(root),
        )
        data = json.loads(result.stdout)
        assert "react_components" in data["lookups"]
        output = data["lookups"]["react_components"]
        assert "Header" in output
        assert "Button" in output
        assert "App" in output


def test_scope_plan_vs_step():
    """Plan scope runs plan detectors; step scope runs step detectors."""
    with tempfile.TemporaryDirectory() as d:
        plan_result = run(["--scope", "plan", "--files", "foo.py"], cwd=d)
        step_result = run(["--scope", "step", "--files", "foo.py"], cwd=d)
        plan_data = json.loads(plan_result.stdout)
        step_data = json.loads(step_result.stdout)
        assert plan_data["scope"] == "plan"
        assert step_data["scope"] == "step"
        # Different detector sets produce different skip lists
        assert plan_data["skipped_detectors"] != step_data["skipped_detectors"]


def test_exit_code_always_zero_on_normal_paths():
    with tempfile.TemporaryDirectory() as d:
        result = run(["--scope", "plan", "--files", "nothing.xyz"], cwd=d)
        assert result.returncode == 0
