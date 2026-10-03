import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT = ["git", "-c", "user.name=Audit Test", "-c", "user.email=audit@example.invalid"]
GIT += ["-c", "commit.gpgsign=false"]
# Secret-shaped strings are assembled at runtime so this file never contains one.
SECRETS = {
    "AWS access key": "AKIA" + "X" * 16,
    "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "GitHub token": "ghp_" + "a1" * 18,
    "API key (sk-)": "sk-" + "b2" * 12,
    "Hugging Face token": "hf_" + "c3" * 16,
}
PRIVATE_IMPORT = "import " + "doctours" + "_ml\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run([*GIT, "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, files: dict[str, str | bytes], remove: tuple[str, ...] = ()) -> Path:
    """A temporary git repo committing `files`, then a second commit deleting `remove`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, "utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add files")
    if remove:
        _git(repo, "rm", "-q", *remove)
        _git(repo, "commit", "-q", "-m", "remove files")
    return repo


def _has(findings: list[str], prefix: str) -> bool:
    return any(finding.startswith(prefix) for finding in findings)


def test_real_repo_passes_tree_and_history(audit: ModuleType) -> None:
    assert audit.run_audit(REPO_ROOT, history=True) == []


@pytest.mark.parametrize(
    ("files", "prefix"),
    [
        ({".cursor/plans/x.plan.md": "# plan\n"}, "path: planning file"),
        ({"notes/x.plan.md": "# plan\n"}, "path: planning file"),
        ({"doctours-cursor-planning-prompt.md": "prompt\n"}, "path: planning prompt"),
        ({"weights/model.safetensors": b"\x00\x01"}, "path: model weights"),
        ({"adapter.gguf": b"\x00"}, "path: model weights"),
        ({".env": "MODEL_API_KEY=x\n"}, "path: environment file"),
        ({".gitattributes": "*.bin filter=lfs diff=lfs merge=lfs -text\n"}, "lfs:"),
        ({"src/app.py": PRIVATE_IMPORT}, "reference: private repository name"),
        ({"big.txt": "x" * (5 * 1024 * 1024 + 1)}, "size:"),
    ],
)
def test_rc_b_tracked_files_fail_the_audit(
    audit: ModuleType, tmp_path: Path, files: dict[str, str | bytes], prefix: str
) -> None:
    assert _has(audit.run_audit(_repo(tmp_path, files), history=False), prefix)


@pytest.mark.parametrize(("label", "secret"), list(SECRETS.items()))
def test_rc_b_3_secret_patterns_fail_the_audit(
    audit: ModuleType, tmp_path: Path, label: str, secret: str
) -> None:
    findings = audit.run_audit(_repo(tmp_path, {"config.py": f"KEY = '{secret}'\n"}), False)
    assert f"secret: {label} in config.py" in findings


@pytest.mark.parametrize(
    ("files", "prefix"),
    [
        ({".cursor/plans/x.plan.md": "# plan\n"}, "history path: planning file"),
        ({"docs/doctours-cursor-planning-prompt.md": "p\n"}, "history path: planning prompt"),
        ({"model.safetensors": b"\x00"}, "history path: model weights"),
        ({"config.py": f"KEY = '{SECRETS['AWS access key']}'\n"}, "history secret"),
        ({"src/app.py": PRIVATE_IMPORT}, "history reference: private repository name"),
    ],
)
def test_rc_b_files_removed_from_the_tree_still_fail_with_history(
    audit: ModuleType, tmp_path: Path, files: dict[str, str | bytes], prefix: str
) -> None:
    repo = _repo(tmp_path, {**files, "README.md": "x\n"}, remove=tuple(files))
    assert not _has(audit.run_audit(repo, history=False), prefix)
    assert _has(audit.run_audit(repo, history=True), prefix)


def test_mismatched_resource_manifest_hash_fails(audit: ModuleType, tmp_path: Path) -> None:
    manifest = (
        '{"schema_version": 1, "fixtures": [{"fixture_id": "f", "derived_from": "hand-authored",'
        ' "files": [{"role": "constants", "path": "f/constants.json", "sha256": "' + "0" * 64 + '"}'
        "]}]}"
    )
    repo = _repo(
        tmp_path,
        {"resources/fixtures/manifest.json": manifest, "resources/fixtures/f/constants.json": "{}"},
    )
    assert "manifest: sha256 mismatch for resources/fixtures/f/constants.json" in audit.run_audit(
        repo, history=False
    )


def test_unlisted_resource_file_and_banned_export_text_fail(
    audit: ModuleType, tmp_path: Path
) -> None:
    repo = _repo(
        tmp_path,
        {
            "resources/fixtures/manifest.json": '{"schema_version": 1, "fixtures": []}',
            "resources/fixtures/extra/tool_data.json": '{"note": "<think>hidden</think>"}',
        },
    )
    findings = audit.run_audit(repo, history=False)
    assert _has(findings, "manifest: resources/fixtures/extra/tool_data.json is not listed")
    assert _has(findings, "export: banned substring '<think>'")


def test_rc_b_4_ci_runs_the_audit_over_full_history() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    assert "fetch-depth: 0" in workflow
    steps = [
        "uv sync --locked",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src",
        'uv run pytest -m "not live"',
        "uv run python scripts/audit_submission.py --history",
    ]
    positions = [workflow.find(step) for step in steps]
    assert -1 not in positions, dict(zip(steps, positions, strict=True))
    assert positions == sorted(positions)
