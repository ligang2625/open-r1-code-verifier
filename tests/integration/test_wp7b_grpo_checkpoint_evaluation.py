"""WP7-b engineering contract for completed GRPO checkpoint evaluation."""

from __future__ import annotations

import json
import re
import shutil
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

import code_verifier.evaluation.generate as generation_module
from code_verifier.data.prepare import load_data_preparation_config, prepare_data
from code_verifier.data.schema import test_case_to_mapping as case_to_mapping
from code_verifier.evaluation.evaluate import (
    EvaluationConfig,
    EvaluationError,
    EvaluationRunSummary,
    load_evaluation_problems,
    run_pass1_evaluation,
)
from code_verifier.evaluation.generate import GenerationConfig, GenerationResult, TransformersCompletionGenerator
from code_verifier.evaluation.metrics import EvaluationAggregateSummary, aggregate_evaluation_run
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training import (
    GRPOCheckpointIdentity,
    grpo_evaluation_checkpoint_id,
    load_completed_grpo_checkpoint,
)


class _FakeTensor:
    def __init__(self, values: list[list[int]]) -> None:
        self.values = values

    def __getitem__(self, index: int) -> list[int]:
        return self.values[index]

    def to(self, device: str) -> _FakeTensor:
        del device
        return self


class _FakeTokenizer:
    chat_template = "engineering-fixture-template"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        add_generation_prompt: bool,
        tokenize: bool,
    ) -> str:
        assert add_generation_prompt is True
        assert tokenize is False
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        return prompt

    def __call__(self, text: str, *, return_tensors: str, add_special_tokens: bool) -> dict[str, _FakeTensor]:
        assert return_tensors == "pt"
        assert add_special_tokens is False
        assert text == self.prompts[-1]
        return {"input_ids": _FakeTensor([[1, 2]])}

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool) -> str:
        assert token_ids == [9]
        assert skip_special_tokens is True
        match = re.search(r"Function signature:\n(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", self.prompts[-1])
        assert match is not None
        return f"```python\n# FIXTURE_CD_CODE_SENTINEL\ndef {match.group(1)}(*args, **kwargs):\n    return None\n```"


class _FakeModel:
    device = "cpu"

    def __init__(self) -> None:
        self.eval_called = False

    def to(self, device: str) -> _FakeModel:
        self.device = device
        return self

    def eval(self) -> None:
        self.eval_called = True

    @staticmethod
    def generate(**kwargs: object) -> list[list[int]]:
        assert kwargs["do_sample"] is False
        return [[1, 2, 9]]


class _Loader:
    def __init__(self, value: object) -> None:
        self.value = value

    def from_pretrained(self, model_id: str, **kwargs: object) -> object:
        del model_id, kwargs
        return self.value


class _FakeTransformers:
    def __init__(self, tokenizer: _FakeTokenizer, model: _FakeModel) -> None:
        self.AutoTokenizer = _Loader(tokenizer)
        self.AutoModelForCausalLM = _Loader(model)

    @staticmethod
    def set_seed(seed: int) -> None:
        assert seed == 42


class _FakeTorch:
    float16 = "float16"
    bfloat16 = "bfloat16"
    float32 = "float32"

    @staticmethod
    def inference_mode() -> Any:
        return nullcontext()


class _FakePeftConfig:
    @staticmethod
    def from_pretrained(adapter_dir: str, **kwargs: object) -> SimpleNamespace:
        del kwargs
        value = json.loads((Path(adapter_dir) / "adapter_config.json").read_text(encoding="utf-8"))
        return SimpleNamespace(
            base_model_name_or_path=value["base_model_name_or_path"],
            revision=value.get("revision"),
        )


class _ParentPolicy:
    def __init__(self, model: object) -> None:
        self.model = model

    def merge_and_unload(self, *, safe_merge: bool) -> object:
        _FakePeftModel.calls.append(("merge_b", safe_merge))
        return self.model


