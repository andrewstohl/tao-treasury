"""Shared utilities for analysis services."""

import math
from typing import List


def compute_volatility(daily_returns: List[float]) -> float:
    """Compute sample standard deviation of daily returns.

    Uses Bessel's correction (n-1 denominator) for unbiased estimate.
    Returns 0.0 if fewer than 2 data points.
    """
    n = len(daily_returns)
    if n < 2:
        return 0.0
    mean = sum(daily_returns) / n
    variance = sum((r - mean) ** 2 for r in daily_returns) / (n - 1)
    return math.sqrt(variance)
