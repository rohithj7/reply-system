"""Live S1 policy-change, fact-change and escalation checks (RC-PL-2, RC-PL-3, RC-E).

Opt in with RUN_LIVE=1 and MODEL_*. Each case runs LIVE_RUNS times (default 3) and
passes on the pre-registered rule: every run for policy and fact changes and for cases
that must escalate, at least two of three for the non-escalating controls. Redacted
traces go to `<LIVE_TRACE_DIR or runs>/live-rc-<run id>/traces.jsonl`.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from doctours_reply.cli import git_sha, new_run_id
from doctours_reply.contract.io import InputItem
from doctours_reply.evaluation.cases import Case, load_suite
from doctours_reply.models.openai_compat import ModelSettings, OpenAICompatClient
from doctours_reply.runtime.pipeline import ItemResult, RunInfo, run_batch
from doctours_reply.runtime.refs import resolve_fixture, resolve_policy_set
from doctours_reply.trace.sink import TraceSink

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to run"),
]

RUNS = int(os.environ.get("LIVE_RUNS", "3"))
HAKAN_ID = "22222222-2222-4222-8222-222222222222"
SAPPHIRE_ID = "55555555-5555-4555-8555-555555555551"
SAPPHIRE_PAYMENT = f"https://www.doctours.com/payment/{SAPPHIRE_ID}"
HAKAN_CHECKOUT = "https://www.doctours.com/clinic/dr-hakan/checkout"
Check = Callable[[ItemResult], bool]


@dataclass(frozen=True)
class Live:
    client: OpenAICompatClient
    run: RunInfo
    sink: TraceSink


@pytest.fixture(scope="module")
def live() -> Live:
    settings = ModelSettings.from_env(os.environ)
    run_id = new_run_id()
    sink = TraceSink(Path(os.environ.get("LIVE_TRACE_DIR", "runs")) / f"live-rc-{run_id}")
    print(f"traces: {sink.path}")
    return Live(
        OpenAICompatClient(settings), RunInfo(run_id, git_sha(), settings.public_config()), sink
    )


def _runs(
    live: Live,
    text: str,
    fixture_id: str = "packet",
    policy_set_id: str = "shipped",
) -> list[ItemResult]:
    items = [InputItem(id=f"run{i + 1}", text=text) for i in range(RUNS)]
    return run_batch(
        items,
        fixture=resolve_fixture(fixture_id),
        policy_set=resolve_policy_set(policy_set_id),
        client=live.client,
        run=live.run,
        sink=live.sink,
        concurrency=RUNS,
        system="modular",
    )


def _passes(results: list[ItemResult], check: Check, label: str) -> int:
    passed = sum(check(r) for r in results)
    print(f"{label}: {passed}/{len(results)}")
    for result in results:
        if not check(result):
            calls = [(m.purpose, m.content) for m in result.trace.model_calls]
            tools = [(o.tool, o.status) for o in result.trace.observations]
            print(f"  failed run {result.trace.item_id}: tools {tools}; calls {calls}")
    return passed


def _saved_selection(result: ItemResult) -> dict[str, object] | None:
    saves = [
        o
        for o in result.trace.observations
        if o.tool == "updateUserClinicPreferences" and o.executed
    ]
    if len(saves) != 1:
        return None
    selection = saves[0].args.get("clinicSelection")
    return selection if isinstance(selection, dict) else None


def _chosen(result: ItemResult) -> bool:
    selection = _saved_selection(result)
    return selection is not None and selection.get("selectedClinicId") == HAKAN_ID


def _soft_interest(result: ItemResult) -> bool:
    selection = _saved_selection(result)
    return (
        selection is not None
        and selection.get("softClinicInterestIds") == [HAKAN_ID]
        and not selection.get("selectedClinicId")
    )


@pytest.mark.parametrize(
    ("policy_set_id", "check"),
    [("shipped", _chosen), ("lean-as-soft-interest", _soft_interest)],
)
def test_a_lean_is_saved_as_the_policy_says_rc_pl_2(
    live: Live, policy_set_id: str, check: Check
) -> None:
    results = _runs(live, "I'm leaning toward Dr. Hakan Clinic.", policy_set_id=policy_set_id)
    assert _passes(results, check, f"RC-PL-2 {policy_set_id}") == RUNS


def _link(result: ItemResult, link_type: str, url: str, other: str) -> bool:
    links = [
        o.args for o in result.trace.observations if o.tool == "getPaymentLink" and o.status == "ok"
    ]
    response = result.reply.response
    return (
        any(args.get("type") == link_type for args in links)
        and response.strip().splitlines()[-1] == url
        and other not in response
    )


@pytest.mark.parametrize(
    ("policy_set_id", "link_type", "url", "other"),
    [
        ("shipped", "payment", SAPPHIRE_PAYMENT, HAKAN_CHECKOUT),
        ("checkout-only-links", "checkout", HAKAN_CHECKOUT, SAPPHIRE_PAYMENT),
    ],
)
def test_the_deposit_link_follows_the_policy_rc_pl_3(
    live: Live, policy_set_id: str, link_type: str, url: str, other: str
) -> None:
    text = (
        "I've decided on Sapphire at Dr. Hakan Clinic. Can you send me the link to pay the deposit?"
    )
    results = _runs(live, text, policy_set_id=policy_set_id)
    passed = _passes(results, lambda r: _link(r, link_type, url, other), f"RC-PL-3 {policy_set_id}")
    assert passed == RUNS


@pytest.mark.parametrize(
    ("fixture_id", "price", "stale"),
    [("packet", "$3,200", "$3,400"), ("sapphire-price-change", "$3,400", "$3,200")],
)
def test_a_price_change_in_the_data_reaches_the_reply(
    live: Live, fixture_id: str, price: str, stale: str
) -> None:
    results = _runs(live, "How much is the Sapphire package at Dr. Hakan Clinic?", fixture_id)
    passed = _passes(
        results,
        lambda r: price in r.reply.response and stale not in r.reply.response,
        f"fact change {fixture_id}",
    )
    assert passed == RUNS


@pytest.mark.parametrize(
    ("policy_set_id", "fee", "stale"),
    [("shipped", "$25", "$40"), ("deposit-fee-change", "$40", "$25")],
)
def test_a_fee_change_in_the_policy_reaches_the_reply(
    live: Live, policy_set_id: str, fee: str, stale: str
) -> None:
    text = "If I cancel before my lock-in date, is there a fee on the deposit refund?"
    results = _runs(live, text, policy_set_id=policy_set_id)
    passed = _passes(
        results,
        lambda r: fee in r.reply.response and stale not in r.reply.response,
        f"policy fee {policy_set_id}",
    )
    assert passed == RUNS


@pytest.mark.parametrize("case", load_suite("regression"), ids=lambda c: c.case_id)
def test_escalation_regression_cases_rc_e(live: Live, case: Case) -> None:
    results = _runs(live, case.text, case.fixture_id, case.policy_set_id)
    passed = _passes(results, lambda r: r.reply.escalate == case.labels.escalate, f"{case.case_id}")
    assert passed >= (RUNS if case.labels.escalate else -(-2 * RUNS // 3))
