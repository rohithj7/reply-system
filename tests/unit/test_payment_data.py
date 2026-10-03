import pytest

from doctours_reply.runtime.payment_data import (
    CARD_FRAGMENT,
    CARD_NUMBER,
    echoes_card_data,
    redact_card_data,
)


@pytest.mark.parametrize(
    "pan",
    [
        "4242424242424242",
        "4242 4242 4242 4242",
        "4242-4242-4242-4242",
        "4222222222222",
        "378282246310005",
        "6011000990139424",
        "4242424242424242428",
    ],
)
def test_luhn_valid_pans_of_13_to_19_digits_are_redacted(pan: str) -> None:
    redacted = redact_card_data(f"my card is {pan} thanks")
    assert redacted.text == f"my card is {CARD_NUMBER} thanks"
    assert pan.replace(" ", "").replace("-", "") in redacted.card_digits


@pytest.mark.parametrize(
    ("text", "digits"),
    [
        ("the card ending in 4242", "4242"),
        ("card ends with 1881", "1881"),
        ("last four 4242", "4242"),
        ("last 4 digits are 9999", "9999"),
        ("exp 12/28", "12/28"),
        ("expiry: 01 / 2030", "01/2030"),
        ("cvv 123", "123"),
        ("security code: 4321", "4321"),
    ],
)
def test_card_fragments_are_redacted(text: str, digits: str) -> None:
    redacted = redact_card_data(text)
    assert CARD_FRAGMENT in redacted.text
    assert digits not in redacted.text
    assert digits in redacted.card_digits


@pytest.mark.parametrize(
    "text",
    [
        "Silver is $3,000 USD",
        "within 12 months",
        "call me at +1 555 555 0123",
        "order 1234567890123",
        "2500 - 3200 grafts",
        "on 2026-10-03 at 10:02",
    ],
)
def test_non_card_numbers_are_kept(text: str) -> None:
    redacted = redact_card_data(text)
    assert redacted.text == text
    assert redacted.card_digits == ()


def test_echo_detection_ignores_spacing_and_word_boundaries() -> None:
    digits = redact_card_data("pay with 4242 4242 4242 4242").card_digits
    assert echoes_card_data("charging 4242-4242-4242-4242 now", digits)
    assert echoes_card_data("the card ending 4242", digits)
    assert not echoes_card_data("Silver is $3,000", digits)
    assert not echoes_card_data("ref 142420", digits)
