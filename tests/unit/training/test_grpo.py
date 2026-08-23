"""Tests for strict GRPO config, reward, runtime, and run artifacts."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

import code_verifier.training.grpo as grpo_module
from code_verifier.analysis import build_cost_row, load_training_curve_rows
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.grpo import (
    GRPOCheckpointIdentity,
    GRPOTrainingConfig,
    GRPOTrainingError,
    _GRPORuntime,
    _load_grpo_runtime,
    _load_merged_sft_policy,
    _runtime_arguments,
    build_grpo_reward_callback,
    grpo_evaluation_checkpoint_id,
    grpo_training_config_from_mapping,
    load_completed_grpo_checkpoint,
    load_grpo_training_config,
    run_grpo_training,
    validate_grpo_artifact_pair,
    validate_grpo_config_pair,
    validate_grpo_training_hardware,
)
from code_verifier.training.sft import SFTCheckpointIdentity, load_completed_sft_checkpoint


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


def test_checked_in_grpo_smoke_and_pilot_pairs_only_change_phase_fields() -> None:
    public_main = load_grpo_training_config(Path("configs/grpo/public.yaml"))
    hidden_main = load_grpo_training_config(Path("configs/grpo/hidden.yaml"))
    public_smoke = load_grpo_training_config(Path("configs/grpo/validation-smoke-public.yaml"))
    hidden_smoke = load_grpo_training_config(Path("configs/grpo/validation-smoke-hidden.yaml"))
    public_pilot = load_grpo_training_config(Path("configs/grpo/validation-pilot-public.yaml"))
    hidden_pilot = load_grpo_training_config(Path("configs/grpo/validation-pilot-hidden.yaml"))

    validate_grpo_config_pair(public_smoke, hidden_smoke)
    validate_grpo_config_pair(public_pilot, hidden_pilot)
    assert public_smoke.max_steps == hidden_smoke.max_steps == 20
    assert public_smoke.save_steps == hidden_smoke.save_steps == 10
    assert public_pilot.max_steps == hidden_pilot.max_steps == 100
    assert public_pilot.save_steps == hidden_pilot.save_steps == 10
    assert public_smoke.run_name != public_pilot.run_name
    assert hidden_smoke.run_name != hidden_pilot.run_name

    for phased, main in (
        (public_smoke, public_main),
        (hidden_smoke, hidden_main),
        (public_pilot, public_main),
        (hidden_pilot, hidden_main),
    ):
        assert (
            replace(
                phased,
                run_name=main.run_name,
                max_steps=main.max_steps,
                save_steps=main.save_steps,
            )
            == main
        )


@pytest.mark.parametrize("num_generations", [1, 3])
def test_grpo_config_rejects_pinned_generation_batch_mismatch(
    tmp_path: Path,
    num_generations: int,
) -> None:
    mapping = _config_mapping(tmp_path)
    mapping["num_generations"] = num_generations
    with pytest.raises(GRPOTrainingError, match="num_generations"):
        grpo_training_config_from_mapping(mapping)


def test_grpo_config_accepts_pinned_generation_batch_divisor_four(tmp_path: Path) -> None:
    config = grpo_training_config_from_mapping(_config_mapping(tmp_path))
    assert config.num_generations == 4


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
            [json.dumps({"input": "VISIBLE_ONE", "expected": "VISIBLE_ONE"})],
            [json.dumps({"input": "VISIBLE_TWO", "expected": "VISIBLE_TWO"})],
        ],
    }
    if hidden:
        columns["train_hidden_tests"] = [
            [json.dumps({"input": "HIDDEN_ONE", "expected": "HIDDEN_ONE"})],
            [json.dumps({"input": "HIDDEN_TWO", "expected": "HIDDEN_TWO"})],
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
    assert component["executor_runtime_ms"] == 1.0
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


def test_grpo_reward_callback_restores_heterogeneous_json_test_values(tmp_path: Path) -> None:
    executor = MockExecutor([_execution_result(passed=True), _execution_result(passed=True)])
    callback = _callback(tmp_path, reward_mode="public", executor=executor)
    columns = _reward_columns(hidden=False)
    columns["visible_tests"] = [
        [json.dumps({"input": [1, {"x": True}], "expected": {"answer": [1, None]}})],
        [json.dumps({"input": {"value": 3.5}, "expected": [False, "ok"]})],
    ]

    callback(
        prompts=[[{"role": "user", "content": "prompt"}]] * 2,
        completions=["```python\ndef solve(value): return value\n```"] * 2,
        completion_ids=[[1], [1]],
        **columns,
    )

    assert executor.calls[0].tests == [{"input": [1, {"x": True}], "expected": {"answer": [1, None]}}]
    assert executor.calls[1].tests == [{"input": {"value": 3.5}, "expected": [False, "ok"]}]


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
    assert training_kwargs["skip_memory_metrics"] is False
    assert training_kwargs["logging_nan_inf_filter"] is False
    assert training_kwargs["save_total_limit"] is None
    assert training_kwargs["save_only_model"] is False


def test_grpo_runtime_arguments_normalize_pinned_constructor_value_error(tmp_path: Path) -> None:
    def reject(**kwargs: object) -> object:
        raise ValueError("raw pinned constructor detail")

    runtime = _GRPORuntime(
        model_config_type=_Recorder(),
        training_config_type=reject,
        trainer_type=object,
        get_peft_config=lambda _: object(),
        get_tokenizer=lambda *_: object(),
        get_model=lambda *_: object(),
        peft_config_type=object,
        peft_model_type=object,
    )
    with pytest.raises(GRPOTrainingError, match="pinned GRPO argument constructor"):
        _runtime_arguments(
            grpo_training_config_from_mapping(_config_mapping(tmp_path)),
            checkpoint_dir=tmp_path / "checkpoints",
            parent_sft=_parent_sft(tmp_path),
            seed=42,
            runtime=runtime,
        )


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


def _write_completed_sft_run(run_dir: Path, *, dataset_hash: str = "b" * 64) -> None:
    run_dir.mkdir()
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "run_id": "completed-b",
                "model_id": "example/model",
                "model_revision": "a" * 40,
                "dataset_hash": dataset_hash,
                "config_hash": "c" * 64,
                "dependency_lock_hash": "d" * 64,
                "seed": 42,
            }
        ),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "example/model", "peft_type": "LORA"}),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_model.safetensors").write_bytes(b"fixture-adapter")
    for name in ("resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log"):
        (run_dir / name).touch()


def _write_completed_grpo_run(
    run_dir: Path,
    parent_run_dir: Path,
    *,
    reward_mode: str = "public",
) -> None:
    parent = SFTCheckpointIdentity(
        run_dir=parent_run_dir.resolve(),
        checkpoint_dir=(parent_run_dir / "checkpoints").resolve(),
        run_id="completed-b",
        model_id="example/model",
        model_revision="a" * 40,
        dataset_hash="b" * 64,
        config_hash="c" * 64,
        dependency_lock_hash="d" * 64,
        seed=42,
    )
    run_dir.mkdir()
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    metadata = {
        "status": "completed",
        "run_id": f"completed-{reward_mode}",
        "reward_mode": reward_mode,
        "dataset_hash": "1" * 64,
        "config_hash": "2" * 64,
        "paired_definition_sha256": "4" * 64,
        "dependency_lock_hash": "3" * 64,
        "seed": 7,
        "parent_sft_run_id": parent.run_id,
        "parent_sft_model_id": parent.model_id,
        "parent_sft_model_revision": parent.model_revision,
        "parent_sft_dataset_hash": parent.dataset_hash,
        "parent_sft_config_hash": parent.config_hash,
        "parent_sft_dependency_lock_hash": parent.dependency_lock_hash,
        "parent_sft_seed": parent.seed,
        "parent_sft_run_path": str(parent.run_dir),
        "parent_sft_checkpoint_path": str(parent.checkpoint_dir),
    }
    (run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (checkpoint_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": parent.model_id,
                "revision": parent.model_revision,
                "peft_type": "LORA",
            }
        ),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_model.safetensors").write_bytes(b"fixture-grpo-adapter")
    (checkpoint_dir / "checkpoint-1").mkdir()
    for name in (
        "resolved_config.yaml",
        "environment.json",
        "metrics.jsonl",
        "rollouts.jsonl",
        "rewards.jsonl",
        "group_metrics.jsonl",
        "stdout.log",
        "stderr.log",
    ):
        (run_dir / name).touch()


def test_load_completed_grpo_checkpoint_accepts_completed_run_and_parent_identity(tmp_path: Path) -> None:
    parent_run = tmp_path / "sft-run"
    grpo_run = tmp_path / "grpo-run"
    _write_completed_sft_run(parent_run)
    _write_completed_grpo_run(grpo_run, parent_run)

    identity = load_completed_grpo_checkpoint(grpo_run)

    assert identity == GRPOCheckpointIdentity(
        run_dir=grpo_run.resolve(),
        checkpoint_dir=(grpo_run / "checkpoints").resolve(),
        run_id="completed-public",
        reward_mode="public",
        dataset_hash="1" * 64,
        config_hash="2" * 64,
        paired_definition_sha256="4" * 64,
        dependency_lock_hash="3" * 64,
        seed=7,
        parent_sft=SFTCheckpointIdentity(
            run_dir=parent_run.resolve(),
            checkpoint_dir=(parent_run / "checkpoints").resolve(),
            run_id="completed-b",
            model_id="example/model",
            model_revision="a" * 40,
            dataset_hash="b" * 64,
            config_hash="c" * 64,
            dependency_lock_hash="d" * 64,
            seed=42,
        ),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "running"),
        ("run_id", ""),
        ("reward_mode", "eval"),
        ("dataset_hash", "invalid"),
        ("config_hash", None),
        ("paired_definition_sha256", "f" * 63),
        ("dependency_lock_hash", "f" * 63),
        ("seed", True),
    ],
)
def test_load_completed_grpo_checkpoint_rejects_running_failed_or_invalid_metadata(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    parent_run = tmp_path / "sft-run"
    grpo_run = tmp_path / "grpo-run"
    _write_completed_sft_run(parent_run)
    _write_completed_grpo_run(grpo_run, parent_run)
    metadata = json.loads((grpo_run / "run.json").read_text(encoding="utf-8"))
    metadata[field] = value
    (grpo_run / "run.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(GRPOTrainingError):
        load_completed_grpo_checkpoint(grpo_run)


@pytest.mark.parametrize("artifact", ["adapter_config.json", "adapter_model.safetensors"])
def test_load_completed_grpo_checkpoint_rejects_missing_or_invalid_adapter_artifact(
    tmp_path: Path,
    artifact: str,
) -> None:
    parent_run = tmp_path / "sft-run"
    grpo_run = tmp_path / "grpo-run"
    _write_completed_sft_run(parent_run)
    _write_completed_grpo_run(grpo_run, parent_run)
    (grpo_run / "checkpoints" / artifact).unlink()

    with pytest.raises(GRPOTrainingError, match="PEFT adapter"):
        load_completed_grpo_checkpoint(grpo_run)


@pytest.mark.parametrize("drift", ["metadata", "path"])
def test_load_completed_grpo_checkpoint_rejects_parent_sft_identity_or_path_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    parent_run = tmp_path / "sft-run"
    grpo_run = tmp_path / "grpo-run"
    _write_completed_sft_run(parent_run)
    _write_completed_grpo_run(grpo_run, parent_run)
    metadata = json.loads((grpo_run / "run.json").read_text(encoding="utf-8"))
    if drift == "metadata":
        metadata["parent_sft_dataset_hash"] = "e" * 64
    else:
        metadata["parent_sft_run_path"] = str(tmp_path / "missing-parent")
    (grpo_run / "run.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="parent SFT"):
        load_completed_grpo_checkpoint(grpo_run)


@pytest.mark.parametrize(
    ("field", "value"),
    [("base_model_name_or_path", "other/model"), ("revision", "e" * 40)],
)
def test_load_completed_grpo_checkpoint_rejects_adapter_base_or_revision_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    parent_run = tmp_path / "sft-run"
    grpo_run = tmp_path / "grpo-run"
    _write_completed_sft_run(parent_run)
    _write_completed_grpo_run(grpo_run, parent_run)
    config_path = grpo_run / "checkpoints" / "adapter_config.json"
    adapter_config = json.loads(config_path.read_text(encoding="utf-8"))
    adapter_config[field] = value
    config_path.write_text(json.dumps(adapter_config), encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="does not match"):
        load_completed_grpo_checkpoint(grpo_run)


def test_grpo_evaluation_checkpoint_id_is_stable_and_binds_parent_and_reward_mode(tmp_path: Path) -> None:
    parent_run = tmp_path / "sft-run"
    grpo_run = tmp_path / "grpo-run"
    _write_completed_sft_run(parent_run)
    _write_completed_grpo_run(grpo_run, parent_run)
    identity = load_completed_grpo_checkpoint(grpo_run)

    checkpoint_id = grpo_evaluation_checkpoint_id(identity)

    assert checkpoint_id == grpo_evaluation_checkpoint_id(identity)
    assert checkpoint_id.startswith(f"{identity.checkpoint_dir}#identity=")
    assert re.fullmatch(r"[0-9a-f]{64}", checkpoint_id.rsplit("=", 1)[1])
    assert grpo_evaluation_checkpoint_id(replace(identity, reward_mode="hidden")) != checkpoint_id
    assert grpo_evaluation_checkpoint_id(replace(identity, paired_definition_sha256="5" * 64)) != checkpoint_id
    changed_parent = replace(identity.parent_sft, dataset_hash="e" * 64)
    assert grpo_evaluation_checkpoint_id(replace(identity, parent_sft=changed_parent)) != checkpoint_id


def _write_grpo_artifact(path: Path, *, reward_mode: str = "public", sentinel: str = "VISIBLE_SENTINEL") -> None:
    record = _artifact_record(hidden=reward_mode == "hidden")
    record["prompt"] = "PRIVATE_PROMPT_SENTINEL"
    record["visible_tests"] = [{"input": sentinel, "expected": sentinel}]
    if reward_mode == "hidden":
        record["train_hidden_tests"] = [{"input": "HIDDEN_SENTINEL", "expected": "HIDDEN_SENTINEL"}]
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


class _FakeMergedPolicy:
    @staticmethod
    def merge_and_unload(*, safe_merge: bool) -> str:
        assert safe_merge is True
        return "MERGED_B"


class _FakePeftConfig:
    @staticmethod
    def from_pretrained(path: str) -> SimpleNamespace:
        assert Path(path).name == "checkpoints"
        return SimpleNamespace(base_model_name_or_path="example/model", revision="a" * 40)


class _FakePeftModel:
    @staticmethod
    def from_pretrained(
        model: object,
        path: str,
        *,
        is_trainable: bool,
        config: object,
    ) -> _FakeMergedPolicy:
        assert model == "BASE_A"
        assert Path(path).name == "checkpoints"
        assert is_trainable is False
        assert config is not None
        return _FakeMergedPolicy()


class _FakeTrainer:
    instances: ClassVar[list[_FakeTrainer]] = []
    loss = 0.25
    extra_metrics: ClassVar[dict[str, float]] = {}

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = dict(kwargs)
        self.resume_from_checkpoint: str | None = None
        self.state = SimpleNamespace(
            log_history=[
                {
                    "loss": 0.3,
                    "step": 1,
                    "generation_runtime_seconds": 0.5,
                    "no_grad_logps_calls": 8.0,
                    "no_grad_logps_runtime_seconds": 0.2,
                    "rollout_runtime_seconds": 0.75,
                    "step_runtime_seconds": 1.0,
                    "ignored": "text",
                }
            ],
            global_step=1,
        )
        self.__class__.instances.append(self)

    def train(self, *, resume_from_checkpoint: str | None) -> SimpleNamespace:
        self.resume_from_checkpoint = resume_from_checkpoint
        dataset = cast(Any, self.kwargs["train_dataset"])
        row = cast(dict[str, object], dataset[0])
        reward_func = cast(Callable[..., list[float]], self.kwargs["reward_funcs"])
        columns = {key: [value] * 4 for key, value in row.items() if key != "prompt"}
        reward_func(
            prompts=[row["prompt"]] * 4,
            completions=["```python\ndef solve(value):\n    return value\n```"] * 4,
            completion_ids=[[1, 2]] * 4,
            **columns,
        )
        return SimpleNamespace(metrics={"train_loss": self.loss, "train_runtime": 1.5, **self.extra_metrics})

    @staticmethod
    def save_state() -> None:
        return None

    @staticmethod
    def save_model(path: str) -> None:
        assert Path(path).name == "checkpoints"


def test_grpo_runtime_telemetry_times_generation_rollout_and_optimizer_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import torch

    class FakeModel:
        def __init__(self) -> None:
            self.training = True
            self.is_gradient_checkpointing = True
            self.generate_states: list[tuple[bool, bool]] = []

        def gradient_checkpointing_disable(self) -> None:
            assert self.is_gradient_checkpointing is True
            self.is_gradient_checkpointing = False

        def gradient_checkpointing_enable(self) -> None:
            self.is_gradient_checkpointing = True

        def generate(self) -> str:
            self.generate_states.append((self.training, self.is_gradient_checkpointing))
            return "generated"

    class FakeAccelerator:
        def __init__(self, model: FakeModel) -> None:
            self.model = model

        def unwrap_model(self, model: object) -> FakeModel:
            assert model is self.model
            return self.model

    class FakeTrainer:
        def __init__(self) -> None:
            self.model = FakeModel()
            self.model_wrapped = self.model
            self.accelerator = FakeAccelerator(self.model)
            self.args = SimpleNamespace(gradient_accumulation_steps=8)
            self.state = SimpleNamespace(global_step=0)
            self.logps_states: list[tuple[bool, bool]] = []
            self._metrics: dict[str, defaultdict[str, list[float]]] = {
                "train": defaultdict(list),
                "eval": defaultdict(list),
            }

        def _generate_and_score_completions(self, inputs: object) -> object:
            assert self.model_wrapped.generate() == "generated"
            return inputs

        def _get_per_token_logps(self, model: FakeModel) -> str:
            self.logps_states.append((torch.is_grad_enabled(), model.is_gradient_checkpointing))
            return "logps"

        def training_step(self) -> str:
            return "loss"

        def _maybe_log_save_evaluate(self) -> str:
            return "logged"

    trainer = FakeTrainer()
    times = iter([10.0, 11.0, 13.5, 14.0, 15.0, 17.0, 20.0, 24.0])
    monkeypatch.setattr("code_verifier.training.grpo.time.perf_counter", lambda: next(times))
    grpo_module._install_grpo_runtime_telemetry(trainer)
    result = trainer._generate_and_score_completions([{"prompt": "hello"}])
    assert result == [{"prompt": "hello"}]
    assert trainer.model.generate_states == [(True, False)]
    assert trainer.model.is_gradient_checkpointing is True
    assert trainer._metrics["train"]["generation_runtime_seconds"] == [pytest.approx(2.5)]
    assert trainer._metrics["train"]["rollout_runtime_seconds"] == [pytest.approx(4.0)]
    with torch.no_grad():
        assert trainer._get_per_token_logps(trainer.model) == "logps"
    assert trainer.logps_states == [(False, False)]
    assert trainer.model.is_gradient_checkpointing is True
    assert trainer.training_step() == "loss"
    trainer.state.global_step = 1
    assert trainer._maybe_log_save_evaluate() == "logged"
    assert trainer._metrics["train"]["step_runtime_seconds"] == [pytest.approx(4.0)]
    assert trainer._metrics["train"]["no_grad_logps_runtime_seconds"] == [pytest.approx(2.0)]
    assert trainer._metrics["train"]["no_grad_logps_calls"] == [1.0]
    assert "generate" not in trainer.model.__dict__


def _fake_grpo_runtime() -> _GRPORuntime:
    return _GRPORuntime(
        model_config_type=_Recorder(),
        training_config_type=_Recorder(),
        trainer_type=_FakeTrainer,
        get_peft_config=lambda _: "NEW_GRPO_LORA",
        get_tokenizer=lambda *_: "TOKENIZER",
        get_model=lambda *_: "BASE_A",
        peft_config_type=_FakePeftConfig,
        peft_model_type=_FakePeftModel,
    )


def _prepare_fake_grpo_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[GRPOTrainingConfig, GRPOTrainingConfig, Path, Path]:
    public_config = grpo_training_config_from_mapping(_config_mapping(tmp_path))
    hidden_config = grpo_training_config_from_mapping(_config_mapping(tmp_path, reward_mode="hidden"))
    _write_grpo_artifact(public_config.dataset_path)
    _write_grpo_artifact(hidden_config.dataset_path, reward_mode="hidden")
    public_config.piston_config.write_text("endpoint: fake\n", encoding="utf-8")
    sft_run_dir = tmp_path / "sft-run"
    _write_completed_sft_run(sft_run_dir)
    _FakeTrainer.instances.clear()
    _FakeTrainer.loss = 0.25
    _FakeTrainer.extra_metrics = {}
    monkeypatch.setattr(grpo_module, "validate_grpo_training_hardware", lambda _: None)
    monkeypatch.setattr(grpo_module, "_load_grpo_runtime", _fake_grpo_runtime)
    monkeypatch.setattr(grpo_module, "_reset_cuda_peak_memory", lambda: None)
    monkeypatch.setattr(grpo_module, "_peak_cuda_memory_bytes", lambda: (123, 456))
    monkeypatch.setattr(grpo_module, "_install_grpo_checkpoint_log_snapshots", lambda *args, **kwargs: None)
    return public_config, hidden_config, sft_run_dir, tmp_path / "outputs"


def _passing_results(count: int) -> list[ExecutionResult]:
    return [_execution_result(passed=True) for _ in range(count)]


def _create_fake_resume_checkpoint(run_dir: Path, *, step: int = 1) -> Path:
    checkpoint = run_dir / "checkpoints" / f"checkpoint-{step}"
    checkpoint.mkdir()
    grpo_module._write_grpo_log_checkpoint_state(run_dir=run_dir, checkpoint_dir=checkpoint, global_step=step)
    return checkpoint


def test_grpo_run_uses_merged_b_new_lora_and_writes_strict_sanitized_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    executor = MockExecutor(_passing_results(4))

    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=executor,
    )

    assert summary.reward_mode == "public"
    assert summary.train_loss == 0.25
    assert summary.train_samples == 1
    assert {path.name for path in summary.run_dir.iterdir()} == {
        "resolved_config.yaml",
        "environment.json",
        "run.json",
        "metrics.jsonl",
        "rollouts.jsonl",
        "rewards.jsonl",
        "group_metrics.jsonl",
        "stdout.log",
        "stderr.log",
        "checkpoints",
    }
    trainer = _FakeTrainer.instances[0]
    assert trainer.kwargs["model"] == "MERGED_B"
    assert trainer.kwargs["peft_config"] == "NEW_GRPO_LORA"
    assert trainer.kwargs["eval_dataset"] is None
    assert executor.calls[0].tests == [{"input": "VISIBLE_SENTINEL", "expected": "VISIBLE_SENTINEL"}]
    assert len(_read_jsonl(summary.run_dir / "rollouts.jsonl")) == 4
    assert len(_read_jsonl(summary.run_dir / "rewards.jsonl")) == 4
    metrics = _read_jsonl(summary.run_dir / "metrics.jsonl")
    assert [row["record_type"] for row in metrics] == ["trainer", "summary"]
    assert metrics[-1]["train_runtime"] == 1.5
    assert metrics[-1]["global_step"] == 1
    assert metrics[-1]["peak_cuda_memory_allocated_bytes"] == 123
    assert metrics[-1]["peak_cuda_memory_reserved_bytes"] == 456
    curve_rows = load_training_curve_rows(summary.run_dir, method="Public-RLVR")
    assert {(row.metric, row.value) for row in curve_rows} == {
        ("generation_runtime_seconds", 0.5),
        ("loss", 0.3),
        ("no_grad_logps_calls", 8.0),
        ("no_grad_logps_runtime_seconds", 0.2),
        ("rollout_runtime_seconds", 0.75),
        ("step_runtime_seconds", 1.0),
    }
    cost_row = build_cost_row(summary.run_dir, method="Public-RLVR", gpu_hour_cost_usd=None)
    assert cost_row.rollouts == 4
    assert cost_row.gpu_hours == pytest.approx(summary.gpu_hours)
    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["status"] == "completed"
    assert run_metadata["parent_sft_run_id"] == "completed-b"
    assert run_metadata["parent_sft_checkpoint_path"] == str((sft_run_dir / "checkpoints").resolve())
    assert re.fullmatch(r"[0-9a-f]{64}", run_metadata["paired_definition_sha256"])
    assert run_metadata["paired_definition_version"] == 2
    assert run_metadata["gpu_count_used"] == 1
    assert run_metadata["global_step"] == 1
    assert run_metadata["peak_cuda_memory_allocated_bytes"] == 123
    assert run_metadata["peak_cuda_memory_reserved_bytes"] == 456
    assert len(run_metadata["attempts"]) == 1
    assert run_metadata["attempts"][0]["status"] == "completed"
    assert run_metadata["gpu_hours"] == pytest.approx(run_metadata["attempts"][0]["gpu_hours"])
    for name in (
        "run.json",
        "environment.json",
        "resolved_config.yaml",
        "metrics.jsonl",
        "rewards.jsonl",
        "group_metrics.jsonl",
        "stdout.log",
        "stderr.log",
    ):
        contents = (summary.run_dir / name).read_text(encoding="utf-8")
        for forbidden in ("PRIVATE_PROMPT_SENTINEL", "VISIBLE_SENTINEL", "HIDDEN_SENTINEL"):
            assert forbidden not in contents


def test_grpo_run_keeps_unused_deepspeed_probe_disabled_through_trainer_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    active = {"value": False}

    class Guard:
        def __enter__(self) -> None:
            assert active["value"] is False
            active["value"] = True

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            active["value"] = False

    class GuardAwareTrainer(_FakeTrainer):
        def __init__(self, **kwargs: object) -> None:
            assert active["value"] is True
            super().__init__(**kwargs)

        def train(self, *, resume_from_checkpoint: str | None) -> SimpleNamespace:
            assert active["value"] is True
            return super().train(resume_from_checkpoint=resume_from_checkpoint)

        @staticmethod
        def save_state() -> None:
            assert active["value"] is True

        @staticmethod
        def save_model(path: str) -> None:
            assert active["value"] is True
            assert Path(path).name == "checkpoints"

    monkeypatch.setattr(grpo_module, "_without_unconfigured_deepspeed_backend", Guard)
    monkeypatch.setattr(
        grpo_module,
        "_load_grpo_runtime",
        lambda: replace(_fake_grpo_runtime(), trainer_type=GuardAwareTrainer),
    )

    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
    )

    assert summary.train_loss == 0.25
    assert active["value"] is False


def test_pinned_grpo_trainer_constructor_succeeds_under_plain_training_deepspeed_guard(
    tmp_path: Path,
) -> None:
    import importlib

    datasets_module = cast(Any, importlib.import_module("datasets"))
    tokenizers_module = cast(Any, importlib.import_module("tokenizers"))
    tokenizers_models = cast(Any, importlib.import_module("tokenizers.models"))
    tokenizers_pre = cast(Any, importlib.import_module("tokenizers.pre_tokenizers"))
    transformers_module = cast(Any, importlib.import_module("transformers"))
    trl_module = cast(Any, importlib.import_module("trl"))

    tokenizer_cls = getattr(tokenizers_module, "Token" + "izer")
    whitespace_cls = getattr(tokenizers_pre, "White" + "space")
    raw_tokenizer = tokenizer_cls(tokenizers_models.WordLevel({"u": 0, "p": 1, "e": 2, "hello": 3}, unk_token="u"))
    raw_tokenizer.pre_tokenizer = whitespace_cls()
    tokenizer_type = getattr(transformers_module, "PreTrained" + "TokenizerFast")
    tokenizer = tokenizer_type(
        tokenizer_object=raw_tokenizer,
        unk_token="u",
        pad_token="p",
        eos_token="e",
    )
    model = transformers_module.Qwen2ForCausalLM(
        transformers_module.Qwen2Config(
            vocab_size=4,
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=4,
            num_key_value_heads=2,
            max_position_embeddings=128,
        )
    )
    dataset = datasets_module.Dataset.from_list([{"prompt": "hello"}])

    def reward(completions: list[str], **_: object) -> list[float]:
        return [0.0 for _ in completions]

    args = trl_module.GRPOConfig(
        output_dir=str(tmp_path / "constructor"),
        do_train=True,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        max_steps=1,
        num_generations=4,
        max_prompt_length=16,
        max_completion_length=8,
        gradient_checkpointing=True,
        bf16=False,
        fp16=False,
        use_cpu=True,
        use_vllm=False,
        report_to=[],
        save_strategy="no",
    )
    assert args.generation_batch_size == 8
    assert args.steps_per_generation == 8

    guard = cast(Any, vars(grpo_module)["_without_unconfigured_deepspeed_backend"])
    with guard():
        trainer = trl_module.GRPOTrainer(
            model=model,
            reward_funcs=reward,
            args=args,
            train_dataset=dataset,
            processing_class=tokenizer,
            peft_config=None,
        )

    assert isinstance(trainer, trl_module.GRPOTrainer)


def test_pinned_grpo_runtime_and_checkpoint_hooks_compose_on_real_train(tmp_path: Path) -> None:
    import importlib

    datasets_module = cast(Any, importlib.import_module("datasets"))
    tokenizers_module = cast(Any, importlib.import_module("tokenizers"))
    tokenizers_models = cast(Any, importlib.import_module("tokenizers.models"))
    tokenizers_pre = cast(Any, importlib.import_module("tokenizers.pre_tokenizers"))
    transformers_module = cast(Any, importlib.import_module("transformers"))
    trl_module = cast(Any, importlib.import_module("trl"))

    run_dir = tmp_path / "real-hook-run"
    checkpoint_root = run_dir / "checkpoints"
    checkpoint_root.mkdir(parents=True)
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        (run_dir / name).touch()

    tokenizer_cls = getattr(tokenizers_module, "Token" + "izer")
    whitespace_cls = getattr(tokenizers_pre, "White" + "space")
    raw_tokenizer = tokenizer_cls(tokenizers_models.WordLevel({"u": 0, "p": 1, "e": 2, "hello": 3}, unk_token="u"))
    raw_tokenizer.pre_tokenizer = whitespace_cls()
    tokenizer_type = getattr(transformers_module, "PreTrained" + "TokenizerFast")
    tokenizer = tokenizer_type(
        tokenizer_object=raw_tokenizer,
        unk_token="u",
        pad_token="p",
        eos_token="e",
    )
    model = transformers_module.Qwen2ForCausalLM(
        transformers_module.Qwen2Config(
            vocab_size=4,
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=4,
            num_key_value_heads=2,
            max_position_embeddings=128,
        )
    )
    dataset = datasets_module.Dataset.from_list([{"prompt": "hello"}])

    def reward(completions: list[str], **_: object) -> list[float]:
        for name in grpo_module._GRPO_STREAM_LOG_NAMES:
            with (run_dir / name).open("a", encoding="utf-8") as handle:
                for index in range(len(completions)):
                    handle.write(json.dumps({"index": index}) + "\n")
                handle.flush()
        return [0.0 for _ in completions]

    args = trl_module.GRPOConfig(
        output_dir=str(checkpoint_root),
        do_train=True,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        max_steps=1,
        num_generations=4,
        max_prompt_length=16,
        max_completion_length=8,
        gradient_checkpointing=True,
        bf16=False,
        fp16=False,
        use_cpu=True,
        use_vllm=False,
        report_to=[],
        save_strategy="steps",
        save_steps=1,
        logging_steps=1,
    )
    guard = cast(Any, vars(grpo_module)["_without_unconfigured_deepspeed_backend"])
    with guard():
        trainer = trl_module.GRPOTrainer(
            model=model,
            reward_funcs=reward,
            args=args,
            train_dataset=dataset,
            processing_class=tokenizer,
            peft_config=None,
        )
        grpo_module._install_grpo_runtime_telemetry(trainer)
        grpo_module._install_grpo_checkpoint_log_snapshots(trainer, run_dir=run_dir)
        trainer.train()

    checkpoint = checkpoint_root / "checkpoint-1"
    state = json.loads((checkpoint / grpo_module._GRPO_LOG_STATE_FILENAME).read_text(encoding="utf-8"))
    assert state["global_step"] == 1
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        assert state["logs"][name] == grpo_module._stream_log_file_state(run_dir / name)
    assert model.is_gradient_checkpointing is True


def test_pinned_grpo_reward_exception_aborts_before_optimizer_update(tmp_path: Path) -> None:
    import importlib

    datasets_module = cast(Any, importlib.import_module("datasets"))
    tokenizers_module = cast(Any, importlib.import_module("tokenizers"))
    tokenizers_models = cast(Any, importlib.import_module("tokenizers.models"))
    tokenizers_pre = cast(Any, importlib.import_module("tokenizers.pre_tokenizers"))
    transformers_module = cast(Any, importlib.import_module("transformers"))
    trl_module = cast(Any, importlib.import_module("trl"))
    torch_module = cast(Any, importlib.import_module("torch"))

    tokenizer_cls = getattr(tokenizers_module, "Token" + "izer")
    whitespace_cls = getattr(tokenizers_pre, "White" + "space")
    raw_tokenizer = tokenizer_cls(tokenizers_models.WordLevel({"u": 0, "p": 1, "e": 2, "hello": 3}, unk_token="u"))
    raw_tokenizer.pre_tokenizer = whitespace_cls()
    tokenizer_type = getattr(transformers_module, "PreTrained" + "TokenizerFast")
    tokenizer = tokenizer_type(
        tokenizer_object=raw_tokenizer,
        unk_token="u",
        pad_token="p",
        eos_token="e",
    )
    model = transformers_module.Qwen2ForCausalLM(
        transformers_module.Qwen2Config(
            vocab_size=4,
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=4,
            num_key_value_heads=2,
            max_position_embeddings=128,
        )
    )
    before = [parameter.detach().clone() for parameter in model.parameters()]
    dataset = datasets_module.Dataset.from_list([{"prompt": "hello"}])

    def reward(*_: object, **__: object) -> list[float]:
        raise GRPOTrainingError("synthetic infrastructure failure")

    output_dir = tmp_path / "fail-before-update"
    args = trl_module.GRPOConfig(
        output_dir=str(output_dir),
        do_train=True,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        max_steps=1,
        num_generations=4,
        max_prompt_length=16,
        max_completion_length=8,
        gradient_checkpointing=True,
        bf16=False,
        fp16=False,
        use_cpu=True,
        use_vllm=False,
        report_to=[],
        save_strategy="steps",
        save_steps=1,
        logging_steps=1,
    )
    guard = cast(Any, vars(grpo_module)["_without_unconfigured_deepspeed_backend"])
    with guard():
        trainer = trl_module.GRPOTrainer(
            model=model,
            reward_funcs=reward,
            args=args,
            train_dataset=dataset,
            processing_class=tokenizer,
            peft_config=None,
        )
        with pytest.raises(GRPOTrainingError, match="synthetic infrastructure failure"):
            trainer.train()

    assert trainer.state.global_step == 0
    assert not (output_dir / "checkpoint-1").exists()
    assert all(
        torch_module.equal(previous, current.detach())
        for previous, current in zip(before, model.parameters(), strict=True)
    )


def test_grpo_run_failure_is_sanitized_and_requires_finite_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    _FakeTrainer.loss = math.nan
    with pytest.raises(GRPOTrainingError, match="finite train_loss"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=42,
            executor=MockExecutor(_passing_results(4)),
        )
    run_dir = output_root / public_config.run_name
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["status"] == "failed"
    assert run_metadata["attempts"][-1]["status"] == "failed"
    assert run_metadata["gpu_hours"] == pytest.approx(sum(item["gpu_hours"] for item in run_metadata["attempts"]))
    assert run_metadata["peak_cuda_memory_allocated_bytes"] == 123
    assert run_metadata["peak_cuda_memory_reserved_bytes"] == 456
    assert (run_dir / "stderr.log").read_text(encoding="utf-8") == "GRPOTrainingError\n"


def test_grpo_run_rejects_nonfinite_train_result_metric(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    _FakeTrainer.extra_metrics = {"train_runtime": math.inf}

    with pytest.raises(GRPOTrainingError, match="finite numeric metrics"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=42,
            executor=MockExecutor(_passing_results(4)),
        )

    run_metadata = json.loads((output_root / public_config.run_name / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["status"] == "failed"
    assert run_metadata["attempts"][-1]["status"] == "failed"


def test_grpo_public_and_hidden_runs_share_paired_definition_sha256(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)

    public_summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
    )
    hidden_summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="hidden",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
    )

    public_metadata = json.loads((public_summary.run_dir / "run.json").read_text(encoding="utf-8"))
    hidden_metadata = json.loads((hidden_summary.run_dir / "run.json").read_text(encoding="utf-8"))
    assert public_metadata["paired_definition_sha256"] == hidden_metadata["paired_definition_sha256"]
    assert public_metadata["paired_public_config_hash"] == hidden_metadata["paired_public_config_hash"]
    assert public_metadata["paired_hidden_config_hash"] == hidden_metadata["paired_hidden_config_hash"]
    assert public_metadata["paired_public_dataset_hash"] == hidden_metadata["paired_public_dataset_hash"]
    assert public_metadata["paired_hidden_dataset_hash"] == hidden_metadata["paired_hidden_dataset_hash"]


def test_grpo_paired_definition_is_portable_across_local_roots(tmp_path: Path) -> None:
    results: list[tuple[str, dict[str, object], str, str]] = []
    for root_name in ("control-plane", "target-gpu"):
        root = tmp_path / root_name
        root.mkdir()
        public = grpo_training_config_from_mapping(_config_mapping(root))
        hidden = grpo_training_config_from_mapping(_config_mapping(root, reward_mode="hidden"))
        _write_grpo_artifact(public.dataset_path)
        _write_grpo_artifact(hidden.dataset_path, reward_mode="hidden")
        public.piston_config.write_text("endpoint: fake\n", encoding="utf-8")
        sft_run = root / "sft-run"
        _write_completed_sft_run(sft_run)
        parent = load_completed_sft_checkpoint(sft_run)
        pair_sha, components = grpo_module._paired_definition(public, hidden, seed=42, parent_sft=parent)
        results.append(
            (
                pair_sha,
                components,
                grpo_module._config_hash(public, seed=42),
                grpo_module._config_hash(hidden, seed=42),
            )
        )

    first, second = results
    assert first[0] == second[0]
    assert first[1] == second[1]
    assert first[1]["paired_definition_version"] == 2
    assert first[2] != second[2]
    assert first[3] != second[3]


def test_grpo_checkpoint_snapshot_binds_stream_logs_after_trainer_save(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    checkpoint_root = run_dir / "checkpoints"
    checkpoint_root.mkdir(parents=True)
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        (run_dir / name).write_text('{"row":1}\n', encoding="utf-8")

    class FakeTrainer:
        def __init__(self) -> None:
            self.args = SimpleNamespace(output_dir=str(checkpoint_root))
            self.state = SimpleNamespace(global_step=10)

        def _save_checkpoint(self, model: object, trial: object) -> None:
            del model, trial
            (checkpoint_root / "checkpoint-10").mkdir()

    trainer = FakeTrainer()
    grpo_module._install_grpo_checkpoint_log_snapshots(trainer, run_dir=run_dir)
    trainer._save_checkpoint(None, None)

    state_path = checkpoint_root / "checkpoint-10" / grpo_module._GRPO_LOG_STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["version"] == 1
    assert state["global_step"] == 10
    assert set(state["logs"]) == set(grpo_module._GRPO_STREAM_LOG_NAMES)
    assert all(item["line_count"] == 1 for item in state["logs"].values())


def test_grpo_resume_archives_failed_suffix_and_restores_checkpoint_prefix(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    checkpoint = run_dir / "checkpoints" / "checkpoint-30"
    checkpoint.mkdir(parents=True)
    prefix_bytes: dict[str, bytes] = {}
    failed_bytes: dict[str, bytes] = {}
    for index, name in enumerate(grpo_module._GRPO_STREAM_LOG_NAMES, 1):
        path = run_dir / name
        path.write_text(f'{{"step":30,"kind":{index}}}\n', encoding="utf-8")
        prefix_bytes[name] = path.read_bytes()
    grpo_module._write_grpo_log_checkpoint_state(run_dir=run_dir, checkpoint_dir=checkpoint, global_step=30)
    for index, name in enumerate(grpo_module._GRPO_STREAM_LOG_NAMES, 1):
        path = run_dir / name
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f'{{"step":31,"failed":{index}}}\n')
        failed_bytes[name] = path.read_bytes()
    future_checkpoint = run_dir / "checkpoints" / "checkpoint-40"
    future_checkpoint.mkdir()
    (future_checkpoint / "partial-state.bin").write_bytes(b"preserve-me")

    archive = grpo_module._archive_and_restore_grpo_logs(
        run_dir=run_dir,
        checkpoint_dir=checkpoint,
        attempt_number=2,
    )

    assert archive.parent == run_dir / "checkpoints" / grpo_module._GRPO_RECOVERY_HISTORY_DIR
    assert archive.name == "before-attempt-2-resume-checkpoint-30"
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["attempt"] == 2
    assert manifest["global_step"] == 30
    assert manifest["superseded_future_checkpoints"] == ["checkpoint-40"]
    assert not future_checkpoint.exists()
    assert (
        archive / "superseded-future-checkpoints" / "checkpoint-40" / "partial-state.bin"
    ).read_bytes() == b"preserve-me"
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        assert (run_dir / name).read_bytes() == prefix_bytes[name]
        assert (archive / name).read_bytes() == failed_bytes[name]

    second_failed_bytes: dict[str, bytes] = {}
    for index, name in enumerate(grpo_module._GRPO_STREAM_LOG_NAMES, 1):
        path = run_dir / name
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f'{{"step":31,"second_failed":{index}}}\n')
        second_failed_bytes[name] = path.read_bytes()
    second_archive = grpo_module._archive_and_restore_grpo_logs(
        run_dir=run_dir,
        checkpoint_dir=checkpoint,
        attempt_number=3,
    )
    assert second_archive.name == "before-attempt-3-resume-checkpoint-30"
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        assert (run_dir / name).read_bytes() == prefix_bytes[name]
        assert (second_archive / name).read_bytes() == second_failed_bytes[name]
    history = run_dir / "checkpoints" / grpo_module._GRPO_RECOVERY_HISTORY_DIR
    assert sorted(path.name for path in history.iterdir()) == [
        "before-attempt-2-resume-checkpoint-30",
        "before-attempt-3-resume-checkpoint-30",
    ]
    assert not any(path.name.startswith(".") and ".resume-" in path.name for path in history.iterdir())


def test_grpo_resume_rejects_checkpoint_without_log_boundary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    checkpoint = run_dir / "checkpoints" / "checkpoint-10"
    checkpoint.mkdir(parents=True)
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        (run_dir / name).write_text('{"row":1}\n', encoding="utf-8")
    with pytest.raises(GRPOTrainingError, match="missing canonical GRPO log-state"):
        grpo_module._validate_resume_log_checkpoint(run_dir, checkpoint)


def test_grpo_resume_is_bound_and_appends_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=7,
        executor=MockExecutor(_passing_results(4)),
    )
    checkpoint = _create_fake_resume_checkpoint(summary.run_dir)
    failed_attempt_logs: dict[str, bytes] = {}
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        path = summary.run_dir / name
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"failed_attempt_suffix":true}\n')
        failed_attempt_logs[name] = path.read_bytes()
    metadata_value = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    metadata_value["status"] = "failed"
    metadata_value["gpu_hours"] = 1.25
    metadata_value["attempts"][-1]["gpu_hours"] = 1.25
    (summary.run_dir / "run.json").write_text(json.dumps(metadata_value), encoding="utf-8")

    resumed = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=7,
        executor=MockExecutor(_passing_results(4)),
        resume_from_checkpoint=checkpoint,
    )

    assert _FakeTrainer.instances[-1].resume_from_checkpoint == str(checkpoint.resolve())
    resumed_metadata = json.loads((resumed.run_dir / "run.json").read_text(encoding="utf-8"))
    assert resumed_metadata["resume_from_checkpoint"] == "checkpoints/checkpoint-1"
    assert resumed_metadata["gpu_hours"] > 1.25
    assert len(resumed_metadata["attempts"]) == 2
    assert resumed_metadata["gpu_hours"] == pytest.approx(
        sum(item["gpu_hours"] for item in resumed_metadata["attempts"])
    )
    assert len(_read_jsonl(resumed.run_dir / "rollouts.jsonl")) == 8
    assert len(_read_jsonl(resumed.run_dir / "metrics.jsonl")) == 2
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        assert b"failed_attempt_suffix" not in (resumed.run_dir / name).read_bytes()
    archive = (
        resumed.run_dir
        / "checkpoints"
        / grpo_module._GRPO_RECOVERY_HISTORY_DIR
        / "before-attempt-2-resume-checkpoint-1"
    )
    assert archive.is_dir()
    for name in grpo_module._GRPO_STREAM_LOG_NAMES:
        assert (archive / name).read_bytes() == failed_attempt_logs[name]


def test_grpo_resume_validation_is_read_only_until_attempt_begin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
    )
    checkpoint = _create_fake_resume_checkpoint(summary.run_dir)
    metadata_value = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    metadata_value["status"] = "failed"
    metadata_value["end_time"] = "preserved-end-time"
    metadata_value["resume_from_checkpoint"] = None
    metadata_value["gpu_hours"] = 1.25
    metadata_value["attempts"][-1]["status"] = "failed"
    metadata_value["attempts"][-1]["end_time"] = "preserved-attempt-end-time"
    metadata_value["attempts"][-1]["gpu_hours"] = 1.25
    before_text = json.dumps(metadata_value, sort_keys=True, indent=2) + "\n"
    (summary.run_dir / "run.json").write_text(before_text, encoding="utf-8")

    def stop_before_attempt(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise GRPOTrainingError("stop before attempt begin")

    monkeypatch.setattr(grpo_module, "_begin_attempt", stop_before_attempt)
    with pytest.raises(GRPOTrainingError, match="stop before attempt begin"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=42,
            executor=MockExecutor(_passing_results(4)),
            resume_from_checkpoint=checkpoint,
        )

    assert (summary.run_dir / "run.json").read_text(encoding="utf-8") == before_text


@pytest.mark.parametrize("drift", ["seed", "config", "dataset", "dependency", "parent"])
def test_grpo_resume_rejects_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
    )
    checkpoint = _create_fake_resume_checkpoint(summary.run_dir)
    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    run_metadata["status"] = "failed"
    if drift == "dependency":
        run_metadata["dependency_lock_hash"] = "0" * 64
    (summary.run_dir / "run.json").write_text(json.dumps(run_metadata), encoding="utf-8")
    seed = 7 if drift == "seed" else 42
    if drift == "config":
        public_config = replace(public_config, temperature=0.7)
        hidden_config = replace(hidden_config, temperature=0.7)
    if drift == "dataset":
        _write_grpo_artifact(public_config.dataset_path, sentinel="CHANGED_VISIBLE")
        _write_grpo_artifact(hidden_config.dataset_path, reward_mode="hidden", sentinel="CHANGED_VISIBLE")
    if drift == "parent":
        sft_metadata = json.loads((sft_run_dir / "run.json").read_text(encoding="utf-8"))
        sft_metadata["dataset_hash"] = "e" * 64
        (sft_run_dir / "run.json").write_text(json.dumps(sft_metadata), encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="identity"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=seed,
            executor=MockExecutor(_passing_results(4)),
            resume_from_checkpoint=checkpoint,
        )


def test_grpo_resume_rejects_counterpart_only_dataset_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
    )
    checkpoint = _create_fake_resume_checkpoint(summary.run_dir)
    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    run_metadata["status"] = "failed"
    (summary.run_dir / "run.json").write_text(json.dumps(run_metadata), encoding="utf-8")

    hidden_record = json.loads(hidden_config.dataset_path.read_text(encoding="utf-8"))
    hidden_record["train_hidden_tests"] = [{"input": "COUNTERPART_DRIFT", "expected": "COUNTERPART_DRIFT"}]
    hidden_config.dataset_path.write_text(json.dumps(hidden_record) + "\n", encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="identity"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=42,
            executor=MockExecutor(_passing_results(4)),
            resume_from_checkpoint=checkpoint,
        )


def test_grpo_hardware_guard_runs_before_parent_or_model_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config = grpo_training_config_from_mapping(_config_mapping(tmp_path))
    hidden_config = grpo_training_config_from_mapping(_config_mapping(tmp_path, reward_mode="hidden"))
    parent_loaded = False

    def fail_hardware(value: object) -> None:
        assert value == public_config
        raise GRPOTrainingError("hardware blocked")

    def load_parent(path: Path) -> object:
        nonlocal parent_loaded
        parent_loaded = True
        return path

    monkeypatch.setattr(grpo_module, "validate_grpo_training_hardware", fail_hardware)
    monkeypatch.setattr(grpo_module, "load_completed_sft_checkpoint", load_parent)
    with pytest.raises(GRPOTrainingError, match="hardware blocked"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=tmp_path / "sft",
            hidden_sft_run_dir=tmp_path / "sft",
            output_root=tmp_path / "outputs",
            seed=42,
            executor=MockExecutor([]),
        )
    assert parent_loaded is False
