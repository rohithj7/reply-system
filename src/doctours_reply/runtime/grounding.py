"""Entity-linked grounding checks on a reply (plan 6.4).

Each money amount must resolve, within its own sentence, to exactly one of: a value the
patient gave and the reply attributes to them, a verified aggregate (minimum, maximum
or range over observed packages), a declared policy fact whose cue is in the clause, or
an attribute of the nearest named package (the deposit when the clause says "deposit",
otherwise the base price). Nothing carries over between sentences. Unit counts must
match the named package, named packages and clinics must exist and agree, and every
other number must appear in what the model was shown.

A negation governs a name or amount only within its clause, at most six words before it,
with no other amount or new predicate in between. Under one:

- a patient's amount that is not the fact is a correction, not a claim ("not $3,500");
- an amount equal to the fact, or a package observed at the clinic named, is a false
  denial;
- a package the patient named but no tool returned is not claimed ("I don't see a
  Platinum package"), and neither is one in a question;
- denying a package at a clinic needs that clinic's packages this turn.

A calculated amount is checked as one: next to "remains", "left" or "balance" it must
equal price minus deposit for the package named in its clause (else the nearest named);
next to "cheaper", "more" or "difference" it must equal the gap, in that direction, between
two packages named in the sentence ("than" picks the second). The currency must match.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from doctours_reply.runtime.evidence import URL, Evidence, Fact, parse_number


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str
    expected: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class Money:
    start: int
    end: int
    amount: Decimal
    currency: str


_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
_WORDS = {"usd": "USD", "eur": "EUR", "gbp": "GBP", "dollar": "USD", "euro": "EUR", "pound": "GBP"}
_AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_MONEY = re.compile(
    rf"(?P<sym>[$€£])\s?(?P<a1>{_AMOUNT})(?:\s?(?P<c1>USD|EUR|GBP)\b)?"
    rf"|\b(?P<c0>USD|EUR|GBP)\s?(?P<a0>{_AMOUNT})"
    rf"|(?<![\w.,])(?P<a2>{_AMOUNT})\s?(?P<c2>USD|EUR|GBP|dollars?|euros?|pounds?)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_CLAUSE_BREAK = re.compile(
    r"(?<!\d),|,(?!\d)|[;:—–()]|\s-\s|\b(?:and|but|while|whereas|with|plus|including)\b"
)
_ABBREVIATIONS = frozenset({"dr", "mr", "mrs", "ms", "st", "vs", "e.g", "i.e", "approx"})
_ATTRIBUTION = re.compile(
    r"\byou(?:'ve|\s+have)?\s+(?:mentioned|said|noted|saw|heard|been\s+quoted|"
    r"were\s+(?:quoted|told))\b|\bquoted\s+you\b|\byour\s+quote\b",
    re.IGNORECASE,
)
_MIN_CUE = re.compile(
    r"(?:start(?:s|ing)?\s+(?:at|from)|from|as\s+low\s+as|at\s+least|minimum\s+(?:of\s+)?)"
    r"\s*(?:about\s+|around\s+)?$",
    re.IGNORECASE,
)
_MAX_CUE = re.compile(
    r"(?:up\s+to|as\s+high\s+as|at\s+most|maximum\s+(?:of\s+)?)\s*(?:about\s+|around\s+)?$",
    re.IGNORECASE,
)
_BETWEEN_CUE = re.compile(r"\bbetween\s*(?:about\s+|around\s+)?$", re.IGNORECASE)
_RANGE_JOIN = re.compile(r"\s*(?:to|-|–|—)\s*$|\s*and\s*$", re.IGNORECASE)
_NAMED_PACKAGE = re.compile(r"\b([A-Z][a-z]+)\s+package\b")
_NAMED_CLINIC = re.compile(r"\b((?:Dr\.?\s+)?[A-Z][a-z]+)\s+Clinic\b")
_NOT_NAMES = frozenset(
    {"The", "This", "That", "Each", "Every", "Your", "Which", "What", "Any", "Our", "One"}
    | {"Doctours", "Their", "Its", "Same", "Other", "Another", "Cheaper", "Bigger", "Clinic"}
)
_NEGATION = re.compile(r"\b(?:no|not|never|cannot|without)\b|n['’]t\b", re.IGNORECASE)
_NOT_ONLY = re.compile(r"not\s+only\b", re.IGNORECASE)
_PREDICATE = re.compile(r"\b(?:is|are|was|were|has|includes|offers|costs)\b", re.IGNORECASE)
_SCOPE_WORDS = 6
_INTERROGATIVE = re.compile(
    r"\W*(?:which|what|who|where|when|how|do|does|did|is|are|was|were|can|could|would|"
    r"should|will|have|has|or)\b",
    re.IGNORECASE,
)
_LABEL_AFTER = re.compile(r"\s*(?:USD\s+)?(?:deposit|fee|price)\b", re.IGNORECASE)
_LABEL_BEFORE = re.compile(r"\b(?:deposit|fee|price|cost)\s+(?:of|is|was|at)?\s*$", re.IGNORECASE)
_REMAINDER_AFTER = re.compile(
    r"\s*(?:USD\s+)?(?:(?:still|is|are|would\s+be|will\s+be)\s+)?"
    r"(?:remain(?:s|ing)?|left|balance|outstanding)\b",
    re.IGNORECASE,
)
_REMAINDER_IN = re.compile(
    r"\b(?:remain(?:s|ing)?|remainder|balance|rest|left|leaving|leaves|outstanding)\b",
    re.IGNORECASE,
)
_COMPARISON_AFTER = re.compile(
    r"\s*(?:USD\s+)?(cheaper|less|lower|more|higher|pricier|difference)\b", re.IGNORECASE
)
_COMPARISON_BEFORE = re.compile(
    r"\b(cheaper|less|lower|more|higher|pricier)(?:\s+expensive)?\s+by\s*$", re.IGNORECASE
)
_DIFFERENCE_IN = re.compile(r"\bdifference\b", re.IGNORECASE)
_DENIED_AFTER = re.compile(
    r"\s+(?:package\s+)?(?:is\s+not|isn['’]t|are\s+not|aren['’]t|does\s+not|doesn['’]t)\s+"
    r"(?:offered|available|listed|exist|an?\s+option)\b",
    re.IGNORECASE,
)
_EXISTENCE = re.compile(
    r"have|has|having|offer|offers|offering|see|seeing|find|finding|list|lists|listing|carry|"
    r"carries|include|includes|show|shows|showing|sell|sells|provide|provides|identify|a|an|any",
    re.IGNORECASE,
)
_ARTICLES = frozenset({"a", "an", "any", "the", "such"})
_ADVERBS = frozenset({"currently", "yet", "really", "actually", "seem", "to", "appear"})
_POSSESSIVE = re.compile(r"['’]s\b")
_EMBEDDED_QUESTION = re.compile(r"\b(?:which|whether)\b", re.IGNORECASE)
_SUBJECT_OF = re.compile(
    r"\s+(?:package\s+)?(?:is|are|has|have|includes|offers|costs)\b(?!\s+not\b)", re.IGNORECASE
)
_COPULA_END = re.compile(r"(?:\b(?:is|of|be|leaves|leaving|remaining|remains|balance)|:)\s*$")
_LOWER = frozenset({"cheaper", "less", "lower"})
_HIGHER = frozenset({"more", "higher", "pricier"})


def money_mentions(text: str) -> list[Money]:
    found = []
    for match in _MONEY.finditer(text):
        amount = match.group("a1") or match.group("a0") or match.group("a2")
        word = (match.group("c1") or match.group("c0") or match.group("c2") or "").lower()
        currency = _WORDS.get(word.rstrip("s")) or _SYMBOLS[match.group("sym")]
        found.append(Money(match.start(), match.end(), parse_number(amount), currency))
    return found


def split_sentences(text: str) -> list[str]:
    parts, start = [], 0
    for match in re.finditer(r"[.!?]+(?=\s|$)|\n+", text):
        word = re.search(r"([\w.]+)$", text[start : match.start()])
        if match.group().startswith(".") and word and word.group(1).lower() in _ABBREVIATIONS:
            continue
        parts.append(text[start : match.end()].strip())
        start = match.end()
    parts.append(text[start:].strip())
    return [p for p in parts if p]


def format_money(amount: Decimal, currency: str) -> str:
    symbol = {v: k for k, v in _SYMBOLS.items()}.get(currency)
    number = f"{amount:,.2f}".removesuffix(".00")
    return f"{symbol}{number}" if symbol else f"{number} {currency}"


def check_grounding(response: str, evidence: Evidence, message: str) -> list[Violation]:
    message_numbers = {parse_number(n) for n in _NUMBER.findall(message)}
    message_words = set(re.findall(r"[a-z]+", message.lower()))
    violations: list[Violation] = []
    for sentence in split_sentences(response):
        if URL.fullmatch(sentence):
            continue
        violations += _check_sentence(sentence, evidence, message_numbers, message_words)
    return violations


def _check_sentence(
    sentence: str, evidence: Evidence, message_numbers: set[Decimal], message_words: set[str]
) -> list[Violation]:
    text = URL.sub(lambda m: " " * len(m.group()), sentence)
    packages = evidence.packages()
    package_spots = sorted(
        (m.start(), name) for name in packages for m in re.finditer(rf"\b{re.escape(name)}\b", text)
    )
    clinic_spots = _clinic_spots(text, evidence)
    violations = _name_violations(text, evidence, package_spots, clinic_spots, message_words)
    claimed: list[tuple[int, int]] = []
    mentions = money_mentions(text)
    skip: set[int] = set()
    for i, money in enumerate(mentions):
        if i in skip:
            continue
        claimed.append((money.start, money.end))
        if _ATTRIBUTION.search(text) and money.amount in message_numbers:
            continue
        calculation = _calculation(text, money, package_spots, packages)
        if calculation is not None:
            violations += calculation
            continue
        clause = _clause(text, money.start).lower()
        attribute = "depositAmount" if "deposit" in clause else "basePrice"
        prefix = text[: money.start]
        partner = mentions[i + 1] if i + 1 < len(mentions) else None
        joined = partner is not None and _RANGE_JOIN.fullmatch(text[money.end : partner.start])
        if (
            partner is not None
            and joined
            and ("and" not in text[money.end : partner.start] or _BETWEEN_CUE.search(prefix))
        ):
            skip.add(i + 1)
            claimed.append((partner.start, partner.end))
            violations += _aggregate(money, "min", attribute, text, evidence, clinic_spots)
            violations += _aggregate(partner, "max", attribute, text, evidence, clinic_spots)
        elif _MIN_CUE.search(prefix):
            violations += _aggregate(money, "min", attribute, text, evidence, clinic_spots)
        elif _MAX_CUE.search(prefix):
            violations += _aggregate(money, "max", attribute, text, evidence, clinic_spots)
        else:
            found, fact, label = _point_claim(money, attribute, clause, evidence, package_spots)
            if not _negated(text, money.start):
                violations += found
            elif fact is not None:
                violations.append(_denial(money, fact, label))
            elif money.amount not in message_numbers:
                violations += found
    unit_violations, unit_spans = _unit_checks(text, packages, package_spots)
    violations += unit_violations
    claimed += unit_spans
    for match in _NUMBER.finditer(text):
        if any(start <= match.start() < end for start, end in claimed):
            continue
        value = parse_number(match.group())
        if value not in evidence.numbers and value not in message_numbers:
            violations.append(
                Violation(
                    "unsupported_number",
                    f"{match.group()} does not appear in the tool results, the policies shown or "
                    "the patient's message.",
                )
            )
    return violations


def _same(money: Money, fact: Fact) -> bool:
    return money.amount == fact.value and money.currency == fact.unit


def _point_claim(
    money: Money,
    attribute: str,
    clause: str,
    evidence: Evidence,
    package_spots: Sequence[tuple[int, str]],
) -> tuple[list[Violation], Fact | None, str]:
    """Check an amount as a policy fact or a package attribute; return the fact it matches."""
    if cued := [f for f in evidence.policy_facts() if any(c in clause for c in f.cues)]:
        same = next((f for f in cued if _same(money, f)), None)
        label = cued[0].entity_name
        return ([] if same else [_mismatch(money, cued[0], label)]), same, label
    if (package := _nearest(package_spots, money.start)) is not None:
        fact = next((f for f in evidence.packages()[package] if f.attribute == attribute), None)
        label = f"{package} {'deposit' if attribute == 'depositAmount' else 'price'}"
        if fact is not None and _same(money, fact):
            return [], fact, label
        return [_mismatch(money, fact, label)], None, label
    unlinked = Violation(
        "unlinked_amount",
        f"{format_money(money.amount, money.currency)} is not tied to a package, policy fact "
        "or verified range in this sentence. Name the package next to the amount, or state it "
        "as a minimum, maximum or range over the packages.",
    )
    return [unlinked], None, ""


def _denial(money: Money, fact: Fact, label: str) -> Violation:
    expected = format_money(fact.value, fact.unit or "")
    return Violation(
        "false_denial",
        f"The reply denies {format_money(money.amount, money.currency)}, but that is the {label}.",
        f"{label} is {expected}",
        fact.source_ref,
    )


def _negation_gap(text: str, position: int) -> list[str] | None:
    """The words between a governing negation and `position`, or None if none governs it."""
    lead = _clause_lead(text, position)
    negations = list(_NEGATION.finditer(lead))
    if not negations or _NOT_ONLY.match(lead, negations[-1].start()):
        return None
    gap = lead[negations[-1].end() :]
    words = gap.split()
    if len(words) > _SCOPE_WORDS or _MONEY.search(gap) or _PREDICATE.search(" ".join(words[1:])):
        return None
    return words


def _negated(text: str, position: int) -> bool:
    return _negation_gap(text, position) is not None


def _denied(text: str, start: int, end: int) -> bool:
    """Whether the observed name at text[start:end] is said not to exist: it is the direct
    object of a negated "have", "offer", "see" and so on ("doesn't have a Gold package",
    "no Gold package"), or is followed by "isn't offered"."""
    after = text[end:]
    if _DENIED_AFTER.match(after):
        return True
    gap = _negation_gap(text, start)
    if gap is None or _POSSESSIVE.match(after) or _SUBJECT_OF.match(after):
        return False
    words = [w for w in gap if w.lower() not in _ADVERBS]
    if not words:
        negations = [m.group().lower() for m in _NEGATION.finditer(_clause_lead(text, start))]
        return negations[-1] == "no"
    head, rest = words[0], words[1:]
    return bool(_EXISTENCE.fullmatch(head)) and len(rest) <= 2 and set(rest) <= _ARTICLES


def _not_claimed(text: str, start: int, end: int) -> bool:
    """Whether a name the patient used is only denied or asked about at text[start:end]."""
    after = text[end:]
    return (
        _is_question(text)
        or bool(_EMBEDDED_QUESTION.search(_clause_lead(text, start)))
        or bool(_DENIED_AFTER.match(after))
        or (_negated(text, start) and not _SUBJECT_OF.match(after))
    )


def _is_question(text: str) -> bool:
    if not text.rstrip().endswith("?"):
        return False
    starts = [0, *(m.end() for m in _CLAUSE_BREAK.finditer(text))]
    return any(_INTERROGATIVE.match(text, start) for start in starts)


def _calculation(
    text: str,
    money: Money,
    package_spots: Sequence[tuple[int, str]],
    packages: dict[str, list[Fact]],
) -> list[Violation] | None:
    """Check an amount cued as a remainder or a difference; None if it is not one."""
    start, end = _clause_span(text, money.start)
    after, lead = text[money.end : end], text[start : money.start]
    remainder = bool(_REMAINDER_AFTER.match(after))
    cue = _COMPARISON_AFTER.match(after) or _COMPARISON_BEFORE.search(lead)
    if not remainder and not cue:
        if _LABEL_AFTER.match(after) or _LABEL_BEFORE.search(lead):
            return None
        remainder = bool(_REMAINDER_IN.search(lead) and _COPULA_END.search(lead))
        before = text[: money.start]
        mentions = list(_DIFFERENCE_IN.finditer(before))
        difference = (
            mentions
            and not _MONEY.search(before[mentions[-1].end() :])
            and _COPULA_END.search(before)
        )
        if not remainder and not difference:
            return None
    attribute = "depositAmount" if "deposit" in text[start:end].lower() else "basePrice"

    def value(name: str, attr: str) -> Fact | None:
        return next((f for f in packages[name] if f.attribute == attr), None)

    in_clause = [name for spot, name in package_spots if start <= spot < end]
    nearest = _nearest(package_spots, money.start)
    if remainder:
        subjects = in_clause or ([nearest] if nearest else [])
        for name in subjects:
            price, deposit = value(name, "basePrice"), value(name, "depositAmount")
            if (
                price
                and deposit
                and price.unit == deposit.unit == money.currency
                and price.value - deposit.value == money.amount
            ):
                return []
        return [_unverified(money, "price minus deposit for the package named next to it")]
    word = cue.group(1).lower() if cue else "difference"
    than = re.search(r"\bthan\b", after)
    if than:
        named = [n for s, n in package_spots if money.end + than.end() <= s < end]
        others = named[:1]
        subject = _nearest([(s, n) for s, n in package_spots if n not in others], money.start)
    else:
        subject = nearest
        others = sorted({n for _, n in package_spots} - {subject}) if subject else []
    for other in others:
        mine = value(subject, attribute) if subject else None
        theirs = value(other, attribute)
        if not (mine and theirs and mine.unit == theirs.unit == money.currency):
            continue
        gap = mine.value - theirs.value
        if (
            (word in _LOWER and -gap == money.amount)
            or (word in _HIGHER and gap == money.amount)
            or (word == "difference" and abs(gap) == money.amount)
        ):
            return []
    return [_unverified(money, "the gap between two packages named in the sentence")]


def _unverified(money: Money, needed: str) -> Violation:
    return Violation(
        "unverified_calculation",
        f"{format_money(money.amount, money.currency)} is stated as a calculated amount, but it "
        f"does not equal {needed}. Name the package or packages in the same sentence, and "
        "state the exact result in the same currency.",
    )


def _mismatch(money: Money, fact: Fact | None, label: str) -> Violation:
    stated = format_money(money.amount, money.currency)
    if fact is None:
        return Violation("wrong_value", f"{label}: {stated} has no supporting tool result.")
    expected = format_money(fact.value, fact.unit or "")
    return Violation(
        "wrong_value", f"{label} is stated as {stated}.", f"{label} is {expected}", fact.source_ref
    )


def _aggregate(
    money: Money,
    bound: str,
    attribute: str,
    text: str,
    evidence: Evidence,
    clinic_spots: Sequence[tuple[int, str]],
) -> list[Violation]:
    start, end = _clause_span(text, money.start)
    clinic_ids = {cid for spot, cid in clinic_spots if start <= spot < end} or {
        cid for _, cid in clinic_spots
    }
    facts = [
        f
        for group in evidence.packages().values()
        for f in group
        if f.attribute == attribute and (len(clinic_ids) != 1 or f.clinic_id in clinic_ids)
    ]
    label = ("lowest " if bound == "min" else "highest ") + (
        "deposit" if attribute == "depositAmount" else "price"
    )
    if not facts:
        return [Violation("unverified_aggregate", f"No observed packages support the {label}.")]
    target = (min if bound == "min" else max)(facts, key=lambda f: f.value)
    if _same(money, target):
        return []
    return [_mismatch(money, target, f"The {label}")]


def _clause_span(text: str, position: int) -> tuple[int, int]:
    start, end = 0, len(text)
    for match in _CLAUSE_BREAK.finditer(text):
        if match.end() <= position:
            start = match.end()
        elif match.start() >= position:
            end = match.start()
            break
    return start, end


def _clause(text: str, position: int) -> str:
    start, end = _clause_span(text, position)
    return text[start:end]


def _clause_lead(text: str, position: int) -> str:
    """The part of the clause containing `position` that comes before it."""
    return text[_clause_span(text, position)[0] : position]


def _nearest(spots: Sequence[tuple[int, str]], position: int) -> str | None:
    before = [s for s in spots if s[0] < position]
    if before:
        return max(before)[1]
    after = [s for s in spots if s[0] > position]
    return min(after)[1] if after else None


def _clinic_tokens(evidence: Evidence) -> dict[str, str]:
    tokens = {}
    for clinic_id, name in evidence.clinic_names.items():
        words = [w for w in re.findall(r"[A-Za-z]+", name) if w not in ("Dr", "Clinic")]
        if words:
            tokens[" ".join(words)] = clinic_id
    return tokens


def _clinic_spots(text: str, evidence: Evidence) -> list[tuple[int, str]]:
    return [
        (m.start(), clinic_id)
        for token, clinic_id in _clinic_tokens(evidence).items()
        for m in re.finditer(rf"\b{re.escape(token)}\b", text)
    ]


def _name_violations(
    text: str,
    evidence: Evidence,
    package_spots: Sequence[tuple[int, str]],
    clinic_spots: Sequence[tuple[int, str]],
    message_words: set[str],
) -> list[Violation]:
    violations = []
    tokens = _clinic_tokens(evidence)
    known_words = {w for token in tokens for w in token.split()} | set(evidence.packages())
    listed = {f.clinic_id for f in evidence.facts if f.entity_type == "package"}

    def clinics_near(position: int) -> set[str]:
        start, end = _clause_span(text, position)
        near = {clinic_id for spot, clinic_id in clinic_spots if start <= spot < end}
        return near or {clinic_id for _, clinic_id in clinic_spots}

    def unverified(clinic_ids: set[str]) -> list[Violation]:
        return [
            Violation(
                "unverified_denial",
                f"No tool result this turn lists {evidence.clinic_names.get(c, 'that clinic')}'s "
                "packages, so the reply cannot say a package is not offered there.",
            )
            for c in sorted(clinic_ids - listed)
        ]

    for match in _NAMED_PACKAGE.finditer(text):
        name = match.group(1)
        if name in known_words | _NOT_NAMES:
            continue
        if name.lower() in message_words and _not_claimed(text, match.start(), match.end()):
            if _denied(text, match.start(), match.end()):
                violations += unverified(clinics_near(match.start()))
            continue
        violations.append(
            Violation("unknown_package", f"No tool result this turn has a {match.group(0)}.")
        )
    for match in _NAMED_CLINIC.finditer(text):
        words = set(re.findall(r"[A-Za-z]+", match.group(1))) - {"Dr"}
        if not words & known_words and not words <= _NOT_NAMES:
            detail = f"{match.group(0)} is not a known clinic."
            violations.append(Violation("unknown_clinic", detail))
    named_clinics = {clinic_id for _, clinic_id in clinic_spots}
    packages = evidence.packages()
    for spot, name in package_spots:
        owner = packages[name][0]
        if _denied(text, spot, spot + len(name)):
            near = clinics_near(spot)
            if not near or owner.clinic_id in near:
                violations.append(
                    Violation(
                        "false_denial",
                        f"{name} is in this turn's tool results, but the reply says it is not.",
                        f"{name} is a {owner.clinic_name or 'listed'} package",
                        owner.source_ref,
                    )
                )
            else:
                violations += unverified(near)
            continue
        if named_clinics and owner.clinic_id not in named_clinics:
            violations.append(
                Violation(
                    "package_clinic_mismatch",
                    f"{name} is named with a clinic that does not offer it.",
                    f"{name} is a {owner.clinic_name or 'different clinic'} package",
                    owner.source_ref,
                )
            )
    return violations


def _unit_checks(
    text: str, packages: dict[str, list[Fact]], package_spots: Sequence[tuple[int, str]]
) -> tuple[list[Violation], list[tuple[int, int]]]:
    units = {
        f.unit
        for group in packages.values()
        for f in group
        if f.attribute not in ("basePrice", "depositAmount") and f.unit
    }
    violations, spans = [], []
    for unit in sorted(u for u in units if u):
        for match in re.finditer(rf"\b(\d+)\s+(?:[a-z]+\s+)?{re.escape(unit)}s?\b", text):
            spans.append(match.span(1))
            count = Decimal(match.group(1))
            package = _nearest(package_spots, match.start())
            candidates = [
                f
                for name, group in packages.items()
                if package is None or name == package
                for f in group
                if f.unit == unit
            ]
            if not any(f.value == count for f in candidates):
                expected = candidates[0] if package is not None and candidates else None
                violations.append(
                    Violation(
                        "wrong_value",
                        f"{match.group(0)} does not match the package's included {unit}s.",
                        f"{package} includes {expected.value} {unit}s" if expected else None,
                        expected.source_ref if expected else None,
                    )
                )
    return violations, spans
