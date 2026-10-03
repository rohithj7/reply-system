"""Deterministic escalation wording, used when no valid model-written handoff exists."""

from typing import Final

from doctours_reply.runtime.outcome import Escalation

HANDOFF_SENTENCE: Final = "Someone from our team will take it from here."
_REASONS: Final = {
    "unverified_reply": "Reply could not be verified",
    "controller_failure": "Automated reply failed",
}
DEFAULT_REASON: Final = "Needs a person to take over"


def template_escalation(code: str) -> Escalation:
    reason = _REASONS.get(code, DEFAULT_REASON)
    return Escalation(code=code, reason=reason, sentence=HANDOFF_SENTENCE)
