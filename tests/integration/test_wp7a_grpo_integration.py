"""Non-training end-to-end integration coverage for WP7-a GRPO."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

import code_verifier.training.grpo as grpo_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.prompting import build_code_prompt_from_fields
from code_verifier.training.grpo import (
    GRPOTrainingConfig,
    GRPOTrainingError,
    GRPOTrainingSummary,
    _GRPORuntime,
    build_grpo_reward_callback,
    grpo_training_config_from_mapping,
    load_grpo_training_config,
    run_grpo_training,
    validate_grpo_artifact_pair,
    validate_grpo_config_pair,
)
from code_verifier.training.grpo_data import build_grpo_dataset


def _metadata() -> dict[str, object]:
    return {
        "difficulty": "easy",
        "category": ["integration"],
        "time_limit_seconds": 1.0,
        "memory_limit_mb": 128,
        "license": "test",
        "source_url_hash": None,
    }


def _record(*, reward_mode: str) -> dict[str, object]:
    record: dict[str, object] = {
        "problem_id": "wp7a-1",
        "prompt": "Return the input.",
        "function_name": "solve",
        "function_signature": "def solve(value):",
        "visible_tests": [{"input": "VISIBLE_SENTINEL", "expected": "VISIBLE_SENTINEL"}],
        "metadata": _metadata(),
    }
    if reward_mode == "hidden":
        record["train_hidden_tests"] = [{"input": "HIDDEN_SENTINEL", "expected": "HIDDEN_SENTINEL"}]
    return record


def _config(tmp_path: Path, *, reward_mode: str) -> GRPOTrainingConfig:
    return grpo_training_config_from_mapping(
        {
            "run_name": f"{reward_mode}-integration",
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
    )


def _result() -> ExecutionResult:
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


def _callback(tmp_path: Path, *, reward_mode: str, executor: MockExecutor) -> Callable[..., list[float]]:
    return build_grpo_reward_callback(
        reward_mode=reward_mode,
        executor=executor,
        rollout_log_path=tmp_path / reward_mode / "rollouts.jsonl",
        reward_log_path=tmp_path / reward_mode / "rewards.jsonl",
        group_metrics_log_path=tmp_path / reward_mode / "group_metrics.jsonl",
        num_generations=1,
        max_completion_length=16,
    )


def _invoke_callback(tmp_path: Path, *, reward_mode: str) -> MockExecutor:
    executor = MockExecutor([_result()])
    callback = _callback(tmp_path, reward_mode=reward_mode, executor=executor)
    columns: dict[str, object] = {
        "problem_id": ["wp7a-1"],
        "function_name": ["solve"],
        "metadata": [_metadata()],
        "visible_tests": [[{"input": "VISIBLE_SENTINEL", "expected": "VISIBLE_SENTINEL"}]],
    }
    if reward_mode == "hidden":
        columns["train_hidden_tests"] = [[{"input": "HIDDEN_SENTINEL", "expected": "HIDDEN_SENTINEL"}]]
    callback(
        prompts=[[{"role": "user", "content": "PROMPT_SENTINEL"}]],
        completions=["```python\ndef solve(value):\n    return value\n```"],
        completion_ids=[[1, 2]],
        **columns,
    )
    return executor


def test_wp7a_public_and_hidden_configs_match_except_reward_source() -> None:
    public = load_grpo_training_config(Path("configs/grpo/public.yaml"))
    hidden = load_grpo_training_config(Path("configs/grpo/hidden.yaml"))
    validate_grpo_config_pair(public, hidden)


def test_wp7a_grpo_dataset_uses_shared_prompt_and_payload_boundaries() -> None:
    public_record = _record(reward_mode="public")
    hidden_record = _record(reward_mode="hidden")
    validate_grpo_artifact_pair([public_record], [hidden_record])
    public = build_grpo_dataset([public_record], reward_mode="public")
    hidden = build_grpo_dataset([hidden_record], reward_mode="hidden")

    expected_prompt = build_code_prompt_from_fields(
        "Return the input.",
        "def solve(value):",
        [{"input": "VISIBLE_SENTINEL", "expected": "VISIBLE_SENTINEL"}],
    )
    assert public[0]["prompt"] == [{"role": "user", "content": expected_prompt}]
    assert "train_hidden_tests" not in public.column_names
    assert hidden[0]["train_hidden_tests"] == [{"input": "HIDDEN_SENTINEL", "expected": "HIDDEN_SENTINEL"}]
    for forbidden in ("eval_hidden_tests", "reference_solution", "starter_code", "sft_response"):
        assert forbidden not in repr(public[0])
        assert forbidden not in repr(hidden[0])


def test_wp7a_public_reward_scores_only_visible_tests(tmp_path: Path) -> None:
    executor = _invoke_callback(tmp_path, reward_mode="public")
    assert executor.calls[0].tests == [{"input": "VISIBLE_SENTINEL", "expected": "VISIBLE_SENTINEL"}]


def test_wp7a_hidden_reward_scores_only_train_hidden_tests(tmp_path: Path) -> None:
    executor = _invoke_callback(tmp_path, reward_mode="hidden")
    assert executor.calls[0].tests == [{"input": "HIDDEN_SENTINEL", "expected": "HIDDEN_SENTINEL"}]


class _Constructor:
    @staticmethod
    def build(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)


class _MergedPolicy:
    events: ClassVar[list[str]] = []

    @classmethod
    def merge_and_unload(cls, *, safe_merge: bool) -> str:
        assert safe_merge is True
        cls.events.append("merge_b")
        return "MERGED_B"


class _PeftConfig:
    @staticmethod
    def from_pretrained(path: str) -> SimpleNamespace:
        assert Path(path).name == "checkpoints"
        return SimpleNamespace(base_model_name_or_path="example/model", revision="a" * 40)


class _PeftModel:
    @staticmethod
    def from_pretrained(
        model: object,
        path: str,
        *,
        is_trainable: bool,
        config: object,
    ) -> _MergedPolicy:
        assert model == "BASE_A"
        assert Path(path).name == "checkpoints"
        assert is_trainable is False
        assert config is not None
        _MergedPolicy.events.append("attach_b")
        return _MergedPolicy()


class _Trainer:
    instances: ClassVar[list[_Trainer]] = []

    def __init__(self, **kwargs: object) -> None:
        assert _MergedPolicy.events == ["base_a", "attach_b", "merge_b"]
        _MergedPolicy.events.append("new_grpo_lora")
        self.kwargs = dict(kwargs)
        self.resume: str | None = None
        self.state = SimpleNamespace(log_history=[{"loss": 0.2, "step": 1}])
        self.__class__.instances.append(self)

    def train(self, *, resume_from_checkpoint: str | None) -> SimpleNamespace:
        self.resume = resume_from_checkpoint
        dataset = cast(Any, self.kwargs["train_dataset"])
        row = cast(dict[str, object], dataset[0])
        reward = cast(Callable[..., list[float]], self.kwargs["reward_funcs"])
        columns = {key: [value] * 4 for key, value in row.items() if key != "prompt"}
        reward(
            prompts=[row["prompt"]] * 4,
            completions=["```python\ndef solve(value):\n    return value\n```"] * 4,
            completion_ids=[[1, 2]] * 4,
            **columns,
        )
        return SimpleNamespace(metrics={"train_loss": 0.125})

    @staticmethod
    def save_state() -> None:
        return None

    @staticmethod
    def save_model(path: str) -> None:
        assert Path(path).name == "checkpoints"


def _runtime() -> _GRPORuntime:
    def get_model(*args: object) -> str:
        assert args
        _MergedPolicy.events.append("base_a")
        return "BASE_A"

    return _GRPORuntime(
        model_config_type=_Constructor.build,
        training_config_type=_Constructor.build,
        trainer_type=_Trainer,
        get_peft_config=lambda _: "NEW_GRPO_LORA",
        get_tokenizer=lambda *_: "TOKENIZER",
        get_model=get_model,
        peft_config_type=_PeftConfig,
        peft_model_type=_PeftModel,
    )


def _write_sft_run(path: Path, *, run_id: str = "shared-b") -> None:
    path.mkdir()
    checkpoints = path / "checkpoints"
    checkpoints.mkdir()
    (path / "run.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "run_id": run_id,
                "model_id": "example/model",
                "model_revision": "a" * 40,
                "dataset_hash": "b" * 64,
                "config_hash": "c" * 64,
                "dependency_lock_hash": "d" * 64,
                "seed": 42,
            }
        ),
        encoding="utf-8",
    )
    (checkpoints / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "example/model", "peft_type": "LORA"}),
        encoding="utf-8",
    )
    (checkpoints / "adapter_model.safetensors").write_bytes(b"fixture")
    for name in ("resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log"):
        (path / name).touch()


def _run_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reward_mode: str,
    sft_run: Path,
) -> tuple[GRPOTrainingConfig, GRPOTrainingSummary, MockExecutor]:
    public_config = _config(tmp_path, reward_mode="public")
    hidden_config = _config(tmp_path, reward_mode="hidden")
    public_config.dataset_path.write_text(json.dumps(_record(reward_mode="public")) + "\n", encoding="utf-8")
    hidden_config.dataset_path.write_text(json.dumps(_record(reward_mode="hidden")) + "\n", encoding="utf-8")
    public_config.piston_config.write_text("fixture\n", encoding="utf-8")
    _MergedPolicy.events.clear()
    _Trainer.instances.clear()
    monkeypatch.setattr(grpo_module, "validate_grpo_training_hardware", lambda _: None)
    monkeypatch.setattr(grpo_module, "_load_grpo_runtime", _runtime)
    executor = MockExecutor([_result(), _result(), _result(), _result()])
    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode=reward_mode,
        public_sft_run_dir=sft_run,
        hidden_sft_run_dir=sft_run,
        output_root=tmp_path / "outputs",
        seed=42,
        executor=executor,
    )
    config = public_config if reward_mode == "public" else hidden_config
    return config, summary, executor


def test_wp7a_c_and_d_bind_the_same_completed_sft_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sft_run = tmp_path / "sft"
    _write_sft_run(sft_run)
    _, public, _ = _run_fixture(tmp_path, monkeypatch, reward_mode="public", sft_run=sft_run)
    _, hidden, _ = _run_fixture(tmp_path, monkeypatch, reward_mode="hidden", sft_run=sft_run)
    public_run = json.loads((public.run_dir / "run.json").read_text(encoding="utf-8"))
    hidden_run = json.loads((hidden.run_dir / "run.json").read_text(encoding="utf-8"))
    for field in (
        "parent_sft_run_id",
        "parent_sft_model_id",
        "parent_sft_model_revision",
        "parent_sft_dataset_hash",
        "parent_sft_config_hash",
        "parent_sft_checkpoint_path",
    ):
        assert public_run[field] == hidden_run[field]


@pytest.mark.parametrize("drift", ["parent", "config", "artifact"])
def test_wp7a_cd_preflight_rejects_fairness_drift_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    public_sft = tmp_path / "public-sft"
    hidden_sft = tmp_path / "hidden-sft"
    _write_sft_run(public_sft)
    _write_sft_run(hidden_sft, run_id="other-b" if drift == "parent" else "shared-b")
    public_config = _config(tmp_path, reward_mode="public")
    hidden_config = _config(tmp_path, reward_mode="hidden")
    if drift == "config":
        hidden_config = replace(hidden_config, temperature=0.7)
    public_record = _record(reward_mode="public")
    hidden_record = _record(reward_mode="hidden")
    if drift == "artifact":
        hidden_record["prompt"] = "DRIFTED_PROMPT"
    public_config.dataset_path.write_text(json.dumps(public_record) + "\n", encoding="utf-8")
    hidden_config.dataset_path.write_text(json.dumps(hidden_record) + "\n", encoding="utf-8")
    monkeypatch.setattr(grpo_module, "validate_grpo_training_hardware", lambda _: None)

    with pytest.raises(GRPOTrainingError):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=public_sft,
            hidden_sft_run_dir=hidden_sft,
            output_root=tmp_path / "outputs",
            seed=42,
            executor=MockExecutor([]),
        )
    assert not (tmp_path / "outputs").exists()


def test_wp7a_sft_adapter_is_merged_before_new_grpo_lora(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sft_run = tmp_path / "sft"
    _write_sft_run(sft_run)
    _run_fixture(tmp_path, monkeypatch, reward_mode="public", sft_run=sft_run)
    assert _MergedPolicy.events == ["base_a", "attach_b", "merge_b", "new_grpo_lora"]
    assert _Trainer.instances[0].kwargs["model"] == "MERGED_B"
    assert _Trainer.instances[0].kwargs["peft_config"] == "NEW_GRPO_LORA"


def test_wp7a_rollout_reward_group_artifacts_are_sanitized_and_recomputable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sft_run = tmp_path / "sft"
    _write_sft_run(sft_run)
    _, summary, _ = _run_fixture(tmp_path, monkeypatch, reward_mode="hidden", sft_run=sft_run)
    rewards = [json.loads(line) for line in (summary.run_dir / "rewards.jsonl").read_text().splitlines()]
    for row in rewards:
        assert row["total_reward"] == pytest.approx(
            row["test_reward"] + row["executable_reward"] + row["timeout_penalty"] + row["invalid_format_penalty"]
        )
    group = json.loads((summary.run_dir / "group_metrics.jsonl").read_text())
    assert group["sample_count"] == 4
    assert group["all_equal"] is True
    for name in ("rewards.jsonl", "group_metrics.jsonl", "run.json", "metrics.jsonl", "stderr.log"):
        contents = (summary.run_dir / name).read_text(encoding="utf-8")
        for forbidden in ("VISIBLE_SENTINEL", "HIDDEN_SENTINEL", "completion", "function_name", "metadata"):
            assert forbidden not in contents


def test_wp7a_resume_requires_same_parent_sft_config_data_and_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sft_run = tmp_path / "sft"
    _write_sft_run(sft_run)
    config, summary, _ = _run_fixture(tmp_path, monkeypatch, reward_mode="public", sft_run=sft_run)
    checkpoint = summary.checkpoint_dir / "checkpoint-1"
    checkpoint.mkdir()
    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    run_metadata["status"] = "failed"
    (summary.run_dir / "run.json").write_text(json.dumps(run_metadata), encoding="utf-8")
    with pytest.raises(GRPOTrainingError, match="identity"):
        run_grpo_training(
            replace(config, temperature=0.7),
            replace(_config(tmp_path, reward_mode="hidden"), temperature=0.7),
            reward_mode="public",
            public_sft_run_dir=sft_run,
            hidden_sft_run_dir=sft_run,
            output_root=tmp_path / "outputs",
            seed=42,
            executor=MockExecutor([_result()] * 4),
            resume_from_checkpoint=checkpoint,
        )
    external = tmp_path / "external" / "checkpoint-1"
    external.mkdir(parents=True)
    with pytest.raises(GRPOTrainingError, match="same GRPO run"):
        run_grpo_training(
            config,
            _config(tmp_path, reward_mode="hidden"),
            reward_mode="public",
            public_sft_run_dir=sft_run,
            hidden_sft_run_dir=sft_run,
            output_root=tmp_path / "outputs",
            seed=42,
            executor=MockExecutor([_result()] * 4),
            resume_from_checkpoint=external,
        )


def test_wp7a_hardware_guard_fails_before_model_loading_on_1660(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, reward_mode="public")
    parent_loaded = False

    def load_parent(path: Path) -> object:
        nonlocal parent_loaded
        parent_loaded = True
        return path

    monkeypatch.setattr(grpo_module, "load_completed_sft_checkpoint", load_parent)
    with pytest.raises(GRPOTrainingError, match="at least 20"):
        run_grpo_training(
            config,
            _config(tmp_path, reward_mode="hidden"),
            reward_mode="public",
            public_sft_run_dir=tmp_path / "sft",
            hidden_sft_run_dir=tmp_path / "sft",
            output_root=tmp_path / "outputs",
            seed=42,
            executor=MockExecutor([]),
        )
    assert parent_loaded is False
