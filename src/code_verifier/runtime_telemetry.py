"""Dependency-free runtime utilization sampling for formal GPU throughput evidence."""

from __future__ import annotations

import math
import os
import resource
import statistics
import subprocess
from collections.abc import Callable, Mapping
from threading import Event, RLock, Thread
from typing import cast

_RUNTIME_UTILIZATION_VERSION = "wp9b-runtime-utilization-v1"


class RuntimeTelemetryError(RuntimeError):
    """Raised when runtime telemetry values or lifecycle operations are invalid."""


def _nvidia_smi_sample() -> tuple[float, float]:
    """Return GPU utilization percent and used-memory MiB from the first visible GPU."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
                "--id=0",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeTelemetryError(f"nvidia-smi sampling failed: {type(error).__name__}") from None
    if result.returncode != 0:
        raise RuntimeTelemetryError("nvidia-smi sampling returned a non-zero status")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeTelemetryError("nvidia-smi sampling returned an unexpected device count")
    parts = [part.strip() for part in lines[0].split(",")]
    if len(parts) != 2:
        raise RuntimeTelemetryError("nvidia-smi sampling returned an invalid row")
    try:
        utilization = float(parts[0])
        memory_mib = float(parts[1])
    except ValueError:
        raise RuntimeTelemetryError("nvidia-smi sampling returned non-numeric values") from None
    if (
        not math.isfinite(utilization)
        or not 0.0 <= utilization <= 100.0
        or not math.isfinite(memory_mib)
        or memory_mib < 0.0
    ):
        raise RuntimeTelemetryError("nvidia-smi sampling returned out-of-range values")
    return utilization, memory_mib


def _percentile_95(values: list[float]) -> float:
    if not values:
        raise RuntimeTelemetryError("cannot compute utilization percentile from no samples")
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


class RuntimeUtilizationSampler:
    """Periodically sample GPU utilization; failures are explicit rather than synthetic zeros."""

    def __init__(
        self,
        *,
        interval_seconds: float = 1.0,
        sample_fn: Callable[[], tuple[float, float]] = _nvidia_smi_sample,
    ) -> None:
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, int | float)
            or not math.isfinite(float(interval_seconds))
            or float(interval_seconds) <= 0.0
        ):
            raise RuntimeTelemetryError("sampling interval must be finite and positive")
        self.interval_seconds = float(interval_seconds)
        self._sample_fn = sample_fn
        self._samples: list[tuple[float, float]] = []
        self._errors = 0
        self._last_error_type: str | None = None
        self._lock = RLock()
        self._stop = Event()
        self._thread: Thread | None = None

    def sample_once(self) -> None:
        """Collect one sample synchronously; useful for deterministic engineering tests."""
        try:
            utilization, memory_mib = self._sample_fn()
            if (
                not math.isfinite(utilization)
                or not 0.0 <= utilization <= 100.0
                or not math.isfinite(memory_mib)
                or memory_mib < 0.0
            ):
                raise RuntimeTelemetryError("runtime utilization sample is out of range")
        except Exception as error:
            with self._lock:
                self._errors += 1
                self._last_error_type = type(error).__name__
            return
        with self._lock:
            self._samples.append((float(utilization), float(memory_mib)))

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample_once()
            if self._stop.wait(self.interval_seconds):
                break

    def start(self) -> None:
        """Start periodic sampling exactly once."""
        with self._lock:
            if self._thread is not None:
                raise RuntimeTelemetryError("runtime utilization sampler was already started")
            self._stop.clear()
            self._thread = Thread(target=self._run, name="runtime-utilization-sampler", daemon=True)
            self._thread.start()

    def stop(self) -> dict[str, object]:
        """Stop periodic sampling and return one payload-free aggregate snapshot."""
        with self._lock:
            thread = self._thread
        if thread is not None:
            self._stop.set()
            thread.join(timeout=max(2.0, self.interval_seconds + 1.0))
            if thread.is_alive():
                raise RuntimeTelemetryError("runtime utilization sampler did not stop cleanly")
        return self.snapshot()

    def snapshot(self) -> dict[str, object]:
        """Return finite aggregates, or explicit unavailable status when every sample failed."""
        with self._lock:
            samples = list(self._samples)
            errors = self._errors
            last_error_type = self._last_error_type
        cpu_count = os.cpu_count()
        max_rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        max_rss_mib = float(max_rss_raw) / 1024.0
        if not math.isfinite(max_rss_mib) or max_rss_mib < 0.0:
            raise RuntimeTelemetryError("host max RSS telemetry is invalid")
        base: dict[str, object] = {
            "version": _RUNTIME_UTILIZATION_VERSION,
            "sample_interval_seconds": self.interval_seconds,
            "sample_count": len(samples),
            "sample_error_count": errors,
            "last_error_type": last_error_type,
            "host_cpu_count": cpu_count,
            "host_max_rss_mib": max_rss_mib,
        }
        if not samples:
            return {**base, "status": "unavailable"}
        utilization = [sample[0] for sample in samples]
        memory = [sample[1] for sample in samples]
        values = {
            "gpu_utilization_mean_percent": statistics.fmean(utilization),
            "gpu_utilization_p95_percent": _percentile_95(utilization),
            "gpu_memory_used_mean_mib": statistics.fmean(memory),
            "gpu_memory_used_p95_mib": _percentile_95(memory),
            "gpu_memory_used_max_mib": max(memory),
        }
        if any(not math.isfinite(value) or value < 0.0 for value in values.values()):
            raise RuntimeTelemetryError("runtime utilization aggregate is invalid")
        return {**base, "status": "available", **values}


def validate_host_runtime_telemetry(value: object) -> Mapping[str, object]:
    """Validate payload-free host resource telemetry without requiring a local GPU."""
    if not isinstance(value, Mapping) or value.get("version") != _RUNTIME_UTILIZATION_VERSION:
        raise RuntimeTelemetryError("host runtime telemetry is missing or invalid")
    host_cpu_count = value.get("host_cpu_count")
    host_max_rss = value.get("host_max_rss_mib")
    if isinstance(host_cpu_count, bool) or not isinstance(host_cpu_count, int) or host_cpu_count <= 0:
        raise RuntimeTelemetryError("host CPU telemetry is invalid")
    if (
        isinstance(host_max_rss, bool)
        or not isinstance(host_max_rss, int | float)
        or not math.isfinite(float(host_max_rss))
        or float(host_max_rss) < 0.0
    ):
        raise RuntimeTelemetryError("host max RSS telemetry is invalid")
    return cast(Mapping[str, object], value)


def validate_formal_runtime_utilization(value: object) -> Mapping[str, object]:
    """Require complete available utilization evidence before a formal throughput report can close."""
    required = {
        "version",
        "status",
        "sample_interval_seconds",
        "sample_count",
        "sample_error_count",
        "last_error_type",
        "host_cpu_count",
        "host_max_rss_mib",
        "gpu_utilization_mean_percent",
        "gpu_utilization_p95_percent",
        "gpu_memory_used_mean_mib",
        "gpu_memory_used_p95_mib",
        "gpu_memory_used_max_mib",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise RuntimeTelemetryError("formal runtime utilization evidence is missing or incomplete")
    if value.get("version") != _RUNTIME_UTILIZATION_VERSION or value.get("status") != "available":
        raise RuntimeTelemetryError("formal runtime utilization evidence is unavailable")
    sample_count = value.get("sample_count")
    sample_errors = value.get("sample_error_count")
    host_cpu_count = value.get("host_cpu_count")
    if isinstance(host_cpu_count, bool) or not isinstance(host_cpu_count, int) or host_cpu_count <= 0:
        raise RuntimeTelemetryError("formal host CPU telemetry is invalid")
    last_error_type = value.get("last_error_type")
    if last_error_type is not None and not isinstance(last_error_type, str):
        raise RuntimeTelemetryError("formal runtime utilization error telemetry is invalid")
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or sample_count <= 0
        or isinstance(sample_errors, bool)
        or not isinstance(sample_errors, int)
        or sample_errors < 0
    ):
        raise RuntimeTelemetryError("formal runtime utilization sample counters are invalid")
    for field in (
        "sample_interval_seconds",
        "host_max_rss_mib",
        "gpu_utilization_mean_percent",
        "gpu_utilization_p95_percent",
        "gpu_memory_used_mean_mib",
        "gpu_memory_used_p95_mib",
        "gpu_memory_used_max_mib",
    ):
        raw = value.get(field)
        if (
            isinstance(raw, bool)
            or not isinstance(raw, int | float)
            or not math.isfinite(float(raw))
            or float(raw) < 0.0
        ):
            raise RuntimeTelemetryError("formal runtime utilization numeric telemetry is invalid")
        if field == "sample_interval_seconds" and float(raw) <= 0.0:
            raise RuntimeTelemetryError("formal runtime utilization sampling interval is invalid")
    for field in ("gpu_utilization_mean_percent", "gpu_utilization_p95_percent"):
        if cast(float, value[field]) > 100.0:
            raise RuntimeTelemetryError("formal GPU utilization exceeds 100 percent")
    return cast(Mapping[str, object], value)
