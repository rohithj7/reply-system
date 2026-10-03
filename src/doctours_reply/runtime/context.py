"""Per-item context: the redacted message plus the fixture and policy set it runs against."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from doctours_reply.runtime.payment_data import RedactedText, redact_card_data
from doctours_reply.runtime.refs import Fixture, PolicySet

_PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")


@dataclass(frozen=True)
class TurnContext:
    index: int
    item_id: str
    message: RedactedText
    fixture: Fixture
    policy_set: PolicySet

    @property
    def working_memory(self) -> Mapping[str, Any]:
        raw = self.fixture.constants.get("WORKING_MEMORY")
        memory = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        return memory if isinstance(memory, dict) else {}


def build_context(
    index: int, item_id: str, text: str, fixture: Fixture, policy_set: PolicySet
) -> TurnContext:
    return TurnContext(index, item_id, redact_card_data(text), fixture, policy_set)


def fill_placeholders(template: str, values: Mapping[str, Any]) -> str:
    """Fill `{{NAME}}` from `values` in one pass; unknown names and filled text stay as is.

    Non-string values are written as JSON.
    """

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            return match.group(0)
        value = values[name]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return _PLACEHOLDER.sub(fill, template)
