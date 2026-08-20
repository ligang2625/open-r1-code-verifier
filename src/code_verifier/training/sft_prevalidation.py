"""Durable off-GPU prevalidation for formal SFT data.

The expensive correctness gate runs visible tests through Piston once on a
non-training host. Formal GPU training later consumes only a cryptographically
bound manifest and never needs to call Piston again.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from code_verifier.data.leakage_checks import TrainingArtifactKind, load_training_artifact
from code_verifier.environment import collect_environment
from code_verifier.execution.base import CodeExecutor
from code_verifier.execution.piston import (
    PistonExecutor,
    load_piston_executor_config,
    piston_executor_version,
)
from code_verifier.training.sft_data import SFTDataError, SFTExample, sft_example_token_count, validate_sft_record

SFT_PREVALIDATION_SCHEMA_VERSION = 1
SFT_PREVALIDATION_IMPLEMENTATION_VERSION = "sft-prevalidation-v1"
_MAX_WORKERS = 32


class SFTPrevalidationError(RuntimeError):
    """Raised when prevalidation evidence cannot be produced or trusted."""


@dataclass(frozen=True)
class SFTPrevalidationSummary:
    """Non-sensitive summary of one completed off-GPU SFT prevalidation."""

    manifest_path: Path
    train_samples: int
    validation_samples: int
    total_samples: int
    max_token_count: int
    elapsed_seconds: float
    workers: int


@dataclass(frozen=True)
class SFTPrevalidationEvidence:
    """Trusted manifest identity consumed by formal SFT training."""

    manifest_sha256: str
    validator_project_commit: str | None
    piston_config_sha256: str
    piston_executor_version: str
    train_samples: int
    validation_samples: int
    max_token_count: int


ProgressCallback = Callable[[str, int, int, float], None]


def _sha256_file(path: Path, *, description: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise SFTPrevalidationError(f"could not read {description}: {type(error).__name__}") from None


def _record_sha256(record: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeEncodeError):
        raise SFTPrevalidationError("SFT record cannot be canonically hashed") from None
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _positive_int(value: object, *, field_name: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SFTPrevalidationError(f"{field_name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise SFTPrevalidationError(f"{field_name} must be <= {maximum}")
    return value


def _optional_revision(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SFTPrevalidationError("model_revision must be null or a non-empty string")
    return value


def _exact_mapping(value: object, *, fields: set[str], description: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise SFTPrevalidationError(f"{description} must be a mapping")
    keys = set(cast(Mapping[str, object], value))
    if keys != fields:
        raise SFTPrevalidationError(f"{description} has an invalid schema")
    return cast(Mapping[str, object], value)


def _ensure_unique_disjoint_splits(
    train_records: Sequence[Mapping[str, object]],
    validation_records: Sequence[Mapping[str, object]],
) -> None:
    def identifiers(records: Sequence[Mapping[str, object]], split: str) -> set[str]:
        result: set[str] = set()
        for record in records:
            problem_id = record.get("problem_id")
            if not isinstance(problem_id, str) or not problem_id.strip():
                raise SFTPrevalidationError(f"{split} SFT artifact contains an invalid problem_id")
            if problem_id in result:
                raise SFTPrevalidationError(f"{split} SFT artifact contains duplicate problem_id values")
            result.add(problem_id)
        return result

    if identifiers(train_records, "train") & identifiers(validation_records, "validation"):
        raise SFTPrevalidationError("SFT train and validation artifacts contain overlapping problem_id values")


def _load_tokenizer(model_id: str, model_revision: str | None) -> Any:
    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            revision=model_revision or "main",
            trust_remote_code=False,
        )
    except Exception as error:
        raise SFTPrevalidationError(f"could not load SFT tokenizer: {type(error).__name__}") from None
    chat_template = getattr(tokenizer, "chat_template", None)
    if not isinstance(chat_template, str) or not chat_template:
        raise SFTPrevalidationError("SFT tokenizer must provide a chat template")
    return tokenizer


def _prevalidate_split(
    records: Sequence[Mapping[str, object]],
    *,
    split: str,
    executor_factory: Callable[[], CodeExecutor],
    tokenizer: Any,
    max_seq_length: int,
    workers: int,
    progress_every: int,
    progress_callback: ProgressCallback | None,
) -> list[dict[str, object]]:
    if not records:
        raise SFTPrevalidationError(f"{split} SFT artifact must be non-empty")
    workers = _positive_int(workers, field_name="workers", maximum=_MAX_WORKERS)
    progress_every = _positive_int(progress_every, field_name="progress_every")
    thread_local = threading.local()
    rows: list[dict[str, object] | None] = [None] * len(records)
    started = time.perf_counter()

    def validate(index: int, record: Mapping[str, object]) -> tuple[int, SFTExample]:
        executor = getattr(thread_local, "executor", None)
        if executor is None:
            executor = executor_factory()
            thread_local.executor = executor
        try:
            example = validate_sft_record(record, executor=cast(CodeExecutor, executor))
        except SFTDataError as error:
            raise SFTPrevalidationError(f"{split} SFT record {index + 1}: {error}") from None
        return index, example

    futures: dict[Future[tuple[int, SFTExample]], int] = {}
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"sft-{split}")
    try:
        for index, record in enumerate(records):
            futures[pool.submit(validate, index, record)] = index
        for completed, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            try:
                result_index, example = future.result()
            except BaseException:
                for pending in futures:
                    pending.cancel()
                raise
            if result_index != index:
                raise SFTPrevalidationError("SFT prevalidation worker returned an invalid record index")
            token_count = sft_example_token_count(tokenizer, example)
            if token_count > max_seq_length:
                raise SFTPrevalidationError(
                    f"{split} SFT record {index + 1}: SFT sequence exceeds max_seq_length; "
                    "target truncation is forbidden"
                )
            rows[index] = {
                "index": index + 1,
                "problem_id": example.problem_id,
                "record_sha256": _record_sha256(records[index]),
                "token_count": token_count,
                "status": "passed",
            }
            if progress_callback is not None and (completed % progress_every == 0 or completed == len(records)):
                progress_callback(split, completed, len(records), time.perf_counter() - started)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    if any(row is None for row in rows):
        raise SFTPrevalidationError(f"{split} SFT prevalidation did not produce one result per record")
    return cast(list[dict[str, object]], rows)


def run_sft_prevalidation(
    *,
    dataset_path: Path,
    validation_dataset_path: Path | None,
    model_id: str,
    model_revision: str | None,
    max_seq_length: int,
    piston_config_path: Path,
    output_manifest: Path,
    workers: int = 4,
    progress_every: int = 25,
    progress_callback: ProgressCallback | None = None,
) -> SFTPrevalidationSummary:
    """Validate formal SFT data once through local Piston and write durable evidence."""
    max_seq_length = _positive_int(max_seq_length, field_name="max_seq_length")
    workers = _positive_int(workers, field_name="workers", maximum=_MAX_WORKERS)
    progress_every = _positive_int(progress_every, field_name="progress_every")
    if output_manifest.exists():
        raise SFTPrevalidationError("prevalidation manifest already exists; preserve evidence and choose a new path")

    try:
        train_records = load_training_artifact(dataset_path, kind=TrainingArtifactKind.SFT)
        validation_records = (
            []
            if validation_dataset_path is None
            else load_training_artifact(validation_dataset_path, kind=TrainingArtifactKind.SFT)
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise SFTPrevalidationError(f"could not load SFT artifact: {type(error).__name__}: {error}") from None
    if validation_records:
        _ensure_unique_disjoint_splits(train_records, validation_records)

    try:
        piston_config = load_piston_executor_config(piston_config_path)
        probe = PistonExecutor(piston_config)
        probe.validate_runtime()
    except Exception as error:
        raise SFTPrevalidationError(
            f"Piston prevalidation runtime is unavailable: {type(error).__name__}: {error}"
        ) from None

    tokenizer = _load_tokenizer(model_id, model_revision)
    environment = collect_environment()
    started = time.perf_counter()

    def executor_factory() -> CodeExecutor:
        return PistonExecutor(piston_config)

    train_rows = _prevalidate_split(
        train_records,
        split="train",
        executor_factory=executor_factory,
        tokenizer=tokenizer,
        max_seq_length=max_seq_length,
        workers=workers,
        progress_every=progress_every,
        progress_callback=progress_callback,
    )
    validation_rows = (
        []
        if not validation_records
        else _prevalidate_split(
            validation_records,
            split="validation",
            executor_factory=executor_factory,
            tokenizer=tokenizer,
            max_seq_length=max_seq_length,
            workers=workers,
            progress_every=progress_every,
            progress_callback=progress_callback,
        )
    )
    elapsed = time.perf_counter() - started
    token_counts = [cast(int, row["token_count"]) for row in train_rows + validation_rows]
    max_token_count = max(token_counts)
    manifest: dict[str, object] = {
        "schema_version": SFT_PREVALIDATION_SCHEMA_VERSION,
        "implementation_version": SFT_PREVALIDATION_IMPLEMENTATION_VERSION,
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validator_environment": environment,
        "model": {
            "model_id": model_id,
            "model_revision": model_revision,
            "max_seq_length": max_seq_length,
        },
        "piston": {
            "config_sha256": _sha256_file(piston_config_path, description="Piston config"),
            "executor_version": piston_executor_version(piston_config),
            "language": piston_config.language,
            "runtime_version": piston_config.version,
        },
        "train": {
            "dataset_sha256": _sha256_file(dataset_path, description="SFT train dataset"),
            "count": len(train_records),
            "records": train_rows,
        },
        "validation": (
            None
            if validation_dataset_path is None
            else {
                "dataset_sha256": _sha256_file(validation_dataset_path, description="SFT validation dataset"),
                "count": len(validation_records),
                "records": validation_rows,
            }
        ),
        "total_records": len(train_records) + len(validation_records),
        "max_token_count": max_token_count,
        "workers": workers,
        "elapsed_seconds": elapsed,
    }
    _atomic_write_json(output_manifest, manifest)
    return SFTPrevalidationSummary(
        manifest_path=output_manifest,
        train_samples=len(train_records),
        validation_samples=len(validation_records),
        total_samples=len(train_records) + len(validation_records),
        max_token_count=max_token_count,
        elapsed_seconds=elapsed,
        workers=workers,
    )


def _validate_manifest_split(
    value: object,
    *,
    split: str,
    dataset_path: Path,
    records: Sequence[Mapping[str, object]],
    max_seq_length: int,
) -> int:
    split_value = _exact_mapping(
        value,
        fields={"dataset_sha256", "count", "records"},
        description=f"prevalidation {split} section",
    )
    dataset_sha = split_value["dataset_sha256"]
    if not isinstance(dataset_sha, str) or dataset_sha != _sha256_file(dataset_path, description=f"{split} dataset"):
        raise SFTPrevalidationError(f"prevalidation {split} dataset hash does not match current data")
    count = split_value["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count != len(records):
        raise SFTPrevalidationError(f"prevalidation {split} count does not match current data")
    row_values = split_value["records"]
    if not isinstance(row_values, list) or len(row_values) != len(records):
        raise SFTPrevalidationError(f"prevalidation {split} record evidence is incomplete")
    max_token_count = 0
    for index, (row_value, record) in enumerate(zip(row_values, records, strict=True), start=1):
        row = _exact_mapping(
            row_value,
            fields={"index", "problem_id", "record_sha256", "token_count", "status"},
            description=f"prevalidation {split} record",
        )
        problem_id = record.get("problem_id")
        if row["index"] != index or row["problem_id"] != problem_id or row["status"] != "passed":
            raise SFTPrevalidationError(f"prevalidation {split} record {index} identity/status mismatch")
        if row["record_sha256"] != _record_sha256(record):
            raise SFTPrevalidationError(f"prevalidation {split} record {index} hash mismatch")
        token_count = row["token_count"]
        if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count <= 0:
            raise SFTPrevalidationError(f"prevalidation {split} record {index} has invalid token_count")
        if token_count > max_seq_length:
            raise SFTPrevalidationError(f"prevalidation {split} record {index} exceeds max_seq_length")
        max_token_count = max(max_token_count, token_count)
    return max_token_count


def validate_sft_prevalidation_manifest(
    manifest_path: Path,
    *,
    dataset_path: Path,
    validation_dataset_path: Path | None,
    model_id: str,
    model_revision: str | None,
    max_seq_length: int,
    piston_config_path: Path,
) -> SFTPrevalidationEvidence:
    """Fail closed unless a completed manifest exactly binds current formal SFT inputs."""
    max_seq_length = _positive_int(max_seq_length, field_name="max_seq_length")
    manifest_sha = _sha256_file(manifest_path, description="SFT prevalidation manifest")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SFTPrevalidationError("SFT prevalidation manifest is unreadable") from None
    manifest = _exact_mapping(
        raw,
        fields={
            "schema_version",
            "implementation_version",
            "status",
            "created_at",
            "validator_environment",
            "model",
            "piston",
            "train",
            "validation",
            "total_records",
            "max_token_count",
            "workers",
            "elapsed_seconds",
        },
        description="SFT prevalidation manifest",
    )
    if manifest["schema_version"] != SFT_PREVALIDATION_SCHEMA_VERSION:
        raise SFTPrevalidationError("unsupported SFT prevalidation manifest schema")
    if manifest["implementation_version"] != SFT_PREVALIDATION_IMPLEMENTATION_VERSION:
        raise SFTPrevalidationError("unsupported SFT prevalidation implementation version")
    if manifest["status"] != "completed":
        raise SFTPrevalidationError("SFT prevalidation manifest is not completed")
    created_at = manifest["created_at"]
    if not isinstance(created_at, str) or not created_at.strip():
        raise SFTPrevalidationError("SFT prevalidation manifest has invalid created_at")
    workers = manifest["workers"]
    _positive_int(workers, field_name="manifest workers", maximum=_MAX_WORKERS)
    elapsed = manifest["elapsed_seconds"]
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, int | float)
        or not math.isfinite(float(elapsed))
        or float(elapsed) < 0
    ):
        raise SFTPrevalidationError("SFT prevalidation manifest has invalid elapsed_seconds")

    model = _exact_mapping(
        manifest["model"],
        fields={"model_id", "model_revision", "max_seq_length"},
        description="prevalidation model section",
    )
    if model["model_id"] != model_id or _optional_revision(model["model_revision"]) != model_revision:
        raise SFTPrevalidationError("SFT prevalidation model identity does not match training config")
    if model["max_seq_length"] != max_seq_length:
        raise SFTPrevalidationError("SFT prevalidation max_seq_length does not match training config")

    try:
        piston_config = load_piston_executor_config(piston_config_path)
    except Exception as error:
        raise SFTPrevalidationError(f"could not load current Piston config: {type(error).__name__}") from None
    piston = _exact_mapping(
        manifest["piston"],
        fields={"config_sha256", "executor_version", "language", "runtime_version"},
        description="prevalidation piston section",
    )
    current_piston_sha = _sha256_file(piston_config_path, description="current Piston config")
    if piston["config_sha256"] != current_piston_sha:
        raise SFTPrevalidationError("SFT prevalidation Piston config hash does not match current config")
    current_executor_version = piston_executor_version(piston_config)
    if piston["executor_version"] != current_executor_version:
        raise SFTPrevalidationError("SFT prevalidation Piston executor definition does not match current config")
    if piston["language"] != piston_config.language or piston["runtime_version"] != piston_config.version:
        raise SFTPrevalidationError("SFT prevalidation Piston runtime identity does not match current config")

    try:
        train_records = load_training_artifact(dataset_path, kind=TrainingArtifactKind.SFT)
        validation_records = (
            []
            if validation_dataset_path is None
            else load_training_artifact(validation_dataset_path, kind=TrainingArtifactKind.SFT)
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise SFTPrevalidationError(f"could not load current SFT artifact: {type(error).__name__}: {error}") from None
    if validation_records:
        _ensure_unique_disjoint_splits(train_records, validation_records)
    train_max = _validate_manifest_split(
        manifest["train"],
        split="train",
        dataset_path=dataset_path,
        records=train_records,
        max_seq_length=max_seq_length,
    )
    if validation_dataset_path is None:
        if manifest["validation"] is not None:
            raise SFTPrevalidationError("prevalidation unexpectedly contains a validation split")
        validation_max = 0
    else:
        if manifest["validation"] is None:
            raise SFTPrevalidationError("prevalidation is missing the configured validation split")
        validation_max = _validate_manifest_split(
            manifest["validation"],
            split="validation",
            dataset_path=validation_dataset_path,
            records=validation_records,
            max_seq_length=max_seq_length,
        )
    total = len(train_records) + len(validation_records)
    if manifest["total_records"] != total:
        raise SFTPrevalidationError("prevalidation total_records does not match current data")
    observed_max = max(train_max, validation_max)
    if manifest["max_token_count"] != observed_max:
        raise SFTPrevalidationError("prevalidation max_token_count is inconsistent with record evidence")

    validator_environment = manifest["validator_environment"]
    if not isinstance(validator_environment, Mapping):
        raise SFTPrevalidationError("prevalidation validator_environment must be a mapping")
    project_commit = validator_environment.get("project_commit")
    if project_commit is not None and (not isinstance(project_commit, str) or not project_commit.strip()):
        raise SFTPrevalidationError("prevalidation validator project commit is invalid")
    return SFTPrevalidationEvidence(
        manifest_sha256=manifest_sha,
        validator_project_commit=project_commit,
        piston_config_sha256=current_piston_sha,
        piston_executor_version=current_executor_version,
        train_samples=len(train_records),
        validation_samples=len(validation_records),
        max_token_count=observed_max,
    )
