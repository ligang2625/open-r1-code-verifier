"""Strict checker for no-backfill WP9-c reduced calibrated pools."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, json_values_equal, loads_strict
from code_verifier.data.leakage_checks import LeakageError, TrainingArtifactKind, load_training_artifact
from code_verifier.training.calibration import (
    CalibrationError,
    CalibrationPoolSummary,
    _calibration_disposition,
    _validate_calibration_record,
)

REDUCED_CALIBRATED_POOL_SCHEMA = "wp9c-reduced-calibration-v1"
REDUCED_POOL_PROTOCOL = "wp9c-reduced-quota-current-viable-v1"
_POST_CALIBRATION_RULE = "report actual class counts; exclude dual_uninformative without backfill"
_CLASS_NAMES = ("dual_informative", "public_only", "hidden_only", "dual_uninformative")
_REQUIRED_ARTIFACTS = {
    "manifest/active_selection.jsonl",
    "manifest/excluded_dual_uninformative.jsonl",
    "manifest/problem_order.jsonl",
    "manifest/retry_problem_ids.jsonl",
    "records/calibration.jsonl",
    "reports/classification_summary.json",
    "reports/disposition_summary.json",
    "reports/pool_composition.json",
    "training/hidden_grpo.jsonl",
    "training/public_grpo.jsonl",
}
_REQUIRED_MANIFEST_FIELDS = {
    "schema_version",
    "protocol_amendment",
    "status",
    "evidence_class",
    "seed",
    "post_calibration_rule",
    "source_expansion_allowed",
    "backfill_performed",
    "minimum_pool_count",
    "precalibration_problem_count",
    "calibrated_problem_count",
    "retry_problem_count",
    "active_problem_count",
    "excluded_dual_uninformative_count",
    "calibrated_problem_order_sha256",
    "active_order_sha256",
    "class_counts",
    "active_class_counts",
    "disposition_counts",
    "sft_checkpoint",
    "public_definition_sha256",
    "hidden_definition_sha256",
    "bindings",
    "artifacts",
}


class ReducedCalibratedPoolError(RuntimeError):
    """Raised when a reduced no-backfill calibrated pool is invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ReducedCalibratedPoolError(f"could not hash reduced calibration artifact: {path}") from error
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise ReducedCalibratedPoolError(f"could not read strict JSON: {path}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ReducedCalibratedPoolError(f"strict JSON object required: {path}")
    return cast(dict[str, object], value)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ReducedCalibratedPoolError(f"could not read JSONL: {path}") from error
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise ReducedCalibratedPoolError(f"invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ReducedCalibratedPoolError(f"JSON object required at {path}:{line_number}")
        rows.append(cast(dict[str, object], value))
    return rows


def _integer_count(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReducedCalibratedPoolError(f"{label} must be a nonnegative integer")
    return value


def _class_counts(value: object, *, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(_CLASS_NAMES):
        raise ReducedCalibratedPoolError(f"{label} has invalid class keys")
    return {name: _integer_count(value[name], label=f"{label}.{name}") for name in _CLASS_NAMES}


def _validate_manifest(pool_dir: Path) -> dict[str, object]:
    manifest = _load_json(pool_dir / "calibration_manifest.json")
    if set(manifest) != _REQUIRED_MANIFEST_FIELDS:
        raise ReducedCalibratedPoolError("reduced calibration manifest fields are invalid")
    if (
        manifest.get("schema_version") != REDUCED_CALIBRATED_POOL_SCHEMA
        or manifest.get("protocol_amendment") != REDUCED_POOL_PROTOCOL
        or manifest.get("status") != "completed"
        or manifest.get("evidence_class") != "formal_calibration"
        or manifest.get("seed") != 42
        or manifest.get("post_calibration_rule") != _POST_CALIBRATION_RULE
        or manifest.get("source_expansion_allowed") is not False
        or manifest.get("backfill_performed") is not False
        or manifest.get("minimum_pool_count") is not None
    ):
        raise ReducedCalibratedPoolError("reduced calibration manifest identity/protocol is invalid")
    for key in (
        "calibrated_problem_order_sha256",
        "active_order_sha256",
        "public_definition_sha256",
        "hidden_definition_sha256",
    ):
        value = manifest.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ReducedCalibratedPoolError(f"reduced calibration manifest {key} is not lowercase SHA256")
    if not isinstance(manifest.get("bindings"), Mapping) or not isinstance(manifest.get("sft_checkpoint"), Mapping):
        raise ReducedCalibratedPoolError("reduced calibration manifest authority bindings are invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != _REQUIRED_ARTIFACTS:
        raise ReducedCalibratedPoolError("reduced calibration artifact inventory is invalid")
    expected_files = {Path(relative) for relative in _REQUIRED_ARTIFACTS} | {Path("calibration_manifest.json")}
    actual_files = {path.relative_to(pool_dir) for path in pool_dir.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise ReducedCalibratedPoolError("reduced calibration artifact tree differs from exact inventory")
    for relative in _REQUIRED_ARTIFACTS:
        expected_sha = artifacts.get(relative)
        if not isinstance(expected_sha, str) or _sha256(pool_dir / relative) != expected_sha:
            raise ReducedCalibratedPoolError(f"reduced calibration artifact hash mismatch: {relative}")
    return manifest


def _validate_records(
    pool_dir: Path, manifest: Mapping[str, object]
) -> tuple[list[dict[str, object]], list[str], set[str]]:
    records = _load_jsonl(pool_dir / "records/calibration.jsonl")
    retry_rows = _load_jsonl(pool_dir / "manifest/retry_problem_ids.jsonl")
    if any(set(row) != {"problem_id"} or not isinstance(row.get("problem_id"), str) for row in retry_rows):
        raise ReducedCalibratedPoolError("reduced calibration retry manifest rows are invalid")
    retry_ids = [cast(str, row["problem_id"]) for row in retry_rows]
    if retry_ids != sorted(retry_ids) or len(retry_ids) != len(set(retry_ids)):
        raise ReducedCalibratedPoolError("reduced calibration retry IDs must be sorted and unique")
    retry_set = set(retry_ids)

    calibrated_count = _integer_count(manifest.get("calibrated_problem_count"), label="calibrated_problem_count")
    precalibration_count = _integer_count(
        manifest.get("precalibration_problem_count"), label="precalibration_problem_count"
    )
    retry_count = _integer_count(manifest.get("retry_problem_count"), label="retry_problem_count")
    if calibrated_count == 0 or calibrated_count != precalibration_count or len(records) != calibrated_count:
        raise ReducedCalibratedPoolError("reduced calibration full population count is invalid")
    if len(retry_ids) != retry_count or retry_count > calibrated_count:
        raise ReducedCalibratedPoolError("reduced calibration retry count is invalid")
    problem_ids = [record.get("problem_id") for record in records]
    if any(not isinstance(problem_id, str) or not problem_id for problem_id in problem_ids):
        raise ReducedCalibratedPoolError("reduced calibration record problem IDs are invalid")
    typed_ids = cast(list[str], problem_ids)
    if len(typed_ids) != len(set(typed_ids)) or manifest.get("calibrated_problem_order_sha256") != stable_json_hash(
        typed_ids
    ):
        raise ReducedCalibratedPoolError("reduced calibration full problem order is invalid")
    if any(problem_id not in set(typed_ids) for problem_id in retry_ids):
        raise ReducedCalibratedPoolError("reduced calibration retry manifest is not a subset of calibrated problems")
    for record in records:
        problem_id = cast(str, record["problem_id"])
        try:
            _validate_calibration_record(
                record,
                expected_sample_indices=range(16) if problem_id in retry_set else range(8),
                require_record_hash=True,
            )
        except CalibrationError as error:
            raise ReducedCalibratedPoolError(
                f"invalid reduced calibration record for {problem_id}: {error}"
            ) from error
    return records, typed_ids, retry_set


def _validate_selection(
    pool_dir: Path,
    manifest: Mapping[str, object],
    records: list[dict[str, object]],
    retry_set: set[str],
) -> tuple[list[str], Counter[str]]:
    class_counts = Counter(cast(str, record["calibration_class"]) for record in records)
    expected_class_counts = {name: class_counts.get(name, 0) for name in _CLASS_NAMES}
    if _class_counts(manifest.get("class_counts"), label="class_counts") != expected_class_counts:
        raise ReducedCalibratedPoolError("reduced calibration class counts do not recompute")
    if _load_json(pool_dir / "reports/classification_summary.json") != expected_class_counts:
        raise ReducedCalibratedPoolError("reduced calibration classification report does not recompute")

    informative = [record for record in records if record.get("calibration_class") != "dual_uninformative"]
    active_rows = _load_jsonl(pool_dir / "manifest/active_selection.jsonl")
    active_ids = [cast(str, record["problem_id"]) for record in informative]
    expected_active_rows = [
        {
            "ordinal": ordinal,
            "problem_id": cast(str, record["problem_id"]),
            "calibration_class": record["calibration_class"],
            "calibration_record_sha256": record["calibration_record_sha256"],
            "overlap_origin": record["overlap_origin"],
        }
        for ordinal, record in enumerate(informative)
    ]
    if active_rows != expected_active_rows:
        raise ReducedCalibratedPoolError(
            "reduced calibration active selection is not the exact informative population"
        )
    if manifest.get("active_order_sha256") != stable_json_hash(active_ids):
        raise ReducedCalibratedPoolError("reduced calibration active order hash does not recompute")
    active_count = _integer_count(manifest.get("active_problem_count"), label="active_problem_count")
    if active_count != len(active_ids):
        raise ReducedCalibratedPoolError("reduced calibration active problem count does not recompute")
    problem_order = _load_jsonl(pool_dir / "manifest/problem_order.jsonl")
    if problem_order != [
        {"ordinal": ordinal, "problem_id": problem_id} for ordinal, problem_id in enumerate(active_ids)
    ]:
        raise ReducedCalibratedPoolError("reduced calibration problem_order manifest differs from active selection")

    active_class_counts = Counter(cast(str, record["calibration_class"]) for record in informative)
    expected_active_counts = {name: active_class_counts.get(name, 0) for name in _CLASS_NAMES}
    if _class_counts(manifest.get("active_class_counts"), label="active_class_counts") != expected_active_counts:
        raise ReducedCalibratedPoolError("reduced calibration active class counts do not recompute")
    if expected_active_counts["dual_uninformative"] != 0:
        raise ReducedCalibratedPoolError("reduced active pool may not contain dual-uninformative problems")
    for name in ("dual_informative", "public_only", "hidden_only"):
        if expected_active_counts[name] != expected_class_counts[name]:
            raise ReducedCalibratedPoolError("reduced no-backfill pool dropped an informative class member")

    disposition_counts: Counter[str] = Counter()
    expected_excluded: list[dict[str, object]] = []
    for record in records:
        problem_id = cast(str, record["problem_id"])
        disposition = _calibration_disposition(record, retried=problem_id in retry_set)
        disposition_counts[disposition] += 1
        if disposition != "eligible":
            expected_excluded.append(
                {
                    "problem_id": problem_id,
                    "reason": disposition,
                    "retried": problem_id in retry_set,
                    "calibration_class": record["calibration_class"],
                    "calibration_record_sha256": record["calibration_record_sha256"],
                }
            )
    excluded = _load_jsonl(pool_dir / "manifest/excluded_dual_uninformative.jsonl")
    if excluded != expected_excluded:
        raise ReducedCalibratedPoolError("reduced calibration exclusion manifest does not recompute")
    excluded_count = _integer_count(
        manifest.get("excluded_dual_uninformative_count"), label="excluded_dual_uninformative_count"
    )
    if excluded_count != len(excluded) or excluded_count != expected_class_counts["dual_uninformative"]:
        raise ReducedCalibratedPoolError("reduced calibration excluded count does not match dual-uninformative class")
    expected_dispositions = dict(sorted(disposition_counts.items()))
    if manifest.get("disposition_counts") != expected_dispositions:
        raise ReducedCalibratedPoolError("reduced calibration disposition counts do not recompute")
    if _load_json(pool_dir / "reports/disposition_summary.json") != expected_dispositions:
        raise ReducedCalibratedPoolError("reduced calibration disposition report does not recompute")

    composition = _load_json(pool_dir / "reports/pool_composition.json")
    expected_composition = {
        "precalibration_problem_count": len(records),
        "retry_problem_count": len(retry_set),
        "active_problem_count": len(active_ids),
        "excluded_dual_uninformative_count": len(excluded),
        "class_counts": expected_class_counts,
        "active_class_counts": expected_active_counts,
        "disposition_counts": expected_dispositions,
        "backfill_performed": False,
        "minimum_pool_count": None,
    }
    if composition != expected_composition:
        raise ReducedCalibratedPoolError("reduced calibration pool composition does not recompute")
    return active_ids, active_class_counts


def _validate_training_views(
    pool_dir: Path,
    records: list[dict[str, object]],
    active_ids: list[str],
) -> tuple[Path, Path]:
    public_path = pool_dir / "training/public_grpo.jsonl"
    hidden_path = pool_dir / "training/hidden_grpo.jsonl"
    try:
        public = load_training_artifact(public_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
        hidden = load_training_artifact(hidden_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
    except LeakageError as error:
        raise ReducedCalibratedPoolError(f"reduced calibration training view failed leakage check: {error}") from error
    if [row["problem_id"] for row in public] != active_ids or [row["problem_id"] for row in hidden] != active_ids:
        raise ReducedCalibratedPoolError("reduced Public/Hidden training views do not share the exact active order")
    record_by_id = {cast(str, record["problem_id"]): record for record in records}
    for public_row, hidden_row in zip(public, hidden, strict=True):
        problem_id = cast(str, public_row["problem_id"])
        if problem_id != hidden_row["problem_id"]:
            raise ReducedCalibratedPoolError("reduced Public/Hidden training IDs differ")
        public_metadata = public_row.get("metadata")
        hidden_metadata = hidden_row.get("metadata")
        if not isinstance(public_metadata, Mapping) or not isinstance(hidden_metadata, Mapping):
            raise ReducedCalibratedPoolError("reduced Public/Hidden training metadata is invalid")
        calibrated = record_by_id[problem_id]
        for metadata in (public_metadata, hidden_metadata):
            if (
                metadata.get("calibration_class") != calibrated["calibration_class"]
                or metadata.get("calibration_record_sha256") != calibrated["calibration_record_sha256"]
                or metadata.get("overlap_origin") != calibrated["overlap_origin"]
            ):
                raise ReducedCalibratedPoolError(
                    "reduced training calibration metadata differs from calibration record"
                )
        hidden_public_projection = {key: value for key, value in hidden_row.items() if key != "train_hidden_tests"}
        if not json_values_equal(public_row, hidden_public_projection):
            raise ReducedCalibratedPoolError("reduced Public/Hidden training whitelist projections differ")
    return public_path, hidden_path


def check_reduced_calibrated_pool(pool_dir: Path) -> CalibrationPoolSummary:
    """Strictly validate a completed no-backfill reduced calibrated pool."""
    manifest = _validate_manifest(pool_dir)
    records, _, retry_set = _validate_records(pool_dir, manifest)
    active_ids, active_class_counts = _validate_selection(pool_dir, manifest, records, retry_set)
    public_path, hidden_path = _validate_training_views(pool_dir, records, active_ids)
    sft_overlap_count = sum(
        record.get("overlap_origin") == "sft_reuse" for record in records if record["problem_id"] in set(active_ids)
    )
    return CalibrationPoolSummary(
        pool_dir=pool_dir,
        selected_problems=len(active_ids),
        dual_informative=active_class_counts.get("dual_informative", 0),
        public_only=active_class_counts.get("public_only", 0),
        hidden_only=active_class_counts.get("hidden_only", 0),
        sft_overlap_count=sft_overlap_count,
        active_order_sha256=cast(str, manifest["active_order_sha256"]),
        calibration_manifest=pool_dir / "calibration_manifest.json",
        public_grpo_jsonl=public_path,
        hidden_grpo_jsonl=hidden_path,
    )
