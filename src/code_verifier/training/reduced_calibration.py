"""Checkpoint-bound scoring for the WP9-c reduced calibration pool."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.prepare import DataPreparationError, load_canonical_jsonl
from code_verifier.data.schema import CodeProblem, JsonValue, problem_to_mapping
from code_verifier.execution.base import CodeExecutor
from code_verifier.rewards.common import RewardContractError, compute_code_rewards_concurrent
from code_verifier.training.calibration import (
    _load_input_bundle,
    _score_record,
    load_completed_calibration_generation,
)
from code_verifier.training.calibration_checkpoint import (
    ScoringCheckpointError,
    append_scoring_checkpoint_record,
    load_or_initialize_scoring_checkpoint,
    scoring_checkpoint_dir,
)

REDUCED_CALIBRATION_SCORING_SCHEMA_VERSION = "wp9c-reduced-calibration-scoring-v1"
REDUCED_POOL_PROTOCOL = "wp9c-reduced-quota-current-viable-v1"


class ReducedCalibrationScoringError(RuntimeError):
    """Raised when reduced-pool scoring inputs, execution, or artifacts are invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ReducedCalibrationScoringError(f"could not hash required file: {path}") from error
    return digest.hexdigest()


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=None if pretty else (",", ":"),
            indent=2 if pretty else None,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError):
        raise ReducedCalibrationScoringError("reduced calibration artifact is not finite JSON") from None
    return (text + "\n").encode()


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _write_json(path: Path, value: object) -> str:
    content = _json_bytes(value, pretty=True)
    _atomic_bytes(path, content)
    return hashlib.sha256(content).hexdigest()


