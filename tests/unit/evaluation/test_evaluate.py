"""Tests for strict WP5 evaluation configuration and records."""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace
from pathlib import Path

import pytest

from code_verifier.data.schema import CodeProblem, ProblemMetadata
from code_verifier.data.schema import TestCase as CodeTestCase
from code_verifier.evaluation.evaluate import (
    EvaluationError,
    EvaluationRecord,
    classify_evaluation_error,
    dataset_hash,
    evaluate_completion,
    evaluation_config_from_mapping,
    evaluation_record_from_mapping,
    evaluation_record_to_mapping,
    load_evaluation_config,
    load_evaluation_records,
)
from code_verifier.evaluation.generate import GenerationResult, build_evaluation_prompt
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.base import TestCaseResult as ExecutionTestCaseResult
from code_verifier.execution.mock import MockExecutor


def _problem() -> CodeProblem:
    return CodeProblem(
        problem_id="problem-1",
        source="unit",
        split="test",
        prompt="Return the input.",
        function_name="solve",
        function_signature="def solve(x):",
        starter_code=None,
        visible_tests=(CodeTestCase(input="VISIBLE_SENTINEL", expected=1),),
        train_hidden_tests=(CodeTestCase(input="TRAIN_SENTINEL", expected=2),),
        eval_hidden_tests=(CodeTestCase(input="EVAL_SENTINEL", expected=3),),
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


def _execution_result(status: ExecutionStatus, *, runtime_ms: float) -> ExecutionResult:
    passed = status is ExecutionStatus.PASSED
    test_result = ExecutionTestCaseResult(
        status=status,
        passed=passed,
        runtime_ms=runtime_ms,
        stdout="",
        stderr="",
    )
    return ExecutionResult(
        status=status,
        passed_tests=1 if passed else 0,
        total_tests=1,
        pass_rate=1.0 if passed else 0.0,
        runtime_ms=runtime_ms,
        test_results=[test_result],
    )


def _config_mapping() -> dict[str, object]:
    return {
        "dataset_dir": "data/processed/wp1-smoke",
        "split": "test",
        "piston_config": "configs/execution/piston-local.yaml",
        "model_revision": None,
        "checkpoint": "base",
        "device": "auto",
        "generation": {
            "do_sample": False,
            "temperature": None,
            "top_p": None,
            "max_new_tokens": 512,
            "dtype": "auto",
        },
    }


def _record() -> EvaluationRecord:
    return EvaluationRecord(
        run_id="run-1",
        model_id="model-1",
        checkpoint="base",
        dataset_hash="d" * 64,
        config_hash="c" * 64,
        problem_id="problem-1",
        prompt_hash="p" * 64,
        completion="```python\ndef solve(x):\n    return x\n```",
        extracted_code="def solve(x):\n    return x\n",
        parse_success=True,
        target_function_found=True,
        visible_pass_rate=1.0,
        train_hidden_pass_rate=0.5,
        eval_hidden_pass_rate=0.0,
        execution_status="wrong_answer",
        visible_execution_status="passed",
        train_hidden_execution_status="wrong_answer",
        eval_hidden_execution_status="wrong_answer",
        visible_failure_counts={},
        train_hidden_failure_counts={"wrong_answer": 1},
        eval_hidden_failure_counts={"wrong_answer": 2},
        parse_error_type=None,
        runtime_ms=3.5,
        generation_latency_ms=10.0,
        completion_tokens=12,
        error_category_auto="visible_only_success",
    )


def test_load_evaluation_config_accepts_pass1_yaml() -> None:
    config = load_evaluation_config(Path("configs/eval/pass1.yaml"))
    assert config.split == "test"
    assert config.generation.max_new_tokens == 512
    assert config.dataset_dir == Path.cwd() / "data/processed/wp1-smoke"


def test_load_evaluation_config_accepts_immutable_base_yaml() -> None:
    config = load_evaluation_config(Path("configs/eval/base.yaml"))

    assert config.split == "test"
    assert config.device == "cuda"
    assert config.generation.dtype == "float16"
    assert config.model_revision is not None
    assert re.fullmatch(r"[0-9a-f]{40}", config.model_revision)


@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_evaluation_config_rejects_unknown_or_missing_keys(mutation: str) -> None:
    mapping = _config_mapping()
    if mutation == "unknown":
        mapping["extra"] = True
    else:
        del mapping["checkpoint"]
    with pytest.raises(EvaluationError):
        evaluation_config_from_mapping(mapping)


def test_evaluation_config_rejects_training_split() -> None:
    mapping = _config_mapping()
    mapping["split"] = "train"
    with pytest.raises(EvaluationError, match="validation or test"):
        evaluation_config_from_mapping(mapping)


def test_pass1_config_uses_float16_for_gpu_debug_evaluation() -> None:
    """The 1660 Ti debug evaluation config must explicitly load in FP16."""
    config = load_evaluation_config(Path("configs/eval/pass1.yaml"))
    assert config.generation.dtype == "float16"


def test_evaluation_record_round_trip_is_exact_and_json_safe() -> None:
    record = _record()
    mapping = evaluation_record_to_mapping(record)
    assert evaluation_record_from_mapping(mapping) == record
    json.dumps(mapping, allow_nan=False)


def test_load_evaluation_records_round_trips_strict_rows(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    rows = [_record(), replace(_record(), problem_id="problem-2")]
    path.write_text(
        "".join(json.dumps(evaluation_record_to_mapping(row), allow_nan=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    assert load_evaluation_records(path) == rows
    path.write_text("", encoding="utf-8")
    assert load_evaluation_records(path) == []


@pytest.mark.parametrize(
    "content",
    [
        b"\n",
        b"{\n",
        b'{"duplicate": 1, "duplicate": 2}\n',
        b'{"unknown": true}\n',
        b"\xff\n",
    ],
)
def test_load_evaluation_records_rejects_blank_invalid_or_unknown_rows(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "results.jsonl"
    path.write_bytes(content)

    with pytest.raises(EvaluationError):
        load_evaluation_records(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("visible_pass_rate", math.nan),
        ("train_hidden_pass_rate", math.inf),
        ("eval_hidden_pass_rate", 1.1),
        ("runtime_ms", -1.0),
        ("generation_latency_ms", math.inf),
    ],
)
def test_evaluation_record_rejects_nan_inf_and_out_of_range_rates(field: str, value: float) -> None:
    mapping = evaluation_record_to_mapping(_record())
    mapping[field] = value
    with pytest.raises(EvaluationError):
        evaluation_record_from_mapping(mapping)


def test_evaluation_record_rejects_unknown_status_or_failure_count() -> None:
    mapping = evaluation_record_to_mapping(_record())
    mapping["execution_status"] = "mystery"
    with pytest.raises(EvaluationError):
        evaluation_record_from_mapping(mapping)

    mapping = evaluation_record_to_mapping(_record())
    mapping["eval_hidden_failure_counts"] = {"passed": 1}
    with pytest.raises(EvaluationError):
        evaluation_record_from_mapping(mapping)


def test_evaluation_record_mapping_contains_no_test_payload_keys() -> None:
    mapping = evaluation_record_to_mapping(replace(_record(), completion="VISIBLE_COMPLETION_SENTINEL"))
    forbidden = {"tests", "expected", "metadata", "reference_solution", "stdout", "stderr"}
    assert forbidden.isdisjoint(mapping)


def test_evaluate_completion_verifies_all_three_layers_and_uses_eval_status() -> None:
    problem = _problem()
    executor = MockExecutor(
        [
            _execution_result(ExecutionStatus.PASSED, runtime_ms=1.0),
            _execution_result(ExecutionStatus.WRONG_ANSWER, runtime_ms=2.0),
            _execution_result(ExecutionStatus.WRONG_ANSWER, runtime_ms=3.0),
        ]
    )
    generation = GenerationResult(
        completion="```python\ndef solve(x):\n    return x\n```",
        completion_tokens=9,
        latency_ms=4.0,
    )
    prompt = build_evaluation_prompt(problem)

    record = evaluate_completion(
        run_id="run-1",
        model_id="model-1",
        checkpoint="base",
        dataset_hash_value=dataset_hash([problem]),
        config_hash="c" * 64,
        problem=problem,
        prompt=prompt,
        generation=generation,
        executor=executor,
    )

    assert len(executor.calls) == 3
    assert executor.calls[0].tests[0]["input"] == "VISIBLE_SENTINEL"
    assert executor.calls[1].tests[0]["input"] == "TRAIN_SENTINEL"
    assert executor.calls[2].tests[0]["input"] == "EVAL_SENTINEL"
    assert record.visible_execution_status == "passed"
    assert record.train_hidden_execution_status == "wrong_answer"
    assert record.eval_hidden_execution_status == "wrong_answer"
    assert record.execution_status == record.eval_hidden_execution_status
    assert record.runtime_ms == 6.0
    assert record.error_category_auto == "visible_only_success"


def test_evaluate_completion_parse_failure_makes_zero_executor_calls() -> None:
    problem = _problem()
    executor = MockExecutor([])
    generation = GenerationResult(completion="not fenced code", completion_tokens=3, latency_ms=1.0)
    record = evaluate_completion(
        run_id="run-1",
        model_id="model-1",
        checkpoint="base",
        dataset_hash_value=dataset_hash([problem]),
        config_hash="c" * 64,
        problem=problem,
        prompt=build_evaluation_prompt(problem),
        generation=generation,
        executor=executor,
    )

    assert executor.calls == ()
    assert record.parse_success is False
    assert record.extracted_code == ""
    assert record.execution_status == "parse_error"
    assert record.error_category_auto == "parse_error:no_supported_code_block"
    assert record.runtime_ms == 0.0


def test_classify_evaluation_error_prioritizes_sandbox_before_gaps() -> None:
    assert (
        classify_evaluation_error(
            parse_error_type=None,
            visible_pass_rate=1.0,
            eval_hidden_pass_rate=0.0,
            eval_hidden_status=ExecutionStatus.SANDBOX_ERROR,
        )
        == "sandbox_failure"
    )
