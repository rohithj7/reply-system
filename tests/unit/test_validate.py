from collections.abc import Sequence
from typing import Any

import pytest
from support import GOLD_ID, GOLD_PAYMENT_URL, HEVA_ID

from doctours_reply.baseline.monolithic import LEGACY_STATIC_LINKS
from doctours_reply.contract.reply import WorkingMemoryUpdates
from doctours_reply.runtime.evidence import Evidence, build_evidence
from doctours_reply.runtime.executor import Executor
from doctours_reply.runtime.observation import Observation
from doctours_reply.runtime.outcome import Draft
from doctours_reply.runtime.payment_data import redact_card_data
from doctours_reply.runtime.policy_loader import PolicyCatalog
from doctours_reply.runtime.refs import Fixture, resolve_policy_set
from doctours_reply.runtime.validate import (
    check_answer,
    check_escalation_reason,
    check_escalation_sentence,
)

SHIPPED = PolicyCatalog(resolve_policy_set("shipped"))
CATALOGS = {
    "shipped": SHIPPED,
    "checkout-only-links": PolicyCatalog(resolve_policy_set("checkout-only-links")),
}
ASSESSMENT_URL = "https://www.doctours.com/assessment/c3d4e5f6-3333-4333-8333-333333333333"
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


def _link_evidence(
    fixture: Fixture,
    observations: Sequence[Observation],
    skills: Sequence[str] = ("payments.links",),
    policy_set_id: str = "shipped",
) -> Evidence:
    loaded = CATALOGS[policy_set_id].load(skills, fixture.constants)
    return build_evidence(
        observations,
        clinics=fixture.tool_data.clinics,
        packages=fixture.tool_data.packages,
        deposit_links=loaded.deposit_links,
        assessment_cues=loaded.assessment_link_cues,
    )


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


@pytest.mark.parametrize(
    ("message", "selection", "response", "codes"),
    [
        (
            "Ready to book Gold, send the link",
            "",
            f"Your assessment.\n{ASSESSMENT_URL}",
            ["missing_link"],
        ),
        ("ready to book gold", "", "Great choice, the link is below.", ["missing_link"]),
        ("Yes, book it", "write", "Saved Heva Gold for you.", ["missing_link"]),
        ("What's next?", "saved", f"Your assessment.\n{ASSESSMENT_URL}", ["missing_link"]),
        ("Ready to book Gold", "", f"Here is the Gold link.\n{GOLD_PAYMENT_URL}", []),
        ("Yes, book it", "write", f"Saved.\n{ASSESSMENT_URL}\n{GOLD_PAYMENT_URL}", []),
        ("Send me the payment link for my package", "", "Which package is it?", []),
        ("Silver or Gold, which is better?", "", "Both suit you.", []),
        ("I want Silver instead", "saved", "Sure, Silver it is.", []),
        ("Ready to book Gold", "not ready", "Let me check that package.", []),
        ("Tell me more about the options", "soft", "Happy to.", []),
    ],
)
def test_a_ready_payment_link_for_the_patients_one_package_is_sent(
    fixture: Fixture, message: str, selection: str, response: str, codes: list[str]
) -> None:
    executor = Executor(fixture.tool_data, fixture.constants)
    user = fixture.constants["USER_ID"]
    executor.execute("c1", "getClinicPackages", {"clinicName": "Heva"})
    executor.execute("c2", "getLatestAssessment", {"userId": user})
    chosen = {"write": "selectedPackageId", "soft": "softPackageInterestIds"}.get(selection)
    if chosen:
        value = GOLD_ID if selection == "write" else [GOLD_ID]
        args = {"userId": user, "clinicSelection": {"selectedClinicId": HEVA_ID, chosen: value}}
        assert executor.execute("c3", "updateUserClinicPreferences", args).status == "ok"
    package = HEVA_ID if selection == "not ready" else GOLD_ID
    executor.execute("c4", "getPaymentLink", {"type": "payment", "clinicPackageId": package})
    observations = list(executor.observations)
    if selection == "saved":
        saved = {"clinicSelectionPreferences": {"selectedPackageId": GOLD_ID}}
        observations.append(
            Observation(
                call_id="c5",
                tool="getPatientContext",
                kind="read",
                args={"userId": user},
                status="ok",
                result=saved,
            )
        )
    assert _codes(_draft(response), _link_evidence(fixture, observations), message) == codes


