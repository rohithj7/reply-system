"""S1 controller decisions: the route step and the decide step (decision record 0002).

The controller never writes patient-facing text. It classifies intents, picks skills,
plans tool calls from the loaded allowlist, and chooses answer, clarify or escalate.
"""

import json
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

IntentKind = Literal[
    "policy_question",
    "information_request",
    "action_request",
    "preference_statement",
    "human_request",
    "pause",
    "other",
]
EscalationCode = Literal[
    "human_requested",
    "unsupported_payment_action",
    "unsupported_money_movement",
    "unsupported_clinic_contact",
    "unsupported_date_hold",
    "unsupported_booking_change",
    "unsupported_document_action",
    "unsupported_other",
]
NOT_AN_ACTION = "n/a"
UNSUPPORTED = "none"


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Intent(_Decision):
    summary: str = Field(max_length=200)
    kind: IntentKind
    supported_by: str = Field(
        description=(
            "For action_request: tool:<name>, self_service:<link or page>, rule:<policy id>, "
            f"or {UNSUPPORTED!r}. For every other kind: {NOT_AN_ACTION!r}."
        )
    )


class EscalationChoice(_Decision):
    code: EscalationCode
    reason: str = Field(description="12 words or fewer, no digits: what the patient asked for.")


class RouteDecision(_Decision):
    intents: list[Intent] = Field(min_length=1, max_length=6)
    skills: list[str] = Field(max_length=4, description="Skill ids from the catalog.")
    outcome: Literal["continue", "escalate"]
    escalation: EscalationChoice | None = None


class PlannedCall(_Decision):
    id: str = Field(
        pattern=r"^[A-Za-z0-9_.-]{1,32}$", description="Unique among this decision's calls."
    )
    name: str
    arguments: dict[str, JsonValue]


class EscalationReview(_Decision):
    needed: bool
    why: str = Field(max_length=200)


class ActionDecision(_Decision):
    escalation_review: EscalationReview | None = Field(
        default=None, description="Required on the first decide step."
    )
    next: Literal["call_tools", "load_skills", "answer", "clarify", "escalate"]
    calls: list[PlannedCall] = Field(default=[], max_length=8)
    skills_to_add: list[str] = Field(default=[], max_length=3)
    escalation: EscalationChoice | None = None


class FinalDecision(_Decision):
    """The decide step once the tool budget is spent: no more calls or skills."""

    escalation_review: EscalationReview | None = None
    next: Literal["answer", "clarify", "escalate"]
    escalation: EscalationChoice | None = None


SCHEMAS: dict[str, type[BaseModel]] = {
    "route": RouteDecision,
    "decide": ActionDecision,
    "decide_final": FinalDecision,
}

if __name__ == "__main__":
    print(json.dumps(SCHEMAS[sys.argv[1]].model_json_schema(), indent=2))
