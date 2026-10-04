"""Aggregate case scores into the pre-registered metrics, with n and Wilson intervals.

With repeated runs, rates also carry a case-bootstrap interval and the number of cases
whose majority of runs hit, since runs of one case are not independent.
"""

import json
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final, get_args

from doctours_reply.evaluation.scorer import HUMAN_CLASS, CaseScore
from doctours_reply.evaluation.stats import (
    Counts,
    case_bootstrap,
    mcnemar_exact,
    paired_difference,
    percentile,
    wilson,
)
from doctours_reply.runtime.decision import EscalationCode

Predicate = Callable[[CaseScore], bool]
Count = Callable[[CaseScore], int]
ESCALATION_CODES: Final = frozenset(get_args(EscalationCode))
PAIRED: Final[dict[str, tuple[Predicate, Predicate | None]]] = {
    "escalation_correct": (lambda s: s.escalate_actual == s.escalate_expected, None),
    "missed_escalation": (lambda s: not s.escalate_actual, lambda s: s.escalate_expected),
    "unnecessary_escalation": (lambda s: s.escalate_actual, lambda s: not s.escalate_expected),
    "goal_complete_proxy": (
        lambda s: s.required_hit == s.required_total,
        lambda s: s.required_total > 0,
    ),
    "tool_selection": (lambda s: bool(s.tool_selection), lambda s: s.tool_selection is not None),
}


def rate(
    scores: Sequence[CaseScore], hit: Predicate, among: Predicate | None = None
) -> dict[str, Any]:
    pool = [s for s in scores if among is None or among(s)]
    k = sum(hit(s) for s in pool)
    low, high = wilson(k, len(pool))
    runs = sorted({s.run for s in pool})
    per_run = [
        round(sum(hit(s) for s in pool if s.run == r) / max(1, sum(s.run == r for s in pool)), 4)
        for r in runs
    ]
    result = {
        "k": k,
        "n": len(pool),
        "rate": round(k / len(pool), 4) if pool else None,
        "ci95": [round(low, 4), round(high, 4)],
        "per_run": per_run,
    }
    return result | _by_case(_case_counts(pool, _as_count(hit)), len(runs))


def pooled(scores: Sequence[CaseScore], hit: Count, total: Count) -> dict[str, Any]:
    """A pooled fraction of countable items, such as required facts, per item."""
    pool = [s for s in scores if total(s) > 0]
    k, n = sum(hit(s) for s in pool), sum(total(s) for s in pool)
    low, high = wilson(k, n)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 4) if n else None,
        "ci95": [round(low, 4), round(high, 4)],
        "per_run": [],
    } | _by_case(_case_counts(pool, hit, total), len({s.run for s in pool}))


def compare(first: Sequence[CaseScore], second: Sequence[CaseScore]) -> dict[str, Any]:
    """`second` minus `first` on shared cases: case-bootstrap differences and exact McNemar
    on each case's majority of runs."""
    result: dict[str, Any] = {}
    for name, (hit, among) in PAIRED.items():
        a, b = (
            _case_counts([s for s in group if among is None or among(s)], _as_count(hit))
            for group in (first, second)
        )
        difference = paired_difference(a, b)
        if difference is None:
            result[name] = None
            continue
        shared = a.keys() & b.keys()
        only_first = sum(_majority(a[i]) and not _majority(b[i]) for i in shared)
        only_second = sum(_majority(b[i]) and not _majority(a[i]) for i in shared)
        result[name] = difference | {
            "discordant_cases": [only_first, only_second],
            "mcnemar_p": round(mcnemar_exact(only_first, only_second), 4),
        }
    coverage = [_case_counts(g, _hit_required, _total_required) for g in (first, second)]
    result["goal_coverage_proxy"] = paired_difference(*coverage)
    result["prompt_tokens_per_item"] = [
        _mean([s.prompt_tokens for s in group]) for group in (first, second)
    ]
    return result


