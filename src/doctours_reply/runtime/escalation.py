"""Deterministic escalation wording, used when no valid model-written handoff exists."""

from typing import Final

from doctours_reply.runtime.outcome import Escalation

HANDOFF_SENTENCE: Final = "Someone from our team will take it from here."
_TEAM: Final = "so someone from our team will take it from here."
_REASONS: Final = {
    "unverified_reply": "Reply could not be verified",
    "controller_failure": "Automated reply failed",
    "human_requested": "Patient asked for a person",
    "unsupported_payment_action": "Asked for a payment action I cannot do",
    "unsupported_money_movement": "Asked to move money already paid",
    "unsupported_clinic_contact": "Asked me to contact a clinic for them",
    "unsupported_date_hold": "Asked to hold a date",
    "unsupported_booking_change": "Asked to change a booking",
    "unsupported_document_action": "Asked me to handle a document",
    "unsupported_other": "Asked for an action I cannot do",
}
_SENTENCES: Final = {
    "human_requested": "Of course, someone from our team will take it from here.",
    "unsupported_payment_action": f"I can't process payments myself, {_TEAM}",
    "unsupported_money_movement": f"I can't move money that's already been paid, {_TEAM}",
    "unsupported_clinic_contact": f"I can't contact the clinic for you, {_TEAM}",
    "unsupported_date_hold": f"I can't hold dates, {_TEAM}",
    "unsupported_booking_change": f"I can't change bookings myself, {_TEAM}",
    "unsupported_document_action": f"I can't send or handle documents, {_TEAM}",
}
DEFAULT_REASON: Final = "Needs a person to take over"


def template_escalation(code: str) -> Escalation:
    reason = _REASONS.get(code, DEFAULT_REASON)
    return Escalation(code=code, reason=reason, sentence=_SENTENCES.get(code, HANDOFF_SENTENCE))
