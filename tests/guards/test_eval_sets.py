"""Evaluation sets stay separate: no message text appears in two suites."""

import json
from pathlib import Path

from doctours_reply.evaluation.cases import EVAL_DIR, SUITES, load_suite


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


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
