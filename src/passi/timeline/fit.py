"""Fit to music: rescale photo durations so the show lasts as long as the music (§1.7)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from passi.timeline.types import DEFAULT_DURATION_LIMITS, DurationLimits, FitResult

_BISECTION_STEPS = 200


def fit_to_music(
    durations: Sequence[float], target_s: float, limits: DurationLimits = DEFAULT_DURATION_LIMITS
) -> FitResult:
    """Scales `durations` by a common factor so they sum to `target_s`, keeping proportions.

    Every duration stays within [limits.minimum, limits.maximum]; photos that hit a limit are
    held there and the others absorb the difference. If the target is out of reach, every
    photo is clamped to the nearest limit and `warning` is set.
    """
    count = len(durations)
    if count == 0:
        return FitResult((), False, 0.0)
    low, high = limits.minimum, limits.maximum
    warning = target_s / count < limits.warn_below or not count * low <= target_s <= count * high
    if target_s <= count * low:
        fitted = [low] * count
    elif target_s >= count * high:
        fitted = [high] * count
    else:
        weights = [max(0.0, d) for d in durations]
        if not any(weights):
            weights = [1.0] * count
        fitted = _scale_with_limits(weights, target_s, low, high)
    return FitResult(tuple(fitted), warning, math.fsum(fitted))


def _scale_with_limits(weights: list[float], target: float, low: float, high: float) -> list[float]:
    """Finds k with sum(clamp(k * w)) == target (the sum is monotonic in k), then solves exactly."""

    def total(k: float) -> float:
        return math.fsum(min(high, max(low, k * w)) for w in weights)

    k_low, k_high = 0.0, high / min(w for w in weights if w > 0)
    for _ in range(_BISECTION_STEPS):
        k_mid = (k_low + k_high) / 2
        if total(k_mid) < target:
            k_low = k_mid
        else:
            k_high = k_mid
        if k_high - k_low <= 1e-15 * k_high:
            break
    k = (k_low + k_high) / 2
    # Exact factor for the photos that are not held at a limit.
    free = [w for w in weights if low < k * w < high]
    held = math.fsum(min(high, max(low, k * w)) for w in weights if not low < k * w < high)
    if free:
        k = (target - held) / math.fsum(free)
    return [min(high, max(low, k * w)) for w in weights]
