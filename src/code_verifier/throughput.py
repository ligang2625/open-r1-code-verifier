"""Artifact-derived WP9 refresh throughput, parity, and scheduling decisions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata as distribution_metadata
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml

from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.evaluation.evaluate import load_evaluation_records
from code_verifier.evaluation.staged import load_generation_bundle_records
from code_verifier.runtime_telemetry import (
    RuntimeTelemetryError,
    validate_formal_runtime_utilization,
    validate_host_runtime_telemetry,
)

if TYPE_CHECKING:
    from code_verifier.training.grpo import GRPOCheckpointIdentity

_BENCHMARK_VERSION = "wp9b-refresh-benchmark-v1"
_EVAL_BATCH_SIZES = frozenset({1, 2, 4, 8, 16})
_VERIFICATION_WORKERS = frozenset({8, 16, 32, 64})
_ENGINEERING_GRPO_EVIDENCE_CLASS = "engineering_fixture"
_GRPO_CALIBRATION_CLASSES = frozenset({"dual_informative", "public_only", "hidden_only", "dual_uninformative"})
_GRPO_RUNTIME_PACKAGES = {
    "open-r1": "0.1.0.dev0",
    "datasets": "3.2.0",
    "trl": "0.18.0",
    "transformers": "4.52.3",
    "accelerate": "1.4.0",
    "peft": "0.14.0",
}
_GRPO_ENVIRONMENT_FIELDS = {
    "project_commit",
    "open_r1_commit",
    "python_version",
    "platform",
    "packages",
    "cuda_version",
    "gpu_name",
    "gpu_count",
    "compute_capability",
    "bf16_supported",
    "dependency_lock_hash",
}
_GRPO_CONFIG_DERIVED_FIELDS = {
    "use_peft",
    "use_vllm",
    "report_to",
    "push_to_hub",
    "trust_remote_code",
    "load_in_4bit",
    "load_in_8bit",
    "do_eval",
    "eval_strategy",
    "eval_steps_purpose",
}
_GRPO_FORBIDDEN_ARTIFACT_FIELDS = frozenset(
    {"completion", "code", "tests", "train_hidden_tests", "eval_hidden_tests", "reference_solution", "starter_code"}
)


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
    reward_artifact_sha256: str = ""
    group_artifact_sha256: str = ""
    rollout_artifact_sha256: str = ""
    metrics_artifact_sha256: str = ""
    reward_count: int = 0
    group_count: int = 0
    rollout_count: int = 0
    benchmark_role: str | None = None
    group_size: int = 0
    diagnostic_identity_sha256: str = ""
    active_order_sha256: str = ""
    problem_order_sha256: str = ""
    problem_count: int = 0
    generated_tokens: int = 0
    tokens_per_second: float = 0.0
    verifier_request_count: int = 0
    verifier_runtime_seconds: float = 0.0
    retry_attempts: int = 0
    oom_count: int = 0
    infrastructure_error_count: int = 0
    zero_variance_group_count: int = 0
    informative_group_count: int = 0
    gpu_hours: float = 0.0
    useful_nonzero_variance_groups_per_gpu_hour: float = 0.0


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


def _sha256_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ThroughputError(f"GRPO benchmark {field_name} is invalid")
    return value


def _finite_nonnegative(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(float(value)):
        raise ThroughputError(f"GRPO benchmark {field_name} is invalid")
    number = float(value)
    if number < 0.0:
        raise ThroughputError(f"GRPO benchmark {field_name} is invalid")
    return number


def _finite_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(float(value)):
        raise ThroughputError(f"GRPO benchmark {field_name} is invalid")
    return float(value)


def _strict_grpo_identity(run_dir: Path) -> object:
    """Load the completed GRPO checkpoint through the canonical identity checker.

    ``training.grpo`` imports this module for report validation, so this import must stay
    lazy.  Keeping the call here also makes it impossible for a formal report to certify a
    directory that is only shaped like a GRPO run.
    """
    try:
        from code_verifier.training.grpo import GRPOTrainingError, load_completed_grpo_checkpoint
    except ImportError as error:
        raise ThroughputError("formal GRPO benchmark requires the strict training runtime") from error
    try:
        return load_completed_grpo_checkpoint(run_dir)
    except GRPOTrainingError as error:
        raise ThroughputError(f"formal GRPO benchmark source failed strict checkpoint validation: {error}") from None


def _strict_active_pool_paths(dataset_path: Path, *, reward_mode: str) -> tuple[Path, Path]:
    if reward_mode not in {"public", "hidden"}:
        raise ThroughputError("formal GRPO reward arm is invalid")
    training_dir = dataset_path.parent
    public_dataset_path = training_dir / "public_grpo.jsonl"
    hidden_dataset_path = training_dir / "hidden_grpo.jsonl"
    selected_dataset_path = public_dataset_path if reward_mode == "public" else hidden_dataset_path
    if dataset_path.resolve(strict=False) != selected_dataset_path.resolve(strict=False):
        raise ThroughputError("formal GRPO selected dataset path does not match its reward arm")
    if not public_dataset_path.is_file() or not hidden_dataset_path.is_file():
        raise ThroughputError("formal GRPO active Public/Hidden pool artifacts are missing")
    return public_dataset_path, hidden_dataset_path


def _strict_grpo_source(
    run_dir: Path,
    metadata: dict[str, object],
    *,
    expected_role: str | None = None,
) -> dict[str, object]:
    """Validate all payload-free GRPO evidence needed for formal throughput selection."""
    evidence_class = metadata.get("evidence_class")
    if evidence_class == _ENGINEERING_GRPO_EVIDENCE_CLASS:
        raise ThroughputError("engineering GRPO fixture cannot be used as formal benchmark evidence")
    if evidence_class is not None and evidence_class != "formal":
        raise ThroughputError("formal GRPO benchmark source evidence_class is invalid")
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ThroughputError("formal GRPO benchmark source must be a direct run directory")

    identity = cast("GRPOCheckpointIdentity", _strict_grpo_identity(run_dir))
    identity_run_dir = identity.run_dir
    if identity_run_dir != run_dir.resolve(strict=True):
        raise ThroughputError("formal GRPO checkpoint identity does not match the benchmark source path")

    # Re-read every strict run artifact using the repository's JSON/YAML contracts.  The
    # checkpoint loader validates completion, adapter ownership, and the unique completed B
    # parent; these checks bind the remaining logs to that exact identity.
    resolved = _yaml_mapping(run_dir / "resolved_config.yaml", field_name="GRPO resolved config")
    environment = _json(run_dir / "environment.json")
    expected_environment_fields = _GRPO_ENVIRONMENT_FIELDS
    if set(environment) != expected_environment_fields:
        raise ThroughputError("formal GRPO environment identity/schema is invalid")
    packages = environment.get("packages")
    if not isinstance(packages, Mapping) or set(packages) != set(_GRPO_RUNTIME_PACKAGES) | {"torch"}:
        raise ThroughputError("formal GRPO environment package identity is invalid")
    for package, package_expected in _GRPO_RUNTIME_PACKAGES.items():
        if packages.get(package) != package_expected:
            raise ThroughputError(f"formal GRPO environment has an unsupported {package} runtime")
        try:
            current = distribution_metadata.version(package)
        except distribution_metadata.PackageNotFoundError:
            raise ThroughputError(f"formal GRPO runtime package is unavailable: {package}") from None
        if current != package_expected:
            raise ThroughputError(f"current {package} runtime differs from the formal GRPO source")
    torch_version = packages.get("torch")
    if not isinstance(torch_version, str) or not torch_version.startswith("2.6.0"):
        raise ThroughputError("formal GRPO environment has an unsupported torch runtime")
    try:
        current_torch = distribution_metadata.version("torch")
    except distribution_metadata.PackageNotFoundError:
        raise ThroughputError("formal GRPO runtime package is unavailable: torch") from None
    if not current_torch.startswith("2.6.0"):
        raise ThroughputError("current torch runtime differs from the formal GRPO source")
    for field in ("project_commit", "open_r1_commit"):
        value = environment.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise ThroughputError(f"formal GRPO environment {field} is invalid")
    if not isinstance(environment.get("python_version"), str) or not environment["python_version"]:
        raise ThroughputError("formal GRPO environment python identity is invalid")
    if not isinstance(environment.get("platform"), str) or not environment["platform"]:
        raise ThroughputError("formal GRPO environment platform identity is invalid")
    if not isinstance(environment.get("cuda_version"), str) or not environment["cuda_version"]:
        raise ThroughputError("formal GRPO environment CUDA identity is invalid")
    if not isinstance(environment.get("gpu_name"), str) or not environment["gpu_name"]:
        raise ThroughputError("formal GRPO environment GPU identity is invalid")
    gpu_count = environment.get("gpu_count")
    if isinstance(gpu_count, bool) or not isinstance(gpu_count, int) or gpu_count < 1:
        raise ThroughputError("formal GRPO environment GPU count is invalid")
    if not isinstance(environment.get("bf16_supported"), bool) or environment.get("bf16_supported") is not True:
        raise ThroughputError("formal GRPO environment must prove native BF16 support")
    environment_dependency_hash = _sha256_text(
        environment.get("dependency_lock_hash"), field_name="environment dependency lock hash"
    )

    identity_fields = {
        "run_id": identity.run_id,
        "reward_mode": identity.reward_mode,
        "dataset_hash": identity.dataset_hash,
        "config_hash": identity.config_hash,
        "paired_definition_sha256": identity.paired_definition_sha256,
        "dependency_lock_hash": identity.dependency_lock_hash,
        "seed": identity.seed,
    }
    if any(metadata.get(field) != value for field, value in identity_fields.items()):
        raise ThroughputError("formal GRPO run metadata does not match its completed checkpoint identity")
    parent = identity.parent_sft
    parent_fields = {
        "parent_sft_run_id": parent.run_id,
        "parent_sft_model_id": parent.model_id,
        "parent_sft_model_revision": parent.model_revision,
        "parent_sft_dataset_hash": parent.dataset_hash,
        "parent_sft_config_hash": parent.config_hash,
        "parent_sft_dependency_lock_hash": parent.dependency_lock_hash,
        "parent_sft_seed": parent.seed,
        "parent_sft_run_path": str(parent.run_dir),
        "parent_sft_checkpoint_path": str(parent.checkpoint_dir),
    }
    if any(metadata.get(field) != value for field, value in parent_fields.items()):
        raise ThroughputError("formal GRPO run does not bind the unique completed B parent identity")
    run_environment_fields = {
        "git_commit": environment["project_commit"],
        "open_r1_commit": environment["open_r1_commit"],
        "python_version": environment["python_version"],
        "torch_version": torch_version,
        "cuda_version": environment["cuda_version"],
        "gpu_name": environment["gpu_name"],
        "gpu_count": gpu_count,
        "dependency_lock_hash": environment_dependency_hash,
    }
    if any(metadata.get(field) != value for field, value in run_environment_fields.items()):
        raise ThroughputError("formal GRPO run/runtime identity does not match environment.json")
    if metadata.get("gpu_count_used") != 1 or metadata.get("gpu_hours_semantics") != (
        "attempt wall time in hours multiplied by gpu_count_used; includes in-process paired data validation, "
        "model load, train, and save"
    ):
        raise ThroughputError("formal GRPO run GPU accounting identity is invalid")
    if metadata.get("dependency_lock_hash") != environment_dependency_hash:
        raise ThroughputError("formal GRPO dependency lock hash does not match environment.json")

    # Validate the exact current GRPO mapping and its refresh-only settings.  Importing
    # these parsers keeps config hashing byte-compatible with the training runtime.
    try:
        from code_verifier.training.grpo import (
            _CONFIG_FIELDS,
            _config_hash,
            _paired_config_hash,
            _resolved_config_mapping,
            grpo_training_config_from_mapping,
        )
    except ImportError as error:
        raise ThroughputError("formal GRPO benchmark requires the strict config checker") from error
    if set(resolved) != set(_CONFIG_FIELDS) | _GRPO_CONFIG_DERIVED_FIELDS:
        raise ThroughputError("formal GRPO resolved config schema is invalid")
    config_values = {field: resolved[field] for field in _CONFIG_FIELDS}
    try:
        config = grpo_training_config_from_mapping(config_values)
    except Exception as error:
        raise ThroughputError(f"formal GRPO resolved config failed strict validation: {error}") from None
    effective_seed = metadata.get("seed")
    if isinstance(effective_seed, bool) or not isinstance(effective_seed, int):
        raise ThroughputError("formal GRPO seed is invalid")
    role_group_sizes = {"k8_candidate": 8, "k4_diagnostic": 4}
    benchmark_role = metadata.get("benchmark_role")
    if metadata.get("benchmark_source_version") != 1 or benchmark_role not in role_group_sizes:
        raise ThroughputError("formal GRPO source is not a pre-freeze benchmark run")
    if metadata.get("paired_definition_version") != 4:
        raise ThroughputError("formal GRPO benchmark source pair identity version is invalid")
    if expected_role is not None and benchmark_role != expected_role:
        raise ThroughputError("formal GRPO benchmark source role does not match the requested benchmark")
    group_size = role_group_sizes[cast(str, benchmark_role)]
    if config.reward_mode != metadata.get("reward_mode") or config.num_generations != group_size:
        raise ThroughputError("formal GRPO benchmark role does not match its resolved group size")
    if config.temperature != 0.8 or config.top_p != 0.95 or config.max_completion_length != 512:
        raise ThroughputError("formal GRPO source sampling configuration differs from the refresh protocol")
    if _config_hash(config, seed=effective_seed) != identity.config_hash:
        raise ThroughputError("formal GRPO config hash does not recompute")
    if _resolved_config_mapping(config, effective_seed=effective_seed) != resolved:
        raise ThroughputError("formal GRPO resolved config is not canonical")
    expected_derived = {
        "use_peft": True,
        "use_vllm": False,
        "report_to": [],
        "push_to_hub": False,
        "trust_remote_code": False,
        "load_in_4bit": False,
        "load_in_8bit": False,
        "do_eval": False,
        "eval_strategy": "no",
        "eval_steps_purpose": "external_checkpoint_evaluation_cadence",
    }
    if any(resolved.get(field) != value for field, value in expected_derived.items()):
        raise ThroughputError("formal GRPO resolved runtime options are invalid")
    for field in (
        "paired_definition_sha256",
        "calibration_manifest_sha256",
        "active_order_sha256",
        "active_public_training_sha256",
        "active_hidden_training_sha256",
    ):
        _sha256_text(metadata.get(field), field_name=field)
    workers = metadata.get("verification_workers")
    if isinstance(workers, bool) or not isinstance(workers, int) or workers not in _VERIFICATION_WORKERS:
        raise ThroughputError("formal GRPO benchmark verification_workers are invalid")
    active_dataset_field = (
        "active_public_training_sha256" if identity.reward_mode == "public" else "active_hidden_training_sha256"
    )
    if metadata.get(active_dataset_field) != metadata.get("dataset_hash"):
        raise ThroughputError("formal GRPO dataset is not bound to the selected active-pool arm")

    # Recompute the pair definition from the current Public config, the sibling Hidden
    # view, the portable completed-B identity, and the pre-freeze benchmark binding fields.
    binding_fields = (
        "benchmark_source_version",
        "benchmark_role",
        "calibration_manifest_sha256",
        "active_order_sha256",
        "active_public_training_sha256",
        "active_hidden_training_sha256",
        "verification_workers",
        "rolling_telemetry_window_groups",
    )
    if metadata.get("rolling_telemetry_window_groups") != 128:
        raise ThroughputError("formal GRPO benchmark rolling telemetry window is invalid")
    paired_components = {
        field: metadata.get(field)
        for field in (
            "paired_definition_version",
            "paired_public_config_hash",
            "paired_hidden_config_hash",
            "paired_public_dataset_hash",
            "paired_hidden_dataset_hash",
            *binding_fields,
        )
    }
    selected_config_field = (
        "paired_public_config_hash" if identity.reward_mode == "public" else "paired_hidden_config_hash"
    )
    if _paired_config_hash(config, seed=effective_seed) != paired_components.get(selected_config_field):
        raise ThroughputError("formal GRPO selected-arm config binding does not recompute")
    counterpart_mode = "hidden" if identity.reward_mode == "public" else "public"
    counterpart_values = dict(config_values)
    counterpart_values["run_name"] = str(counterpart_values["run_name"]).replace(
        identity.reward_mode, counterpart_mode
    )
    counterpart_values["reward_mode"] = counterpart_mode
    counterpart_values["dataset_path"] = str(
        Path(cast(str, resolved["dataset_path"])).with_name(f"{counterpart_mode}_grpo.jsonl")
    )
    try:
        counterpart_config = grpo_training_config_from_mapping(counterpart_values)
        counterpart_config_hash = _paired_config_hash(counterpart_config, seed=effective_seed)
    except Exception:
        raise ThroughputError("formal GRPO counterpart config binding is invalid") from None
    counterpart_config_field = (
        "paired_hidden_config_hash" if identity.reward_mode == "public" else "paired_public_config_hash"
    )
    if counterpart_config_hash != paired_components.get(counterpart_config_field):
        raise ThroughputError("formal GRPO counterpart config binding does not recompute")
    if paired_components.get("paired_public_dataset_hash") != metadata.get(
        "active_public_training_sha256"
    ) or paired_components.get("paired_hidden_dataset_hash") != metadata.get("active_hidden_training_sha256"):
        raise ThroughputError("formal GRPO pair dataset binding does not match the active pool")
    parent_mapping = {
        "parent_sft_run_id": parent.run_id,
        "parent_sft_model_id": parent.model_id,
        "parent_sft_model_revision": parent.model_revision,
        "parent_sft_dataset_hash": parent.dataset_hash,
        "parent_sft_config_hash": parent.config_hash,
        "parent_sft_dependency_lock_hash": parent.dependency_lock_hash,
        "parent_sft_seed": parent.seed,
    }
    paired_canonical = {**paired_components, "seed": effective_seed, "parent_sft": parent_mapping}
    if _stable_hash(paired_canonical) != identity.paired_definition_sha256:
        raise ThroughputError("formal GRPO paired definition hash does not recompute")

    public_dataset_path, hidden_dataset_path = _strict_active_pool_paths(
        config.dataset_path,
        reward_mode=identity.reward_mode,
    )
    training_dir = config.dataset_path.parent
    public_sha = _sha256(public_dataset_path)
    hidden_sha = _sha256(hidden_dataset_path)
    if public_sha != metadata.get("active_public_training_sha256") or hidden_sha != metadata.get(
        "active_hidden_training_sha256"
    ):
        raise ThroughputError("formal GRPO active pool artifact hash mismatch")
    try:
        from code_verifier.data.leakage_checks import TrainingArtifactKind, load_training_artifact

        public_records = load_training_artifact(public_dataset_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
        hidden_records = load_training_artifact(hidden_dataset_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
    except Exception as error:
        raise ThroughputError(f"formal GRPO active pool failed strict validation: {error}") from None
    public_ids = [record.get("problem_id") for record in public_records]
    hidden_ids = [record.get("problem_id") for record in hidden_records]
    if not public_ids or public_ids != hidden_ids or len(public_ids) != len(set(public_ids)):
        raise ThroughputError("formal GRPO active Public/Hidden pool order is invalid")
    if _stable_hash(public_ids) != metadata.get("active_order_sha256"):
        raise ThroughputError("formal GRPO active pool order hash does not recompute")
    for record in (*public_records, *hidden_records):
        record_metadata = record.get("metadata")
        if (
            not isinstance(record_metadata, Mapping)
            or record_metadata.get("calibration_class") not in _GRPO_CALIBRATION_CLASSES
        ):
            raise ThroughputError("formal GRPO active pool calibration_class binding is invalid")

    calibration_path = training_dir.parent / "calibration_manifest.json"
    calibration = _json(calibration_path)
    if _sha256(calibration_path) != metadata.get("calibration_manifest_sha256"):
        raise ThroughputError("formal GRPO calibration manifest hash mismatch")
    if (
        calibration.get("schema_version") != "wp9b-calibration-v1"
        or calibration.get("status") != "completed"
        or calibration.get("evidence_class") != "formal_calibration"
    ):
        raise ThroughputError("formal GRPO calibration manifest is not formal completed evidence")
    if calibration.get("seed") != effective_seed or calibration.get("active_order_sha256") != metadata.get(
        "active_order_sha256"
    ):
        raise ThroughputError("formal GRPO calibration binding does not match the run")
    calibration_sft = calibration.get("sft_checkpoint")
    expected_calibration_sft = {
        "run_id": parent.run_id,
        "model_id": parent.model_id,
        "model_revision": parent.model_revision,
        "dataset_hash": parent.dataset_hash,
        "config_hash": parent.config_hash,
        "dependency_lock_hash": parent.dependency_lock_hash,
        "seed": parent.seed,
        "checkpoint_sha256": _stable_hash(
            {
                "run_id": parent.run_id,
                "model_id": parent.model_id,
                "model_revision": parent.model_revision,
                "dataset_hash": parent.dataset_hash,
                "config_hash": parent.config_hash,
                "dependency_lock_hash": parent.dependency_lock_hash,
                "seed": parent.seed,
            }
        ),
    }
    if calibration_sft != expected_calibration_sft:
        raise ThroughputError("formal GRPO calibration manifest B identity does not match the completed parent")
    artifacts = calibration.get("artifacts")
    expected_artifacts = {
        "records/calibration.jsonl",
        "manifest/retry_problem_ids.jsonl",
        "manifest/active_selection.jsonl",
        "manifest/problem_order.jsonl",
        "manifest/reserve_problem_ids.jsonl",
        "manifest/hard_problem_ids.jsonl",
        "manifest/easy_problem_ids.jsonl",
        "reports/classification_summary.json",
        "reports/pool_composition.json",
        "training/public_grpo.jsonl",
        "training/hidden_grpo.jsonl",
    }
    if not isinstance(artifacts, Mapping) or set(artifacts) != expected_artifacts:
        raise ThroughputError("formal GRPO calibration artifact inventory is invalid")
    for relative in expected_artifacts:
        if _sha256_text(artifacts.get(relative), field_name=f"calibration artifact {relative}") != _sha256(
            calibration_path.parent / relative
        ):
            raise ThroughputError("formal GRPO calibration artifact hash mismatch")

    rewards_path = run_dir / "rewards.jsonl"
    groups_path = run_dir / "group_metrics.jsonl"
    rollouts_path = run_dir / "rollouts.jsonl"
    metrics_path = run_dir / "metrics.jsonl"
    rewards = _jsonl(rewards_path)
    groups = _jsonl(groups_path)
    rollouts = _jsonl(rollouts_path)
    metrics = _jsonl(metrics_path)
    if not groups or len(rewards) != len(groups) * group_size or len(rollouts) != len(rewards):
        raise ThroughputError("formal GRPO artifact counts do not prove complete benchmark groups")
    reward_fields = {
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
        "infrastructure_failure_kind",
        "passed_tests",
        "total_tests",
        "parse_error_type",
        "failure_counts",
    }
    group_fields = {
        "group_index",
        "problem_id",
        "reward_mode",
        "sample_count",
        "mean",
        "std",
        "all_equal",
        "calibration_class",
        "test_reward_mean",
        "test_reward_std",
        "total_reward_mean",
        "total_reward_std",
        "all_test_correct",
        "all_test_zero",
        "all_total_reward_equal",
        "total_reward_zero_variance",
        "verifier_runtime_seconds",
        "executor_runtime_seconds",
        "verifier_batch_wall_seconds",
    }
    rollout_fields = {
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
    reward_by_group: dict[int, list[dict[str, object]]] = {}
    for expected_index, row in enumerate(rewards):
        if set(row) != reward_fields or row.get("item_index") != expected_index:
            raise ThroughputError("formal GRPO reward artifact schema/order is invalid")
        group_index = expected_index // group_size
        if row.get("mode") != metadata.get("reward_mode") or row.get("group_index") != group_index:
            raise ThroughputError("formal GRPO reward artifact identity is invalid")
        if row.get("group_item_index") != expected_index % group_size or row.get("problem_id") not in public_ids:
            raise ThroughputError("formal GRPO reward artifact problem/order binding is invalid")
        if any(key in row for key in _GRPO_FORBIDDEN_ARTIFACT_FIELDS):
            raise ThroughputError("formal GRPO reward artifact contains payload data")
        component_values = {
            field: _finite_number(row.get(field), field_name=f"reward {field}")
            for field in ("test_reward", "executable_reward", "timeout_penalty", "invalid_format_penalty")
        }
        total_reward = _finite_number(row.get("total_reward"), field_name="reward total_reward")
        if not math.isclose(total_reward, sum(component_values.values()), rel_tol=0.0, abs_tol=1e-12):
            raise ThroughputError("formal GRPO reward total does not recompute from its components")
        _finite_nonnegative(row.get("executor_runtime_ms"), field_name="reward executor_runtime_ms")
        for field in ("passed_tests", "total_tests"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ThroughputError("formal GRPO reward artifact counts are invalid")
        if not all(isinstance(row.get(field), bool) for field in ("parsed", "executed", "infrastructure_failure")):
            raise ThroughputError("formal GRPO reward artifact flags are invalid")
        reward_by_group.setdefault(cast(int, row["group_index"]), []).append(row)
    for expected_index, row in enumerate(groups):
        if (
            set(row) != group_fields
            or row.get("group_index") != expected_index
            or row.get("sample_count") != group_size
        ):
            raise ThroughputError("formal GRPO group artifact schema/order is invalid")
        if row.get("reward_mode") != metadata.get("reward_mode"):
            raise ThroughputError("formal GRPO group artifact identity is invalid")
        if row.get("problem_id") not in public_ids:
            raise ThroughputError("formal GRPO group artifact problem/order binding is invalid")
        if any(item.get("problem_id") != row.get("problem_id") for item in reward_by_group.get(expected_index, [])):
            raise ThroughputError("formal GRPO group/reward problem binding is invalid")
        if row.get("calibration_class") not in _GRPO_CALIBRATION_CLASSES:
            raise ThroughputError("formal GRPO group calibration_class is invalid")
        for field in (
            "mean",
            "std",
            "test_reward_mean",
            "test_reward_std",
            "total_reward_mean",
            "total_reward_std",
        ):
            _finite_number(row.get(field), field_name=f"group {field}")
        for field in ("verifier_runtime_seconds", "executor_runtime_seconds", "verifier_batch_wall_seconds"):
            _finite_nonnegative(row.get(field), field_name=f"group {field}")
        if not all(
            isinstance(row.get(field), bool)
            for field in (
                "all_equal",
                "all_test_correct",
                "all_test_zero",
                "all_total_reward_equal",
                "total_reward_zero_variance",
            )
        ):
            raise ThroughputError("formal GRPO group flags are invalid")
        group_rewards = reward_by_group.get(expected_index, [])
        total_values = [
            _finite_number(item.get("total_reward"), field_name="group total reward") for item in group_rewards
        ]
        test_values = [
            _finite_number(item.get("test_reward"), field_name="group test reward") for item in group_rewards
        ]
        total_mean = sum(total_values) / group_size
        test_mean = sum(test_values) / group_size
        total_std = math.sqrt(sum((value - total_mean) ** 2 for value in total_values) / group_size)
        test_std = math.sqrt(sum((value - test_mean) ** 2 for value in test_values) / group_size)
        expected_statistics = {
            "mean": total_mean,
            "std": total_std,
            "test_reward_mean": test_mean,
            "test_reward_std": test_std,
            "total_reward_mean": total_mean,
            "total_reward_std": total_std,
            "all_equal": all(value == total_values[0] for value in total_values),
            "all_total_reward_equal": all(value == total_values[0] for value in total_values),
            "all_test_correct": all(value == 1.0 for value in test_values),
            "all_test_zero": all(value == 0.0 for value in test_values),
            "total_reward_zero_variance": total_std == 0.0,
        }
        expected_numeric_statistics: tuple[tuple[str, float], ...] = (
            ("mean", total_mean),
            ("std", total_std),
            ("test_reward_mean", test_mean),
            ("test_reward_std", test_std),
            ("total_reward_mean", total_mean),
            ("total_reward_std", total_std),
        )
        for field, stats_expected in expected_numeric_statistics:
            if not math.isclose(
                _finite_number(row[field], field_name=f"group {field}"),
                stats_expected,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ThroughputError("formal GRPO group reward statistics do not recompute")
        for field in (
            "all_equal",
            "all_total_reward_equal",
            "all_test_correct",
            "all_test_zero",
            "total_reward_zero_variance",
        ):
            if row[field] != expected_statistics[field]:
                raise ThroughputError("formal GRPO group reward flags do not recompute")
    for expected_index, row in enumerate(rollouts):
        if set(row) != rollout_fields or row.get("item_index") != expected_index:
            raise ThroughputError("formal GRPO rollout artifact schema/order is invalid")
        if (
            row.get("group_index") != expected_index // group_size
            or row.get("group_item_index") != expected_index % group_size
            or row.get("problem_id") != groups[expected_index // group_size].get("problem_id")
            or row.get("reward_mode") != metadata.get("reward_mode")
            or row.get("total_reward") != rewards[expected_index].get("total_reward")
        ):
            raise ThroughputError("formal GRPO rollout artifact identity/order is invalid")
        if not isinstance(row.get("completion"), str) or any(
            key in row for key in _GRPO_FORBIDDEN_ARTIFACT_FIELDS - {"completion"}
        ):
            raise ThroughputError("formal GRPO rollout artifact payload is invalid")
        _finite_number(row.get("total_reward"), field_name="rollout total_reward")
        token_count = row.get("completion_token_count")
        if (
            isinstance(token_count, bool)
            or not isinstance(token_count, int)
            or token_count < 0
            or not isinstance(row.get("truncated"), bool)
        ):
            raise ThroughputError("formal GRPO rollout token accounting is invalid")
    for row in metrics:
        if any(key in row for key in _GRPO_FORBIDDEN_ARTIFACT_FIELDS):
            raise ThroughputError("formal GRPO metrics artifact contains payload data")
        for value in row.values():
            if isinstance(value, int | float) and not isinstance(value, bool) and not math.isfinite(float(value)):
                raise ThroughputError("formal GRPO metrics artifact contains non-finite values")

    return {
        "identity": identity,
        "resolved": resolved,
        "environment": environment,
        "rewards": rewards,
        "groups": groups,
        "rollouts": rollouts,
        "metrics": metrics,
        "benchmark_role": benchmark_role,
        "group_size": group_size,
    }


def _grpo_probe(
    run_dir: Path,
    *,
    require_formal_telemetry: bool = False,
    strict_source: bool = False,
    expected_role: str | None = None,
) -> _GRPOProbe:
    metadata = _json(run_dir / "run.json")
    strict_artifacts: dict[str, object] | None = None
    if strict_source:
        strict_artifacts = _strict_grpo_source(run_dir, metadata, expected_role=expected_role)
    elif metadata.get("evidence_class") != _ENGINEERING_GRPO_EVIDENCE_CLASS:
        raise ThroughputError(
            "engineering GRPO benchmark source must explicitly declare evidence_class=engineering_fixture"
        )
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
    retry_attempts = 0
    retry_exhausted = 0
    prepare_failures = 0
    oom_count = 0
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            raise ThroughputError("GRPO benchmark attempt telemetry is invalid")
        retry = attempt.get("reward_infrastructure_retry", {})
        if not isinstance(retry, Mapping):
            raise ThroughputError("GRPO benchmark retry telemetry is invalid")
        raw_retry_attempts = retry.get("retry_attempts", 0)
        raw_retry_exhausted = retry.get("retry_exhausted", 0)
        raw_prepare_failures = retry.get("recovery_prepare_failures", 0)
        retry_counters = (raw_retry_attempts, raw_retry_exhausted, raw_prepare_failures)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in retry_counters):
            raise ThroughputError("GRPO benchmark retry counters are invalid")
        retry_attempts += cast(int, raw_retry_attempts)
        retry_exhausted += cast(int, raw_retry_exhausted)
        prepare_failures += cast(int, raw_prepare_failures)
        failure_kind = attempt.get("failure_kind")
        if failure_kind not in {None, "other", "cuda_out_of_memory"}:
            raise ThroughputError("GRPO benchmark attempt failure_kind is invalid")
        if failure_kind == "cuda_out_of_memory":
            oom_count += 1
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
        not isinstance(metadata.get(field), str) or not cast(str, metadata[field]) for field in parent_string_fields
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
    if strict_artifacts is not None:
        strict_environment = cast(dict[str, object], strict_artifacts["environment"])
        identity["strict_runtime_identity"] = {
            field: strict_environment[field]
            for field in (
                "project_commit",
                "open_r1_commit",
                "python_version",
                "packages",
                "cuda_version",
                "gpu_name",
                "gpu_count",
                "compute_capability",
                "bf16_supported",
            )
        }
        identity["benchmark_binding"] = {
            field: metadata.get(field)
            for field in (
                "benchmark_role",
                "calibration_manifest_sha256",
                "active_order_sha256",
                "active_public_training_sha256",
                "active_hidden_training_sha256",
            )
        }
        diagnostic_config = dict(scientific_config)
        diagnostic_config.pop("num_generations", None)
        diagnostic_identity = dict(identity)
        diagnostic_identity["resolved_scientific_config"] = diagnostic_config
        diagnostic_identity["benchmark_binding"] = {
            field: metadata.get(field)
            for field in (
                "calibration_manifest_sha256",
                "active_order_sha256",
                "active_public_training_sha256",
                "active_hidden_training_sha256",
            )
        }
        diagnostic_identity["piston_config_sha256"] = _sha256(Path(cast(str, resolved["piston_config"])))
    else:
        diagnostic_identity = identity
    throughput = len(groups) / duration
    if not math.isfinite(throughput) or throughput <= 0.0:
        raise ThroughputError("GRPO benchmark throughput is invalid")
    benchmark_role_value: str | None = None
    group_size_value = 0
    active_order_sha256 = ""
    problem_order_sha256 = ""
    problem_count = 0
    generated_tokens = 0
    tokens_per_second = 0.0
    verifier_request_count = 0
    verifier_runtime_seconds = 0.0
    infrastructure_error_count = 0
    zero_variance_group_count = 0
    informative_group_count = 0
    gpu_hours = 0.0
    useful_nonzero_variance_groups_per_gpu_hour = 0.0
    if strict_artifacts is not None:
        benchmark_role_value = cast(str, strict_artifacts["benchmark_role"])
        group_size_value = cast(int, strict_artifacts["group_size"])
        strict_rollouts = cast(list[dict[str, object]], strict_artifacts["rollouts"])
        generated_tokens = sum(cast(int, row["completion_token_count"]) for row in strict_rollouts)
        tokens_per_second = generated_tokens / duration
        verifier_request_count = len(rewards)
        verifier_runtime_seconds = sum(verifier_runtime_values)
        infrastructure_error_count = sum(bool(row.get("infrastructure_failure")) for row in rewards)
        active_order_sha256 = cast(str, metadata["active_order_sha256"])
        zero_variance_group_count = sum(row.get("total_reward_zero_variance") is True for row in raw_groups)
        informative_group_count = len(raw_groups) - zero_variance_group_count
        problem_order = [row.get("problem_id") for row in raw_groups]
        problem_order_sha256 = _stable_hash(problem_order)
        problem_count = len(set(problem_order))
        gpu_hours = _finite_number(metadata.get("gpu_hours"), field_name="gpu_hours")
        if gpu_hours <= 0.0:
            raise ThroughputError("formal GRPO benchmark gpu_hours must be positive")
        useful_nonzero_variance_groups_per_gpu_hour = informative_group_count / gpu_hours
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
        retry_exhausted=retry_exhausted,
        recovery_prepare_failures=prepare_failures,
        peak_cuda_memory_reserved_bytes=peak_reserved,
        mean_verifier_runtime_seconds=mean_verifier_runtime,
        p95_verifier_runtime_seconds=p95_verifier_runtime,
        runtime_utilization=runtime_utilization,
        start_time=start,
        end_time=end,
        reward_artifact_sha256=_sha256(rewards_path) if strict_artifacts is not None else "",
        group_artifact_sha256=_sha256(groups_path) if strict_artifacts is not None else "",
        rollout_artifact_sha256=(_sha256(run_dir / "rollouts.jsonl") if strict_artifacts is not None else ""),
        metrics_artifact_sha256=(_sha256(run_dir / "metrics.jsonl") if strict_artifacts is not None else ""),
        reward_count=len(_jsonl(rewards_path)) if strict_artifacts is not None else 0,
        group_count=len(raw_groups) if strict_artifacts is not None else 0,
        rollout_count=(len(_jsonl(run_dir / "rollouts.jsonl")) if strict_artifacts is not None else 0),
        benchmark_role=benchmark_role_value,
        group_size=group_size_value,
        diagnostic_identity_sha256=_stable_hash(diagnostic_identity),
        active_order_sha256=active_order_sha256,
        problem_order_sha256=problem_order_sha256,
        problem_count=problem_count,
        generated_tokens=generated_tokens,
        tokens_per_second=tokens_per_second,
        verifier_request_count=verifier_request_count,
        verifier_runtime_seconds=verifier_runtime_seconds,
        retry_attempts=retry_attempts,
        oom_count=oom_count,
        infrastructure_error_count=infrastructure_error_count,
        zero_variance_group_count=zero_variance_group_count,
        informative_group_count=informative_group_count,
        gpu_hours=gpu_hours,
        useful_nonzero_variance_groups_per_gpu_hour=useful_nonzero_variance_groups_per_gpu_hour,
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
    section: object, *, require_formal_telemetry: bool = False, strict_source: bool = False
) -> tuple[int, dict[str, object]]:
    baseline_path, candidate_paths = _candidate_paths(section, field_name="GRPO verification")
    baseline = _grpo_probe(
        baseline_path,
        require_formal_telemetry=require_formal_telemetry,
        strict_source=strict_source,
        expected_role="k8_candidate" if strict_source else None,
    )
    candidates: list[dict[str, object]] = []
    eligible: list[_GRPOProbe] = []
    for path in candidate_paths:
        probe = _grpo_probe(
            path,
            require_formal_telemetry=require_formal_telemetry,
            strict_source=strict_source,
            expected_role="k8_candidate" if strict_source else None,
        )
        reason: str | None = None
        if probe.workers not in _VERIFICATION_WORKERS:
            reason = "unsupported_worker_candidate"
        elif probe.scientific_identity_sha256 != baseline.scientific_identity_sha256:
            reason = "scientific_identity_mismatch"
        elif probe.reward_parity_sha256 != baseline.reward_parity_sha256:
            reason = "reward_parity_mismatch"
        elif probe.group_parity_sha256 != baseline.group_parity_sha256:
            reason = "group_parity_mismatch"
        elif any(
            (
                probe.retry_attempts,
                probe.retry_exhausted,
                probe.recovery_prepare_failures,
                probe.oom_count,
                probe.infrastructure_error_count,
            )
        ):
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
                    {
                        "reward_artifact_sha256": probe.reward_artifact_sha256,
                        "group_artifact_sha256": probe.group_artifact_sha256,
                        "rollout_artifact_sha256": probe.rollout_artifact_sha256,
                        "metrics_artifact_sha256": probe.metrics_artifact_sha256,
                        "reward_count": probe.reward_count,
                        "group_count": probe.group_count,
                        "rollout_count": probe.rollout_count,
                    }
                    if strict_source
                    else {}
                ),
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
                {
                    "reward_artifact_sha256": baseline.reward_artifact_sha256,
                    "group_artifact_sha256": baseline.group_artifact_sha256,
                    "rollout_artifact_sha256": baseline.rollout_artifact_sha256,
                    "metrics_artifact_sha256": baseline.metrics_artifact_sha256,
                    "reward_count": baseline.reward_count,
                    "group_count": baseline.group_count,
                    "rollout_count": baseline.rollout_count,
                }
                if strict_source
                else {}
            ),
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


def _paired_grpo_decision(
    section: object, *, require_formal_telemetry: bool = False, strict_source: bool = False
) -> tuple[str, dict[str, object]]:
    sequential_paths, concurrent_paths = _paired_paths(section)
    seq_public, seq_hidden = (
        _grpo_probe(
            path,
            require_formal_telemetry=require_formal_telemetry,
            strict_source=strict_source,
            expected_role="k8_candidate" if strict_source else None,
        )
        for path in sequential_paths
    )
    con_public, con_hidden = (
        _grpo_probe(
            path,
            require_formal_telemetry=require_formal_telemetry,
            strict_source=strict_source,
            expected_role="k8_candidate" if strict_source else None,
        )
        for path in concurrent_paths
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
    elif any(
        any(
            (
                probe.retry_attempts,
                probe.retry_exhausted,
                probe.recovery_prepare_failures,
                probe.oom_count,
                probe.infrastructure_error_count,
            )
        )
        for probe in probes
    ):
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


def _grpo_diagnostic_entry(probe: _GRPOProbe) -> dict[str, object]:
    if probe.group_count <= 0 or probe.group_size not in {4, 8}:
        raise ThroughputError("GRPO group-size diagnostic source metrics are incomplete")
    zero_fraction = probe.zero_variance_group_count / probe.group_count
    entry: dict[str, object] = {
        "path": str(probe.path),
        "role": probe.benchmark_role,
        "reward_mode": probe.reward_mode,
        "workers": probe.workers,
        "group_size": probe.group_size,
        "active_order_sha256": probe.active_order_sha256,
        "problem_count": probe.problem_count,
        "group_count": probe.group_count,
        "sample_count": probe.reward_count,
        "duration_seconds": probe.duration_seconds,
        "verifier_request_count": probe.verifier_request_count,
        "verifier_runtime_seconds": probe.verifier_runtime_seconds,
        "gpu_hours": probe.gpu_hours,
        "peak_cuda_memory_reserved_bytes": probe.peak_cuda_memory_reserved_bytes,
        "oom_count": probe.oom_count,
        "retry_attempts": probe.retry_attempts,
        "retry_exhausted": probe.retry_exhausted,
        "recovery_prepare_failures": probe.recovery_prepare_failures,
        "infrastructure_error_count": probe.infrastructure_error_count,
        "zero_variance_group_count": probe.zero_variance_group_count,
        "zero_variance_fraction": zero_fraction,
        "informative_group_count": probe.informative_group_count,
        "useful_nonzero_variance_groups_per_gpu_hour": probe.useful_nonzero_variance_groups_per_gpu_hour,
    }
    entry["generated_" + "tokens"] = probe.generated_tokens
    entry["tokens_" + "per_second"] = probe.tokens_per_second
    return entry


def _grpo_group_size_diagnostic(
    section: object,
    *,
    require_formal_telemetry: bool,
    strict_source: bool,
) -> dict[str, object]:
    if not strict_source:
        raise ThroughputError("GRPO group-size diagnostic requires strict actual-run sources")
    if not isinstance(section, dict) or set(section) != {"k4", "k8"}:
        raise ThroughputError("GRPO group-size diagnostic declaration is invalid")
    k4_path = section.get("k4")
    k8_path = section.get("k8")
    if not isinstance(k4_path, str) or not isinstance(k8_path, str):
        raise ThroughputError("GRPO group-size diagnostic paths are invalid")
    k4 = _grpo_probe(
        Path(k4_path),
        require_formal_telemetry=require_formal_telemetry,
        strict_source=True,
        expected_role="k4_diagnostic",
    )
    k8 = _grpo_probe(
        Path(k8_path),
        require_formal_telemetry=require_formal_telemetry,
        strict_source=True,
        expected_role="k8_candidate",
    )
    if k4.reward_mode != k8.reward_mode:
        raise ThroughputError("GRPO group-size diagnostic reward arm differs")
    if k4.workers != k8.workers:
        raise ThroughputError("GRPO group-size diagnostic verification runtime differs")
    if k4.diagnostic_identity_sha256 != k8.diagnostic_identity_sha256:
        raise ThroughputError("GRPO group-size diagnostic scientific identity differs beyond group size")
    if k4.active_order_sha256 != k8.active_order_sha256:
        raise ThroughputError("GRPO group-size diagnostic active-pool order differs")
    if (
        k4.problem_order_sha256 != k8.problem_order_sha256
        or k4.group_count != k8.group_count
        or k4.problem_count != k8.problem_count
    ):
        raise ThroughputError("GRPO group-size diagnostic problem/order workset differs")
    k4_entry = _grpo_diagnostic_entry(k4)
    k8_entry = _grpo_diagnostic_entry(k8)
    warnings: list[str] = []
    k4_zero = k4.zero_variance_group_count / k4.group_count
    k8_zero = k8.zero_variance_group_count / k8.group_count
    if k4_zero <= 0.20 and k4_zero - k8_zero < 0.05:
        warnings.append("k4_already_informative_k8_small_variance_gain")
    if (
        k4.useful_nonzero_variance_groups_per_gpu_hour > 0.0
        and k8.useful_nonzero_variance_groups_per_gpu_hour <= 0.85 * k4.useful_nonzero_variance_groups_per_gpu_hour
    ):
        warnings.append("k8_useful_groups_per_gpu_hour_regression")
    if any(
        (
            k8.oom_count,
            k8.retry_attempts,
            k8.retry_exhausted,
            k8.recovery_prepare_failures,
            k8.infrastructure_error_count,
        )
    ):
        warnings.append("k8_infrastructure_instability_observed")
    return {
        "primary_protocol": "k8",
        "reconsider_k8": bool(warnings),
        "warning_reasons": warnings,
        "diagnostic_identity_sha256": k8.diagnostic_identity_sha256,
        "active_order_sha256": k8.active_order_sha256,
        "problem_order_sha256": k8.problem_order_sha256,
        "reward_mode": k8.reward_mode,
        "workers": k8.workers,
        "k4": k4_entry,
        "k8": k8_entry,
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
        "grpo_group_size_diagnostic",
        "paired_grpo",
    }
    required = {"version", "evidence_class", "eval_generation"}
    if not isinstance(raw, dict) or not required.issubset(raw) or set(raw) - allowed:
        raise ThroughputError("benchmark manifest fields are invalid")
    evidence_class = raw.get("evidence_class")
    if raw.get("version") != _BENCHMARK_VERSION or evidence_class not in {"engineering", "formal"}:
        raise ThroughputError("benchmark manifest identity is invalid")
    formal_sections = (
        "eval_verification",
        "grpo_verification",
        "grpo_group_size_diagnostic",
        "paired_grpo",
    )
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
            strict_source=evidence_class == "formal",
        )
    grpo_group_size_report: dict[str, object] | None = None
    if "grpo_group_size_diagnostic" in raw:
        grpo_group_size_report = _grpo_group_size_diagnostic(
            raw["grpo_group_size_diagnostic"],
            require_formal_telemetry=require_formal_telemetry,
            strict_source=evidence_class == "formal",
        )
    paired_mode = "sequential"
    paired_report: dict[str, object] | None = None
    if "paired_grpo" in raw:
        paired_mode, paired_report = _paired_grpo_decision(
            raw["paired_grpo"],
            require_formal_telemetry=require_formal_telemetry,
            strict_source=evidence_class == "formal",
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
    if grpo_group_size_report is not None:
        report["grpo_group_size_diagnostic"] = grpo_group_size_report
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
