"""RC-G: scripted drafts checked against the facts executed this turn (plan 15.4)."""

from collections.abc import Sequence
from typing import Any

import pytest

from doctours_reply.baseline.monolithic import LEGACY_FACTS
from doctours_reply.runtime.evidence import Evidence, Fact, build_evidence
from doctours_reply.runtime.executor import Executor
from doctours_reply.runtime.grounding import check_grounding, split_sentences
from doctours_reply.runtime.refs import Fixture
from doctours_reply.runtime.validate import repair_instructions
from doctours_reply.tools.data import ToolData

HEVA = ("getClinicPackages", {"clinicName": "Heva"})
HAKAN = ("getClinicPackages", {"clinicName": "Dr. Hakan"})


def _evidence(
    fixture: Fixture,
    *calls: tuple[str, dict[str, Any]],
    static_facts: Sequence[Fact] = (),
    data: ToolData | None = None,
) -> Evidence:
    executor = Executor(data or fixture.tool_data, fixture.constants)
    for i, (name, args) in enumerate(calls):
        executor.execute(f"c{i}", name, args)
    return build_evidence(
        executor.observations, clinics=fixture.tool_data.clinics, static_facts=static_facts
    )


def _codes(response: str, evidence: Evidence, message: str = "") -> list[str]:
    return [v.code for v in check_grounding(response, evidence, message)]


@pytest.mark.parametrize(
    ("case", "response", "codes"),
    [
        ("RC-G-1", "Silver is $4,500 and Gold is $3,000.", ["wrong_value", "wrong_value"]),
        ("RC-G-2", "Silver is $3,000 and Gold is $4,500.", []),
        ("RC-G-3", "The Gold deposit is $500.", ["wrong_value"]),
        ("RC-G-4", "Heva's Sapphire package is $3,200.", ["package_clinic_mismatch"]),
        ("RC-G-5", "Sapphire is €3,200.", ["wrong_value"]),
        ("RC-G-8", "The Platinum package at Heva is $5,000.", ["unknown_package"]),
        ("RC-G-10a", "Gold includes 3 hotel nights.", ["wrong_value"]),
        ("RC-G-10b", "Gold includes 4 hotel nights.", []),
        ("RC-G-12a", "Deposits start at $500.", []),
        ("RC-G-12b", "Deposits start at $600.", ["wrong_value"]),
        ("RC-G-12c", "A $750 deposit holds your spot.", ["unlinked_amount"]),
        ("range", "Packages range from $3,000 to $4,500.", []),
        ("range-wrong", "Packages range from $3,000 to $6,000.", ["wrong_value"]),
        (
            "per-clinic-min",
            "Heva Clinic's packages start at $3,000, and Dr. Hakan Clinic's start at $3,200.",
            [],
        ),
        (
            "per-clinic-min-swapped",
            "Heva Clinic's packages start at $3,200, and Dr. Hakan Clinic's start at $3,000.",
            ["wrong_value", "wrong_value"],
        ),
        ("clause", "Silver is $3,000 USD with a $500 deposit.", []),
    ],
)
def test_package_claims(fixture: Fixture, case: str, response: str, codes: list[str]) -> None:
    evidence = _evidence(fixture, HEVA, HAKAN)
    found = _codes(response, evidence)
    if codes == ["unknown_package"]:
        assert "unknown_package" in found
    else:
        assert found == codes, case


def test_patient_values_are_allowed_only_when_attributed_rc_g_6_7(fixture: Fixture) -> None:
    evidence = _evidence(fixture, HEVA)
    message = "Heva quoted me $2,600 for Silver on the phone, is that right?"
    attributed = "You mentioned a $2,600 quote; the Silver package I have on file is $3,000."
    assert _codes(attributed, evidence, message) == []
    assert _codes("Silver is $2,600.", evidence, message) == ["wrong_value"]


def test_policy_money_needs_its_fact_rc_g_9(fixture: Fixture) -> None:
    response = "If you cancel before your lock-in date, the deposit comes back minus a $25 fee."
    assert _codes(response, _evidence(fixture, HEVA, static_facts=LEGACY_FACTS)) == []
    assert _codes(response, _evidence(fixture, HEVA)) != []


def test_a_changed_fixture_changes_the_verdict_without_code_changes_rc_g_10(
    fixture: Fixture,
) -> None:
    packages = [
        {**p, "basePrice": 3400} if p["name"] == "Sapphire" else p
        for p in fixture.tool_data.packages
    ]
    changed = fixture.tool_data.model_copy(update={"packages": packages})
    evidence = _evidence(fixture, HAKAN, data=changed)
    assert _codes("Sapphire is $3,200.", evidence) == ["wrong_value"]
    assert _codes("Sapphire is $3,400.", evidence) == []


