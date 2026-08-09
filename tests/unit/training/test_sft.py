"""Tests for strict LoRA SFT configuration, runtime mapping, and artifacts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar, cast

import pytest

import code_verifier.training.sft as sft_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.sft import (
    SFTTrainingConfig,
    SFTTrainingError,
    _load_sft_runtime,
    _runtime_arguments,
    _SFTRuntime,
    load_sft_training_config,
    run_sft_training,
    sft_training_config_from_mapping,
    validate_sft_training_hardware,
)


def _config_mapping(tmp_path: Path) -> dict[str, object]:
    return {
        "run_name": "unit-run",
        "model_id": "example/model",
        "model_revision": "a" * 40,
        "dataset_path": str(tmp_path / "sft.jsonl"),
        "piston_config": str(tmp_path / "piston.yaml"),
        "max_seq_length": 128,
        "max_steps": 2,
        "num_train_epochs": 1.0,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 2,
        "learning_rate": 0.0002,
        "warmup_ratio": 0.05,
        "lr_scheduler_type": "cosine",
        "logging_steps": 1,
        "save_strategy": "steps",
        "save_steps": 1,
        "eval_strategy": "no",
        "eval_steps": None,
        "bf16": False,
        "fp16": True,
        "gradient_checkpointing": True,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "seed": 42,
        "min_cuda_memory_gb": 20.0,
    }


def _config(tmp_path: Path) -> SFTTrainingConfig:
    return sft_training_config_from_mapping(_config_mapping(tmp_path))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_name", "../escape"),
        ("bf16", True),
        ("fp16", False),
        ("gradient_checkpointing", False),
        ("max_seq_length", 0),
        ("max_steps", 0),
        ("learning_rate", math.nan),
        ("lora_r", 0),
        ("lora_dropout", 1.0),
        ("lr_scheduler_type", "linear"),
    ],
)
def test_load_sft_training_config_rejects_unknown_and_unsafe_values(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    mapping = _config_mapping(tmp_path)
    mapping[field] = value
    if field == "bf16":
        mapping["fp16"] = True
    with pytest.raises(SFTTrainingError):
        sft_training_config_from_mapping(mapping)

    mapping = _config_mapping(tmp_path)
    mapping["unknown"] = True
    with pytest.raises(SFTTrainingError, match="unknown"):
        sft_training_config_from_mapping(mapping)


def test_main_config_matches_spec_lora_defaults_and_frozen_revision() -> None:
    config = load_sft_training_config(Path("configs/sft/main.yaml"))

    assert config.model_id == "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    assert config.model_revision is not None
    assert re.fullmatch(r"[0-9a-f]{40}", config.model_revision)
    assert config.max_seq_length == 1024
    assert config.num_train_epochs == 2.0
    assert config.per_device_train_batch_size == 1
    assert config.gradient_accumulation_steps == 16
    assert config.learning_rate == 0.0002
    assert config.lora_r == 16
    assert config.lora_alpha == 32
    assert config.lora_dropout == 0.05
    assert config.bf16 is True
    assert config.fp16 is False
    assert config.gradient_checkpointing is True


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


def test_hardware_guard_rejects_six_gb_gpu_before_model_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sft_module,
        "_load_torch_runtime",
        lambda: SimpleNamespace(cuda=_FakeCuda(memory_gb=6.0, bf16=False)),
    )
    with pytest.raises(SFTTrainingError, match="at least 20"):
        validate_sft_training_hardware(_config(tmp_path))


def test_hardware_guard_accepts_mock_24gb_bf16_gpu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(_config(tmp_path), bf16=True, fp16=False)
    monkeypatch.setattr(
        sft_module,
        "_load_torch_runtime",
        lambda: SimpleNamespace(cuda=_FakeCuda(memory_gb=24.0, bf16=True)),
    )
    validate_sft_training_hardware(config)


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(dict(kwargs))
        return SimpleNamespace(**kwargs)


def _argument_runtime() -> tuple[_SFTRuntime, _Recorder, _Recorder]:
    model_config = _Recorder()
    training_config = _Recorder()
    runtime = _SFTRuntime(
        model_config_type=model_config,
        training_config_type=training_config,
        trainer_type=object,
        get_peft_config=lambda _: object(),
        get_tokenizer=lambda *_: object(),
        get_model=lambda *_: object(),
    )
    return runtime, model_config, training_config


def test_runtime_maps_project_max_seq_length_to_trl_max_length(tmp_path: Path) -> None:
    runtime, _, training_config = _argument_runtime()
    _runtime_arguments(
        _config(tmp_path),
        checkpoint_dir=tmp_path / "checkpoints",
        seed=7,
        runtime=runtime,
    )

    kwargs = training_config.calls[0]
    assert kwargs["max_length"] == 128
    assert "max_seq_length" not in kwargs
    assert kwargs["report_to"] == []
    assert kwargs["seed"] == 7


def test_runtime_uses_lora_without_quantization_or_remote_code(tmp_path: Path) -> None:
    runtime, model_config, _ = _argument_runtime()
    _runtime_arguments(
        _config(tmp_path),
        checkpoint_dir=tmp_path / "checkpoints",
        seed=42,
        runtime=runtime,
    )

    kwargs = model_config.calls[0]
    assert kwargs["use_peft"] is True
    assert kwargs["trust_remote_code"] is False
    assert kwargs["load_in_4bit"] is False
    assert kwargs["load_in_8bit"] is False
    assert kwargs["lora_target_modules"] is None
    assert kwargs["lora_r"] == 16


def test_pinned_sft_runtime_contract() -> None:
    runtime = _load_sft_runtime()
    for symbol in (
        runtime.model_config_type,
        runtime.training_config_type,
        runtime.trainer_type,
        runtime.get_peft_config,
        runtime.get_tokenizer,
        runtime.get_model,
    ):
        assert callable(symbol)


class _FakeTokenizer:
    chat_template = "fake-template"

    @staticmethod
    def apply_chat_template(
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> list[int]:
        assert messages
        assert tokenize is True
        assert add_generation_prompt is False
        return [1, 2, 3]


class _FakeTrainer:
    loss = 0.25
    instances: ClassVar[list[_FakeTrainer]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = dict(kwargs)
        self.resume_from_checkpoint: str | None = None
        self.state_saved = False
        self.model_saved_to: str | None = None
        self.__class__.instances.append(self)

    def train(self, *, resume_from_checkpoint: str | None) -> SimpleNamespace:
        self.resume_from_checkpoint = resume_from_checkpoint
        return SimpleNamespace(metrics={"train_loss": self.loss})

    def save_state(self) -> None:
        self.state_saved = True

    def save_model(self, path: str) -> None:
        self.model_saved_to = path


def _fake_runtime() -> _SFTRuntime:
    return _SFTRuntime(
        model_config_type=_Recorder(),
        training_config_type=_Recorder(),
        trainer_type=_FakeTrainer,
        get_peft_config=lambda _: "PEFT_CONFIG",
        get_tokenizer=lambda *_: _FakeTokenizer(),
        get_model=lambda *_: "MODEL",
    )


def _execution_result() -> ExecutionResult:
    return ExecutionResult(
        status=ExecutionStatus.PASSED,
        passed_tests=1,
        total_tests=1,
        pass_rate=1.0,
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(
                status=ExecutionStatus.PASSED,
                passed=True,
                runtime_ms=1.0,
                stdout="",
                stderr="",
            )
        ],
    )


def _write_artifact(path: Path) -> None:
    record = {
        "problem_id": "unit-1",
        "prompt": "PRIVATE_PROMPT_SENTINEL",
        "function_name": "solve",
        "visible_tests": [{"input": 1, "expected": 1}],
        "sft_response": "def solve(value):\n    return value",
        "metadata": {
            "difficulty": "easy",
            "category": ["unit"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "test",
            "source_url_hash": None,
        },
    }
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")


def _prepare_fake_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    loss: float = 0.25,
) -> tuple[SFTTrainingConfig, Path]:
    config = _config(tmp_path)
    _write_artifact(config.dataset_path)
    config.piston_config.write_text("endpoint: fake\n", encoding="utf-8")
    _FakeTrainer.instances.clear()
    _FakeTrainer.loss = loss
    monkeypatch.setattr(sft_module, "validate_sft_training_hardware", lambda _: None)
    monkeypatch.setattr(sft_module, "_load_sft_runtime", _fake_runtime)
    return config, tmp_path / "outputs"


def test_run_artifacts_are_payload_free_and_loss_must_be_finite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, output_root = _prepare_fake_run(tmp_path, monkeypatch)
    summary = run_sft_training(
        config,
        output_root=output_root,
        seed=42,
        executor=MockExecutor([_execution_result()]),
    )

    assert summary.train_loss == 0.25
    assert summary.train_samples == 1
    assert summary.checkpoint_dir == summary.run_dir / "checkpoints"
    assert {path.name for path in summary.run_dir.iterdir()} == {
        "resolved_config.yaml",
        "environment.json",
        "run.json",
        "metrics.jsonl",
        "stdout.log",
        "stderr.log",
        "checkpoints",
    }
    trainer = _FakeTrainer.instances[0]
    assert trainer.kwargs["eval_dataset"] is None
    assert trainer.kwargs["peft_config"] == "PEFT_CONFIG"
    assert trainer.state_saved is True
    assert trainer.model_saved_to == str(summary.checkpoint_dir)
    for artifact in summary.run_dir.iterdir():
        if artifact.is_file():
            assert "PRIVATE_PROMPT_SENTINEL" not in artifact.read_text(encoding="utf-8")
    assert json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "completed"

    invalid_root = tmp_path / "invalid"
    invalid_config = replace(config, run_name="invalid-loss")
    _FakeTrainer.loss = math.nan
    with pytest.raises(SFTTrainingError, match="finite train_loss"):
        run_sft_training(
            invalid_config,
            output_root=invalid_root,
            seed=42,
            executor=MockExecutor([_execution_result()]),
        )
    invalid_run = invalid_root / "invalid-loss"
    assert json.loads((invalid_run / "run.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_resume_path_is_forwarded_without_changing_run_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, output_root = _prepare_fake_run(tmp_path, monkeypatch)
    checkpoint = tmp_path / "source-checkpoint"
    checkpoint.mkdir()
    summary = run_sft_training(
        config,
        output_root=output_root,
        seed=7,
        executor=MockExecutor([_execution_result()]),
        resume_from_checkpoint=checkpoint,
    )

    trainer = _FakeTrainer.instances[0]
    assert trainer.resume_from_checkpoint == str(checkpoint.resolve())
    run_metadata = cast(dict[str, object], json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8")))
    assert run_metadata["run_id"] == config.run_name
    assert run_metadata["seed"] == 7
