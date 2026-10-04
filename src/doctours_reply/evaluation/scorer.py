"""Deterministic per-case scores, and the official checks from the packet's grading note.

The official checks (packet L759) read `eval/official/expected_replies.json`; nothing
else does.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from doctours_reply.contract.reply import Reply
from doctours_reply.evaluation.cases import (
    EVAL_DIR,
    MONEY_ATTRIBUTES,
    WEEKDAY_ATTRIBUTE,
    Case,
    FactLabel,
    Labels,
)
from doctours_reply.runtime.evidence import urls_in
from doctours_reply.runtime.grounding import money_mentions, split_sentences
from doctours_reply.runtime.observation import Observation
from doctours_reply.runtime.payment_data import echoes_card_data, redact_card_data
from doctours_reply.runtime.refs import Fixture
from doctours_reply.tools.packet_tools import find_clinic
from doctours_reply.trace.schema import TraceRecord

HUMAN_CLASS = "human_requested"
OFFICIAL_CHECKS_VERSION = "2"
"""v2: a clinic flag counts when affirmed of a clinic that has it, in the flag's own words or
that clinic's own wording for it (v1 required the flag's exact words anywhere in the reply)."""
_GENERIC = frozenset({"Dr", "Clinic"})
_FLAG_CLAUSE = re.compile(r"[,;:]|\b(?:but|while|whereas)\b", re.IGNORECASE)
_FLAG_NEGATION = re.compile(r"\b(?:no|not|never|cannot)\b|n['’]t\b", re.IGNORECASE)


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    suite: str
    system: str
    run: int
    escalate_expected: bool
    escalate_actual: bool
    escalation_class: str | None
    control: str | None
    stage: str | None
    escalated_after_write: bool
    valid_before_repair: bool
    valid_after_finalize: bool
    grounded_first_try: bool | None
    validation_repairs: int
    tool_selection: bool | None
    required_facts_hit: int
    required_facts_total: int
    forbidden_hits: int
    urls_required_hit: int
    urls_required_total: int
    urls_forbidden_hits: int
    memory_ok: bool
    memory_tool_calls: int
    model_calls: int
    retries: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    official: dict[str, bool] | None = None
    cached_prompt_tokens: int = 0
    judge: dict[str, Any] | None = None
    escalation_code: str | None = None
    json_repairs: int = 0
    tool_not_loaded: int = 0
    skill_loads: int = 0
    end_to_end_ms: int = 0
    """Wall time for the item; `latency_ms` sums model calls only."""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def required_hit(self) -> int:
        return self.required_facts_hit + self.urls_required_hit

    @property
    def required_total(self) -> int:
        return self.required_facts_total + self.urls_required_total


def score_case(
    case: Case,
    suite: str,
    system: str,
    run: int,
    reply: Reply,
    trace: TraceRecord,
    fixture: Fixture,
    expected: Mapping[str, Any] | None = None,
) -> CaseScore:
    labels, outcome = case.labels, trace.outcome
    purposes = [call.purpose for call in trace.model_calls]
    answered_checks = [v for v in trace.validations if v.attempt == 1]
    return CaseScore(
        case_id=case.case_id,
        suite=suite,
        system=system,
        run=run,
        escalate_expected=labels.escalate,
        escalate_actual=reply.escalate,
        escalation_class=labels.escalation_class,
        control=labels.control,
        stage=outcome.stage if outcome else None,
        escalated_after_write=bool(reply.escalate and outcome and outcome.executed_writes),
        valid_before_repair="json_repair" not in purposes and bool(trace.model_calls),
        valid_after_finalize=_valid(reply),
        grounded_first_try=(
            not answered_checks[0].violations if answered_checks and not reply.escalate else None
        ),
        validation_repairs=purposes.count("validation_repair"),
        tool_selection=tool_selection(labels, trace.observations, fixture),
        required_facts_hit=sum(has_fact(reply.response, f) for f in labels.required_facts),
        required_facts_total=len(labels.required_facts),
        forbidden_hits=sum(has_fact(reply.response, f) for f in labels.forbidden_facts),
        urls_required_hit=sum(u in _reply_urls(reply) for u in labels.urls_required),
        urls_required_total=len(labels.urls_required),
        urls_forbidden_hits=sum(u in _reply_urls(reply) for u in labels.urls_forbidden),
        memory_ok=_memory_ok(labels, reply),
        memory_tool_calls=sum(
            o.tool == "updateWorkingMemory" and o.executed for o in trace.observations
        ),
        model_calls=len(trace.model_calls),
        retries=sum(call.attempts - 1 for call in trace.model_calls),
        prompt_tokens=sum(call.prompt_tokens for call in trace.model_calls),
        completion_tokens=sum(call.completion_tokens for call in trace.model_calls),
        latency_ms=sum(call.latency_ms for call in trace.model_calls),
        official=official_checks(case.text, reply, expected, fixture) if expected else None,
        cached_prompt_tokens=sum(call.cached_prompt_tokens for call in trace.model_calls),
        escalation_code=outcome.escalation.code if outcome and outcome.escalation else None,
        json_repairs=purposes.count("json_repair"),
        tool_not_loaded=sum(o.status == "tool_not_loaded" for o in trace.observations),
        skill_loads=sum(d["decision"].get("next") == "load_skills" for d in trace.decisions),
        end_to_end_ms=trace.latency_ms,
    )


def load_expected(eval_dir: Path = EVAL_DIR) -> dict[str, Mapping[str, Any]]:
    path = eval_dir / "official" / "expected_replies.json"
    return {row["id"]: row for row in json.loads(path.read_text("utf-8"))}


def official_checks(
    message: str, reply: Reply, expected: Mapping[str, Any], fixture: Fixture
) -> dict[str, bool]:
    """Packet L759: match `escalate`; carry the expected facts; or hand off cleanly."""
    checks = {"escalate": reply.escalate == expected["escalate"]}
    if expected["escalate"]:
        checks["no_sales_answer"] = not (
            money_mentions(reply.response)
            or urls_in(reply.response)
            or _package_names(reply.response, fixture)
        )
        checks["no_card_number"] = not echoes_card_data(
            reply.model_dump_json(), redact_card_data(message).card_digits
        )
        return checks
    text = expected["response"]
    for name in _package_names(text, fixture):
        checks[f"package {name}"] = name in reply.response
    actual_amounts = {m.amount for m in money_mentions(reply.response)}
    for money in money_mentions(text):
        checks[f"amount {money.amount}"] = money.amount in actual_amounts
    flags = {f["value"] for c in fixture.tool_data.clinics for f in c.get("clinic_flags", [])}
    for flag in sorted(flags):
        if flag.lower() in text.lower():
            checks[f"fact {flag}"] = _affirms_flag(reply.response, flag, fixture)
    for url in urls_in(text):
        checks[f"url {url}"] = url in _reply_urls(reply)
    return checks


def tool_selection(
    labels: Labels, observations: Sequence[Observation], fixture: Fixture
) -> bool | None:
    """True when the executed calls match one acceptable set, allowing optional reads."""
    if labels.tool_sets is None:
        return None
    executed = [o for o in observations if o.executed and o.tool != "updateWorkingMemory"]
    for option in labels.tool_sets:
        remaining = list(executed)
        for expectation in option:
            match = next((o for o in remaining if _matches(expectation, o, fixture)), None)
            if match is None:
                break
            remaining.remove(match)
        else:
            if all(
                o.tool in (labels.optional_reads if o.kind == "read" else labels.writes_allowed)
                for o in remaining
            ):
                return True
    return False


def _matches(expectation: Any, observation: Observation, fixture: Fixture) -> bool:
    if observation.tool != expectation.tool:
        return False
    args = observation.args if isinstance(observation.args, dict) else {}
    selection = args.get("clinicSelection")
    selection = selection if isinstance(selection, dict) else {}
    if expectation.type is not None and args.get("type") != expectation.type:
        return False
    if expectation.clinic is not None:
        lookup = {
            "clinicId": args.get("clinicId") or selection.get("selectedClinicId"),
            "clinicName": args.get("clinicName"),
        }
        clinic = find_clinic(fixture.tool_data, lookup)
        if clinic is None or clinic["slug"] != expectation.clinic:
            return False
    if expectation.package is not None:
        package_id = args.get("clinicPackageId") or selection.get("selectedPackageId")
        names = {p["id"]: p["name"] for p in fixture.tool_data.packages}
        if names.get(package_id) != expectation.package:
            return False
    return True


def has_fact(response: str, fact: FactLabel) -> bool:
    if fact.attribute in MONEY_ATTRIBUTES:
        return any(
            re.search(rf"\b{re.escape(fact.entity)}\b", sentence, re.IGNORECASE)
            and any(m.amount == fact.value for m in money_mentions(sentence))
            for sentence in split_sentences(response)
        )
    if fact.attribute == WEEKDAY_ATTRIBUTE:
        return _mentions_weekday(response, str(fact.value))
    if isinstance(fact.value, str):
        value = _normalized(fact.value)
        if counted := re.fullmatch(r"(\d+) (\w+)", value):
            number, unit = counted.groups()
            phrase = rf"(?<!\w){number}(?: \w+)? {re.escape(unit)}s?(?!\w)"
        else:
            phrase = rf"(?<!\w){re.escape(value)}s?(?!\w)"
        return re.search(phrase, _normalized(response)) is not None
    return re.search(rf"\b{re.escape(fact.entity)}\b", response, re.IGNORECASE) is not None


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY = "(" + "|".join(f"{day}|{day[:3]}" for day in _WEEKDAYS) + ")s?"
_DAY_WORD = re.compile(rf"\b{_DAY}\b")
_DAY_RANGE = re.compile(rf"\b{_DAY}\.?\s*(?:-|–|—|to|through|thru)\s*{_DAY}\b")


def _mentions_weekday(response: str, day: str) -> bool:
    """`day` named as a word, or inside a stated range such as "Monday to Friday"."""
    text = response.lower()
    target = _day_index(day)
    if any(_day_index(m.group(1)) == target for m in _DAY_WORD.finditer(text)):
        return True
    return any(_day_index(a) <= target <= _day_index(b) for a, b in _DAY_RANGE.findall(text))


def _day_index(name: str) -> int:
    return [day[:3] for day in _WEEKDAYS].index(name[:3].lower())


_NUMBER_WORDS = {
    word: str(n)
    for n, word in enumerate(
        ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"), start=1
    )
}


def _normalized(text: str) -> str:
    """Lowercase, hyphens as spaces and number words as digits, for phrase matching."""
    words = re.sub(r"[-\s]+", " ", text.lower()).split(" ")
    return " ".join(_NUMBER_WORDS.get(word, word) for word in words)


def _reply_urls(reply: Reply) -> set[str]:
    return set(urls_in(reply.response)) | set(reply.attachmentUrls or [])


def _memory_ok(labels: Labels, reply: Reply) -> bool:
    updates = (
        reply.workingMemoryUpdates.model_dump(exclude_unset=True)
        if reply.workingMemoryUpdates
        else {}
    )
    return all(updates.get(k) == v for k, v in labels.memory.must_set.items()) and not any(
        key in updates for key in labels.memory.must_not_set
    )


def _affirms_flag(response: str, flag: str, fixture: Fixture) -> bool:
    """A clause states `flag`, or its clinic's own `bestFor` wording that holds every word of
    it, of a clinic that has the flag, without negating it. A sentence that names no clinic
    refers to the last clinic named before it."""
    clinics = fixture.tool_data.clinics
    owners = {c["name"] for c in clinics if flag in (f["value"] for f in c.get("clinic_flags", []))}
    words = set(re.findall(r"[a-z]+", flag.lower()))
    phrases = {flag} | {
        phrase
        for c in clinics
        if c["name"] in owners
        for phrase in c.get("ai_context", {}).get("bestFor", [])
        if words <= set(re.findall(r"[a-z]+", phrase.lower()))
    }
    tokens = {
        c["name"]: " ".join(w for w in re.findall(r"[A-Za-z]+", c["name"]) if w not in _GENERIC)
        for c in clinics
    }
    last: str | None = None
    for sentence in split_sentences(response):
        spots = sorted(
            (m.start(), name)
            for name, token in tokens.items()
            for m in re.finditer(rf"\b{re.escape(token)}\b", sentence)
        )
        for phrase in phrases:
            for match in re.finditer(rf"\b{re.escape(phrase)}\b", sentence, re.IGNORECASE):
                before = [name for spot, name in spots if spot < match.start()]
                after = [name for spot, name in spots if spot > match.start()]
                clinic = before[-1] if before else after[0] if after else last
                clause = _FLAG_CLAUSE.split(sentence[: match.start()])[-1]
                if clinic in owners and not _FLAG_NEGATION.search(clause):
                    return True
        last = spots[-1][1] if spots else last
    return False


def _package_names(text: str, fixture: Fixture) -> list[str]:
    return [
        p["name"]
        for p in fixture.tool_data.packages
        if re.search(rf"\b{re.escape(p['name'])}\b", text)
    ]


def _valid(reply: Reply) -> bool:
    try:
        Reply.model_validate_json(reply.model_dump_json(exclude_unset=True))
    except ValueError:
        return False
    return True