@pytest.mark.parametrize(
    ("message", "setup", "response", "codes"),
    [
        ("Send me the checkout link for Heva", "", "Sure, here you go.", ["missing_link"]),
        ("send me the heva checkout link", "", "Sure, it is below.", ["missing_link"]),
        ("I'm ready to book, what's next?", "saved", "Great, see you soon.", ["missing_link"]),
        ("I'm going with Heva, send me the link", "packages", "Great choice.", ["missing_link"]),
        ("I don't want a call, just send me the Heva checkout link", "", "Sure.", ["missing_link"]),
        ("Send me the checkout link for Heva", "", f"Here it is.\n{CHECKOUT_URL}", []),
        ("Heva or Dr. Hakan, which is better?", "", "Both are good.", []),
        ("How do I pay the deposit?", "", "From the clinic checkout.", []),
        ("I'd rather go with Dr. Hakan", "saved", "Sure.", []),
        ("I'll take Gold, send me the link", "payment", f"Here.\n{GOLD_PAYMENT_URL}", []),
        ("Don't send me the Heva checkout link yet.", "", "Sure, whenever you're ready.", []),
        ("Please don't send the checkout link yet", "saved", "Of course.", []),
    ],
)
def test_a_ready_checkout_link_for_the_patients_one_clinic_is_sent(
    fixture: Fixture, message: str, setup: str, response: str, codes: list[str]
) -> None:
    executor = Executor(fixture.tool_data, fixture.constants)
    executor.execute("c1", "getAllClinics", {})
    if setup in ("packages", "payment"):
        executor.execute("c2", "getClinicPackages", {"clinicName": "Heva"})
    if setup == "payment":
        executor.execute("c3", "getPaymentLink", {"type": "payment", "clinicPackageId": GOLD_ID})
    executor.execute("c4", "getPaymentLink", {"type": "checkout", "clinicId": HEVA_ID})
    observations = list(executor.observations)
    if setup == "saved":
        saved = {"clinicSelectionPreferences": {"selectedClinicId": HEVA_ID}}
        observations.append(
            Observation(
                call_id="c5",
                tool="getPatientContext",
                kind="read",
                args={"userId": fixture.constants["USER_ID"]},
                status="ok",
                result=saved,
            )
        )
    assert _codes(_draft(response), _link_evidence(fixture, observations), message) == codes


@pytest.mark.parametrize(
    ("message", "setup"),
    [
        ("I've decided on Gold at Heva. How do I pay the deposit?", "packages"),
        ("I've decided on Gold at Heva. How do I pay the deposit?", "clinics"),
        ("How do I pay the deposit?", "saved"),
    ],
)
@pytest.mark.parametrize(
    ("policy_set_id", "codes"), [("shipped", []), ("checkout-only-links", ["missing_link"])]
)
def test_a_decided_patient_needs_the_deposit_link_type_the_policy_sends(
    fixture: Fixture, message: str, setup: str, policy_set_id: str, codes: list[str]
) -> None:
    executor = Executor(fixture.tool_data, fixture.constants)
    executor.execute("c1", "getAllClinics", {})
    if setup == "packages":
        executor.execute("c2", "getClinicPackages", {"clinicName": "Heva"})
    executor.execute("c3", "getPaymentLink", {"type": "checkout", "clinicId": HEVA_ID})
    observations = list(executor.observations)
    if setup == "saved":
        saved = {"selectedPackageId": GOLD_ID, "selectedClinicId": HEVA_ID}
        observations.append(
            Observation(
                call_id="c4",
                tool="getPatientContext",
                kind="read",
                args={"userId": fixture.constants["USER_ID"]},
                status="ok",
                result={"clinicSelectionPreferences": saved},
            )
        )
    evidence = _link_evidence(fixture, observations, policy_set_id=policy_set_id)
    assert _codes(_draft("Great choice."), evidence, message) == codes