class _FakePeftModel:
    calls: ClassVar[list[tuple[object, ...]]] = []
    parent_checkpoint: ClassVar[Path]

    @classmethod
    def from_pretrained(cls, model: object, adapter_dir: str, **kwargs: object) -> object:
        path = Path(adapter_dir)
        assert kwargs["is_trainable"] is False
        if path == cls.parent_checkpoint:
            cls.calls.append(("attach_b", path, model, kwargs["is_trainable"]))
            return _ParentPolicy(model)
        cls.calls.append(("attach_cd", path, model, kwargs["is_trainable"]))
        return model


class _NoCallGenerator:
    @staticmethod
    def generate(prompt: str, *, seed: int) -> GenerationResult:
        del prompt, seed
        pytest.fail("an exact-prefix resume must not generate another completion")


def _write_completed_sft_run(run_dir: Path, *, run_id: str = "fixture-b") -> None:
    run_dir.mkdir(parents=True)
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    metadata = {
        "status": "completed",
        "run_id": run_id,
        "model_id": "fixture/base-model",
        "model_revision": "a" * 40,
        "dataset_hash": "b" * 64,
        "config_hash": "c" * 64,
        "dependency_lock_hash": "d" * 64,
        "seed": 42,
        "evidence_class": "engineering_fixture",
    }
    (run_dir / "run.json").write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    (checkpoint_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "fixture/base-model", "peft_type": "LORA"}),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_model.safetensors").write_bytes(b"fixture-b-adapter")
    for name in ("resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log"):
        (run_dir / name).touch()


def _write_completed_grpo_run(run_dir: Path, parent_run: Path, *, reward_mode: str, run_id: str) -> None:
    run_dir.mkdir(parents=True)
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    parent_checkpoint = (parent_run / "checkpoints").resolve()
    metadata = {
        "status": "completed",
        "run_id": run_id,
        "reward_mode": reward_mode,
        "dataset_hash": "1" * 64,
        "config_hash": "2" * 64,
        "dependency_lock_hash": "3" * 64,
        "seed": 42,
        "parent_sft_run_id": json.loads((parent_run / "run.json").read_text(encoding="utf-8"))["run_id"],
        "parent_sft_model_id": "fixture/base-model",
        "parent_sft_model_revision": "a" * 40,
        "parent_sft_dataset_hash": "b" * 64,
        "parent_sft_config_hash": "c" * 64,
        "parent_sft_dependency_lock_hash": "d" * 64,
        "parent_sft_seed": 42,
        "parent_sft_run_path": str(parent_run.resolve()),
        "parent_sft_checkpoint_path": str(parent_checkpoint),
        "evidence_class": "engineering_fixture",
    }
    (run_dir / "run.json").write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    (checkpoint_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": "fixture/base-model",
                "revision": "a" * 40,
                "peft_type": "LORA",
            }
        ),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_model.safetensors").write_bytes(b"fixture-cd-adapter")
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


def _passed_execution() -> ExecutionResult:
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


@dataclass(frozen=True)
class _Artifacts:
    identities: dict[str, GRPOCheckpointIdentity]
    configs: dict[str, EvaluationConfig]
    runs: dict[str, EvaluationRunSummary]
    aggregates: dict[str, EvaluationAggregateSummary]
    tokenizer: _FakeTokenizer
    output_root: Path


