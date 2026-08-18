"""Tests for strict LoRA SFT configuration, runtime mapping, and artifacts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
import yaml

import code_verifier.training.sft as sft_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.sft import (
    SFTCheckpointIdentity,
    SFTTrainingConfig,
    SFTTrainingError,
    _load_sft_runtime,
    _runtime_arguments,
    _SFTRuntime,
    load_completed_sft_checkpoint,
    load_sft_training_config,
    run_sft_training,
    sft_training_config_from_mapping,
    validate_sft_training_hardware,
)


def _write_completed_sft_run(run_dir: Path) -> None:
    run_dir.mkdir()
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    metadata = {
        "status": "completed",
        "run_id": "completed-run",
        "model_id": "example/model",
        "model_revision": "a" * 40,
        "dataset_hash": "b" * 64,
        "config_hash": "c" * 64,
        "dependency_lock_hash": "d" * 64,
        "seed": 42,
    }
    (run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (checkpoint_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "example/model", "peft_type": "LORA"}),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_model.safetensors").write_bytes(b"fixture-adapter")
    for name in ("resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log"):
        (run_dir / name).touch()


def test_load_completed_sft_checkpoint_accepts_completed_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "completed-run"
    _write_completed_sft_run(run_dir)

    identity = load_completed_sft_checkpoint(run_dir)

    assert identity == SFTCheckpointIdentity(
        run_dir=run_dir.resolve(),
        checkpoint_dir=(run_dir / "checkpoints").resolve(),
        run_id="completed-run",
        model_id="example/model",
        model_revision="a" * 40,
        dataset_hash="b" * 64,
        config_hash="c" * 64,
        dependency_lock_hash="d" * 64,
        seed=42,
    )


def test_load_completed_sft_checkpoint_rejects_non_completed_status(tmp_path: Path) -> None:
    run_dir = tmp_path / "incomplete-run"
    _write_completed_sft_run(run_dir)
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    metadata["status"] = "running"
    (run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(SFTTrainingError, match="completed run"):
        load_completed_sft_checkpoint(run_dir)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", ""),
        ("model_id", None),
        ("model_revision", ""),
        ("dataset_hash", "not-a-hash"),
        ("config_hash", None),
        ("dependency_lock_hash", "e" * 63),
        ("seed", True),
    ],
)
def test_load_completed_sft_checkpoint_rejects_missing_or_invalid_identity(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    run_dir = tmp_path / "invalid-identity"
    _write_completed_sft_run(run_dir)
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    metadata[field] = value
    (run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(SFTTrainingError, match=field):
        load_completed_sft_checkpoint(run_dir)


@pytest.mark.parametrize("artifact", ["adapter_config.json", "adapter_model.safetensors"])
def test_load_completed_sft_checkpoint_rejects_missing_or_invalid_adapter_artifact(
    tmp_path: Path,
    artifact: str,
) -> None:
    run_dir = tmp_path / "invalid-adapter"
    _write_completed_sft_run(run_dir)
    (run_dir / "checkpoints" / artifact).unlink()

    with pytest.raises(SFTTrainingError, match="PEFT adapter"):
        load_completed_sft_checkpoint(run_dir)


def test_load_completed_sft_checkpoint_binds_checkpoint_to_same_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "escaped-checkpoint"
    _write_completed_sft_run(run_dir)
    external_checkpoint = tmp_path / "external-checkpoint"
    (run_dir / "checkpoints").rename(external_checkpoint)
    (run_dir / "checkpoints").symlink_to(external_checkpoint, target_is_directory=True)

    with pytest.raises(SFTTrainingError, match="directly"):
        load_completed_sft_checkpoint(run_dir)


def _config_mapping(tmp_path: Path) -> dict[str, object]:
    return {
        "run_name": "unit-run",
        "model_id": "example/model",
        "model_revision": "a" * 40,
        "dataset_path": str(tmp_path / "sft.jsonl"),
        "validation_dataset_path": None,
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
        ("min_cuda_memory_gb", 19.9),
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
    assert config.max_seq_length == 1536
    assert config.logging_steps == 1
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
    assert config.eval_strategy == "steps"
    assert config.eval_steps == 100
    assert config.validation_dataset_path == Path.cwd() / "data/processed/wp1-smoke/training/sft_validation.jsonl"


def test_validation_smoke_uses_formal_model_revision_bf16_and_two_steps() -> None:
    main = load_sft_training_config(Path("configs/sft/main.yaml"))
    smoke = load_sft_training_config(Path("configs/sft/validation-smoke.yaml"))

    assert smoke.model_id == main.model_id
    assert smoke.model_revision == main.model_revision
    assert smoke.max_seq_length == main.max_seq_length == 1536
    assert smoke.learning_rate == main.learning_rate
    assert (smoke.lora_r, smoke.lora_alpha, smoke.lora_dropout) == (
        main.lora_r,
        main.lora_alpha,
        main.lora_dropout,
    )
    assert smoke.bf16 is True and smoke.fp16 is False
    assert smoke.max_steps == 2
    assert smoke.logging_steps == 1
    assert smoke.save_steps == 1
    assert smoke.eval_strategy == "no"
    assert smoke.validation_dataset_path is None


def test_eval_strategy_requires_exactly_one_validation_artifact_mode(tmp_path: Path) -> None:
    mapping = _config_mapping(tmp_path)
    mapping["eval_strategy"] = "steps"
    mapping["eval_steps"] = 1
    with pytest.raises(SFTTrainingError, match="validation_dataset_path"):
        sft_training_config_from_mapping(mapping)

    mapping = _config_mapping(tmp_path)
    mapping["validation_dataset_path"] = str(tmp_path / "validation.jsonl")
    with pytest.raises(SFTTrainingError, match="validation_dataset_path"):
        sft_training_config_from_mapping(mapping)


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

    lowered_config = replace(_config(tmp_path), min_cuda_memory_gb=1.0)
    with pytest.raises(SFTTrainingError, match="at least 20"):
        validate_sft_training_hardware(lowered_config)


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
    assert kwargs["skip_memory_metrics"] is False
    assert kwargs["include_num_input_tokens_seen"] is True
    assert kwargs["logging_nan_inf_filter"] is False
    assert kwargs["save_total_limit"] is None
    assert kwargs["save_only_model"] is False
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
        self.state = SimpleNamespace(
            global_step=1,
            log_history=[
                {
                    "loss": 0.3,
                    "grad_norm": 0.5,
                    "learning_rate": 0.0002,
                    "epoch": 0.5,
                    "step": 1,
                    "ignored": "text",
                }
            ],
        )
        self.__class__.instances.append(self)

    def train(self, *, resume_from_checkpoint: str | None) -> SimpleNamespace:
        self.resume_from_checkpoint = resume_from_checkpoint
        return SimpleNamespace(metrics={"train_loss": self.loss, "train_runtime": 2.0, "num_input_tokens_seen": 128})

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


def _write_artifact(
    path: Path,
    *,
    problem_id: str = "unit-1",
    prompt: str = "PRIVATE_PROMPT_SENTINEL",
    visible_value: int = 1,
) -> None:
    record = {
        "problem_id": problem_id,
        "prompt": prompt,
        "function_name": "solve",
        "visible_tests": [{"input": visible_value, "expected": visible_value}],
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
    monkeypatch.setattr(
        sft_module,
        "collect_environment",
        lambda: {
            "project_commit": "1" * 40,
            "open_r1_commit": "2" * 40,
            "python_version": "3.10.0",
            "packages": {"torch": "2.6.0"},
            "cuda_version": "12.4",
            "gpu_name": "fixture-gpu",
            "gpu_count": 1,
            "dependency_lock_hash": "3" * 64,
        },
    )
    monkeypatch.setattr(sft_module, "_reset_cuda_peak_memory", lambda: None)
    monkeypatch.setattr(sft_module, "_peak_cuda_memory_bytes", lambda: (1234, 5678))
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
    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["status"] == "completed"
    assert run_metadata["gpu_count_used"] == 1
    assert "attempt wall time" in run_metadata["gpu_hours_semantics"]
    assert len(run_metadata["attempts"]) == 1
    assert run_metadata["attempts"][0]["status"] == "completed"

    invalid_root = tmp_path / "invalid"
    invalid_config = replace(config, run_name="invalid-loss")
    _FakeTrainer.loss = math.nan
    with pytest.raises(SFTTrainingError, match="finite numeric metrics"):
        run_sft_training(
            invalid_config,
            output_root=invalid_root,
            seed=42,
            executor=MockExecutor([_execution_result()]),
        )
    invalid_run = invalid_root / "invalid-loss"
    assert json.loads((invalid_run / "run.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_eval_strategy_steps_builds_independent_payload_minimal_validation_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, output_root = _prepare_fake_run(tmp_path, monkeypatch)
    validation_path = tmp_path / "sft-validation.jsonl"
    _write_artifact(
        validation_path,
        problem_id="validation-1",
        prompt="VALIDATION_PROMPT_SENTINEL",
        visible_value=2,
    )
    config = replace(
        config,
        validation_dataset_path=validation_path,
        eval_strategy="steps",
        eval_steps=1,
    )
    summary = run_sft_training(
        config,
        output_root=output_root,
        seed=42,
        executor=MockExecutor([_execution_result(), _execution_result()]),
    )

    trainer = _FakeTrainer.instances[0]
    train_dataset = cast(Any, trainer.kwargs["train_dataset"])
    eval_dataset = cast(Any, trainer.kwargs["eval_dataset"])
    assert train_dataset.column_names == ["prompt", "completion"]
    assert eval_dataset.column_names == ["prompt", "completion"]
    assert len(train_dataset) == 1
    assert len(eval_dataset) == 1
    assert "VALIDATION_PROMPT_SENTINEL" not in repr(train_dataset[0])
    assert "PRIVATE_PROMPT_SENTINEL" not in repr(eval_dataset[0])
    for forbidden in ("visible_tests", "function_name", "metadata"):
        assert forbidden not in repr(eval_dataset[0])
    metrics = [json.loads(line) for line in (summary.run_dir / "metrics.jsonl").read_text().splitlines()]
    assert metrics[-1]["eval_samples"] == 1


def test_run_sft_training_persists_finite_trainer_curve_metrics(
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

    metrics = [json.loads(line) for line in (summary.run_dir / "metrics.jsonl").read_text().splitlines()]
    assert metrics[0] == {
        "epoch": 0.5,
        "grad_norm": 0.5,
        "learning_rate": 0.0002,
        "loss": 0.3,
        "record_type": "trainer",
        "step": 1.0,
    }
    assert metrics[1]["record_type"] == "summary"
    assert metrics[1]["train_loss"] == 0.25
    assert metrics[1]["train_runtime"] == 2.0
    assert metrics[1]["num_input_tokens_seen"] == 128.0
    assert metrics[1]["global_step"] == 1
    assert metrics[1]["peak_cuda_memory_allocated_bytes"] == 1234
    assert metrics[1]["peak_cuda_memory_reserved_bytes"] == 5678
    assert metrics[1]["gpu_count_used"] == 1
    assert metrics[1]["train_samples"] == 1


def test_sft_trainer_metrics_reject_non_finite_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, output_root = _prepare_fake_run(tmp_path, monkeypatch)
    original_init = _FakeTrainer.__init__

    def init_with_non_finite(self: _FakeTrainer, **kwargs: object) -> None:
        original_init(self, **kwargs)
        self.state = SimpleNamespace(log_history=[{"loss": math.nan}])

    monkeypatch.setattr(_FakeTrainer, "__init__", init_with_non_finite)

    with pytest.raises(SFTTrainingError, match="trainer metrics must be finite"):
        run_sft_training(
            config,
            output_root=output_root,
            seed=42,
            executor=MockExecutor([_execution_result()]),
        )


def test_resume_rejects_fresh_run_external_and_cross_run_checkpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, output_root = _prepare_fake_run(tmp_path, monkeypatch)
    external_checkpoint = tmp_path / "checkpoint-1"
    external_checkpoint.mkdir()
    with pytest.raises(SFTTrainingError, match="existing SFT run"):
        run_sft_training(
            config,
            output_root=output_root,
            seed=42,
            executor=MockExecutor([_execution_result()]),
            resume_from_checkpoint=external_checkpoint,
        )

    summary = run_sft_training(
        config,
        output_root=output_root,
        seed=42,
        executor=MockExecutor([_execution_result()]),
    )
    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    run_metadata["status"] = "failed"
    (summary.run_dir / "run.json").write_text(json.dumps(run_metadata), encoding="utf-8")
    other_checkpoint = tmp_path / "other-run" / "checkpoints" / "checkpoint-1"
    other_checkpoint.mkdir(parents=True)
    with pytest.raises(SFTTrainingError, match="same SFT run"):
        run_sft_training(
            config,
            output_root=output_root,
            seed=42,
            executor=MockExecutor([_execution_result()]),
            resume_from_checkpoint=other_checkpoint,
        )


def test_resume_is_provenance_bound_records_source_and_accumulates_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, output_root = _prepare_fake_run(tmp_path, monkeypatch)
    summary = run_sft_training(
        config,
        output_root=output_root,
        seed=7,
        executor=MockExecutor([_execution_result()]),
    )
    checkpoint = summary.checkpoint_dir / "checkpoint-1"
    checkpoint.mkdir()
    run_metadata = cast(dict[str, object], json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8")))
    run_metadata["status"] = "failed"
    run_metadata["gpu_hours"] = 1.25
    (summary.run_dir / "run.json").write_text(json.dumps(run_metadata), encoding="utf-8")

    resumed = run_sft_training(
        config,
        output_root=output_root,
        seed=7,
        executor=MockExecutor([_execution_result()]),
        resume_from_checkpoint=checkpoint,
    )

    trainer = _FakeTrainer.instances[-1]
    assert trainer.resume_from_checkpoint == str(checkpoint.resolve())
    run_metadata = cast(dict[str, object], json.loads((resumed.run_dir / "run.json").read_text(encoding="utf-8")))
    assert run_metadata["run_id"] == config.run_name
    assert run_metadata["seed"] == 7
    assert run_metadata["seed_override"] == {"config": 42, "cli": 7}
    assert run_metadata["resume_from_checkpoint"] == "checkpoints/checkpoint-1"
    assert cast(float, run_metadata["gpu_hours"]) > 1.25
    resolved_config = cast(
        dict[str, object],
        yaml.safe_load((resumed.run_dir / "resolved_config.yaml").read_text(encoding="utf-8")),
    )
    assert resolved_config["seed"] == 7
    assert "effective_seed" not in resolved_config


def test_resume_rejects_repository_provenance_drift(
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
    checkpoint = summary.checkpoint_dir / "checkpoint-1"
    checkpoint.mkdir()
    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    run_metadata["status"] = "failed"
    run_metadata["git_commit"] = "0" * 40
    (summary.run_dir / "run.json").write_text(json.dumps(run_metadata), encoding="utf-8")

    with pytest.raises(SFTTrainingError, match="identity"):
        run_sft_training(
            config,
            output_root=output_root,
            seed=42,
            executor=MockExecutor([_execution_result()]),
            resume_from_checkpoint=checkpoint,
        )