@pytest.mark.parametrize(
    ("message", "skills", "setup", "response", "codes"),
    [
        ("Is my assessment where I'd pay?", ["payments.links"], "", "Yes.", ["missing_link"]),
        ("How do I book from the assessment?", ["payments.links"], "", "Yes.", ["missing_link"]),
        ("Can you send me my assessment again?", ["assessment"], "", "Sure.", ["missing_link"]),
        ("I lost the link to my results", ["assessment"], "", "No problem.", ["missing_link"]),
        (
            "Can you send me my assessment again?",
            ["assessment"],
            "missing_input",
            "Sure.",
            ["missing_link"],
        ),
        (
            "Is my assessment where I'd pay?",
            ["payments.links"],
            "rejected",
            "Yes.",
            ["missing_link"],
        ),
        (
            "What's Sapphire at these days? I'm still comparing clinics, but can I put the "
            "deposit down from my assessment?",
            ["payments.links"],
            "",
            "Yes, you can.",
            ["missing_link"],
        ),
        ("Can you send me my assessment again?", ["assessment"], "", f"Hi.\n{ASSESSMENT_URL}", []),
        ("How many grafts do I need?", ["assessment"], "", "Your surgeon confirms it.", []),
        ("Can I change my hairline in the assessment?", ["assessment"], "", "Yes.", []),
        ("How much is the deposit?", ["payments.links"], "", "It depends on the package.", []),
        ("Is my assessment where I'd pay?", [], "", "Yes.", []),
        ("Is my assessment where I'd pay?", ["payments.links"], "pending", "Soon.", []),
        ("Where do I pay?", ["payments.links"], "missing_input", "Which package?", []),
    ],
)
def test_the_assessment_link_is_sent_when_a_loaded_policy_answers_with_it(
    fixture: Fixture, message: str, skills: list[str], setup: str, response: str, codes: list[str]
) -> None:
    executor = Executor(fixture.tool_data, fixture.constants)
    executor.execute("c1", "getLatestAssessment", {"userId": fixture.constants["USER_ID"]})
    if setup in ("missing_input", "rejected"):
        package = None if setup == "missing_input" else ""
        link = executor.execute(
            "c2", "getPaymentLink", {"type": "payment", "clinicPackageId": package}
        )
        assert link.status == ("ok" if package is None else "rejected")
    observations = list(executor.observations)
    if setup == "pending":
        assessment = observations[0].result
        assert isinstance(assessment, dict)
        result = {**assessment, "shareStatus": "pending"}
        observations[0] = observations[0].model_copy(update={"result": result})
    evidence = _link_evidence(fixture, observations, skills)
    assert _codes(_draft(response), evidence, message) == codes


def test_a_decided_patient_needs_the_payment_link_not_the_assessment(fixture: Fixture) -> None:
    executor = Executor(fixture.tool_data, fixture.constants)
    executor.execute("c1", "getClinicPackages", {"clinicName": "Heva"})
    executor.execute("c2", "getLatestAssessment", {"userId": fixture.constants["USER_ID"]})
    executor.execute("c3", "getPaymentLink", {"type": "payment", "clinicPackageId": GOLD_ID})
    evidence = _link_evidence(fixture, executor.observations)
    message = redact_card_data("I've decided on Gold. Can I pay from my assessment?")
    wrong = check_answer(_draft(f"Yes, pay from it.\n{ASSESSMENT_URL}"), evidence, message)
    assert [(v.code, v.source_ref) for v in wrong] == [("missing_link", "getPaymentLink#c3")]
    assert GOLD_PAYMENT_URL in wrong[0].detail
    right = _draft(f"Here is the Gold link.\n{GOLD_PAYMENT_URL}")
    assert check_answer(right, evidence, message) == []


def test_a_decided_patients_unretrieved_payment_link_is_not_replaced_by_the_assessment(
    fixture: Fixture,
) -> None:
    executor = Executor(fixture.tool_data, fixture.constants)
    executor.execute("c1", "getClinicPackages", {"clinicName": "Heva"})
    executor.execute("c2", "getLatestAssessment", {"userId": fixture.constants["USER_ID"]})
    executor.execute("c3", "getPaymentLink", {"type": "payment", "clinicPackageId": None})
    message = "I've decided on Gold. Can I pay from my assessment?"
    reply = _draft("I couldn't generate the Gold link, but you can book from your assessment.")
    assert _codes(reply, _link_evidence(fixture, executor.observations), message) == []


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
