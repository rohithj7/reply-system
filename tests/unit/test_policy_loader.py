"""Runtime policy modules: front matter, activation, dependency closure, facts and phrases."""

from decimal import Decimal
from typing import Any

import pytest

from doctours_reply.runtime.policy_loader import PolicyCatalog, When, parse_policy
from doctours_reply.runtime.refs import PolicyModule, RefError, resolve_fixture, resolve_policy_set
from doctours_reply.runtime.validate import check_policy_phrases

SHIPPED = PolicyCatalog(resolve_policy_set("shipped"))
CONSTANTS = resolve_fixture("packet").constants


def _module(**fields: Any) -> PolicyModule:
    meta = {
        "id": "demo.module",
        "version": "1.0.0",
        "layer": "skill",
        "summary": "Demo",
        "sources": ["packet:L1-L2"],
        **fields,
    }
    lines = [f"{key} = {_toml(value)}" for key, value in meta.items()]
    text = "+++\n" + "\n".join(lines) + "\n+++\nBody.\n"
    return PolicyModule("demo.module", "1.0.0", "0" * 64, text)


def _toml(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + " }"
    return '"' + str(value).replace("\\", "\\\\") + '"'


def test_every_shipped_module_parses_with_sources() -> None:
    layers = {p.meta.layer for p in SHIPPED.policies.values()}
    assert layers == {"core", "context", "skill", "writer"}
    assert all(p.meta.sources and p.body for p in SHIPPED.policies.values())


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"allowed_tools": ["bookFlight"]}, "unknown tools"),
        ({"allowed_tools": ["updateWorkingMemory"]}, "runs only as the memory commit"),
        ({"layer": "context"}, "have `when`"),
        ({"when": {"constant": "PROMO_OFFER", "values": ["*"]}}, "have `when`"),
        ({"static_links": ["http://www.doctours.com/x"]}, "https"),
        ({"sources": ["somewhere"]}, "sources look like"),
        ({"forbidden_patterns": ["(unclosed"]}, "forbidden pattern"),
        ({"surprise": "field"}, "invalid front matter"),
    ],
)
def test_front_matter_is_checked(fields: dict[str, Any], problem: str) -> None:
    with pytest.raises(RefError, match="invalid front matter") as error:
        parse_policy(_module(**fields))
    assert problem in str(error.value)


def test_the_packet_turn_loads_core_and_matching_context_only() -> None:
    loaded = SHIPPED.load([], CONSTANTS)
    assert loaded.ids == (
        "core.boundaries",
        "core.escalation",
        "core.identity",
        "promo.none",
        "stage.decision",
    )
    assert loaded.allowed_tools == frozenset()


def test_skills_close_over_requires_and_writer_modules_stay_apart() -> None:
    loaded = SHIPPED.load(["financing"], CONSTANTS)
    assert {"financing", "payments.terms"} <= set(loaded.ids)
    meeting = SHIPPED.load([], {**CONSTANTS, "PIPELINE_STATUS": "MEETING_BOOKED"})
    assert {"stage.meeting", "consultation"} <= set(meeting.ids)
    assert "stage.decision" not in meeting.ids
    assert not {"writer.output", "writer.memory"} & set(loaded.ids)
    assert SHIPPED.writer().ids == ("writer.memory", "writer.output")


@pytest.mark.parametrize(
    ("values", "raw", "matches"),
    [
        (["*"], "Spring offer", True),
        (["*"], None, False),
        (["*"], " null ", False),
        (["null"], "", True),
        (["LEAD"], "LEAD", True),
        (["LEAD"], "PREP_PRE_CLINICAL", False),
    ],
)
def test_when_matches_a_constant(values: list[str], raw: str | None, matches: bool) -> None:
    assert When(constant="X", values=values).matches({"X": raw}) is matches


def test_unknown_requires_are_refused() -> None:
    policy_set = resolve_policy_set("shipped")
    broken = _module(requires=["nowhere"])
    modules = {**policy_set.modules, broken.module_id: broken}
    with pytest.raises(RefError, match="requires unknown"):
        PolicyCatalog(type(policy_set)("broken", modules, "x"))


@pytest.mark.parametrize(
    ("policy_set_id", "version", "fee"),
    [("shipped", "1.0.0", Decimal(25)), ("deposit-fee-change", "1.1.0", Decimal(40))],
)
def test_policy_facts_carry_their_module_version(
    policy_set_id: str, version: str, fee: Decimal
) -> None:
    loaded = PolicyCatalog(resolve_policy_set(policy_set_id)).load(["payments.terms"], CONSTANTS)
    (fact,) = [f for f in loaded.facts if f.attribute == "deposit-cancellation-fee"]
    assert (fact.value, fact.unit) == (fee, "USD")
    assert fact.source_ref.startswith(f"payments.terms@{version} packet:")


@pytest.mark.parametrize(
    ("response", "module"),
    [
        ("I'll note that for the team.", "core.boundaries"),
        ("I can share more over this chat.", "core.identity"),
        ("Dr. Hakan Clinic is marked as recommended.", "clinics.facts"),
    ],
)
def test_forbidden_phrases_point_to_their_module(response: str, module: str) -> None:
    loaded = SHIPPED.load(["clinics.facts"], CONSTANTS)
    (violation,) = check_policy_phrases(response, loaded.forbidden_patterns)
    assert violation.code == "policy_phrase"
    assert violation.source_ref is not None and violation.source_ref.startswith(f"{module}@")


def test_plain_text_passes_the_phrase_check() -> None:
    loaded = SHIPPED.load(["clinics.facts"], CONSTANTS)
    assert check_policy_phrases("Heva is in Istanbul.", loaded.forbidden_patterns) == []
