"""Deterministic problem-level bootstrap confidence intervals."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass


class BootstrapError(ValueError):
    """Raised when bootstrap inputs or parameters violate the statistical contract."""


@dataclass(frozen=True)
class BootstrapInterval:
    """One deterministic percentile bootstrap interval."""

    estimate: float
    lower: float
    upper: float
    confidence_level: float
    resamples: int
    seed: int


def _finite_values(values: Sequence[float], *, field_name: str) -> tuple[float, ...]:
    if not values:
        raise BootstrapError(f"{field_name} must be non-empty")
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise BootstrapError(f"{field_name} must contain only finite numbers")
        number = float(value)
        if not math.isfinite(number):
            raise BootstrapError(f"{field_name} must contain only finite numbers")
        result.append(number)
    return tuple(result)


def _parameters(*, seed: int, resamples: int, confidence_level: float) -> tuple[int, int, float]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise BootstrapError("seed must be an integer")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples <= 0:
        raise BootstrapError("resamples must be a positive integer")
    if isinstance(confidence_level, bool) or not isinstance(confidence_level, int | float):
        raise BootstrapError("confidence_level must be a finite number between 0 and 1")
    confidence = float(confidence_level)
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise BootstrapError("confidence_level must be a finite number between 0 and 1")
    return seed, resamples, confidence


def _linear_quantile(sorted_values: Sequence[float], quantile: float) -> float:
    """Return q using the fixed position q*(n-1) and linear interpolation rule."""
    if not sorted_values:
        raise BootstrapError("quantile values must be non-empty")
    position = quantile * (len(sorted_values) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return lower + (upper - lower) * (position - lower_index)


def _interval(
    *,
    estimate: float,
    replicates: list[float],
    seed: int,
    resamples: int,
    confidence_level: float,
) -> BootstrapInterval:
    replicates.sort()
    tail = (1.0 - confidence_level) / 2.0
    lower = _linear_quantile(replicates, tail)
    upper = _linear_quantile(replicates, 1.0 - tail)
    if not all(math.isfinite(value) for value in (estimate, lower, upper)) or lower > upper:
        raise BootstrapError("bootstrap produced an invalid confidence interval")
    return BootstrapInterval(
        estimate=estimate,
        lower=lower,
        upper=upper,
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
    )


def bootstrap_mean_interval(
    values: Sequence[float],
    *,
    seed: int,
    resamples: int = 10_000,
    confidence_level: float = 0.95,
) -> BootstrapInterval:
    """Bootstrap a mean by resampling problem indices with replacement."""
    samples = _finite_values(values, field_name="values")
    seed, resamples, confidence_level = _parameters(
        seed=seed,
        resamples=resamples,
        confidence_level=confidence_level,
    )
    rng = random.Random(seed)
    count = len(samples)
    replicates = [sum(samples[rng.randrange(count)] for _ in range(count)) / count for _ in range(resamples)]
    return _interval(
        estimate=sum(samples) / count,
        replicates=replicates,
        seed=seed,
        resamples=resamples,
        confidence_level=confidence_level,
    )


def paired_bootstrap_difference(
    left: Sequence[float],
    right: Sequence[float],
    *,
    seed: int,
    resamples: int = 10_000,
    confidence_level: float = 0.95,
) -> BootstrapInterval:
    """Bootstrap mean(left-right) using the same sampled problem indices for each side."""
    left_values = _finite_values(left, field_name="left")
    right_values = _finite_values(right, field_name="right")
    if len(left_values) != len(right_values):
        raise BootstrapError("paired bootstrap inputs must have equal lengths")
    seed, resamples, confidence_level = _parameters(
        seed=seed,
        resamples=resamples,
        confidence_level=confidence_level,
    )
    differences = tuple(
        left_value - right_value for left_value, right_value in zip(left_values, right_values, strict=True)
    )
    rng = random.Random(seed)
    count = len(differences)
    replicates = [sum(differences[rng.randrange(count)] for _ in range(count)) / count for _ in range(resamples)]
    return _interval(
        estimate=sum(differences) / count,
        replicates=replicates,
        seed=seed,
        resamples=resamples,
        confidence_level=confidence_level,
    )
