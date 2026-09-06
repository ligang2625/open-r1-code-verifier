#!/usr/bin/env python3
"""Strict WP9-c C29 k=8 pilot acceptance checker."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import cast

from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.training.grpo import load_completed_grpo_checkpoint

MIN_GROUPS = 100
EXPECTED_SAMPLE_COUNT = 8
GREEN_THRESHOLD = 0.20
STOP_THRESHOLD = 0.25
EXPECTED_CALIBRATION_SHA256 = "5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b"
EXPECTED_ACTIVE_ORDER_SHA256 = "401f854032095cb638637dcf2d1ec000b770cd2d4c78619331f0b13746618c14"
EXPECTED_PUBLIC_SHA256 = "558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c"
EXPECTED_HIDDEN_SHA256 = "9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec"


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise ValueError(f"cannot read strict JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return cast(dict[str, object], value)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"cannot read JSONL: {path}") from error
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"JSON object required at {path}:{line_number}")
        rows.append(cast(dict[str, object], value))
    return rows


def check_pilot(run_dir: Path, *, reward_mode: str) -> dict[str, object]:
    if reward_mode not in {"public", "hidden"}:
        raise ValueError("reward_mode must be public or hidden")
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.reward_mode != reward_mode:
        raise ValueError("pilot reward mode drift")
    if identity.parent_sft.run_id != "B-sft-formal-seed42":
        raise ValueError("pilot parent B drift")

    run = _load_json(run_dir / "run.json")
    if run.get("status") != "completed":
        raise ValueError("pilot run is not completed")
    if run.get("calibration_manifest_sha256") != EXPECTED_CALIBRATION_SHA256:
        raise ValueError("pilot calibration manifest drift")
    if run.get("active_order_sha256") != EXPECTED_ACTIVE_ORDER_SHA256:
        raise ValueError("pilot active order drift")
    if run.get("active_public_training_sha256") != EXPECTED_PUBLIC_SHA256:
        raise ValueError("pilot Public training identity drift")
    if run.get("active_hidden_training_sha256") != EXPECTED_HIDDEN_SHA256:
        raise ValueError("pilot Hidden training identity drift")
    benchmark_sha = run.get("benchmark_report_sha256")
    workers = run.get("verification_workers")
    if not isinstance(benchmark_sha, str) or len(benchmark_sha) != 64:
        raise ValueError("pilot benchmark report identity is missing")
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 64:
        raise ValueError("pilot verification worker identity is invalid")
    runtime = run.get("runtime_utilization")
    if not isinstance(runtime, dict) or runtime.get("status") != "available":
        raise ValueError("pilot runtime utilization is unavailable")
    sample_count = runtime.get("sample_count")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
        raise ValueError("pilot runtime utilization sample_count is invalid")
    if runtime.get("sample_error_count") != 0:
        raise ValueError("pilot runtime utilization sampling reported errors")
    for field in (
        "gpu_utilization_mean_percent",
        "gpu_utilization_p95_percent",
        "gpu_memory_used_mean_mib",
        "gpu_memory_used_p95_mib",
        "gpu_memory_used_max_mib",
        "host_max_rss_mib",
    ):
        value = runtime.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError(f"pilot runtime utilization field is invalid: {field}")

    retry = run.get("reward_infrastructure_retry")
    if not isinstance(retry, dict):
        raise ValueError("pilot reward infrastructure telemetry is missing")
    for field in ("retry_attempts", "retry_successes", "retry_exhausted", "recovery_prepare_failures"):
        value = retry.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"pilot infrastructure telemetry field is invalid: {field}")
    unstable_fields = ("retry_attempts", "retry_exhausted", "recovery_prepare_failures")
    if any(int(cast(int, retry[field])) != 0 for field in unstable_fields):
        raise ValueError("pilot observed reward infrastructure instability")

    peak = run.get("peak_cuda_memory_reserved_bytes")
    if isinstance(peak, bool) or not isinstance(peak, int) or peak <= 0:
        raise ValueError("pilot peak CUDA memory telemetry is invalid")

    groups = _load_jsonl(run_dir / "group_metrics.jsonl")
    if len(groups) < MIN_GROUPS:
        raise ValueError(f"pilot has too few groups: {len(groups)}/{MIN_GROUPS}")
    zero_variance = 0
    all_correct = 0
    all_zero = 0
    for index, row in enumerate(groups):
        if row.get("reward_mode") != reward_mode:
            raise ValueError(f"pilot group reward mode drift at row {index}")
        if row.get("sample_count") != EXPECTED_SAMPLE_COUNT:
            raise ValueError(f"pilot group sample_count drift at row {index}")
        for field in (
            "test_reward_mean",
            "test_reward_std",
            "total_reward_mean",
            "total_reward_std",
            "verifier_runtime_seconds",
            "executor_runtime_seconds",
            "verifier_batch_wall_seconds",
        ):
            value = row.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                raise ValueError(f"pilot group field is invalid at row {index}: {field}")
        marker = row.get("total_reward_zero_variance")
        if not isinstance(marker, bool):
            raise ValueError(f"pilot zero-variance marker missing at row {index}")
        zero_variance += int(marker)
        all_correct += int(row.get("all_test_correct") is True)
        all_zero += int(row.get("all_test_zero") is True)

    fraction = zero_variance / len(groups)
    if fraction > STOP_THRESHOLD:
        decision = "stop"
    elif fraction >= GREEN_THRESHOLD:
        decision = "warning"
    else:
        decision = "green"
    return {
        "schema_version": "wp9c-c29-grpo-pilot-acceptance-v1",
        "status": "completed",
        "decision": decision,
        "reward_mode": reward_mode,
        "run_dir": str(run_dir),
        "run_id": identity.run_id,
        "group_count": len(groups),
        "sample_count_per_group": EXPECTED_SAMPLE_COUNT,
        "zero_variance_group_count": zero_variance,
        "zero_variance_fraction": fraction,
        "green_threshold_exclusive": GREEN_THRESHOLD,
        "stop_threshold_exclusive": STOP_THRESHOLD,
        "all_test_correct_fraction": all_correct / len(groups),
        "all_test_zero_fraction": all_zero / len(groups),
        "peak_cuda_memory_reserved_bytes": peak,
        "benchmark_report_sha256": benchmark_sha,
        "verification_workers": workers,
        "calibration_manifest_sha256": EXPECTED_CALIBRATION_SHA256,
        "active_order_sha256": EXPECTED_ACTIVE_ORDER_SHA256,
        "public_training_sha256": EXPECTED_PUBLIC_SHA256,
        "hidden_training_sha256": EXPECTED_HIDDEN_SHA256,
        "runtime_utilization": runtime,
        "reward_infrastructure_retry": retry,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--reward-mode", choices=("public", "hidden"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check_pilot(args.run_dir, reward_mode=args.reward_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["decision"] == "green" else 3


if __name__ == "__main__":
    raise SystemExit(main())
