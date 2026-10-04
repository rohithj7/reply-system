"""S1, the modular system: route, load, decide, execute and observe, write, validate,
commit memory (decision record 0002).

Bounds: one route call, at most one extra skill load, at most 3 execute rounds and the
executor's 8 tool calls, so at most 6 controller calls. The controller only proposes
calls; the executor runs them against the loaded allowlist. A read this turn already ran
with the same arguments is not run again, since its result is in STATE.history, and a
round that runs nothing new ends the tool rounds. An escalation closes the
executor at once, so no tool or memory call follows it, and the patient sees the
escalation code's template sentence.
"""

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from doctours_reply.models.client import ModelClient
from doctours_reply.runtime import controller
from doctours_reply.runtime.context import TurnContext
from doctours_reply.runtime.controller import Budget, DecideState
from doctours_reply.runtime.controller_io import (
    controller_messages,
    history,
    tool_specs,
    writer_messages,
)
from doctours_reply.runtime.decision import ActionDecision, EscalationChoice, Intent, PlannedCall
from doctours_reply.runtime.escalation import template_escalation
from doctours_reply.runtime.evidence import build_evidence
from doctours_reply.runtime.executor import Executor
from doctours_reply.runtime.finalize import memory_diff
from doctours_reply.runtime.observation import Observation
from doctours_reply.runtime.outcome import Draft, Escalation, OutcomeStage, TerminalOutcome
from doctours_reply.runtime.policy_loader import LoadedPolicies, PolicyCatalog
from doctours_reply.runtime.validate import check_escalation_reason
from doctours_reply.runtime.writer import record_validation, write_reply
from doctours_reply.tools.registry import TOOLS, UnknownToolError, resolve_tool_name
from doctours_reply.trace.schema import TraceRecord

MEMORY_CALL_ID = "memory"


def run_modular(
    ctx: TurnContext, client: ModelClient, executor: Executor, trace: TraceRecord
) -> TerminalOutcome:
    catalog = PolicyCatalog(ctx.policy_set)
    constants = ctx.fixture.constants
    known = frozenset(catalog.skill_ids)
    mandatory = catalog.load([], constants)
    trace.policies = mandatory.record()

    route_state = {"step": "route", "catalog": catalog.catalog()}
    route = controller.route(client, controller_messages(ctx, mandatory, route_state), trace, known)
    if route is None:
        return _failed(executor)
    if route.escalation is not None:
        return _escalate(ctx, executor, trace, route.escalation, "route")

    skills = list(dict.fromkeys(route.skills))
    loaded = catalog.load(skills, constants)
    trace.policies = loaded.record()
    budget = Budget(calls_left=executor.calls_left)
    review_required = True
    rounds = 0
    while True:
        state = DecideState(known, frozenset(skills), budget, review_required)
        decide_state = _decide_state(
            ctx, catalog, mandatory, loaded, route.intents, state, executor
        )
        decision = controller.decide(
            client, controller_messages(ctx, mandatory, decide_state), trace, state
        )
        if decision is None:
            return _failed(executor)
        review_required = False
        if decision.escalation is not None:
            return _escalate(ctx, executor, trace, decision.escalation, "decide")
        if not isinstance(decision, ActionDecision) or decision.next in ("answer", "clarify"):
            break
        if decision.next == "load_skills":
            skills += [s for s in decision.skills_to_add if s not in skills]
            loaded = catalog.load(skills, constants)
            trace.policies = loaded.record()
            budget.skill_loads_left -= 1
            continue
        rounds += 1
        ran = 0
        for call in decision.calls:
            if _already_read(call, executor.observations):
                continue
            executor.execute(
                f"r{rounds}.{call.id}", call.name, call.arguments, allowed=loaded.allowed_tools
            )
            ran += 1
        budget.rounds_left = budget.rounds_left - 1 if ran else 0
        budget.calls_left = executor.calls_left

    writer_policies = catalog.writer()
    trace.policies = loaded.record() + writer_policies.record()
    messages = writer_messages(
        ctx,
        mandatory,
        writer_policies,
        _skills_only(loaded, mandatory),
        decision.next,
        route.intents,
        executor.observations,
    )
    evidence = build_evidence(
        executor.observations,
        clinics=ctx.fixture.tool_data.clinics,
        static_facts=loaded.facts,
        static_links=loaded.static_links,
        assessment_cues=loaded.assessment_link_cues,
        shown_text=" ".join(str(m["content"]) for m in messages),
    )
    trace.fact_table = [{**asdict(f), "value": str(f.value)} for f in evidence.facts]
    checked = LoadedPolicies(loaded.policies + writer_policies.policies)
    result = write_reply(client, messages, trace, evidence, ctx.message, checked)
    if result == "controller_failure":
        return _failed(executor)
    if not isinstance(result, Draft):
        executor.close()
        return _escalated(executor, template_escalation("unverified_reply"), "validation")
    diff = memory_diff(result.workingMemoryUpdates, ctx.working_memory)
    if diff is not None:
        executor.commit_memory(MEMORY_CALL_ID, diff.model_dump(mode="json", exclude_unset=True))
    return TerminalOutcome(
        kind="clarified" if decision.next == "clarify" else "answered",
        stage=None,
        draft=result,
        executed_writes=executor.executed_writes,
    )


def _decide_state(
    ctx: TurnContext,
    catalog: PolicyCatalog,
    mandatory: LoadedPolicies,
    loaded: LoadedPolicies,
    intents: list[Intent],
    state: DecideState,
    executor: Executor,
) -> dict[str, Any]:
    loadable = state.budget.skill_loads_left > 0
    return {
        "step": "decide",
        "review_required": state.review_required,
        "intents": [i.model_dump() for i in intents],
        "loaded_skills": sorted(state.loaded_skills),
        "policies": _skills_only(loaded, mandatory).render(),
        "catalog": [c for c in catalog.catalog() if loadable and c["id"] not in loaded.ids],
        "tools": tool_specs(loaded),
        "history": history(executor.observations, ctx),
        "writes_executed": list(executor.executed_writes),
        "budget": state.budget.as_state(),
    }


def _already_read(call: PlannedCall, observations: Sequence[Observation]) -> bool:
    try:
        spec = TOOLS[resolve_tool_name(call.name)]
    except UnknownToolError:
        return False
    return spec.kind == "read" and any(
        o.tool == spec.name and o.executed and o.args == call.arguments for o in observations
    )


def _skills_only(loaded: LoadedPolicies, mandatory: LoadedPolicies) -> LoadedPolicies:
    return LoadedPolicies(tuple(p for p in loaded.policies if p.id not in mandatory.ids))


def _escalate(
    ctx: TurnContext,
    executor: Executor,
    trace: TraceRecord,
    choice: EscalationChoice,
    stage: OutcomeStage,
) -> TerminalOutcome:
    """The handoff sentence is the code's template; the controller's reason is kept if valid."""
    executor.close()
    template = template_escalation(choice.code)
    reason = choice.reason.strip()
    problems = check_escalation_reason(reason, ctx.message)
    record_validation(trace, problems)
    escalation = Escalation(
        code=choice.code,
        reason=template.reason if problems else reason,
        sentence=template.sentence,
    )
    return _escalated(executor, escalation, stage)


def _failed(executor: Executor) -> TerminalOutcome:
    executor.close()
    return _escalated(executor, template_escalation("controller_failure"), "controller_failure")


def _escalated(executor: Executor, escalation: Escalation, stage: OutcomeStage) -> TerminalOutcome:
    return TerminalOutcome(
        kind="escalated",
        stage=stage,
        escalation=escalation,
        executed_writes=executor.executed_writes,
    )
