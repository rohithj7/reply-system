"""The only component that runs packet tools (decision record 0002, traceability R-13).

One `Executor` serves one item. It validates arguments against the registry, requires
clinic and package IDs to have come from a tool result this turn, runs each distinct
write at most once and `updateWorkingMemory` at most once, and refuses every call after
`close()`. With an `allowed` set, a tool outside it is refused as `tool_not_loaded`
without spending budget. Every request, accepted or not, is recorded as an `Observation`.
"""

import json
import time
from collections.abc import Iterable, Mapping
from typing import Any, Final

from pydantic import JsonValue, ValidationError

from doctours_reply.runtime.observation import Observation, ObservationStatus
from doctours_reply.tools.data import ToolData
from doctours_reply.tools.registry import (
    TOOLS,
    ToolKind,
    ToolSpec,
    UnknownToolError,
    resolve_tool_name,
)

MAX_TOOL_CALLS: Final = 8
TRUSTED_ID_CONSTANTS: Final = (
    "USER_ID",
    "SENDER_USER_ID",
    "RESOURCE_ID",
    "THREAD_ID",
    "SUPABASE_CHAT_ID",
)
_PATIENT_ID_ARGS: Final = frozenset({"userId", "chatId"})
_MEMORY_TOOL: Final = "updateWorkingMemory"


class ExecutorClosedError(RuntimeError):
    """A tool was requested after the item's terminal outcome was selected."""


class Executor:
    def __init__(
        self, data: ToolData, constants: Mapping[str, Any], max_calls: int = MAX_TOOL_CALLS
    ) -> None:
        self._data = data
        self._trusted_ids = {
            value for name in TRUSTED_ID_CONSTANTS if isinstance(value := constants.get(name), str)
        }
        self._observed_ids: set[str] = set()
        self._writes: dict[str, Observation] = {}
        self._calls_left = max_calls
        self._closed = False
        self.observations: list[Observation] = []

    @property
    def executed_writes(self) -> tuple[str, ...]:
        return tuple(o.call_id for o in self.observations if o.kind == "write" and o.executed)

    @property
    def calls_left(self) -> int:
        return self._calls_left

    def close(self) -> None:
        self._closed = True

    def execute(
        self,
        call_id: str,
        name: str,
        args: Mapping[str, Any] | str,
        allowed: frozenset[str] | None = None,
    ) -> Observation:
        if self._closed:
            raise ExecutorClosedError(f"{name} requested after the outcome was selected")
        try:
            spec = TOOLS[resolve_tool_name(name)]
        except UnknownToolError:
            return self._record(call_id, name, None, args, "rejected", reason="unknown tool")
        raw = _as_object(args)
        if raw is None:
            return self._record(
                call_id, spec.name, spec.kind, args, "rejected", reason="arguments not an object"
            )
        if allowed is not None and spec.name not in allowed:
            return self._record(
                call_id,
                spec.name,
                spec.kind,
                raw,
                "tool_not_loaded",
                reason="no loaded policy allows this tool",
            )
        if self._calls_left <= 0:
            return self._record(
                call_id, spec.name, spec.kind, raw, "rejected", reason="tool call budget used up"
            )
        self._calls_left -= 1
        try:
            parsed = spec.args_model.model_validate(raw).model_dump(exclude_unset=True)
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            return self._record(call_id, spec.name, spec.kind, raw, "rejected", reason=reason)
        if unproven := self._unproven_ids(parsed):
            reason = f"IDs not returned by a tool this turn: {', '.join(unproven)}"
            return self._record(call_id, spec.name, spec.kind, parsed, "rejected", reason=reason)
        return self._run_once(call_id, spec, parsed)

    def commit_memory(self, call_id: str, diff: Mapping[str, Any]) -> Observation:
        """Ledger A-15: the single `updateWorkingMemory` call, outside the tool budget."""
        if self._closed:
            raise ExecutorClosedError(f"{_MEMORY_TOOL} requested after the outcome was selected")
        spec = TOOLS[_MEMORY_TOOL]
        args = spec.args_model.model_validate({"memory": dict(diff)}).model_dump(exclude_unset=True)
        return self._run_once(call_id, spec, args)

    def _run_once(self, call_id: str, spec: ToolSpec, parsed: dict[str, Any]) -> Observation:
        key = _MEMORY_TOOL if spec.name == _MEMORY_TOOL else f"{spec.name}:{_canonical(parsed)}"
        if spec.kind == "write" and (first := self._writes.get(key)) is not None:
            return self._record(
                call_id,
                spec.name,
                spec.kind,
                parsed,
                "duplicate_write",
                result=first.result,
                reason=f"same write already ran as {first.call_id}",
            )
        observation = self._run(call_id, spec, parsed)
        if spec.kind == "write":
            self._writes[key] = observation
        return observation

    def _run(self, call_id: str, spec: ToolSpec, args: dict[str, Any]) -> Observation:
        started = time.monotonic()
        try:
            result = spec.function(self._data, args)
        except Exception as exc:
            return self._record(
                call_id,
                spec.name,
                spec.kind,
                args,
                "error",
                reason=f"{type(exc).__name__}: {exc}",
                started=started,
            )
        self._observed_ids.update(_ids_in(result))
        status: ObservationStatus = "null_result" if result is None else "ok"
        return self._record(call_id, spec.name, spec.kind, args, status, result, started=started)

    def _unproven_ids(self, args: Mapping[str, Any]) -> list[str]:
        unproven = []
        for key, value in args.items():
            if key in _PATIENT_ID_ARGS:
                if value is not None and value not in self._trusted_ids:
                    unproven.append(f"{key}={value}")
            elif key == "clinicSelection" and isinstance(value, Mapping):
                unproven += [
                    f"{key}.{k}={v}" for k, v in _id_items(value) if v not in self._observed_ids
                ]
            elif key.endswith("Id") and value is not None and value not in self._observed_ids:
                unproven.append(f"{key}={value}")
        return unproven

    def _record(
        self,
        call_id: str,
        tool: str,
        kind: ToolKind | None,
        args: Any,
        status: ObservationStatus,
        result: Any = None,
        reason: str | None = None,
        started: float | None = None,
    ) -> Observation:
        latency = 0 if started is None else round((time.monotonic() - started) * 1000)
        observation = Observation(
            call_id=call_id,
            tool=tool,
            kind=kind,
            args=_jsonable(args),
            status=status,
            result=result,
            reason=reason,
            latency_ms=latency,
        )
        self.observations.append(observation)
        return observation


def _as_object(args: Mapping[str, Any] | str) -> dict[str, Any] | None:
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return None
    return dict(args) if isinstance(args, Mapping) else None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _jsonable(value: Any) -> JsonValue:
    return value if isinstance(value, str) else json.loads(_canonical(value))


def _is_id_key(key: str) -> bool:
    return key == "id" or key.endswith("Id")


def _is_ids_key(key: str) -> bool:
    return key == "ids" or key.endswith("Ids")


def _id_items(selection: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    for key, value in selection.items():
        if _is_id_key(key) and value is not None:
            yield key, value
        elif _is_ids_key(key) and isinstance(value, list):
            yield from ((key, item) for item in value)


def _ids_in(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, str) and _is_id_key(key):
                yield item
            elif isinstance(item, list) and _is_ids_key(key):
                yield from (i for i in item if isinstance(i, str))
            else:
                yield from _ids_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _ids_in(item)
