"""An OpenAI-compatible chat client, configured only from environment variables.

Retries are bounded and apply to timeouts, connection errors, HTTP 429 and 5xx. Other
HTTP errors fail at once. Error messages name the error class and status only, never
the key or the request.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

import openai
from openai.types.shared import ReasoningEffort

from doctours_reply.models.client import (
    ChatRequest,
    ChatResponse,
    ModelConfigError,
    ModelUnavailableError,
    ToolCall,
)

StructuredOutput = Literal["json_schema", "json_object"]
_REASONING_EFFORTS: tuple[str, ...] = get_args(get_args(ReasoningEffort)[0])
_RETRYABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)
_ENV = {
    "MODEL": ("MODEL_BASE_URL", "MODEL_API_KEY", "MODEL_ID"),
    "JUDGE": ("JUDGE_BASE_URL", "JUDGE_API_KEY", "JUDGE_MODEL_ID"),
}


@dataclass(frozen=True)
class ModelSettings:
    base_url: str
    api_key: str = field(repr=False)
    model_id: str
    timeout_seconds: float = 60.0
    max_retries: int = 3
    structured_output: StructuredOutput = "json_schema"
    temperature: float | None = None
    reasoning_effort: str | None = None

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str], prefix: Literal["MODEL", "JUDGE"] = "MODEL"
    ) -> "ModelSettings":
        """Read `<prefix>_BASE_URL`, `<prefix>_API_KEY` and the model ID, plus optional knobs.

        Optional: `<prefix>_TIMEOUT_SECONDS`, `<prefix>_MAX_RETRIES`,
        `<prefix>_STRUCTURED_OUTPUT` (`json_schema` or `json_object`), `<prefix>_TEMPERATURE`
        and `<prefix>_REASONING_EFFORT`. Unset temperature and reasoning effort are not sent.
        """
        names = _ENV[prefix]
        missing = [name for name in names if not environ.get(name, "").strip()]
        if missing:
            raise ModelConfigError(f"missing required environment variables: {', '.join(missing)}")
        base_url, api_key, model_id = (environ[name].strip() for name in names)
        if not base_url.startswith(("https://", "http://")):
            raise ModelConfigError(f"{names[0]} must be an http(s) URL")
        try:
            timeout = float(environ.get(f"{prefix}_TIMEOUT_SECONDS", "60"))
            retries = int(environ.get(f"{prefix}_MAX_RETRIES", "3"))
            temperature_text = environ.get(f"{prefix}_TEMPERATURE", "").strip()
            temperature = float(temperature_text) if temperature_text else None
        except ValueError as exc:
            raise ModelConfigError(f"invalid numeric {prefix}_* setting: {exc}") from None
        structured: StructuredOutput
        match environ.get(f"{prefix}_STRUCTURED_OUTPUT", "json_schema"):
            case "json_schema":
                structured = "json_schema"
            case "json_object":
                structured = "json_object"
            case _:
                raise ModelConfigError(
                    f"{prefix}_STRUCTURED_OUTPUT must be json_schema or json_object"
                )
        if timeout <= 0 or not 0 <= retries <= 10:
            raise ModelConfigError(f"{prefix}_TIMEOUT_SECONDS must be > 0 and retries 0-10")
        reasoning = environ.get(f"{prefix}_REASONING_EFFORT", "").strip() or None
        if reasoning is not None and reasoning not in _REASONING_EFFORTS:
            raise ModelConfigError(
                f"{prefix}_REASONING_EFFORT must be one of {', '.join(_REASONING_EFFORTS)}"
            )
        return cls(
            base_url, api_key, model_id, timeout, retries, structured, temperature, reasoning
        )

    def public_config(self) -> dict[str, Any]:
        """Settings safe to record in traces and reports: no key, no full endpoint URL."""
        host = self.base_url.split("://", 1)[1].split("/", 1)[0]
        return {
            "model_id": self.model_id,
            "endpoint_host": host,
            "structured_output": self.structured_output,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


class OpenAICompatClient:
    def __init__(
        self,
        settings: ModelSettings,
        *,
        sdk: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._sdk = sdk or openai.OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )
        self._sleep = sleep

    @property
    def model_id(self) -> str:
        return self._settings.model_id

    def complete(self, request: ChatRequest) -> ChatResponse:
        kwargs: dict[str, Any] = {"model": self.model_id, "messages": list(request.messages)}
        if request.tools:
            kwargs["tools"] = list(request.tools)
            if request.tool_choice is not None:
                kwargs["tool_choice"] = request.tool_choice
        if request.response_schema is not None:
            kwargs["response_format"] = self._response_format(request)
        if self._settings.temperature is not None:
            kwargs["temperature"] = self._settings.temperature
        if self._settings.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self._settings.reasoning_effort
        started = time.monotonic()
        attempts = self._settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                completion = self._sdk.chat.completions.create(**kwargs)
                break
            except _RETRYABLE as exc:
                if attempt == attempts:
                    raise ModelUnavailableError(
                        f"model endpoint failed after {attempt} attempts ({_describe(exc)})"
                    ) from None
                self._sleep(min(2.0 ** (attempt - 1), 8.0))
            except openai.APIStatusError as exc:
                raise ModelUnavailableError(
                    f"model endpoint rejected the request ({_describe(exc)})"
                ) from None
            except openai.OpenAIError as exc:
                raise ModelUnavailableError(f"model client error ({_describe(exc)})") from None
        return _to_response(completion, started, attempt)

    def _response_format(self, request: ChatRequest) -> dict[str, Any]:
        if self._settings.structured_output == "json_object":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": request.schema_name,
                "schema": dict(request.response_schema or {}),
                "strict": False,
            },
        }


def _describe(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    return type(exc).__name__ + (f", HTTP {status}" if status is not None else "")


def _to_response(completion: Any, started: float, attempts: int) -> ChatResponse:
    latency = round((time.monotonic() - started) * 1000)
    choices = getattr(completion, "choices", None) or []
    message = choices[0].message if choices else None
    calls = tuple(
        ToolCall(call.id, call.function.name, call.function.arguments or "")
        for call in (getattr(message, "tool_calls", None) or [])
        if getattr(call, "function", None) is not None
    )
    usage = getattr(completion, "usage", None)
    details = getattr(usage, "prompt_tokens_details", None)
    return ChatResponse(
        content=getattr(message, "content", None),
        tool_calls=calls,
        model_id=getattr(completion, "model", None) or "",
        finish_reason=choices[0].finish_reason if choices else None,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        cached_prompt_tokens=getattr(details, "cached_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        latency_ms=latency,
        attempts=attempts,
    )
