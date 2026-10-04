"""S1 controller steps: route and decide (plan 6.2-6.3).

Each step is one model call whose JSON must parse into its decision model and pass the
semantic checks below. An invalid decision gets one retry with the problems listed;
a second invalid decision returns None, which the caller turns into `controller_failure`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel

from doctours_reply.models.client import ChatRequest, ChatResponse, Message, ModelClient
from doctours_reply.runtime.decision import (
    NOT_AN_ACTION,
    UNSUPPORTED,
    ActionDecision,
    FinalDecision,
    RouteDecision,
)
from doctours_reply.runtime.model_calls import complete, follow_up, parse_json
from doctours_reply.tools.registry import TOOLS
from doctours_reply.trace.schema import Purpose, TraceRecord

MAX_EXECUTE_ROUNDS: Final = 3
MAX_SKILL_LOADS: Final = 1
_SUPPORT: Final = re.compile(r"^(?:tool:(?P<tool>\w+)|self_service:.+|rule:.+|none)$")
_RETRY: Final = (
    "That decision was not accepted: {problems}\n"
    "Return a corrected JSON object for the same STATE only."
)


@dataclass
class Budget:
    rounds_left: int = MAX_EXECUTE_ROUNDS
    calls_left: int = 8
    skill_loads_left: int = MAX_SKILL_LOADS

    @property
    def spent(self) -> bool:
        return self.rounds_left <= 0 or self.calls_left <= 0

    def as_state(self) -> dict[str, int]:
        return {
            "rounds_left": self.rounds_left,
            "calls_left": self.calls_left,
            "skill_loads_left": self.skill_loads_left,
        }


@dataclass
class DecideState:
    """What the decide step may rely on beyond the serialized STATE."""

    known_skills: frozenset[str]
    loaded_skills: frozenset[str]
    budget: Budget
    review_required: bool


def escalation_required(route: RouteDecision) -> bool:
    return any(
        i.kind == "human_request" or (i.kind == "action_request" and i.supported_by == UNSUPPORTED)
        for i in route.intents
    )


def route_problems(route: RouteDecision, known_skills: frozenset[str]) -> list[str]:
    problems = [f"unknown skill {s!r}" for s in route.skills if s not in known_skills]
    if len(set(route.skills)) != len(route.skills):
        problems.append("skills repeat")
    for intent in route.intents:
        if intent.kind == "action_request":
            match = _SUPPORT.match(intent.supported_by)
            if match is None:
                problems.append(
                    f"supported_by {intent.supported_by!r} is not tool:<name>, "
                    f"self_service:<link>, rule:<policy id> or {UNSUPPORTED!r}"
                )
            elif match["tool"] and match["tool"] not in TOOLS:
                problems.append(
                    f"supported_by {intent.supported_by!r} names no tool; use {UNSUPPORTED!r} "
                    "if nothing supports the action"
                )
        elif intent.supported_by != NOT_AN_ACTION:
            problems.append(f"supported_by is {NOT_AN_ACTION!r} for a {intent.kind}")
    required = escalation_required(route)
    if required != (route.outcome == "escalate"):
        problems.append(
            "outcome must be 'escalate' exactly when an intent is human_request or an "
            f"action_request with supported_by {UNSUPPORTED!r}"
        )
    if (route.outcome == "escalate") != (route.escalation is not None):
        problems.append("escalation is set exactly when outcome is 'escalate'")
    return problems


def decide_problems(decision: ActionDecision | FinalDecision, state: DecideState) -> list[str]:
    problems = []
    review = decision.escalation_review
    if state.review_required and review is None:
        problems.append("escalation_review is required on this step")
    if review is not None and review.needed and decision.next != "escalate":
        problems.append("escalation_review.needed is true, so next must be 'escalate'")
    if (decision.next == "escalate") != (decision.escalation is not None):
        problems.append("escalation is set exactly when next is 'escalate'")
    if isinstance(decision, ActionDecision):
        problems += _action_problems(decision, state)
    return problems


def _action_problems(decision: ActionDecision, state: DecideState) -> list[str]:
    problems = []
    if decision.next == "call_tools":
        ids = [c.id for c in decision.calls]
        if not ids:
            problems.append("call_tools needs at least one call")
        if len(ids) > state.budget.calls_left:
            problems.append(f"at most {state.budget.calls_left} calls are left")
        if len(set(ids)) != len(ids):
            problems.append("call ids must be unique")
    elif decision.calls:
        problems.append("calls are only for next 'call_tools'")
    if decision.next == "load_skills":
        if state.budget.skill_loads_left <= 0:
            problems.append("no skill loads are left")
        new = [s for s in decision.skills_to_add if s not in state.loaded_skills]
        if not new:
            problems.append(
                "skills_to_add needs at least one skill that is not loaded; loaded skills are "
                "in STATE.policies, so choose call_tools, answer, clarify or escalate instead"
            )
        problems += [f"unknown skill {s!r}" for s in new if s not in state.known_skills]
    elif decision.skills_to_add:
        problems.append("skills_to_add is only for next 'load_skills'")
    return problems


def route(
    client: ModelClient,
    messages: list[Message],
    trace: TraceRecord,
    known_skills: frozenset[str],
) -> RouteDecision | None:
    return _decide_step(
        client, messages, trace, "route", RouteDecision, lambda d: route_problems(d, known_skills)
    )


def decide(
    client: ModelClient, messages: list[Message], trace: TraceRecord, state: DecideState
) -> ActionDecision | FinalDecision | None:
    model: type[ActionDecision] | type[FinalDecision] = (
        FinalDecision if state.budget.spent else ActionDecision
    )
    return _decide_step(
        client, messages, trace, "decide", model, lambda d: decide_problems(d, state)
    )


def _decide_step[D: BaseModel](
    client: ModelClient,
    messages: list[Message],
    trace: TraceRecord,
    purpose: Purpose,
    model: type[D],
    check: Callable[[D], list[str]],
) -> D | None:
    request = ChatRequest(
        messages=list(messages), response_schema=model.model_json_schema(), schema_name=purpose
    )
    response = complete(client, request, trace, purpose)
    decision, problems = _parse(response, model, check)
    if decision is not None:
        _record(trace, purpose, decision)
        return decision
    retry = ChatRequest(
        messages=[*messages, *follow_up(response, _RETRY.format(problems="; ".join(problems)))],
        response_schema=request.response_schema,
        schema_name=purpose,
    )
    response = complete(client, retry, trace, "json_repair")
    decision, _ = _parse(response, model, check)
    if decision is not None:
        _record(trace, purpose, decision)
    return decision


def _parse[D: BaseModel](
    response: ChatResponse, model: type[D], check: Callable[[D], list[str]]
) -> tuple[D | None, list[str]]:
    decision, problems = parse_json(response, model)
    if decision is None:
        return None, problems
    problems = check(decision)
    return (None, problems) if problems else (decision, [])


def _record(trace: TraceRecord, step: str, decision: BaseModel) -> None:
    trace.decisions.append({"step": step, "decision": decision.model_dump(mode="json")})
