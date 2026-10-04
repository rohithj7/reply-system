"""S1 writer: the grounded patient-facing reply (decision record 0002).

The writer has no tool client. It sees the loaded policies, the context and this
turn's tool results; its draft goes through the shared validators with one JSON repair
and one validation repair, as S0's does.
"""

from dataclasses import asdict
from typing import Final

from doctours_reply.models.client import ChatRequest, Message, ModelClient
from doctours_reply.runtime.evidence import Evidence
from doctours_reply.runtime.grounding import Violation
from doctours_reply.runtime.model_calls import complete, follow_up, parse_json
from doctours_reply.runtime.outcome import Draft, OutcomeStage
from doctours_reply.runtime.payment_data import RedactedText
from doctours_reply.runtime.policy_loader import LoadedPolicies
from doctours_reply.runtime.validate import check_answer, check_policy_phrases, repair_instructions
from doctours_reply.trace.schema import TraceRecord, ValidationResult

DRAFT_SCHEMA: Final = Draft.model_json_schema()
_JSON_REPAIR: Final = (
    "That was not a valid reply object: {error}\nReturn only the JSON object with the listed keys."
)


def write_reply(
    client: ModelClient,
    messages: list[Message],
    trace: TraceRecord,
    evidence: Evidence,
    message: RedactedText,
    policies: LoadedPolicies,
) -> Draft | OutcomeStage:
    """Return a validated draft, or the stage that failed."""
    response = complete(client, _request(messages), trace, "write")
    draft, problems = parse_json(response, Draft)
    if draft is None:
        messages = [*messages, *follow_up(response, _JSON_REPAIR.format(error="; ".join(problems)))]
        response = complete(client, _request(messages), trace, "json_repair")
        draft, _ = parse_json(response, Draft)
        if draft is None:
            return "controller_failure"
    violations = _validate(draft, evidence, message, policies, trace)
    if not violations:
        return draft
    messages = [*messages, *follow_up(response, repair_instructions(violations))]
    response = complete(client, _request(messages), trace, "validation_repair")
    repaired, _ = parse_json(response, Draft)
    if repaired is not None and not _validate(repaired, evidence, message, policies, trace):
        return repaired
    return "validation"


def _request(messages: list[Message]) -> ChatRequest:
    return ChatRequest(messages=list(messages), response_schema=DRAFT_SCHEMA, schema_name="reply")


def _validate(
    draft: Draft,
    evidence: Evidence,
    message: RedactedText,
    policies: LoadedPolicies,
    trace: TraceRecord,
) -> list[Violation]:
    violations = check_answer(draft, evidence, message)
    violations += check_policy_phrases(draft.response, policies.forbidden_patterns)
    record_validation(trace, violations)
    return violations


def record_validation(trace: TraceRecord, violations: list[Violation]) -> None:
    trace.validations.append(
        ValidationResult(
            attempt=len(trace.validations) + 1, violations=[asdict(v) for v in violations]
        )
    )
