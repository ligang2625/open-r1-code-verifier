"""Tests for deterministic problem-level bootstrap intervals."""

from __future__ import annotations

import math
import random

import pytest

from code_verifier.evaluation.bootstrap import (
    BootstrapError,
    bootstrap_mean_interval,
    paired_bootstrap_difference,
)


def test_bootstrap_mean_is_deterministic_for_seed() -> None:
    first = bootstrap_mean_interval([0.0, 0.5, 1.0], seed=42, resamples=200)
    second = bootstrap_mean_interval([0.0, 0.5, 1.0], seed=42, resamples=200)

    assert first == second
    assert first.estimate == 0.5


@pytest.mark.parametrize(
    ("values", "kwargs"),
    [
        ([], {}),
        ([math.nan], {}),
        ([math.inf], {}),
        ([True], {}),
        ([1.0], {"seed": True}),
        ([1.0], {"resamples": 0}),
        ([1.0], {"resamples": True}),
        ([1.0], {"confidence_level": 0.0}),
        ([1.0], {"confidence_level": math.nan}),
        ([1.0], {"confidence_level": True}),
    ],
)
def test_bootstrap_mean_rejects_empty_nonfinite_bool_and_bad_parameters(
    values: list[float], kwargs: dict[str, object]
) -> None:
    parameters: dict[str, object] = {"seed": 1}
    parameters.update(kwargs)
    with pytest.raises(BootstrapError):
        bootstrap_mean_interval(values, **parameters)  # type: ignore[arg-type]


def test_bootstrap_single_problem_collapses_interval() -> None:
    interval = bootstrap_mean_interval([0.25], seed=7, resamples=50)

    assert interval.estimate == interval.lower == interval.upper == 0.25


def test_paired_bootstrap_uses_shared_problem_indices() -> None:
    interval = paired_bootstrap_difference([0.0, 1.0, 0.0], [0.0, 1.0, 0.0], seed=9, resamples=100)

    assert interval.estimate == interval.lower == interval.upper == 0.0


def test_paired_bootstrap_rejects_mismatched_lengths() -> None:
    with pytest.raises(BootstrapError, match="equal lengths"):
        paired_bootstrap_difference([1.0], [1.0, 0.0], seed=1)


def test_bootstrap_linear_percentile_definition_is_stable() -> None:
    values = [0.0, 10.0]
    seed = 3
    resamples = 4
    confidence_level = 0.5
    rng = random.Random(seed)
    replicates = sorted(sum(values[rng.randrange(2)] for _ in range(2)) / 2 for _ in range(resamples))
    expected_lower = replicates[0] + (replicates[1] - replicates[0]) * 0.75
    expected_upper = replicates[2] + (replicates[3] - replicates[2]) * 0.25

    interval = bootstrap_mean_interval(
        values,
        seed=seed,
        resamples=resamples,
        confidence_level=confidence_level,
    )

    assert interval.lower == expected_lower
    assert interval.upper == expected_upper


def test_bootstrap_does_not_mutate_global_random_state() -> None:
    random.seed(123)
    expected = random.random()
    random.seed(123)
    bootstrap_mean_interval([0.0, 1.0], seed=5, resamples=10)

    assert random.random() == expected
