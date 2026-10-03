"""Redact card data from every string in a JSON value before it is written anywhere."""

from typing import Any

from doctours_reply.runtime.payment_data import redact_card_data


def redact_json(value: Any) -> Any:
    if isinstance(value, str):
        return redact_card_data(value).text
    if isinstance(value, dict):
        return {key: redact_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return value
