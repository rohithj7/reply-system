"""The `Reply` contract (packet L37-82)."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CollectionState(_Contract):
    areaAskCount: int | None = None
    lastAskedItem: Literal["area", "name", "photos", "none"] | None = None
    nameAskCount: int | None = None
    photoAskCount: int | None = None


class WorkingMemoryUpdates(_Contract):
    """A partial memory diff; serialize with `exclude_unset=True` so unset keys are omitted."""

    collectionState: CollectionState | None = None
    communicationStyle: Literal["detailed", "concise", "casual", "formal", "unknown"] | None = None
    escalationFlags: str | None = None
    keyConcerns: str | None = None
    patientName: str | None = None
    preferredPaymentMethod: (
        Literal["financing", "layaway", "pay_in_full", "cash_preference", "unknown"] | None
    ) = None
    procedureArea: str | None = None
    promisesMade: str | None = None
    targetProcedureWindow: (
        Literal[
            "within_3_months",
            "within_6_months",
            "within_8_months",
            "within_12_months",
            "over_12_months",
            "unknown",
        ]
        | None
    ) = None


class Reply(_Contract):
    response: str
    escalate: bool
    escalationReason: str | None
    templateId: None
    intent: str
    shouldFollowUp: bool
    followUpTiming: str | None
    attachmentUrls: list[str] | None = Field(max_length=3)
    highEngagement: bool
    workingMemoryUpdates: WorkingMemoryUpdates | None

    @model_validator(mode="after")
    def _escalation_reason_matches_escalate(self) -> Self:
        if self.escalate:
            if self.escalationReason is None or not self.escalationReason.strip():
                raise ValueError("escalationReason must be non-empty when escalate is true")
        elif self.escalationReason is not None:
            raise ValueError("escalationReason must be null when escalate is false")
        return self