def system_metrics(scores: Sequence[CaseScore]) -> dict[str, Any]:
    answered = [s for s in scores if not s.escalate_actual]
    controls = sorted({s.control for s in scores if s.control})
    metrics: dict[str, Any] = {
        "cases_per_run": len({s.case_id for s in scores}),
        "runs": len({s.run for s in scores}),
        "output_valid_after_finalize": rate(scores, lambda s: s.valid_after_finalize),
        "output_valid_before_repair": rate(scores, lambda s: s.valid_before_repair),
        "escalation_correct": rate(scores, lambda s: s.escalate_actual == s.escalate_expected),
        "missed_escalation": {
            "human_request": rate(
                scores,
                lambda s: not s.escalate_actual,
                lambda s: s.escalation_class == HUMAN_CLASS,
            ),
            "unsupported_action": rate(
                scores,
                lambda s: not s.escalate_actual,
                lambda s: s.escalate_expected and s.escalation_class != HUMAN_CLASS,
            ),
        },
        "missed_escalation_by_class": {
            name: rate(scores, lambda s: not s.escalate_actual, _class_is(name))
            for name in sorted({s.escalation_class for s in scores if s.escalation_class})
        },
        "escalation_code_correct": rate(
            scores,
            lambda s: s.escalation_code == s.escalation_class,
            lambda s: s.escalate_expected and s.escalation_code in ESCALATION_CODES,
        ),
        "unnecessary_escalation": {
            "all_non_escalating": rate(
                scores, lambda s: s.escalate_actual, lambda s: not s.escalate_expected
            ),
            **{control: _control_rate(scores, control) for control in controls},
        },
        "escalations_after_write": rate(
            scores, lambda s: s.escalated_after_write, lambda s: s.escalate_actual
        ),
        "escalations_by_stage": dict(Counter(s.stage for s in scores if s.escalate_actual)),
        "tool_selection": rate(
            scores, lambda s: bool(s.tool_selection), lambda s: s.tool_selection is not None
        ),
        "required_facts": _fraction(
            sum(s.required_facts_hit for s in scores), sum(s.required_facts_total for s in scores)
        ),
        "forbidden_fact_cases": rate(scores, lambda s: s.forbidden_hits > 0),
        "required_urls": _fraction(
            sum(s.urls_required_hit for s in scores), sum(s.urls_required_total for s in scores)
        ),
        "forbidden_url_cases": rate(scores, lambda s: s.urls_forbidden_hits > 0),
        "goal_coverage_proxy": pooled(scores, _hit_required, _total_required),
        "goal_complete_proxy": rate(scores, *PAIRED["goal_complete_proxy"]),
        "tool_not_loaded_items": rate(scores, lambda s: s.tool_not_loaded > 0),
        "memory_labels_ok": rate(scores, lambda s: s.memory_ok),
        "memory_tool_called_when_answered": rate(answered, lambda s: s.memory_tool_calls > 0),
        "grounded_first_try": rate(
            scores, lambda s: bool(s.grounded_first_try), lambda s: s.grounded_first_try is not None
        ),
        "validation_stage_escalation": rate(scores, lambda s: s.stage == "validation"),
        "controller_failure": rate(scores, lambda s: s.stage == "controller_failure"),
        "cost": {
            "model_calls_per_item": _mean([s.model_calls for s in scores]),
            "retries_total": sum(s.retries for s in scores),
            "json_repairs_total": sum(s.json_repairs for s in scores),
            "validation_repairs_total": sum(s.validation_repairs for s in scores),
            "skill_loads_per_item": _mean([s.skill_loads for s in scores]),
            "prompt_tokens_per_item": _mean([s.prompt_tokens for s in scores]),
            "cached_prompt_tokens_per_item": _mean([s.cached_prompt_tokens for s in scores]),
            "completion_tokens_per_item": _mean([s.completion_tokens for s in scores]),
            "latency_ms_p50": percentile([s.latency_ms for s in scores], 50),
            "latency_ms_p95": percentile([s.latency_ms for s in scores], 95),
            "end_to_end_ms_p50": percentile([s.end_to_end_ms for s in scores], 50),
            "end_to_end_ms_p95": percentile([s.end_to_end_ms for s in scores], 95),
        },
    }
    official = [s for s in scores if s.official is not None]
    if official:
        metrics["official_checks"] = {
            s.case_id + f"#run{s.run}": s.official for s in sorted(official, key=_key)
        }
    judged = [s for s in scores if s.judge is not None]
    if judged:
        metrics["judge"] = {
            "n": len(judged),
            "goal_coverage_mean": _mean([s.judge["goal_coverage"] for s in judged if s.judge]),
            "policy_correctness_mean": _mean(
                [s.judge["policy_correctness"] for s in judged if s.judge]
            ),
            "unsupported_claims": rate(
                judged, lambda s: bool(s.judge and s.judge["unsupported_claims"])
            ),
        }
    return metrics


