"""Analysis curve, cost, manual-label, and report artifact generation."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

from code_verifier.analysis.compare import (
    FailureCandidate,
    PairedComparison,
    compare_evaluation_records,
    select_failure_candidates,
)
from code_verifier.analysis.experiment import AnalysisConfig, AnalysisError, AnalysisInputs, load_analysis_inputs
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.evaluation.bootstrap import BootstrapInterval
from code_verifier.evaluation.metrics import EvaluationAggregate, aggregate_evaluation_records


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
_REWARD_FIELDS_LEGACY = {
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
_REWARD_FIELDS = {*_REWARD_FIELDS_LEGACY, "infrastructure_failure_kind"}


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
            row_fields = set(row)
            if row_fields != _REWARD_FIELDS_LEGACY and row_fields != _REWARD_FIELDS:
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
        if normalized["candidate_reasons"] != "|".join(candidate.candidate_reasons):
            raise AnalysisError("manual label candidate_reasons does not match its candidate")
        if normalized["auto_error_category"] != candidate.auto_error_category:
            raise AnalysisError("manual label auto_error_category does not match its candidate")
        if normalized["manual_category"] not in _MANUAL_CATEGORIES:
            raise AnalysisError("manual_category is invalid")
        if not normalized["source_results_path"].strip():
            raise AnalysisError("manual label source_results_path must be non-empty")
        seen.add(key)
        validated.append(dict(normalized))
    return tuple(validated)


_ANALYSIS_LAYOUT = {
    "report_data.json",
    "main_results.csv",
    "paired_comparisons.csv",
    "auto_error_counts.csv",
    "training_curves.csv",
    "failure_candidates.jsonl",
    "manual_labels_template.csv",
    "manual_error_counts.csv",
    "costs.csv",
    "resolved_analysis.yaml",
}


def _config_mapping(config: AnalysisConfig) -> dict[str, object]:
    return {
        "base_evaluation_run_dir": str(config.base_evaluation_run_dir),
        "sft_evaluation_run_dir": str(config.sft_evaluation_run_dir),
        "public_evaluation_run_dir": str(config.public_evaluation_run_dir),
        "hidden_evaluation_run_dir": str(config.hidden_evaluation_run_dir),
        "sft_training_run_dir": str(config.sft_training_run_dir),
        "public_grpo_run_dir": str(config.public_grpo_run_dir),
        "hidden_grpo_run_dir": str(config.hidden_grpo_run_dir),
        "bootstrap": {
            "seed": config.bootstrap_seed,
            "resamples": config.bootstrap_resamples,
            "confidence_level": config.confidence_level,
        },
        "cost": {"gpu_hour_cost_usd": config.gpu_hour_cost_usd},
        "manual_labels_path": None if config.manual_labels_path is None else str(config.manual_labels_path),
    }


def _manifest_hash(config: AnalysisConfig) -> str:
    encoded = json.dumps(
        _config_mapping(config), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise AnalysisError("source results JSONL is unreadable") from None


def _write_json(path: Path, value: object) -> None:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
    except (TypeError, ValueError, OverflowError):
        raise AnalysisError("analysis output is not finite and JSON-safe") from None
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    try:
        text = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
            for row in rows
        )
    except (TypeError, ValueError, OverflowError):
        raise AnalysisError("analysis JSONL output is not finite and JSON-safe") from None
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, UnicodeError, csv.Error, ValueError):
        raise AnalysisError("analysis CSV output could not be written") from None


def _interval_mapping(interval: BootstrapInterval) -> dict[str, object]:
    return asdict(interval)


def _main_result_rows(
    inputs: AnalysisInputs,
    aggregates: Mapping[str, EvaluationAggregate],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for method in ("Base", "SFT", "Public-RLVR", "Hidden-RLVR"):
        metadata = inputs.evaluation_metadata[method]
        metrics = aggregates[method].metrics
        if method == "Public-RLVR":
            train_verifier_gap: float | None = metrics.visible_pass_at_1 - metrics.eval_hidden_pass_at_1
        elif method == "Hidden-RLVR":
            train_verifier_gap = metrics.train_hidden_pass_at_1 - metrics.eval_hidden_pass_at_1
        else:
            train_verifier_gap = None
        rows.append(
            {
                "method": method,
                "run_id": metadata["run_id"],
                "model_id": metadata["model_id"],
                "checkpoint": metadata["checkpoint"],
                "total_problems": metrics.total_problems,
                "visible_pass_at_1": metrics.visible_pass_at_1,
                "train_hidden_pass_at_1": metrics.train_hidden_pass_at_1,
                "eval_hidden_pass_at_1": metrics.eval_hidden_pass_at_1,
                "train_verifier_gap": train_verifier_gap,
                "public_eval_gap": metrics.public_eval_gap,
                "executable_rate": metrics.executable_rate,
                "timeout_rate": metrics.timeout_rate,
                "mean_completion_tokens": metrics.mean_completion_tokens,
            }
        )
    return rows


def _comparison_mapping(comparison: PairedComparison) -> dict[str, object]:
    return {
        "left_method": comparison.left_method,
        "right_method": comparison.right_method,
        "total_problems": comparison.total_problems,
        "eval_hidden_delta": comparison.eval_hidden_delta,
        "eval_hidden_ci_lower": comparison.eval_hidden_delta_ci.lower,
        "eval_hidden_ci_upper": comparison.eval_hidden_delta_ci.upper,
        "public_eval_gap_delta": comparison.public_eval_gap_delta,
        "public_eval_gap_ci_lower": comparison.public_eval_gap_delta_ci.lower,
        "public_eval_gap_ci_upper": comparison.public_eval_gap_delta_ci.upper,
        "reward_hacking_candidate_rate_delta": comparison.reward_hacking_candidate_rate_delta,
        "reward_hacking_candidate_rate_ci_lower": comparison.reward_hacking_candidate_rate_delta_ci.lower,
        "reward_hacking_candidate_rate_ci_upper": comparison.reward_hacking_candidate_rate_delta_ci.upper,
    }


def _candidate_mapping(candidate: FailureCandidate) -> dict[str, object]:
    value = asdict(candidate)
    value["candidate_reasons"] = list(candidate.candidate_reasons)
    return value


def _source_results_path(inputs: AnalysisInputs, method: str) -> Path:
    run_dirs = {
        "Base": inputs.config.base_evaluation_run_dir,
        "SFT": inputs.config.sft_evaluation_run_dir,
        "Public-RLVR": inputs.config.public_evaluation_run_dir,
        "Hidden-RLVR": inputs.config.hidden_evaluation_run_dir,
    }
    return run_dirs[method].resolve() / "samples" / "results.jsonl"


def _manual_template_rows(inputs: AnalysisInputs, candidates: Sequence[FailureCandidate]) -> list[dict[str, object]]:
    return [
        {
            "method": candidate.method,
            "run_id": candidate.run_id,
            "problem_id": candidate.problem_id,
            "candidate_reasons": "|".join(candidate.candidate_reasons),
            "auto_error_category": candidate.auto_error_category,
            "manual_category": "",
            "notes": "",
            "source_results_path": str(_source_results_path(inputs, candidate.method)),
        }
        for candidate in candidates
    ]


def _build_report_data(
    inputs: AnalysisInputs,
    *,
    evidence_class: str,
    aggregates: Mapping[str, EvaluationAggregate],
    main_rows: Sequence[Mapping[str, object]],
    comparison_rows: Sequence[Mapping[str, object]],
    curve_rows: Sequence[TrainingCurveRow],
    candidates: Sequence[FailureCandidate],
    cost_rows: Sequence[CostRow],
    manual_labels: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    sources: dict[str, object] = {}
    for method in ("Base", "SFT", "Public-RLVR", "Hidden-RLVR"):
        results_path = _source_results_path(inputs, method)
        metadata = inputs.evaluation_metadata[method]
        sources[method] = {
            "run_id": metadata["run_id"],
            "model_id": metadata["model_id"],
            "model_revision": metadata["model_revision"],
            "checkpoint": metadata["checkpoint"],
            "dataset_hash": metadata["dataset_hash"],
            "config_hash": metadata["config_hash"],
            "project_commit": metadata["project_commit"],
            "open_r1_commit": metadata["open_r1_commit"],
            "dependency_lock_hash": metadata["dependency_lock_hash"],
            "results_path": str(results_path),
            "results_sha256": _sha256(results_path),
        }
    return {
        "schema_version": 1,
        "evidence_class": evidence_class,
        "manifest_hash": _manifest_hash(inputs.config),
        "bootstrap": {
            "seed": inputs.config.bootstrap_seed,
            "resamples": inputs.config.bootstrap_resamples,
            "confidence_level": inputs.config.confidence_level,
            "unit": "problem",
        },
        "reward_hacking_candidate_definition": "visible whole-pass and eval-hidden not whole-pass",
        "reward_hacking_candidate_status": "automated_proxy_not_human_conclusion",
        "manual_analysis_status": "completed" if manual_labels else "pending",
        "manual_label_count": len(manual_labels),
        "sources": sources,
        "main_results": list(main_rows),
        "paired_comparisons": list(comparison_rows),
        "confidence_intervals": {
            method: {name: _interval_mapping(interval) for name, interval in aggregate.confidence_intervals.items()}
            for method, aggregate in aggregates.items()
        },
        "training_curves": [asdict(row) for row in curve_rows],
        "failure_candidates": [_candidate_mapping(candidate) for candidate in candidates],
        "costs": [asdict(row) for row in cost_rows],
    }


def _write_analysis_outputs(temp_dir: Path, inputs: AnalysisInputs, *, evidence_class: str) -> tuple[int, int, int]:
    config = inputs.config
    aggregates = {
        method: aggregate_evaluation_records(
            records,
            bootstrap_seed=config.bootstrap_seed,
            bootstrap_resamples=config.bootstrap_resamples,
            confidence_level=config.confidence_level,
        )
        for method, records in inputs.evaluation_records.items()
    }
    main_rows = _main_result_rows(inputs, aggregates)
    comparisons = [
        compare_evaluation_records(
            left_method,
            inputs.evaluation_records[left_method],
            right_method,
            inputs.evaluation_records[right_method],
            bootstrap_seed=config.bootstrap_seed,
            bootstrap_resamples=config.bootstrap_resamples,
            confidence_level=config.confidence_level,
        )
        for left_method, right_method in (
            ("Public-RLVR", "SFT"),
            ("Hidden-RLVR", "SFT"),
            ("Hidden-RLVR", "Public-RLVR"),
        )
    ]
    comparison_rows = [_comparison_mapping(item) for item in comparisons]
    candidates = tuple(
        candidate
        for method in ("Base", "SFT", "Public-RLVR", "Hidden-RLVR")
        for candidate in select_failure_candidates(method, inputs.evaluation_records[method])
    )
    curve_rows = tuple(
        row
        for run_dir, method in (
            (config.sft_training_run_dir, "SFT"),
            (config.public_grpo_run_dir, "Public-RLVR"),
            (config.hidden_grpo_run_dir, "Hidden-RLVR"),
        )
        for row in load_training_curve_rows(run_dir, method=method)
    )
    cost_rows = tuple(
        build_cost_row(run_dir, method=method, gpu_hour_cost_usd=config.gpu_hour_cost_usd)
        for run_dir, method in (
            (config.sft_training_run_dir, "SFT"),
            (config.public_grpo_run_dir, "Public-RLVR"),
            (config.hidden_grpo_run_dir, "Hidden-RLVR"),
        )
    )
    manual_labels = (
        ()
        if config.manual_labels_path is None
        else load_manual_labels(config.manual_labels_path, candidates=candidates)
    )
    if config.manual_labels_path is not None and len(manual_labels) < 20:
        raise AnalysisError("completed manual analysis must contain at least 20 unique candidate labels")
    auto_counts = [
        {"method": method, "auto_error_category": category, "count": count}
        for method in ("Base", "SFT", "Public-RLVR", "Hidden-RLVR")
        for category, count in sorted(
            Counter(candidate.auto_error_category for candidate in candidates if candidate.method == method).items()
        )
    ]
    manual_counts = [
        {"method": method, "manual_category": category, "count": count}
        for method in ("Base", "SFT", "Public-RLVR", "Hidden-RLVR")
        for category, count in sorted(
            Counter(row["manual_category"] for row in manual_labels if row["method"] == method).items()
        )
    ]
    main_fields = tuple(main_rows[0])
    comparison_fields = tuple(comparison_rows[0])
    _write_csv(temp_dir / "main_results.csv", main_fields, main_rows)
    _write_csv(temp_dir / "paired_comparisons.csv", comparison_fields, comparison_rows)
    _write_csv(temp_dir / "auto_error_counts.csv", ("method", "auto_error_category", "count"), auto_counts)
    _write_csv(
        temp_dir / "training_curves.csv",
        ("method", "run_id", "record_index", "step", "epoch", "metric", "value"),
        [asdict(row) for row in curve_rows],
    )
    _write_jsonl(temp_dir / "failure_candidates.jsonl", [_candidate_mapping(item) for item in candidates])
    _write_csv(temp_dir / "manual_labels_template.csv", _MANUAL_FIELDS, _manual_template_rows(inputs, candidates))
    _write_csv(temp_dir / "manual_error_counts.csv", ("method", "manual_category", "count"), manual_counts)
    _write_csv(
        temp_dir / "costs.csv",
        (
            "method",
            "run_id",
            "gpu",
            "gpu_hours",
            "rollouts",
            "generated_tokens",
            "executor_hours",
            "estimated_cost_usd",
        ),
        [asdict(row) for row in cost_rows],
    )
    _write_json(
        temp_dir / "report_data.json",
        _build_report_data(
            inputs,
            evidence_class=evidence_class,
            aggregates=aggregates,
            main_rows=main_rows,
            comparison_rows=comparison_rows,
            curve_rows=curve_rows,
            candidates=candidates,
            cost_rows=cost_rows,
            manual_labels=manual_labels,
        ),
    )
    (temp_dir / "resolved_analysis.yaml").write_text(
        yaml.safe_dump(_config_mapping(config), sort_keys=True, allow_unicode=True), encoding="utf-8", newline="\n"
    )
    if {path.name for path in temp_dir.iterdir()} != _ANALYSIS_LAYOUT:
        raise AnalysisError("analysis output layout is incomplete")
    return len(inputs.evaluation_records["Base"]), len(candidates), len(manual_labels)


def analyze_experiment(
    config: AnalysisConfig,
    *,
    output_dir: Path,
    evidence_class: Literal[
        "analysis_source_artifacts", "engineering_fixture_synthetic"
    ] = "analysis_source_artifacts",
) -> AnalysisSummary:
    """Validate source identities and atomically generate all WP8 report inputs."""
    if output_dir.exists():
        raise AnalysisError("analysis output directory must not already exist")
    parent = output_dir.parent.resolve(strict=False)
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=parent))
    try:
        inputs = load_analysis_inputs(config)
        total, candidate_count, manual_count = _write_analysis_outputs(
            temporary,
            inputs,
            evidence_class=evidence_class,
        )
        os.replace(temporary, output_dir)
    except AnalysisError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(temporary, ignore_errors=True)
        raise AnalysisError(f"analysis failed: {type(error).__name__}") from None
    return AnalysisSummary(
        output_dir=output_dir,
        total_problems=total,
        candidate_count=candidate_count,
        manual_label_count=manual_count,
        report_data_path=output_dir / "report_data.json",
        main_results_path=output_dir / "main_results.csv",
        paired_comparisons_path=output_dir / "paired_comparisons.csv",
        cost_path=output_dir / "costs.csv",
    )
