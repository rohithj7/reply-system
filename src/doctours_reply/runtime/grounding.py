"""Entity-linked grounding checks on a reply (plan 6.4).

Each money amount must resolve, within its own sentence, to exactly one of: a value the
patient gave and the reply attributes to them, a verified aggregate (minimum, maximum
or range over observed packages), a declared policy fact whose cue is in the clause, or
an attribute of the nearest named package (the deposit when the clause says "deposit",
otherwise the base price). Nothing carries over between sentences. Unit counts must
match the named package, named packages and clinics must exist and agree, and every
other number must appear in what the model was shown.
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
    | {"Doctours", "Their", "Its", "Same", "Other", "Another", "Cheaper", "Bigger"}
)


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
    violations: list[Violation] = []
    for sentence in split_sentences(response):
        if URL.fullmatch(sentence):
            continue
        violations += _check_sentence(sentence, evidence, message_numbers)
    return violations


def _check_sentence(
    sentence: str, evidence: Evidence, message_numbers: set[Decimal]
) -> list[Violation]:
    text = URL.sub(lambda m: " " * len(m.group()), sentence)
    packages = evidence.packages()
    package_spots = [
        (m.start(), name) for name in packages for m in re.finditer(rf"\b{re.escape(name)}\b", text)
    ]
    clinic_spots = _clinic_spots(text, evidence)
    violations = _name_violations(text, evidence, package_spots, clinic_spots)
    claimed: list[tuple[int, int]] = []
    mentions = money_mentions(text)
    skip: set[int] = set()
    for i, money in enumerate(mentions):
        if i in skip:
            continue
        claimed.append((money.start, money.end))
        if _ATTRIBUTION.search(text) and money.amount in message_numbers:
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
        elif cued := [f for f in evidence.policy_facts() if any(c in clause for c in f.cues)]:
            if not any(_same(money, f) for f in cued):
                violations.append(_mismatch(money, cued[0], cued[0].entity_name))
        elif (package := _nearest(package_spots, money.start)) is not None:
            fact = next((f for f in packages[package] if f.attribute == attribute), None)
            if fact is None or not _same(money, fact):
                label = "deposit" if attribute == "depositAmount" else "price"
                violations.append(_mismatch(money, fact, f"{package} {label}"))
        else:
            violations.append(
                Violation(
                    "unlinked_amount",
                    f"{format_money(money.amount, money.currency)} is not tied to a package, "
                    "policy fact or verified range in this sentence. Name the package next to "
                    "the amount, or state it as a minimum, maximum or range over the packages.",
                )
            )
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
    clinic_ids = {clinic_id for _, clinic_id in clinic_spots}
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


def _clause(text: str, position: int) -> str:
    start, end = 0, len(text)
    for match in _CLAUSE_BREAK.finditer(text):
        if match.end() <= position:
            start = match.end()
        elif match.start() >= position:
            end = match.start()
            break
    return text[start:end]


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
) -> list[Violation]:
    violations = []
    tokens = _clinic_tokens(evidence)
    known_words = {w for token in tokens for w in token.split()} | set(evidence.packages())
    for match in _NAMED_PACKAGE.finditer(text):
        if match.group(1) not in known_words | _NOT_NAMES:
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
    for _, name in package_spots:
        owner = packages[name][0]
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
