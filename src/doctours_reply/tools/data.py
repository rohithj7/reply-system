"""The tables and canned results the tools read, loaded from a fixture's `tool_data.json`."""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

Record = dict[str, Any]


class _ToolTable(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SavedClinics(_ToolTable):
    count: int
    recommendationStatus: str
    ids: list[str]


class ClinicPreferences(_ToolTable):
    userId: str
    tentativeProcedureDates: Record


class ToolData(_ToolTable):
    clinics: list[Record]
    doctors: list[Record]
    packages: list[Record]
    consultation_reschedule_link: Record
    full_calls: Record
    latest_assessment: Record
    patient_context: Record
    patient_images: Record
    saved_clinics: SavedClinics
    promo_code: Record
    update_user: Record
    clinic_preferences: ClinicPreferences
    update_working_memory: Record

    @model_validator(mode="after")
    def _one_saved_id_per_clinic(self) -> Self:
        if len(self.saved_clinics.ids) != len(self.clinics):
            raise ValueError("saved_clinics.ids needs one id per clinic")
        return self
