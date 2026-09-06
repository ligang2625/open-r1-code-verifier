#!/usr/bin/env python3
"""Freeze the formal systems benchmark report for C29 active-1354 GRPO."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from code_verifier.throughput import check_refresh_benchmark_report, summarize_refresh_benchmarks


def _existing_dir(value: str, *, label: str) -> str:
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError(f"{label} must be an existing absolute directory: {path}")
    return str(path)


def _run_metadata(path: str, *, label: str) -> dict[str, object]:
    run_dir = Path(_existing_dir(path, label=label))
    try:
        value = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} run.json is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} run.json must be an object")
    return value


def _assert_eval200_generation_source(path: str, *, batch_size: int) -> str:
    label = f"eval_b{batch_size}"
    resolved = _existing_dir(path, label=label)
    value = _run_metadata(resolved, label=label)
    expected_run_id = f"wp9c-c29-b-eval200-b{batch_size}-seed42"
    if value.get("run_id") != expected_run_id:
        raise ValueError(f"{label} is not the expected eval200 run")
    if value.get("status") != "completed" or value.get("seed") != 42:
        raise ValueError(f"{label} is not a completed seed-42 run")
    if value.get("batch_size") != batch_size:
        raise ValueError(f"{label} batch size drift")
    if value.get("total_problems") != 200 or value.get("completed_records") != 200:
        raise ValueError(f"{label} must contain exactly 200 completed eval problems")
    return resolved


def _assert_eval200_verification_source(path: str, *, workers: int) -> tuple[str, str]:
    label = f"eval_v{workers}"
    resolved = _existing_dir(path, label=label)
    value = _run_metadata(resolved, label=label)
    if value.get("run_id") != "wp9c-c29-b-eval200-b1-seed42":
        raise ValueError(f"{label} run identity is not the fresh eval200 b1 source")
    if value.get("status") != "completed" or value.get("seed") != 42:
        raise ValueError(f"{label} is not a completed seed-42 verification run")
    if value.get("verification_workers") != workers:
        raise ValueError(f"{label} verification worker count drift")
    if value.get("total_problems") != 200 or value.get("completed_records") != 200:
        raise ValueError(f"{label} must contain exactly 200 completed verification records")
    generation_run_id = value.get("generation_bundle_run_id")
    records_sha = value.get("generation_bundle_records_sha256")
    if generation_run_id != "wp9c-c29-b-eval200-b1-seed42" or not isinstance(records_sha, str):
        raise ValueError(f"{label} generation source provenance drift")
    return resolved, records_sha


def build(args: argparse.Namespace) -> dict[str, object]:
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        raise ValueError("output_root must be absolute")
    manifest_path = output_root / "benchmark_manifest.yaml"
    report_dir = output_root / "report"
    if manifest_path.exists() or report_dir.exists():
        raise FileExistsError("formal benchmark output already exists; do not overwrite")

    eval_generation = {
        batch_size: _assert_eval200_generation_source(getattr(args, f"eval_b{batch_size}"), batch_size=batch_size)
        for batch_size in (1, 2, 4, 8)
    }
    eval_verification: dict[int, str] = {}
    verification_generation_records_sha: str | None = None
    for workers in (1, 8, 16, 32, 64):
        path, records_sha = _assert_eval200_verification_source(getattr(args, f"eval_v{workers}"), workers=workers)
        if verification_generation_records_sha is None:
            verification_generation_records_sha = records_sha
        elif records_sha != verification_generation_records_sha:
            raise ValueError("eval verification candidates do not bind the same fresh eval200 b1 generation bundle")
        eval_verification[workers] = path

    manifest = {
        "version": "wp9b-refresh-benchmark-v1",
        "evidence_class": "formal",
        "eval_generation": {
            "baseline": eval_generation[1],
            "candidates": [eval_generation[batch_size] for batch_size in (2, 4, 8)],
        },
        "eval_verification": {
            "baseline": eval_verification[1],
            "candidates": [eval_verification[workers] for workers in (8, 16, 32, 64)],
        },
        "grpo_verification": {
            "baseline": _existing_dir(args.grpo_k8_w8, label="grpo_k8_w8"),
            "candidates": [
                _existing_dir(args.grpo_k8_w16, label="grpo_k8_w16"),
                _existing_dir(args.grpo_k8_w32, label="grpo_k8_w32"),
                _existing_dir(args.grpo_k8_w64, label="grpo_k8_w64"),
            ],
        },
        "grpo_group_size_diagnostic": {
            "k4": _existing_dir(args.grpo_k4_w8, label="grpo_k4_w8"),
            "k8": _existing_dir(args.grpo_k8_w8, label="grpo_k8_w8"),
        },
        "paired_grpo": {
            "sequential": {
                "public": _existing_dir(args.grpo_k8_w8, label="grpo_k8_w8"),
                "hidden": _existing_dir(args.grpo_hidden_sequential, label="grpo_hidden_sequential"),
            },
            "concurrent": {
                "public": _existing_dir(args.grpo_public_concurrent, label="grpo_public_concurrent"),
                "hidden": _existing_dir(args.grpo_hidden_concurrent, label="grpo_hidden_concurrent"),
            },
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    summary = summarize_refresh_benchmarks(manifest_path, output_dir=report_dir)
    checked = check_refresh_benchmark_report(summary.report_path)
    if checked.evidence_class != "formal":
        raise ValueError("frozen benchmark report is not formal")
    if checked.calibration_manifest_sha256 != "5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b":
        raise ValueError("frozen benchmark report is not bound to C29 calibration")
    if checked.active_order_sha256 != "401f854032095cb638637dcf2d1ec000b770cd2d4c78619331f0b13746618c14":
        raise ValueError("frozen benchmark report active order differs from C29")
    if checked.active_public_training_sha256 != "558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c":
        raise ValueError("frozen benchmark report Public training identity differs from C29")
    if checked.active_hidden_training_sha256 != "9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec":
        raise ValueError("frozen benchmark report Hidden training identity differs from C29")
    result = {
        "schema_version": "wp9c-c29-formal-benchmark-freeze-v1",
        "status": "completed",
        "manifest": str(manifest_path),
        "report": str(summary.report_path),
        "systems_benchmark_eval_problem_count": 200,
        "systems_benchmark_eval_generation_candidates": [1, 2, 4, 8],
        "eval_generation_batch16_skipped_by_operator": True,
        "scientific_heldout_eval400_remains_authoritative": True,
        "selected_eval_generation_batch_size": checked.selected_eval_generation_batch_size,
        "selected_eval_verification_workers": checked.selected_eval_verification_workers,
        "selected_grpo_verification_workers": checked.selected_grpo_verification_workers,
        "paired_grpo_mode": checked.paired_grpo_mode,
        "calibration_manifest_sha256": checked.calibration_manifest_sha256,
        "active_order_sha256": checked.active_order_sha256,
        "active_public_training_sha256": checked.active_public_training_sha256,
        "active_hidden_training_sha256": checked.active_hidden_training_sha256,
    }
    (output_root / "freeze_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("eval_b1", "eval_b2", "eval_b4", "eval_b8"):
        parser.add_argument(f"--{name.replace('_', '-')}", required=True)
    for name in ("eval_v1", "eval_v8", "eval_v16", "eval_v32", "eval_v64"):
        parser.add_argument(f"--{name.replace('_', '-')}", required=True)
    parser.add_argument("--grpo-k8-w8", required=True)
    parser.add_argument("--grpo-k8-w16", required=True)
    parser.add_argument("--grpo-k8-w32", required=True)
    parser.add_argument("--grpo-k8-w64", required=True)
    parser.add_argument("--grpo-k4-w8", required=True)
    parser.add_argument("--grpo-hidden-sequential", required=True)
    parser.add_argument("--grpo-public-concurrent", required=True)
    parser.add_argument("--grpo-hidden-concurrent", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
