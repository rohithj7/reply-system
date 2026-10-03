import json
import random
import time
from pathlib import Path

import pytest
from support import reply_json

from doctours_reply.contract.io import InputItem
from doctours_reply.models.client import ChatRequest, ChatResponse, ModelUnavailableError
from doctours_reply.models.scripted import ScriptedModelClient, text_response, tool_response
from doctours_reply.runtime.pipeline import ItemFailedError, RunInfo, run_batch
from doctours_reply.runtime.refs import Fixture, PolicySet
from doctours_reply.trace.sink import TraceSink

RUN = RunInfo("run-test", None, None)
WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
MEMORY = ("updateWorkingMemory", {"memory": {"keyConcerns": "cost"}})


def _word(request: ChatRequest) -> str:
    content = str(request.messages[1]["content"])
    return next(word for word in WORDS if f"word {word}" in content)


class _PerItemClient:
    """Each item writes memory once, then answers with its own word after a random delay."""

    model_id = "scripted"

    def complete(self, request: ChatRequest) -> ChatResponse:
        word = _word(request)
        time.sleep(random.uniform(0, 0.02))
        if request.messages[-1]["role"] != "tool":
            return tool_response(MEMORY)
        return text_response(reply_json(f"Reply for {word}."))


def _items(words: list[str]) -> list[InputItem]:
    return [InputItem(id=f"id-{w}", text=f"word {w}") for w in words]


def test_replies_follow_input_order_under_concurrency(
    fixture: Fixture, policy_set: PolicySet
) -> None:
    results = run_batch(
        _items(WORDS),
        fixture=fixture,
        policy_set=policy_set,
        client=_PerItemClient(),
        run=RUN,
        concurrency=4,
    )
    assert [r.reply.response for r in results] == [f"Reply for {w}." for w in WORDS]
    assert [r.trace.item_index for r in results] == list(range(len(WORDS)))


def test_items_are_isolated_and_order_independent(fixture: Fixture, policy_set: PolicySet) -> None:
    shuffled = random.Random(7).sample(WORDS, len(WORDS))
    results = {
        r.trace.item_id: r
        for words in (WORDS, shuffled)
        for r in run_batch(
            _items(words),
            fixture=fixture,
            policy_set=policy_set,
            client=_PerItemClient(),
            run=RUN,
            concurrency=3,
        )
    }
    for word in WORDS:
        result = results[f"id-{word}"]
        assert result.reply.response == f"Reply for {word}."
        assert [o.status for o in result.trace.observations] == ["ok"]


def test_an_outage_after_a_write_stops_the_batch_and_keeps_the_trace_rc_w_9(
    fixture: Fixture, policy_set: PolicySet, tmp_path: Path
) -> None:
    client = ScriptedModelClient(
        [tool_response(MEMORY), ModelUnavailableError("model endpoint failed after 4 attempts")]
    )
    sink = TraceSink(tmp_path)
    with pytest.raises(ItemFailedError) as raised:
        run_batch(
            _items(["alpha", "bravo"]),
            fixture=fixture,
            policy_set=policy_set,
            client=client,
            run=RUN,
            sink=sink,
        )
    assert raised.value.index == 0
    records = [json.loads(line) for line in sink.path.read_text().splitlines()]
    assert [r["item_id"] for r in records] == ["id-alpha"]
    assert records[0]["error"].startswith("model endpoint failed")
    assert [(o["tool"], o["status"]) for o in records[0]["observations"]] == [
        ("updateWorkingMemory", "ok")
    ]
    assert records[0]["reply"] is None
