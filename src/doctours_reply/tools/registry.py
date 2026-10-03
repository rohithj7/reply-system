"""The 14 packet tools: argument models, read/write classification and `xTool` aliases."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from doctours_reply.tools import packet_tools
from doctours_reply.tools.data import ToolData

ToolKind = Literal["read", "write"]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NoArgs(ToolArgs):
    pass


class ClinicLookupArgs(ToolArgs):
    clinicId: str | None = None
    clinicName: str | None = None


class UserArgs(ToolArgs):
    userId: str | None = None


class FullCallsArgs(ToolArgs):
    chatId: str | None = None
    limit: int | float | None = None


class PaymentLinkArgs(ToolArgs):
    clinicPackageId: str | None = None
    type: str | None = None
    clinicId: str | None = None


class UpdateUserArgs(ToolArgs):
    firstName: str | None = None
    lastName: str | None = None
    userId: str | None = None


class ClinicPreferencesArgs(ToolArgs):
    clinicSelection: dict[str, JsonValue] | None = None
    userId: str | None = None


class WorkingMemoryArgs(ToolArgs):
    memory: dict[str, JsonValue] | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: ToolKind
    args_model: type[ToolArgs]
    function: Callable[[ToolData, Mapping[str, Any]], Any]


TOOLS: Final[Mapping[str, ToolSpec]] = MappingProxyType(
    {
        spec.name: spec
        for spec in (
            ToolSpec("getAllClinics", "read", NoArgs, packet_tools.get_all_clinics),
            ToolSpec("getClinicDoctors", "read", ClinicLookupArgs, packet_tools.get_clinic_doctors),
            ToolSpec(
                "getClinicPackages", "read", ClinicLookupArgs, packet_tools.get_clinic_packages
            ),
            ToolSpec(
                "getConsultationRescheduleLink",
                "read",
                UserArgs,
                packet_tools.get_consultation_reschedule_link,
            ),
            ToolSpec("getFullCalls", "read", FullCallsArgs, packet_tools.get_full_calls),
            ToolSpec("getLatestAssessment", "read", UserArgs, packet_tools.get_latest_assessment),
            ToolSpec("getPatientContext", "read", UserArgs, packet_tools.get_patient_context),
            ToolSpec("getPatientImages", "read", UserArgs, packet_tools.get_patient_images),
            ToolSpec("getPaymentLink", "read", PaymentLinkArgs, packet_tools.get_payment_link),
            ToolSpec("getSavedClinics", "read", UserArgs, packet_tools.get_saved_clinics),
            ToolSpec("issuePromoCode", "write", UserArgs, packet_tools.issue_promo_code),
            ToolSpec("updateUser", "write", UpdateUserArgs, packet_tools.update_user),
            ToolSpec(
                "updateUserClinicPreferences",
                "write",
                ClinicPreferencesArgs,
                packet_tools.update_user_clinic_preferences,
            ),
            ToolSpec(
                "updateWorkingMemory",
                "write",
                WorkingMemoryArgs,
                packet_tools.update_working_memory,
            ),
        )
    }
)


class UnknownToolError(LookupError):
    """No packet tool has this name or `xTool` alias."""


class ToolArgumentError(ValueError):
    """The arguments do not match the tool's parameters."""


def resolve_tool_name(name: str) -> str:
    """Map a function name or its `xTool` alias (packet L319) to the function name."""
    if name in TOOLS:
        return name
    if name.endswith("Tool") and name[: -len("Tool")] in TOOLS:
        return name[: -len("Tool")]
    raise UnknownToolError(name)


def call_tool(data: ToolData, name: str, args: Mapping[str, object]) -> Any:
    """Validate `args` against the tool's parameters, then run the tool."""
    spec = TOOLS[resolve_tool_name(name)]
    try:
        parsed = spec.args_model.model_validate(args)
    except ValidationError as exc:
        raise ToolArgumentError(f"{spec.name}: {exc}") from exc
    return spec.function(data, parsed.model_dump(exclude_unset=True))
