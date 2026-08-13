"""WP6-c engineering contract for completed SFT checkpoint evaluation."""

from __future__ import annotations

import json
import re
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
from code_verifier.training import SFTCheckpointIdentity, load_completed_sft_checkpoint


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
        return f"```python\n# FIXTURE_CODE_SENTINEL\ndef {match.group(1)}(*args, **kwargs):\n    return None\n```"


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
        del adapter_dir, kwargs
        return SimpleNamespace(base_model_name_or_path="fixture/base-model", revision=None)


class _FakePeftModel:
    @staticmethod
    def from_pretrained(model: object, adapter_dir: str, **kwargs: object) -> object:
        del adapter_dir
        assert kwargs["is_trainable"] is False
        return model


class _NoCallGenerator:
    @staticmethod
    def generate(prompt: str, *, seed: int) -> GenerationResult:
        del prompt, seed
        pytest.fail("an exact-prefix resume must not generate another completion")


def _write_completed_fixture_run(run_dir: Path, *, run_id: str = "fixture-sft-run") -> None:
    run_dir.mkdir(parents=True)
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "run_id": run_id,
                "model_id": "fixture/base-model",
                "model_revision": "a" * 40,
                "dataset_hash": "b" * 64,
                "config_hash": "c" * 64,
                "dependency_lock_hash": "d" * 64,
                "seed": 42,
                "evidence_class": "engineering_fixture",
                "private_training_payload": "TRAINING_PAYLOAD_SENTINEL",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": "fixture/base-model",
                "peft_type": "LORA",
            }
        ),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_model.safetensors").write_bytes(b"engineering-fixture-only")
    for name in ("resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log"):
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
    identity: SFTCheckpointIdentity
    config: EvaluationConfig
    run: EvaluationRunSummary
    aggregate: EvaluationAggregateSummary
    tokenizer: _FakeTokenizer
    output_root: Path


@pytest.fixture
def artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Artifacts:
    prepared = tmp_path / "prepared"
    prepare_data(load_data_preparation_config(Path("configs/data/smoke.yaml")), seed=42, output_dir=prepared)
    sft_run_dir = tmp_path / "sft" / "fixture-sft-run"
    _write_completed_fixture_run(sft_run_dir)
    identity = load_completed_sft_checkpoint(sft_run_dir)
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    transformers_runtime = _FakeTransformers(tokenizer, model)
    monkeypatch.setattr(
        generation_module,
        "_load_transformers_runtime",
        lambda: (_FakeTorch(), transformers_runtime),
    )
    monkeypatch.setattr(
        generation_module,
        "_load_peft_runtime",
        lambda: (_FakePeftConfig, _FakePeftModel),
    )
    config = EvaluationConfig(
        dataset_dir=prepared,
        split="test",
        piston_config=Path("configs/execution/piston-local.yaml").resolve(),
        model_revision=identity.model_revision,
        checkpoint=str(identity.checkpoint_dir),
        device="cpu",
        generation=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
    )
    generator = TransformersCompletionGenerator.from_peft_checkpoint(
        base_model_id=identity.model_id,
        base_model_revision=identity.model_revision,
        adapter_dir=identity.checkpoint_dir,
        device=config.device,
        config=config.generation,
    )
    problem_count = len(load_evaluation_problems(config))
    output_root = tmp_path / "outputs"
    run = run_pass1_evaluation(
        config=config,
        model_id=identity.model_id,
        generator=generator,
        executor=MockExecutor([_passed_execution() for _ in range(problem_count * 3)]),
        run_id="wp6c-fixture-evaluation",
        output_root=output_root,
        seed=42,
    )
    aggregate = aggregate_evaluation_run(run.results_path.parents[1], bootstrap_seed=42, bootstrap_resamples=100)
    assert model.eval_called is True
    return _Artifacts(identity, config, run, aggregate, tokenizer, output_root)


