"""S0: one model, the verbatim packet prompt and all 14 packet functions as native tools.

The model sees the filled legacy system prompt (packet Flow, L29-33) plus the contract
appendix below, which restates the output contract (L7, L82) and quotes no packet
message. Tool calls go through the shared executor; the final JSON goes through the
shared validators, one repair and the finalizer. See decision record 0003.
"""

import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import ValidationError

from doctours_reply.contract.reply import Reply
from doctours_reply.models.client import ChatRequest, ChatResponse, Message, ModelClient
from doctours_reply.runtime.context import TurnContext, fill_placeholders
from doctours_reply.runtime.escalation import DEFAULT_REASON, HANDOFF_SENTENCE, template_escalation
from doctours_reply.runtime.evidence import Evidence, Fact, build_evidence
from doctours_reply.runtime.executor import Executor
from doctours_reply.runtime.grounding import Violation
from doctours_reply.runtime.observation import Observation
from doctours_reply.runtime.outcome import Draft, Escalation, OutcomeStage, TerminalOutcome
from doctours_reply.runtime.validate import (
    check_answer,
    check_escalation_reason,
    check_escalation_sentence,
    repair_instructions,
)
from doctours_reply.tools.registry import TOOLS
from doctours_reply.trace.schema import ModelCall, TraceRecord, ValidationResult

LEGACY_DIR: Final = Path(__file__).resolve().parents[1] / "prompts" / "legacy"
MAX_TOOL_ROUNDS: Final = 3
ESCALATION_CODE: Final = "baseline_handoff"

CONTRACT_APPENDIX: Final = """\
OUTPUT CONTRACT FOR THIS HARNESS (overrides the output notes above where they differ)
Finish every turn with exactly one JSON object and nothing else, with these keys:
response, escalate, escalationReason, templateId, intent, shouldFollowUp, \
followUpTiming, attachmentUrls, highEngagement, workingMemoryUpdates.
- response: the reply in plain text. If it includes a URL, that URL is on the last line.
- templateId: always null.
- attachmentUrls: at most 3 URLs, only URLs a tool returned on this turn; [] when none.
- workingMemoryUpdates: only the memory fields that changed, or null.
- escalate: true only when a person must take over. That is when the patient asks for a \
human, or asks for something no tool and no rule here can do, such as charging a card, \
moving money that was already paid, or contacting a clinic to hold a date. When you \
escalate, response is one short sentence, you call no more tools, and you do not answer \
the rest of the message.
- escalationReason: a short reason when escalate is true, otherwise null."""

LEGACY_STATIC_LINKS: Final = (
    "https://www.doctours.com/image-upload",
    "https://www.doctours.com/consultation",
)
"""Static links the legacy prompt declares (packet L1453, L1462, L1467)."""

LEGACY_FACTS: Final = (
    Fact(
        "policy",
        "deposit-cancellation-fee",
        "Deposit cancellation fee",
        None,
        None,
        "cancellationFee",
        Decimal(25),
        "USD",
        "packet L1147",
        ("fee", "cancel"),
    ),
)
"""Money facts the legacy prompt states as policy rather than as an example."""

TOOL_SCHEMAS: Final = tuple(
    {
        "type": "function",
        "function": {"name": spec.name, "parameters": spec.args_model.model_json_schema()},
    }
    for spec in TOOLS.values()
)
REPLY_SCHEMA: Final = Reply.model_json_schema()
_JSON_REPAIR: Final = (
    "That was not a valid reply object: {error}\n"
    "Return only the JSON object described in the output contract. Do not call tools."
)

Purpose = Literal["turn", "json_repair", "validation_repair"]


def legacy_messages(ctx: TurnContext) -> list[Message]:
    constants = ctx.fixture.constants
    system = fill_placeholders((LEGACY_DIR / "system_prompt.txt").read_text("utf-8"), constants)
    user = fill_placeholders(
        (LEGACY_DIR / "user_message.txt").read_text("utf-8"),
        {
            "HUMAN_MESSAGE": ctx.message.text,
            "RECENT_CONVERSATION_SUMMARY": constants["RECENT_CONVERSATION_SUMMARY"],
        },
    )
    return [
        {"role": "system", "content": f"{system}\n\n{CONTRACT_APPENDIX}"},
        {"role": "user", "content": user},
    ]


def run_baseline(
    ctx: TurnContext, client: ModelClient, executor: Executor, trace: TraceRecord
) -> TerminalOutcome:
    messages = legacy_messages(ctx)
    response = _call(client, messages, trace, "turn", "auto")
    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        if not response.tool_calls:
            break
        messages.append(_assistant_tool_message(response))
        for call in response.tool_calls:
            observation = executor.execute(f"r{round_number}.{call.id}", call.name, call.arguments)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": _tool_content(observation)}
            )
        last = round_number == MAX_TOOL_ROUNDS
        response = _call(client, messages, trace, "turn", "none" if last else "auto")

    reply, error = _parse(response)
    if reply is None:
        messages += _follow_up(response, _JSON_REPAIR.format(error=error))
        response = _call(client, messages, trace, "json_repair", "none")
        reply, error = _parse(response)
        if reply is None:
            failure = template_escalation("controller_failure")
            return _escalated(executor, failure, "controller_failure")
    if reply.escalate:
        return _model_escalation(reply, ctx, executor, trace)

    evidence = _evidence(ctx, executor, messages)
    trace.fact_table = [{**asdict(f), "value": str(f.value)} for f in evidence.facts]
    draft = _draft(reply)
    violations = _validate(draft, evidence, ctx, trace)
    if not violations:
        return _answered(executor, draft)
    messages += _follow_up(response, repair_instructions(violations))
    response = _call(client, messages, trace, "validation_repair", "none")
    repaired, _ = _parse(response)
    if repaired is not None and repaired.escalate:
        return _model_escalation(repaired, ctx, executor, trace)
    if repaired is not None and not _validate(_draft(repaired), evidence, ctx, trace):
        return _answered(executor, _draft(repaired))
    return _escalated(executor, template_escalation("unverified_reply"), "validation")


