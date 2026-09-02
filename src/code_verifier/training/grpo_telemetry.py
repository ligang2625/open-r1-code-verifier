"""Bounded telemetry helpers for refresh GRPO engineering and validation."""

from __future__ import annotations

import math
from threading import RLock


class GRPORollingTelemetry:
    """Thread-safe bounded group telemetry for zero-variance monitoring."""

    def __init__(self, *, window_size: int = 128) -> None:
        if isinstance(window_size, bool) or not isinstance(window_size, int) or window_size <= 0:
            raise ValueError("window_size must be a positive integer")
        self.window_size = window_size
        self._records: list[tuple[bool, bool, float, float]] = []
        self._lock = RLock()

    def observe(
        self,
        *,
        all_test_correct: bool,
        all_test_zero: bool,
        total_reward_std: float,
        verifier_runtime_seconds: float,
    ) -> None:
        """Append one validated group observation and retain only the bounded suffix."""
        if (
            not math.isfinite(total_reward_std)
            or total_reward_std < 0.0
            or not math.isfinite(verifier_runtime_seconds)
            or verifier_runtime_seconds < 0.0
        ):
            raise ValueError("telemetry values must be finite and non-negative")
        with self._lock:
            self._records.append((all_test_correct, all_test_zero, total_reward_std, verifier_runtime_seconds))
            overflow = len(self._records) - self.window_size
            if overflow > 0:
                del self._records[:overflow]

    def snapshot(self) -> dict[str, float]:
        """Return finite rolling fractions/counts/timing for the current bounded suffix."""
        with self._lock:
            records = list(self._records)
        if not records:
            return {}
        count = len(records)
        stds = sorted(record[2] for record in records)
        midpoint = count // 2
        median_std = stds[midpoint] if count % 2 else (stds[midpoint - 1] + stds[midpoint]) / 2.0
        values = {
            "rolling_window_groups": float(count),
            "rolling_all_test_correct_fraction": sum(record[0] for record in records) / count,
            "rolling_all_test_zero_fraction": sum(record[1] for record in records) / count,
            "rolling_total_reward_zero_variance_fraction": sum(record[2] == 0.0 for record in records) / count,
            "rolling_group_reward_std_mean": sum(record[2] for record in records) / count,
            "rolling_group_reward_std_median": median_std,
            "rolling_effective_nonzero_variance_groups": float(sum(record[2] > 0.0 for record in records)),
            "rolling_verifier_runtime_seconds": sum(record[3] for record in records),
        }
        if any(not math.isfinite(value) or value < 0.0 for value in values.values()):
            raise ValueError("telemetry snapshot must be finite and non-negative")
        return values
