from typing import Any

import pytest
from support import GOLD_PAYMENT_URL, HEVA_ID

from doctours_reply.baseline.monolithic import LEGACY_STATIC_LINKS
from doctours_reply.contract.reply import WorkingMemoryUpdates
from doctours_reply.runtime.evidence import Evidence, build_evidence
from doctours_reply.runtime.executor import Executor
from doctours_reply.runtime.outcome import Draft
from doctours_reply.runtime.payment_data import redact_card_data
from doctours_reply.runtime.refs import Fixture
from doctours_reply.runtime.validate import (
    check_answer,
    check_escalation_reason,
    check_escalation_sentence,
)

CHECKOUT_URL = "https://www.doctours.com/clinic/heva/checkout"
IMAGE_URL = "https://assets.example.invalid/intake/7c2e1a40-6b8f-4d3a-9e15-2f0a8b6c4d11/front.jpg"


@pytest.fixture
def evidence(fixture: Fixture) -> Evidence:
    executor = Executor(fixture.tool_data, fixture.constants)
    executor.execute("c1", "getAllClinics", {})
    executor.execute("c2", "getClinicPackages", {"clinicName": "Heva"})
    executor.execute(
        "c3",
        "getPaymentLink",
        {"type": "payment", "clinicPackageId": "44444444-4444-4444-8444-444444444442"},
    )
    executor.execute("c4", "getPaymentLink", {"type": "checkout", "clinicId": HEVA_ID})
    executor.execute("c5", "getPatientImages", {"userId": fixture.constants["USER_ID"]})
    return build_evidence(
        executor.observations,
        clinics=fixture.tool_data.clinics,
        static_links=LEGACY_STATIC_LINKS,
    )


def _draft(response: str, **fields: Any) -> Draft:
    values: dict[str, Any] = {
        "response": response,
        "intent": "answer",
        "shouldFollowUp": False,
        "followUpTiming": None,
        "attachmentUrls": [],
        "highEngagement": False,
        "workingMemoryUpdates": None,
    }
    return Draft(**(values | fields))


def _codes(draft: Draft, evidence: Evidence, message: str = "hi") -> list[str]:
    return [v.code for v in check_answer(draft, evidence, redact_card_data(message))]


@pytest.mark.parametrize(
    ("response", "codes"),
    [
        (f"Here is the Gold link.\n{GOLD_PAYMENT_URL}", []),
        ("You can book from the clinic page.\nhttps://www.doctours.com/clinic/heva", []),
        ("Upload them here.\nhttps://www.doctours.com/image-upload", []),
        (f"Pay here {GOLD_PAYMENT_URL} today.", ["url_placement"]),
        ("Pay here.\nhttps://www.doctours.com/payment/made-up", ["url_provenance"]),
        ("See it here.\nhttps://www.doctours.com/clinic/istanbul-best", ["url_provenance"]),
        (f"Either works.\n{GOLD_PAYMENT_URL}\n{CHECKOUT_URL}", ["payment_and_checkout"]),
        ("**Gold** is great.", ["markdown"]),
        ("- Gold\n- Silver", ["markdown"]),
        ("   ", ["empty_response"]),
    ],
)
def test_reply_checks(response: str, codes: list[str], evidence: Evidence) -> None:
    assert _codes(_draft(response), evidence) == codes


def test_attachments_must_be_tool_returned(evidence: Evidence) -> None:
    assert _codes(_draft("Here they are.", attachmentUrls=[IMAGE_URL]), evidence) == []
    stray = _draft("Here.", attachmentUrls=["https://example.com/x.jpg"])
    assert _codes(stray, evidence) == ["attachment_provenance"]


def test_memory_never_stores_dates(evidence: Evidence) -> None:
    memory = WorkingMemoryUpdates(keyConcerns="wants May 12 at Heva")
    assert _codes(_draft("Noted.", workingMemoryUpdates=memory), evidence) == ["memory_date"]


def test_card_digits_are_never_echoed(evidence: Evidence) -> None:
    message = "my card 4242 4242 4242 4242 is fine?"
    echoed = _draft("Please don't share 4242-4242-4242-4242 here.")
    assert "card_echo" in _codes(echoed, evidence, message)
    assert _codes(_draft("Please don't share card details here."), evidence, message) == []


def test_escalation_sentence_and_reason_form() -> None:
    message = redact_card_data("charge 4242 4242 4242 4242")
    assert check_escalation_sentence("I'm getting a person for you.", message) == []
    assert check_escalation_sentence("Sure. A person will help.", message) != []
    assert check_escalation_sentence("Gold is $4,500, a person will help.", message) != []
    assert check_escalation_reason("Asked to charge a card", message) == []
    assert check_escalation_reason("Card 4242", message) != []
    assert check_escalation_reason(" ", message) != []
