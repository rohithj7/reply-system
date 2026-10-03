"""RC-R-1: every evaluation case and dataset row names a fixture and policy set that resolve."""

import json
import shutil
from pathlib import Path

from doctours_reply.runtime.refs import (
    RESOURCES_DIR,
    SHIPPED_POLICIES_DIR,
    RefError,
    resolve_fixture,
    resolve_policy_set,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_FILES = sorted((REPO_ROOT / "eval").rglob("*.jsonl")) + sorted(
    (REPO_ROOT / "datasets").glob("*.jsonl")
)


def unresolved_refs(
    path: Path, resources_dir: Path = RESOURCES_DIR, shipped_dir: Path = SHIPPED_POLICIES_DIR
) -> list[str]:
    problems = []
    for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        fixture_id, policy_set_id = row.get("fixture_id"), row.get("policy_set_id")
        if not isinstance(fixture_id, str) or not isinstance(policy_set_id, str):
            problems.append(f"{path.name}:{number}: needs fixture_id and policy_set_id")
            continue
        try:
            resolve_fixture(fixture_id, resources_dir)
            resolve_policy_set(policy_set_id, resources_dir, shipped_dir)
        except RefError as exc:
            problems.append(f"{path.name}:{number}: {exc}")
    return problems


def test_rc_r_1_committed_case_references_resolve() -> None:
    assert [problem for path in CASE_FILES for problem in unresolved_refs(path)] == []


def test_unresolvable_rows_are_reported(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    shutil.copytree(RESOURCES_DIR, resources)
    cases = tmp_path / "cases.jsonl"
    rows = [
        {"case_id": "ok", "fixture_id": "packet", "policy_set_id": "shipped"},
        {"case_id": "no-policy", "fixture_id": "packet"},
        {"case_id": "bad-fixture", "fixture_id": "nope", "policy_set_id": "shipped"},
        {"case_id": "bad-set", "fixture_id": "packet", "policy_set_id": "nope"},
    ]
    cases.write_text("\n".join(json.dumps(row) for row in rows) + "\n", "utf-8")
    problems = unresolved_refs(cases, resources, tmp_path / "policies")
    assert [problem.split(":")[1] for problem in problems] == ["2", "3", "4"]
