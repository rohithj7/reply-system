"""Run items in isolation and return their replies in input order (plan guarantee 8).

Each item gets a fresh context, executor and outcome slot; only the immutable fixture
and policy set are shared. A model failure stops the batch: its partial trace, including
any writes already executed, is still written, and the caller writes no output.
"""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Literal

from doctours_reply.baseline.monolithic import run_baseline
from doctours_reply.contract.io import InputItem
from doctours_reply.contract.reply import Reply
from doctours_reply.models.client import ModelClient, ModelError
from doctours_reply.runtime.context import TurnContext, build_context
from doctours_reply.runtime.executor import Executor
from doctours_reply.runtime.finalize import finalize
from doctours_reply.runtime.outcome import Draft, OutcomeSlot, TerminalOutcome
from doctours_reply.runtime.refs import Fixture, PolicySet
from doctours_reply.trace.schema import TraceRecord
from doctours_reply.trace.sink import TraceSink

System = Literal["baseline"]
SystemRunner = Callable[[TurnContext, ModelClient, Executor, TraceRecord], TerminalOutcome]
SYSTEMS: dict[System, SystemRunner] = {"baseline": run_baseline}

BLANK_MESSAGE_DRAFT = Draft(
    response="It looks like your message came through empty. What can I help you with?",
    intent="clarify empty message",
    shouldFollowUp=False,
    followUpTiming=None,
    attachmentUrls=[],
    highEngagement=False,
    workingMemoryUpdates=None,
)
"""Ledger A-22: blank text gets a short clarifying reply without a model call."""


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    git_sha: str | None
    model: dict[str, Any] | None


@dataclass(frozen=True)
class ItemResult:
    reply: Reply
    trace: TraceRecord


class ItemFailedError(Exception):
    def __init__(self, index: int, item_id: str, cause: ModelError, trace: TraceRecord) -> None:
        super().__init__(f"item {index} ({item_id!r}) failed: {cause}")
        self.index = index
        self.trace = trace


def run_item(
    index: int,
    item: InputItem,
    *,
    fixture: Fixture,
    policy_set: PolicySet,
    client: ModelClient,
    run: RunInfo,
    system: System = "baseline",
) -> ItemResult:
    ctx = build_context(index, item.id, item.text, fixture, policy_set)
    trace = TraceRecord(
        run_id=run.run_id,
        item_index=index,
        item_id=item.id,
        system=system,
        fixture_id=fixture.fixture_id,
        fixture_sha256=fixture.resolved_hash,
        policy_set_id=policy_set.policy_set_id,
        policy_set_sha256=policy_set.resolved_hash,
        git_sha=run.git_sha,
        model=run.model,
        message=ctx.message.text,
        redactions=ctx.message.text.count("[CARD_"),
    )
    executor = Executor(fixture.tool_data, fixture.constants)
    slot = OutcomeSlot()
    try:
        if ctx.message.text.strip():
            slot.set(SYSTEMS[system](ctx, client, executor, trace))
        else:
            slot.set(TerminalOutcome(kind="clarified", stage=None, draft=BLANK_MESSAGE_DRAFT))
    except ModelError as exc:
        trace.observations = list(executor.observations)
        trace.error = str(exc)
        raise ItemFailedError(index, item.id, exc, trace) from exc
    finally:
        executor.close()
    outcome = slot.outcome
    assert outcome is not None
    reply = finalize(outcome, ctx.working_memory)
    trace.observations = list(executor.observations)
    trace.outcome = outcome
    trace.reply = reply
    return ItemResult(reply, trace)


def run_batch(
    items: Sequence[InputItem],
    *,
    fixture: Fixture,
    policy_set: PolicySet,
    client: ModelClient,
    run: RunInfo,
    sink: TraceSink | None = None,
    concurrency: int = 1,
    system: System = "baseline",
) -> list[ItemResult]:
    results: list[ItemResult | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(
                run_item,
                index,
                item,
                fixture=fixture,
                policy_set=policy_set,
                client=client,
                run=run,
                system=system,
            ): index
            for index, item in enumerate(items)
        }
        try:
            for future in as_completed(futures):
                result = future.result()
                results[futures[future]] = result
                if sink is not None:
                    sink.write(result.trace)
        except ItemFailedError as exc:
            for pending in futures:
                pending.cancel()
            if sink is not None:
                sink.write(exc.trace)
            raise
    return [result for result in results if result is not None]
