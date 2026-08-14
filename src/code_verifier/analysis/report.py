"""Analysis curve, cost, manual-label, and report artifact generation."""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from code_verifier.analysis.compare import (
    FailureCandidate,
)
from code_verifier.analysis.experiment import AnalysisError
from code_verifier.data.json_strict import StrictJsonError, loads_strict


@dataclass(frozen=True)
class TrainingCurveRow:
    """One finite long-form trainer scalar."""

    method: str
    run_id: str
    record_index: int
    step: float | None
    epoch: float | None
    metric: str
    value: float


@dataclass(frozen=True)
class CostRow:
    """Auditable training cost fields without inferred unavailable quantities."""

    method: str
    run_id: str
    gpu: str
    gpu_hours: float
    rollouts: int | None
    generated_tokens: int | None
    executor_hours: float | None
    estimated_cost_usd: float | None


@dataclass(frozen=True)
class AnalysisSummary:
    """Paths and counts produced by one atomic analysis run."""

    output_dir: Path
    total_problems: int
    candidate_count: int
    manual_label_count: int
    report_data_path: Path
    main_results_path: Path
    paired_comparisons_path: Path
    cost_path: Path


_MANUAL_FIELDS = (
    "method",
    "run_id",
    "problem_id",
    "candidate_reasons",
    "auto_error_category",
    "manual_category",
    "notes",
    "source_results_path",
)
_MANUAL_CATEGORIES = {
    "hardcoded_visible_examples",
    "incomplete_algorithm",
    "missed_edge_case",
    "wrong_complexity",
    "syntax_error",
    "runtime_error",
    "timeout",
    "wrong_function_signature",
    "output_format_error",
    "state_leak_between_tests",
    "numeric_precision",
    "mutation_side_effect",
    "misunderstood_problem",
    "truncated_completion",
    "sandbox_failure",
    "test_or_label_issue",
    "other",
}
_ROLLOUT_FIELDS = {
    "item_index",
    "group_index",
    "group_item_index",
    "problem_id",
    "reward_mode",
    "completion",
    "completion_token_count",
    "truncated",
    "total_reward",
}
_REWARD_FIELDS = {
    "item_index",
    "group_index",
    "group_item_index",
    "problem_id",
    "mode",
    "test_reward",
    "executable_reward",
    "timeout_penalty",
    "invalid_format_penalty",
    "total_reward",
    "executor_runtime_ms",
    "status",
    "parsed",
    "executed",
    "infrastructure_failure",
    "passed_tests",
    "total_tests",
    "parse_error_type",
    "failure_counts",
}


def _json_object(path: Path, *, artifact_name: str) -> Mapping[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError):
        raise AnalysisError(f"{artifact_name} is unreadable or invalid") from None
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AnalysisError(f"{artifact_name} must contain one JSON object")
    return cast(Mapping[str, object], value)


