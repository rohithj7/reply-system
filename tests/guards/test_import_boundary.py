"""The runtime never imports evaluation code or reads `eval/` or `docs/` (packet L719)."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "src" / "doctours_reply"
RUNTIME_MODULES = sorted(
    path for path in PACKAGE.rglob("*.py") if "evaluation" not in path.relative_to(PACKAGE).parts
)
FORBIDDEN_DIRS = {"eval", "docs"}
PRIVATE_PACKAGE = "doctours" + "_ml"
# The `eval` subcommand's dispatch, imported inside `main` only.
LAZY_ALLOWED = {
    "cli.py": frozenset({"doctours_reply.evaluation.cli", "doctours_reply.evaluation.cli.main"})
}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, owners)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def _forbidden_path(value: str) -> bool:
    parts = value.replace("\\", "/").split("/")
    return any(part in FORBIDDEN_DIRS for part in parts[:-1]) or (
        len(parts) > 1 and parts[-1] in FORBIDDEN_DIRS
    )


def violations(source: str, lazy_allowed: frozenset[str] = frozenset()) -> list[str]:
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    top_level = {id(node) for node in tree.body}
    found = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
        lazy = id(node) not in top_level and set(modules) <= lazy_allowed
        bad = [
            m
            for m in modules
            if not lazy and (m.startswith("doctours_reply.evaluation") or PRIVATE_PACKAGE in m)
        ]
        if bad:
            found.append(f"line {node.lineno}: imports {bad[0]}")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            for side in (node.left, node.right):
                if isinstance(side, ast.Constant) and side.value in FORBIDDEN_DIRS:
                    found.append(f"line {node.lineno}: joins path {side.value!r}")
        if isinstance(node, ast.Call):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value in FORBIDDEN_DIRS:
                    found.append(f"line {node.lineno}: passes path {arg.value!r}")
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and _forbidden_path(node.value)
        ):
            found.append(f"line {node.lineno}: path string {node.value!r}")
    return found


@pytest.mark.parametrize("path", RUNTIME_MODULES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_runtime_module_respects_the_boundary(path: Path) -> None:
    allowed = LAZY_ALLOWED.get(str(path.relative_to(PACKAGE)), frozenset())
    assert violations(path.read_text("utf-8"), allowed) == []


def test_lazy_allowance_does_not_cover_module_level_imports() -> None:
    source = "from doctours_reply.evaluation.cli import main\n"
    assert violations(source, LAZY_ALLOWED["cli.py"]) != []


def test_run_command_never_loads_evaluation(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    source.write_text("[]")
    probe = (
        "import sys\n"
        "from doctours_reply.cli import main\n"
        f"assert main(['run', '--input', {str(source)!r}, '--output', '-']) == 0\n"
        "loaded = [m for m in sys.modules if m.startswith('doctours_reply.evaluation')]\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr


def test_checker_flags_planted_violations() -> None:
    source = (
        '"""Docstrings may mention eval/ and docs/."""\n'
        "from doctours_reply.evaluation import scorer\n"
        "from doctours_reply import evaluation\n"
        f"import {PRIVATE_PACKAGE}.export\n"
        'CASES = ROOT / "eval"\n'
        'PACKET = Path("docs")\n'
        'EXPECTED = "eval/official/expected_replies.json"\n'
    )
    assert len(violations(source)) == 6
