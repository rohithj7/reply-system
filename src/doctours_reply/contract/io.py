"""Parsing the input array and serializing the output array."""

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from doctours_reply.contract.reply import Reply


class InputItem(BaseModel):
    """One message in the shape of `HUMAN_MESSAGES`; other keys are ignored."""

    model_config = ConfigDict(extra="ignore", strict=True)

    id: str
    text: str


class InputContractError(ValueError):
    """The input is not a JSON array of `{id, text}` string objects."""


_INPUT = TypeAdapter(list[InputItem])


def parse_input(raw: str | bytes) -> list[InputItem]:
    try:
        return _INPUT.validate_json(raw)
    except ValidationError as exc:
        raise InputContractError(str(exc)) from exc


def dump_replies(replies: Sequence[Reply]) -> str:
    payload = [reply.model_dump(mode="json", exclude_unset=True) for reply in replies]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
