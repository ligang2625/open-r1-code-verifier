from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest

from code_verifier.runtime_telemetry import (
    RuntimeTelemetryError,
    RuntimeUtilizationSampler,
    validate_formal_runtime_utilization,
    validate_host_runtime_telemetry,
)


def _samples(values: list[tuple[float, float]]) -> Iterator[tuple[float, float]]:
    yield from values


def test_runtime_sampler_reports_available_aggregates_without_synthetic_values() -> None:
    values = _samples([(10.0, 1000.0), (50.0, 1200.0), (90.0, 1400.0)])
    sampler = RuntimeUtilizationSampler(sample_fn=lambda: next(values))

    sampler.sample_once()
    sampler.sample_once()
    sampler.sample_once()
    snapshot = sampler.snapshot()

    assert snapshot["status"] == "available"
    assert snapshot["sample_count"] == 3
    assert snapshot["sample_error_count"] == 0
    assert snapshot["gpu_utilization_mean_percent"] == 50.0
    assert snapshot["gpu_utilization_p95_percent"] == 90.0
    assert snapshot["gpu_memory_used_mean_mib"] == 1200.0
    assert snapshot["gpu_memory_used_p95_mib"] == 1400.0
    assert snapshot["gpu_memory_used_max_mib"] == 1400.0
    validate_formal_runtime_utilization(snapshot)


def test_runtime_sampler_records_unavailable_instead_of_zero_on_sampling_failure() -> None:
    def fail() -> tuple[float, float]:
        raise RuntimeError("fixture sampling failure")

    sampler = RuntimeUtilizationSampler(sample_fn=fail)
    sampler.sample_once()
    snapshot = sampler.snapshot()

    assert snapshot["status"] == "unavailable"
    assert snapshot["sample_count"] == 0
    assert snapshot["sample_error_count"] == 1
    assert snapshot["last_error_type"] == "RuntimeError"
    assert "gpu_utilization_mean_percent" not in snapshot
    validate_host_runtime_telemetry(snapshot)
    with pytest.raises(RuntimeTelemetryError, match="missing or incomplete"):
        validate_formal_runtime_utilization(snapshot)


def test_runtime_sampler_thread_lifecycle_collects_immediate_sample() -> None:
    sampler = RuntimeUtilizationSampler(interval_seconds=60.0, sample_fn=lambda: (25.0, 512.0))
    sampler.start()
    snapshot = sampler.stop()

    assert snapshot["status"] == "available"
    assert cast(int, snapshot["sample_count"]) >= 1