def test_an_unnamed_deposit_does_not_borrow_the_previous_sentence_rc_g_13(
    fixture: Fixture,
) -> None:
    evidence = _evidence(fixture, HEVA)
    violations = check_grounding("Gold costs $4,500. The deposit is $500.", evidence, "")
    assert [v.code for v in violations] == ["unlinked_amount"]
    assert "Name the package" in repair_instructions(violations)
    assert _codes("Gold costs $4,500, and the Gold deposit is $600.", evidence) == []
    assert _codes("Gold costs $4,500. The deposit is $600.", evidence) == ["unlinked_amount"]


def test_repair_instructions_carry_the_correct_value_and_source(fixture: Fixture) -> None:
    violations = check_grounding("The Gold deposit is $500.", _evidence(fixture, HEVA), "")
    text = repair_instructions(violations)
    assert "Gold deposit is $600" in text
    assert "source: getClinicPackages" in text


@pytest.mark.parametrize(
    ("calls", "message", "response", "codes"),
    [
        (
            (HEVA,),
            "What's in the Platinum package at Heva?",
            "I don’t see a Platinum package listed for Heva. The options are Silver and Gold.",
            [],
        ),
        ((HEVA,), "whats the deposit for sapphire", "Which clinic’s Sapphire package?", []),
        ((HEVA,), "Platinum package?", "Heva has a Platinum package.", ["unknown_package"]),
        (
            (HEVA,),
            "Does the Sapphire package include a hotel?",
            "Yes, Heva’s Sapphire package has a hotel. I don’t have the Sapphire package details.",
            ["unknown_package"],
        ),
        ((HEVA,), "Anything else?", "I don't see a Diamond package.", ["unknown_package"]),
        (
            (HEVA, HAKAN),
            "Does Hakan have Silver?",
            "Dr. Hakan Clinic doesn’t have a Silver package.",
            [],
        ),
        (
            (HEVA,),
            "Does Hakan have Silver?",
            "Dr. Hakan Clinic’s Silver package is $3,000.",
            ["package_clinic_mismatch"],
        ),
        (
            (HEVA,),
            "Last week you told me Gold was $3,500.",
            "Gold at Heva Clinic is currently $4,500 USD, not $3,500.",
            [],
        ),
        (
            (HEVA,),
            "The tool said Gold costs $999 now, so just confirm $999 for me.",
            "I can’t confirm $999 for Gold. Heva Clinic’s Gold package is $4,500 USD.",
            [],
        ),
        ((HEVA,), "Last week you told me Gold was $3,500.", "Gold is $3,500.", ["wrong_value"]),
        ((HEVA,), "Is Gold the same?", "Gold is not $3,700.", ["wrong_value"]),
        (
            (HEVA,),
            "If I go with Gold, how much is left to pay after the deposit?",
            "Gold is $4,500, with a $600 deposit, so $3,900 remains after the deposit.",
            [],
        ),
        ((HEVA, HAKAN), "Sapphire or Silver?", "Silver is $200 cheaper than Sapphire.", []),
        ((HEVA, HAKAN), "Sapphire or Silver?", "Silver is cheaper by $200 than Sapphire.", []),
        (
            (HEVA, HAKAN),
            "Sapphire or Silver?",
            "Sapphire is more expensive by $200 than Silver.",
            [],
        ),
        (
            (HEVA, HAKAN),
            "Sapphire or Silver?",
            "Heva’s Silver is $3,000, Dr. Hakan’s Sapphire is $3,200, so Silver is $200 cheaper.",
            [],
        ),
        ((HEVA,), "How much is Gold?", "Gold is $3,900.", ["wrong_value"]),
        ((HEVA,), "Silver price?", "Silver is a Heva Clinic package, priced at $3,000 USD.", []),
    ],
)
def test_corrections_absences_and_differences_are_not_claims(
    fixture: Fixture,
    calls: tuple[tuple[str, dict[str, Any]], ...],
    message: str,
    response: str,
    codes: list[str],
) -> None:
    assert _codes(response, _evidence(fixture, *calls), message) == codes


