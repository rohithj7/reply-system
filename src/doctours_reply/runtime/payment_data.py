"""Card-data redaction for patient text, model input and traces (ledger A-21).

Redaction only rewrites text. It never sets or influences escalation.
"""

import re
from dataclasses import dataclass

CARD_NUMBER = "[CARD_NUMBER]"
CARD_FRAGMENT = "[CARD_FRAGMENT]"

_PAN = re.compile(r"(?<![\d.,])\d(?:[ -]?\d){12,18}(?![\d,]|\.\d)")
# Clinic, package and patient IDs are UUIDs whose digit runs can pass the Luhn check.
_UUID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.IGNORECASE)
_FRAGMENTS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:ending|ends)\s+(?:in|with)\s*:?\s*(\d{4})\b",
        r"\blast\s+(?:four|4)(?:\s+digits)?(?:\s+(?:are|is))?\s*:?\s*(\d{4})\b",
        r"\b(?:exp(?:iry|iration|ires)?|valid\s+thru)(?:\s+date)?\.?\s*:?\s*(\d{1,2}\s*/\s*\d{2,4})",
        r"\b(?:cvv2?|cvc2?|csc|security\s+code)\s*[:#]?\s*(\d{3,4})\b",
    )
)


@dataclass(frozen=True)
class RedactedText:
    text: str
    card_digits: tuple[str, ...]
    """Digit strings removed from the text, for the no-echo check."""


def _luhn_valid(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def redact_card_data(text: str) -> RedactedText:
    removed: list[str] = []
    uuids = [m.span() for m in _UUID.finditer(text)]

    def pan(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        in_uuid = any(start < match.end() and match.start() < end for start, end in uuids)
        if in_uuid or not _luhn_valid(digits):
            return match.group()
        removed.extend((digits, digits[-4:]))
        return CARD_NUMBER

    def fragment(match: re.Match[str]) -> str:
        removed.append(re.sub(r"\s", "", match.group(1)))
        start, end = match.span(1)
        whole = match.group()
        offset = match.start()
        return whole[: start - offset] + CARD_FRAGMENT + whole[end - offset :]

    redacted = _PAN.sub(pan, text)
    for pattern in _FRAGMENTS:
        redacted = pattern.sub(fragment, redacted)
    return RedactedText(redacted, tuple(dict.fromkeys(removed)))


def echoes_card_data(text: str, card_digits: tuple[str, ...]) -> bool:
    """True if `text` repeats any redacted digit string, ignoring spaces and dashes."""
    compact = re.sub(r"[ -]", "", text)
    return any(re.search(rf"(?<!\d){re.escape(d)}(?!\d)", compact) for d in card_digits)
