"""Append redacted trace records to `<trace dir>/traces.jsonl`, one line per item."""

import json
import threading
from pathlib import Path

from doctours_reply.trace.redact import redact_json
from doctours_reply.trace.schema import TraceRecord


class TraceSink:
    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "traces.jsonl"
        self._lock = threading.Lock()

    def write(self, record: TraceRecord) -> None:
        line = json.dumps(redact_json(record.model_dump(mode="json")), ensure_ascii=False)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
