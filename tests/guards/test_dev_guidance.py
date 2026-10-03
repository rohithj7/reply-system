"""Development rules and skills are well formed and only cite checks that CI runs."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES = ["reply-contract", "tools-and-fixtures", "policies-and-eval"]
SKILLS = ["phase-gate", "policy-change", "regression-eval"]
CI = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")


def _front_matter(path: Path) -> dict[str, str]:
    text = path.read_text("utf-8")
    assert text.startswith("---\n"), path
    block = text[4 : text.index("\n---\n", 4)]
    return {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in block.splitlines())}


def _uv_commands(path: Path) -> list[str]:
    return re.findall(r"^\s*(uv run .+?)\s*$", path.read_text("utf-8"), re.MULTILINE)


@pytest.mark.parametrize("rule", RULES)
def test_rules_have_scoped_front_matter(rule: str) -> None:
    meta = _front_matter(REPO_ROOT / ".cursor" / "rules" / f"{rule}.mdc")
    assert set(meta) == {"description", "globs", "alwaysApply"}
    assert meta["description"] and meta["globs"] and meta["alwaysApply"] == "false"


@pytest.mark.parametrize("skill", SKILLS)
def test_skills_are_named_after_their_folder(skill: str) -> None:
    meta = _front_matter(REPO_ROOT / ".agents" / "skills" / skill / "SKILL.md")
    assert meta["name"] == skill and meta["description"]
    assert (meta.get("disable-model-invocation") == "true") == (skill == "phase-gate")


@pytest.mark.parametrize(
    "path",
    [REPO_ROOT / "AGENTS.md", *(REPO_ROOT / ".agents" / "skills" / s / "SKILL.md" for s in SKILLS)],
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_cited_uv_checks_are_ci_steps(path: Path) -> None:
    commands = [c for c in _uv_commands(path) if "extract_packet.py --check" not in c]
    assert commands
    assert [c for c in commands if c not in CI] == []
