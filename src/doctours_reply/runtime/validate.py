"""Deterministic reply checks. They read evidence only and never run tools or models."""

import re
from collections.abc import Sequence

from doctours_reply.contract.reply import WorkingMemoryUpdates
from doctours_reply.runtime.evidence import Evidence, ReadyLink, urls_in
from doctours_reply.runtime.grounding import (
    Violation,
    check_grounding,
    clinic_tokens,
    split_sentences,
)
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
_LINK_REQUESTS = {
    "payment": "The patient has decided on {name} and its payment link is ready: "
    "paste {url} exactly, alone on the last line.",
    "checkout": "The patient is ready to book at {name} and its checkout link is ready: "
    "paste {url} exactly, alone on the last line.",
    "assessment": "The policy {policy} answers this request with the patient's assessment "
    "link: paste {url} exactly, alone on the last line.",
}
_DECLINED_LINK = re.compile(
    r"\b(?:don[’']?t|do not|no need to)\s+(?:send|share|give|need|want)(?:\s+(?:me|us|it))?"
    r"(?:\s+(?:the|a|any|that|my|your))?(?:\s+[\w.]+){0,2}?\s+"
    r"(?:(checkout|payment|deposit|assessment)\s+)?links?\b",
    re.IGNORECASE,
)
_DECLINED_KINDS = {"assessment": ("assessment",), "": ("payment", "checkout", "assessment")}
_STILL_DECIDING = re.compile(
    r"\b(?:still (?:comparing|weighing|deciding|choosing)"
    r"|(?:before|once|until) I (?:settle|decide|choose|pick)"
    r"|(?:haven[’']?t|have not) (?:decided|chosen))\b",
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
    violations += _missing_links(response, evidence, message.text)
    violations += check_grounding(response, evidence, message.text)
    violations += _memory_violations(draft.workingMemoryUpdates)
    memory_text = draft.workingMemoryUpdates.model_dump_json() if draft.workingMemoryUpdates else ""
    if echoes_card_data(response + memory_text, message.card_digits):
        violations.append(Violation("card_echo", "Never repeat card digits from the message."))
    return violations


def check_policy_phrases(
    response: str, patterns: Sequence[tuple[str, re.Pattern[str]]]
) -> list[Violation]:
    """Phrases a loaded policy module forbids; `patterns` pairs a module ref with a regex."""
    return [
        Violation(
            "policy_phrase",
            f"The reply says {found.group(0)!r}, which a loaded policy forbids.",
            source_ref=ref,
        )
        for ref, pattern in patterns
        if (found := pattern.search(response))
    ]


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


def _missing_links(response: str, evidence: Evidence, message: str) -> list[Violation]:
    """A ready link the request calls for goes in the reply. Its kind and subject come from
    the request and the active policy, never from which links a tool returned: a required
    link no tool returned is the controller's to fetch, and no other link stands in for it.

    The patient's package is the one package the message names, else their selection; their
    clinic is the one clinic the message names or whose package it names, else their
    selection. A patient still deciding has neither. The deposit link is the first of the
    policy's `deposit_links` that fits: "payment" needs a package, "checkout" a clinic. A
    request a loaded policy answers with the assessment link needs it, unless a deposit link
    answers the patient's package. A link the patient asks not to be sent is never required."""
    declined = {
        kind
        for found in _DECLINED_LINK.finditer(message)
        for kind in _DECLINED_KINDS.get((found.group(1) or "").lower(), ("payment", "checkout"))
    }
    named = {n for n in evidence.package_clinics if _names(message, n)}
    clinics = {c for token, c in clinic_tokens(evidence).items() if _names(message, token)}
    clinics |= {c for n in named for c in evidence.package_clinics[n]}
    deciding = _STILL_DECIDING.search(message) is not None
    selection = evidence.selection
    package = not deciding and (len(named) == 1 or not named and "selectedPackageId" in selection)
    clinic = not deciding and (len(clinics) == 1 or not clinics and "selectedClinicId" in selection)
    kind = next(
        (k for k in evidence.deposit_links if (package if k == "payment" else clinic)), None
    )
    kind = None if kind in declined else kind
    mentioned = named if kind == "payment" else clinics

    def chosen(link: ReadyLink) -> bool:
        subject = link.name if link.kind == "payment" else link.clinic_id
        return mentioned <= {subject} and (link.selected or subject in mentioned)

    required = [k for k in evidence.links if k.kind == kind and chosen(k)]
    cue = next((ref for ref, cue in evidence.assessment_cues if cue.search(message)), None)
    if cue and "assessment" not in declined and not (package and kind):
        required += [k for k in evidence.links if k.kind == "assessment"]
    sent = set(urls_in(response))
    return [
        Violation(
            "missing_link",
            _LINK_REQUESTS[link.kind].format(name=link.name, url=link.url, policy=cue),
            source_ref=link.source_ref,
        )
        for link in required
        if link.url not in sent
    ]


def _names(message: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b", message, re.IGNORECASE) is not None


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
