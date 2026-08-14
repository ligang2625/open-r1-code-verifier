"""Tests for strict GRPO config, reward, runtime, and run artifacts."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import code_verifier.training.grpo as grpo_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.grpo import (
    GRPOTrainingError,
    _GRPORuntime,
    _load_grpo_runtime,
    _load_merged_sft_policy,
    _runtime_arguments,
    build_grpo_reward_callback,
    grpo_training_config_from_mapping,
    load_grpo_training_config,
    validate_grpo_artifact_pair,
    validate_grpo_config_pair,
    validate_grpo_training_hardware,
)
from code_verifier.training.sft import SFTCheckpointIdentity


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


class _FakeCuda:
    def __init__(self, *, memory_gb: float, bf16: bool) -> None:
        self.memory_gb = memory_gb
        self.bf16 = bf16

    @staticmethod
    def is_available() -> bool:
        return True

    def get_device_properties(self, index: int) -> SimpleNamespace:
        assert index == 0
        return SimpleNamespace(total_memory=int(self.memory_gb * 1024**3))

    def is_bf16_supported(self, *, including_emulation: bool) -> bool:
        assert including_emulation is False
        return self.bf16


def test_grpo_hardware_guard_rejects_six_gb_and_accepts_mock_24gb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = grpo_training_config_from_mapping(_config_mapping(tmp_path))
    monkeypatch.setattr(
        grpo_module,
        "_load_torch_runtime",
        lambda: SimpleNamespace(cuda=_FakeCuda(memory_gb=6.0, bf16=False)),
    )
    with pytest.raises(GRPOTrainingError, match="at least 20"):
        validate_grpo_training_hardware(config)
    with pytest.raises(GRPOTrainingError, match="at least 20"):
        validate_grpo_training_hardware(replace(config, min_cuda_memory_gb=1.0))

    monkeypatch.setattr(
        grpo_module,
        "_load_torch_runtime",
        lambda: SimpleNamespace(cuda=_FakeCuda(memory_gb=24.0, bf16=True)),
    )
    validate_grpo_training_hardware(config)


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(dict(kwargs))
        return SimpleNamespace(**kwargs)


def _parent_sft(tmp_path: Path) -> SFTCheckpointIdentity:
    return SFTCheckpointIdentity(
        run_dir=tmp_path / "sft-run",
        checkpoint_dir=tmp_path / "sft-run" / "checkpoints",
        run_id="sft-b",
        model_id="example/model",
        model_revision="a" * 40,
        dataset_hash="b" * 64,
        config_hash="c" * 64,
        dependency_lock_hash="d" * 64,
        seed=42,
    )


def _argument_runtime() -> tuple[_GRPORuntime, _Recorder, _Recorder]:
    model_config = _Recorder()
    training_config = _Recorder()
    return (
        _GRPORuntime(
            model_config_type=model_config,
            training_config_type=training_config,
            trainer_type=object,
            get_peft_config=lambda _: "NEW_LORA",
            get_tokenizer=lambda *_: object(),
            get_model=lambda *_: object(),
            peft_config_type=object,
            peft_model_type=object,
        ),
        model_config,
        training_config,
    )


def test_grpo_runtime_arguments_bind_parent_model_and_frozen_invariants(tmp_path: Path) -> None:
    runtime, model_config, training_config = _argument_runtime()
    config = grpo_training_config_from_mapping(_config_mapping(tmp_path))
    _runtime_arguments(
        config,
        checkpoint_dir=tmp_path / "checkpoints",
        parent_sft=_parent_sft(tmp_path),
        seed=7,
        runtime=runtime,
    )

    model_kwargs = model_config.calls[0]
    assert model_kwargs["model_name_or_path"] == "example/model"
    assert model_kwargs["model_revision"] == "a" * 40
    assert model_kwargs["use_peft"] is True
    assert model_kwargs["trust_remote_code"] is False
    assert model_kwargs["load_in_4bit"] is False
    assert model_kwargs["load_in_8bit"] is False
    training_kwargs = training_config.calls[0]
    assert training_kwargs["do_eval"] is False
    assert training_kwargs["eval_strategy"] == "no"
    assert training_kwargs["use_vllm"] is False
    assert training_kwargs["report_to"] == []
    assert training_kwargs["push_to_hub"] is False
    assert training_kwargs["seed"] == 7


def test_pinned_grpo_runtime_contract() -> None:
    runtime = _load_grpo_runtime()
    for symbol in (
        runtime.model_config_type,
        runtime.training_config_type,
        runtime.trainer_type,
        runtime.get_peft_config,
        runtime.get_tokenizer,
        runtime.get_model,
        runtime.peft_config_type,
        runtime.peft_model_type,
    ):
        assert callable(symbol)


def test_sft_adapter_is_loaded_read_only_and_safe_merged_before_grpo_lora(tmp_path: Path) -> None:
    calls: list[Any] = []
    adapter_config = SimpleNamespace(base_model_name_or_path="example/model", revision="a" * 40)

    class _PeftConfig:
        @staticmethod
        def from_pretrained(path: str) -> object:
            calls.append(("adapter_config", path))
            return adapter_config

    class _Policy:
        def merge_and_unload(self, *, safe_merge: bool) -> str:
            calls.append(("merge", safe_merge))
            return "MERGED_B"

    class _PeftModel:
        @staticmethod
        def from_pretrained(
            model: object,
            path: str,
            *,
            is_trainable: bool,
            config: object,
        ) -> _Policy:
            calls.append(("attach_b", model, path, is_trainable, config))
            return _Policy()

    def get_model(*args: object) -> str:
        assert args
        calls.append("base_a")
        return "BASE_A"

    runtime = _GRPORuntime(
        model_config_type=object,
        training_config_type=object,
        trainer_type=object,
        get_peft_config=lambda _: object(),
        get_tokenizer=lambda *_: object(),
        get_model=get_model,
        peft_config_type=_PeftConfig,
        peft_model_type=_PeftModel,
    )
    merged = _load_merged_sft_policy(
        parent_sft=_parent_sft(tmp_path),
        model_args=object(),
        training_args=object(),
        runtime=runtime,
    )

    assert merged == "MERGED_B"
    assert calls[0][0] == "adapter_config"
    assert calls[1] == "base_a"
    assert calls[2][0] == "attach_b"
    assert calls[2][3] is False
    assert calls[3] == ("merge", True)


@pytest.mark.parametrize(
    "adapter_config",
    [
        SimpleNamespace(base_model_name_or_path="other/model", revision="a" * 40),
        SimpleNamespace(base_model_name_or_path="example/model", revision="e" * 40),
    ],
)
def test_sft_adapter_identity_mismatch_fails_before_base_load(tmp_path: Path, adapter_config: object) -> None:
    base_loaded = False

    class _PeftConfig:
        @staticmethod
        def from_pretrained(path: str) -> object:
            assert path
            return adapter_config

    def get_model(*args: object) -> object:
        nonlocal base_loaded
        base_loaded = True
        return object()

    runtime = _GRPORuntime(
        model_config_type=object,
        training_config_type=object,
        trainer_type=object,
        get_peft_config=lambda _: object(),
        get_tokenizer=lambda *_: object(),
        get_model=get_model,
        peft_config_type=_PeftConfig,
        peft_model_type=object,
    )
    with pytest.raises(GRPOTrainingError, match="does not match"):
        _load_merged_sft_policy(
            parent_sft=_parent_sft(tmp_path),
            model_args=object(),
            training_args=object(),
            runtime=runtime,
        )
    assert base_loaded is False
