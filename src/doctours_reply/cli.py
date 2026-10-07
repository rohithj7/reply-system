"""`doctours-reply run` reads `[{id, text}]` and writes one `Reply` per item, in order.

Exit codes: 0 success; 2 invalid input or reference; 3 missing or invalid model
configuration; 4 model failure. On any failure no output is written. Traces go to
`--trace-dir` (default `runs/<run id>/`), never to the output.

`doctours-reply try` runs messages from its arguments or a prompt through the same
pipeline, one isolated item each, and prints each reply with its timings and trace.

`doctours-reply eval ...` is the evaluation runner; only that subcommand loads it.
"""

import argparse
import os
import secrets
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

from doctours_reply.contract.io import InputContractError, InputItem, dump_replies, parse_input
from doctours_reply.models.client import ModelConfigError
from doctours_reply.models.openai_compat import ModelSettings, OpenAICompatClient
from doctours_reply.runtime.pipeline import ItemFailedError, ItemResult, RunInfo, run_batch
from doctours_reply.runtime.refs import SHIPPED, RefError, resolve_fixture, resolve_policy_set
from doctours_reply.trace.sink import TraceSink

MAX_CONCURRENCY = 16


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["eval"]:
        from doctours_reply.evaluation.cli import main as evaluation_main

        return evaluation_main(args[1:])
    parser = argparse.ArgumentParser(
        prog="doctours-reply",
        description=__doc__.splitlines()[0],
        epilog="Evaluation runner: doctours-reply eval -h",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="reply to a JSON array of messages")
    run.add_argument("--input", required=True, help="input JSON path, or - for stdin")
    run.add_argument("--output", required=True, help="output JSON path, or - for stdout")
    run.add_argument("--system", choices=["baseline", "modular"], default="baseline")
    run.add_argument("--trace-dir", type=Path, help="default: runs/<run id>/")
    run.add_argument("--concurrency", type=int, default=1, help=f"1-{MAX_CONCURRENCY}")
    run.add_argument("--fixture-id", default="packet", help=argparse.SUPPRESS)
    run.add_argument("--policy-set", default=SHIPPED, help=argparse.SUPPRESS)
    trial = commands.add_parser("try", help="reply to messages one at a time, with timings")
    trial.add_argument("message", nargs="*", help="messages to send; default: read at a prompt")
    trial.add_argument("--system", choices=["baseline", "modular"], default="baseline")
    trial.add_argument("--trace-dir", type=Path, help="default: runs/<run id>/")
    trial.add_argument("--fixture-id", default="packet", help=argparse.SUPPRESS)
    trial.add_argument("--policy-set", default=SHIPPED, help=argparse.SUPPRESS)
    parsed = parser.parse_args(args)
    if parsed.command == "try":
        return _try(parsed)
    if not 1 <= parsed.concurrency <= MAX_CONCURRENCY:
        parser.error(f"--concurrency must be between 1 and {MAX_CONCURRENCY}")
    return _run(parsed)


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def write_atomic(path: Path, text: str) -> None:
    """Write via a temporary file in the same directory, then rename over `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(handle.name, path)


def _run(args: argparse.Namespace) -> int:
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_bytes()
        items = parse_input(raw)
        fixture = resolve_fixture(args.fixture_id)
        policy_set = resolve_policy_set(args.policy_set)
    except (OSError, InputContractError, RefError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    results = []
    if items:
        try:
            settings = ModelSettings.from_env(os.environ)
        except ModelConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        run_id = new_run_id()
        sink = TraceSink(args.trace_dir or Path("runs") / run_id)
        try:
            results = run_batch(
                items,
                fixture=fixture,
                policy_set=policy_set,
                client=OpenAICompatClient(settings),
                run=RunInfo(run_id, git_sha(), settings.public_config()),
                sink=sink,
                concurrency=args.concurrency,
                system=args.system,
            )
        except ItemFailedError as exc:
            print(f"error: {exc}; no output written; trace: {sink.path}", file=sys.stderr)
            return 4
        print(f"traces: {sink.path}", file=sys.stderr)
    text = dump_replies([result.reply for result in results])
    if args.output == "-":
        sys.stdout.write(text)
    else:
        write_atomic(Path(args.output), text)
    return 0


def _try(args: argparse.Namespace) -> int:
    try:
        fixture = resolve_fixture(args.fixture_id)
        policy_set = resolve_policy_set(args.policy_set)
    except RefError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        settings = ModelSettings.from_env(os.environ)
    except ModelConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    run_id = new_run_id()
    sink = TraceSink(args.trace_dir or Path("runs") / run_id)
    client = OpenAICompatClient(settings)
    run = RunInfo(run_id, git_sha(), settings.public_config())
    status = 0
    for number, text in enumerate(args.message or _prompted(), 1):
        item = InputItem(id=f"try-{number}", text=text)
        try:
            [result] = run_batch(
                [item],
                fixture=fixture,
                policy_set=policy_set,
                client=client,
                run=run,
                sink=sink,
                system=args.system,
            )
        except ItemFailedError as exc:
            print(f"error: {exc}; trace: {sink.path}, item {item.id}", file=sys.stderr)
            status = 4
            continue
        print(_report(result, f"{sink.path}, item {item.id}"), flush=True)
    return status


def _prompted() -> Iterator[str]:
    print("Each message starts from the fixture's state. Ctrl-D quits.", file=sys.stderr)
    while True:
        try:
            yield input("patient> ")
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return


def _report(result: ItemResult, trace: str) -> str:
    reply, record = result.reply, result.trace
    lines = [f"reply: {reply.response}"]
    if reply.escalate:
        lines.append(f"escalated: {reply.escalationReason}")
    lines.append(f"elapsed: {record.latency_ms / 1000:.2f} s")
    for call in record.model_calls:
        retries = f", {call.attempts} attempts" if call.attempts > 1 else ""
        lines.append(
            f"  {call.purpose:<17} {call.model_id:<18} {call.latency_ms / 1000:6.2f} s"
            f"  {call.completion_tokens} tokens, {call.finish_reason}{retries}"
        )
    for observation in record.observations:
        lines.append(
            f"  tool {observation.tool:<31} {observation.latency_ms / 1000:6.2f} s"
            f"  {observation.status}"
        )
    lines.append(f"trace: {trace}")
    return "\n".join(lines)
