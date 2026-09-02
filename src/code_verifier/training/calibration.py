"""WP9 offline calibration, dual-verifier scoring, and fixed active-pool artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import statistics
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import cast

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.leakage_checks import TrainingArtifactKind, load_training_artifact
from code_verifier.data.refresh import check_refresh_data
from code_verifier.evaluation.generate import GenerationResult, GroupSamplingGenerator
from code_verifier.execution.base import CodeExecutor
from code_verifier.rewards.common import RewardContractError, compute_code_rewards_concurrent
from code_verifier.training.grpo_data import build_grpo_row
from code_verifier.training.sft import SFTCheckpointIdentity, load_completed_sft_checkpoint

CALIBRATION_SCHEMA_VERSION = "wp9b-calibration-v1"
CALIBRATION_TEST_SCHEMA_VERSION = "wp9b-calibration-test-v1"
_INPUT_FIELDS = {
    "problem_id",
    "prompt",
    "function_name",
    "source_name",
    "difficulty",
    "overlap_origin",
    "quality_gate_required",
}


class CalibrationError(RuntimeError):
    """Raised when a calibration artifact or invariant fails closed."""


class CalibrationClass(str, Enum):
    """Frozen Public/Hidden test-reward informativeness class."""

    DUAL_INFORMATIVE = "dual_informative"
    PUBLIC_ONLY = "public_only"
    HIDDEN_ONLY = "hidden_only"
    DUAL_UNINFORMATIVE = "dual_uninformative"


@dataclass(frozen=True)
class CalibrationConfig:
    """Validated WP9 offline-calibration and fixed-pool protocol."""

    initial_generations: int
    retry_generations: int
    temperature: float
    top_p: float
    max_new_tokens: int
    active_pool_size: int
    sft_overlap_fraction: float
    sft_overlap_hard_max: float
    dual_informative_min_fraction: float
    public_only_max_fraction: float
    hidden_only_max_fraction: float

    def __post_init__(self) -> None:
        for name in ("initial_generations", "retry_generations"):
            if getattr(self, name) != 8:
                raise CalibrationError(f"{name} must equal 8")
        if self.temperature != 0.8 or self.top_p != 0.95 or self.max_new_tokens != 512:
            raise CalibrationError("calibration sampling must equal 0.8/0.95/512")
        if isinstance(self.active_pool_size, bool) or not isinstance(self.active_pool_size, int):
            raise CalibrationError("active_pool_size must be a positive integer")
        if self.active_pool_size <= 0:
            raise CalibrationError("active_pool_size must be a positive integer")
        fractions = {
            "sft_overlap_fraction": self.sft_overlap_fraction,
            "sft_overlap_hard_max": self.sft_overlap_hard_max,
            "dual_informative_min_fraction": self.dual_informative_min_fraction,
            "public_only_max_fraction": self.public_only_max_fraction,
            "hidden_only_max_fraction": self.hidden_only_max_fraction,
        }
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
            for value in fractions.values()
        ):
            raise CalibrationError("calibration fractions must be finite values in [0, 1]")
        if self.sft_overlap_fraction > self.sft_overlap_hard_max or self.sft_overlap_hard_max > 0.15:
            raise CalibrationError("SFT overlap exceeds the frozen 15% hard maximum")
        if self.dual_informative_min_fraction < 0.70:
            raise CalibrationError("dual informative minimum cannot be below 70%")
        if self.public_only_max_fraction > 0.15 or self.hidden_only_max_fraction > 0.15:
            raise CalibrationError("single-arm informative caps cannot exceed 15%")


@dataclass(frozen=True)
class CalibrationInputRecord:
    problem_id: str
    prompt: str
    function_name: str
    source_name: str
    difficulty: str
    overlap_origin: str
    quality_gate_required: bool


@dataclass(frozen=True)
class CalibrationGenerationRecord:
    problem_id: str
    block_index: int
    sample_index: int
    sample_seed: int
    completion: str
    completion_tokens: int
    generation_latency_ms: float
    hit_max_new_tokens: bool


@dataclass(frozen=True)
class CalibrationGenerationSummary:
    run_dir: Path
    records_path: Path
    record_count: int
    problem_count: int
    records_sha256: str
    block_index: int


@dataclass(frozen=True)
class CalibrationPoolSummary:
    pool_dir: Path
    selected_problems: int
    dual_informative: int
    public_only: int
    hidden_only: int
    sft_overlap_count: int
    active_order_sha256: str
    calibration_manifest: Path
    public_grpo_jsonl: Path
    hidden_grpo_jsonl: Path


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise CalibrationError(f"could not read calibration artifact {path.name}") from error


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    indent = 2 if pretty else None
    separators = None if pretty else (",", ":")
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError):
        raise CalibrationError("calibration artifact must be finite and JSON serializable") from None
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


def _write_json(path: Path, value: object) -> None:
    _atomic_bytes(path, _json_bytes(value, pretty=True))


def _write_jsonl(path: Path, records: Sequence[Mapping[str, object]]) -> str:
    content = b"".join(_json_bytes(dict(record)) for record in records)
    _atomic_bytes(path, content)
    return hashlib.sha256(content).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise CalibrationError(f"could not load calibration artifact {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CalibrationError(f"calibration artifact {path.name} must contain an object")
    return cast(dict[str, object], value)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeError) as error:
        raise CalibrationError(f"could not load calibration artifact {path.name}") from error
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise CalibrationError(f"{path.name} line {line_number} is invalid") from error
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise CalibrationError(f"{path.name} line {line_number} must contain an object")
        records.append(cast(dict[str, object], value))
    return records


def load_calibration_config(path: Path) -> CalibrationConfig:
    """Load the exact tracked WP9-b calibration configuration."""
    root = load_yaml_mapping(path)
    expected = {"version", "sampling", "active_pool"}
    if set(root) != expected or root.get("version") != CALIBRATION_SCHEMA_VERSION:
        raise ConfigError("refresh calibration config fields/version are invalid")
    sampling = root.get("sampling")
    pool = root.get("active_pool")
    if not isinstance(sampling, Mapping) or set(sampling) != {
        "initial_generations",
        "retry_generations",
        "temperature",
        "top_p",
        "max_new_tokens",
    }:
        raise ConfigError("refresh calibration sampling config is invalid")
    if not isinstance(pool, Mapping) or set(pool) != {
        "size",
        "sft_overlap_fraction",
        "sft_overlap_hard_max",
        "dual_informative_min_fraction",
        "public_only_max_fraction",
        "hidden_only_max_fraction",
    }:
        raise ConfigError("refresh calibration active-pool config is invalid")
    try:
        return CalibrationConfig(
            initial_generations=cast(int, sampling["initial_generations"]),
            retry_generations=cast(int, sampling["retry_generations"]),
            temperature=cast(float, sampling["temperature"]),
            top_p=cast(float, sampling["top_p"]),
            max_new_tokens=cast(int, sampling["max_new_tokens"]),
            active_pool_size=cast(int, pool["size"]),
            sft_overlap_fraction=cast(float, pool["sft_overlap_fraction"]),
            sft_overlap_hard_max=cast(float, pool["sft_overlap_hard_max"]),
            dual_informative_min_fraction=cast(float, pool["dual_informative_min_fraction"]),
            public_only_max_fraction=cast(float, pool["public_only_max_fraction"]),
            hidden_only_max_fraction=cast(float, pool["hidden_only_max_fraction"]),
        )
    except CalibrationError as error:
        raise ConfigError(str(error)) from error


def calibration_problem_seed(base_seed: int, problem_id: str, block_index: int) -> int:
    """Derive a stable per-problem/per-block Transformers seed."""
    if isinstance(base_seed, bool) or not isinstance(base_seed, int):
        raise CalibrationError("base_seed must be an integer")
    if not isinstance(problem_id, str) or not problem_id:
        raise CalibrationError("problem_id must be a non-empty string")
    if block_index not in {0, 1}:
        raise CalibrationError("block_index must be 0 or 1")
    digest = hashlib.sha256(f"wp9b-calibration-v1|{base_seed}|{problem_id}|{block_index}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def _selection_records(dataset_dir: Path) -> list[dict[str, object]]:
    records = _load_jsonl(dataset_dir / "manifest" / "selection.jsonl")
    required = {"problem_id", "source", "difficulty", "overlap_origin", "quality_gate_required"}
    if any(not required.issubset(record) for record in records):
        raise CalibrationError("WP9-a selection records are missing calibration fields")
    return records


def prepare_calibration_input_bundle(
    *,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
    output_dir: Path,
    seed: int,
    allow_test_protocol: bool = False,
) -> Path:
    """Create a deterministic Public-safe calibration prompt bundle from strict WP9-a artifacts."""
    summary = check_refresh_data(
        refresh_dataset_dir,
        reference_dataset_dir=reference_dataset_dir,
        allow_test_protocol=allow_test_protocol,
    )
    public_rows = load_training_artifact(summary.public_grpo_jsonl, kind=TrainingArtifactKind.PUBLIC_GRPO)
    selections = _selection_records(refresh_dataset_dir)
    if len(public_rows) != len(selections):
        raise CalibrationError("WP9-a public view and selection manifest are not aligned")
    if not allow_test_protocol and len(public_rows) != 10_000:
        raise CalibrationError("production calibration input must contain exactly 10,000 problems")
    input_records: list[dict[str, object]] = []
    for public, selection in zip(public_rows, selections, strict=True):
        row = build_grpo_row(public, reward_mode="public")
        prompt_messages = row["prompt"]
        if not isinstance(prompt_messages, list) or len(prompt_messages) != 1:
            raise CalibrationError("GRPO prompt projection is invalid")
        prompt_message = prompt_messages[0]
        if not isinstance(prompt_message, Mapping) or not isinstance(prompt_message.get("content"), str):
            raise CalibrationError("GRPO prompt projection is invalid")
        metadata = public.get("metadata")
        difficulty = metadata.get("difficulty") if isinstance(metadata, Mapping) else None
        if not isinstance(difficulty, str):
            raise CalibrationError("WP9-a difficulty metadata is invalid")
        problem_id = public.get("problem_id")
        if problem_id != selection.get("problem_id") or not isinstance(problem_id, str):
            raise CalibrationError("WP9-a public view and selection IDs/order differ")
        input_records.append(
            {
                "problem_id": problem_id,
                "prompt": prompt_message["content"],
                "function_name": public["function_name"],
                "source_name": selection["source"],
                "difficulty": difficulty,
                "overlap_origin": selection["overlap_origin"],
                "quality_gate_required": selection["quality_gate_required"],
            }
        )
    if output_dir.exists():
        raise CalibrationError("calibration input output directory must not already exist")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records_sha = _write_jsonl(temporary / "inputs.jsonl", input_records)
        source_manifest_sha = _sha256(summary.root_manifest)
        source_manifest = _load_json(summary.root_manifest)
        manifest = {
            "schema_version": CALIBRATION_TEST_SCHEMA_VERSION if allow_test_protocol else CALIBRATION_SCHEMA_VERSION,
            "seed": seed,
            "record_count": len(input_records),
            "records_sha256": records_sha,
            "problem_order_sha256": stable_json_hash([record["problem_id"] for record in input_records]),
            "wp9a_schema_version": source_manifest.get("schema_version"),
            "wp9a_manifest_sha256": source_manifest_sha,
            "wp9a_selected_order_sha256": source_manifest.get("selected_ids_order_sha256"),
            "wp9a_public_training_sha256": _sha256(summary.public_grpo_jsonl),
            "wp9a_hidden_training_sha256": _sha256(summary.hidden_grpo_jsonl),
            "evidence_class": "engineering" if allow_test_protocol else "formal_input",
        }
        _write_json(temporary / "input_manifest.json", manifest)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_dir


def _load_input_bundle(input_bundle_dir: Path) -> tuple[dict[str, object], list[CalibrationInputRecord]]:
    manifest = _load_json(input_bundle_dir / "input_manifest.json")
    if manifest.get("schema_version") not in {CALIBRATION_SCHEMA_VERSION, CALIBRATION_TEST_SCHEMA_VERSION}:
        raise CalibrationError("calibration input schema is invalid")
    raw = _load_jsonl(input_bundle_dir / "inputs.jsonl")
    if manifest.get("records_sha256") != _sha256(input_bundle_dir / "inputs.jsonl"):
        raise CalibrationError("calibration input records hash mismatch")
    if manifest.get("record_count") != len(raw):
        raise CalibrationError("calibration input record count mismatch")
    if any(set(record) != _INPUT_FIELDS for record in raw):
        raise CalibrationError("calibration input record fields are invalid")
    forbidden = ("train_hidden_tests", "eval_hidden_tests", "reference_solution", "starter_code", "sft_response")
    serialized = (input_bundle_dir / "inputs.jsonl").read_text(encoding="utf-8")
    if any(field in serialized for field in forbidden):
        raise CalibrationError("calibration input contains a forbidden hidden/reference field")
    records: list[CalibrationInputRecord] = []
    for record in raw:
        string_fields = ("problem_id", "prompt", "function_name", "source_name", "difficulty", "overlap_origin")
        if any(not isinstance(record[field], str) or not record[field] for field in string_fields) or not isinstance(
            record["quality_gate_required"], bool
        ):
            raise CalibrationError("calibration input record types are invalid")
        item = CalibrationInputRecord(
            problem_id=cast(str, record["problem_id"]),
            prompt=cast(str, record["prompt"]),
            function_name=cast(str, record["function_name"]),
            source_name=cast(str, record["source_name"]),
            difficulty=cast(str, record["difficulty"]),
            overlap_origin=cast(str, record["overlap_origin"]),
            quality_gate_required=record["quality_gate_required"],
        )
        records.append(item)
    ids = [record.problem_id for record in records]
    if len(ids) != len(set(ids)) or manifest.get("problem_order_sha256") != stable_json_hash(ids):
        raise CalibrationError("calibration input problem order is invalid")
    return manifest, records


def _sft_identity(identity: SFTCheckpointIdentity) -> dict[str, object]:
    return {
        "run_id": identity.run_id,
        "model_id": identity.model_id,
        "model_revision": identity.model_revision,
        "dataset_hash": identity.dataset_hash,
        "config_hash": identity.config_hash,
        "dependency_lock_hash": identity.dependency_lock_hash,
        "seed": identity.seed,
        "checkpoint_sha256": stable_json_hash(
            {
                "run_id": identity.run_id,
                "model_id": identity.model_id,
                "model_revision": identity.model_revision,
                "dataset_hash": identity.dataset_hash,
                "config_hash": identity.config_hash,
                "dependency_lock_hash": identity.dependency_lock_hash,
                "seed": identity.seed,
            }
        ),
    }


def run_calibration_generation(
    *,
    input_bundle_dir: Path,
    sft_run_dir: Path,
    generator: GroupSamplingGenerator,
    output_dir: Path,
    block_index: int,
    retry_manifest: Path | None = None,
) -> CalibrationGenerationSummary:
    """Generate or exact-prefix resume one initial/retry k=8 sampled-B bundle."""
    input_manifest, input_records = _load_input_bundle(input_bundle_dir)
    try:
        sft = load_completed_sft_checkpoint(sft_run_dir)
    except Exception as error:
        raise CalibrationError(f"completed B identity is invalid: {type(error).__name__}") from None
    if block_index not in {0, 1}:
        raise CalibrationError("block_index must be 0 or 1")
    if block_index == 0 and retry_manifest is not None:
        raise CalibrationError("initial generation cannot consume a retry manifest")
    if block_index == 1 and retry_manifest is None:
        raise CalibrationError("retry generation requires an immutable retry manifest")
    selected = input_records
    retry_sha: str | None = None
    if retry_manifest is not None:
        retry_rows = _load_jsonl(retry_manifest)
        if any(set(row) != {"problem_id"} or not isinstance(row.get("problem_id"), str) for row in retry_rows):
            raise CalibrationError("retry manifest fields are invalid")
        retry_ids = [cast(str, row["problem_id"]) for row in retry_rows]
        if retry_ids != sorted(retry_ids) or len(retry_ids) != len(set(retry_ids)):
            raise CalibrationError("retry manifest IDs must be unique and sorted")
        by_id = {record.problem_id: record for record in input_records}
        if any(problem_id not in by_id for problem_id in retry_ids):
            raise CalibrationError("retry manifest contains an unknown problem ID")
        selected = [by_id[problem_id] for problem_id in retry_ids]
        retry_sha = _sha256(retry_manifest)
    identity = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "status": "running",
        "block_index": block_index,
        "samples_per_problem": 8,
        "input_manifest_sha256": _sha256(input_bundle_dir / "input_manifest.json"),
        "input_records_sha256": input_manifest["records_sha256"],
        "problem_order_sha256": stable_json_hash([record.problem_id for record in selected]),
        "retry_manifest_sha256": retry_sha,
        "sft_checkpoint": _sft_identity(sft),
    }
    records_path = output_dir / "samples" / "generations.jsonl"
    existing: list[dict[str, object]] = []
    if output_dir.exists():
        existing_manifest = _load_json(output_dir / "run.json")
        comparable = dict(existing_manifest)
        comparable.pop("status", None)
        comparable.pop("record_count", None)
        comparable.pop("records_sha256", None)
        expected = dict(identity)
        expected.pop("status")
        if comparable != expected:
            raise CalibrationError("calibration generation resume identity mismatch")
        existing = _load_jsonl(records_path)
    else:
        output_dir.mkdir(parents=True)
        _write_json(output_dir / "run.json", identity)
    expected_keys = [
        (record.problem_id, block_index * 8 + sample_offset) for record in selected for sample_offset in range(8)
    ]
    if len(existing) > len(expected_keys):
        raise CalibrationError("calibration generation resume has too many records")
    for index, row in enumerate(existing):
        if (row.get("problem_id"), row.get("sample_index")) != expected_keys[index]:
            raise CalibrationError("calibration generation resume is not an exact prefix")
    completed_problem_count = len(existing) // 8
    if len(existing) % 8:
        raise CalibrationError("calibration generation resume ends inside a problem group")
    records = list(existing)
    base_seed = input_manifest.get("seed")
    if isinstance(base_seed, bool) or not isinstance(base_seed, int):
        raise CalibrationError("calibration input seed is invalid")
    for item in selected[completed_problem_count:]:
        group_seed = calibration_problem_seed(base_seed, item.problem_id, block_index)
        generated = generator.generate_group(item.prompt, seed=group_seed, num_generations=8)
        if len(generated) != 8 or any(not isinstance(result, GenerationResult) for result in generated):
            raise CalibrationError("calibration generator must return exactly eight GenerationResult values")
        group_records = [
            {
                "problem_id": item.problem_id,
                "block_index": block_index,
                "sample_index": block_index * 8 + offset,
                "sample_seed": calibration_problem_seed(base_seed, item.problem_id, block_index),
                "completion": result.completion,
                "completion_tokens": result.completion_tokens,
                "generation_latency_ms": result.latency_ms,
                "hit_max_new_tokens": result.hit_max_new_tokens,
            }
            for offset, result in enumerate(generated)
        ]
        records.extend(group_records)
        _write_jsonl(records_path, records)
    records_sha = _sha256(records_path)
    final = {
        **identity,
        "status": "completed",
        "record_count": len(records),
        "records_sha256": records_sha,
    }
    _write_json(output_dir / "run.json", final)
    return CalibrationGenerationSummary(
        run_dir=output_dir,
        records_path=records_path,
        record_count=len(records),
        problem_count=len(selected),
        records_sha256=records_sha,
        block_index=block_index,
    )


def load_completed_calibration_generation(run_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Strictly load one completed sampled-generation bundle."""
    manifest = _load_json(run_dir / "run.json")
    if manifest.get("schema_version") != CALIBRATION_SCHEMA_VERSION or manifest.get("status") != "completed":
        raise CalibrationError("calibration generation is not completed")
    records = _load_jsonl(run_dir / "samples" / "generations.jsonl")
    if manifest.get("records_sha256") != _sha256(run_dir / "samples" / "generations.jsonl"):
        raise CalibrationError("calibration generation records hash mismatch")
    if manifest.get("record_count") != len(records):
        raise CalibrationError("calibration generation record count mismatch")
    block = manifest.get("block_index")
    if block not in {0, 1} or len(records) % 8:
        raise CalibrationError("calibration generation block shape is invalid")
    expected_fields = {
        "problem_id",
        "block_index",
        "sample_index",
        "sample_seed",
        "completion",
        "completion_tokens",
        "generation_latency_ms",
        "hit_max_new_tokens",
    }
    if any(set(row) != expected_fields or row.get("block_index") != block for row in records):
        raise CalibrationError("calibration generation record fields are invalid")
    return manifest, records


