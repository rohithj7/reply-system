"""Deterministic reply checks. They read evidence only and never run tools or models."""

import re
from collections.abc import Sequence

from doctours_reply.contract.reply import WorkingMemoryUpdates
from doctours_reply.runtime.evidence import Evidence, urls_in
from doctours_reply.runtime.grounding import Violation, check_grounding, split_sentences
from doctours_reply.runtime.outcome import Draft
from doctours_reply.runtime.payment_data import RedactedText, echoes_card_data

MAX_ESCALATION_WORDS = 20
MAX_REASON_WORDS = 12
_MARKDOWN = (
    re.compile(r"\*\*|__"),
    re.compile(r"^\s{0,3}#{1,6}\s", re.MULTILINE),
    re.compile(r"^\s*(?:[-*•]|\d+[.)])\s", re.MULTILINE),
    re.compile(r"(?<![\w*])\*[^*\s][^*\n]*\*(?![\w*])"),
)
_DATE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b"
    r"|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)


def check_answer(draft: Draft, evidence: Evidence, message: RedactedText) -> list[Violation]:
    response = draft.response
    violations: list[Violation] = []
    if not response.strip():
        violations.append(Violation("empty_response", "The response is empty."))
    if any(pattern.search(response) for pattern in _MARKDOWN):
        violations.append(
            Violation("markdown", "Use plain text: no bold, italics, headers or list markers.")
        )
    violations += _url_violations(response, draft.attachmentUrls or [], evidence)
    violations += check_grounding(response, evidence, message.text)
    violations += _memory_violations(draft.workingMemoryUpdates)
    memory_text = draft.workingMemoryUpdates.model_dump_json() if draft.workingMemoryUpdates else ""
    if echoes_card_data(response + memory_text, message.card_digits):
        violations.append(Violation("card_echo", "Never repeat card digits from the message."))
    return violations


def check_escalation_sentence(sentence: str, message: RedactedText) -> list[Violation]:
    violations = []
    if len(split_sentences(sentence)) != 1 or len(sentence.split()) > MAX_ESCALATION_WORDS:
        violations.append(
            Violation(
                "escalation_form",
                f"Use exactly one sentence of {MAX_ESCALATION_WORDS} words or fewer.",
            )
        )
    if urls_in(sentence) or re.search(r"[\d$€£]", sentence):
        violations.append(
            Violation("escalation_form", "No URL, digits or prices in an escalation sentence.")
        )
    if echoes_card_data(sentence, message.card_digits):
        violations.append(Violation("card_echo", "Never repeat card digits from the message."))
    return violations


def check_escalation_reason(reason: str, message: RedactedText) -> list[Violation]:
    violations = []
    if not reason.strip() or len(reason.split()) > MAX_REASON_WORDS or re.search(r"\d", reason):
        violations.append(
            Violation(
                "escalation_reason",
                f"The reason is {MAX_REASON_WORDS} words or fewer, with no digits.",
            )
        )
    if echoes_card_data(reason, message.card_digits):
        violations.append(Violation("card_echo", "Never repeat card digits from the message."))
    return violations


def repair_instructions(violations: Sequence[Violation]) -> str:
    lines = ["The reply was not sent because it failed these checks:"]
    for v in violations:
        line = f"- {v.code}: {v.detail}"
        if v.expected:
            line += f" Correct value: {v.expected}"
        if v.source_ref:
            line += f" (source: {v.source_ref})"
        lines.append(line)
    lines.append("Return the corrected reply as the same JSON object only. Do not call tools.")
    return "\n".join(lines)


def _url_violations(
    response: str, attachments: Sequence[str], evidence: Evidence
) -> list[Violation]:
    violations = []
    lines = response.rstrip().split("\n")
    trailing = 0
    while trailing < len(lines) and _only_url(lines[len(lines) - 1 - trailing]):
        trailing += 1
    body = "\n".join(lines[: len(lines) - trailing])
    if urls_in(body):
        violations.append(
            Violation("url_placement", "Every URL goes on its own line at the end of the reply.")
        )
    urls = urls_in(response)
    for url in sorted(set(urls) - evidence.response_urls):
        violations.append(
            Violation(
                "url_provenance",
                f"{url} was not returned by a tool this turn or declared as a static link.",
            )
        )
    for url in sorted(set(attachments) - evidence.attachment_urls):
        violations.append(
            Violation("attachment_provenance", f"Attachment {url} was not returned by a tool.")
        )
    if any("/payment/" in u for u in urls) and any(u.endswith("/checkout") for u in urls):
        violations.append(
            Violation("payment_and_checkout", "Send one link: a payment link or a checkout link.")
        )
    return violations


def _only_url(line: str) -> bool:
    found = urls_in(line)
    return len(found) == 1 and line.strip().rstrip(".,;:!?") == found[0]


def _memory_violations(memory: WorkingMemoryUpdates | None) -> list[Violation]:
    if memory is None:
        return []
    texts = [v for v in memory.model_dump(exclude_unset=True).values() if isinstance(v, str)]
    if any(_DATE.search(text) for text in texts):
        return [Violation("memory_date", "Working memory never stores tentative dates.")]
    return []
