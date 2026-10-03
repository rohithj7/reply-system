"""The model client interface. Requests are plain message lists and JSON schemas."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Message = Mapping[str, Any]


@dataclass(frozen=True)
class ChatRequest:
    messages: Sequence[Message]
    response_schema: Mapping[str, Any] | None = None
    """JSON schema the final message must satisfy; the client picks the provider format."""
    schema_name: str = "reply"
    tools: Sequence[Mapping[str, Any]] = ()
    tool_choice: Literal["auto", "none"] | None = None


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    model_id: str = ""
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 1


class ModelClient(Protocol):
    @property
    def model_id(self) -> str: ...

    def complete(self, request: ChatRequest) -> ChatResponse: ...


class ModelError(Exception):
    """Base class for model client failures. Messages never include credentials."""


class ModelConfigError(ModelError):
    """Required model configuration is missing or invalid."""


class ModelUnavailableError(ModelError):
    """The endpoint refused the request, or kept failing after bounded retries."""
