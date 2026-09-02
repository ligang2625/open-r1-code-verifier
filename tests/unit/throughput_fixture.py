from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import yaml


def write_grpo_probe(
    root: Path,
    *,
    name: str,
    reward_mode: str,
    workers: int,
    start: datetime,
    duration_seconds: float,
    reward_drift: bool = False,
    infrastructure_failure: bool = False,
    parent_config_hash: str = "7" * 64,
    parent_dependency_lock_hash: str = "8" * 64,
) -> Path:
    run = root / name
    run.mkdir(parents=True)
    end = start + timedelta(seconds=duration_seconds)
    dataset_hash = ("2" if reward_mode == "public" else "3") * 64
    metadata = {
        "status": "completed",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "reward_mode": reward_mode,
        "verification_workers": workers,
        "paired_definition_sha256": "4" * 64,
        "dataset_hash": dataset_hash,
        "seed": 42,
        "parent_sft_run_id": "B",
        "parent_sft_model_id": "model",
        "parent_sft_model_revision": "5" * 40,
        "parent_sft_dataset_hash": "6" * 64,
        "parent_sft_config_hash": parent_config_hash,
        "parent_sft_dependency_lock_hash": parent_dependency_lock_hash,
        "parent_sft_seed": 42,
        "peak_cuda_memory_reserved_bytes": 1024,
        "attempts": [
            {
                "reward_infrastructure_retry": {
                    "retry_exhausted": 1 if infrastructure_failure else 0,
                    "recovery_prepare_failures": 0,
                }
            }
        ],
    }
    (run / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (run / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "run_name": name,
                "reward_mode": reward_mode,
                "dataset_path": f"/{reward_mode}.jsonl",
                "piston_config": "/piston.yaml",
                "num_generations": 8,
                "max_completion_length": 512,
                "temperature": 0.8,
                "top_p": 0.95,
                "learning_rate": 5.0e-6,
                "seed": 42,
            }
        ),
        encoding="utf-8",
    )
    reward_value = 0.75 if reward_drift else 0.5
    reward_row = {
        "item_index": 0,
        "group_index": 0,
        "group_item_index": 0,
        "problem_id": "p1",
        "test_reward": reward_value,
        "total_reward": reward_value + 0.1,
        "executor_runtime_ms": duration_seconds * 10.0,
    }
    group_row = {
        "group_index": 0,
        "problem_id": "p1",
        "reward_mode": reward_mode,
        "sample_count": 8,
        "test_reward_mean": 0.5,
        "test_reward_std": 0.25,
        "total_reward_mean": 0.6,
        "total_reward_std": 0.25,
        "all_test_correct": False,
        "all_test_zero": False,
        "all_total_reward_equal": False,
        "executor_runtime_seconds": duration_seconds / 2.0,
        "verifier_runtime_seconds": duration_seconds / 2.0,
        "verifier_batch_wall_seconds": duration_seconds,
    }
    (run / "rewards.jsonl").write_text(json.dumps(reward_row) + "\n", encoding="utf-8")
    (run / "group_metrics.jsonl").write_text(json.dumps(group_row) + "\n", encoding="utf-8")
    return run
