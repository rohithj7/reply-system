"""Resolve `fixture_id` and `policy_set_id` references from `resources/`, verifying hashes.

Fixtures live in `resources/fixtures/<fixture_id>/` and policy-set snapshots and overlays
in `resources/policy_sets/<policy_set_id>/`, each listed with file hashes in the
directory's `manifest.json`. `shipped` is the policy tree under
`src/doctours_reply/policies/` at the checked-out commit. Evaluation labels and answers
live under `eval/`, which the runtime never reads.
"""

import hashlib
import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from doctours_reply.tools.data import ToolData

PACKAGE_DIR = Path(__file__).resolve().parents[1]
RESOURCES_DIR = PACKAGE_DIR.parents[1] / "resources"
SHIPPED_POLICIES_DIR = PACKAGE_DIR / "policies"
SHIPPED = "shipped"


class RefError(Exception):
    """A fixture or policy-set reference cannot be resolved."""


class UnknownRefError(RefError):
    """The ID, or a file it lists, does not exist."""


class HashMismatchError(RefError):
    """A file's bytes do not match the sha256 recorded in its manifest."""


class StaleOverlayError(RefError):
    """An overlay replaces a module whose base version is not the one it declares."""


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class FixtureFile(_Manifest):
    role: Literal["constants", "tool_data"]
    path: str
    sha256: str


class FixtureEntry(_Manifest):
    fixture_id: str
    derived_from: Literal["packet", "hand-authored"]
    files: list[FixtureFile]

    @model_validator(mode="after")
    def _one_file_per_role(self) -> Self:
        if sorted(f.role for f in self.files) != ["constants", "tool_data"]:
            raise ValueError("a fixture lists exactly one constants and one tool_data file")
        return self


class FixtureManifest(_Manifest):
    schema_version: Literal[1]
    fixtures: list[FixtureEntry]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [f.fixture_id for f in self.fixtures]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate fixture_id")
        return self


class PolicyModuleEntry(_Manifest):
    module_id: str
    path: str
    sha256: str
    replaces_version: str | None = None


class PolicySetEntry(_Manifest):
    policy_set_id: str
    kind: Literal["snapshot", "overlay"]
    base: str | None = None
    modules: list[PolicyModuleEntry]

    @model_validator(mode="after")
    def _overlay_fields(self) -> Self:
        overlay = self.kind == "overlay"
        if overlay != (self.base is not None):
            raise ValueError("an overlay needs a base and a snapshot has none")
        if any(overlay != (m.replaces_version is not None) for m in self.modules):
            raise ValueError("overlay modules need replaces_version and snapshot modules have none")
        return self


class PolicySetManifest(_Manifest):
    schema_version: Literal[1]
    policy_sets: list[PolicySetEntry]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [s.policy_set_id for s in self.policy_sets]
        if len(ids) != len(set(ids)) or SHIPPED in ids:
            raise ValueError(f"duplicate or reserved policy_set_id ({SHIPPED!r} is reserved)")
        return self


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    constants: Mapping[str, Any]
    tool_data: ToolData
    resolved_hash: str


@dataclass(frozen=True)
class PolicyModule:
    module_id: str
    version: str
    sha256: str
    text: str


@dataclass(frozen=True)
class PolicySet:
    policy_set_id: str
    modules: Mapping[str, PolicyModule]
    resolved_hash: str


def resolve_fixture(fixture_id: str, resources_dir: Path = RESOURCES_DIR) -> Fixture:
    base = resources_dir / "fixtures"
    manifest = _load_manifest(FixtureManifest, base / "manifest.json")
    entry = next((f for f in manifest.fixtures if f.fixture_id == fixture_id), None)
    if entry is None:
        raise UnknownRefError(f"unknown fixture_id {fixture_id!r}")
    files = {f.role: _read_verified(base, f.path, f.sha256) for f in entry.files}
    try:
        tool_data = ToolData.model_validate_json(files["tool_data"])
        constants = json.loads(files["constants"])
    except (ValidationError, ValueError) as exc:
        raise RefError(f"fixture {fixture_id!r} is malformed: {exc}") from exc
    digest = hashlib.sha256()
    for f in sorted(entry.files, key=lambda f: f.role):
        digest.update(f"{f.role}:{f.sha256}\n".encode())
    return Fixture(fixture_id, constants, tool_data, digest.hexdigest())


