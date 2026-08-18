"""Non-training end-to-end integration coverage for WP6-a SFT."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

import code_verifier.training.sft as sft_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.sft import (
    SFTTrainingConfig,
    _SFTRuntime,
    run_sft_training,
    sft_training_config_from_mapping,
)


class _Tokenizer:
    chat_template = "fake-template"
    calls: ClassVar[list[list[dict[str, str]]]] = []

    @classmethod
    def apply_chat_template(
        cls,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> list[int]:
        assert tokenize is True
        assert add_generation_prompt is False
        cls.calls.append(messages)
        return [1, 2, 3, 4]


class _Trainer:
    instances: ClassVar[list[_Trainer]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = dict(kwargs)
        self.state = SimpleNamespace(global_step=1, log_history=[{"loss": 0.125, "step": 1}])
        self.__class__.instances.append(self)

    @staticmethod
    def train(*, resume_from_checkpoint: str | None) -> SimpleNamespace:
        assert resume_from_checkpoint is None
        return SimpleNamespace(metrics={"train_loss": 0.125})

    @staticmethod
    def save_state() -> None:
        return None

    @staticmethod
    def save_model(path: str) -> None:
        assert Path(path).name == "checkpoints"


class _Constructor:
    @staticmethod
    def build(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)


def _runtime() -> _SFTRuntime:
    return _SFTRuntime(
        model_config_type=_Constructor.build,
        training_config_type=_Constructor.build,
        trainer_type=_Trainer,
        get_peft_config=lambda _: "LORA",
        get_tokenizer=lambda *_: _Tokenizer(),
        get_model=lambda *_: "MODEL",
    )


def _passing_result() -> ExecutionResult:
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


def _record() -> dict[str, object]:
    return {
        "problem_id": "wp6a-1",
        "prompt": "VISIBLE_ONLY_PROMPT",
        "function_name": "solve",
        "visible_tests": [{"input": "VISIBLE_VALUE", "expected": "VISIBLE_VALUE"}],
        "sft_response": "def solve(value):\n    return value",
        "metadata": {
            "difficulty": "easy",
            "category": ["integration"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "test",
            "source_url_hash": None,
        },
    }


def _config(tmp_path: Path, artifact: Path) -> SFTTrainingConfig:
    return sft_training_config_from_mapping(
        {
            "run_name": "wp6a-integration",
            "model_id": "example/model",
            "model_revision": "a" * 40,
            "dataset_path": str(artifact),
            "validation_dataset_path": None,
            "piston_config": str(tmp_path / "piston.yaml"),
            "max_seq_length": 128,
            "max_steps": 1,
            "num_train_epochs": 1.0,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 1,
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
    )


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    _Tokenizer.calls.clear()
    _Trainer.instances.clear()
    monkeypatch.setattr(sft_module, "validate_sft_training_hardware", lambda _: None)
    monkeypatch.setattr(sft_module, "_load_sft_runtime", _runtime)


def test_wp6a_sft_pipeline_maps_visible_only_data_and_writes_reproducible_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "sft.jsonl"
    artifact.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    config = _config(tmp_path, artifact)
    _install_fakes(monkeypatch)
    executor = MockExecutor([_passing_result()])

    summary = run_sft_training(
        config,
        output_root=tmp_path / "outputs" / "sft",
        seed=42,
        executor=executor,
    )

    assert summary.train_loss == 0.125
    assert executor.calls[0].tests == [{"input": "VISIBLE_VALUE", "expected": "VISIBLE_VALUE"}]
    trainer_dataset = cast(Any, _Trainer.instances[0].kwargs["train_dataset"])
    assert trainer_dataset.column_names == ["prompt", "completion"]
    serialized = repr(trainer_dataset[0])
    for forbidden in ("visible_tests", "metadata", "function_name", "VISIBLE_VALUE"):
        assert forbidden not in serialized
    for name in ("run.json", "environment.json", "resolved_config.yaml", "metrics.jsonl", "stdout.log", "stderr.log"):
        contents = (summary.run_dir / name).read_text(encoding="utf-8")
        assert "VISIBLE_ONLY_PROMPT" not in contents
        assert "VISIBLE_VALUE" not in contents


def test_wp6a_sft_pipeline_rejects_hidden_field_or_failed_trajectory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "sft.jsonl"
    record = _record()
    record["eval_hidden_tests"] = [{"input": "EVAL_HIDDEN_SENTINEL", "expected": 0}]
    artifact.write_text(json.dumps(record) + "\n", encoding="utf-8")
    config = _config(tmp_path, artifact)
    _install_fakes(monkeypatch)
    executor = MockExecutor([_passing_result()])

    with pytest.raises(ValueError):
        run_sft_training(
            config,
            output_root=tmp_path / "outputs" / "sft",
            seed=42,
            executor=executor,
        )

    assert executor.calls == ()
    assert _Tokenizer.calls == []
    assert _Trainer.instances == []
