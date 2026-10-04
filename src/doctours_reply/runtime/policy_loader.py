"""Versioned runtime policies: front matter, the skill catalog, activation and rendering.

Every module in a policy set carries TOML front matter (`refs.py` checks `id` and
`version`). `core` modules load on every step; a `context` module loads when its `when`
matches a fixture constant; a `skill` module loads when the controller picks it or a
loaded module requires it; `writer` modules go to the writer only. The tools a step
may call are the union of its loaded modules' `allowed_tools`.
"""

import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from doctours_reply.runtime.evidence import Fact
from doctours_reply.runtime.refs import PolicyModule, PolicySet, RefError
from doctours_reply.tools.registry import TOOLS

Layer = Literal["core", "skill", "context", "writer"]
LAYER_ORDER: dict[Layer, int] = {"core": 0, "context": 1, "skill": 2, "writer": 3}
MEMORY_TOOL = "updateWorkingMemory"
ANY_VALUE = "*"
_UNSET = {"", "null"}


class _Meta(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class FactSpec(_Meta):
    name: str
    label: str
    value: str = Field(pattern=r"^\d+(?:\.\d+)?$")
    unit: str
    cues: list[str] = Field(min_length=1)
    source: str


class When(_Meta):
    constant: str
    values: list[str] = Field(min_length=1)

    def matches(self, constants: Mapping[str, Any]) -> bool:
        raw = constants.get(self.constant)
        value = "null" if raw is None or str(raw).strip() in _UNSET else str(raw)
        return value in self.values or (ANY_VALUE in self.values and value != "null")


class PolicyMeta(_Meta):
    id: str = Field(pattern=r"^[a-z]+(?:[._][a-z]+)*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    layer: Layer
    summary: str
    activates_on: list[str] = []
    requires: list[str] = []
    allowed_tools: list[str] = []
    static_links: list[str] = []
    forbidden_patterns: list[str] = []
    facts: list[FactSpec] = []
    sources: list[str] = Field(min_length=1)
    when: When | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        unknown = set(self.allowed_tools) - set(TOOLS)
        if unknown:
            raise ValueError(f"unknown tools {sorted(unknown)}")
        if MEMORY_TOOL in self.allowed_tools:
            raise ValueError(f"{MEMORY_TOOL} runs only as the memory commit")
        if (self.layer == "context") != (self.when is not None):
            raise ValueError("context modules, and only they, have `when`")
        if any(not link.startswith("https://") for link in self.static_links):
            raise ValueError("static links are https URLs")
        if any(not re.match(r"^(packet|assignment):L\d+(-L\d+)?$", s) for s in self.sources):
            raise ValueError("sources look like packet:L12-L34 or assignment:L7")
        for pattern in self.forbidden_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"forbidden pattern {pattern!r}: {exc}") from exc
        return self


@dataclass(frozen=True)
class Policy:
    meta: PolicyMeta
    body: str
    sha256: str

    @property
    def id(self) -> str:
        return self.meta.id

    @property
    def version(self) -> str:
        return self.meta.version


def parse_policy(module: PolicyModule) -> Policy:
    end = module.text.find("\n+++\n", 4)
    try:
        meta = PolicyMeta.model_validate(tomllib.loads(module.text[4:end]))
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        raise RefError(f"policy {module.module_id!r}: invalid front matter: {exc}") from exc
    return Policy(meta, module.text[end + len("\n+++\n") :].strip(), module.sha256)


@dataclass(frozen=True)
class LoadedPolicies:
    policies: tuple[Policy, ...]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.policies)

    @cached_property
    def allowed_tools(self) -> frozenset[str]:
        return frozenset(t for p in self.policies for t in p.meta.allowed_tools)

    @property
    def static_links(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(link for p in self.policies for link in p.meta.static_links))

    @property
    def facts(self) -> tuple[Fact, ...]:
        return tuple(
            Fact(
                "policy",
                spec.name,
                spec.label,
                None,
                None,
                spec.name,
                Decimal(spec.value),
                spec.unit,
                f"{p.id}@{p.version} {spec.source}",
                tuple(spec.cues),
            )
            for p in self.policies
            for spec in p.meta.facts
        )

    @property
    def forbidden_patterns(self) -> tuple[tuple[str, re.Pattern[str]], ...]:
        return tuple(
            (f"{p.id}@{p.version}", re.compile(pattern, re.IGNORECASE))
            for p in self.policies
            for pattern in p.meta.forbidden_patterns
        )

    def render(self) -> str:
        return "\n\n".join(f"[policy {p.id} v{p.version}]\n{p.body}" for p in self.policies)

    def record(self) -> list[dict[str, str]]:
        return [{"id": p.id, "version": p.version, "sha256": p.sha256} for p in self.policies]


class PolicyCatalog:
    """The parsed modules of one policy set."""

    def __init__(self, policy_set: PolicySet) -> None:
        self.policy_set_id = policy_set.policy_set_id
        self.policies = {mid: parse_policy(m) for mid, m in policy_set.modules.items()}
        for policy in self.policies.values():
            missing = set(policy.meta.requires) - set(self.policies)
            if missing:
                raise RefError(f"policy {policy.id!r} requires unknown {sorted(missing)}")

    @property
    def skill_ids(self) -> tuple[str, ...]:
        return tuple(sorted(i for i, p in self.policies.items() if p.meta.layer == "skill"))

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "id": i,
                "summary": self.policies[i].meta.summary,
                "use_for": self.policies[i].meta.activates_on,
            }
            for i in self.skill_ids
        ]

    def load(self, skills: Iterable[str], constants: Mapping[str, Any]) -> LoadedPolicies:
        """Core, matching context modules and the given skills, closed over `requires`."""
        wanted = [
            i
            for i, p in self.policies.items()
            if p.meta.layer == "core"
            or (p.meta.layer == "context" and p.meta.when and p.meta.when.matches(constants))
        ]
        wanted += skills
        return LoadedPolicies(self._ordered(self._closure(wanted)))

    def writer(self) -> LoadedPolicies:
        return LoadedPolicies(
            self._ordered(i for i, p in self.policies.items() if p.meta.layer == "writer")
        )

    def _closure(self, ids: Iterable[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(ids)
        while stack:
            current = stack.pop()
            if current not in seen:
                seen.add(current)
                stack.extend(self.policies[current].meta.requires)
        return seen

    def _ordered(self, ids: Iterable[str]) -> tuple[Policy, ...]:
        policies = (self.policies[i] for i in ids)
        return tuple(sorted(policies, key=lambda p: (LAYER_ORDER[p.meta.layer], p.id)))
