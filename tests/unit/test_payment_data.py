import json

import pytest

from doctours_reply.runtime.payment_data import (
    CARD_FRAGMENT,
    CARD_NUMBER,
    echoes_card_data,
    redact_card_data,
)
from doctours_reply.runtime.refs import Fixture


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
    ("text", "expected"),
    [
        ("My card is 5555555555554444, keep it.", f"My card is {CARD_NUMBER}, keep it."),
        ("card 4242-4242-4242-4242, thanks", f"card {CARD_NUMBER}, thanks"),
        ("It's 4242 4242 4242 4242.", f"It's {CARD_NUMBER}."),
        ("card no.4242424242424242 please", f"card no.{CARD_NUMBER} please"),
        ("4242424242424242 4242424242424242", f"{CARD_NUMBER} {CARD_NUMBER}"),
        ("4111 1111 1111 1111 11/29 731", f"{CARD_NUMBER} {CARD_FRAGMENT} {CARD_FRAGMENT}"),
        ("4111 1111 1111 1111 3/29 731", f"{CARD_NUMBER} {CARD_FRAGMENT} {CARD_FRAGMENT}"),
        ("4242424242424242, 11/29, 731", f"{CARD_NUMBER}, {CARD_FRAGMENT}, {CARD_FRAGMENT}"),
        ("4111 1111 1111 1111 731 thanks", f"{CARD_NUMBER} {CARD_FRAGMENT} thanks"),
        ("378282246310005 1234", f"{CARD_NUMBER} {CARD_FRAGMENT}"),
        ("Can I use my Visa ending 9876?", f"Can I use my Visa ending {CARD_FRAGMENT}?"),
        ("the card ending 9876 was declined", f"the card ending {CARD_FRAGMENT} was declined"),
    ],
)
def test_card_details_are_redacted_up_to_their_own_boundaries(text: str, expected: str) -> None:
    assert redact_card_data(text).text == expected


@pytest.mark.parametrize(
    "text",
    [
        "Silver is $3,000 USD",
        "Prices are $3,000, $4,500 and $600.",
        "within 12 months",
        "call me at +1 555 555 0123",
        "order 1234567890123",
        "ref 42424242424242421",
        "4242 4242 4242 4242 4242 4242",
        "4242424242424242.50",
        "the offer ending 2027",
        "2500 - 3200 grafts",
        "on 2026-10-03 at 10:02",
    ],
)
def test_non_card_numbers_are_kept(text: str) -> None:
    redacted = redact_card_data(text)
    assert redacted.text == text
    assert redacted.card_digits == ()


def test_uuids_and_digests_are_kept_even_when_their_digits_pass_luhn(fixture: Fixture) -> None:
    clinic_id = "11111111-1111-4111-8111-111111111111"
    digest = "ab" * 8 + "4242424242424242" + "cd" * 8
    redacted = redact_card_data(f"select {clinic_id} ({digest}) and charge 4242424242424242")
    assert redacted.text == f"select {clinic_id} ({digest}) and charge {CARD_NUMBER}"
    assert redact_card_data("my card is4242424242424242").text == f"my card is{CARD_NUMBER}"
    strings = [fixture.tool_data.model_dump_json(), json.dumps(dict(fixture.constants))]
    assert all(redact_card_data(s).text == s for s in strings)


def test_echo_detection_ignores_spacing_and_word_boundaries() -> None:
    digits = redact_card_data("pay with 4242 4242 4242 4242").card_digits
    assert echoes_card_data("charging 4242-4242-4242-4242 now", digits)
    assert echoes_card_data("the card ending 4242", digits)
    assert not echoes_card_data("Silver is $3,000", digits)
    assert not echoes_card_data("ref 142420", digits)
