"""Tests for strict GRPO config, reward, runtime, and run artifacts."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import code_verifier.training.grpo as grpo_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.grpo import (
    GRPOTrainingError,
    build_grpo_reward_callback,
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


def _execution_result(*, passed: bool) -> ExecutionResult:
    status = ExecutionStatus.PASSED if passed else ExecutionStatus.WRONG_ANSWER
    return ExecutionResult(
        status=status,
        passed_tests=int(passed),
        total_tests=1,
        pass_rate=float(passed),
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(
                status=status,
                passed=passed,
                runtime_ms=1.0,
                stdout="",
                stderr="",
            )
        ],
    )


def _callback(
    tmp_path: Path,
    *,
    reward_mode: str,
    executor: MockExecutor,
    num_generations: int = 2,
) -> Callable[..., list[float]]:
    return build_grpo_reward_callback(
        reward_mode=reward_mode,
        executor=executor,
        rollout_log_path=tmp_path / reward_mode / "rollouts.jsonl",
        reward_log_path=tmp_path / reward_mode / "rewards.jsonl",
        group_metrics_log_path=tmp_path / reward_mode / "group_metrics.jsonl",
        num_generations=num_generations,
        max_completion_length=3,
    )


def _reward_columns(*, hidden: bool) -> dict[str, object]:
    metadata = {
        "difficulty": "easy",
        "category": ["unit"],
        "time_limit_seconds": 1.0,
        "memory_limit_mb": 128,
        "license": "test",
        "source_url_hash": None,
    }
    columns: dict[str, object] = {
        "problem_id": ["problem-1", "problem-1"],
        "function_name": ["solve", "solve"],
        "metadata": [metadata, metadata],
        "visible_tests": [
            [{"input": "VISIBLE_ONE", "expected": "VISIBLE_ONE"}],
            [{"input": "VISIBLE_TWO", "expected": "VISIBLE_TWO"}],
        ],
    }
    if hidden:
        columns["train_hidden_tests"] = [
            [{"input": "HIDDEN_ONE", "expected": "HIDDEN_ONE"}],
            [{"input": "HIDDEN_TWO", "expected": "HIDDEN_TWO"}],
        ]
    return columns


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("reward_mode", ["public", "hidden"])
def test_grpo_reward_callback_selects_only_configured_test_source_and_writes_sanitized_logs(
    tmp_path: Path,
    reward_mode: str,
) -> None:
    executor = MockExecutor([_execution_result(passed=True), _execution_result(passed=False)])
    callback = _callback(tmp_path, reward_mode=reward_mode, executor=executor)
    columns = _reward_columns(hidden=reward_mode == "hidden")

    rewards = callback(
        prompts=[[{"role": "user", "content": "PROMPT_SENTINEL"}]] * 2,
        completions=["```python\ndef solve(value): return value\n```"] * 2,
        completion_ids=[[1, 2], [1, 2, 3]],
        **columns,
    )

    selected = "VISIBLE_ONE" if reward_mode == "public" else "HIDDEN_ONE"
    assert executor.calls[0].tests == [{"input": selected, "expected": selected}]
    assert rewards == [1.1, 0.1]
    assert callback.__name__ == f"{reward_mode}_code_reward"
    rollouts = _read_jsonl(tmp_path / reward_mode / "rollouts.jsonl")
    reward_rows = _read_jsonl(tmp_path / reward_mode / "rewards.jsonl")
    groups = _read_jsonl(tmp_path / reward_mode / "group_metrics.jsonl")
    assert [row["truncated"] for row in rollouts] == [False, True]
    assert groups == [
        {
            "all_equal": False,
            "group_index": 0,
            "mean": pytest.approx(0.6),
            "problem_id": "problem-1",
            "reward_mode": reward_mode,
            "sample_count": 2,
            "std": pytest.approx(0.5),
        }
    ]
    component = reward_rows[0]
    assert component["total_reward"] == pytest.approx(
        cast(float, component["test_reward"])
        + cast(float, component["executable_reward"])
        + cast(float, component["timeout_penalty"])
        + cast(float, component["invalid_format_penalty"])
    )
    for path in (tmp_path / reward_mode / "rewards.jsonl", tmp_path / reward_mode / "group_metrics.jsonl"):
        contents = path.read_text(encoding="utf-8")
        for forbidden in ("PROMPT_SENTINEL", "VISIBLE_ONE", "HIDDEN_ONE", "completion", "function_name", "metadata"):
            assert forbidden not in contents


def test_grpo_reward_callback_rejects_batch_group_and_column_mismatch(tmp_path: Path) -> None:
    executor = MockExecutor([_execution_result(passed=True), _execution_result(passed=True)])
    callback = _callback(tmp_path, reward_mode="public", executor=executor)
    columns = _reward_columns(hidden=False)
    with pytest.raises(GRPOTrainingError, match="batch lengths"):
        callback(prompts=[[]], completions=["one", "two"], completion_ids=[[1], [1]], **columns)
    with pytest.raises(GRPOTrainingError, match="num_generations"):
        callback(
            prompts=[[], []],
            completions=["one", "two"],
            completion_ids=[[1], [1]],
            **{**columns, "problem_id": ["one", "two"]},
        )
    with pytest.raises(GRPOTrainingError, match="unexpected or missing"):
        callback(
            prompts=[[], []],
            completions=["one", "two"],
            completion_ids=[[1], [1]],
            **{**columns, "eval_hidden_tests": [[], []]},
        )
    assert executor.calls == ()


def test_grpo_reward_callback_rejects_nonfinite_core_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = _callback(tmp_path, reward_mode="public", executor=MockExecutor([]))
    monkeypatch.setattr(grpo_module, "compute_code_rewards", lambda *args, **kwargs: ([math.nan] * 2, [{}, {}]))
    with pytest.raises(GRPOTrainingError, match="finite"):
        callback(
            prompts=[[], []],
            completions=["one", "two"],
            completion_ids=[[1], [1]],
            **_reward_columns(hidden=False),
        )
