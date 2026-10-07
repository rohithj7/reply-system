from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

from doctours_reply.models.client import ChatRequest, ModelConfigError, ModelUnavailableError
from doctours_reply.models.openai_compat import ModelSettings, OpenAICompatClient

KEY = "sk-test-not-a-real-key"
ENV = {
    "MODEL_BASE_URL": "https://models.example.invalid/v1",
    "MODEL_API_KEY": KEY,
    "MODEL_ID": "m1",
}
REQUEST = httpx2.Request("POST", "https://models.example.invalid/v1/chat/completions")


def _status(cls: type[openai.APIStatusError], code: int) -> openai.APIStatusError:
    return cls("failed", response=httpx2.Response(code, request=REQUEST), body=None)


def _completion(content: str = "{}") -> Any:
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=3,
            prompt_tokens_details=SimpleNamespace(cached_tokens=8),
        ),
        model="m1-2026",
    )


class FakeSDK:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(sdk: FakeSDK, **env: str) -> tuple[OpenAICompatClient, list[float]]:
    sleeps: list[float] = []
    settings = ModelSettings.from_env({**ENV, **env})
    return OpenAICompatClient(settings, sdk=sdk, sleep=sleeps.append), sleeps


def _request(**fields: Any) -> ChatRequest:
    return ChatRequest(messages=[{"role": "user", "content": "hi"}], **fields)


def test_settings_come_from_the_environment_and_hide_the_key() -> None:
    settings = ModelSettings.from_env({**ENV, "MODEL_TEMPERATURE": "0", "MODEL_MAX_RETRIES": "1"})
    assert (settings.model_id, settings.temperature, settings.max_retries) == ("m1", 0.0, 1)
    assert KEY not in repr(settings)
    public = settings.public_config()
    assert public["endpoint_host"] == "models.example.invalid"
    assert public["reasoning_effort"] is None
    assert KEY not in str(public)
    effort = ModelSettings.from_env({**ENV, "MODEL_REASONING_EFFORT": " none "})
    assert effort.public_config()["reasoning_effort"] == "none"


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "MODEL_BASE_URL, MODEL_API_KEY, MODEL_ID"),
        ({**ENV, "MODEL_ID": " "}, "MODEL_ID"),
        ({**ENV, "MODEL_BASE_URL": "models.example.invalid"}, "http(s) URL"),
        ({**ENV, "MODEL_STRUCTURED_OUTPUT": "xml"}, "json_schema or json_object"),
        ({**ENV, "MODEL_MAX_RETRIES": "many"}, "invalid numeric"),
        ({**ENV, "MODEL_REASONING_EFFORT": "off"}, "MODEL_REASONING_EFFORT must be one of none"),
    ],
)
def test_missing_or_invalid_settings_are_reported(env: dict[str, str], message: str) -> None:
    with pytest.raises(ModelConfigError, match=message.replace("(", r"\(").replace(")", r"\)")):
        ModelSettings.from_env(env)


def test_judge_settings_use_their_own_prefix() -> None:
    with pytest.raises(ModelConfigError, match="JUDGE_BASE_URL"):
        ModelSettings.from_env(ENV, "JUDGE")
    judge_env = {
        "JUDGE_BASE_URL": ENV["MODEL_BASE_URL"],
        "JUDGE_API_KEY": KEY,
        "JUDGE_MODEL_ID": "j1",
        "CONTROLLER_MODEL_ID": "c1",
    }
    assert ModelSettings.from_env(judge_env, "JUDGE").model_for("controller") == "j1"


def test_controller_and_writer_requests_go_to_their_own_model_ids() -> None:
    unnamed = _completion()
    unnamed.model = None
    sdk = FakeSDK(_completion(), unnamed, _completion())
    client, _ = _client(sdk, CONTROLLER_MODEL_ID=" controller-lora ", WRITER_MODEL_ID=" ")
    responses = [client.complete(_request(model_role=role)) for role in ("writer", "controller")]
    client.complete(_request())
    assert [call["model"] for call in sdk.calls] == ["m1", "controller-lora", "m1"]
    assert responses[1].model_id == "controller-lora"
    public = ModelSettings.from_env({**ENV, "WRITER_MODEL_ID": "w1"}).public_config()
    assert (public["controller_model_id"], public["writer_model_id"]) == (None, "w1")


@pytest.mark.parametrize(
    "error",
    [
        _status(openai.RateLimitError, 429),
        _status(openai.InternalServerError, 503),
        openai.APITimeoutError(request=REQUEST),
        openai.APIConnectionError(request=REQUEST),
    ],
    ids=["429", "503", "timeout", "connection"],
)
def test_transient_failures_are_retried_with_bounded_backoff(error: Exception) -> None:
    sdk = FakeSDK(error, error, _completion("ok"))
    client, sleeps = _client(sdk)
    response = client.complete(_request())
    assert (response.content, response.attempts, response.model_id) == ("ok", 3, "m1-2026")
    assert (response.prompt_tokens, response.completion_tokens) == (11, 3)
    assert response.cached_prompt_tokens == 8
    assert sleeps == [1.0, 2.0]


def test_retries_run_out_into_an_unavailable_error_without_secrets() -> None:
    error = _status(openai.InternalServerError, 500)
    sdk = FakeSDK(*[error] * 4)
    client, sleeps = _client(sdk)
    with pytest.raises(ModelUnavailableError) as raised:
        client.complete(_request())
    assert "after 4 attempts" in str(raised.value)
    assert "HTTP 500" in str(raised.value)
    assert KEY not in str(raised.value)
    assert raised.value.__cause__ is None
    assert sleeps == [1.0, 2.0, 4.0]


@pytest.mark.parametrize(
    "error",
    [_status(openai.AuthenticationError, 401), _status(openai.BadRequestError, 400)],
    ids=["401", "400"],
)
def test_client_errors_are_not_retried(error: Exception) -> None:
    sdk = FakeSDK(error, _completion())
    client, sleeps = _client(sdk)
    with pytest.raises(ModelUnavailableError, match="rejected"):
        client.complete(_request())
    assert (len(sdk.calls), sleeps) == (1, [])


def test_request_shape_for_each_structured_output_mode() -> None:
    tools = ({"type": "function", "function": {"name": "getAllClinics", "parameters": {}}},)
    request = _request(response_schema={"type": "object"}, tools=tools, tool_choice="none")
    sdk = FakeSDK(_completion(), _completion())
    _client(sdk)[0].complete(request)
    _client(
        sdk,
        MODEL_STRUCTURED_OUTPUT="json_object",
        MODEL_TEMPERATURE="0.2",
        MODEL_REASONING_EFFORT="none",
    )[0].complete(request)
    schema_call, object_call = sdk.calls
    assert schema_call["response_format"]["type"] == "json_schema"
    assert schema_call["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert (schema_call["tool_choice"], "temperature" in schema_call) == ("none", False)
    assert "reasoning_effort" not in schema_call
    assert object_call["response_format"] == {"type": "json_object"}
    assert (object_call["temperature"], object_call["reasoning_effort"]) == (0.2, "none")


def test_tool_calls_are_mapped() -> None:
    call = SimpleNamespace(
        id="call_1", function=SimpleNamespace(name="getAllClinics", arguments=None)
    )
    completion = _completion()
    completion.choices[0].message = SimpleNamespace(content=None, tool_calls=[call])
    response = _client(FakeSDK(completion))[0].complete(_request())
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [
        ("call_1", "getAllClinics", "")
    ]
