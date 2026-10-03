"""The single terminal outcome of an item (plan guarantee 6)."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doctours_reply.contract.reply import WorkingMemoryUpdates

OutcomeKind = Literal["answered", "clarified", "escalated"]
OutcomeStage = Literal["route", "decide", "validation", "controller_failure"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Draft(_Frozen):
    """The patient-facing fields of a non-escalated reply, before finalizing."""

    response: str
    intent: str
    shouldFollowUp: bool
    followUpTiming: str | None
    attachmentUrls: list[str] | None = Field(max_length=3)
    highEngagement: bool
    workingMemoryUpdates: WorkingMemoryUpdates | None


class Escalation(_Frozen):
    code: str
    reason: str
    sentence: str


class TerminalOutcome(_Frozen):
    kind: OutcomeKind
    stage: OutcomeStage | None
    draft: Draft | None = None
    escalation: Escalation | None = None
    executed_writes: tuple[str, ...] = ()
    """Call IDs of writes that ran in this item before the outcome was set."""

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Self:
        escalated = self.kind == "escalated"
        if escalated != (self.escalation is not None) or escalated == (self.draft is not None):
            raise ValueError("an escalated outcome has an escalation and no draft; others a draft")
        if escalated != (self.stage is not None):
            raise ValueError("only an escalated outcome has a stage")
        return self


class OutcomeAlreadySetError(RuntimeError):
    """An item's terminal outcome was assigned twice."""


class OutcomeSlot:
    """Holds an item's terminal outcome; it can be assigned exactly once."""

    def __init__(self) -> None:
        self._outcome: TerminalOutcome | None = None

    def set(self, outcome: TerminalOutcome) -> None:
        if self._outcome is not None:
            raise OutcomeAlreadySetError(f"outcome already {self._outcome.kind}")
        self._outcome = outcome

    @property
    def outcome(self) -> TerminalOutcome | None:
        return self._outcome
