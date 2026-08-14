"""Tests for strict GRPO config, reward, runtime, and run artifacts."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest

from code_verifier.training.grpo import (
    GRPOTrainingError,
    grpo_training_config_from_mapping,
    load_grpo_training_config,
    validate_grpo_artifact_pair,
    validate_grpo_config_pair,
)


def _config_mapping(tmp_path: Path, *, reward_mode: str = "public") -> dict[str, object]:
    return {
        "run_name": f"{reward_mode}-unit",
        "reward_mode": reward_mode,
        "dataset_path": str(tmp_path / f"{reward_mode}.jsonl"),
        "piston_config": str(tmp_path / "piston.yaml"),
        "num_generations": 4,
        "max_prompt_length": 1024,
        "max_completion_length": 512,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "learning_rate": 0.000005,
        "num_train_epochs": 1.0,
        "max_steps": 300,
        "warmup_ratio": 0.05,
        "lr_scheduler_type": "cosine",
        "temperature": 0.8,
        "top_p": 0.95,
        "beta": 0.01,
        "bf16": True,
        "fp16": False,
        "gradient_checkpointing": True,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "logging_steps": 1,
        "save_steps": 50,
        "eval_steps": 50,
        "seed": 42,
        "min_cuda_memory_gb": 20.0,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_name", "../escape"),
        ("reward_mode", "eval"),
        ("num_generations", 0),
        ("learning_rate", math.nan),
        ("warmup_ratio", 1.1),
        ("temperature", 0.0),
        ("top_p", 1.1),
        ("beta", -0.1),
        ("bf16", False),
        ("gradient_checkpointing", False),
        ("lora_dropout", 1.0),
        ("lr_scheduler_type", "linear"),
        ("min_cuda_memory_gb", 19.9),
    ],
)
def test_grpo_config_rejects_unknown_and_unsafe_values(tmp_path: Path, field: str, value: object) -> None:
    mapping = _config_mapping(tmp_path)
    mapping[field] = value
    with pytest.raises(GRPOTrainingError):
        grpo_training_config_from_mapping(mapping)

    mapping = _config_mapping(tmp_path)
    mapping["unknown"] = True
    with pytest.raises(GRPOTrainingError, match="unknown"):
        grpo_training_config_from_mapping(mapping)


def test_checked_in_grpo_configs_match_spec_and_each_other() -> None:
    public = load_grpo_training_config(Path("configs/grpo/public.yaml"))
    hidden = load_grpo_training_config(Path("configs/grpo/hidden.yaml"))

    validate_grpo_config_pair(public, hidden)
    assert public.num_generations == 4
    assert public.max_prompt_length == 1024
    assert public.max_completion_length == 512
    assert public.per_device_train_batch_size == 1
    assert public.gradient_accumulation_steps == 8
    assert public.learning_rate == 0.000005
    assert public.max_steps == 300
    assert public.lora_r == 16
    assert public.lora_alpha == 32
    assert public.lora_dropout == 0.05
    assert public.min_cuda_memory_gb == 20.0


def test_grpo_config_pair_rejects_experiment_drift(tmp_path: Path) -> None:
    public = grpo_training_config_from_mapping(_config_mapping(tmp_path))
    hidden = grpo_training_config_from_mapping(_config_mapping(tmp_path, reward_mode="hidden"))
    validate_grpo_config_pair(public, hidden)

    with pytest.raises(GRPOTrainingError, match="must match"):
        validate_grpo_config_pair(public, replace(hidden, temperature=0.7))
    with pytest.raises(GRPOTrainingError, match="ordered"):
        validate_grpo_config_pair(hidden, public)


def _artifact_record(*, hidden: bool, problem_id: str = "grpo-1") -> dict[str, object]:
    record: dict[str, object] = {
        "problem_id": problem_id,
        "prompt": "Return input.",
        "function_name": "solve",
        "function_signature": "def solve(value):",
        "visible_tests": [{"input": 1, "expected": 1}],
        "metadata": {
            "difficulty": "easy",
            "category": ["unit"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "test",
            "source_url_hash": None,
        },
    }
    if hidden:
        record["train_hidden_tests"] = [{"input": 2, "expected": 2}]
    return record


def test_grpo_artifact_pair_requires_order_and_shared_fields() -> None:
    public = [_artifact_record(hidden=False, problem_id="one"), _artifact_record(hidden=False, problem_id="two")]
    hidden = [_artifact_record(hidden=True, problem_id="one"), _artifact_record(hidden=True, problem_id="two")]
    validate_grpo_artifact_pair(public, hidden)

    hidden[1]["prompt"] = "drift"
    with pytest.raises(GRPOTrainingError, match="identical inputs"):
        validate_grpo_artifact_pair(public, hidden)


def test_grpo_artifact_pair_rejects_wrong_schema_or_length() -> None:
    public = [_artifact_record(hidden=False)]
    hidden = [_artifact_record(hidden=True)]
    hidden[0]["eval_hidden_tests"] = []
    with pytest.raises(GRPOTrainingError):
        validate_grpo_artifact_pair(public, hidden)
    with pytest.raises(GRPOTrainingError, match="equal non-zero"):
        validate_grpo_artifact_pair(public, [])
