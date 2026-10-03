"""Interval estimates for reported rates (plan 8.4)."""

import math
from collections.abc import Sequence


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
