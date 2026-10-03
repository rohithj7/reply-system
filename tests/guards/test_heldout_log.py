"""The committed held-out log is consistent and every held-out summary has its entry."""

from doctours_reply.evaluation.cases import FROZEN_HASHES, frozen_hash_problem
from doctours_reply.evaluation.schedule import (
    LOG_PATH,
    SCHEDULE,
    log_problems,
    read_log,
    summary_problems,
)


def test_the_log_is_consistent() -> None:
    entries = read_log(LOG_PATH)
    assert log_problems(entries) == []
    assert all(e.purpose in SCHEDULE for e in entries)


def test_every_committed_summary_has_a_current_entry() -> None:
    assert summary_problems(LOG_PATH.parent, read_log(LOG_PATH)) == []


def test_frozen_sets_match_their_committed_hashes() -> None:
    assert [problem for suite in FROZEN_HASHES if (problem := frozen_hash_problem(suite))] == []  # type: ignore[arg-type]
