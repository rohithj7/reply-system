"""Evaluation cases, their labels and the suites under `eval/` (plan 8.3).

Labels come from the requirement list, never from expected outputs. `check_case`
verifies label consistency against the case's fixture, so authoring errors fail early.
"""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError, model_validator

from doctours_reply.runtime.decision import EscalationCode, IntentKind
from doctours_reply.runtime.refs import Fixture
from doctours_reply.tools.registry import TOOLS

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
EVAL_DIR: Final = REPO_ROOT / "eval"

Control = Literal[
    "policy_question",
    "negated_or_quoted_human_mention",
    "hypothetical_human_mention",
    "card_data_without_action",
    "supported_payment_link",
    "rule_backed_redirect",
]
MONEY_ATTRIBUTES: Final = ("basePrice", "depositAmount")
WEEKDAY_ATTRIBUTE: Final = "bookableWeekdays"


class _Label(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ToolExpectation(_Label):
    tool: str
    clinic: str | None = None
    """Clinic slug the call must resolve to."""
    package: str | None = None
    """Package name whose ID the call must carry."""
    type: Literal["payment", "checkout"] | None = None


class FactLabel(_Label):
    entity: str
    attribute: str | None = None
    value: int | float | str | None = None


class MemoryLabel(_Label):
    must_set: dict[str, JsonValue] = {}
    must_not_set: list[str] = []


class Labels(_Label):
    escalate: bool
    escalation_class: EscalationCode | None = None
    control: Control | None = None
    intent_kinds: list[IntentKind]
    tool_sets: list[list[ToolExpectation]] | None = None
    """Acceptable executed tool multisets; null means tool use is not scored."""
    optional_reads: list[str] = []
    writes_allowed: list[str] = []
    required_facts: list[FactLabel] = []
    forbidden_facts: list[FactLabel] = []
    urls_required: list[str] = []
    urls_forbidden: list[str] = []
    memory: MemoryLabel = MemoryLabel()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.escalate != (self.escalation_class is not None):
            raise ValueError("escalation_class is set exactly when escalate is true")
        if self.escalate and self.control is not None:
            raise ValueError("control types label non-escalating cases only")
        return self


class Case(_Label):
    case_id: str
    text: str
    fixture_id: str
    policy_set_id: str
    labels: Labels


class OfficialLabel(_Label):
    case_id: str
    fixture_id: str
    policy_set_id: str
    labels: Labels


Suite = Literal["official", "dev", "adversarial", "regression", "heldout_v1"]
SUITES: Final[dict[Suite, str]] = {
    "official": "official/labels.jsonl",
    "dev": "dev/v0.jsonl",
    "adversarial": "adversarial/v1.jsonl",
    "regression": "regression/rc_e.jsonl",
    "heldout_v1": "heldout/v1.jsonl",
}
GUARDED_SUITES: Final = frozenset({"heldout_v1"})
FROZEN_HASHES: Final = {"heldout_v1": "heldout/v1.sha256"}


class CaseError(ValueError):
    """A suite file is missing, malformed or inconsistent."""


def suite_path(suite: Suite, eval_dir: Path = EVAL_DIR) -> Path:
    return eval_dir / SUITES[suite]


def suite_sha256(suite: Suite, eval_dir: Path = EVAL_DIR) -> str:
    return hashlib.sha256(suite_path(suite, eval_dir).read_bytes()).hexdigest()


def frozen_hash_problem(suite: Suite, eval_dir: Path = EVAL_DIR) -> str | None:
    """None if `suite` is not frozen or still matches its committed hash."""
    if suite not in FROZEN_HASHES:
        return None
    hash_file = eval_dir / FROZEN_HASHES[suite]
    if not hash_file.is_file():
        return f"{suite} has no frozen hash at {hash_file.name}"
    recorded = hash_file.read_text("utf-8").split()[0]
    actual = suite_sha256(suite, eval_dir)
    return None if recorded == actual else f"{suite} changed: frozen {recorded}, now {actual}"


def load_suite(suite: Suite, eval_dir: Path = EVAL_DIR) -> list[Case]:
    path = suite_path(suite, eval_dir)
    rows = _jsonl(path)
    try:
        if suite != "official":
            cases = [Case.model_validate(row) for row in rows]
        else:
            texts = {
                m["id"]: m["text"]
                for m in json.loads((path.parent / "human_messages.json").read_text("utf-8"))
            }
            cases = [
                Case(
                    text=texts[label.case_id],
                    **label.model_dump(exclude={"labels"}),
                    labels=label.labels,
                )
                for label in (OfficialLabel.model_validate(row) for row in rows)
            ]
    except (ValidationError, KeyError) as exc:
        raise CaseError(f"{path}: {exc}") from exc
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise CaseError(f"{path}: duplicate case_id")
    return cases


def check_case(case: Case, fixture: Fixture) -> list[str]:
    """Label problems for `case` against its fixture; empty when consistent."""
    labels, data = case.labels, fixture.tool_data
    slugs = {c["slug"] for c in data.clinics}
    packages = {p["name"]: p for p in data.packages}
    clinic_names = {c["name"] for c in data.clinics}
    problems = []
    expectations = [e for option in labels.tool_sets or [] for e in option]
    for name in [e.tool for e in expectations] + labels.optional_reads + labels.writes_allowed:
        if name not in TOOLS:
            problems.append(f"unknown tool {name!r}")
    problems += [
        f"unknown clinic {e.clinic!r}" for e in expectations if e.clinic not in (None, *slugs)
    ]
    problems += [
        f"unknown package {e.package!r}" for e in expectations if e.package not in (None, *packages)
    ]
    for fact in labels.required_facts:
        if fact.entity not in packages and fact.entity not in clinic_names:
            problems.append(f"required fact names unknown entity {fact.entity!r}")
        elif (
            fact.attribute in MONEY_ATTRIBUTES
            and fact.entity in packages
            and packages[fact.entity][fact.attribute] != fact.value
        ):
            problems.append(f"{fact.entity}.{fact.attribute} is not {fact.value}")
        elif (
            fact.attribute == WEEKDAY_ATTRIBUTE
            and fact.entity in packages
            and str(fact.value)[:3].upper() not in packages[fact.entity][WEEKDAY_ATTRIBUTE]
        ):
            problems.append(f"{fact.entity} is not bookable on {fact.value}")
        elif fact.attribute and fact.attribute.startswith("included.") and fact.entity in packages:
            addon = fact.attribute.removeprefix("included.")
            included = {
                a["name"]: f"{a['includedQuantity']} {a['unitDescription']}"
                for a in packages[fact.entity]["includedAddons"]
            }
            if included.get(addon) != fact.value:
                problems.append(f"{fact.entity} does not include {fact.value!r} {addon}")
    for url in labels.urls_required + labels.urls_forbidden:
        if not url.startswith("https://"):
            problems.append(f"bad url {url!r}")
    return [f"{case.case_id}: {problem}" for problem in problems]


def _jsonl(path: Path) -> Iterable[dict[str, object]]:
    try:
        lines = path.read_text("utf-8").splitlines()
    except FileNotFoundError as exc:
        raise CaseError(f"missing suite file {path}") from exc
    rows = []
    for number, line in enumerate(lines, 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CaseError(f"{path}:{number}: {exc}") from exc
    return rows
