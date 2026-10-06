"""S0 end to end on scripted model responses: no network, no live model."""

import json
from pathlib import Path

import pytest
from support import (
    CARD_DETAILS,
    GOLD_ID,
    HEVA_ANSWER,
    HEVA_ID,
    USER_ID,
    escalation_json,
    reply_json,
)

from doctours_reply.baseline.monolithic import MAX_TOOL_ROUNDS, TOOL_SCHEMAS
from doctours_reply.contract.io import InputItem
from doctours_reply.models.scripted import ScriptedModelClient, text_response, tool_response
from doctours_reply.runtime.escalation import DEFAULT_REASON, HANDOFF_SENTENCE
from doctours_reply.runtime.payment_data import CARD_NUMBER
from doctours_reply.runtime.pipeline import BLANK_MESSAGE_DRAFT, ItemResult, RunInfo, run_item
from doctours_reply.runtime.refs import Fixture, PolicySet
from doctours_reply.trace.sink import TraceSink

RUN = RunInfo("run-test", None, None)
HEVA = ("getClinicPackages", {"clinicName": "Heva"})
SAVE_GOLD = (
    "updateUserClinicPreferences",
    {
        "userId": USER_ID,
        "clinicSelection": {"selectedClinicId": HEVA_ID, "selectedPackageId": GOLD_ID},
    },
)


def _run(
    fixture: Fixture, policy_set: PolicySet, client: ScriptedModelClient, text: str = "Heva prices?"
) -> ItemResult:
    return run_item(
        0,
        InputItem(id="t1", text=text),
        fixture=fixture,
        policy_set=policy_set,
        client=client,
        run=RUN,
    )


def _purposes(result: ItemResult) -> list[str]:
    return [call.purpose for call in result.trace.model_calls]


def test_answered_turn(fixture: Fixture, policy_set: PolicySet) -> None:
    client = ScriptedModelClient([tool_response(HEVA), text_response(reply_json(HEVA_ANSWER))])
    result = _run(fixture, policy_set, client)
    assert (result.reply.escalate, result.reply.response) == (False, HEVA_ANSWER)
    assert result.reply.attachmentUrls == []
    assert _purposes(result) == ["turn", "turn"]
    assert [o.status for o in result.trace.observations] == ["ok"]
    assert [v.violations for v in result.trace.validations] == [[]]
    first, second = client.requests
    assert (first.model_role, second.model_role) == (None, None)
    assert first.tool_choice == "auto"
    assert first.tools == TOOL_SCHEMAS and len(TOOL_SCHEMAS) == 14
    assert second.messages[-1]["role"] == "tool"
    assert result.trace.outcome is not None and result.trace.outcome.kind == "answered"