def _population_stats(values: Sequence[float]) -> tuple[float, float]:
    if not values or any(not math.isfinite(value) for value in values):
        raise CalibrationError("calibration rewards must be non-empty and finite")
    return statistics.fmean(values), statistics.pstdev(values)


def _classification(public_std: float, hidden_std: float) -> CalibrationClass:
    public = public_std > 0.0
    hidden = hidden_std > 0.0
    if public and hidden:
        return CalibrationClass.DUAL_INFORMATIVE
    if public:
        return CalibrationClass.PUBLIC_ONLY
    if hidden:
        return CalibrationClass.HIDDEN_ONLY
    return CalibrationClass.DUAL_UNINFORMATIVE


def _score_record(
    *,
    input_record: CalibrationInputRecord,
    generation_rows: Sequence[Mapping[str, object]],
    public_components: Sequence[Mapping[str, object]],
    hidden_components: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    public_test = [float(cast(float, item["test_reward"])) for item in public_components]
    hidden_test = [float(cast(float, item["test_reward"])) for item in hidden_components]
    public_total = [float(cast(float, item["total_reward"])) for item in public_components]
    hidden_total = [float(cast(float, item["total_reward"])) for item in hidden_components]
    public_test_mean, public_test_std = _population_stats(public_test)
    hidden_test_mean, hidden_test_std = _population_stats(hidden_test)
    public_total_mean, public_total_std = _population_stats(public_total)
    hidden_total_mean, hidden_total_std = _population_stats(hidden_total)
    return {
        "problem_id": input_record.problem_id,
        "source_name": input_record.source_name,
        "difficulty": input_record.difficulty,
        "overlap_origin": input_record.overlap_origin,
        "quality_gate_required": input_record.quality_gate_required,
        "sample_indices": [row["sample_index"] for row in generation_rows],
        "completion_sha256": [
            hashlib.sha256(cast(str, row["completion"]).encode()).hexdigest() for row in generation_rows
        ],
        "public_test_rewards": public_test,
        "hidden_test_rewards": hidden_test,
        "public_total_rewards": public_total,
        "hidden_total_rewards": hidden_total,
        "public_test_reward_mean": public_test_mean,
        "public_test_reward_std": public_test_std,
        "hidden_test_reward_mean": hidden_test_mean,
        "hidden_test_reward_std": hidden_test_std,
        "public_total_reward_mean": public_total_mean,
        "public_total_reward_std": public_total_std,
        "hidden_total_reward_mean": hidden_total_mean,
        "hidden_total_reward_std": hidden_total_std,
        "public_informative": public_test_std > 0.0,
        "hidden_informative": hidden_test_std > 0.0,
        "calibration_class": _classification(public_test_std, hidden_test_std).value,
        "public_all_test_correct": all(value == 1.0 for value in public_test),
        "hidden_all_test_correct": all(value == 1.0 for value in hidden_test),
        "public_all_test_zero": all(value == 0.0 for value in public_test),
        "hidden_all_test_zero": all(value == 0.0 for value in hidden_test),
        "public_full_pass_count": sum(value == 1.0 for value in public_test),
        "hidden_full_pass_count": sum(value == 1.0 for value in hidden_test),
        "parse_failure_count": sum(not bool(item["parsed"]) for item in public_components),
        "execution_failure_count": sum(not bool(item["executed"]) for item in public_components),
        "timeout_count": sum(item["status"] == "timeout" for item in public_components),
        "infrastructure_failure_count": sum(
            bool(item["infrastructure_failure"]) for item in (*public_components, *hidden_components)
        ),
        "completion_token_mean": statistics.fmean(
            float(cast(int, row["completion_tokens"])) for row in generation_rows
        ),
        "completion_token_max": max(cast(int, row["completion_tokens"]) for row in generation_rows),
        "truncation_count": sum(bool(row["hit_max_new_tokens"]) for row in generation_rows),
    }


def score_calibration_generation(
    *,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
    input_bundle_dir: Path,
    generation_run_dir: Path,
    output_dir: Path,
    executor_factory: Callable[[], CodeExecutor],
    workers: int,
    allow_test_protocol: bool = False,
) -> Path:
    """Score identical sampled completions with Public and Hidden verifiers concurrently."""
    summary = check_refresh_data(
        refresh_dataset_dir,
        reference_dataset_dir=reference_dataset_dir,
        allow_test_protocol=allow_test_protocol,
    )
    input_manifest, inputs = _load_input_bundle(input_bundle_dir)
    generation_manifest, generations = load_completed_calibration_generation(generation_run_dir)
    if generation_manifest.get("input_manifest_sha256") != _sha256(input_bundle_dir / "input_manifest.json"):
        raise CalibrationError("generation bundle is not bound to the selected input bundle")
    public_rows = load_training_artifact(summary.public_grpo_jsonl, kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden_rows = load_training_artifact(summary.hidden_grpo_jsonl, kind=TrainingArtifactKind.HIDDEN_GRPO)
    public_by_id = {cast(str, row["problem_id"]): row for row in public_rows}
    hidden_by_id = {cast(str, row["problem_id"]): row for row in hidden_rows}
    input_by_id = {row.problem_id: row for row in inputs}
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in generations:
        problem_id = row.get("problem_id")
        if not isinstance(problem_id, str) or problem_id not in input_by_id:
            raise CalibrationError("generation bundle contains an unknown problem ID")
        grouped.setdefault(problem_id, []).append(row)
    score_records: list[dict[str, object]] = []
    for problem_id, generation_rows in grouped.items():
        if problem_id not in public_by_id or problem_id not in hidden_by_id or len(generation_rows) != 8:
            raise CalibrationError("generation and WP9-a training views are not aligned")
        public = public_by_id[problem_id]
        hidden = hidden_by_id[problem_id]
        completions = [row["completion"] for row in generation_rows]
        metadata_batch = [public["metadata"]] * len(completions)
        functions = [public["function_name"]] * len(completions)
        try:
            _, public_components = compute_code_rewards_concurrent(
                completions,
                [public["visible_tests"]] * len(completions),
                functions,
                metadata_batch,
                executor_factory=executor_factory,
                mode="public",
                max_concurrency=workers,
            )
            _, hidden_components = compute_code_rewards_concurrent(
                completions,
                [hidden["train_hidden_tests"]] * len(completions),
                functions,
                metadata_batch,
                executor_factory=executor_factory,
                mode="hidden",
                max_concurrency=workers,
            )
        except RewardContractError as error:
            raise CalibrationError(f"calibration scoring failed: {error}") from error
        if any(bool(item["infrastructure_failure"]) for item in (*public_components, *hidden_components)):
            raise CalibrationError("calibration scoring encountered an infrastructure failure")
        score_records.append(
            _score_record(
                input_record=input_by_id[problem_id],
                generation_rows=generation_rows,
                public_components=public_components,
                hidden_components=hidden_components,
            )
        )
    retry_ids = sorted(
        cast(str, record["problem_id"])
        for record in score_records
        if generation_manifest["block_index"] == 0
        and record["public_all_test_zero"] is True
        and record["hidden_all_test_zero"] is True
    )
    if output_dir.exists():
        raise CalibrationError("calibration scoring output directory must not already exist")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records_sha = _write_jsonl(temporary / "records" / "scoring.jsonl", score_records)
        retry_sha = _write_jsonl(
            temporary / "manifest" / "retry_problem_ids.jsonl",
            [{"problem_id": problem_id} for problem_id in retry_ids],
        )
        manifest = {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "status": "completed",
            "block_index": generation_manifest["block_index"],
            "workers": workers,
            "problem_count": len(score_records),
            "records_sha256": records_sha,
            "retry_problem_ids_sha256": retry_sha,
            "generation_run_manifest_sha256": _sha256(generation_run_dir / "run.json"),
            "generation_records_sha256": generation_manifest["records_sha256"],
            "input_manifest_sha256": _sha256(input_bundle_dir / "input_manifest.json"),
            "wp9a_manifest_sha256": input_manifest["wp9a_manifest_sha256"],
            "wp9a_public_training_sha256": _sha256(summary.public_grpo_jsonl),
            "wp9a_hidden_training_sha256": _sha256(summary.hidden_grpo_jsonl),
            "sft_checkpoint": generation_manifest["sft_checkpoint"],
        }
        _write_json(temporary / "score_manifest.json", manifest)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_dir


def _load_scores(score_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = _load_json(score_dir / "score_manifest.json")
    if manifest.get("schema_version") != CALIBRATION_SCHEMA_VERSION or manifest.get("status") != "completed":
        raise CalibrationError("calibration scoring run is not completed")
    records = _load_jsonl(score_dir / "records" / "scoring.jsonl")
    if manifest.get("records_sha256") != _sha256(score_dir / "records" / "scoring.jsonl"):
        raise CalibrationError("calibration scoring records hash mismatch")
    retry_path = score_dir / "manifest" / "retry_problem_ids.jsonl"
    if manifest.get("retry_problem_ids_sha256") != _sha256(retry_path):
        raise CalibrationError("calibration retry manifest hash mismatch")
    return manifest, records


def _merge_score_records(initial: Mapping[str, object], retry: Mapping[str, object] | None) -> dict[str, object]:
    if retry is None:
        return dict(initial)
    result = dict(initial)
    for prefix in ("public_test", "hidden_test", "public_total", "hidden_total"):
        field = f"{prefix}_rewards"
        left = initial.get(field)
        right = retry.get(field)
        if not isinstance(left, list) or not isinstance(right, list):
            raise CalibrationError("calibration score reward arrays are invalid")
        values = [float(value) for value in (*left, *right)]
        result[field] = values
        mean, std = _population_stats(values)
        result[f"{prefix}_reward_mean"] = mean
        result[f"{prefix}_reward_std"] = std
    public = cast(list[float], result["public_test_rewards"])
    hidden = cast(list[float], result["hidden_test_rewards"])
    public_std = cast(float, result["public_test_reward_std"])
    hidden_std = cast(float, result["hidden_test_reward_std"])
    result["sample_indices"] = [
        *cast(list[object], initial["sample_indices"]),
        *cast(list[object], retry["sample_indices"]),
    ]
    result["completion_sha256"] = [
        *cast(list[object], initial["completion_sha256"]),
        *cast(list[object], retry["completion_sha256"]),
    ]
    result["public_informative"] = public_std > 0.0
    result["hidden_informative"] = hidden_std > 0.0
    result["calibration_class"] = _classification(public_std, hidden_std).value
    result["public_all_test_correct"] = all(value == 1.0 for value in public)
    result["hidden_all_test_correct"] = all(value == 1.0 for value in hidden)
    result["public_all_test_zero"] = all(value == 0.0 for value in public)
    result["hidden_all_test_zero"] = all(value == 0.0 for value in hidden)
    result["public_full_pass_count"] = sum(value == 1.0 for value in public)
    result["hidden_full_pass_count"] = sum(value == 1.0 for value in hidden)
    for field in (
        "parse_failure_count",
        "execution_failure_count",
        "timeout_count",
        "infrastructure_failure_count",
        "truncation_count",
    ):
        result[field] = cast(int, initial[field]) + cast(int, retry[field])
    result["completion_token_max"] = max(
        cast(int, initial["completion_token_max"]), cast(int, retry["completion_token_max"])
    )
    result["completion_token_mean"] = statistics.fmean(
        (cast(float, initial["completion_token_mean"]), cast(float, retry["completion_token_mean"]))
    )
    return result


def _selection_hash(seed: int, problem_id: str) -> str:
    return hashlib.sha256(f"wp9b-active-pool-v1|{seed}|{problem_id}".encode()).hexdigest()


def build_calibrated_active_pool(
    *,
    config: CalibrationConfig,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
    input_bundle_dir: Path,
    initial_scoring_dir: Path,
    retry_scoring_dir: Path | None,
    output_dir: Path,
    seed: int,
    allow_test_protocol: bool = False,
) -> CalibrationPoolSummary:
    """Merge 8+8 calibration results and freeze one shared constrained Public/Hidden pool."""
    refresh = check_refresh_data(
        refresh_dataset_dir,
        reference_dataset_dir=reference_dataset_dir,
        allow_test_protocol=allow_test_protocol,
    )
    input_manifest, _ = _load_input_bundle(input_bundle_dir)
    initial_manifest, initial_records = _load_scores(initial_scoring_dir)
    if initial_manifest.get("block_index") != 0:
        raise CalibrationError("initial scoring directory must contain block 0")
    expected_retry_ids = [
        cast(str, row["problem_id"])
        for row in _load_jsonl(initial_scoring_dir / "manifest" / "retry_problem_ids.jsonl")
    ]
    retry_by_id: dict[str, dict[str, object]] = {}
    retry_manifest: dict[str, object] | None = None
    if expected_retry_ids:
        if retry_scoring_dir is None:
            raise CalibrationError("both-zero initial problems require retry scoring")
        retry_manifest, retry_records = _load_scores(retry_scoring_dir)
        if retry_manifest.get("block_index") != 1:
            raise CalibrationError("retry scoring directory must contain block 1")
        retry_ids = [cast(str, record["problem_id"]) for record in retry_records]
        if retry_ids != expected_retry_ids:
            raise CalibrationError("retry scoring IDs/order do not match the initial retry manifest")
        retry_by_id = {cast(str, record["problem_id"]): record for record in retry_records}
    elif retry_scoring_dir is not None:
        raise CalibrationError("retry scoring was supplied without any eligible retry problems")
    final_records = [
        _merge_score_records(record, retry_by_id.get(cast(str, record["problem_id"]))) for record in initial_records
    ]
    eligible: list[dict[str, object]] = []
    reserve: list[dict[str, object]] = []
    hard: list[dict[str, object]] = []
    easy: list[dict[str, object]] = []
    for record in final_records:
        problem_id = cast(str, record["problem_id"])
        record["calibration_record_sha256"] = stable_json_hash(record)
        if record["quality_gate_required"] is True:
            reserve.append({"problem_id": problem_id, "reason": "quality_gate_required"})
        elif record["public_all_test_correct"] is True and record["hidden_all_test_correct"] is True:
            easy.append({"problem_id": problem_id, "reason": "dual_saturated"})
        elif problem_id in retry_by_id and record["calibration_class"] == CalibrationClass.DUAL_UNINFORMATIVE.value:
            hard.append({"problem_id": problem_id, "reason": "dual_uninformative_after_16"})
        elif record["calibration_class"] == CalibrationClass.DUAL_UNINFORMATIVE.value:
            reserve.append({"problem_id": problem_id, "reason": "dual_uninformative"})
        else:
            eligible.append(record)
    overlap_target = int(round(config.active_pool_size * config.sft_overlap_fraction))
    buckets = {
        "sft_reuse": [record for record in eligible if record["overlap_origin"] == "sft_reuse"],
        "external_new": [record for record in eligible if record["overlap_origin"] != "sft_reuse"],
    }
    quotas = {"sft_reuse": overlap_target, "external_new": config.active_pool_size - overlap_target}
    selected: list[dict[str, object]] = []
    for bucket_name in ("sft_reuse", "external_new"):
        population = buckets[bucket_name]
        class_rank = {
            CalibrationClass.DUAL_INFORMATIVE.value: 0,
            CalibrationClass.PUBLIC_ONLY.value: 1,
            CalibrationClass.HIDDEN_ONLY.value: 1,
        }
        population.sort(
            key=lambda record: (
                class_rank[cast(str, record["calibration_class"])],
                _selection_hash(seed, cast(str, record["problem_id"])),
            )
        )
        if len(population) < quotas[bucket_name]:
            raise CalibrationError(f"insufficient {bucket_name} calibrated population for frozen quota")
        selected.extend(population[: quotas[bucket_name]])
        reserve.extend(
            {"problem_id": cast(str, record["problem_id"]), "reason": "informative_not_selected"}
            for record in population[quotas[bucket_name] :]
        )
    counts = Counter(cast(str, record["calibration_class"]) for record in selected)
    if counts[CalibrationClass.DUAL_INFORMATIVE.value] < math.ceil(
        config.active_pool_size * config.dual_informative_min_fraction
    ):
        raise CalibrationError("selected pool cannot satisfy the dual-informative minimum")
    if counts[CalibrationClass.PUBLIC_ONLY.value] > math.floor(
        config.active_pool_size * config.public_only_max_fraction
    ) or counts[CalibrationClass.HIDDEN_ONLY.value] > math.floor(
        config.active_pool_size * config.hidden_only_max_fraction
    ):
        raise CalibrationError("selected pool cannot satisfy the single-arm informative caps")
    selected.sort(key=lambda record: _selection_hash(seed + 1, cast(str, record["problem_id"])))
    selected_ids = [cast(str, record["problem_id"]) for record in selected]
    active_order_sha = stable_json_hash(selected_ids)
    public_rows = load_training_artifact(refresh.public_grpo_jsonl, kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden_rows = load_training_artifact(refresh.hidden_grpo_jsonl, kind=TrainingArtifactKind.HIDDEN_GRPO)
    public_by_id = {cast(str, row["problem_id"]): row for row in public_rows}
    hidden_by_id = {cast(str, row["problem_id"]): row for row in hidden_rows}
    record_by_id = {cast(str, record["problem_id"]): record for record in selected}

    def training_rows(source: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for problem_id in selected_ids:
            row = dict(source[problem_id])
            metadata = row.get("metadata")
            if not isinstance(metadata, Mapping):
                raise CalibrationError("selected training metadata is invalid")
            calibrated = record_by_id[problem_id]
            row["metadata"] = {
                **dict(metadata),
                "calibration_class": calibrated["calibration_class"],
                "calibration_record_sha256": calibrated["calibration_record_sha256"],
                "overlap_origin": calibrated["overlap_origin"],
            }
            rows.append(row)
        return rows

    public_active = training_rows(public_by_id)
    hidden_active = training_rows(hidden_by_id)
    if output_dir.exists():
        raise CalibrationError("calibrated pool output directory must not already exist")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records_sha = _write_jsonl(temporary / "records" / "calibration.jsonl", final_records)
        retry_sha = _write_jsonl(
            temporary / "manifest" / "retry_problem_ids.jsonl",
            [{"problem_id": problem_id} for problem_id in expected_retry_ids],
        )
        selection_rows = [
            {
                "ordinal": ordinal,
                "problem_id": problem_id,
                "calibration_class": record_by_id[problem_id]["calibration_class"],
                "calibration_record_sha256": record_by_id[problem_id]["calibration_record_sha256"],
                "overlap_origin": record_by_id[problem_id]["overlap_origin"],
            }
            for ordinal, problem_id in enumerate(selected_ids)
        ]
        active_selection_sha = _write_jsonl(temporary / "manifest" / "active_selection.jsonl", selection_rows)
        problem_order_sha = _write_jsonl(
            temporary / "manifest" / "problem_order.jsonl",
            [{"ordinal": ordinal, "problem_id": problem_id} for ordinal, problem_id in enumerate(selected_ids)],
        )
        reserve_sha = _write_jsonl(
            temporary / "manifest" / "reserve_problem_ids.jsonl",
            sorted(reserve, key=lambda row: cast(str, row["problem_id"])),
        )
        hard_sha = _write_jsonl(temporary / "manifest" / "hard_problem_ids.jsonl", hard)
        easy_sha = _write_jsonl(temporary / "manifest" / "easy_problem_ids.jsonl", easy)
        public_sha = _write_jsonl(temporary / "training" / "public_grpo.jsonl", public_active)
        hidden_sha = _write_jsonl(temporary / "training" / "hidden_grpo.jsonl", hidden_active)
        class_counts = {item.value: counts[item.value] for item in CalibrationClass}
        composition = {
            "selected_problems": len(selected_ids),
            "class_counts": class_counts,
            "class_fractions": {key: value / len(selected_ids) for key, value in class_counts.items()},
            "sft_overlap_count": overlap_target,
            "sft_overlap_fraction": overlap_target / len(selected_ids),
            "quality_excluded_count": sum(record["quality_gate_required"] is True for record in final_records),
        }
        _write_json(
            temporary / "reports" / "classification_summary.json",
            dict(Counter(cast(str, record["calibration_class"]) for record in final_records)),
        )
        _write_json(temporary / "reports" / "pool_composition.json", composition)
        artifacts = {
            "records/calibration.jsonl": records_sha,
            "manifest/retry_problem_ids.jsonl": retry_sha,
            "manifest/active_selection.jsonl": active_selection_sha,
            "manifest/problem_order.jsonl": problem_order_sha,
            "manifest/reserve_problem_ids.jsonl": reserve_sha,
            "manifest/hard_problem_ids.jsonl": hard_sha,
            "manifest/easy_problem_ids.jsonl": easy_sha,
            "training/public_grpo.jsonl": public_sha,
            "training/hidden_grpo.jsonl": hidden_sha,
        }
        manifest = {
            "schema_version": CALIBRATION_TEST_SCHEMA_VERSION if allow_test_protocol else CALIBRATION_SCHEMA_VERSION,
            "status": "completed",
            "evidence_class": "engineering" if allow_test_protocol else "formal_calibration",
            "seed": seed,
            "config": asdict(config),
            "wp9a_manifest_sha256": input_manifest["wp9a_manifest_sha256"],
            "wp9a_selected_order_sha256": input_manifest["wp9a_selected_order_sha256"],
            "input_manifest_sha256": _sha256(input_bundle_dir / "input_manifest.json"),
            "initial_scoring_manifest_sha256": _sha256(initial_scoring_dir / "score_manifest.json"),
            "retry_scoring_manifest_sha256": (
                None if retry_scoring_dir is None else _sha256(retry_scoring_dir / "score_manifest.json")
            ),
            "sft_checkpoint": initial_manifest["sft_checkpoint"],
            "active_order_sha256": active_order_sha,
            "composition": composition,
            "artifacts": artifacts,
        }
        _write_json(temporary / "calibration_manifest.json", manifest)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return check_calibrated_active_pool(
        output_dir,
        refresh_dataset_dir=refresh_dataset_dir,
        reference_dataset_dir=reference_dataset_dir,
        allow_test_protocol=allow_test_protocol,
    )


def check_calibrated_active_pool(
    pool_dir: Path,
    *,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
    allow_test_protocol: bool = False,
) -> CalibrationPoolSummary:
    """Recompute core active-pool identity, pairing, class, overlap, and payload invariants."""
    refresh = check_refresh_data(
        refresh_dataset_dir,
        reference_dataset_dir=reference_dataset_dir,
        allow_test_protocol=allow_test_protocol,
    )
    manifest = _load_json(pool_dir / "calibration_manifest.json")
    expected_schema = CALIBRATION_TEST_SCHEMA_VERSION if allow_test_protocol else CALIBRATION_SCHEMA_VERSION
    if manifest.get("schema_version") != expected_schema or manifest.get("status") != "completed":
        raise CalibrationError("calibrated active-pool manifest is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise CalibrationError("calibrated active-pool artifact inventory is invalid")
    for relative, expected_sha in artifacts.items():
        if (
            not isinstance(relative, str)
            or not isinstance(expected_sha, str)
            or _sha256(pool_dir / relative) != expected_sha
        ):
            raise CalibrationError("calibrated active-pool artifact hash mismatch")
    order_rows = _load_jsonl(pool_dir / "manifest" / "problem_order.jsonl")
    selected_ids = [row.get("problem_id") for row in order_rows]
    if any(not isinstance(item, str) for item in selected_ids) or [row.get("ordinal") for row in order_rows] != list(
        range(len(order_rows))
    ):
        raise CalibrationError("calibrated active-pool order is invalid")
    public = load_training_artifact(pool_dir / "training" / "public_grpo.jsonl", kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden = load_training_artifact(pool_dir / "training" / "hidden_grpo.jsonl", kind=TrainingArtifactKind.HIDDEN_GRPO)
    public_ids = [row["problem_id"] for row in public]
    hidden_ids = [row["problem_id"] for row in hidden]
    if public_ids != selected_ids or hidden_ids != selected_ids:
        raise CalibrationError("active Public/Hidden training views have different IDs/order")
    source_public = {
        row["problem_id"]: row
        for row in load_training_artifact(refresh.public_grpo_jsonl, kind=TrainingArtifactKind.PUBLIC_GRPO)
    }
    source_hidden = {
        row["problem_id"]: row
        for row in load_training_artifact(refresh.hidden_grpo_jsonl, kind=TrainingArtifactKind.HIDDEN_GRPO)
    }
    for mode_rows, source in ((public, source_public), (hidden, source_hidden)):
        for row in mode_rows:
            source_row = source[row["problem_id"]]
            if row.get("prompt") != source_row.get("prompt") or row.get("function_name") != source_row.get(
                "function_name"
            ):
                raise CalibrationError("active training view changed the frozen problem/prompt identity")
    selection = _load_jsonl(pool_dir / "manifest" / "active_selection.jsonl")
    if [row.get("problem_id") for row in selection] != selected_ids:
        raise CalibrationError("active selection does not match active order")
    class_counts = Counter(cast(str, row["calibration_class"]) for row in selection)
    overlap_count = sum(row["overlap_origin"] == "sft_reuse" for row in selection)
    composition = manifest.get("composition")
    if not isinstance(composition, Mapping):
        raise CalibrationError("active pool composition is invalid")
    if (
        composition.get("selected_problems") != len(selected_ids)
        or composition.get("sft_overlap_count") != overlap_count
    ):
        raise CalibrationError("active pool composition does not match raw selection")
    if manifest.get("active_order_sha256") != stable_json_hash(selected_ids):
        raise CalibrationError("active pool order hash mismatch")
    return CalibrationPoolSummary(
        pool_dir=pool_dir,
        selected_problems=len(selected_ids),
        dual_informative=class_counts[CalibrationClass.DUAL_INFORMATIVE.value],
        public_only=class_counts[CalibrationClass.PUBLIC_ONLY.value],
        hidden_only=class_counts[CalibrationClass.HIDDEN_ONLY.value],
        sft_overlap_count=overlap_count,
        active_order_sha256=cast(str, manifest["active_order_sha256"]),
        calibration_manifest=pool_dir / "calibration_manifest.json",
        public_grpo_jsonl=pool_dir / "training" / "public_grpo.jsonl",
        hidden_grpo_jsonl=pool_dir / "training" / "hidden_grpo.jsonl",
    )
