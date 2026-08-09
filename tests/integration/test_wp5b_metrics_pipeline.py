"""CPU-only end-to-end regression for WP5-b aggregate artifacts."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from code_verifier.data.prepare import load_data_preparation_config, prepare_data
from code_verifier.evaluation.evaluate import EvaluationConfig, load_evaluation_problems, run_pass1_evaluation
from code_verifier.evaluation.generate import GenerationConfig, GenerationResult
from code_verifier.evaluation.metrics import EvaluationAggregateSummary, aggregate_evaluation_run
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.base import TestCaseResult as ExecutionTestCaseResult
from code_verifier.execution.mock import MockExecutor


class _Generator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        del seed
        index = self.calls
        self.calls += 1
        if index == 3:
            return GenerationResult(completion="PRIVATE_COMPLETION_SENTINEL", completion_tokens=4, latency_ms=4.0)
        match = re.search(r"Function signature:\n(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", prompt)
        if match is None:
            raise AssertionError("prompt is missing a function signature")
        function_name = match.group(1)
        completion = f"```python\n# PRIVATE_CODE_SENTINEL\ndef {function_name}(*args, **kwargs):\n    return None\n```"
        return GenerationResult(
            completion=completion,
            completion_tokens=(index + 1) * 10,
            latency_ms=float(index + 1),
        )


def _execution_result(status: ExecutionStatus) -> ExecutionResult:
    passed = status is ExecutionStatus.PASSED
    return ExecutionResult(
        status=status,
        passed_tests=2 if passed else 0,
        total_tests=2,
        pass_rate=1.0 if passed else 0.0,
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(status=status, passed=passed, runtime_ms=0.5, stdout="", stderr="")
            for _ in range(2)
        ],
    )


@dataclass(frozen=True)
class _Artifacts:
    aggregate: EvaluationAggregateSummary
    results_path: Path
    rows: list[dict[str, object]]


@pytest.fixture
def artifacts(tmp_path: Path) -> _Artifacts:
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
    generator = _Generator()
    executor = MockExecutor(
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
    run = run_pass1_evaluation(
        config=config,
        model_id="fake/wp5b-model",
        generator=generator,
        executor=executor,
        run_id="wp5b-integration",
        output_root=tmp_path / "outputs",
        seed=42,
    )
    aggregate = aggregate_evaluation_run(
        run.results_path.parents[1],
        bootstrap_seed=42,
        bootstrap_resamples=200,
    )
    rows = [json.loads(line) for line in run.results_path.read_text(encoding="utf-8").splitlines()]
    assert generator.calls == len(problems)
    return _Artifacts(aggregate=aggregate, results_path=run.results_path, rows=rows)


def test_wp5b_completed_run_generates_results_summary_and_main_table(artifacts: _Artifacts) -> None:
    assert len(artifacts.rows) == 4
    assert artifacts.aggregate.summary_path.is_file()
    assert artifacts.aggregate.main_results_path.is_file()
    summary = json.loads(artifacts.aggregate.summary_path.read_text(encoding="utf-8"))
    csv_rows = list(csv.DictReader(io.StringIO(artifacts.aggregate.main_results_path.read_text(encoding="utf-8"))))

    assert summary["bootstrap"] == {"confidence_level": 0.95, "resamples": 200, "seed": 42}
    assert sum(summary["metrics"]["error_category_counts"].values()) == 4
    assert sum(summary["metrics"]["execution_status_counts"].values()) == 4
    assert len(csv_rows) == 1


def test_wp5b_summary_metrics_trace_back_to_per_problem_rows(artifacts: _Artifacts) -> None:
    summary = json.loads(artifacts.aggregate.summary_path.read_text(encoding="utf-8"))
    metrics = summary["metrics"]
    total = len(artifacts.rows)
    visible_pass = sum(float(row["visible_pass_rate"] == 1.0) for row in artifacts.rows) / total
    eval_pass = sum(float(row["eval_hidden_pass_rate"] == 1.0) for row in artifacts.rows) / total
    average_eval_pass = sum(cast(float, row["eval_hidden_pass_rate"]) for row in artifacts.rows) / total
    executable = (
        sum(
            float(bool(row["parse_success"]) and row["eval_hidden_execution_status"] != "sandbox_error")
            for row in artifacts.rows
        )
        / total
    )

    assert metrics["visible_pass@1"] == visible_pass
    assert metrics["eval_hidden_pass@1"] == eval_pass
    assert metrics["eval_hidden_average_test_pass_rate"] == average_eval_pass
    assert metrics["public_eval_gap"] == visible_pass - eval_pass
    assert metrics["executable_rate"] == executable


def test_wp5b_same_records_and_seed_reproduce_identical_aggregate(artifacts: _Artifacts) -> None:
    first_summary = artifacts.aggregate.summary_path.read_bytes()
    first_csv = artifacts.aggregate.main_results_path.read_bytes()

    repeated = aggregate_evaluation_run(
        artifacts.results_path.parents[1],
        bootstrap_seed=42,
        bootstrap_resamples=200,
    )

    assert repeated.summary_path.read_bytes() == first_summary
    assert repeated.main_results_path.read_bytes() == first_csv


def test_wp5b_summary_artifacts_do_not_contain_sensitive_payloads(artifacts: _Artifacts) -> None:
    results_text = artifacts.results_path.read_text(encoding="utf-8")
    derived_text = artifacts.aggregate.summary_path.read_text(
        encoding="utf-8"
    ) + artifacts.aggregate.main_results_path.read_text(encoding="utf-8")

    assert "PRIVATE_COMPLETION_SENTINEL" in results_text
    assert "PRIVATE_CODE_SENTINEL" in results_text
    assert "PRIVATE_COMPLETION_SENTINEL" not in derived_text
    assert "PRIVATE_CODE_SENTINEL" not in derived_text
    for forbidden in ('"completion"', '"extracted_code"', '"tests"', '"reference_solution"', '"stdout"', '"stderr"'):
        assert forbidden not in derived_text
