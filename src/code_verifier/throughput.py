"""Artifact-derived WP9 refresh throughput, parity, and scheduling decisions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import yaml

from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.evaluation.evaluate import load_evaluation_records
from code_verifier.evaluation.staged import load_generation_bundle_records
from code_verifier.runtime_telemetry import (
    RuntimeTelemetryError,
    validate_formal_runtime_utilization,
    validate_host_runtime_telemetry,
)

_BENCHMARK_VERSION = "wp9b-refresh-benchmark-v1"
_EVAL_BATCH_SIZES = frozenset({1, 2, 4, 8, 16})
_VERIFICATION_WORKERS = frozenset({8, 16, 32, 64})


class ThroughputError(RuntimeError):
    """Raised when benchmark source artifacts do not prove a valid comparison."""


@dataclass(frozen=True)
class GenerationParity:
    exact: bool
    reason: str | None
    problem_count: int


@dataclass(frozen=True)
class RefreshBenchmarkSummary:
    report_dir: Path
    report_path: Path
    selected_eval_generation_batch_size: int
    evidence_class: str
    selected_grpo_verification_workers: int | None = None
    selected_eval_verification_workers: int | None = None
    paired_grpo_mode: str = "sequential"


@dataclass(frozen=True)
class _VerificationProbe:
    path: Path
    workers: int
    duration_seconds: float
    throughput_per_second: float
    mean_latency_ms: float
    p95_latency_ms: float
    host_runtime: dict[str, object] | None
    identity_sha256: str
    result_sha256: str
    run_manifest_sha256: str
    record_count: int


@dataclass(frozen=True)
class _GRPOProbe:
    path: Path
    workers: int
    reward_mode: str
    duration_seconds: float
    throughput_per_second: float
    scientific_identity_sha256: str
    reward_parity_sha256: str
    group_parity_sha256: str
    paired_definition_sha256: str
    run_manifest_sha256: str
    retry_exhausted: int
    recovery_prepare_failures: int
    peak_cuda_memory_reserved_bytes: int
    mean_verifier_runtime_seconds: float
    p95_verifier_runtime_seconds: float
    runtime_utilization: dict[str, object] | None
    start_time: datetime
    end_time: datetime


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ThroughputError(f"benchmark artifact is unreadable: {path.name}") from error


def _stable_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json(path: Path) -> dict[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise ThroughputError(f"benchmark artifact is invalid: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ThroughputError(f"benchmark artifact must contain an object: {path.name}")
    return cast(dict[str, object], value)


def _jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ThroughputError(f"benchmark JSONL is unreadable: {path.name}") from error
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise ThroughputError(f"benchmark JSONL contains a blank line: {path.name}:{line_number}")
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise ThroughputError(f"benchmark JSONL is invalid: {path.name}:{line_number}") from error
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ThroughputError(f"benchmark JSONL row must be an object: {path.name}:{line_number}")
        rows.append(cast(dict[str, object], value))
    if not rows:
        raise ThroughputError(f"benchmark JSONL must be non-empty: {path.name}")
    return rows


def _yaml_mapping(path: Path, *, field_name: str) -> dict[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ThroughputError(f"benchmark {field_name} is invalid") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ThroughputError(f"benchmark {field_name} must be a string-keyed mapping")
    return cast(dict[str, object], value)


def _p95(values: list[float], *, field_name: str) -> float:
    if not values or any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ThroughputError(f"{field_name} values must be finite, non-negative, and non-empty")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ThroughputError(f"benchmark {field_name} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ThroughputError(f"benchmark {field_name} must be a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ThroughputError(f"benchmark {field_name} must be timezone-aware")
    return parsed


def _completed_duration(metadata: dict[str, object]) -> tuple[datetime, datetime, float]:
    if metadata.get("status") != "completed":
        raise ThroughputError("benchmark source run must be completed")
    start = _timestamp(metadata.get("start_time"), field_name="start_time")
    end = _timestamp(metadata.get("end_time"), field_name="end_time")
    duration = (end - start).total_seconds()
    if not math.isfinite(duration) or duration <= 0.0:
        raise ThroughputError("benchmark source run duration must be finite and positive")
    return start, end, duration


def _completed_bundle(run_dir: Path) -> tuple[dict[str, object], Path, str]:
    metadata = _json(run_dir / "run.json")
    records_path = run_dir / "samples" / "generations.jsonl"
    resolved_path = run_dir / "resolved_config.yaml"
    if (
        metadata.get("schema_version") != 2
        or metadata.get("status") != "completed"
        or metadata.get("artifact_type") != "evaluation_generation_bundle"
    ):
        raise ThroughputError("benchmark generation bundle must be a completed v2 artifact")
    if metadata.get("records_sha256") != _sha256(records_path):
        raise ThroughputError("benchmark generation bundle records hash mismatch")
    resolved = _yaml_mapping(resolved_path, field_name="generation resolved config")
    expected_resolved_fields = {
        "schema_version",
        "run_id",
        "model_id",
        "model_revision",
        "checkpoint",
        "seed",
        "split",
        "device",
        "generation",
        "dataset_hash",
        "piston_config_sha256",
        "batch_size",
    }
    if set(resolved) != expected_resolved_fields:
        raise ThroughputError("benchmark generation resolved config schema is invalid")
    for field in (
        "schema_version",
        "run_id",
        "model_id",
        "model_revision",
        "checkpoint",
        "seed",
        "dataset_hash",
        "batch_size",
    ):
        if metadata.get(field) != resolved.get(field):
            raise ThroughputError(f"benchmark generation run/resolved config mismatch for {field}")
    if metadata.get("resolved_config_sha256") != _sha256(resolved_path):
        raise ThroughputError("benchmark generation resolved config hash mismatch")
    if metadata.get("evaluation_contract_sha256") != _stable_hash(resolved):
        raise ThroughputError("benchmark generation contract hash does not recompute")
    records = load_generation_bundle_records(records_path)
    if metadata.get("completed_records") != len(records) or metadata.get("total_problems") != len(records):
        raise ThroughputError("benchmark generation bundle is incomplete")
    ordered_ids_sha256 = _stable_hash([record.problem_id for record in records])
    if metadata.get("ordered_problem_ids_sha256") != ordered_ids_sha256:
        raise ThroughputError("benchmark generation problem-order hash does not recompute")
    for record in records:
        expected_record_identity = {
            "run_id": metadata.get("run_id"),
            "model_id": metadata.get("model_id"),
            "checkpoint": metadata.get("checkpoint"),
            "dataset_hash": metadata.get("dataset_hash"),
            "evaluation_contract_sha256": metadata.get("evaluation_contract_sha256"),
        }
        if any(getattr(record, field) != value for field, value in expected_record_identity.items()):
            raise ThroughputError("benchmark generation row identity is inconsistent with run metadata")
    scientific_config = dict(resolved)
    scientific_config.pop("run_id")
    scientific_config.pop("batch_size")
    scientific_identity_sha256 = _stable_hash(
        {
            "resolved_scientific_config": scientific_config,
            "ordered_problem_ids_sha256": ordered_ids_sha256,
        }
    )
    return metadata, records_path, scientific_identity_sha256


def compare_generation_bundle_parity(baseline_run_dir: Path, candidate_run_dir: Path) -> GenerationParity:
    """Compare exact deterministic outputs while ignoring operational run/batch identity."""
    _baseline_meta, baseline_path, baseline_identity = _completed_bundle(baseline_run_dir)
    _candidate_meta, candidate_path, candidate_identity = _completed_bundle(candidate_run_dir)
    if baseline_identity != candidate_identity:
        return GenerationParity(False, "source_identity_mismatch", 0)
    baseline = load_generation_bundle_records(baseline_path)
    candidate = load_generation_bundle_records(candidate_path)
    if len(baseline) != len(candidate):
        return GenerationParity(False, "problem_count_mismatch", min(len(baseline), len(candidate)))
    for left, right in zip(baseline, candidate, strict=True):
        if left.problem_id != right.problem_id or left.prompt_hash != right.prompt_hash:
            return GenerationParity(False, "problem_order_mismatch", len(baseline))
        if (
            left.completion != right.completion
            or left.completion_tokens != right.completion_tokens
            or left.hit_max_new_tokens != right.hit_max_new_tokens
        ):
            return GenerationParity(False, "generation_output_mismatch", len(baseline))
    return GenerationParity(True, None, len(baseline))


def _bundle_metrics(run_dir: Path, *, require_formal_telemetry: bool = False) -> dict[str, object]:
    metadata, records_path, scientific_identity_sha256 = _completed_bundle(run_dir)
    records = load_generation_bundle_records(records_path)
    batch_size = metadata.get("batch_size", 1)
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size not in _EVAL_BATCH_SIZES:
        raise ThroughputError("benchmark bundle batch_size is invalid")
    latency_seconds = sum(record.generation_latency_ms for record in records) / 1000.0
    tokens = sum(record.completion_tokens for record in records)
    if latency_seconds <= 0 or tokens < 0:
        raise ThroughputError("benchmark bundle has invalid persisted timing/token accounting")
    tokens_per_second = tokens / latency_seconds
    if not math.isfinite(tokens_per_second):
        raise ThroughputError("benchmark bundle throughput is non-finite")
    runtime_utilization: dict[str, object] | None = None
    if require_formal_telemetry:
        try:
            runtime_utilization = dict(validate_formal_runtime_utilization(metadata.get("runtime_utilization")))
        except RuntimeTelemetryError as error:
            raise ThroughputError(f"formal generation runtime telemetry is incomplete: {error}") from None
    return {
        "batch_size": batch_size,
        "problem_count": len(records),
        "completion_tokens": tokens,
        "generation_wall_seconds": latency_seconds,
        "tokens_per_second": tokens_per_second,
        "scientific_identity_sha256": scientific_identity_sha256,
        "run_manifest_sha256": _sha256(run_dir / "run.json"),
        "records_sha256": _sha256(records_path),
        **({"runtime_utilization": runtime_utilization} if runtime_utilization is not None else {}),
    }


def _evaluation_verification_probe(
    run_dir: Path, *, require_formal_host_telemetry: bool = False
) -> _VerificationProbe:
    metadata = _json(run_dir / "run.json")
    _, _, duration = _completed_duration(metadata)
    workers = metadata.get("verification_workers")
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 64:
        raise ThroughputError("evaluation verification workers are invalid")
    results_path = run_dir / "samples" / "results.jsonl"
    records = load_evaluation_records(results_path)
    if not records:
        raise ThroughputError("evaluation verification results must be non-empty")
    identity_fields = {
        key: metadata.get(key)
        for key in (
            "generation_bundle_schema_version",
            "generation_bundle_run_id",
            "generation_bundle_records_sha256",
            "generation_bundle_contract_sha256",
            "generation_bundle_ordered_problem_ids_sha256",
            "generation_environment_sha256",
            "generation_batch_size",
        )
        if key in metadata
    }
    throughput = len(records) / duration
    if not math.isfinite(throughput) or throughput <= 0.0:
        raise ThroughputError("evaluation verification throughput is invalid")
    latencies = [record.runtime_ms for record in records]
    if any(not math.isfinite(value) or value < 0.0 for value in latencies):
        raise ThroughputError("evaluation verifier latency is invalid")
    mean_latency = sum(latencies) / len(latencies)
    p95_latency = _p95(latencies, field_name="evaluation verifier latency")
    host_runtime: dict[str, object] | None = None
    if require_formal_host_telemetry:
        try:
            host_runtime = dict(validate_host_runtime_telemetry(metadata.get("runtime_utilization")))
        except RuntimeTelemetryError as error:
            raise ThroughputError(f"formal verification host telemetry is incomplete: {error}") from None
    return _VerificationProbe(
        path=run_dir,
        workers=workers,
        duration_seconds=duration,
        throughput_per_second=throughput,
        mean_latency_ms=mean_latency,
        p95_latency_ms=p95_latency,
        host_runtime=host_runtime,
        identity_sha256=_stable_hash(identity_fields),
        result_sha256=_sha256(results_path),
        run_manifest_sha256=_sha256(run_dir / "run.json"),
        record_count=len(records),
    )


def _strip_operational_fields(rows: list[dict[str, object]], *, group: bool) -> list[dict[str, object]]:
    ignored = {"executor_runtime_ms"}
    if group:
        ignored.update(
            {
                "executor_runtime_seconds",
                "verifier_runtime_seconds",
                "verifier_batch_wall_seconds",
            }
        )
    return [{key: value for key, value in row.items() if key not in ignored} for row in rows]


def _grpo_probe(run_dir: Path, *, require_formal_telemetry: bool = False) -> _GRPOProbe:
    metadata = _json(run_dir / "run.json")
    start, end, duration = _completed_duration(metadata)
    reward_mode = metadata.get("reward_mode")
    if reward_mode not in {"public", "hidden"}:
        raise ThroughputError("GRPO benchmark reward_mode is invalid")
    workers = metadata.get("verification_workers", 1)
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 64:
        raise ThroughputError("GRPO benchmark verification_workers is invalid")
    paired_definition = metadata.get("paired_definition_sha256")
    if not isinstance(paired_definition, str) or len(paired_definition) != 64:
        raise ThroughputError("GRPO benchmark paired definition is invalid")
    peak_reserved = metadata.get("peak_cuda_memory_reserved_bytes", 0)
    if isinstance(peak_reserved, bool) or not isinstance(peak_reserved, int) or peak_reserved < 0:
        raise ThroughputError("GRPO benchmark peak memory is invalid")
    attempts = metadata.get("attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
        raise ThroughputError("GRPO benchmark attempt telemetry is invalid")
    retry = cast(dict[str, object], attempts[-1]).get("reward_infrastructure_retry", {})
    if not isinstance(retry, dict):
        raise ThroughputError("GRPO benchmark retry telemetry is invalid")
    retry_exhausted = retry.get("retry_exhausted", 0)
    prepare_failures = retry.get("recovery_prepare_failures", 0)
    retry_counters = (retry_exhausted, prepare_failures)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in retry_counters):
        raise ThroughputError("GRPO benchmark retry counters are invalid")
    rewards_path = run_dir / "rewards.jsonl"
    groups_path = run_dir / "group_metrics.jsonl"
    rewards = _strip_operational_fields(_jsonl(rewards_path), group=False)
    raw_groups = _jsonl(groups_path)
    verifier_runtime_values: list[float] = []
    for row in raw_groups:
        raw_runtime = row.get("verifier_runtime_seconds")
        if (
            isinstance(raw_runtime, bool)
            or not isinstance(raw_runtime, int | float)
            or not math.isfinite(float(raw_runtime))
            or float(raw_runtime) < 0.0
        ):
            raise ThroughputError("GRPO verifier runtime telemetry is missing or invalid")
        verifier_runtime_values.append(float(raw_runtime))
    mean_verifier_runtime = sum(verifier_runtime_values) / len(verifier_runtime_values)
    p95_verifier_runtime = _p95(verifier_runtime_values, field_name="GRPO verifier runtime")
    groups = _strip_operational_fields(raw_groups, group=True)
    resolved_path = run_dir / "resolved_config.yaml"
    try:
        resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ThroughputError("GRPO benchmark resolved config is invalid") from error
    if not isinstance(resolved, dict):
        raise ThroughputError("GRPO benchmark resolved config must be a mapping")
    scientific_config = dict(resolved)
    scientific_config.pop("run_name", None)
    scientific_config.pop("dataset_path", None)
    scientific_config.pop("piston_config", None)
    parent_string_fields = (
        "parent_sft_run_id",
        "parent_sft_model_id",
        "parent_sft_model_revision",
        "parent_sft_dataset_hash",
        "parent_sft_config_hash",
        "parent_sft_dependency_lock_hash",
    )
    if any(
        not isinstance(metadata.get(field), str) or not cast(str, metadata[field])
        for field in parent_string_fields
    ):
        raise ThroughputError("GRPO benchmark parent SFT identity is incomplete")
    parent_seed = metadata.get("parent_sft_seed")
    if isinstance(parent_seed, bool) or not isinstance(parent_seed, int):
        raise ThroughputError("GRPO benchmark parent SFT seed is invalid")
    identity = {
        "reward_mode": reward_mode,
        "dataset_hash": metadata.get("dataset_hash"),
        "seed": metadata.get("seed"),
        "parent_sft_run_id": metadata.get("parent_sft_run_id"),
        "parent_sft_model_id": metadata.get("parent_sft_model_id"),
        "parent_sft_model_revision": metadata.get("parent_sft_model_revision"),
        "parent_sft_dataset_hash": metadata.get("parent_sft_dataset_hash"),
        "parent_sft_config_hash": metadata.get("parent_sft_config_hash"),
        "parent_sft_dependency_lock_hash": metadata.get("parent_sft_dependency_lock_hash"),
        "parent_sft_seed": metadata.get("parent_sft_seed"),
        "resolved_scientific_config": scientific_config,
    }
    throughput = len(groups) / duration
    if not math.isfinite(throughput) or throughput <= 0.0:
        raise ThroughputError("GRPO benchmark throughput is invalid")
    runtime_utilization: dict[str, object] | None = None
    if require_formal_telemetry:
        try:
            runtime_utilization = dict(validate_formal_runtime_utilization(metadata.get("runtime_utilization")))
        except RuntimeTelemetryError as error:
            raise ThroughputError(f"formal GRPO runtime telemetry is incomplete: {error}") from None
    return _GRPOProbe(
        path=run_dir,
        workers=workers,
        reward_mode=cast(str, reward_mode),
        duration_seconds=duration,
        throughput_per_second=throughput,
        scientific_identity_sha256=_stable_hash(identity),
        reward_parity_sha256=_stable_hash(rewards),
        group_parity_sha256=_stable_hash(groups),
        paired_definition_sha256=paired_definition,
        run_manifest_sha256=_sha256(run_dir / "run.json"),
        retry_exhausted=cast(int, retry_exhausted),
        recovery_prepare_failures=cast(int, prepare_failures),
        peak_cuda_memory_reserved_bytes=peak_reserved,
        mean_verifier_runtime_seconds=mean_verifier_runtime,
        p95_verifier_runtime_seconds=p95_verifier_runtime,
        runtime_utilization=runtime_utilization,
        start_time=start,
        end_time=end,
    )


def _candidate_paths(section: object, *, field_name: str) -> tuple[Path, list[Path]]:
    if not isinstance(section, dict) or set(section) != {"baseline", "candidates"}:
        raise ThroughputError(f"{field_name} benchmark declaration is invalid")
    baseline = section.get("baseline")
    candidates = section.get("candidates")
    if not isinstance(baseline, str) or not isinstance(candidates, list) or not candidates:
        raise ThroughputError(f"{field_name} benchmark paths are invalid")
    if any(not isinstance(item, str) for item in candidates):
        raise ThroughputError(f"{field_name} benchmark candidate paths are invalid")
    return Path(baseline), [Path(cast(str, item)) for item in candidates]


def _select_eval_generation(
    section: object, *, require_formal_telemetry: bool = False
) -> tuple[int, dict[str, object]]:
    baseline, candidate_paths = _candidate_paths(section, field_name="eval generation")
    baseline_metrics = _bundle_metrics(baseline, require_formal_telemetry=require_formal_telemetry)
    if baseline_metrics["batch_size"] != 1:
        raise ThroughputError("eval generation baseline must use batch_size=1")
    candidates: list[dict[str, object]] = []
    for path in candidate_paths:
        metrics = _bundle_metrics(path, require_formal_telemetry=require_formal_telemetry)
        parity = compare_generation_bundle_parity(baseline, path)
        candidates.append({"path": str(path), **metrics, "exact_parity": parity.exact, "rejection": parity.reason})
    baseline_rate = cast(float, baseline_metrics["tokens_per_second"])
    eligible = [
        item
        for item in candidates
        if item["exact_parity"] is True and cast(float, item["tokens_per_second"]) >= baseline_rate
    ]
    selected = (
        min(
            eligible,
            key=lambda item: (-cast(float, item["tokens_per_second"]), cast(int, item["batch_size"])),
        )
        if eligible
        else {"batch_size": 1, **baseline_metrics}
    )
    return cast(int, selected["batch_size"]), {
        "baseline": {"path": str(baseline), **baseline_metrics},
        "candidates": candidates,
    }


def _select_eval_verification(
    section: object, *, require_formal_host_telemetry: bool = False
) -> tuple[int, dict[str, object]]:
    baseline_path, candidate_paths = _candidate_paths(section, field_name="eval verification")
    baseline = _evaluation_verification_probe(
        baseline_path,
        require_formal_host_telemetry=require_formal_host_telemetry,
    )
    candidates: list[dict[str, object]] = []
    eligible: list[_VerificationProbe] = []
    for path in candidate_paths:
        probe = _evaluation_verification_probe(
            path,
            require_formal_host_telemetry=require_formal_host_telemetry,
        )
        reason: str | None = None
        if probe.workers not in _VERIFICATION_WORKERS:
            reason = "unsupported_worker_candidate"
        elif probe.identity_sha256 != baseline.identity_sha256:
            reason = "source_identity_mismatch"
        elif probe.result_sha256 != baseline.result_sha256 or probe.record_count != baseline.record_count:
            reason = "verification_result_mismatch"
        if reason is None:
            eligible.append(probe)
        candidates.append(
            {
                "path": str(path),
                "workers": probe.workers,
                "duration_seconds": probe.duration_seconds,
                "throughput_per_second": probe.throughput_per_second,
                "mean_verifier_latency_ms": probe.mean_latency_ms,
                "p95_verifier_latency_ms": probe.p95_latency_ms,
                **({"host_runtime": probe.host_runtime} if probe.host_runtime is not None else {}),
                "result_sha256": probe.result_sha256,
                "run_manifest_sha256": probe.run_manifest_sha256,
                "rejection": reason,
            }
        )
    if not eligible:
        raise ThroughputError("no stable eval verification worker candidate passed parity checks")
    selected = min(eligible, key=lambda probe: (-probe.throughput_per_second, probe.workers))
    return selected.workers, {
        "baseline": {
            "path": str(baseline.path),
            "workers": baseline.workers,
            "duration_seconds": baseline.duration_seconds,
            "throughput_per_second": baseline.throughput_per_second,
            "mean_verifier_latency_ms": baseline.mean_latency_ms,
            "p95_verifier_latency_ms": baseline.p95_latency_ms,
            **({"host_runtime": baseline.host_runtime} if baseline.host_runtime is not None else {}),
            "result_sha256": baseline.result_sha256,
            "run_manifest_sha256": baseline.run_manifest_sha256,
        },
        "candidates": candidates,
    }


def _select_grpo_verification(
    section: object, *, require_formal_telemetry: bool = False
) -> tuple[int, dict[str, object]]:
    baseline_path, candidate_paths = _candidate_paths(section, field_name="GRPO verification")
    baseline = _grpo_probe(baseline_path, require_formal_telemetry=require_formal_telemetry)
    candidates: list[dict[str, object]] = []
    eligible: list[_GRPOProbe] = []
    for path in candidate_paths:
        probe = _grpo_probe(path, require_formal_telemetry=require_formal_telemetry)
        reason: str | None = None
        if probe.workers not in _VERIFICATION_WORKERS:
            reason = "unsupported_worker_candidate"
        elif probe.scientific_identity_sha256 != baseline.scientific_identity_sha256:
            reason = "scientific_identity_mismatch"
        elif probe.reward_parity_sha256 != baseline.reward_parity_sha256:
            reason = "reward_parity_mismatch"
        elif probe.group_parity_sha256 != baseline.group_parity_sha256:
            reason = "group_parity_mismatch"
        elif probe.retry_exhausted or probe.recovery_prepare_failures:
            reason = "infrastructure_instability"
        if reason is None:
            eligible.append(probe)
        candidates.append(
            {
                "path": str(path),
                "workers": probe.workers,
                "duration_seconds": probe.duration_seconds,
                "throughput_per_second": probe.throughput_per_second,
                "run_manifest_sha256": probe.run_manifest_sha256,
                "reward_parity_sha256": probe.reward_parity_sha256,
                "group_parity_sha256": probe.group_parity_sha256,
                "peak_cuda_memory_reserved_bytes": probe.peak_cuda_memory_reserved_bytes,
                "mean_verifier_runtime_seconds": probe.mean_verifier_runtime_seconds,
                "p95_verifier_runtime_seconds": probe.p95_verifier_runtime_seconds,
                **(
                    {"runtime_utilization": probe.runtime_utilization} if probe.runtime_utilization is not None else {}
                ),
                "rejection": reason,
            }
        )
    if not eligible:
        raise ThroughputError("no stable GRPO verification worker candidate passed parity checks")
    selected = min(eligible, key=lambda probe: (-probe.throughput_per_second, probe.workers))
    return selected.workers, {
        "baseline": {
            "path": str(baseline.path),
            "workers": baseline.workers,
            "duration_seconds": baseline.duration_seconds,
            "throughput_per_second": baseline.throughput_per_second,
            "run_manifest_sha256": baseline.run_manifest_sha256,
            "reward_parity_sha256": baseline.reward_parity_sha256,
            "group_parity_sha256": baseline.group_parity_sha256,
            "peak_cuda_memory_reserved_bytes": baseline.peak_cuda_memory_reserved_bytes,
            "mean_verifier_runtime_seconds": baseline.mean_verifier_runtime_seconds,
            "p95_verifier_runtime_seconds": baseline.p95_verifier_runtime_seconds,
            **(
                {"runtime_utilization": baseline.runtime_utilization}
                if baseline.runtime_utilization is not None
                else {}
            ),
        },
        "candidates": candidates,
    }


def _paired_paths(section: object) -> tuple[tuple[Path, Path], tuple[Path, Path]]:
    if not isinstance(section, dict) or set(section) != {"sequential", "concurrent"}:
        raise ThroughputError("paired GRPO benchmark declaration is invalid")
    pairs: list[tuple[Path, Path]] = []
    for key in ("sequential", "concurrent"):
        value = section.get(key)
        if not isinstance(value, dict) or set(value) != {"public", "hidden"}:
            raise ThroughputError("paired GRPO arm paths are invalid")
        public = value.get("public")
        hidden = value.get("hidden")
        if not isinstance(public, str) or not isinstance(hidden, str):
            raise ThroughputError("paired GRPO arm paths are invalid")
        pairs.append((Path(public), Path(hidden)))
    return pairs[0], pairs[1]


def _paired_grpo_decision(section: object, *, require_formal_telemetry: bool = False) -> tuple[str, dict[str, object]]:
    sequential_paths, concurrent_paths = _paired_paths(section)
    seq_public, seq_hidden = (
        _grpo_probe(path, require_formal_telemetry=require_formal_telemetry) for path in sequential_paths
    )
    con_public, con_hidden = (
        _grpo_probe(path, require_formal_telemetry=require_formal_telemetry) for path in concurrent_paths
    )
    probes = (seq_public, seq_hidden, con_public, con_hidden)
    stable = True
    rejection: str | None = None
    if (seq_public.reward_mode, seq_hidden.reward_mode, con_public.reward_mode, con_hidden.reward_mode) != (
        "public",
        "hidden",
        "public",
        "hidden",
    ):
        stable = False
        rejection = "arm_mode_mismatch"
    elif len({probe.paired_definition_sha256 for probe in probes}) != 1:
        stable = False
        rejection = "paired_definition_mismatch"
    elif (
        seq_public.scientific_identity_sha256 != con_public.scientific_identity_sha256
        or seq_hidden.scientific_identity_sha256 != con_hidden.scientific_identity_sha256
        or seq_public.reward_parity_sha256 != con_public.reward_parity_sha256
        or seq_hidden.reward_parity_sha256 != con_hidden.reward_parity_sha256
        or seq_public.group_parity_sha256 != con_public.group_parity_sha256
        or seq_hidden.group_parity_sha256 != con_hidden.group_parity_sha256
    ):
        stable = False
        rejection = "concurrent_scientific_parity_mismatch"
    elif any(probe.retry_exhausted or probe.recovery_prepare_failures for probe in probes):
        stable = False
        rejection = "infrastructure_instability"
    sequential_wall = seq_public.duration_seconds + seq_hidden.duration_seconds
    concurrent_start = min(con_public.start_time, con_hidden.start_time)
    concurrent_end = max(con_public.end_time, con_hidden.end_time)
    concurrent_wall = (concurrent_end - concurrent_start).total_seconds()
    if not math.isfinite(concurrent_wall) or concurrent_wall <= 0.0:
        raise ThroughputError("paired concurrent wall time is invalid")
    gain_fraction = 1.0 - concurrent_wall / sequential_wall
    recommendation = "concurrent" if stable and concurrent_wall <= 0.85 * sequential_wall else "sequential"
    return recommendation, {
        "sequential_wall_seconds": sequential_wall,
        "concurrent_wall_seconds": concurrent_wall,
        "gain_fraction": gain_fraction,
        "stable": stable,
        "rejection": rejection,
        "sequential": {
            "public_run_manifest_sha256": seq_public.run_manifest_sha256,
            "hidden_run_manifest_sha256": seq_hidden.run_manifest_sha256,
        },
        "concurrent": {
            "public_run_manifest_sha256": con_public.run_manifest_sha256,
            "hidden_run_manifest_sha256": con_hidden.run_manifest_sha256,
        },
    }


def summarize_refresh_benchmarks(manifest_path: Path, *, output_dir: Path) -> RefreshBenchmarkSummary:
    """Derive refresh operational selections only from completed, hash-bound run artifacts."""
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ThroughputError("benchmark manifest is unreadable") from error
    allowed = {
        "version",
        "evidence_class",
        "eval_generation",
        "eval_verification",
        "grpo_verification",
        "paired_grpo",
    }
    required = {"version", "evidence_class", "eval_generation"}
    if not isinstance(raw, dict) or not required.issubset(raw) or set(raw) - allowed:
        raise ThroughputError("benchmark manifest fields are invalid")
    evidence_class = raw.get("evidence_class")
    if raw.get("version") != _BENCHMARK_VERSION or evidence_class not in {"engineering", "formal"}:
        raise ThroughputError("benchmark manifest identity is invalid")
    formal_sections = ("eval_verification", "grpo_verification", "paired_grpo")
    if evidence_class == "formal" and any(key not in raw for key in formal_sections):
        raise ThroughputError("formal benchmark manifest requires all refresh benchmark sections")

    require_formal_telemetry = evidence_class == "formal"
    selected_eval_batch, eval_generation_report = _select_eval_generation(
        raw["eval_generation"],
        require_formal_telemetry=require_formal_telemetry,
    )
    selected_eval_workers: int | None = None
    eval_verification_report: dict[str, object] | None = None
    if "eval_verification" in raw:
        selected_eval_workers, eval_verification_report = _select_eval_verification(
            raw["eval_verification"],
            require_formal_host_telemetry=require_formal_telemetry,
        )
    selected_grpo_workers: int | None = None
    grpo_verification_report: dict[str, object] | None = None
    if "grpo_verification" in raw:
        selected_grpo_workers, grpo_verification_report = _select_grpo_verification(
            raw["grpo_verification"],
            require_formal_telemetry=require_formal_telemetry,
        )
    paired_mode = "sequential"
    paired_report: dict[str, object] | None = None
    if "paired_grpo" in raw:
        paired_mode, paired_report = _paired_grpo_decision(
            raw["paired_grpo"],
            require_formal_telemetry=require_formal_telemetry,
        )

    report: dict[str, object] = {
        "version": _BENCHMARK_VERSION,
        "evidence_class": evidence_class,
        "source_manifest_sha256": _sha256(manifest_path),
        "source_manifest_artifact": "benchmark_manifest.yaml",
        "eval_generation": eval_generation_report,
        "baseline": eval_generation_report["baseline"],
        "candidates": eval_generation_report["candidates"],
        "selected_eval_generation_batch_size": selected_eval_batch,
        "selected_eval_verification_workers": selected_eval_workers,
        "selected_grpo_verification_workers": selected_grpo_workers,
        "paired_grpo_mode": paired_mode,
    }
    if eval_verification_report is not None:
        report["eval_verification"] = eval_verification_report
    if grpo_verification_report is not None:
        report["grpo_verification"] = grpo_verification_report
    if paired_report is not None:
        report["paired_grpo"] = paired_report
    if output_dir.exists():
        raise ThroughputError("benchmark output directory must not already exist")
    output_dir.mkdir(parents=True)
    source_manifest_copy = output_dir / "benchmark_manifest.yaml"
    try:
        source_manifest_copy.write_bytes(manifest_path.read_bytes())
    except OSError as error:
        raise ThroughputError("benchmark source manifest could not be snapshotted") from error
    report_path = output_dir / "refresh_benchmark_report.json"
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_dir, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, report_path)
    return RefreshBenchmarkSummary(
        report_dir=output_dir,
        report_path=report_path,
        selected_eval_generation_batch_size=selected_eval_batch,
        evidence_class=cast(str, evidence_class),
        selected_grpo_verification_workers=selected_grpo_workers,
        selected_eval_verification_workers=selected_eval_workers,
        paired_grpo_mode=paired_mode,
    )


def check_refresh_benchmark_report(
    report_path: Path,
    *,
    allow_engineering: bool = False,
) -> RefreshBenchmarkSummary:
    """Rebuild a benchmark report from its snapshotted manifest and strict source artifacts."""
    report = _json(report_path)
    evidence_class = report.get("evidence_class")
    if report.get("version") != _BENCHMARK_VERSION or evidence_class not in {"engineering", "formal"}:
        raise ThroughputError("refresh benchmark report identity is invalid")
    if not allow_engineering and evidence_class != "formal":
        raise ThroughputError("refresh benchmark report is not formal evidence")
    if report.get("source_manifest_artifact") != "benchmark_manifest.yaml":
        raise ThroughputError("refresh benchmark report source manifest artifact is invalid")
    source_manifest_path = report_path.parent / "benchmark_manifest.yaml"
    if report.get("source_manifest_sha256") != _sha256(source_manifest_path):
        raise ThroughputError("refresh benchmark report source manifest hash mismatch")

    with tempfile.TemporaryDirectory(prefix="wp9b-benchmark-check-") as temporary_root:
        rebuilt = summarize_refresh_benchmarks(
            source_manifest_path,
            output_dir=Path(temporary_root) / "rebuilt",
        )
        rebuilt_report = _json(rebuilt.report_path)
    if rebuilt_report != report:
        raise ThroughputError("refresh benchmark report does not recompute from source artifacts")
    return RefreshBenchmarkSummary(
        report_dir=report_path.parent,
        report_path=report_path,
        selected_eval_generation_batch_size=rebuilt.selected_eval_generation_batch_size,
        evidence_class=rebuilt.evidence_class,
        selected_grpo_verification_workers=rebuilt.selected_grpo_verification_workers,
        selected_eval_verification_workers=rebuilt.selected_eval_verification_workers,
        paired_grpo_mode=rebuilt.paired_grpo_mode,
    )
