#!/usr/bin/env python3
"""Run the exact C32 SFT-only continuation from frozen parent B on the 24GB target."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import cast

from code_verifier.training.sft import load_completed_sft_checkpoint, load_sft_training_config, run_sft_training

ROOT = Path(__file__).resolve().parents[6]
STAGE = ROOT / "ai-work/executor/operator/WP9-c/wp9c-sft-only-active1354/C32"
CHECKPOINT = STAGE / "checkpoint.json"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _parent_identity(run_dir: Path) -> dict[str, object]:
    parent = load_completed_sft_checkpoint(run_dir)
    return {
        "run_id": parent.run_id,
        "model_id": parent.model_id,
        "model_revision": parent.model_revision,
        "dataset_hash": parent.dataset_hash,
        "config_hash": parent.config_hash,
        "dependency_lock_hash": parent.dependency_lock_hash,
        "seed": parent.seed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--parent-sft-run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume-from-checkpoint", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/sft/wp9c-sft-only-active1354.yaml")
    args = parser.parse_args()

    checkpoint = _json(CHECKPOINT)
    if checkpoint.get("status") != "awaiting_4090_training":
        raise ValueError("C32 checkpoint is not awaiting target training")
    expected_parent = checkpoint.get("frozen_parent_b")
    if not isinstance(expected_parent, dict) or _parent_identity(args.parent_sft_run_dir) != expected_parent:
        raise ValueError("C32 parent B identity drift")

    dataset_report = _json(args.dataset_dir / "report.json")
    expected_dataset = checkpoint.get("dataset")
    if not isinstance(expected_dataset, dict):
        raise ValueError("C32 dataset checkpoint is invalid")
    if (
        dataset_report.get("status") != "prepared"
        or dataset_report.get("train_problem_count") != 1354
        or dataset_report.get("active_order_sha256") != expected_dataset.get("active_order_sha256")
        or dataset_report.get("artifacts") != expected_dataset.get("artifacts")
    ):
        raise ValueError("C32 dataset identity drift")

    config = load_sft_training_config(args.config)
    config = replace(
        config,
        dataset_path=args.dataset_dir / "training/sft.jsonl",
        validation_dataset_path=args.dataset_dir / "training/sft_validation.jsonl",
        piston_config=ROOT / "configs/execution/piston-local.yaml",
    )
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    summary = run_sft_training(
        config,
        output_root=args.output_root,
        seed=42,
        prevalidation_manifest=args.dataset_dir / "prevalidation.json",
        resume_from_checkpoint=args.resume_from_checkpoint,
        parent_sft_run_dir=args.parent_sft_run_dir,
    )
    print(
        json.dumps(
            {
                "status": "C32_SFT_CONTINUATION_COMPLETED",
                "run_dir": str(summary.run_dir),
                "checkpoint_dir": str(summary.checkpoint_dir),
                "train_samples": summary.train_samples,
                "train_loss": summary.train_loss,
                "gpu_hours": summary.gpu_hours,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
