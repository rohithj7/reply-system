"""The trace record: one JSON line per item. Plain JSON, independent of any framework."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from doctours_reply.contract.reply import Reply
from doctours_reply.runtime.observation import Observation
from doctours_reply.runtime.outcome import TerminalOutcome

TRACE_VERSION: Literal["1"] = "1"


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


Purpose = Literal["turn", "json_repair", "validation_repair", "route", "decide", "write"]


class ModelCall(_Record):
    purpose: Purpose
    request_sha256: str
    model_id: str
    content: str | None
    tool_calls: list[dict[str, str]]
    finish_reason: str | None
    prompt_tokens: int
    cached_prompt_tokens: int = 0
    completion_tokens: int
    latency_ms: int
    attempts: int


class ValidationResult(_Record):
    attempt: int
    violations: list[dict[str, Any]]


class TraceRecord(_Record):
    trace_version: Literal["1"] = TRACE_VERSION
    run_id: str
    item_index: int
    item_id: str
    system: Literal["baseline", "modular"]
    fixture_id: str
    fixture_sha256: str
    policy_set_id: str
    policy_set_sha256: str
    git_sha: str | None
    model: dict[str, Any] | None
    message: str
    redactions: int
    model_calls: list[ModelCall] = []
    decisions: list[dict[str, Any]] = []
    """S1 controller decisions, in order, each with its step name."""
    policies: list[dict[str, str]] = []
    """S1 loaded policy modules: id, version and sha256."""
    observations: list[Observation] = []
    fact_table: list[dict[str, Any]] = []
    validations: list[ValidationResult] = []
    outcome: TerminalOutcome | None = None
    reply: Reply | None = None
    error: str | None = None
    latency_ms: int = 0
    """End-to-end wall time for the item, model calls and tools included."""
