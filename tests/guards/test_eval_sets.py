"""Evaluation sets stay separate: no message text appears in two suites."""

import json
import re
from pathlib import Path

from doctours_reply.evaluation.cases import EVAL_DIR, GUARDED_SUITES, SUITES, load_suite

NEAR_COPY = 0.75


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def test_no_open_case_is_a_near_copy_of_a_heldout_case() -> None:
    heldout = [(c.case_id, _words(c.text)) for s in GUARDED_SUITES for c in load_suite(s)]
    for suite in SUITES:
        if suite in GUARDED_SUITES:
            continue
        for case in load_suite(suite):
            words = _words(case.text)
            for heldout_id, heldout_words in heldout:
                overlap = len(words & heldout_words) / max(1, len(words | heldout_words))
                assert overlap < NEAR_COPY, (case.case_id, heldout_id)


def test_no_message_text_appears_twice_across_suites() -> None:
    seen: dict[str, str] = {}
    for suite in SUITES:
        for case in load_suite(suite):
            text = _normalized(case.text)
            assert text not in seen, (case.case_id, seen.get(text))
            seen[text] = case.case_id


def test_case_ids_are_unique_across_suites() -> None:
    seen: dict[str, str] = {}
    for suite in SUITES:
        for case in load_suite(suite):
            assert case.case_id not in seen, (case.case_id, seen.get(case.case_id), suite)
            seen[case.case_id] = suite


def test_official_labels_do_not_copy_expected_outputs() -> None:
    expected = json.loads((EVAL_DIR / "official" / "expected_replies.json").read_text("utf-8"))
    labels = Path(EVAL_DIR / SUITES["official"]).read_text("utf-8")
    for row in expected:
        assert row["response"] not in labels
        if row["escalationReason"]:
            assert row["escalationReason"] not in labels