def test_card_numbers_never_reach_the_model_trace_or_reply_rc_e_8(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    text = "Is it safe to send my card number here? It's 4242 4242 4242 4242."
    answer = "Please don't send card details here; checkout handles payment securely."
    client = ScriptedModelClient([text_response(reply_json(answer))])
    result = _run(fixture, policy_set, client, text)
    sent = json.dumps([r.messages for r in client.requests])
    assert CARD_NUMBER in sent
    for leaked in ("4242 4242", "4242424242424242", "4242-4242"):
        assert leaked not in sent
        assert leaked not in result.trace.model_dump_json()
        assert leaked not in result.reply.model_dump_json()
    assert result.trace.redactions == 1
    assert result.reply.escalate is False


@pytest.mark.parametrize(("text", "details"), CARD_DETAILS)
def test_card_details_never_reach_the_model_or_the_saved_trace(
    fixture: Fixture, policy_set: PolicySet, tmp_path: Path, text: str, details: tuple[str, ...]
) -> None:
    client = ScriptedModelClient([text_response(reply_json("Please don't send card details."))])
    result = _run(fixture, policy_set, client, text)
    sink = TraceSink(tmp_path)
    sink.write(result.trace)
    sent, saved = json.dumps([r.messages for r in client.requests]), sink.path.read_text()
    assert "[CARD_" in sent and "[CARD_" in saved
    for detail in details:
        assert detail not in sent and detail not in saved


def test_escalation_after_a_write_stops_tools_and_keeps_the_write_rc_w_4(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    client = ScriptedModelClient(
        [
            tool_response(HEVA),
            tool_response(SAVE_GOLD),
            text_response(escalation_json("I'm getting a person for you.", "Asked for a person")),
        ]
    )
    result = _run(fixture, policy_set, client, "Save Gold, then get me a human")
    outcome = result.trace.outcome
    assert outcome is not None
    assert (outcome.kind, outcome.stage, outcome.executed_writes) == (
        "escalated",
        "decide",
        ("r2.call_0",),
    )
    assert [o.tool for o in result.trace.observations] == [
        "getClinicPackages",
        "updateUserClinicPreferences",
    ]
    reply = result.reply
    assert (reply.escalate, reply.response, reply.escalationReason) == (
        True,
        "I'm getting a person for you.",
        "Asked for a person",
    )
    assert reply.workingMemoryUpdates is not None
    assert reply.workingMemoryUpdates.escalationFlags == "baseline_handoff"


def test_an_invalid_escalation_falls_back_to_templates(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    client = ScriptedModelClient(
        [text_response(escalation_json("Sure. Gold is $4,500 and I'll get someone.", "Card 4242"))]
    )
    result = _run(fixture, policy_set, client, "charge 4242 4242 4242 4242")
    assert (result.reply.response, result.reply.escalationReason) == (
        HANDOFF_SENTENCE,
        DEFAULT_REASON,
    )
    assert result.trace.validations[-1].violations


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all",
        json.dumps({"response": "Hi"}),
        json.dumps(reply_json("Hi", templateId="t")),
    ],
    ids=["text", "missing-fields", "template-id"],
)
def test_malformed_output_gets_one_json_repair(
    fixture: Fixture, policy_set: PolicySet, bad: str
) -> None:
    client = ScriptedModelClient([text_response(bad), text_response(reply_json("Happy to help."))])
    result = _run(fixture, policy_set, client, "hello")
    assert (result.reply.escalate, result.reply.response) == (False, "Happy to help.")
    assert _purposes(result) == ["turn", "json_repair"]
    repair = client.requests[1]
    assert repair.tool_choice == "none"
    assert "not a valid reply object" in repair.messages[-1]["content"]


def test_malformed_output_twice_is_a_controller_failure(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    client = ScriptedModelClient([text_response("nope"), tool_response(HEVA)])
    result = _run(fixture, policy_set, client, "hello")
    assert result.trace.outcome is not None
    assert result.trace.outcome.stage == "controller_failure"
    assert (result.reply.escalate, result.reply.escalationReason) == (
        True,
        "Automated reply failed",
    )
    assert result.trace.observations == []


def test_a_grounding_failure_is_repaired_once_rc_g_11(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    swapped = reply_json("Silver is $4,500 and Gold is $3,000.")
    client = ScriptedModelClient(
        [tool_response(HEVA), text_response(swapped), text_response(reply_json(HEVA_ANSWER))]
    )
    result = _run(fixture, policy_set, client)
    assert (result.reply.escalate, result.reply.response) == (False, HEVA_ANSWER)
    assert _purposes(result) == ["turn", "turn", "validation_repair"]
    first, second = result.trace.validations
    assert [v["code"] for v in first.violations] == ["wrong_value", "wrong_value"]
    assert second.violations == []
    instruction = client.requests[-1].messages[-1]["content"]
    assert "Correct value: Silver price is $3,000" in instruction
    assert "source: getClinicPackages" in instruction
    assert client.requests[-1].tool_choice == "none"


def test_a_second_grounding_failure_escalates_at_validation_rc_g_11(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    swapped = text_response(reply_json("Silver is $4,500 and Gold is $3,000."))
    client = ScriptedModelClient([tool_response(HEVA), swapped, swapped])
    result = _run(fixture, policy_set, client)
    assert result.trace.outcome is not None
    assert result.trace.outcome.stage == "validation"
    assert result.reply.escalationReason == "Reply could not be verified"
    assert result.reply.workingMemoryUpdates is not None
    assert result.reply.workingMemoryUpdates.escalationFlags == "unverified_reply"


def test_a_write_then_two_failed_drafts_keeps_the_write_rc_w_5(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    unlisted = text_response(reply_json("Saved.\nhttps://www.doctours.com/payment/made-up"))
    client = ScriptedModelClient(
        [tool_response(HEVA), tool_response(SAVE_GOLD), unlisted, unlisted]
    )
    result = _run(fixture, policy_set, client, "Save Gold")
    outcome = result.trace.outcome
    assert outcome is not None
    assert (outcome.stage, outcome.executed_writes) == ("validation", ("r2.call_0",))
    assert len(result.trace.observations) == 2


def test_tool_rounds_are_bounded(fixture: Fixture, policy_set: PolicySet) -> None:
    looping = tool_response(("getAllClinics", {}))
    client = ScriptedModelClient([looping] * (MAX_TOOL_ROUNDS + 2))
    result = _run(fixture, policy_set, client)
    assert len(result.trace.observations) == MAX_TOOL_ROUNDS
    assert [r.tool_choice for r in client.requests] == ["auto", "auto", "auto", "none", "none"]
    assert result.trace.outcome is not None
    assert result.trace.outcome.stage == "controller_failure"


def test_the_baseline_memory_call_runs_once_rc_w_8(fixture: Fixture, policy_set: PolicySet) -> None:
    memory = ("updateWorkingMemory", {"memory": {"preferredPaymentMethod": "pay_in_full"}})
    diff = {"preferredPaymentMethod": "pay_in_full"}
    client = ScriptedModelClient(
        [
            tool_response(memory),
            tool_response(memory),
            text_response(reply_json("Noted, paying in full works.", workingMemoryUpdates=diff)),
        ]
    )
    result = _run(fixture, policy_set, client, "I'll pay in full")
    assert [o.status for o in result.trace.observations] == ["ok", "duplicate_write"]
    assert result.reply.workingMemoryUpdates is not None
    assert result.reply.workingMemoryUpdates.model_dump(exclude_unset=True) == diff


def test_tool_failures_are_shown_to_the_model(fixture: Fixture, policy_set: PolicySet) -> None:
    client = ScriptedModelClient(
        [
            tool_response(("getClinicPackages", {"clinicId": HEVA_ID})),
            text_response(reply_json("I couldn't load Heva's packages just now.")),
        ]
    )
    result = _run(fixture, policy_set, client)
    shown = json.loads(client.requests[1].messages[-1]["content"])
    assert shown["status"] == "rejected"
    assert "clinicId" in shown["reason"]
    assert result.reply.escalate is False


def test_a_blank_message_needs_no_model_call(fixture: Fixture, policy_set: PolicySet) -> None:
    client = ScriptedModelClient([])
    result = _run(fixture, policy_set, client, "  \n ")
    assert client.requests == []
    assert result.reply.response == BLANK_MESSAGE_DRAFT.response
    assert result.reply.escalate is False
