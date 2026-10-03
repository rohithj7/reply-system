import hashlib
import json
import shutil
from pathlib import Path

import pytest

from doctours_reply.runtime.refs import (
    HashMismatchError,
    RefError,
    StaleOverlayError,
    UnknownRefError,
    resolve_fixture,
    resolve_policy_set,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _module(path: Path, module_id: str, version: str, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'+++\nid = "{module_id}"\nversion = "{version}"\n+++\n{body}\n', "utf-8")
    return path


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), "utf-8")


@pytest.fixture
def copied_fixture(tmp_path: Path) -> Path:
    """A temporary resources dir holding a copy of the packet fixture as `copy`."""
    fixtures = tmp_path / "resources" / "fixtures"
    shutil.copytree(REPO_ROOT / "resources" / "fixtures" / "packet", fixtures / "copy")
    files = [
        {"role": role, "path": f"copy/{role}.json", "sha256": _sha(fixtures / f"copy/{role}.json")}
        for role in ("constants", "tool_data")
    ]
    _write_json(
        fixtures / "manifest.json",
        {
            "schema_version": 1,
            "fixtures": [{"fixture_id": "copy", "derived_from": "packet", "files": files}],
        },
    )
    return tmp_path / "resources"


def _policy_sets(resources: Path, entries: list[dict[str, object]]) -> None:
    _write_json(
        resources / "policy_sets" / "manifest.json", {"schema_version": 1, "policy_sets": entries}
    )


def test_packet_fixture_resolves_from_shipped_resources() -> None:
    fixture = resolve_fixture("packet")
    assert fixture.constants["TIER"] == "pre_deposit"
    assert [c["slug"] for c in fixture.tool_data.clinics] == ["heva", "dr-hakan"]


def test_shipped_policy_set_resolves_deterministically() -> None:
    first, second = resolve_policy_set("shipped"), resolve_policy_set("shipped")
    assert first.resolved_hash == second.resolved_hash
    assert first.modules == second.modules


def test_unknown_ids_are_typed_errors() -> None:
    with pytest.raises(UnknownRefError):
        resolve_fixture("no-such-fixture")
    with pytest.raises(UnknownRefError):
        resolve_policy_set("no-such-set")


def test_rc_r_2_one_changed_byte_in_a_fixture_copy_is_a_hash_mismatch(
    copied_fixture: Path,
) -> None:
    assert resolve_fixture("copy", copied_fixture).constants == resolve_fixture("packet").constants
    path = copied_fixture / "fixtures" / "copy" / "tool_data.json"
    data = bytearray(path.read_bytes())
    data[data.index(b"3000")] = ord("4")
    path.write_bytes(bytes(data))
    with pytest.raises(HashMismatchError):
        resolve_fixture("copy", copied_fixture)


def test_missing_fixture_file_and_escaping_paths_are_rejected(copied_fixture: Path) -> None:
    manifest_path = copied_fixture / "fixtures" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["fixtures"][0]["files"][0]["path"] = "../../outside.json"
    _write_json(manifest_path, manifest)
    with pytest.raises(RefError):
        resolve_fixture("copy", copied_fixture)
    (copied_fixture / "fixtures" / "copy" / "constants.json").unlink()
    manifest["fixtures"][0]["files"][0]["path"] = "copy/constants.json"
    _write_json(manifest_path, manifest)
    with pytest.raises(UnknownRefError):
        resolve_fixture("copy", copied_fixture)


def test_rc_r_3_overlay_resolves_until_the_base_module_version_is_bumped(tmp_path: Path) -> None:
    resources, shipped = tmp_path / "resources", tmp_path / "policies"
    base = _module(shipped / "payments" / "fees.md", "payments.fees", "1.0.0", "Fee is $25.")
    _module(shipped / "core" / "voice.md", "core.voice", "1.0.0", "Be brief.")
    overlay = _module(
        resources / "policy_sets" / "fee-change" / "fees.md", "payments.fees", "1.0.1", "Fee $40."
    )
    _policy_sets(
        resources,
        [
            {
                "policy_set_id": "fee-change",
                "kind": "overlay",
                "base": "shipped",
                "modules": [
                    {
                        "module_id": "payments.fees",
                        "path": "fee-change/fees.md",
                        "sha256": _sha(overlay),
                        "replaces_version": "1.0.0",
                    }
                ],
            }
        ],
    )
    resolved = resolve_policy_set("fee-change", resources, shipped)
    assert resolved.modules["payments.fees"].text.endswith("Fee $40.\n")
    assert resolved.modules["core.voice"].version == "1.0.0"
    assert resolved.resolved_hash != resolve_policy_set("shipped", resources, shipped).resolved_hash

    base.write_text(base.read_text("utf-8").replace('"1.0.0"', '"1.1.0"'), "utf-8")
    with pytest.raises(StaleOverlayError):
        resolve_policy_set("fee-change", resources, shipped)


def test_overlay_of_a_module_missing_from_the_base_is_stale(tmp_path: Path) -> None:
    resources, shipped = tmp_path / "resources", tmp_path / "policies"
    overlay = _module(resources / "policy_sets" / "o" / "x.md", "x.new", "1.0.0", "New.")
    _policy_sets(
        resources,
        [
            {
                "policy_set_id": "o",
                "kind": "overlay",
                "base": "shipped",
                "modules": [
                    {
                        "module_id": "x.new",
                        "path": "o/x.md",
                        "sha256": _sha(overlay),
                        "replaces_version": "1.0.0",
                    }
                ],
            }
        ],
    )
    with pytest.raises(StaleOverlayError):
        resolve_policy_set("o", resources, shipped)


def test_snapshot_modules_are_hash_checked(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    module = _module(resources / "policy_sets" / "snap" / "a.md", "core.a", "2.0.0", "Text.")
    entry = {"module_id": "core.a", "path": "snap/a.md", "sha256": _sha(module)}
    _policy_sets(resources, [{"policy_set_id": "snap", "kind": "snapshot", "modules": [entry]}])
    assert resolve_policy_set("snap", resources).modules["core.a"].version == "2.0.0"
    module.write_text(module.read_text("utf-8") + " ", "utf-8")
    with pytest.raises(HashMismatchError):
        resolve_policy_set("snap", resources)
