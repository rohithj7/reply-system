"""Live smoke test against the configured endpoint. Opt in with RUN_LIVE=1 and MODEL_*."""

import os

import pytest

from doctours_reply.baseline.monolithic import REPLY_SCHEMA, TOOL_SCHEMAS
from doctours_reply.contract.io import InputItem
from doctours_reply.models.client import ChatRequest
from doctours_reply.models.openai_compat import ModelSettings, OpenAICompatClient
from doctours_reply.runtime.pipeline import RunInfo, run_batch
from doctours_reply.runtime.refs import resolve_fixture, resolve_policy_set

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to run"),
]


@pytest.fixture(scope="module")
def client() -> OpenAICompatClient:
    return OpenAICompatClient(ModelSettings.from_env(os.environ))


def test_endpoint_supports_tool_calls_and_structured_output(client: OpenAICompatClient) -> None:
    tools = client.complete(
        ChatRequest(
            messages=[{"role": "user", "content": "List the clinics. Use the tool."}],
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
    )
    assert tools.tool_calls, "the endpoint returned no tool call"
    reply = client.complete(
        ChatRequest(
            messages=[{"role": "user", "content": "Return a reply object saying hello."}],
            response_schema=REPLY_SCHEMA,
        )
    )
    assert reply.content


def test_the_baseline_returns_valid_replies(client: OpenAICompatClient) -> None:
    items = [
        InputItem(id="smoke-price", text="How much is Silver at Heva?"),
        InputItem(id="smoke-hold", text="Can you hold June 3 at Heva for me?"),
    ]
    results = run_batch(
        items,
        fixture=resolve_fixture("packet"),
        policy_set=resolve_policy_set("shipped"),
        client=client,
        run=RunInfo("live-smoke", None, None),
    )
    assert [r.trace.item_id for r in results] == ["smoke-price", "smoke-hold"]
    assert all(r.reply.templateId is None for r in results)
