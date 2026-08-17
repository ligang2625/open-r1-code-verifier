"""Tests for strict WP5-a run artifacts, interruption, and prefix resume."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import code_verifier.evaluation.evaluate as evaluation_module
from code_verifier.data.schema import CodeProblem, ProblemMetadata
from code_verifier.data.schema import TestCase as CodeTestCase
from code_verifier.evaluation.evaluate import EvaluationConfig, EvaluationError, run_pass1_evaluation
from code_verifier.evaluation.generate import GenerationConfig, GenerationError, GenerationResult
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.base import TestCaseResult as ExecutionTestCaseResult
from code_verifier.execution.mock import MockExecutor


class _SequenceGenerator:
    def __init__(self, results: list[GenerationResult | BaseException]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, int]] = []

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        self.calls.append((prompt, seed))
        if not self._results:
            raise AssertionError("unexpected generation call")
        value = self._results.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def _problem(problem_id: str, marker: str) -> CodeProblem:
    return CodeProblem(
        problem_id=problem_id,
        source="unit",
        split="test",
        prompt=f"Return the input for {marker}.",
        function_name="solve",
        function_signature="def solve(x):",
        starter_code=None,
        visible_tests=(CodeTestCase(input=f"VISIBLE_{marker}", expected=1),),
        train_hidden_tests=(CodeTestCase(input=f"TRAIN_{marker}", expected=2),),
        eval_hidden_tests=(CodeTestCase(input=f"EVAL_{marker}", expected=3),),
        reference_solution=None,
        sft_response=None,
        metadata=ProblemMetadata(
            difficulty="easy",
            category=("unit",),
            time_limit_seconds=1.0,
            memory_limit_mb=128,
            license="test",
            source_url_hash=None,
        ),
    )


def _pass_result() -> ExecutionResult:
    test_result = ExecutionTestCaseResult(
        status=ExecutionStatus.PASSED,
        passed=True,
        runtime_ms=1.0,
        stdout="",
        stderr="",
    )
    return ExecutionResult(
        status=ExecutionStatus.PASSED,
        passed_tests=1,
        total_tests=1,
        pass_rate=1.0,
        runtime_ms=1.0,
        test_results=[test_result],
    )


def _config(tmp_path: Path) -> EvaluationConfig:
    piston_config = tmp_path / "piston.yaml"
    piston_config.write_text("piston:\n  url: http://127.0.0.1:2000\n", encoding="utf-8")
    return EvaluationConfig(
        dataset_dir=tmp_path / "prepared",
        split="test",
        piston_config=piston_config,
        model_revision=None,
        checkpoint="base",
        device="cpu",
        generation=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=512),
    )


def _completion(marker: str) -> GenerationResult:
    return GenerationResult(
        completion=f"```python\n# {marker}\ndef solve(x):\n    return x\n```",
        completion_tokens=8,
        latency_ms=2.0,
    )


def test_fresh_completed_run_records_timing_and_gpu_hours(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    monkeypatch.setattr(evaluation_module, "_run_gpu_count_used", lambda config, environment: 1)
    output_root = tmp_path / "outputs"

    summary = run_pass1_evaluation(
        config=_config(tmp_path),
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="timing-fresh",
        output_root=output_root,
        seed=42,
    )

    metadata = json.loads((summary.results_path.parents[1] / "run.json").read_text(encoding="utf-8"))
    start = datetime.fromisoformat(metadata["start_time"])
    end = datetime.fromisoformat(metadata["end_time"])
    assert metadata["created_at"] == metadata["start_time"]
    assert start.tzinfo is not None and end.tzinfo is not None
    assert end >= start
    assert metadata["status"] == "completed"
    assert metadata["gpu_count_used"] == 1
    assert metadata["gpu_hours_semantics"] == "persisted_generation_latency_ms_x_gpu_count_used"
    assert metadata["gpu_hours"] == pytest.approx(2.0 / 3_600_000.0)


def test_keyboard_interrupt_resume_accumulates_only_persisted_generation_gpu_hours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem("p1", "ONE"), _problem("p2", "TWO")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    monkeypatch.setattr(evaluation_module, "_run_gpu_count_used", lambda config, environment: 1)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"

    with pytest.raises(KeyboardInterrupt):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([_completion("ONE"), KeyboardInterrupt()]),
            executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
            run_id="timing-resume",
            output_root=output_root,
            seed=42,
        )

    run_json = output_root / "evaluation" / "timing-resume" / "run.json"
    interrupted = json.loads(run_json.read_text(encoding="utf-8"))
    immutable_start = interrupted["start_time"]
    assert interrupted["status"] == "failed"
    assert interrupted["end_time"] is None
    assert interrupted["gpu_hours"] == pytest.approx(2.0 / 3_600_000.0)

    resumed = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("TWO")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="timing-resume",
        output_root=output_root,
        seed=42,
    )
    completed = json.loads(run_json.read_text(encoding="utf-8"))
    assert resumed.completed_before_run == 1
    assert resumed.generated_this_run == 1
    assert completed["start_time"] == immutable_start
    assert completed["status"] == "completed"
    assert completed["end_time"] is not None
    assert completed["gpu_hours"] == pytest.approx(4.0 / 3_600_000.0)

    frozen_metadata = run_json.read_bytes()
    no_op = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([]),
        executor=MockExecutor([]),
        run_id="timing-resume",
        output_root=output_root,
        seed=42,
    )
    assert no_op.completed_before_run == 2
    assert no_op.generated_this_run == 0
    assert run_json.read_bytes() == frozen_metadata


def test_interrupted_run_resumes_exact_prefix_without_regeneration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem("p1", "ONE"), _problem("p2", "TWO")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"

    first_generator = _SequenceGenerator([_completion("COMPLETION_ONE"), GenerationError("interrupted")])
    first_executor = MockExecutor([_pass_result(), _pass_result(), _pass_result()])
    with pytest.raises(GenerationError, match="interrupted"):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=first_generator,
            executor=first_executor,
            run_id="resume-test",
            output_root=output_root,
            seed=42,
        )

    second_generator = _SequenceGenerator([_completion("COMPLETION_TWO")])
    second_executor = MockExecutor([_pass_result(), _pass_result(), _pass_result()])
    summary = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=second_generator,
        executor=second_executor,
        run_id="resume-test",
        output_root=output_root,
        seed=42,
    )

    assert summary.completed_before_run == 1
    assert summary.generated_this_run == 1
    assert len(second_generator.calls) == 1
    rows = summary.results_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert json.loads(rows[0])["problem_id"] == "p1"
    assert json.loads(rows[1])["problem_id"] == "p2"

    completed_generator = _SequenceGenerator([])
    completed_summary = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=completed_generator,
        executor=MockExecutor([]),
        run_id="resume-test",
        output_root=output_root,
        seed=42,
    )
    assert completed_summary.completed_before_run == 2
    assert completed_summary.generated_this_run == 0
    assert completed_generator.calls == []


def test_resume_allows_known_derived_artifacts_for_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem("p1", "ONE")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    summary = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="derived-completed",
        output_root=output_root,
        seed=42,
    )
    run_dir = summary.results_path.parents[1]
    (run_dir / "summary.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "main_results.csv").write_text("header\n", encoding="utf-8")

    resumed = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([]),
        executor=MockExecutor([]),
        run_id="derived-completed",
        output_root=output_root,
        seed=42,
    )

    assert resumed.generated_this_run == 0


def test_resume_rejects_derived_artifacts_for_partial_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE"), _problem("p2", "TWO")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    with pytest.raises(GenerationError):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([_completion("ONE"), GenerationError("stop")]),
            executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
            run_id="derived-partial",
            output_root=output_root,
            seed=42,
        )
    run_dir = output_root / "evaluation" / "derived-partial"
    (run_dir / "summary.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(EvaluationError, match="derived summary artifacts"):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([_completion("TWO")]),
            executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
            run_id="derived-partial",
            output_root=output_root,
            seed=42,
        )


def test_resume_still_rejects_unknown_run_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    summary = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="unknown-artifact",
        output_root=output_root,
        seed=42,
    )
    (summary.results_path.parents[1] / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(EvaluationError, match="strict WP5-a artifact layout"):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="unknown-artifact",
            output_root=output_root,
            seed=42,
        )


def test_resume_rejects_model_identity_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("MODEL_ONE")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="identity-test",
        output_root=output_root,
        seed=42,
    )

    with pytest.raises(EvaluationError):
        run_pass1_evaluation(
            config=config,
            model_id="different/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="identity-test",
            output_root=output_root,
            seed=42,
        )


def test_resume_rejects_corrupt_or_prompt_drifted_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    summary = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("CORRUPT_TEST")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="corrupt-test",
        output_root=output_root,
        seed=42,
    )
    row = json.loads(summary.results_path.read_text(encoding="utf-8"))
    row["prompt_hash"] = "x" * 64
    summary.results_path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationError, match="exact expected resume prefix"):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="corrupt-test",
            output_root=output_root,
            seed=42,
        )

    summary.results_path.write_text("{\n", encoding="utf-8")
    with pytest.raises(EvaluationError, match="invalid"):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="corrupt-test",
            output_root=output_root,
            seed=42,
        )


def test_non_result_artifacts_do_not_persist_completion_or_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem("p1", "ONE")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    summary = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("PRIVATE_COMPLETION_SENTINEL")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="payload-test",
        output_root=tmp_path / "outputs",
        seed=42,
    )
    run_dir = summary.results_path.parents[1]
    resolved = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    assert resolved["run_id"] == "payload-test"
    assert resolved["model_id"] == "example/model"
    assert resolved["seed"] == 42
    for path in (
        run_dir / "resolved_config.yaml",
        run_dir / "environment.json",
        run_dir / "run.json",
        run_dir / "metrics.jsonl",
        run_dir / "stdout.log",
        run_dir / "stderr.log",
    ):
        assert "PRIVATE_COMPLETION_SENTINEL" not in path.read_text(encoding="utf-8")
    assert "PRIVATE_COMPLETION_SENTINEL" in summary.results_path.read_text(encoding="utf-8")


def test_resume_rejects_checkpoint_seed_or_dataset_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_problems = [_problem("p1", "ONE")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: original_problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("DRIFT_BASE")]),
        executor=MockExecutor([_pass_result(), _pass_result(), _pass_result()]),
        run_id="drift-test",
        output_root=output_root,
        seed=42,
    )

    with pytest.raises(EvaluationError):
        run_pass1_evaluation(
            config=replace(config, checkpoint="other"),
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="drift-test",
            output_root=output_root,
            seed=42,
        )
    with pytest.raises(EvaluationError):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="drift-test",
            output_root=output_root,
            seed=43,
        )

    changed_problems = [_problem("p1", "CHANGED")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: changed_problems)
    with pytest.raises(EvaluationError):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="drift-test",
            output_root=output_root,
            seed=42,
        )


def test_resume_rejects_nonfinite_or_out_of_order_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE"), _problem("p2", "TWO")]
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    summary = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ROW_ONE"), _completion("ROW_TWO")]),
        executor=MockExecutor([_pass_result() for _ in range(6)]),
        run_id="row-test",
        output_root=output_root,
        seed=42,
    )
    rows = [json.loads(line) for line in summary.results_path.read_text(encoding="utf-8").splitlines()]
    rows[0], rows[1] = rows[1], rows[0]
    serialized_rows = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    summary.results_path.write_text(serialized_rows, encoding="utf-8")
    with pytest.raises(EvaluationError, match="exact expected resume prefix"):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="row-test",
            output_root=output_root,
            seed=42,
        )

    rows[0], rows[1] = rows[1], rows[0]
    rows[0]["runtime_ms"] = float("nan")
    summary.results_path.write_text(json.dumps(rows[0], allow_nan=True) + "\n", encoding="utf-8")
    with pytest.raises(EvaluationError, match="finite non-negative"):
        run_pass1_evaluation(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([]),
            executor=MockExecutor([]),
            run_id="row-test",
            output_root=output_root,
            seed=42,
        )


def test_load_evaluation_problems_rejects_missing_hf_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        evaluation_module,
        "check_prepared_data",
        lambda dataset_dir: SimpleNamespace(hf_dataset_dir=None),
    )
    with pytest.raises(EvaluationError, match="hf_dataset"):
        evaluation_module.load_evaluation_problems(_config(tmp_path))
