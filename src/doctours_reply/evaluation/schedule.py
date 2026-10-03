"""The fixed held-out schedule and its append-only log (plan 8.2).

A held-out or sealed suite runs only under a schedule row, once per row. The entry is
appended before the run starts, so an aborted run still counts; `--void-previous`
marks it void for an infrastructure failure and never deletes it. Rows that compare
systems need their section in `eval/preregistration.md` first.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from doctours_reply.evaluation.cases import EVAL_DIR


@dataclass(frozen=True)
class ScheduleRow:
    row_id: str
    suite: str
    systems: tuple[str, ...]
    preregistered: bool


SCHEDULE: Final = {
    row.row_id: row
    for row in (
        ScheduleRow("phase2-s0-baseline", "heldout_v1", ("baseline",), False),
        ScheduleRow("phase3-s0-vs-s1", "heldout_v1", ("baseline", "modular"), True),
        ScheduleRow("phase5-s0-s3", "heldout_v2", ("baseline", "modular"), True),
        ScheduleRow("phase6-hosted-parity", "heldout_v2", ("modular",), False),
        ScheduleRow("phase7-sealed", "sealed", ("baseline", "modular"), False),
    )
}
LOG_PATH: Final = EVAL_DIR / "results" / "heldout-log.md"
PREREGISTRATION_PATH: Final = EVAL_DIR / "preregistration.md"
_COLUMNS: Final = (
    "#",
    "date",
    "purpose",
    "set",
    "set sha256",
    "systems",
    "config sha256",
    "git sha",
    "prereg sha256",
    "status",
)
_VOID: Final = re.compile(r"^void #(\d+): .+")


class ScheduleError(ValueError):
    """The requested held-out run is not allowed by the schedule."""


@dataclass(frozen=True)
class LogEntry:
    number: int
    date: str
    purpose: str
    set: str
    set_sha256: str
    systems: str
    config_sha256: str
    git_sha: str
    prereg_sha256: str
    status: str

    def cells(self) -> list[str]:
        return [str(self.number), *(getattr(self, f) for f in _FIELDS[1:])]


_FIELDS: Final = tuple(LogEntry.__dataclass_fields__)


def read_log(path: Path = LOG_PATH) -> list[LogEntry]:
    entries = []
    for line in path.read_text("utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == len(_COLUMNS) and cells[0].isdigit():
            entries.append(LogEntry(int(cells[0]), *cells[1:]))
    return entries


def log_problems(entries: Sequence[LogEntry]) -> list[str]:
    problems = []
    for position, entry in enumerate(entries, 1):
        if entry.number != position:
            problems.append(f"entry {entry.number} is out of sequence")
        if entry.purpose not in SCHEDULE:
            problems.append(f"entry {entry.number} names unknown purpose {entry.purpose!r}")
        void = _VOID.match(entry.status)
        if entry.status != "valid" and not void:
            problems.append(f"entry {entry.number} has bad status {entry.status!r}")
        if void:
            target = int(void.group(1))
            earlier = entries[target - 1] if 0 < target < position else None
            if earlier is None or earlier.purpose != entry.purpose or earlier.status != "valid":
                problems.append(f"entry {entry.number} voids an invalid target #{target}")
    for row_id in SCHEDULE:
        if len(current_entries(entries, row_id)) > 1:
            problems.append(f"{row_id} has more than one valid entry")
    return problems


def current_entries(entries: Sequence[LogEntry], row_id: str) -> list[LogEntry]:
    voided = {int(m.group(1)) for e in entries if (m := _VOID.match(e.status))}
    return [
        e for e in entries if e.purpose == row_id and e.status == "valid" and e.number not in voided
    ]


def begin_logged_run(
    row_id: str,
    *,
    suites: Sequence[str],
    systems: Sequence[str],
    set_sha256: str,
    config_sha256: str,
    git_sha: str,
    date: str,
    void_reason: str | None = None,
    log_path: Path = LOG_PATH,
    preregistration_path: Path = PREREGISTRATION_PATH,
) -> LogEntry:
    """Check the schedule, then append this run's entry (and any void marker) to the log."""
    row = SCHEDULE.get(row_id)
    if row is None:
        raise ScheduleError(f"{row_id!r} is not a schedule row: {', '.join(SCHEDULE)}")
    if row.suite not in suites or tuple(systems) != row.systems:
        raise ScheduleError(f"{row_id} runs {row.suite} with systems {', '.join(row.systems)}")
    prereg_sha = "-"
    if preregistration_path.is_file():
        prereg_sha = hashlib.sha256(preregistration_path.read_bytes()).hexdigest()
    if row.preregistered and (
        prereg_sha == "-"
        or not re.search(
            rf"^## {re.escape(row_id)}\b", preregistration_path.read_text("utf-8"), re.M
        )
    ):
        raise ScheduleError(f"{row_id} needs its section in {preregistration_path.name} first")
    entries = read_log(log_path)
    if problems := log_problems(entries):
        raise ScheduleError("held-out log is inconsistent: " + "; ".join(problems))
    current = current_entries(entries, row_id)
    new: list[LogEntry] = []
    if void_reason is not None:
        reason = " ".join(void_reason.replace("|", "/").split())
        if not reason:
            raise ScheduleError("--void-previous needs the infrastructure failure as its reason")
        if not current:
            raise ScheduleError(f"{row_id} has no entry to void")
        new.append(
            LogEntry(
                len(entries) + 1,
                date,
                row_id,
                row.suite,
                "-",
                "-",
                "-",
                git_sha,
                "-",
                f"void #{current[0].number}: {reason}",
            )
        )
    elif current:
        raise ScheduleError(
            f"{row_id} already ran as entry #{current[0].number}; a repeat needs "
            '--void-previous "<infrastructure reason>"'
        )
    entry = LogEntry(
        len(entries) + len(new) + 1,
        date,
        row_id,
        row.suite,
        set_sha256,
        ",".join(systems),
        config_sha256,
        git_sha,
        prereg_sha,
        "valid",
    )
    with log_path.open("a", encoding="utf-8") as handle:
        for item in [*new, entry]:
            handle.write("| " + " | ".join(item.cells()) + " |\n")
    return entry


def summary_problems(results_dir: Path, entries: Sequence[LogEntry]) -> list[str]:
    """Every committed held-out summary must belong to a current log entry."""
    problems = []
    for path in sorted(results_dir.glob("*.md")):
        if path.name == LOG_PATH.name:
            continue
        row = next((r for r in SCHEDULE if path.name.startswith(r)), None)
        if row is None or not current_entries(entries, row):
            problems.append(f"{path.name} has no current held-out log entry")
    return problems
