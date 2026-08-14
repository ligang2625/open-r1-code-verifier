"""Strict A-D analysis manifest and source identity validation."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.evaluation.evaluate import (
    EvaluationError,
    EvaluationRecord,
    load_evaluation_records,
    resolved_evaluation_config_hash,
)
from code_verifier.training.grpo import (
    GRPOCheckpointIdentity,
    GRPOTrainingError,
    grpo_evaluation_checkpoint_id,
    load_completed_grpo_checkpoint,
)
from code_verifier.training.sft import SFTCheckpointIdentity, SFTTrainingError, load_completed_sft_checkpoint


class AnalysisError(RuntimeError):
    """Raised when analysis configuration or source artifacts fail closed."""


@dataclass(frozen=True)
class AnalysisConfig:
    """Resolved exact-schema analysis inputs and statistical settings."""

    base_evaluation_run_dir: Path
    sft_evaluation_run_dir: Path
    public_evaluation_run_dir: Path
    hidden_evaluation_run_dir: Path
    sft_training_run_dir: Path
    public_grpo_run_dir: Path
    hidden_grpo_run_dir: Path
    bootstrap_seed: int
    bootstrap_resamples: int
    confidence_level: float
    gpu_hour_cost_usd: float | None
    manual_labels_path: Path | None


@dataclass(frozen=True)
class AnalysisInputs:
    """Validated A-D records, metadata, and completed checkpoint identities."""

    config: AnalysisConfig
    evaluation_records: dict[str, tuple[EvaluationRecord, ...]]
    evaluation_metadata: dict[str, Mapping[str, object]]
    evaluation_resolved_configs: dict[str, Mapping[str, object]]
    sft_checkpoint: SFTCheckpointIdentity
    public_grpo_checkpoint: GRPOCheckpointIdentity
    hidden_grpo_checkpoint: GRPOCheckpointIdentity


_CONFIG_FIELDS = {
    "base_evaluation_run_dir",
    "sft_evaluation_run_dir",
    "public_evaluation_run_dir",
    "hidden_evaluation_run_dir",
    "sft_training_run_dir",
    "public_grpo_run_dir",
    "hidden_grpo_run_dir",
    "bootstrap",
    "cost",
    "manual_labels_path",
}
_BOOTSTRAP_FIELDS = {"seed", "resamples", "confidence_level"}
_COST_FIELDS = {"gpu_hour_cost_usd"}
_METHODS = ("Base", "SFT", "Public-RLVR", "Hidden-RLVR")


def _exact_mapping(value: object, expected: set[str], *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AnalysisError(f"{field_name} must be a mapping with string keys")
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise AnalysisError(f"{field_name} is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise AnalysisError(f"{field_name} contains unknown field(s): {', '.join(sorted(unknown))}")
    return cast(Mapping[str, object], value)


def _path(value: object, *, field_name: str, nullable: bool = False) -> Path | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError(f"{field_name} must be a non-empty path string")
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def _finite_number(value: object, *, field_name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AnalysisError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise AnalysisError(f"{field_name} must be a finite number")
    return number


def load_analysis_config(path: Path) -> AnalysisConfig:
    """Load one exact analysis YAML manifest."""
    try:
        root = _exact_mapping(load_yaml_mapping(path), _CONFIG_FIELDS, field_name="analysis manifest")
    except ConfigError as error:
        raise AnalysisError(f"analysis manifest is invalid: {type(error).__name__}") from None
    bootstrap = _exact_mapping(root["bootstrap"], _BOOTSTRAP_FIELDS, field_name="bootstrap")
    cost = _exact_mapping(root["cost"], _COST_FIELDS, field_name="cost")
    seed = bootstrap["seed"]
    resamples = bootstrap["resamples"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise AnalysisError("bootstrap.seed must be an integer")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples <= 0:
        raise AnalysisError("bootstrap.resamples must be a positive integer")
    confidence = _finite_number(bootstrap["confidence_level"], field_name="bootstrap.confidence_level")
    if not 0.0 < confidence < 1.0:
        raise AnalysisError("bootstrap.confidence_level must be between 0 and 1")
    raw_rate = cost["gpu_hour_cost_usd"]
    rate = None if raw_rate is None else _finite_number(raw_rate, field_name="cost.gpu_hour_cost_usd", minimum=0.0)
    return AnalysisConfig(
        base_evaluation_run_dir=cast(
            Path, _path(root["base_evaluation_run_dir"], field_name="base_evaluation_run_dir")
        ),
        sft_evaluation_run_dir=cast(Path, _path(root["sft_evaluation_run_dir"], field_name="sft_evaluation_run_dir")),
        public_evaluation_run_dir=cast(
            Path, _path(root["public_evaluation_run_dir"], field_name="public_evaluation_run_dir")
        ),
        hidden_evaluation_run_dir=cast(
            Path, _path(root["hidden_evaluation_run_dir"], field_name="hidden_evaluation_run_dir")
        ),
        sft_training_run_dir=cast(Path, _path(root["sft_training_run_dir"], field_name="sft_training_run_dir")),
        public_grpo_run_dir=cast(Path, _path(root["public_grpo_run_dir"], field_name="public_grpo_run_dir")),
        hidden_grpo_run_dir=cast(Path, _path(root["hidden_grpo_run_dir"], field_name="hidden_grpo_run_dir")),
        bootstrap_seed=seed,
        bootstrap_resamples=resamples,
        confidence_level=confidence,
        gpu_hour_cost_usd=rate,
        manual_labels_path=_path(root["manual_labels_path"], field_name="manual_labels_path", nullable=True),
    )


def _read_json_object(path: Path, *, artifact_name: str) -> Mapping[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError):
        raise AnalysisError(f"{artifact_name} is unreadable or invalid") from None
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AnalysisError(f"{artifact_name} must contain one JSON object")
    return cast(Mapping[str, object], value)


def _load_evaluation_run(
    run_dir: Path, *, method: str
) -> tuple[tuple[EvaluationRecord, ...], Mapping[str, object], Mapping[str, object]]:
    try:
        resolved_dir = run_dir.resolve(strict=True)
        metadata = _read_json_object(resolved_dir / "run.json", artifact_name=f"{method} run.json")
        resolved_value = yaml.safe_load((resolved_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
        records = tuple(load_evaluation_records(resolved_dir / "samples" / "results.jsonl"))
    except AnalysisError:
        raise
    except (OSError, UnicodeError, yaml.YAMLError, EvaluationError):
        raise AnalysisError(f"{method} evaluation artifacts are unreadable or invalid") from None
    if metadata.get("status") != "completed":
        raise AnalysisError(f"{method} evaluation must be completed")
    if not isinstance(resolved_value, Mapping) or not all(isinstance(key, str) for key in resolved_value):
        raise AnalysisError(f"{method} resolved evaluation config is invalid")
    if not records:
        raise AnalysisError(f"{method} evaluation must contain records")
    try:
        resolved_config_hash = resolved_evaluation_config_hash(resolved_value)
    except EvaluationError:
        raise AnalysisError(f"{method} resolved evaluation config identity is invalid") from None
    if resolved_config_hash != metadata.get("config_hash"):
        raise AnalysisError(f"{method} resolved evaluation config does not match config_hash")
    for field in ("project_commit", "open_r1_commit"):
        provenance_value = metadata.get(field)
        if field not in metadata or (
            provenance_value is not None and (not isinstance(provenance_value, str) or not provenance_value.strip())
        ):
            raise AnalysisError(f"{method} evaluation has invalid {field} provenance")
    dependency_lock_hash = metadata.get("dependency_lock_hash")
    if not isinstance(dependency_lock_hash, str) or not dependency_lock_hash.strip():
        raise AnalysisError(f"{method} evaluation has invalid dependency_lock_hash provenance")
    problem_ids = [record.problem_id for record in records]
    if len(problem_ids) != len(set(problem_ids)):
        raise AnalysisError(f"{method} evaluation contains duplicate problem_id values")
    identity = {
        "run_id": records[0].run_id,
        "model_id": records[0].model_id,
        "checkpoint": records[0].checkpoint,
        "dataset_hash": records[0].dataset_hash,
        "config_hash": records[0].config_hash,
    }
    if any(getattr(record, key) != expected for record in records for key, expected in identity.items()):
        raise AnalysisError(f"{method} evaluation records contain mixed identity")
    if any(metadata.get(key) != expected for key, expected in identity.items()):
        raise AnalysisError(f"{method} evaluation metadata does not match records")
    return records, metadata, cast(Mapping[str, object], resolved_value)


def _piston_definition_hash(resolved: Mapping[str, object], *, method: str) -> str:
    value = resolved.get("piston_config")
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError(f"{method} resolved evaluation config has invalid piston_config")
    try:
        return hashlib.sha256(Path(value).read_bytes()).hexdigest()
    except OSError:
        raise AnalysisError(f"{method} Piston definition is unreadable") from None


def _validate_shared_evaluation_contract(
    records: Mapping[str, tuple[EvaluationRecord, ...]],
    metadata: Mapping[str, Mapping[str, object]],
    resolved: Mapping[str, Mapping[str, object]],
) -> None:
    base_problem_ids = {record.problem_id for record in records["Base"]}
    for method in _METHODS[1:]:
        if {record.problem_id for record in records[method]} != base_problem_ids:
            raise AnalysisError("A-D evaluations must use the same problem_id set")
    for field in ("dataset_hash", "seed"):
        if len({metadata[method].get(field) for method in _METHODS}) != 1:
            raise AnalysisError(f"A-D evaluations must use the same {field}")
    for field in ("split", "device", "generation"):
        if len({json.dumps(resolved[method].get(field), sort_keys=True, allow_nan=False) for method in _METHODS}) != 1:
            raise AnalysisError(f"A-D evaluations must use the same {field}")
    if len({_piston_definition_hash(resolved[method], method=method) for method in _METHODS}) != 1:
        raise AnalysisError("A-D evaluations must use the same Piston definition")


def load_analysis_inputs(config: AnalysisConfig) -> AnalysisInputs:
    """Load and cross-check completed A-D evaluation and training identities."""
    run_dirs = {
        "Base": config.base_evaluation_run_dir,
        "SFT": config.sft_evaluation_run_dir,
        "Public-RLVR": config.public_evaluation_run_dir,
        "Hidden-RLVR": config.hidden_evaluation_run_dir,
    }
    records: dict[str, tuple[EvaluationRecord, ...]] = {}
    metadata: dict[str, Mapping[str, object]] = {}
    resolved: dict[str, Mapping[str, object]] = {}
    for method, run_dir in run_dirs.items():
        records[method], metadata[method], resolved[method] = _load_evaluation_run(run_dir, method=method)
    _validate_shared_evaluation_contract(records, metadata, resolved)
    try:
        sft = load_completed_sft_checkpoint(config.sft_training_run_dir)
        public = load_completed_grpo_checkpoint(config.public_grpo_run_dir)
        hidden = load_completed_grpo_checkpoint(config.hidden_grpo_run_dir)
    except (SFTTrainingError, GRPOTrainingError) as error:
        raise AnalysisError(f"completed training identity is invalid: {type(error).__name__}") from None
    if public.reward_mode != "public" or hidden.reward_mode != "hidden":
        raise AnalysisError("C/D reward modes must be public and hidden")
    if public.parent_sft != sft or hidden.parent_sft != sft:
        raise AnalysisError("C/D must share the configured completed B parent")
    base = metadata["Base"]
    if (
        base.get("model_id") != sft.model_id
        or base.get("model_revision") != sft.model_revision
        or base.get("checkpoint") != "base"
    ):
        raise AnalysisError("Base evaluation identity does not match the B parent base model")
    sft_metadata = metadata["SFT"]
    if (
        sft_metadata.get("model_id") != sft.model_id
        or sft_metadata.get("model_revision") != sft.model_revision
        or sft_metadata.get("checkpoint") != str(sft.checkpoint_dir)
    ):
        raise AnalysisError("SFT evaluation checkpoint identity does not match completed B")
    for method, identity in (("Public-RLVR", public), ("Hidden-RLVR", hidden)):
        expected_checkpoint = grpo_evaluation_checkpoint_id(identity)
        if (
            metadata[method].get("model_id") != sft.model_id
            or metadata[method].get("model_revision") != sft.model_revision
            or metadata[method].get("checkpoint") != expected_checkpoint
        ):
            raise AnalysisError(f"{method} evaluation checkpoint identity is invalid")
    return AnalysisInputs(
        config=config,
        evaluation_records=records,
        evaluation_metadata=metadata,
        evaluation_resolved_configs=resolved,
        sft_checkpoint=sft,
        public_grpo_checkpoint=public,
        hidden_grpo_checkpoint=hidden,
    )
