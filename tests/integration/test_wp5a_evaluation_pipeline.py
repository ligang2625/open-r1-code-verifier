"""End-to-end WP5-a evaluation test with prepared HF data and fake runtime dependencies."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from code_verifier.data.prepare import load_data_preparation_config, prepare_data
from code_verifier.data.schema import test_case_to_mapping as case_to_mapping
from code_verifier.evaluation.evaluate import EvaluationConfig, load_evaluation_problems, run_pass1_evaluation
from code_verifier.evaluation.generate import GenerationConfig, GenerationError, GenerationResult
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.base import TestCaseResult as ExecutionTestCaseResult
from code_verifier.execution.mock import MockExecutor


class _PromptAwareGenerator:
    def __init__(self, *, fail_after: int | None = None, parse_failure_at: int | None = None) -> None:
        self.fail_after = fail_after
        self.parse_failure_at = parse_failure_at
        self.prompts: list[str] = []
        self.seeds: list[int] = []

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        call_index = len(self.prompts)
        if self.fail_after is not None and call_index >= self.fail_after:
            raise GenerationError("integration interruption")
        self.prompts.append(prompt)
        self.seeds.append(seed)
        if self.parse_failure_at == call_index:
            return GenerationResult(completion="analysis only", completion_tokens=2, latency_ms=1.0)
        match = re.search(r"Function signature:\n(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", prompt)
        if match is None:
            raise AssertionError("evaluation prompt did not contain the function signature")
        function_name = match.group(1)
        completion = f"```python\ndef {function_name}(*args, **kwargs):\n    return None\n```"
        return GenerationResult(completion=completion, completion_tokens=10, latency_ms=1.0)


def _execution_result(status: ExecutionStatus) -> ExecutionResult:
    passed = status is ExecutionStatus.PASSED
    test_results = [
        ExecutionTestCaseResult(
            status=status,
            passed=passed,
            runtime_ms=0.5,
            stdout="",
            stderr="",
        )
        for _ in range(2)
    ]
    return ExecutionResult(
        status=status,
        passed_tests=2 if passed else 0,
        total_tests=2,
        pass_rate=1.0 if passed else 0.0,
        runtime_ms=1.0,
        test_results=test_results,
    )


def test_prepared_hf_evaluation_interrupts_resumes_and_writes_exact_rows(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    prepare_data(
        load_data_preparation_config(Path("configs/data/smoke.yaml")),
        seed=42,
        output_dir=prepared,
    )
    config = EvaluationConfig(
        dataset_dir=prepared,
        split="test",
        piston_config=Path("configs/execution/piston-local.yaml").resolve(),
        model_revision=None,
        checkpoint="base",
        device="cpu",
        generation=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=512),
    )
    problems = load_evaluation_problems(config)
    assert len(problems) == 4
    output_root = tmp_path / "outputs"
    first_count = len(problems) // 2
    first_generator = _PromptAwareGenerator(fail_after=first_count)
    first_executor = MockExecutor(
        [
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.WRONG_ANSWER),
            _execution_result(ExecutionStatus.WRONG_ANSWER),
        ]
    )

    with pytest.raises(GenerationError, match="integration interruption"):
        run_pass1_evaluation(
            config=config,
            model_id="fake/integration-model",
            generator=first_generator,
            executor=first_executor,
            run_id="integration-resume",
            output_root=output_root,
            seed=42,
        )

    second_generator = _PromptAwareGenerator(parse_failure_at=1)
    remaining = len(problems) - first_count
    second_executor = MockExecutor(
        [
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.TIMEOUT),
        ]
    )
    summary = run_pass1_evaluation(
        config=config,
        model_id="fake/integration-model",
        generator=second_generator,
        executor=second_executor,
        run_id="integration-resume",
        output_root=output_root,
        seed=42,
    )

    assert summary.completed_before_run == first_count
    assert summary.generated_this_run == remaining
    assert len(first_generator.prompts) == first_count
    assert len(second_generator.prompts) == remaining
    assert len(first_executor.calls) == 6
    assert len(second_executor.calls) == 3
    all_prompts = first_generator.prompts + second_generator.prompts
    assert first_generator.seeds + second_generator.seeds == [42] * len(problems)
    for problem, prompt in zip(problems, all_prompts, strict=True):
        assert "train_hidden_tests" not in prompt
        assert "eval_hidden_tests" not in prompt
        assert "reference_solution" not in prompt
        assert "sft_response" not in prompt
        for test_case in problem.eval_hidden_tests:
            hidden_payload = json.dumps(
                case_to_mapping(test_case),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            assert hidden_payload not in prompt

    rows = [json.loads(line) for line in summary.results_path.read_text(encoding="utf-8").splitlines()]
    assert [row["problem_id"] for row in rows] == [problem.problem_id for problem in problems]
    assert len({row["problem_id"] for row in rows}) == len(problems)
    expected_fields = {
        "run_id",
        "model_id",
        "checkpoint",
        "dataset_hash",
        "config_hash",
        "problem_id",
        "prompt_hash",
        "completion",
        "extracted_code",
        "parse_success",
        "target_function_found",
        "visible_pass_rate",
        "train_hidden_pass_rate",
        "eval_hidden_pass_rate",
        "execution_status",
        "visible_execution_status",
        "train_hidden_execution_status",
        "eval_hidden_execution_status",
        "visible_failure_counts",
        "train_hidden_failure_counts",
        "eval_hidden_failure_counts",
        "parse_error_type",
        "runtime_ms",
        "generation_latency_ms",
        "completion_tokens",
        "error_category_auto",
    }
    assert all(set(row) == expected_fields for row in rows)
    assert [row["execution_status"] for row in rows] == [
        "passed",
        "wrong_answer",
        "timeout",
        "parse_error",
    ]
    assert rows[1]["error_category_auto"] == "visible_only_success"
    assert rows[2]["error_category_auto"] == "timeout"
    assert str(rows[3]["error_category_auto"]).startswith("parse_error:")
    assert all(row["execution_status"] == row["eval_hidden_execution_status"] for row in rows)

    run_dir = summary.results_path.parents[1]
    assert {path.name for path in run_dir.iterdir()} == {
        "resolved_config.yaml",
        "environment.json",
        "run.json",
        "metrics.jsonl",
        "stdout.log",
        "stderr.log",
        "samples",
    }
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["status"] == "completed"
    non_result_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            run_dir / "resolved_config.yaml",
            run_dir / "environment.json",
            run_dir / "run.json",
            run_dir / "metrics.jsonl",
            run_dir / "stdout.log",
            run_dir / "stderr.log",
        )
    )
    for problem in problems:
        for test_case in problem.eval_hidden_tests:
            hidden_payload = json.dumps(
                case_to_mapping(test_case),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            assert hidden_payload not in non_result_text

    third_generator = _PromptAwareGenerator(fail_after=0)
    completed = run_pass1_evaluation(
        config=config,
        model_id="fake/integration-model",
        generator=third_generator,
        executor=MockExecutor([]),
        run_id="integration-resume",
        output_root=output_root,
        seed=42,
    )
    assert completed.completed_before_run == len(problems)
    assert completed.generated_this_run == 0
    assert third_generator.prompts == []

    repeat_generator = _PromptAwareGenerator(parse_failure_at=3)
    repeat_executor = MockExecutor(
        [
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.WRONG_ANSWER),
            _execution_result(ExecutionStatus.WRONG_ANSWER),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.PASSED),
            _execution_result(ExecutionStatus.TIMEOUT),
        ]
    )
    repeated = run_pass1_evaluation(
        config=config,
        model_id="fake/integration-model",
        generator=repeat_generator,
        executor=repeat_executor,
        run_id="integration-repeat",
        output_root=output_root,
        seed=42,
    )
    repeat_rows = [json.loads(line) for line in repeated.results_path.read_text(encoding="utf-8").splitlines()]
    assert repeat_generator.seeds == [42] * len(problems)
    for original, repeated_row in zip(rows, repeat_rows, strict=True):
        original_identity = {key: value for key, value in original.items() if key != "run_id"}
        repeated_identity = {key: value for key, value in repeated_row.items() if key != "run_id"}
        assert repeated_identity == original_identity