def _write_jsonl(path: Path, records: Sequence[Mapping[str, object]]) -> str:
    content = b"".join(_json_bytes(dict(record)) for record in records)
    _atomic_bytes(path, content)
    return hashlib.sha256(content).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise ReducedCalibrationScoringError(f"could not read strict JSON: {path}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ReducedCalibrationScoringError(f"strict JSON object required: {path}")
    return cast(dict[str, object], value)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ReducedCalibrationScoringError(f"could not read JSONL: {path}") from error
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise ReducedCalibrationScoringError(f"invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ReducedCalibrationScoringError(f"JSON object required at {path}:{line_number}")
        records.append(cast(dict[str, object], value))
    return records


def _definition_sha256(problems: Sequence[CodeProblem], *, test_field: str) -> str:
    if test_field not in {"visible_tests", "train_hidden_tests"}:
        raise ReducedCalibrationScoringError("invalid reduced calibration test definition selector")
    projection: list[dict[str, JsonValue]] = []
    for problem in problems:
        row = problem_to_mapping(problem)
        projection.append(
            {
                "problem_id": row["problem_id"],
                "function_name": row["function_name"],
                "metadata": row["metadata"],
                "tests": row[test_field],
            }
        )
    return stable_json_hash(projection)


def _validate_authority(
    *,
    c24_checkpoint_path: Path,
    c25_checkpoint_path: Path,
    formal_problems_path: Path,
    input_bundle_dir: Path,
    generation_run_dir: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    c24 = _load_json(c24_checkpoint_path)
    c25 = _load_json(c25_checkpoint_path)
    c24_sha = _sha256(c24_checkpoint_path)
    c25_sha = _sha256(c25_checkpoint_path)
    if c24_sha != "48ac639cc3fba0c540437bfbba0b65403575f424c06eefd6b8c51d00771313f1":
        raise ReducedCalibrationScoringError("C24 checkpoint SHA256 is not the accepted reduced-pool authority")
    if c25_sha != "0ba51b0b502357482d6eba137d900b6686a19bab3470255992502a9ebb750916":
        raise ReducedCalibrationScoringError("C25 checkpoint SHA256 is not the accepted generation authority")
    if (
        c24.get("status") != "completed_verified"
        or c24.get("protocol_amendment") != REDUCED_POOL_PROTOCOL
        or cast(Mapping[str, object], c24.get("verified_result", {})).get("precalibration_pool_total") != 1602
    ):
        raise ReducedCalibrationScoringError("C24 reduced-pool checkpoint identity is invalid")
    c24_artifacts = c24.get("verified_artifacts")
    if not isinstance(c24_artifacts, Mapping):
        raise ReducedCalibrationScoringError("C24 verified artifact bindings are invalid")
    formal_sha = _sha256(formal_problems_path)
    if formal_sha != c24_artifacts.get("external_formal_problems_sha256"):
        raise ReducedCalibrationScoringError("current formal Public/Hidden definitions do not match C24")
    if (
        c25.get("status") != "awaiting_operator"
        or c25.get("protocol_amendment") != REDUCED_POOL_PROTOCOL
        or c25.get("expected_problem_count") != 1602
        or c25.get("expected_record_count") != 12816
        or c25.get("problem_batch_size") != 4
    ):
        raise ReducedCalibrationScoringError("C25 checkpoint generation contract is invalid")
    c25_bindings = c25.get("bindings")
    if not isinstance(c25_bindings, Mapping):
        raise ReducedCalibrationScoringError("C25 checkpoint bindings are invalid")
    if c25_bindings.get("c24_checkpoint_sha256") != c24_sha:
        raise ReducedCalibrationScoringError("C25 is not bound to the accepted C24 checkpoint")
    if _sha256(input_bundle_dir / "input_manifest.json") != c25_bindings.get("input_manifest_sha256"):
        raise ReducedCalibrationScoringError("C25 input manifest does not match its checkpoint binding")
    if _sha256(input_bundle_dir / "inputs.jsonl") != c25_bindings.get("inputs_sha256"):
        raise ReducedCalibrationScoringError("C25 input records do not match their checkpoint binding")
    generation_manifest, _ = load_completed_calibration_generation(generation_run_dir)
    if generation_manifest.get("input_manifest_sha256") != c25_bindings.get("input_manifest_sha256"):
        raise ReducedCalibrationScoringError("generation run is not bound to the accepted C25 input manifest")
    if generation_manifest.get("input_records_sha256") != c25_bindings.get("inputs_sha256"):
        raise ReducedCalibrationScoringError("generation run is not bound to the accepted C25 input records")
    if generation_manifest.get("sft_checkpoint") != c25.get("sft_identity"):
        raise ReducedCalibrationScoringError("generation run frozen-B identity differs from C25")
    return c24, c25


def _group_generation_rows(
    generations: Sequence[dict[str, object]], *, block_index: int
) -> tuple[list[str], dict[str, list[dict[str, object]]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in generations:
        problem_id = row.get("problem_id")
        if not isinstance(problem_id, str) or not problem_id:
            raise ReducedCalibrationScoringError("generation record has an invalid problem_id")
        grouped.setdefault(problem_id, []).append(row)
    expected_indices = list(range(block_index * 8, block_index * 8 + 8))
    for problem_id, rows in grouped.items():
        if len(rows) != 8:
            raise ReducedCalibrationScoringError(f"problem {problem_id} does not contain exactly eight completions")
        if [row.get("sample_index") for row in rows] != expected_indices:
            raise ReducedCalibrationScoringError(f"problem {problem_id} sample indices are not the exact block")
        if any(row.get("block_index") != block_index for row in rows):
            raise ReducedCalibrationScoringError(f"problem {problem_id} block index drift")
        if any(not isinstance(row.get("completion"), str) for row in rows):
            raise ReducedCalibrationScoringError(f"problem {problem_id} completion bytes are invalid")
    return list(grouped), grouped


def score_reduced_pool_calibration_generation(
    *,
    c24_checkpoint_path: Path,
    c25_checkpoint_path: Path,
    formal_problems_path: Path,
    input_bundle_dir: Path,
    generation_run_dir: Path,
    piston_config_path: Path,
    output_dir: Path,
    executor_factory: Callable[[], CodeExecutor],
    workers: int,
) -> Path:
    """Fresh-score one accepted reduced-pool k=8 generation block with both verifier definitions."""
    if output_dir.exists():
        raise ReducedCalibrationScoringError("reduced calibration scoring output directory already exists")
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 64:
        raise ReducedCalibrationScoringError("workers must be an integer in [1, 64]")
    _validate_authority(
        c24_checkpoint_path=c24_checkpoint_path,
        c25_checkpoint_path=c25_checkpoint_path,
        formal_problems_path=formal_problems_path,
        input_bundle_dir=input_bundle_dir,
        generation_run_dir=generation_run_dir,
    )
    input_manifest, input_records = _load_input_bundle(input_bundle_dir)
    generation_manifest, generations = load_completed_calibration_generation(generation_run_dir)
    try:
        formal_problems = load_canonical_jsonl(formal_problems_path)
    except DataPreparationError as error:
        raise ReducedCalibrationScoringError(
            f"current formal reduced-pool definitions are invalid: {error}"
        ) from error
    if len(input_records) != 1602 or len(formal_problems) != 1602:
        raise ReducedCalibrationScoringError("C24/C25 reduced-pool authority must contain exactly 1602 problems")
    input_ids = [record.problem_id for record in input_records]
    formal_ids = [problem.problem_id for problem in formal_problems]
    if input_ids != formal_ids or len(set(input_ids)) != 1602:
        raise ReducedCalibrationScoringError("C24 formal definition order does not exactly match the C25 input order")
    formal_by_id = {problem.problem_id: problem for problem in formal_problems}
    input_by_id = {record.problem_id: record for record in input_records}
    for input_record, problem in zip(input_records, formal_problems, strict=True):
        if (
            input_record.function_name != problem.function_name
            or input_record.source_name != problem.source
            or input_record.difficulty != problem.metadata.difficulty
        ):
            raise ReducedCalibrationScoringError("C24/C25 problem identity projection differs")
    block_index = generation_manifest.get("block_index")
    if block_index not in {0, 1}:
        raise ReducedCalibrationScoringError("generation block index is invalid")
    problem_ids, grouped = _group_generation_rows(generations, block_index=cast(int, block_index))
    if len(problem_ids) != len(set(problem_ids)):
        raise ReducedCalibrationScoringError("generation problem IDs are not unique")
    if any(problem_id not in formal_by_id for problem_id in problem_ids):
        raise ReducedCalibrationScoringError("generation contains a problem outside the current reduced pool")
    if block_index == 0 and problem_ids != input_ids:
        raise ReducedCalibrationScoringError("initial generation order is not the exact current 1602 order")
    if generation_manifest.get("problem_order_sha256") != stable_json_hash(problem_ids):
        raise ReducedCalibrationScoringError("generation problem order hash does not match its records")

    public_definition_sha256 = _definition_sha256(formal_problems, test_field="visible_tests")
    hidden_definition_sha256 = _definition_sha256(formal_problems, test_field="train_hidden_tests")
    checkpoint_manifest = {
        "version": 1,
        "schema_version": REDUCED_CALIBRATION_SCORING_SCHEMA_VERSION,
        "protocol": REDUCED_POOL_PROTOCOL,
        "scoring_semantics": "same_completion_bytes_public_then_hidden_v1",
        "block_index": block_index,
        "workers": workers,
        "problem_count": len(problem_ids),
        "problem_order_sha256": stable_json_hash(problem_ids),
        "piston_config_sha256": _sha256(piston_config_path),
        "c24_checkpoint_sha256": _sha256(c24_checkpoint_path),
        "c25_checkpoint_sha256": _sha256(c25_checkpoint_path),
        "formal_problems_sha256": _sha256(formal_problems_path),
        "public_definition_sha256": public_definition_sha256,
        "hidden_definition_sha256": hidden_definition_sha256,
        "input_manifest_sha256": _sha256(input_bundle_dir / "input_manifest.json"),
        "input_records_sha256": _sha256(input_bundle_dir / "inputs.jsonl"),
        "generation_run_manifest_sha256": _sha256(generation_run_dir / "run.json"),
        "generation_records_sha256": generation_manifest["records_sha256"],
        "sft_checkpoint": generation_manifest["sft_checkpoint"],
    }
    checkpoint_dir = scoring_checkpoint_dir(output_dir)
    try:
        score_records, checkpoint_byte_count = load_or_initialize_scoring_checkpoint(
            checkpoint_dir,
            expected_manifest=checkpoint_manifest,
            expected_problem_ids=problem_ids,
        )
    except (ScoringCheckpointError, OSError) as error:
        raise ReducedCalibrationScoringError(
            f"reduced calibration scoring checkpoint recovery failed: {error}"
        ) from error
    checkpoint_problem_count = len(score_records)
    for problem_index, problem_id in enumerate(problem_ids):
        if problem_index < checkpoint_problem_count:
            continue
        generation_rows = grouped[problem_id]
        formal_mapping = problem_to_mapping(formal_by_id[problem_id])
        completions = [cast(str, row["completion"]) for row in generation_rows]
        completion_sha256_before = [hashlib.sha256(item.encode()).hexdigest() for item in completions]
        functions = [cast(str, formal_mapping["function_name"])] * 8
        metadata_batch = [cast(Mapping[str, object], formal_mapping["metadata"])] * 8
        try:
            _, public_components = compute_code_rewards_concurrent(
                completions,
                [cast(Sequence[Mapping[str, object]], formal_mapping["visible_tests"])] * 8,
                functions,
                metadata_batch,
                executor_factory=executor_factory,
                mode="public",
                max_concurrency=workers,
            )
            if [hashlib.sha256(item.encode()).hexdigest() for item in completions] != completion_sha256_before:
                raise ReducedCalibrationScoringError("Public scoring changed completion bytes")
            _, hidden_components = compute_code_rewards_concurrent(
                completions,
                [cast(Sequence[Mapping[str, object]], formal_mapping["train_hidden_tests"])] * 8,
                functions,
                metadata_batch,
                executor_factory=executor_factory,
                mode="hidden",
                max_concurrency=workers,
            )
        except RewardContractError as error:
            raise ReducedCalibrationScoringError(f"reduced calibration reward contract failed: {error}") from error
        if [hashlib.sha256(item.encode()).hexdigest() for item in completions] != completion_sha256_before:
            raise ReducedCalibrationScoringError("Hidden scoring changed completion bytes")
        infrastructure_failures = [
            (
                mode,
                generation_rows[index].get("sample_index"),
                item.get("infrastructure_failure_kind"),
                item.get("status"),
            )
            for mode, components in (("public", public_components), ("hidden", hidden_components))
            for index, item in enumerate(components)
            if bool(item.get("infrastructure_failure"))
        ]
        if infrastructure_failures:
            raise ReducedCalibrationScoringError(
                f"infrastructure failure is fail-closed for problem_id={problem_id}: {infrastructure_failures}"
            )
        record = _score_record(
            input_record=input_by_id[problem_id],
            generation_rows=generation_rows,
            public_components=public_components,
            hidden_components=hidden_components,
        )
        if record.get("completion_sha256") != completion_sha256_before:
            raise ReducedCalibrationScoringError("score record completion-byte binding mismatch")
        try:
            checkpoint_problem_count, checkpoint_byte_count = append_scoring_checkpoint_record(
                checkpoint_dir,
                record,
                committed_problem_count=checkpoint_problem_count,
                committed_byte_count=checkpoint_byte_count,
            )
        except (ScoringCheckpointError, OSError) as error:
            raise ReducedCalibrationScoringError(f"reduced calibration checkpoint commit failed: {error}") from error
        score_records.append(record)
    if checkpoint_problem_count != len(problem_ids) or len(score_records) != len(problem_ids):
        raise ReducedCalibrationScoringError("reduced calibration scoring did not cover the exact problem order")

    retry_ids = sorted(
        cast(str, record["problem_id"])
        for record in score_records
        if block_index == 0
        and record.get("public_all_test_zero") is True
        and record.get("hidden_all_test_zero") is True
    )
    if len(retry_ids) != len(set(retry_ids)) or any(problem_id not in input_by_id for problem_id in retry_ids):
        raise ReducedCalibrationScoringError("derived retry IDs are not unique members of the current 1602")

    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records_sha256 = _write_jsonl(temporary / "records" / "scoring.jsonl", score_records)
        retry_sha256 = _write_jsonl(
            temporary / "manifest" / "retry_problem_ids.jsonl",
            [{"problem_id": problem_id} for problem_id in retry_ids],
        )
        manifest = {
            **checkpoint_manifest,
            "status": "completed",
            "records_sha256": records_sha256,
            "retry_problem_count": len(retry_ids),
            "retry_problem_ids_sha256": retry_sha256,
        }
        _write_json(temporary / "score_manifest.json", manifest)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    check_reduced_pool_calibration_scoring(output_dir)
    return output_dir


def check_reduced_pool_calibration_scoring(output_dir: Path) -> dict[str, object]:
    """Strictly read back one completed reduced-pool scoring artifact."""
    manifest = _load_json(output_dir / "score_manifest.json")
    required = {
        "version",
        "schema_version",
        "protocol",
        "scoring_semantics",
        "block_index",
        "workers",
        "problem_count",
        "problem_order_sha256",
        "piston_config_sha256",
        "c24_checkpoint_sha256",
        "c25_checkpoint_sha256",
        "formal_problems_sha256",
        "public_definition_sha256",
        "hidden_definition_sha256",
        "input_manifest_sha256",
        "input_records_sha256",
        "generation_run_manifest_sha256",
        "generation_records_sha256",
        "sft_checkpoint",
        "status",
        "records_sha256",
        "retry_problem_count",
        "retry_problem_ids_sha256",
    }
    if (
        set(manifest) != required
        or manifest.get("version") != 1
        or manifest.get("schema_version") != REDUCED_CALIBRATION_SCORING_SCHEMA_VERSION
        or manifest.get("protocol") != REDUCED_POOL_PROTOCOL
        or manifest.get("scoring_semantics") != "same_completion_bytes_public_then_hidden_v1"
        or manifest.get("status") != "completed"
    ):
        raise ReducedCalibrationScoringError("reduced calibration score manifest is invalid")
    records_path = output_dir / "records" / "scoring.jsonl"
    retry_path = output_dir / "manifest" / "retry_problem_ids.jsonl"
    records = _load_jsonl(records_path)
    retry_records = _load_jsonl(retry_path)
    if manifest.get("records_sha256") != _sha256(records_path):
        raise ReducedCalibrationScoringError("reduced calibration scoring records SHA256 mismatch")
    if manifest.get("retry_problem_ids_sha256") != _sha256(retry_path):
        raise ReducedCalibrationScoringError("reduced calibration retry manifest SHA256 mismatch")
    if manifest.get("problem_count") != len(records):
        raise ReducedCalibrationScoringError("reduced calibration score problem count mismatch")
    problem_ids = [record.get("problem_id") for record in records]
    if any(not isinstance(problem_id, str) for problem_id in problem_ids) or len(problem_ids) != len(set(problem_ids)):
        raise ReducedCalibrationScoringError("reduced calibration scoring problem IDs are invalid")
    if manifest.get("problem_order_sha256") != stable_json_hash(problem_ids):
        raise ReducedCalibrationScoringError("reduced calibration scoring problem order SHA256 mismatch")
    if any(record.get("infrastructure_failure_count") != 0 for record in records):
        raise ReducedCalibrationScoringError("completed reduced calibration scoring contains infrastructure failure")
    expected_retry = sorted(
        cast(str, record["problem_id"])
        for record in records
        if manifest.get("block_index") == 0
        and record.get("public_all_test_zero") is True
        and record.get("hidden_all_test_zero") is True
    )
    retry_ids = [record.get("problem_id") for record in retry_records]
    if retry_ids != expected_retry or len(retry_ids) != len(set(cast(list[str], retry_ids))):
        raise ReducedCalibrationScoringError(
            "reduced calibration retry manifest is not the exact sorted both-zero set"
        )
    if manifest.get("retry_problem_count") != len(retry_ids):
        raise ReducedCalibrationScoringError("reduced calibration retry problem count mismatch")
    return manifest
