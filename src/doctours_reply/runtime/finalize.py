"""Build the `Reply` from the terminal outcome. Pure: it reads the outcome and memory only."""

from collections.abc import Mapping
from typing import Any, Final

from doctours_reply.contract.reply import Reply, WorkingMemoryUpdates
from doctours_reply.runtime.outcome import TerminalOutcome

ESCALATION_INTENT: Final = "human handoff"


def finalize(outcome: TerminalOutcome, memory: Mapping[str, Any]) -> Reply:
    """Escalated replies take the ledger A-18 side fields; memory diffs drop unchanged keys."""
    if outcome.escalation is not None:
        escalation = outcome.escalation
        return Reply(
            response=escalation.sentence,
            escalate=True,
            escalationReason=escalation.reason,
            templateId=None,
            intent=ESCALATION_INTENT,
            shouldFollowUp=False,
            followUpTiming=None,
            attachmentUrls=[],
            highEngagement=False,
            workingMemoryUpdates=WorkingMemoryUpdates(escalationFlags=escalation.code),
        )
    assert outcome.draft is not None
    draft = outcome.draft
    return Reply(
        response=draft.response.strip(),
        escalate=False,
        escalationReason=None,
        templateId=None,
        intent=draft.intent,
        shouldFollowUp=draft.shouldFollowUp,
        followUpTiming=draft.followUpTiming,
        attachmentUrls=list(draft.attachmentUrls or []),
        highEngagement=draft.highEngagement,
        workingMemoryUpdates=memory_diff(draft.workingMemoryUpdates, memory),
    )


def memory_diff(
    updates: WorkingMemoryUpdates | None, memory: Mapping[str, Any]
) -> WorkingMemoryUpdates | None:
    if updates is None:
        return None
    diff: dict[str, Any] = {}
    for key, value in updates.model_dump(exclude_unset=True).items():
        current = memory.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            value = {k: v for k, v in value.items() if current.get(k) != v}
            if value:
                diff[key] = value
        elif key not in memory or current != value:
            diff[key] = value
    return WorkingMemoryUpdates.model_validate(diff) if diff else None
