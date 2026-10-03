import json

import pytest

from doctours_reply.contract.io import InputContractError, InputItem, dump_replies, parse_input
from doctours_reply.contract.reply import Reply


def test_valid_array_parses_in_order() -> None:
    items = parse_input(json.dumps([{"id": "b", "text": "two"}, {"id": "a", "text": "one"}]))
    assert items == [InputItem(id="b", text="two"), InputItem(id="a", text="one")]


def test_empty_array_and_duplicate_ids_are_accepted() -> None:
    assert parse_input("[]") == []
    items = parse_input(json.dumps([{"id": "x", "text": "a"}, {"id": "x", "text": "b"}]))
    assert [item.text for item in items] == ["a", "b"]


def test_blank_text_and_extra_keys_are_accepted() -> None:
    (item,) = parse_input(json.dumps([{"id": "x", "text": "", "channel": "sms"}]))
    assert item == InputItem(id="x", text="")


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        '{"id": "x", "text": "a"}',
        '"text"',
        '[{"id": "x"}]',
        '[{"text": "a"}]',
        '[{"id": 1, "text": "a"}]',
        '[{"id": "x", "text": null}]',
        '[{"id": "x", "text": ["a"]}]',
        '["a"]',
    ],
)
def test_malformed_input_raises_a_typed_error(raw: str) -> None:
    with pytest.raises(InputContractError):
        parse_input(raw)


def test_dump_replies_preserves_order_and_omits_unset_memory_keys() -> None:
    replies = [
        Reply.model_validate(
            {
                "response": text,
                "escalate": False,
                "escalationReason": None,
                "templateId": None,
                "intent": "question",
                "shouldFollowUp": False,
                "followUpTiming": None,
                "attachmentUrls": [],
                "highEngagement": False,
                "workingMemoryUpdates": {"keyConcerns": "cost"},
            }
        )
        for text in ("first", "second")
    ]
    out = json.loads(dump_replies(replies))
    assert [reply["response"] for reply in out] == ["first", "second"]
    assert out[0]["workingMemoryUpdates"] == {"keyConcerns": "cost"}
    assert "id" not in out[0]
