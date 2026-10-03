"""What the executor returns for every requested tool call."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from doctours_reply.tools.registry import ToolKind

ObservationStatus = Literal["ok", "null_result", "rejected", "duplicate_write", "error"]
EXECUTED: frozenset[ObservationStatus] = frozenset({"ok", "null_result", "error"})


class Observation(BaseModel):
    """`result` is the tool's actual return value; `reason` explains a non-ok status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    tool: str
    kind: ToolKind | None
    args: JsonValue
    status: ObservationStatus
    result: JsonValue = None
    reason: str | None = None
    latency_ms: int = 0

    @property
    def executed(self) -> bool:
        return self.status in EXECUTED
