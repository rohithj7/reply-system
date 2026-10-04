"""Aggregate case scores into the metrics of plan 8.3, with n and Wilson intervals."""

import json
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from doctours_reply.evaluation.scorer import HUMAN_CLASS, CaseScore
from doctours_reply.evaluation.stats import percentile, wilson

Predicate = Callable[[CaseScore], bool]


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
    return {
        "k": k,
        "n": len(pool),
        "rate": round(k / len(pool), 4) if pool else None,
        "ci95": [round(low, 4), round(high, 4)],
        "per_run": per_run,
    }


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
            "prompt_tokens_per_item": _mean([s.prompt_tokens for s in scores]),
            "cached_prompt_tokens_per_item": _mean([s.cached_prompt_tokens for s in scores]),
            "completion_tokens_per_item": _mean([s.completion_tokens for s in scores]),
            "latency_ms_p50": percentile([s.latency_ms for s in scores], 50),
            "latency_ms_p95": percentile([s.latency_ms for s in scores], 95),
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
    report = {
        "config": config,
        "systems": {
            name: system_metrics([s for s in scores if s.system == name]) for name in systems
        },
    }
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
        lines += ["| metric | k/n | rate | 95% CI | per run |", "|---|---|---|---|---|"]
        for label, value in _flatten(metrics):
            if isinstance(value, dict) and "ci95" in value:
                low, high = value["ci95"]
                shown = "-" if value["rate"] is None else f"{value['rate']:.3f}"
                lines.append(
                    f"| {label} | {value['k']}/{value['n']} | {shown} | "
                    f"[{low:.3f}, {high:.3f}] | {value['per_run']} |"
                )
        lines += ["", f"Escalations by stage: {metrics['escalations_by_stage']}", ""]
        lines += [f"Cost: {json.dumps(metrics['cost'])}", ""]
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
