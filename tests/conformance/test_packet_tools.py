import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from doctours_reply.runtime.refs import resolve_fixture
from doctours_reply.tools import packet_tools
from doctours_reply.tools.registry import TOOLS

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "tests" / "conformance" / "reference" / "packet_tools.ts"
GOLDENS = json.loads(
    (REPO_ROOT / "tests" / "conformance" / "goldens" / "packet_tools.json").read_text("utf-8")
)
PORTED = {name: spec.function for name, spec in TOOLS.items()} | {
    "findClinic": packet_tools.find_clinic
}
TOOL_DATA = resolve_fixture("packet").tool_data


def test_goldens_were_generated_from_the_committed_reference() -> None:
    assert GOLDENS["source_sha256"] == hashlib.sha256(REFERENCE.read_bytes()).hexdigest()


def test_reference_defines_exactly_the_ported_functions() -> None:
    defined = set(re.findall(r"^function (\w+)\(", REFERENCE.read_text("utf-8"), re.MULTILINE))
    assert defined == set(PORTED)
    assert {case["function"] for case in GOLDENS["cases"]} == set(PORTED)


@pytest.mark.parametrize(
    "case",
    GOLDENS["cases"],
    ids=[f"{case['function']}-{i}" for i, case in enumerate(GOLDENS["cases"])],
)
def test_port_matches_typescript_golden(case: dict[str, Any]) -> None:
    result = PORTED[case["function"]](TOOL_DATA, case["args"] or {})
    # Key order is compared too: the model sees these objects serialized.
    assert json.dumps(result, ensure_ascii=False) == json.dumps(case["result"], ensure_ascii=False)


@pytest.mark.parametrize(
    ("function", "args"),
    [
        ("getAllClinics", {}),
        ("getClinicPackages", {"clinicName": "Heva"}),
        ("getClinicDoctors", {"clinicName": "Hakan"}),
        ("getSavedClinics", {}),
        ("getPatientContext", {}),
        ("getPatientImages", {}),
        ("getPaymentLink", {"type": "payment", "clinicPackageId": TOOL_DATA.packages[0]["id"]}),
        ("updateUserClinicPreferences", {}),
        ("updateWorkingMemory", {}),
    ],
)
def test_results_are_deep_copies(function: str, args: dict[str, Any]) -> None:
    before = TOOL_DATA.model_dump()
    first = PORTED[function](TOOL_DATA, args)
    expected = json.dumps(first)
    _scramble(first)
    assert json.dumps(PORTED[function](TOOL_DATA, args)) == expected
    assert TOOL_DATA.model_dump() == before


def _scramble(value: Any) -> None:
    if isinstance(value, dict):
        for key in list(value):
            _scramble(value[key])
            value[key] = "changed" if not isinstance(value[key], dict | list) else value[key]
        value["injected"] = True
    elif isinstance(value, list):
        for item in value:
            _scramble(item)
        value.append("injected")