def resolve_policy_set(
    policy_set_id: str,
    resources_dir: Path = RESOURCES_DIR,
    shipped_dir: Path = SHIPPED_POLICIES_DIR,
) -> PolicySet:
    modules = _policy_modules(policy_set_id, resources_dir, shipped_dir, allow_overlay=True)
    digest = hashlib.sha256()
    for module_id in sorted(modules):
        module = modules[module_id]
        digest.update(f"{module_id}@{module.version}:{module.sha256}\n".encode())
    return PolicySet(policy_set_id, modules, digest.hexdigest())


def _policy_modules(
    policy_set_id: str, resources_dir: Path, shipped_dir: Path, *, allow_overlay: bool
) -> dict[str, PolicyModule]:
    if policy_set_id == SHIPPED:
        return _shipped_modules(shipped_dir)
    base = resources_dir / "policy_sets"
    manifest = _load_manifest(PolicySetManifest, base / "manifest.json")
    entry = next((s for s in manifest.policy_sets if s.policy_set_id == policy_set_id), None)
    if entry is None:
        raise UnknownRefError(f"unknown policy_set_id {policy_set_id!r}")
    own: dict[str, PolicyModule] = {}
    for m in entry.modules:
        module = _parse_module(_read_verified(base, m.path, m.sha256), m.path)
        if module.module_id != m.module_id:
            raise RefError(f"{m.path}: front matter id {module.module_id!r} != {m.module_id!r}")
        own[m.module_id] = module
    if entry.kind == "snapshot":
        return own
    if not allow_overlay or entry.base is None:
        raise RefError(f"overlay {policy_set_id!r} must be based on {SHIPPED!r} or a snapshot")
    modules = _policy_modules(entry.base, resources_dir, shipped_dir, allow_overlay=False)
    for m in entry.modules:
        current = modules.get(m.module_id)
        if current is None or current.version != m.replaces_version:
            found = "missing" if current is None else current.version
            raise StaleOverlayError(
                f"overlay {policy_set_id!r} replaces {m.module_id}@{m.replaces_version}, "
                f"but base {entry.base!r} has {found}"
            )
    return modules | own


def _shipped_modules(shipped_dir: Path) -> dict[str, PolicyModule]:
    modules: dict[str, PolicyModule] = {}
    for path in sorted(shipped_dir.rglob("*.md")) if shipped_dir.is_dir() else []:
        module = _parse_module(path.read_bytes(), str(path))
        if module.module_id in modules:
            raise RefError(f"duplicate shipped policy id {module.module_id!r}")
        modules[module.module_id] = module
    return modules


def _parse_module(data: bytes, where: str) -> PolicyModule:
    text = data.decode("utf-8")
    end = text.find("\n+++\n", 4)
    if not text.startswith("+++\n") or end == -1:
        raise RefError(f"{where}: missing +++ front matter")
    try:
        meta = tomllib.loads(text[4:end])
    except tomllib.TOMLDecodeError as exc:
        raise RefError(f"{where}: invalid front matter: {exc}") from exc
    module_id, version = meta.get("id"), meta.get("version")
    if not isinstance(module_id, str) or not isinstance(version, str):
        raise RefError(f"{where}: front matter needs string id and version")
    return PolicyModule(module_id, version, hashlib.sha256(data).hexdigest(), text)


def _load_manifest[M: _Manifest](model: type[M], path: Path) -> M:
    try:
        return model.model_validate_json(path.read_bytes())
    except FileNotFoundError as exc:
        raise UnknownRefError(f"missing manifest {path}") from exc
    except ValidationError as exc:
        raise RefError(f"invalid manifest {path}: {exc}") from exc


def _read_verified(base: Path, relative: str, sha256: str) -> bytes:
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise RefError(f"{relative!r} points outside {base}")
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise UnknownRefError(f"missing file {relative!r} under {base}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        raise HashMismatchError(f"{relative}: manifest sha256 {sha256}, actual {actual}")
    return data
