"""Tests for strict problem-level WP5 aggregate metrics."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from code_verifier.evaluation.evaluate import EvaluationRecord
from code_verifier.evaluation.metrics import (
    EvaluationAggregate,
    MetricsError,
    aggregate_evaluation_records,
    evaluation_aggregate_to_mapping,
)


def _record(problem_id: str, **changes: object) -> EvaluationRecord:
    values: dict[str, object] = {
        "run_id": "run-1",
        "model_id": "model-1",
        "checkpoint": "base",
        "dataset_hash": "d" * 64,
        "config_hash": "c" * 64,
        "problem_id": problem_id,
        "prompt_hash": problem_id * 8,
        "completion": "PRIVATE_COMPLETION",
        "extracted_code": "PRIVATE_CODE",
        "parse_success": True,
        "target_function_found": True,
        "visible_pass_rate": 1.0,
        "train_hidden_pass_rate": 1.0,
        "eval_hidden_pass_rate": 1.0,
        "execution_status": "passed",
        "visible_execution_status": "passed",
        "train_hidden_execution_status": "passed",
        "eval_hidden_execution_status": "passed",
        "visible_failure_counts": {},
        "train_hidden_failure_counts": {},
        "eval_hidden_failure_counts": {},
        "parse_error_type": None,
        "runtime_ms": 1.0,
        "generation_latency_ms": 10.0,
        "completion_tokens": 10,
        "error_category_auto": "passed",
    }
    values.update(changes)
    return EvaluationRecord(**values)  # type: ignore[arg-type]


def _aggregate(records: list[EvaluationRecord]) -> EvaluationAggregate:
    return aggregate_evaluation_records(records, bootstrap_seed=42, bootstrap_resamples=200)


def test_aggregate_metrics_matches_exact_problem_level_definitions() -> None:
    records = [
        _record("p1", completion_tokens=10, generation_latency_ms=10.0, runtime_ms=1.0),
        _record(
            "p2",
            visible_pass_rate=1.0,
            train_hidden_pass_rate=0.5,
            eval_hidden_pass_rate=0.5,
            execution_status="wrong_answer",
            eval_hidden_execution_status="wrong_answer",
            eval_hidden_failure_counts={"wrong_answer": 3},
            completion_tokens=20,
            generation_latency_ms=20.0,
            runtime_ms=3.0,
            error_category_auto="visible_only_success",
        ),
        _record(
            "p3",
            parse_success=False,
            target_function_found=False,
            visible_pass_rate=0.0,
            train_hidden_pass_rate=0.0,
            eval_hidden_pass_rate=0.0,
            execution_status="parse_error",
            visible_execution_status="parse_error",
            train_hidden_execution_status="parse_error",
            eval_hidden_execution_status="parse_error",
            parse_error_type="no_code",
            completion_tokens=30,
            generation_latency_ms=30.0,
            runtime_ms=5.0,
            error_category_auto="parse_error:no_code",
        ),
    ]

    metrics = _aggregate(records).metrics

    assert metrics.total_problems == 3
    assert metrics.parse_success_rate == pytest.approx(2 / 3)
    assert metrics.target_function_found_rate == pytest.approx(2 / 3)
    assert metrics.visible_pass_at_1 == pytest.approx(2 / 3)
    assert metrics.train_hidden_pass_at_1 == pytest.approx(1 / 3)
    assert metrics.eval_hidden_pass_at_1 == pytest.approx(1 / 3)
    assert metrics.eval_hidden_average_test_pass_rate == 0.5
    assert metrics.public_eval_gap == pytest.approx(1 / 3)
    assert metrics.mean_completion_tokens == 20.0
    assert metrics.p50_completion_tokens == 20.0
    assert metrics.p95_completion_tokens == 29.0
    assert metrics.mean_generation_latency_ms == 20.0
    assert metrics.mean_execution_runtime_ms == 3.0


def test_executable_rate_matches_verification_executed_semantics() -> None:
    records = [
        _record("p1"),
        _record("p2", execution_status="syntax_error", eval_hidden_execution_status="syntax_error"),
        _record(
            "p3",
            execution_status="sandbox_error",
            eval_hidden_execution_status="sandbox_error",
            error_category_auto="sandbox_failure",
        ),
        _record(
            "p4",
            parse_success=False,
            target_function_found=False,
            execution_status="parse_error",
            visible_execution_status="parse_error",
            train_hidden_execution_status="parse_error",
            eval_hidden_execution_status="parse_error",
            parse_error_type="missing",
            error_category_auto="parse_error:missing",
        ),
    ]

    assert _aggregate(records).metrics.executable_rate == 0.5


def test_error_rates_use_problem_not_test_case_weighting() -> None:
    records = [
        _record(
            "p1",
            execution_status="wrong_answer",
            eval_hidden_execution_status="wrong_answer",
            eval_hidden_failure_counts={"syntax_error": 99, "runtime_error": 1},
        ),
        _record("p2", execution_status="timeout", eval_hidden_execution_status="timeout"),
        _record("p3"),
    ]

    metrics = _aggregate(records).metrics

    assert metrics.syntax_error_rate == pytest.approx(1 / 3)
    assert metrics.runtime_error_rate == pytest.approx(1 / 3)
    assert metrics.timeout_rate == pytest.approx(1 / 3)


def test_pass_at_1_is_not_average_test_pass_rate() -> None:
    metrics = _aggregate([_record("p1", eval_hidden_pass_rate=0.5)]).metrics

    assert metrics.eval_hidden_pass_at_1 == 0.0
    assert metrics.eval_hidden_average_test_pass_rate == 0.5


def test_public_eval_gap_and_ci_preserve_pairing() -> None:
    records = [
        _record("p1", visible_pass_rate=1.0, eval_hidden_pass_rate=0.0),
        _record("p2", visible_pass_rate=0.0, eval_hidden_pass_rate=1.0),
    ]

    aggregate = _aggregate(records)

    assert aggregate.metrics.public_eval_gap == 0.0
    assert aggregate.confidence_intervals["public_eval_gap"].estimate == 0.0


@pytest.mark.parametrize(
    "records",
    [
        [],
        [_record("p1"), _record("p1")],
        [_record("p1"), replace(_record("p2"), run_id="other")],
        [_record("p1"), replace(_record("p2"), model_id="other")],
        [_record("p1"), replace(_record("p2"), checkpoint="other")],
        [_record("p1"), replace(_record("p2"), dataset_hash="other")],
        [_record("p1"), replace(_record("p2"), config_hash="other")],
    ],
)
def test_aggregate_rejects_empty_duplicates_and_mixed_identity(records: list[EvaluationRecord]) -> None:
    with pytest.raises(MetricsError):
        _aggregate(records)


def test_error_category_and_execution_status_counts_cover_all_records() -> None:
    records = [
        _record("p1"),
        _record(
            "p2",
            execution_status="wrong_answer",
            eval_hidden_execution_status="wrong_answer",
            error_category_auto="visible_only_success",
        ),
    ]

    metrics = _aggregate(records).metrics

    assert metrics.error_category_counts == {"passed": 1, "visible_only_success": 1}
    assert metrics.execution_status_counts == {"passed": 1, "wrong_answer": 1}
    assert sum(metrics.error_category_counts.values()) == metrics.total_problems
    assert sum(metrics.execution_status_counts.values()) == metrics.total_problems


def test_metric_mapping_is_finite_json_safe_and_payload_free() -> None:
    mapping = evaluation_aggregate_to_mapping(_aggregate([_record("p1")]))
    serialized = json.dumps(mapping, allow_nan=False)
    metrics_mapping = mapping["metrics"]

    assert "PRIVATE_COMPLETION" not in serialized
    assert "PRIVATE_CODE" not in serialized
    assert isinstance(metrics_mapping, dict)
    assert all(key in metrics_mapping for key in ("visible_pass@1", "eval_hidden_pass@1", "public_eval_gap"))
