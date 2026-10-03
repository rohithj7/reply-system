import pytest

from doctours_reply.runtime.refs import resolve_fixture
from doctours_reply.tools.packet_tools import get_clinic_packages
from doctours_reply.tools.registry import (
    TOOLS,
    ToolArgumentError,
    UnknownToolError,
    call_tool,
    resolve_tool_name,
)

TOOL_DATA = resolve_fixture("packet").tool_data

READS = {
    "getAllClinics",
    "getClinicDoctors",
    "getClinicPackages",
    "getConsultationRescheduleLink",
    "getFullCalls",
    "getLatestAssessment",
    "getPatientContext",
    "getPatientImages",
    "getPaymentLink",
    "getSavedClinics",
}
WRITES = {"issuePromoCode", "updateUser", "updateUserClinicPreferences", "updateWorkingMemory"}


def test_registry_holds_exactly_the_fourteen_packet_functions() -> None:
    assert len(TOOLS) == 14
    assert {name for name, spec in TOOLS.items() if spec.kind == "read"} == READS
    assert {name for name, spec in TOOLS.items() if spec.kind == "write"} == WRITES
    assert all(spec.name == name for name, spec in TOOLS.items())


@pytest.mark.parametrize("name", sorted(READS | WRITES))
def test_function_names_and_tool_aliases_resolve(name: str) -> None:
    assert resolve_tool_name(name) == name
    assert resolve_tool_name(f"{name}Tool") == name


@pytest.mark.parametrize(
    "name", ["findClinic", "getAllClinicsTools", "Tool", "getTripDetailsTool", "getallclinics"]
)
def test_unknown_names_are_rejected(name: str) -> None:
    with pytest.raises(UnknownToolError):
        resolve_tool_name(name)


@pytest.mark.parametrize("name", sorted(READS | WRITES))
def test_unknown_argument_keys_are_rejected(name: str) -> None:
    with pytest.raises(ToolArgumentError):
        call_tool(TOOL_DATA, name, {"unknownKey": "x"})


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("getClinicPackages", {"clinicId": 5}),
        ("getClinicPackages", {"clinicName": ["Heva"]}),
        ("getPaymentLink", {"type": True}),
        ("getFullCalls", {"limit": "5"}),
        ("updateUserClinicPreferences", {"clinicSelection": "Heva"}),
        ("updateWorkingMemory", {"memory": ["Jordan"]}),
    ],
)
def test_wrong_argument_types_are_rejected(name: str, args: dict[str, object]) -> None:
    with pytest.raises(ToolArgumentError):
        call_tool(TOOL_DATA, name, args)


def test_call_tool_runs_the_port_with_validated_arguments() -> None:
    args = {"clinicName": "heva", "clinicId": None}
    assert call_tool(TOOL_DATA, "getClinicPackagesTool", args) == get_clinic_packages(
        TOOL_DATA, args
    )
    assert call_tool(TOOL_DATA, "getAllClinics", {})["clinics"] == TOOL_DATA.clinics
