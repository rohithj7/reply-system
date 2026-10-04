"""Evidence for checking a reply: the fact table, the allowed URLs and the ready links
(decision record 0002).

Facts come from tool results executed this turn, plus static facts declared by the
loaded policy text. Response URLs may come from tool results, declared static links,
or Doctours clinic pages for slugs a tool returned this turn. Attachment URLs must
come from tool results.
"""

import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from doctours_reply.runtime.observation import Observation

CLINIC_PAGE = "https://www.doctours.com/clinic/{slug}"
URL = re.compile(r"https?://[^\s<>\"'()\[\]]+")
_URL_TRAILING = ".,;:!?"
_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_LINK_TYPES = ("payment", "checkout")


@dataclass(frozen=True)
class Fact:
    entity_type: Literal["package", "policy"]
    entity_id: str
    entity_name: str
    clinic_id: str | None
    clinic_name: str | None
    attribute: str
    value: Decimal
    unit: str | None
    source_ref: str
    cues: tuple[str, ...] = ()
    """For policy facts: phrases that tie an amount in a clause to this fact."""


@dataclass(frozen=True)
class ReadyLink:
    kind: Literal["payment", "checkout", "assessment"]
    url: str
    name: str
    """The package (payment link), the clinic (checkout link) or "assessment"."""
    clinic_id: str | None
    selected: bool
    """The package or clinic is the patient's selection: saved this turn, else already saved."""
    source_ref: str


@dataclass(frozen=True)
class Evidence:
    facts: tuple[Fact, ...]
    response_urls: frozenset[str]
    attachment_urls: frozenset[str]
    clinic_names: Mapping[str, str]
    numbers: frozenset[Decimal]
    """Every number shown to the model or returned by a tool this turn."""
    links: tuple[ReadyLink, ...]
    """Ready payment, checkout and assessment links returned by a tool this turn."""
    deposit_link_asked: bool
    """getPaymentLink was called this turn, whatever came back."""
    assessment_cues: tuple[tuple[str, re.Pattern[str]], ...]
    """Requests a loaded policy answers with the assessment link."""

    def packages(self) -> dict[str, list[Fact]]:
        grouped: dict[str, list[Fact]] = {}
        for fact in self.facts:
            if fact.entity_type == "package":
                grouped.setdefault(fact.entity_name, []).append(fact)
        return grouped

    def policy_facts(self) -> list[Fact]:
        return [f for f in self.facts if f.entity_type == "policy"]


def build_evidence(
    observations: Sequence[Observation],
    *,
    clinics: Sequence[Mapping[str, Any]],
    static_facts: Sequence[Fact] = (),
    static_links: Iterable[str] = (),
    assessment_cues: Sequence[tuple[str, re.Pattern[str]]] = (),
    shown_text: str = "",
) -> Evidence:
    """`clinics` names the owners of observed packages; it adds no facts of its own."""
    executed = [o for o in observations if o.status == "ok"]
    clinic_names = {c["id"]: c["name"] for c in clinics if "id" in c and "name" in c}
    facts: list[Fact] = list(static_facts)
    tool_urls: set[str] = set()
    pages: set[str] = set()
    links: list[tuple[Mapping[str, Any], str]] = []
    written: dict[str, Any] = {}
    saved: dict[str, Any] = {}
    for observation in executed:
        source = f"{observation.tool}#{observation.call_id}"
        for record in _records(observation.result):
            if "slug" in record and "name" in record and "id" in record:
                clinic_names[record["id"]] = record["name"]
                pages.add(CLINIC_PAGE.format(slug=record["slug"]))
        for record in _records(observation.result):
            if "basePrice" in record and "name" in record and "id" in record:
                facts.extend(_package_facts(record, clinic_names, source))
            if record.get("linkType") in _LINK_TYPES and record.get("status") == "ready":
                links.append((record, source))
            if isinstance(record.get("assessmentUrl"), str) and (
                record.get("shareStatus") == "available"
            ):
                links.append((record, source))
            for key in ("selectedPackageId", "selectedClinicId"):
                if record.get(key):
                    (written if observation.kind == "write" else saved)[key] = record[key]
        tool_urls.update(urls_in(json.dumps(observation.result, ensure_ascii=False)))
    selected = saved | written
    shown = " ".join([shown_text, *(json.dumps(o.result) for o in executed)])
    numbers = {parse_number(n) for n in _NUMBER.findall(shown)}
    numbers.update(f.value for f in facts)
    return Evidence(
        facts=tuple(facts),
        response_urls=frozenset(tool_urls | pages | set(static_links)),
        attachment_urls=frozenset(tool_urls),
        clinic_names=clinic_names,
        numbers=frozenset(numbers),
        links=tuple(_ready_link(record, selected, source) for record, source in links),
        deposit_link_asked=any(o.tool == "getPaymentLink" for o in observations),
        assessment_cues=tuple(assessment_cues),
    )


def _ready_link(record: Mapping[str, Any], selected: Mapping[str, Any], source: str) -> ReadyLink:
    if "assessmentUrl" in record:
        return ReadyLink("assessment", record["assessmentUrl"], "assessment", None, False, source)
    if record["linkType"] == "payment":
        return ReadyLink(
            "payment",
            record["url"],
            record["clinicPackageName"],
            record["clinicId"],
            record["clinicPackageId"] == selected.get("selectedPackageId"),
            source,
        )
    clinic = record["clinicId"]
    return ReadyLink(
        "checkout",
        record["url"],
        record["clinicName"],
        clinic,
        clinic == selected.get("selectedClinicId"),
        source,
    )


def urls_in(text: str) -> list[str]:
    return [match.rstrip(_URL_TRAILING) for match in URL.findall(text)]


def parse_number(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _records(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for item in value.values():
            yield from _records(item)
    elif isinstance(value, list):
        for item in value:
            yield from _records(item)


def _package_facts(
    package: Mapping[str, Any], clinic_names: Mapping[str, str], source: str
) -> Iterator[Fact]:
    clinic_id = package.get("clinicId")
    clinic_name = clinic_names.get(clinic_id) if isinstance(clinic_id, str) else None

    def fact(attribute: str, value: Any, unit: str | None) -> Fact:
        return Fact(
            "package",
            package["id"],
            package["name"],
            clinic_id if isinstance(clinic_id, str) else None,
            clinic_name,
            attribute,
            Decimal(str(value)),
            unit,
            source,
        )

    currency = package.get("currency") or "USD"
    for attribute in ("basePrice", "depositAmount"):
        if isinstance(package.get(attribute), int | float):
            yield fact(attribute, package[attribute], currency)
    for addon in package.get("includedAddons") or []:
        quantity = addon.get("includedQuantity") if isinstance(addon, Mapping) else None
        if isinstance(quantity, int | float) and isinstance(addon.get("unitDescription"), str):
            name = str(addon.get("name", "")).lower()
            yield fact(f"included.{name}", quantity, addon["unitDescription"].lower())