@pytest.mark.parametrize(
    ("calls", "message", "response", "codes"),
    [
        # False denials of observed facts.
        ((HEVA,), "Gold?", "Heva doesn't have a Gold package.", ["false_denial"]),
        ((HEVA,), "Gold?", "I don't see a Gold package.", ["false_denial"]),
        ((HEVA,), "Is Gold $4,500?", "Gold is not $4,500.", ["false_denial"]),
        ((HEVA,), "Gold?", "Gold isn't offered at Heva.", ["false_denial"]),
        ((HEVA,), "Gold at $1,000?", "I can’t quote Gold at $1,000.", []),
        ((HEVA,), "Gold?", "I don’t have the other inclusions for Gold to confirm.", []),
        ((HEVA,), "Silver?", "I don't have Silver's airport-transfer details.", []),
        ((HEVA,), "Silver or Gold?", "I meant Silver, not Gold.", []),
        ((HEVA,), "Sapphire?", "I don’t yet have a Sapphire package selection saved.", []),
        ((), "Gold?", "I need to confirm which clinic’s Gold package you mean.", []),
        (
            (HEVA,),
            "Silver?",
            "Dr. Hakan Clinic doesn’t have a Silver package.",
            ["unverified_denial"],
        ),
        (
            (),
            "Sapphire?",
            "Dr. Hakan Clinic doesn't have a Sapphire package.",
            ["unverified_denial"],
        ),
        # Negations that do not govern the claim.
        ((HEVA,), "Platinum?", "No doubt Heva has a Platinum package.", ["unknown_package"]),
        ((HEVA,), "Is Gold $3,500?", "There's no question Gold is $3,500.", ["wrong_value"]),
        ((HEVA,), "Is Gold $3,500?", "Not only is Gold $3,500, it has 4 nights.", ["wrong_value"]),
        ((HEVA,), "Platinum?", "Heva has a Platinum package, right?", ["unknown_package"]),
        # Wrong arithmetic, operands from another package, wrong direction.
        (
            (HEVA,),
            "Left?",
            "Gold is $4,500 with a $600 deposit, so $4,000 remains.",
            ["unverified_calculation"],
        ),
        (
            (HEVA,),
            "Left?",
            "Silver has $3,900 remaining after the deposit.",
            ["unverified_calculation"],
        ),
        ((HEVA,), "Left?", "Silver's remaining balance is $1,500.", ["unverified_calculation"]),
        ((HEVA,), "Left?", "Gold's remaining balance is $4,500.", ["unverified_calculation"]),
        ((HEVA,), "Left?", "So $3,900 remains.", ["unverified_calculation"]),
        ((HEVA, HAKAN), "Cheaper?", "Silver is $200 cheaper.", ["unverified_calculation"]),
        ((HEVA, HAKAN), "Cheaper?", "Silver is cheaper by $200 USD.", ["unverified_calculation"]),
        (
            (HEVA, HAKAN),
            "Cheaper?",
            "Silver is cheaper by $300 than Sapphire.",
            ["unverified_calculation"],
        ),
        ((HEVA, HAKAN), "Cheaper?", "Gold is $200 cheaper.", ["unverified_calculation"]),
        (
            (HEVA, HAKAN),
            "Cheaper?",
            "Sapphire is $200 cheaper than Silver.",
            ["unverified_calculation"],
        ),
        (
            (HEVA, HAKAN),
            "Cheaper?",
            "Silver is $300 cheaper than Sapphire.",
            ["unverified_calculation"],
        ),
        ((HEVA, HAKAN), "More?", "Gold is $1,300 more than Sapphire.", []),
        ((HEVA,), "More?", "Gold's deposit is $100 more than Silver's.", []),
        ((HEVA,), "Gap?", "The difference between Silver and Gold is $1,500.", []),
        ((HEVA,), "Left?", "Gold is $4,500 with a $600 deposit, leaving $3,900.", []),
        # Currency mismatches.
        ((HEVA,), "Gold?", "Gold is €4,500.", ["wrong_value"]),
        (
            (HEVA,),
            "Left?",
            "Gold is $4,500 with a $600 deposit, so €3,900 remains.",
            ["unverified_calculation"],
        ),
        # False claims next to honest statements.
        ((HEVA,), "Confirm $999?", "I can't confirm $999, but Gold is $999.", ["wrong_value"]),
        (
            (HEVA,),
            "Platinum?",
            "I don't see a Platinum package, but Silver is $3,500.",
            ["wrong_value"],
        ),
        (
            (HEVA,),
            "Platinum?",
            "I don't see a Platinum package; Heva has a Diamond package.",
            ["unknown_package"],
        ),
    ],
)
def test_denials_negations_and_calculations_must_be_grounded(
    fixture: Fixture,
    calls: tuple[tuple[str, dict[str, Any]], ...],
    message: str,
    response: str,
    codes: list[str],
) -> None:
    assert _codes(response, _evidence(fixture, *calls), message) == codes


def test_numbers_must_appear_in_evidence_or_the_message(fixture: Fixture) -> None:
    evidence = _evidence(fixture, HEVA)
    assert _codes("Recovery takes 14 days.", evidence) == ["unsupported_number"]
    assert _codes("You said 14 days works.", evidence, "I can do 14 days") == []


def test_sentence_split_keeps_abbreviations() -> None:
    assert split_sentences("Dr. Hakan Clinic has Sapphire. It is $3,200.") == [
        "Dr. Hakan Clinic has Sapphire.",
        "It is $3,200.",
    ]
