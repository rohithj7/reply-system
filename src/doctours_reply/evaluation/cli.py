"""`doctours-reply eval`: run suites through a system, score them and write a report.

Held-out suites run only with `--log-entry <schedule row>`. `--dry-run` validates every
case, label and reference without calling a model.
"""

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, cast, get_args

from doctours_reply.cli import git_sha, new_run_id
from doctours_reply.contract.io import InputItem
from doctours_reply.evaluation.cases import (
    GUARDED_SUITES,
    SUITES,
    Case,
    CaseError,
    Suite,
    check_case,
    frozen_hash_problem,
    load_suite,
    suite_sha256,
)
from doctours_reply.evaluation.judge import judge_reply
from doctours_reply.evaluation.report import write_report
from doctours_reply.evaluation.schedule import ScheduleError, begin_logged_run
from doctours_reply.evaluation.scorer import CaseScore, load_expected, score_case
from doctours_reply.models.client import ModelClient, ModelConfigError
from doctours_reply.models.openai_compat import ModelSettings, OpenAICompatClient
from doctours_reply.runtime.pipeline import ItemFailedError, RunInfo, System, run_item
from doctours_reply.runtime.refs import (
    Fixture,
    PolicySet,
    RefError,
    resolve_fixture,
    resolve_policy_set,
)
from doctours_reply.trace.sink import TraceSink

MAX_RUNS = 5


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doctours-reply eval", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--suite", required=True, help=f"comma-separated {', '.join(SUITES)}, or all"
    )
    parser.add_argument("--system", default="baseline", help="comma-separated: baseline, modular")
    parser.add_argument("--runs", type=int, default=1, help=f"1-{MAX_RUNS} runs per system")
    parser.add_argument("--report", type=Path, help="default: runs/eval-<run id>/")
    parser.add_argument("--log-entry", help="schedule row; required for held-out suites")
    parser.add_argument("--void-previous", metavar="REASON", help="infrastructure failure to void")
    parser.add_argument("--judge", action="store_true", help="also score with the JUDGE_* model")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="validate cases; call no model")
    args = parser.parse_args(argv)
    try:
        suites = _suites(args.suite)
        systems = _systems(args.system)
        cases = {suite: load_suite(suite) for suite in suites}
        problems = [p for suite in suites if (p := frozen_hash_problem(suite))]
        problems += [p for suite in suites for case in cases[suite] for p in _case_problems(case)]
    except (CaseError, RefError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if problems:
        print("\n".join(f"error: {p}" for p in problems), file=sys.stderr)
        return 2
    if args.dry_run:
        for suite in suites:
            print(f"{suite}: {len(cases[suite])} cases, labels and references ok")
        return 0
    guarded = [s for s in suites if s in GUARDED_SUITES]
    if guarded and not args.log_entry:
        print(
            f"error: {', '.join(guarded)} runs only through the schedule; pass --log-entry",
            file=sys.stderr,
        )
        return 2
    if args.log_entry and not guarded:
        print("error: --log-entry is only for held-out suites", file=sys.stderr)
        return 2
    if args.void_previous is not None and not args.log_entry:
        print("error: --void-previous needs --log-entry", file=sys.stderr)
        return 2
    if not 1 <= args.runs <= MAX_RUNS or not 1 <= args.concurrency <= 16:
        print(f"error: --runs must be 1-{MAX_RUNS} and --concurrency 1-16", file=sys.stderr)
        return 2
    try:
        settings = ModelSettings.from_env(os.environ)
        judge_settings = ModelSettings.from_env(os.environ, "JUDGE") if args.judge else None
    except ModelConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    system_models = {
        settings.model_id,
        settings.model_for("controller"),
        settings.model_for("writer"),
    }
    if judge_settings and judge_settings.model_id in system_models:
        print(
            "error: the judge must be a different model from MODEL_ID, CONTROLLER_MODEL_ID"
            " and WRITER_MODEL_ID",
            file=sys.stderr,
        )
        return 3
    config = {
        "suites": {s: suite_sha256(s) for s in suites},
        "systems": systems,
        "runs": args.runs,
        "model": settings.public_config(),
        "judge": judge_settings.public_config() if judge_settings else None,
    }
    config["config_sha256"] = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()
    run_id = new_run_id()
    sha = git_sha() or "unknown"
    if args.log_entry:
        try:
            entry = begin_logged_run(
                args.log_entry,
                suites=suites,
                systems=systems,
                set_sha256=suite_sha256(guarded[0]),
                config_sha256=config["config_sha256"],
                git_sha=sha,
                date=f"{datetime.now(UTC):%Y-%m-%d}",
                void_reason=args.void_previous,
            )
        except ScheduleError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"held-out log entry #{entry.number} appended for {args.log_entry}", file=sys.stderr)
    report_dir = args.report or Path("runs") / f"eval-{run_id}"
    client = OpenAICompatClient(settings)
    judge = OpenAICompatClient(judge_settings) if judge_settings else None
    run = RunInfo(run_id, sha, settings.public_config())
    expected = load_expected() if "official" in suites else {}
    scores: list[CaseScore] = []
    try:
        for system in systems:
            for number in range(1, args.runs + 1):
                sink = TraceSink(report_dir / "traces" / f"{system}-run{number}")
                for suite in suites:
                    scores += _run_suite(
                        cases[suite],
                        suite,
                        system,
                        number,
                        client,
                        judge,
                        run,
                        sink,
                        args.concurrency,
                        expected,
                    )
    except ItemFailedError as exc:
        print(f"error: {exc}; partial traces in {report_dir}", file=sys.stderr)
        return 4
    write_report(report_dir, scores, {"run_id": run_id, "git_sha": sha, **config})
    print(f"report: {report_dir / 'summary.md'}", file=sys.stderr)
    return 0


