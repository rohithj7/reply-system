import inspect
import json

import pytest

from doctours_reply.contract.reply import CollectionState, WorkingMemoryUpdates
from doctours_reply.runtime import finalize as finalize_module
from doctours_reply.runtime import validate as validate_module
from doctours_reply.runtime.escalation import HANDOFF_SENTENCE, template_escalation
from doctours_reply.runtime.finalize import ESCALATION_INTENT, finalize
from doctours_reply.runtime.outcome import (
    Draft,
    Escalation,
    OutcomeAlreadySetError,
    OutcomeSlot,
    TerminalOutcome,
)
from doctours_reply.runtime.refs import Fixture

DRAFT = Draft(
    response="  Gold is $4,500.  ",
    intent="answer price",
    shouldFollowUp=True,
    followUpTiming="tomorrow",
    attachmentUrls=None,
    highEngagement=True,
    workingMemoryUpdates=WorkingMemoryUpdates(
        communicationStyle="casual",
        preferredPaymentMethod="financing",
        collectionState=CollectionState(areaAskCount=1, photoAskCount=2),
    ),
)


def _memory(fixture: Fixture) -> dict[str, object]:
    return json.loads(fixture.constants["WORKING_MEMORY"])


def test_answered_reply_drops_unchanged_memory_and_defaults_attachments(
    fixture: Fixture,
) -> None:
    outcome = TerminalOutcome(kind="answered", stage=None, draft=DRAFT)
    reply = finalize(outcome, _memory(fixture))
    assert reply.response == "Gold is $4,500."
    assert reply.attachmentUrls == []
    assert reply.workingMemoryUpdates is not None
    assert reply.workingMemoryUpdates.model_dump(exclude_unset=True) == {
        "preferredPaymentMethod": "financing",
        "collectionState": {"photoAskCount": 2},
    }


def test_an_all_unchanged_memory_diff_becomes_null(fixture: Fixture) -> None:
    draft = DRAFT.model_copy(
        update={"workingMemoryUpdates": WorkingMemoryUpdates(communicationStyle="casual")}
    )
    reply = finalize(TerminalOutcome(kind="answered", stage=None, draft=draft), _memory(fixture))
    assert reply.workingMemoryUpdates is None


def test_escalated_reply_takes_the_a18_fields(fixture: Fixture) -> None:
    outcome = TerminalOutcome(
        kind="escalated",
        stage="validation",
        escalation=template_escalation("unverified_reply"),
        executed_writes=("r1.call_0",),
    )
    reply = finalize(outcome, _memory(fixture))
    assert reply.escalate is True
    assert reply.response == HANDOFF_SENTENCE
    assert reply.escalationReason == "Reply could not be verified"
    assert (reply.intent, reply.shouldFollowUp, reply.followUpTiming) == (
        ESCALATION_INTENT,
        False,
        None,
    )
    assert (reply.attachmentUrls, reply.highEngagement) == ([], False)
    assert reply.workingMemoryUpdates is not None
    assert reply.workingMemoryUpdates.model_dump(exclude_unset=True) == {
        "escalationFlags": "unverified_reply"
    }


def test_outcome_fields_must_match_its_kind() -> None:
    with pytest.raises(ValueError):
        TerminalOutcome(kind="answered", stage="decide", draft=DRAFT)
    with pytest.raises(ValueError):
        TerminalOutcome(
            kind="escalated", stage=None, escalation=Escalation(code="x", reason="y", sentence="z")
        )


def test_the_outcome_is_set_once_rc_w_10() -> None:
    slot = OutcomeSlot()
    slot.set(TerminalOutcome(kind="answered", stage=None, draft=DRAFT))
    with pytest.raises(OutcomeAlreadySetError):
        slot.set(TerminalOutcome(kind="answered", stage=None, draft=DRAFT))


@pytest.mark.parametrize("module", [finalize_module, validate_module])
def test_finalizer_and_validators_get_no_tool_or_model_client_rc_w_10(module: object) -> None:
    source = inspect.getsource(module)  # type: ignore[arg-type]
    for name in ("Executor", "ModelClient", "TOOLS", "packet_tools"):
        assert name not in source
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if function.__module__ == module.__name__:  # type: ignore[attr-defined]
            params = inspect.signature(function).parameters
            assert not {"executor", "client", "tools"} & set(params), name


def test_finalize_is_pure(fixture: Fixture) -> None:
    memory = _memory(fixture)
    snapshot = json.dumps(memory, sort_keys=True)
    outcome = TerminalOutcome(kind="answered", stage=None, draft=DRAFT)
    assert finalize(outcome, memory) == finalize(outcome, memory)
    assert json.dumps(memory, sort_keys=True) == snapshot