def test_wp6c_completed_sft_checkpoint_runs_through_existing_evaluator(artifacts: _Artifacts) -> None:
    run_dir = artifacts.run.results_path.parents[1]
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in artifacts.run.results_path.read_text(encoding="utf-8").splitlines()]

    assert artifacts.run.total_problems == 4
    assert metadata["model_id"] == artifacts.identity.model_id
    assert metadata["model_revision"] == artifacts.identity.model_revision
    assert metadata["checkpoint"] == str(artifacts.identity.checkpoint_dir)
    assert all(row["checkpoint"] == str(artifacts.identity.checkpoint_dir) for row in rows)
    assert artifacts.aggregate.summary_path.is_file()
    assert artifacts.aggregate.main_results_path.is_file()


def test_wp6c_b_evaluation_resume_is_bound_to_checkpoint_identity(
    artifacts: _Artifacts,
    tmp_path: Path,
) -> None:
    resumed = run_pass1_evaluation(
        config=artifacts.config,
        model_id=artifacts.identity.model_id,
        generator=_NoCallGenerator(),
        executor=MockExecutor([]),
        run_id="wp6c-fixture-evaluation",
        output_root=artifacts.output_root,
        seed=42,
    )
    assert resumed.completed_before_run == resumed.total_problems
    assert resumed.generated_this_run == 0

    other_run = tmp_path / "sft" / "other-fixture-run"
    _write_completed_fixture_run(other_run, run_id="other-fixture-run")
    other_identity = load_completed_sft_checkpoint(other_run)
    changed_config = replace(artifacts.config, checkpoint=str(other_identity.checkpoint_dir))
    with pytest.raises(EvaluationError, match="identity"):
        run_pass1_evaluation(
            config=changed_config,
            model_id=other_identity.model_id,
            generator=_NoCallGenerator(),
            executor=MockExecutor([]),
            run_id="wp6c-fixture-evaluation",
            output_root=artifacts.output_root,
            seed=42,
        )


def test_wp6c_b_evaluation_artifacts_preserve_payload_boundaries(artifacts: _Artifacts) -> None:
    problems = load_evaluation_problems(artifacts.config)
    for problem, prompt in zip(problems, artifacts.tokenizer.prompts, strict=True):
        assert problem.prompt in prompt
        assert problem.function_signature in prompt
        for test_case in (*problem.train_hidden_tests, *problem.eval_hidden_tests):
            hidden_payload = json.dumps(
                case_to_mapping(test_case),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            assert hidden_payload not in prompt
        assert problem.reference_solution is not None
        assert problem.reference_solution not in prompt
        assert problem.sft_response is not None
        assert problem.sft_response not in prompt

    run_dir = artifacts.run.results_path.parents[1]
    non_sample_text = "\n".join(path.read_text(encoding="utf-8") for path in run_dir.iterdir() if path.is_file())
    for forbidden in (
        "FIXTURE_CODE_SENTINEL",
        "TRAINING_PAYLOAD_SENTINEL",
        '"completion"',
        '"extracted_code"',
        '"visible_tests"',
        '"train_hidden_tests"',
        '"eval_hidden_tests"',
        '"reference_solution"',
        '"sft_response"',
    ):
        assert forbidden not in non_sample_text
    assert "FIXTURE_CODE_SENTINEL" in artifacts.run.results_path.read_text(encoding="utf-8")


def test_wp6c_fixture_checkpoint_is_never_reported_as_real_training_evidence(artifacts: _Artifacts) -> None:
    run_dir = artifacts.run.results_path.parents[1]
    derived_text = artifacts.aggregate.summary_path.read_text(
        encoding="utf-8"
    ) + artifacts.aggregate.main_results_path.read_text(encoding="utf-8")
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert metadata["command"] == "code-verifier evaluate"
    assert "train_loss" not in derived_text
    assert "gpu_hours" not in derived_text
    assert "engineering_fixture" not in derived_text
    assert "real" not in derived_text.lower()