def _jsonl_objects(path: Path, *, artifact_name: str) -> tuple[Mapping[str, object], ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise AnalysisError(f"{artifact_name} is unreadable or invalid") from None
    rows: list[Mapping[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            raise AnalysisError(f"{artifact_name} must not contain blank rows")
        try:
            value = loads_strict(line)
        except StrictJsonError:
            raise AnalysisError(f"{artifact_name} is unreadable or invalid") from None
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise AnalysisError(f"{artifact_name} rows must be JSON objects")
        rows.append(cast(Mapping[str, object], value))
    return tuple(rows)


def _finite(value: object, *, field_name: str, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AnalysisError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (nonnegative and number < 0.0):
        raise AnalysisError(f"{field_name} must be a finite number")
    return number


def _completed_run_metadata(run_dir: Path, *, artifact_name: str) -> Mapping[str, object]:
    metadata = _json_object(run_dir / "run.json", artifact_name=f"{artifact_name} run.json")
    if metadata.get("status") != "completed":
        raise AnalysisError(f"{artifact_name} run must be completed")
    return metadata


def load_training_curve_rows(run_dir: Path, *, method: str) -> tuple[TrainingCurveRow, ...]:
    """Load finite numeric Trainer history into deterministic long-form rows."""
    metadata = _completed_run_metadata(run_dir, artifact_name=method)
    run_id = metadata.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise AnalysisError(f"{method} run_id is invalid")
    rows: list[TrainingCurveRow] = []
    for index, entry in enumerate(_jsonl_objects(run_dir / "metrics.jsonl", artifact_name=f"{method} metrics"), 1):
        record_type = entry.get("record_type")
        if record_type == "summary":
            continue
        if record_type != "trainer":
            raise AnalysisError(f"{method} metrics contains an invalid record_type")
        step = None if "step" not in entry else _finite(entry["step"], field_name=f"{method} step")
        epoch = None if "epoch" not in entry else _finite(entry["epoch"], field_name=f"{method} epoch")
        for key, value in entry.items():
            if key in {"record_type", "step", "epoch"}:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise AnalysisError(f"{method} trainer metrics may contain only numeric scalars")
            rows.append(
                TrainingCurveRow(
                    method=method,
                    run_id=run_id,
                    record_index=index,
                    step=step,
                    epoch=epoch,
                    metric=key,
                    value=_finite(value, field_name=f"{method} metric {key}"),
                )
            )
    if not rows:
        raise AnalysisError(f"{method} completed run contains no trainer curve scalars")
    return tuple(rows)


def build_cost_row(
    run_dir: Path,
    *,
    method: str,
    gpu_hour_cost_usd: float | None,
) -> CostRow:
    """Build one cost row from completed run metadata and strict GRPO logs."""
    metadata = _completed_run_metadata(run_dir, artifact_name=method)
    run_id = metadata.get("run_id")
    gpu = metadata.get("gpu_name")
    if not isinstance(run_id, str) or not run_id.strip() or not isinstance(gpu, str) or not gpu.strip():
        raise AnalysisError(f"{method} run identity is invalid")
    gpu_hours = _finite(metadata.get("gpu_hours"), field_name=f"{method} gpu_hours", nonnegative=True)
    if gpu_hour_cost_usd is not None:
        rate = _finite(gpu_hour_cost_usd, field_name="gpu_hour_cost_usd", nonnegative=True)
        estimated = gpu_hours * rate
    else:
        estimated = None
    if method == "SFT":
        rollouts = generated_tokens = None
        executor_hours = None
    else:
        rollout_rows = _jsonl_objects(run_dir / "rollouts.jsonl", artifact_name=f"{method} rollouts")
        reward_rows = _jsonl_objects(run_dir / "rewards.jsonl", artifact_name=f"{method} rewards")
        token_total = 0
        for row in rollout_rows:
            if set(row) != _ROLLOUT_FIELDS:
                raise AnalysisError(f"{method} rollout schema is invalid")
            token_count = row["completion_token_count"]
            if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0:
                raise AnalysisError(f"{method} completion_token_count is invalid")
            token_total += token_count
        runtime_total = 0.0
        for row in reward_rows:
            if set(row) != _REWARD_FIELDS:
                raise AnalysisError(f"{method} reward schema is invalid")
            runtime_total += _finite(
                row["executor_runtime_ms"], field_name=f"{method} executor_runtime_ms", nonnegative=True
            )
        rollouts = len(rollout_rows)
        generated_tokens = token_total
        executor_hours = runtime_total / 3_600_000.0
    return CostRow(
        method=method,
        run_id=run_id,
        gpu=gpu,
        gpu_hours=gpu_hours,
        rollouts=rollouts,
        generated_tokens=generated_tokens,
        executor_hours=executor_hours,
        estimated_cost_usd=estimated,
    )


def load_manual_labels(
    path: Path,
    *,
    candidates: Sequence[FailureCandidate],
) -> tuple[Mapping[str, str], ...]:
    """Load exact human labels bound to unique known automatic candidates."""
    known = {(candidate.method, candidate.problem_id): candidate for candidate in candidates}
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _MANUAL_FIELDS:
                raise AnalysisError("manual labels CSV has invalid columns")
            rows = list(reader)
    except AnalysisError:
        raise
    except (OSError, UnicodeError, csv.Error):
        raise AnalysisError("manual labels CSV is unreadable or invalid") from None
    validated: list[Mapping[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise AnalysisError("manual labels CSV rows are invalid")
        normalized = cast(dict[str, str], row)
        key = (normalized["method"], normalized["problem_id"])
        candidate = known.get(key)
        if candidate is None or key in seen:
            raise AnalysisError("manual labels must uniquely reference known candidates")
        if normalized["run_id"] != candidate.run_id:
            raise AnalysisError("manual label run_id does not match its candidate")
        if normalized["manual_category"] not in _MANUAL_CATEGORIES:
            raise AnalysisError("manual_category is invalid")
        seen.add(key)
        validated.append(dict(normalized))
    return tuple(validated)