def _run_suite(
    cases: Sequence[Case],
    suite: str,
    system: System,
    number: int,
    client: ModelClient,
    judge: ModelClient | None,
    run: RunInfo,
    sink: TraceSink,
    concurrency: int,
    expected: dict[str, Any],
) -> list[CaseScore]:
    def one(index: int, case: Case) -> CaseScore:
        fixture, policy_set = _refs(case.fixture_id, case.policy_set_id)
        try:
            result = run_item(
                index,
                InputItem(id=case.case_id, text=case.text),
                fixture=fixture,
                policy_set=policy_set,
                client=client,
                run=run,
                system=system,
            )
        except ItemFailedError as exc:
            sink.write(exc.trace)
            raise
        sink.write(result.trace)
        score = score_case(
            case,
            suite,
            system,
            number,
            result.reply,
            result.trace,
            fixture,
            expected.get(case.case_id) if suite == "official" else None,
        )
        if judge is not None:
            verdict = judge_reply(
                judge, result.trace.message, result.trace.observations, result.reply
            )
            score = replace(score, judge=verdict.model_dump() if verdict else None)
        return score

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(one, range(len(cases)), cases))


@cache
def _refs(fixture_id: str, policy_set_id: str) -> tuple[Fixture, PolicySet]:
    return resolve_fixture(fixture_id), resolve_policy_set(policy_set_id)


def _case_problems(case: Case) -> list[str]:
    fixture, _ = _refs(case.fixture_id, case.policy_set_id)
    return check_case(case, fixture)


def _suites(value: str) -> list[Suite]:
    names = list(SUITES) if value == "all" else [v.strip() for v in value.split(",") if v.strip()]
    unknown = [n for n in names if n not in SUITES]
    if unknown or not names:
        raise ValueError(
            f"unknown suite {', '.join(unknown) or value!r}; choose from {', '.join(SUITES)}"
        )
    return [cast(Suite, n) for n in dict.fromkeys(names)]


def _systems(value: str) -> list[System]:
    names = [v.strip() for v in value.split(",") if v.strip()]
    allowed = get_args(System)
    if not names or any(n not in allowed for n in names):
        raise ValueError(f"unknown system in {value!r}; available: {', '.join(allowed)}")
    return [cast(System, n) for n in dict.fromkeys(names)]