def write_report(
    directory: Path, scores: Sequence[CaseScore], config: dict[str, Any]
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    systems = sorted({s.system for s in scores})
    by_system = {name: [s for s in scores if s.system == name] for name in systems}
    report: dict[str, Any] = {
        "config": config,
        "systems": {name: system_metrics(group) for name, group in by_system.items()},
    }
    if {"baseline", "modular"} <= by_system.keys():
        report["modular_minus_baseline"] = compare(by_system["baseline"], by_system["modular"])
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    with (directory / "cases.jsonl").open("w", encoding="utf-8") as handle:
        for score in sorted(scores, key=_key):
            handle.write(json.dumps(score.to_json(), ensure_ascii=False) + "\n")
    (directory / "summary.md").write_text(_markdown(report), "utf-8")
    return report


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Evaluation summary",
        "",
        f"Config sha256: `{report['config']['config_sha256']}`",
        "",
    ]
    for name, metrics in report["systems"].items():
        lines += [
            f"## {name}",
            "",
            f"{metrics['cases_per_run']} cases x {metrics['runs']} runs.",
            "",
        ]
        lines += [
            "| metric | k/n | rate | 95% CI | cases | 95% CI by case | majority | per run |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for label, value in _flatten(metrics):
            if isinstance(value, dict) and "ci95" in value:
                low, high = value["ci95"]
                shown = "-" if value["rate"] is None else f"{value['rate']:.3f}"
                by_case = value.get("ci95_cases")
                shown_case = "-" if by_case is None else f"[{by_case[0]:.3f}, {by_case[1]:.3f}]"
                lines.append(
                    f"| {label} | {value['k']}/{value['n']} | {shown} | "
                    f"[{low:.3f}, {high:.3f}] | {value.get('cases', '-')} | {shown_case} | "
                    f"{value.get('majority', '-')} | {value['per_run']} |"
                )
        lines += ["", f"Escalations by stage: {metrics['escalations_by_stage']}", ""]
        lines += [f"Cost: {json.dumps(metrics['cost'])}", ""]
    if comparison := report.get("modular_minus_baseline"):
        lines += ["## modular minus baseline", "", "```json", json.dumps(comparison, indent=2)]
        lines += ["```", ""]
    return "\n".join(lines)


def _flatten(metrics: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    items = []
    for key, value in metrics.items():
        label = f"{prefix}{key}"
        if isinstance(value, dict) and "ci95" not in value:
            items += _flatten(value, label + ".")
        else:
            items.append((label, value))
    return items


def _control_rate(scores: Sequence[CaseScore], control: str) -> dict[str, Any]:
    return rate(scores, lambda s: s.escalate_actual, lambda s: s.control == control)


def _class_is(name: str) -> Predicate:
    return lambda s: s.escalation_class == name


def _as_count(hit: Predicate) -> Count:
    return lambda s: int(hit(s))


def _hit_required(score: CaseScore) -> int:
    return score.required_hit


def _total_required(score: CaseScore) -> int:
    return score.required_total


def _case_counts(
    pool: Sequence[CaseScore], hit: Count, total: Count = lambda s: 1
) -> dict[str, Counts]:
    counts: dict[str, Counts] = {}
    for score in pool:
        if (n := total(score)) > 0:
            k0, n0 = counts.get(f"{score.suite}/{score.case_id}", (0, 0))
            counts[f"{score.suite}/{score.case_id}"] = (k0 + hit(score), n0 + n)
    return counts


def _by_case(cases: dict[str, Counts], runs: int) -> dict[str, Any]:
    result: dict[str, Any] = {"cases": len(cases)}
    if runs > 1:
        low, high = case_bootstrap(list(cases.values()))
        result["ci95_cases"] = [round(low, 4), round(high, 4)]
        result["majority"] = sum(_majority(c) for c in cases.values())
    return result


def _majority(counts: Counts) -> bool:
    k, n = counts
    return 2 * k > n


def _fraction(k: int, n: int) -> dict[str, Any]:
    low, high = wilson(k, n)
    rate_value = round(k / n, 4) if n else None
    return {
        "k": k,
        "n": n,
        "rate": rate_value,
        "ci95": [round(low, 4), round(high, 4)],
        "per_run": [],
    }


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _key(score: CaseScore) -> tuple[str, str, int, str]:
    return score.system, score.suite, score.run, score.case_id
