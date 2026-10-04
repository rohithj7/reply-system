"""Send one model request and record it in the item's trace; parse its JSON answer."""

import hashlib
import json

from pydantic import BaseModel, ValidationError

from doctours_reply.models.client import ChatRequest, ChatResponse, Message, ModelClient
from doctours_reply.trace.schema import ModelCall, Purpose, TraceRecord


def complete(
    client: ModelClient, request: ChatRequest, trace: TraceRecord, purpose: Purpose
) -> ChatResponse:
    response = client.complete(request)
    trace.model_calls.append(
        ModelCall(
            purpose=purpose,
            request_sha256=request_hash(request),
            model_id=response.model_id or client.model_id,
            content=response.content,
            tool_calls=[
                {"id": c.id, "name": c.name, "arguments": c.arguments} for c in response.tool_calls
            ],
            finish_reason=response.finish_reason,
            prompt_tokens=response.prompt_tokens,
            cached_prompt_tokens=response.cached_prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            attempts=response.attempts,
        )
    )
    return response


def parse_json[M: BaseModel](response: ChatResponse, model: type[M]) -> tuple[M | None, list[str]]:
    if response.tool_calls or not response.content:
        return None, ["expected a JSON object, got no content"]
    try:
        return model.model_validate_json(response.content), []
    except ValidationError as exc:
        errors = exc.errors()
        return None, [f"{'.'.join(map(str, e['loc'])) or 'object'}: {e['msg']}" for e in errors]


def follow_up(response: ChatResponse, instruction: str) -> list[Message]:
    return [
        {"role": "assistant", "content": response.content or ""},
        {"role": "user", "content": instruction},
    ]


def request_hash(request: ChatRequest) -> str:
    payload = {
        "messages": list(request.messages),
        "tools": list(request.tools),
        "tool_choice": request.tool_choice,
        "response_schema": request.response_schema,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