@pytest.fixture
def artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Artifacts:
    prepared = tmp_path / "prepared"
    prepare_data(load_data_preparation_config(Path("configs/data/smoke.yaml")), seed=42, output_dir=prepared)
    parent_run = tmp_path / "sft" / "fixture-b"
    _write_completed_sft_run(parent_run)
    grpo_dirs = {"public": tmp_path / "grpo" / "fixture-c", "hidden": tmp_path / "grpo" / "fixture-d"}
    for mode, run_dir in grpo_dirs.items():
        _write_completed_grpo_run(run_dir, parent_run, reward_mode=mode, run_id=f"fixture-{mode}")
    identities = {mode: load_completed_grpo_checkpoint(path) for mode, path in grpo_dirs.items()}
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    transformers_runtime = _FakeTransformers(tokenizer, model)
    _FakePeftModel.calls.clear()
    _FakePeftModel.parent_checkpoint = identities["public"].parent_sft.checkpoint_dir
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), transformers_runtime))
    monkeypatch.setattr(generation_module, "_load_peft_runtime", lambda: (_FakePeftConfig, _FakePeftModel))
    output_root = tmp_path / "outputs"
    configs: dict[str, EvaluationConfig] = {}
    runs: dict[str, EvaluationRunSummary] = {}
    aggregates: dict[str, EvaluationAggregateSummary] = {}
    for mode, identity in identities.items():
        config = EvaluationConfig(
            dataset_dir=prepared,
            split="test",
            piston_config=Path("configs/execution/piston-local.yaml").resolve(),
            model_revision=identity.parent_sft.model_revision,
            checkpoint=grpo_evaluation_checkpoint_id(identity),
            device="cpu",
            generation=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        )
        generator = TransformersCompletionGenerator.from_grpo_checkpoint(
            base_model_id=identity.parent_sft.model_id,
            base_model_revision=identity.parent_sft.model_revision,
            parent_sft_adapter_dir=identity.parent_sft.checkpoint_dir,
            grpo_adapter_dir=identity.checkpoint_dir,
            device=config.device,
            config=config.generation,
        )
        problem_count = len(load_evaluation_problems(config))
        run = run_pass1_evaluation(
            config=config,
            model_id=identity.parent_sft.model_id,
            generator=generator,
            executor=MockExecutor([_passed_execution() for _ in range(problem_count * 3)]),
            run_id=f"wp7b-fixture-{mode}",
            output_root=output_root,
            seed=42,
        )
        configs[mode] = config
        runs[mode] = run
        aggregates[mode] = aggregate_evaluation_run(
            run.results_path.parents[1], bootstrap_seed=42, bootstrap_resamples=100
        )
    assert model.eval_called is True
    return _Artifacts(identities, configs, runs, aggregates, tokenizer, output_root)


def test_wp7b_completed_grpo_checkpoint_runs_through_existing_evaluator(artifacts: _Artifacts) -> None:
    for mode in ("public", "hidden"):
        identity = artifacts.identities[mode]
        run = artifacts.runs[mode]
        run_dir = run.results_path.parents[1]
        metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in run.results_path.read_text(encoding="utf-8").splitlines()]
        assert run.total_problems == 4
        assert metadata["model_id"] == identity.parent_sft.model_id
        assert metadata["checkpoint"] == grpo_evaluation_checkpoint_id(identity)
        assert all(row["checkpoint"] == metadata["checkpoint"] for row in rows)
        assert artifacts.aggregates[mode].summary_path.is_file()
        assert artifacts.aggregates[mode].main_results_path.is_file()


def test_wp7b_cd_reload_order_is_a_then_merged_b_then_cd_adapter(artifacts: _Artifacts) -> None:
    del artifacts
    assert [call[0] for call in _FakePeftModel.calls] == [
        "attach_b",
        "merge_b",
        "attach_cd",
        "attach_b",
        "merge_b",
        "attach_cd",
    ]
    assert all(call[-1] is False for call in _FakePeftModel.calls if call[0].startswith("attach"))
    assert all(call[1] is True for call in _FakePeftModel.calls if call[0] == "merge_b")


