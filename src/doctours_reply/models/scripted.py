"""A network-free client that replays scripted responses and records every request.

Used by the test suite and for scripted traces; it never contacts an endpoint.
"""

import json
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from doctours_reply.models.client import ChatRequest, ChatResponse, ToolCall

Step = ChatResponse | Exception
Responder = Callable[[ChatRequest], Step]


class ScriptedModelClient:
    model_id = "scripted"

    def __init__(self, script: Sequence[Step] | Responder) -> None:
        self._responder = script if callable(script) else None
        self._remaining = [] if callable(script) else list(script)
        self._lock = threading.Lock()
        self.requests: list[ChatRequest] = []

    def complete(self, request: ChatRequest) -> ChatResponse:
        with self._lock:
            self.requests.append(request)
            if self._responder is not None:
                step = self._responder(request)
            elif self._remaining:
                step = self._remaining.pop(0)
            else:
                raise LookupError("scripted responses exhausted")
        if isinstance(step, Exception):
            raise step
        return step


def text_response(content: str | Mapping[str, Any]) -> ChatResponse:
    """A final message; mappings are serialized as JSON."""
    text = content if isinstance(content, str) else json.dumps(content)
    return ChatResponse(content=text, model_id=ScriptedModelClient.model_id)


def tool_response(*calls: tuple[str, Mapping[str, Any]]) -> ChatResponse:
    """A message that requests the given `(tool name, arguments)` calls."""
    return ChatResponse(
        content=None,
        tool_calls=tuple(
            ToolCall(f"call_{i}", name, json.dumps(args)) for i, (name, args) in enumerate(calls)
        ),
        model_id=ScriptedModelClient.model_id,
    )