def _call(
    client: ModelClient,
    messages: list[Message],
    trace: TraceRecord,
    purpose: Purpose,
    tool_choice: Literal["auto", "none"],
) -> ChatResponse:
    request = ChatRequest(
        messages=list(messages),
        response_schema=REPLY_SCHEMA,
        tools=TOOL_SCHEMAS,
        tool_choice=tool_choice,
    )
    response = client.complete(request)
    trace.model_calls.append(
        ModelCall(
            purpose=purpose,
            request_sha256=_request_hash(request),
            model_id=response.model_id or client.model_id,
            content=response.content,
            tool_calls=[
                {"id": c.id, "name": c.name, "arguments": c.arguments} for c in response.tool_calls
            ],
            finish_reason=response.finish_reason,
            prompt_tokens=response.prompt_tokens,
            cached_prompt_tokens=response.cached_prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            attempts=response.attempts,
        )
    )
    return response


def _request_hash(request: ChatRequest) -> str:
    payload = {
        "messages": list(request.messages),
        "tools": list(request.tools),
        "tool_choice": request.tool_choice,
        "response_schema": request.response_schema,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _assistant_tool_message(response: ChatResponse) -> Message:
    return {
        "role": "assistant",
        "content": response.content,
        "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in response.tool_calls
        ],
    }


def _tool_content(observation: Observation) -> str:
    if observation.status in ("ok", "null_result"):
        payload: Any = observation.result
    else:
        payload = {
            "status": observation.status,
            "reason": observation.reason,
            "result": observation.result,
        }
    return json.dumps(payload, ensure_ascii=False)


def _follow_up(response: ChatResponse, instruction: str) -> list[Message]:
    return [
        {"role": "assistant", "content": response.content or ""},
        {"role": "user", "content": instruction},
    ]


def _parse(response: ChatResponse) -> tuple[Reply | None, str | None]:
    if response.tool_calls or not response.content:
        return None, "expected a JSON object, got no content"
    try:
        return Reply.model_validate_json(response.content), None
    except ValidationError as exc:
        return None, "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'reply'}: {e['msg']}" for e in exc.errors()
        )


def _draft(reply: Reply) -> Draft:
    return Draft(
        response=reply.response,
        intent=reply.intent,
        shouldFollowUp=reply.shouldFollowUp,
        followUpTiming=reply.followUpTiming,
        attachmentUrls=reply.attachmentUrls,
        highEngagement=reply.highEngagement,
        workingMemoryUpdates=reply.workingMemoryUpdates,
    )


def _evidence(ctx: TurnContext, executor: Executor, messages: list[Message]) -> Evidence:
    shown = " ".join(str(m.get("content") or "") for m in messages[:2])
    return build_evidence(
        executor.observations,
        clinics=ctx.fixture.tool_data.clinics,
        static_facts=LEGACY_FACTS,
        static_links=LEGACY_STATIC_LINKS,
        shown_text=shown,
    )


def _validate(
    draft: Draft, evidence: Evidence, ctx: TurnContext, trace: TraceRecord
) -> list[Violation]:
    violations = check_answer(draft, evidence, ctx.message)
    trace.validations.append(
        ValidationResult(
            attempt=len(trace.validations) + 1, violations=[asdict(v) for v in violations]
        )
    )
    return violations


def _model_escalation(
    reply: Reply, ctx: TurnContext, executor: Executor, trace: TraceRecord
) -> TerminalOutcome:
    sentence = reply.response.strip()
    reason = (reply.escalationReason or "").strip()
    sentence_problems = check_escalation_sentence(sentence, ctx.message)
    reason_problems = check_escalation_reason(reason, ctx.message)
    trace.validations.append(
        ValidationResult(
            attempt=len(trace.validations) + 1,
            violations=[asdict(v) for v in sentence_problems + reason_problems],
        )
    )
    escalation = Escalation(
        code=ESCALATION_CODE,
        reason=DEFAULT_REASON if reason_problems else reason,
        sentence=HANDOFF_SENTENCE if sentence_problems else sentence,
    )
    return _escalated(executor, escalation, "decide")


def _answered(executor: Executor, draft: Draft) -> TerminalOutcome:
    return TerminalOutcome(
        kind="answered", stage=None, draft=draft, executed_writes=executor.executed_writes
    )


def _escalated(executor: Executor, escalation: Escalation, stage: OutcomeStage) -> TerminalOutcome:
    return TerminalOutcome(
        kind="escalated",
        stage=stage,
        escalation=escalation,
        executed_writes=executor.executed_writes,
    )
