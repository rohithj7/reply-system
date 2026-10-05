"""Shared IDs and reply builders for the unit tests."""

from collections.abc import Mapping
from typing import Any

HEVA_ID = "11111111-1111-4111-8111-111111111111"
HAKAN_ID = "22222222-2222-4222-8222-222222222222"
SILVER_ID = "44444444-4444-4444-8444-444444444441"
GOLD_ID = "44444444-4444-4444-8444-444444444442"
SAPPHIRE_ID = "55555555-5555-4555-8555-555555555551"
USER_ID = "7c2e1a40-6b8f-4d3a-9e15-2f0a8b6c4d11"
GOLD_PAYMENT_URL = f"https://www.doctours.com/payment/{GOLD_ID}"
HEVA_ANSWER = "Silver is $3,000 USD with a $500 deposit. Gold is $4,500 USD with a $600 deposit."
CARD_DETAILS = [
    ("My card number is 5555555555554444, keep it on file.", ("5555555555554444",)),
    ("4111 1111 1111 1111 11/29 731", ("4111 1111", "4111111111111111", "11/29", "29 731")),
    ("4111 1111 1111 1111 3/29 731", ("4111 1111", "4111111111111111", "3/29", "29 731")),
    ("Can I use my Visa ending 9876?", ("ending 9876",)),
]
"""Patient texts with card details, each with the details no model request or saved trace holds."""


def reply_json(response: str, **overrides: Any) -> Mapping[str, Any]:
    """A complete, valid model reply object; `overrides` replace individual keys."""
    return {
        "response": response,
        "escalate": False,
        "escalationReason": None,
        "templateId": None,
        "intent": "answer question",
        "shouldFollowUp": False,
        "followUpTiming": None,
        "attachmentUrls": [],
        "highEngagement": False,
        "workingMemoryUpdates": None,
        **overrides,
    }


def escalation_json(sentence: str, reason: str) -> Mapping[str, Any]:
    return reply_json(sentence, escalate=True, escalationReason=reason)