def test_wp7b_cd_evaluation_resume_is_bound_to_cd_and_parent_b_identity(
    artifacts: _Artifacts,
    tmp_path: Path,
) -> None:
    public_config = artifacts.configs["public"]
    resumed = run_pass1_evaluation(
        config=public_config,
        model_id=artifacts.identities["public"].parent_sft.model_id,
        generator=_NoCallGenerator(),
        executor=MockExecutor([]),
        run_id="wp7b-fixture-public",
        output_root=artifacts.output_root,
        seed=42,
    )
    assert resumed.completed_before_run == resumed.total_problems
    assert resumed.generated_this_run == 0

    changed_configs = [
        artifacts.configs["hidden"],
        replace(public_config, generation=replace(public_config.generation, max_new_tokens=9)),
    ]
    copied_data = tmp_path / "prepared-copy"
    shutil.copytree(public_config.dataset_dir, copied_data)
    changed_configs.append(replace(public_config, dataset_dir=copied_data))
    other_parent = tmp_path / "sft" / "other-b"
    _write_completed_sft_run(other_parent, run_id="other-b")
    other_grpo = tmp_path / "grpo" / "other-c"
    _write_completed_grpo_run(other_grpo, other_parent, reward_mode="public", run_id="other-c")
    other_identity = load_completed_grpo_checkpoint(other_grpo)
    changed_configs.append(replace(public_config, checkpoint=grpo_evaluation_checkpoint_id(other_identity)))
    for changed in changed_configs:
        with pytest.raises(EvaluationError, match="identity"):
            run_pass1_evaluation(
                config=changed,
                model_id=artifacts.identities["public"].parent_sft.model_id,
                generator=_NoCallGenerator(),
                executor=MockExecutor([]),
                run_id="wp7b-fixture-public",
                output_root=artifacts.output_root,
                seed=42,
            )
    with pytest.raises(EvaluationError, match="identity"):
        run_pass1_evaluation(
            config=public_config,
            model_id=artifacts.identities["public"].parent_sft.model_id,
            generator=_NoCallGenerator(),
            executor=MockExecutor([]),
            run_id="wp7b-fixture-public",
            output_root=artifacts.output_root,
            seed=7,
        )


def test_wp7b_cd_evaluation_artifacts_preserve_payload_boundaries(artifacts: _Artifacts) -> None:
    problems = load_evaluation_problems(artifacts.configs["public"])
    for problem, prompt in zip(problems * 2, artifacts.tokenizer.prompts, strict=True):
        assert problem.prompt in prompt
        assert problem.function_signature in prompt
        for test_case in (*problem.train_hidden_tests, *problem.eval_hidden_tests):
            hidden_payload = json.dumps(case_to_mapping(test_case), sort_keys=True, separators=(",", ":"))
            assert hidden_payload not in prompt
        assert problem.reference_solution is not None and problem.reference_solution not in prompt
        assert problem.sft_response is not None and problem.sft_response not in prompt
    for run in artifacts.runs.values():
        run_dir = run.results_path.parents[1]
        non_sample_text = "\n".join(path.read_text(encoding="utf-8") for path in run_dir.iterdir() if path.is_file())
        for forbidden in (
            "FIXTURE_CD_CODE_SENTINEL",
            '"completion"',
            '"extracted_code"',
            '"visible_tests"',
            '"train_hidden_tests"',
            '"eval_hidden_tests"',
            '"reference_solution"',
            '"starter_code"',
            '"sft_response"',
        ):
            assert forbidden not in non_sample_text
        assert "FIXTURE_CD_CODE_SENTINEL" in run.results_path.read_text(encoding="utf-8")


def test_wp7b_fixture_cd_is_never_reported_as_real_training_evidence(artifacts: _Artifacts) -> None:
    for mode, run in artifacts.runs.items():
        run_dir = run.results_path.parents[1]
        metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        derived = artifacts.aggregates[mode].summary_path.read_text(encoding="utf-8") + artifacts.aggregates[
            mode
        ].main_results_path.read_text(encoding="utf-8")
        assert metadata["command"] == "code-verifier evaluate"
        assert "train_loss" not in derived
        assert "gpu_hours" not in derived
        assert "engineering_fixture" not in derived
        assert "real training" not in derived.lower()
