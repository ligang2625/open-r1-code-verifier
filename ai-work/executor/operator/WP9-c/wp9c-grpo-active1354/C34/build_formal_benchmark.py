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


def build(args: argparse.Namespace) -> dict[str, object]:
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        raise ValueError("output_root must be absolute")
    manifest_path = output_root / "benchmark_manifest.yaml"
    report_dir = output_root / "report"
    if manifest_path.exists() or report_dir.exists():
        raise FileExistsError("formal benchmark output already exists; do not overwrite")

    manifest = {
        "version": "wp9b-refresh-benchmark-v1",
        "evidence_class": "formal",
        "eval_generation": {
            "baseline": _existing_dir(args.eval_b1, label="eval_b1"),
            "candidates": [
                _existing_dir(args.eval_b2, label="eval_b2"),
                _existing_dir(args.eval_b4, label="eval_b4"),
                _existing_dir(args.eval_b8, label="eval_b8"),
                _existing_dir(args.eval_b16, label="eval_b16"),
            ],
        },
        "eval_verification": {
            "baseline": _existing_dir(args.eval_v1, label="eval_v1"),
            "candidates": [
                _existing_dir(args.eval_v8, label="eval_v8"),
                _existing_dir(args.eval_v16, label="eval_v16"),
                _existing_dir(args.eval_v32, label="eval_v32"),
                _existing_dir(args.eval_v64, label="eval_v64"),
            ],
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
    for name in ("eval_b1", "eval_b2", "eval_b4", "eval_b8", "eval_b16"):
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
