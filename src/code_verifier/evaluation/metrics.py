"""Strict problem-level aggregate metrics for completed WP5 evaluations."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from code_verifier.evaluation.bootstrap import (
    BootstrapError,
    BootstrapInterval,
    _linear_quantile,
    bootstrap_mean_interval,
    paired_bootstrap_difference,
)
from code_verifier.evaluation.evaluate import EvaluationRecord
from code_verifier.execution.base import ExecutionStatus


class MetricsError(RuntimeError):
    """Raised when evaluation records cannot form one trustworthy aggregate."""


@dataclass(frozen=True)
class EvaluationMetrics:
    """WP5 metrics computed at one-record-per-problem granularity."""

    total_problems: int
    parse_success_rate: float
    target_function_found_rate: float
    executable_rate: float
    syntax_error_rate: float
    runtime_error_rate: float
    timeout_rate: float
    visible_pass_at_1: float
    train_hidden_pass_at_1: float
    eval_hidden_pass_at_1: float
    eval_hidden_average_test_pass_rate: float
    public_eval_gap: float
    mean_completion_tokens: float
    p50_completion_tokens: float
    p95_completion_tokens: float
    mean_generation_latency_ms: float
    mean_execution_runtime_ms: float
    error_category_counts: dict[str, int]
    execution_status_counts: dict[str, int]


@dataclass(frozen=True)
class EvaluationAggregate:
    """Point metrics and deterministic problem-level confidence intervals."""

    metrics: EvaluationMetrics
    confidence_intervals: dict[str, BootstrapInterval]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _indicator(value: bool) -> float:
    return 1.0 if value else 0.0


def _problem_has_status(record: EvaluationRecord, status: ExecutionStatus) -> float:
    return _indicator(
        record.eval_hidden_execution_status == status.value
        or record.eval_hidden_failure_counts.get(status.value, 0) > 0
    )


def _validate_records(records: Sequence[EvaluationRecord]) -> tuple[EvaluationRecord, ...]:
    if not records:
        raise MetricsError("evaluation records must be non-empty")
    record_tuple = tuple(records)
    problem_ids = [record.problem_id for record in record_tuple]
    if len(problem_ids) != len(set(problem_ids)):
        raise MetricsError("evaluation records contain duplicate problem_id values")
    identity_fields = ("run_id", "model_id", "checkpoint", "dataset_hash", "config_hash")
    for field_name in identity_fields:
        if len({getattr(record, field_name) for record in record_tuple}) != 1:
            raise MetricsError(f"evaluation records contain mixed {field_name} identity")
    return record_tuple


def aggregate_evaluation_records(
    records: Sequence[EvaluationRecord],
    *,
    bootstrap_seed: int,
    bootstrap_resamples: int = 10_000,
    confidence_level: float = 0.95,
) -> EvaluationAggregate:
    """Compute WP5 metrics and confidence intervals from strict per-problem records."""
    rows = _validate_records(records)
    parse_success = [_indicator(record.parse_success) for record in rows]
    target_found = [_indicator(record.target_function_found) for record in rows]
    executable = [
        _indicator(record.parse_success and record.eval_hidden_execution_status != ExecutionStatus.SANDBOX_ERROR.value)
        for record in rows
    ]
    syntax_errors = [_problem_has_status(record, ExecutionStatus.SYNTAX_ERROR) for record in rows]
    runtime_errors = [_problem_has_status(record, ExecutionStatus.RUNTIME_ERROR) for record in rows]
    timeouts = [_problem_has_status(record, ExecutionStatus.TIMEOUT) for record in rows]
    visible_whole_pass = [_indicator(record.visible_pass_rate == 1.0) for record in rows]
    train_hidden_whole_pass = [_indicator(record.train_hidden_pass_rate == 1.0) for record in rows]
    eval_hidden_whole_pass = [_indicator(record.eval_hidden_pass_rate == 1.0) for record in rows]
    eval_hidden_test_pass_rates = [record.eval_hidden_pass_rate for record in rows]
    completion_tokens = [float(record.completion_tokens) for record in rows]
    sorted_completion_tokens = sorted(completion_tokens)
    error_category_counts = dict(sorted(Counter(record.error_category_auto for record in rows).items()))
    execution_status_counts = dict(sorted(Counter(record.execution_status for record in rows).items()))
    metrics = EvaluationMetrics(
        total_problems=len(rows),
        parse_success_rate=_mean(parse_success),
        target_function_found_rate=_mean(target_found),
        executable_rate=_mean(executable),
        syntax_error_rate=_mean(syntax_errors),
        runtime_error_rate=_mean(runtime_errors),
        timeout_rate=_mean(timeouts),
        visible_pass_at_1=_mean(visible_whole_pass),
        train_hidden_pass_at_1=_mean(train_hidden_whole_pass),
        eval_hidden_pass_at_1=_mean(eval_hidden_whole_pass),
        eval_hidden_average_test_pass_rate=_mean(eval_hidden_test_pass_rates),
        public_eval_gap=_mean(visible_whole_pass) - _mean(eval_hidden_whole_pass),
        mean_completion_tokens=_mean(completion_tokens),
        p50_completion_tokens=_linear_quantile(sorted_completion_tokens, 0.50),
        p95_completion_tokens=_linear_quantile(sorted_completion_tokens, 0.95),
        mean_generation_latency_ms=_mean([record.generation_latency_ms for record in rows]),
        mean_execution_runtime_ms=_mean([record.runtime_ms for record in rows]),
        error_category_counts=error_category_counts,
        execution_status_counts=execution_status_counts,
    )
    try:
        intervals = {
            "visible_pass@1": bootstrap_mean_interval(
                visible_whole_pass,
                seed=bootstrap_seed,
                resamples=bootstrap_resamples,
                confidence_level=confidence_level,
            ),
            "train_hidden_pass@1": bootstrap_mean_interval(
                train_hidden_whole_pass,
                seed=bootstrap_seed,
                resamples=bootstrap_resamples,
                confidence_level=confidence_level,
            ),
            "eval_hidden_pass@1": bootstrap_mean_interval(
                eval_hidden_whole_pass,
                seed=bootstrap_seed,
                resamples=bootstrap_resamples,
                confidence_level=confidence_level,
            ),
            "eval_hidden_average_test_pass_rate": bootstrap_mean_interval(
                eval_hidden_test_pass_rates,
                seed=bootstrap_seed,
                resamples=bootstrap_resamples,
                confidence_level=confidence_level,
            ),
            "public_eval_gap": paired_bootstrap_difference(
                visible_whole_pass,
                eval_hidden_whole_pass,
                seed=bootstrap_seed,
                resamples=bootstrap_resamples,
                confidence_level=confidence_level,
            ),
        }
    except BootstrapError as error:
        raise MetricsError(str(error)) from None
    aggregate = EvaluationAggregate(metrics=metrics, confidence_intervals=intervals)
    evaluation_aggregate_to_mapping(aggregate)
    return aggregate


def evaluation_aggregate_to_mapping(aggregate: EvaluationAggregate) -> dict[str, object]:
    """Serialize aggregate metrics with specification-facing names and finite JSON values."""
    metrics = aggregate.metrics
    metrics_mapping: dict[str, object] = {
        "total_problems": metrics.total_problems,
        "parse_success_rate": metrics.parse_success_rate,
        "target_function_found_rate": metrics.target_function_found_rate,
        "executable_rate": metrics.executable_rate,
        "syntax_error_rate": metrics.syntax_error_rate,
        "runtime_error_rate": metrics.runtime_error_rate,
        "timeout_rate": metrics.timeout_rate,
        "visible_pass@1": metrics.visible_pass_at_1,
        "train_hidden_pass@1": metrics.train_hidden_pass_at_1,
        "eval_hidden_pass@1": metrics.eval_hidden_pass_at_1,
        "eval_hidden_average_test_pass_rate": metrics.eval_hidden_average_test_pass_rate,
        "public_eval_gap": metrics.public_eval_gap,
        "mean_completion_tokens": metrics.mean_completion_tokens,
        "p50_completion_tokens": metrics.p50_completion_tokens,
        "p95_completion_tokens": metrics.p95_completion_tokens,
        "mean_generation_latency_ms": metrics.mean_generation_latency_ms,
        "mean_execution_runtime_ms": metrics.mean_execution_runtime_ms,
        "error_category_counts": dict(metrics.error_category_counts),
        "execution_status_counts": dict(metrics.execution_status_counts),
    }
    mapping: dict[str, object] = {
        "metrics": metrics_mapping,
        "confidence_intervals": {
            name: asdict(interval) for name, interval in sorted(aggregate.confidence_intervals.items())
        },
    }
    try:
        json.dumps(mapping, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        raise MetricsError("evaluation aggregate must contain only finite JSON-safe values") from None
    if not all(
        math.isfinite(value)
        for value in metrics_mapping.values()
        if isinstance(value, float) and not isinstance(value, bool)
    ):
        raise MetricsError("evaluation aggregate must contain only finite JSON-safe values")
    return mapping
