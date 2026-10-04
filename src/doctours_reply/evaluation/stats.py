"""Interval estimates and paired tests for reported rates (`eval/preregistration.md`).

Runs of the same case are correlated, so the bootstrap resamples cases with all of
their runs rather than treating every run as an independent item.
"""

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

RESAMPLES = 10_000
SEED = 7

Counts = tuple[int, int]
"""Per case: (items that hit, items)."""


def wilson(successes: int, total: int, z: float = 1.959964) -> tuple[float, float]:
    """The Wilson score interval for a binomial proportion; (0, 1) when `total` is 0."""
    if total == 0:
        return 0.0, 1.0
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, `q` in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def case_bootstrap(cases: Sequence[Counts]) -> tuple[float, float]:
    """A 95% percentile interval for the pooled rate, resampling whole cases."""
    if not cases:
        return 0.0, 1.0
    rng = random.Random(SEED)
    rates = []
    for _ in range(RESAMPLES):
        sample = rng.choices(cases, k=len(cases))
        rates.append(sum(k for k, _ in sample) / sum(n for _, n in sample))
    return percentile(rates, 2.5), percentile(rates, 97.5)


def paired_difference(
    first: Mapping[str, Counts], second: Mapping[str, Counts]
) -> dict[str, Any] | None:
    """`second` minus `first` on their shared cases, with a 95% case-bootstrap interval."""
    shared = sorted(first.keys() & second.keys())
    if not shared:
        return None

    def difference(ids: Sequence[str]) -> float:
        def pooled(counts: Mapping[str, Counts]) -> float:
            return sum(counts[i][0] for i in ids) / sum(counts[i][1] for i in ids)

        return pooled(second) - pooled(first)

    rng = random.Random(SEED)
    samples = [difference(rng.choices(shared, k=len(shared))) for _ in range(RESAMPLES)]
    return {
        "difference": round(difference(shared), 4),
        "ci95": [round(percentile(samples, 2.5), 4), round(percentile(samples, 97.5), 4)],
        "cases": len(shared),
    }


def mcnemar_exact(only_first: int, only_second: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pair counts."""
    total = only_first + only_second
    if total == 0:
        return 1.0
    tail = sum(math.comb(total, i) for i in range(min(only_first, only_second) + 1))
    return min(1.0, 2 * tail / (1 << total))
