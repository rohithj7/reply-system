import json
import typing
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from doctours_reply.contract.reply import CollectionState, Reply, WorkingMemoryUpdates

REPO_ROOT = Path(__file__).resolve().parents[2]


def _reply(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "response": "Hello.",
        "escalate": False,
        "escalationReason": None,
        "templateId": None,
        "intent": "greeting",
        "shouldFollowUp": False,
        "followUpTiming": None,
        "attachmentUrls": [],
        "highEngagement": False,
        "workingMemoryUpdates": None,
    }
    base.update(overrides)
    return base


def test_valid_reply_round_trips() -> None:
    raw = json.dumps(_reply(attachmentUrls=["https://a.example/1"], followUpTiming="tomorrow"))
    reply = Reply.model_validate_json(raw)
    assert json.loads(raw) == reply.model_dump(mode="json", exclude_unset=True)


def test_every_field_is_required() -> None:
    for field in Reply.model_fields:
        data = _reply()
        del data[field]
        with pytest.raises(ValidationError):
            Reply.model_validate(data)


@pytest.mark.parametrize("extra", ["id", "message", "templateName"])
def test_extra_fields_are_rejected(extra: str) -> None:
    with pytest.raises(ValidationError):
        Reply.model_validate(_reply(**{extra: "x"}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("response", 1),
        ("response", None),
        ("escalate", "true"),
        ("escalate", 1),
        ("escalationReason", 5),
        ("templateId", "template-1"),
        ("intent", None),
        ("shouldFollowUp", 0),
        ("followUpTiming", 3),
        ("attachmentUrls", "https://a.example/1"),
        ("attachmentUrls", [1]),
        ("highEngagement", "no"),
        ("workingMemoryUpdates", "x"),
        ("workingMemoryUpdates", {"patientName": 1}),
        ("workingMemoryUpdates", {"collectionState": {"areaAskCount": "1"}}),
        ("workingMemoryUpdates", {"collectionState": {"areaAskCount": True}}),
        ("workingMemoryUpdates", {"collectionState": {"extra": 1}}),
        ("workingMemoryUpdates", {"unknownKey": "x"}),
    ],
)
def test_wrong_types_are_rejected(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        Reply.model_validate_json(json.dumps(_reply(**{field: value})))


@pytest.mark.parametrize("field", ["followUpTiming", "attachmentUrls", "workingMemoryUpdates"])
def test_nullable_fields_accept_null(field: str) -> None:
    Reply.model_validate(_reply(**{field: None}))


def test_attachment_urls_hold_at_most_three() -> None:
    Reply.model_validate(_reply(attachmentUrls=["https://a.example/1"] * 3))
    with pytest.raises(ValidationError):
        Reply.model_validate(_reply(attachmentUrls=["https://a.example/1"] * 4))


def test_escalation_reason_tracks_escalate() -> None:
    Reply.model_validate(_reply(escalate=True, escalationReason="Asked for a person"))
    for bad in (
        {"escalate": True, "escalationReason": None},
        {"escalate": True, "escalationReason": "  "},
        {"escalate": False, "escalationReason": "Asked for a person"},
    ):
        with pytest.raises(ValidationError):
            Reply.model_validate(_reply(**bad))


def _literal_values(model: type[BaseModel], field: str) -> tuple[str, ...]:
    annotation = model.model_fields[field].annotation
    (literal,) = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
    return typing.get_args(literal)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("communicationStyle", ("detailed", "concise", "casual", "formal", "unknown")),
        (
            "preferredPaymentMethod",
            ("financing", "layaway", "pay_in_full", "cash_preference", "unknown"),
        ),
        (
            "targetProcedureWindow",
            (
                "within_3_months",
                "within_6_months",
                "within_8_months",
                "within_12_months",
                "over_12_months",
                "unknown",
            ),
        ),
    ],
)
def test_memory_enums_match_the_packet(field: str, expected: tuple[str, ...]) -> None:
    assert _literal_values(WorkingMemoryUpdates, field) == expected
    for value in (*expected, None):
        WorkingMemoryUpdates.model_validate({field: value})
    with pytest.raises(ValidationError):
        WorkingMemoryUpdates.model_validate({field: "other"})


def test_last_asked_item_enum_matches_the_packet() -> None:
    expected = ("area", "name", "photos", "none")
    assert _literal_values(CollectionState, "lastAskedItem") == expected
    for value in (*expected, None):
        CollectionState.model_validate({"lastAskedItem": value})
    with pytest.raises(ValidationError):
        CollectionState.model_validate({"lastAskedItem": "email"})


def test_unset_memory_keys_are_omitted_and_explicit_nulls_kept() -> None:
    memory = WorkingMemoryUpdates.model_validate(
        {"patientName": "Jordan", "promisesMade": None, "collectionState": {"nameAskCount": 2}}
    )
    reply = Reply.model_validate(_reply(workingMemoryUpdates=memory))
    assert reply.model_dump(mode="json", exclude_unset=True)["workingMemoryUpdates"] == {
        "patientName": "Jordan",
        "promisesMade": None,
        "collectionState": {"nameAskCount": 2},
    }


def test_schema_snapshot_matches_the_models() -> None:
    snapshot = (REPO_ROOT / "schemas" / "reply.schema.json").read_text(encoding="utf-8")
    assert snapshot == json.dumps(Reply.model_json_schema(), indent=2) + "\n", (
        "regenerate with: uv run python -m doctours_reply.contract > schemas/reply.schema.json"
    )
