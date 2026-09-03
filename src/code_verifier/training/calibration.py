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
from typing import TypeVar, cast

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.leakage_checks import TrainingArtifactKind, load_training_artifact
from code_verifier.data.refresh import check_refresh_data
from code_verifier.evaluation.generate import BatchedGroupSamplingGenerator, GenerationResult, GroupSamplingGenerator
from code_verifier.execution.base import CodeExecutor
from code_verifier.rewards.common import RewardContractError, compute_code_rewards_concurrent
from code_verifier.training.grpo_data import build_grpo_row
from code_verifier.training.sft import SFTCheckpointIdentity, load_completed_sft_checkpoint

CALIBRATION_SCHEMA_VERSION = "wp9b-calibration-v1"
CALIBRATION_TEST_SCHEMA_VERSION = "wp9b-calibration-test-v1"
_CALIBRATION_PROGRESS_VERSION = 1
_INPUT_FIELDS = {
    "problem_id",
    "prompt",
    "function_name",
    "source_name",
    "difficulty",
    "overlap_origin",
    "quality_gate_required",
}
_SelectionKey = TypeVar("_SelectionKey")


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


def _write_generation_progress(output_dir: Path, *, record_count: int, byte_count: int) -> None:
    if record_count < 0 or record_count % 8 or byte_count < 0:
        raise CalibrationError("calibration generation progress is invalid")
    _write_json(
        output_dir / "samples" / "progress.json",
        {
            "version": _CALIBRATION_PROGRESS_VERSION,
            "record_count": record_count,
            "byte_count": byte_count,
        },
    )


def _load_running_calibration_generation_prefix(output_dir: Path) -> tuple[list[dict[str, object]], int]:
    """Load the durable running prefix and discard only bytes newer than its atomic progress marker."""
    records_path = output_dir / "samples" / "generations.jsonl"
    progress_path = output_dir / "samples" / "progress.json"
    if not progress_path.exists():
        if records_path.exists():
            records = _load_jsonl(records_path)
            if len(records) % 8:
                raise CalibrationError("legacy calibration generation resume ends inside a problem group")
            byte_count = records_path.stat().st_size
            _write_generation_progress(output_dir, record_count=len(records), byte_count=byte_count)
            return records, byte_count
        _write_generation_progress(output_dir, record_count=0, byte_count=0)
        return [], 0
    progress = _load_json(progress_path)
    if set(progress) != {"version", "record_count", "byte_count"}:
        raise CalibrationError("calibration generation progress fields are invalid")
    if progress.get("version") != _CALIBRATION_PROGRESS_VERSION:
        raise CalibrationError("calibration generation progress version is invalid")
    progress_record_count = progress.get("record_count")
    progress_byte_count = progress.get("byte_count")
    if (
        isinstance(progress_record_count, bool)
        or not isinstance(progress_record_count, int)
        or progress_record_count < 0
        or progress_record_count % 8
        or isinstance(progress_byte_count, bool)
        or not isinstance(progress_byte_count, int)
        or progress_byte_count < 0
    ):
        raise CalibrationError("calibration generation progress values are invalid")
    if not records_path.exists():
        if progress_record_count != 0 or progress_byte_count != 0:
            raise CalibrationError("calibration generation progress points to missing committed data")
        return [], 0
    current_size = records_path.stat().st_size
    if current_size < progress_byte_count:
        raise CalibrationError("calibration generation committed data is shorter than its progress marker")
    if current_size > progress_byte_count:
        with records_path.open("r+b") as handle:
            handle.truncate(progress_byte_count)
            handle.flush()
            os.fsync(handle.fileno())
    if progress_byte_count:
        with records_path.open("rb") as handle:
            handle.seek(progress_byte_count - 1)
            if handle.read(1) != b"\n":
                raise CalibrationError("calibration generation committed prefix does not end on a JSONL boundary")
    records = _load_jsonl(records_path)
    if len(records) != progress_record_count:
        raise CalibrationError("calibration generation progress record count mismatch")
    return records, progress_byte_count


def _append_calibration_generation_batch(
    output_dir: Path,
    records: Sequence[Mapping[str, object]],
    *,
    committed_record_count: int,
    committed_byte_count: int,
) -> tuple[int, int]:
    """Durably append one complete multi-problem batch, then atomically advance its commit marker."""
    if not records or len(records) % 8:
        raise CalibrationError("calibration generation append must contain complete problem groups")
    records_path = output_dir / "samples" / "generations.jsonl"
    records_path.parent.mkdir(parents=True, exist_ok=True)
    current_size = records_path.stat().st_size if records_path.exists() else 0
    if current_size != committed_byte_count:
        raise CalibrationError("calibration generation file changed after progress recovery")
    content = b"".join(_json_bytes(dict(record)) for record in records)
    with records_path.open("ab") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    next_record_count = committed_record_count + len(records)
    next_byte_count = committed_byte_count + len(content)
    _write_generation_progress(output_dir, record_count=next_record_count, byte_count=next_byte_count)
    return next_record_count, next_byte_count


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
        config = CalibrationConfig(
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
    frozen = CalibrationConfig(
        initial_generations=8,
        retry_generations=8,
        temperature=0.8,
        top_p=0.95,
        max_new_tokens=512,
        active_pool_size=3000,
        sft_overlap_fraction=0.075,
        sft_overlap_hard_max=0.15,
        dual_informative_min_fraction=0.70,
        public_only_max_fraction=0.15,
        hidden_only_max_fraction=0.15,
    )
    if config != frozen:
        raise ConfigError("tracked refresh calibration config must match the frozen WP9 protocol")
    return config


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
    problem_batch_size: int = 1,
) -> CalibrationGenerationSummary:
    """Generate or exact-prefix resume one initial/retry k=8 sampled-B bundle."""
    input_manifest, input_records = _load_input_bundle(input_bundle_dir)
    try:
        sft = load_completed_sft_checkpoint(sft_run_dir)
    except Exception as error:
        raise CalibrationError(f"completed B identity is invalid: {type(error).__name__}") from None
    if block_index not in {0, 1}:
        raise CalibrationError("block_index must be 0 or 1")
    if (
        isinstance(problem_batch_size, bool)
        or not isinstance(problem_batch_size, int)
        or not 1 <= problem_batch_size <= 8
    ):
        raise CalibrationError("problem_batch_size must be an integer between 1 and 8")
    if problem_batch_size > 1 and not isinstance(generator, BatchedGroupSamplingGenerator):
        raise CalibrationError("problem_batch_size > 1 requires a batched group sampling generator")
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
        "problem_batch_size": problem_batch_size,
        "input_manifest_sha256": _sha256(input_bundle_dir / "input_manifest.json"),
        "input_records_sha256": input_manifest["records_sha256"],
        "problem_order_sha256": stable_json_hash([record.problem_id for record in selected]),
        "retry_manifest_sha256": retry_sha,
        "sft_checkpoint": _sft_identity(sft),
    }
    records_path = output_dir / "samples" / "generations.jsonl"
    existing: list[dict[str, object]] = []
    existing_status = "running"
    completed_manifest: dict[str, object] | None = None
    committed_byte_count = 0
    if output_dir.exists():
        existing_manifest = _load_json(output_dir / "run.json")
        status = existing_manifest.get("status")
        if status not in {"running", "completed"}:
            raise CalibrationError("calibration generation resume status is invalid")
        existing_status = cast(str, status)
        comparable = dict(existing_manifest)
        comparable.pop("status", None)
        comparable.pop("record_count", None)
        comparable.pop("records_sha256", None)
        expected = dict(identity)
        expected.pop("status")
        if comparable != expected:
            raise CalibrationError("calibration generation resume identity mismatch")
        if existing_status == "completed":
            completed_manifest, existing = load_completed_calibration_generation(output_dir)
        else:
            existing, committed_byte_count = _load_running_calibration_generation_prefix(output_dir)
    else:
        output_dir.mkdir(parents=True)
        _write_json(output_dir / "run.json", identity)
        _write_generation_progress(output_dir, record_count=0, byte_count=0)
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
    if existing_status == "completed":
        if completed_manifest is None or len(existing) != len(expected_keys):
            raise CalibrationError("completed calibration generation does not cover the full exact prefix")
        records_sha = completed_manifest.get("records_sha256")
        if not isinstance(records_sha, str):
            raise CalibrationError("completed calibration generation records hash is invalid")
        return CalibrationGenerationSummary(
            run_dir=output_dir,
            records_path=records_path,
            record_count=len(existing),
            problem_count=len(selected),
            records_sha256=records_sha,
            block_index=block_index,
        )
    committed_record_count = len(existing)
    base_seed = input_manifest.get("seed")
    if isinstance(base_seed, bool) or not isinstance(base_seed, int):
        raise CalibrationError("calibration input seed is invalid")
    remaining = selected[completed_problem_count:]
    for batch_start in range(0, len(remaining), problem_batch_size):
        items = remaining[batch_start : batch_start + problem_batch_size]
        seeds = [calibration_problem_seed(base_seed, item.problem_id, block_index) for item in items]
        if len(items) > 1:
            batched_generator = cast(BatchedGroupSamplingGenerator, generator)
            generated_groups = batched_generator.generate_groups(
                [item.prompt for item in items],
                seeds=seeds,
                num_generations=8,
            )
        else:
            generated_groups = [generator.generate_group(items[0].prompt, seed=seeds[0], num_generations=8)]
        if len(generated_groups) != len(items):
            raise CalibrationError("calibration batched generator returned an unexpected number of problem groups")
        batch_records: list[dict[str, object]] = []
        for item, group_seed, generated in zip(items, seeds, generated_groups, strict=True):
            if len(generated) != 8 or any(not isinstance(result, GenerationResult) for result in generated):
                raise CalibrationError("calibration generator must return exactly eight GenerationResult values")
            batch_records.extend(
                {
                    "problem_id": item.problem_id,
                    "block_index": block_index,
                    "sample_index": block_index * 8 + offset,
                    "sample_seed": group_seed,
                    "completion": result.completion,
                    "completion_tokens": result.completion_tokens,
                    "generation_latency_ms": result.latency_ms,
                    "hit_max_new_tokens": result.hit_max_new_tokens,
                }
                for offset, result in enumerate(generated)
            )
        committed_record_count, committed_byte_count = _append_calibration_generation_batch(
            output_dir,
            batch_records,
            committed_record_count=committed_record_count,
            committed_byte_count=committed_byte_count,
        )
    if committed_record_count != len(expected_keys):
        raise CalibrationError("calibration generation did not cover the exact selected problem set")
    if not records_path.exists():
        _atomic_bytes(records_path, b"")
    records_sha = _sha256(records_path)
    final = {
        **identity,
        "status": "completed",
        "record_count": committed_record_count,
        "records_sha256": records_sha,
    }
    _write_json(output_dir / "run.json", final)
    return CalibrationGenerationSummary(
        run_dir=output_dir,
        records_path=records_path,
        record_count=committed_record_count,
        problem_count=len(selected),
        records_sha256=records_sha,
        block_index=block_index,
    )


def load_completed_calibration_generation(run_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Strictly load one completed sampled-generation bundle."""
    manifest = _load_json(run_dir / "run.json")
    if manifest.get("schema_version") != CALIBRATION_SCHEMA_VERSION or manifest.get("status") != "completed":
        raise CalibrationError("calibration generation is not completed")
    records_path = run_dir / "samples" / "generations.jsonl"
    records = _load_jsonl(records_path)
    batch_size = manifest.get("problem_batch_size")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 8:
        raise CalibrationError("calibration generation problem batch size is invalid")
    progress = _load_json(run_dir / "samples" / "progress.json")
    if set(progress) != {"version", "record_count", "byte_count"}:
        raise CalibrationError("completed calibration generation progress fields are invalid")
    if progress.get("version") != _CALIBRATION_PROGRESS_VERSION:
        raise CalibrationError("completed calibration generation progress version is invalid")
    if progress.get("record_count") != len(records) or progress.get("byte_count") != records_path.stat().st_size:
        raise CalibrationError("completed calibration generation progress does not match records")
    if manifest.get("records_sha256") != _sha256(records_path):
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


def _is_sha256_text(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _validate_score_manifest_binding(
    manifest: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
    *,
    expected_block: int,
    expected_problem_ids: Sequence[str],
    input_manifest_path: Path,
    input_manifest: Mapping[str, object],
    public_training_path: Path,
    hidden_training_path: Path,
    expected_sft_checkpoint: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if manifest.get("block_index") != expected_block or manifest.get("problem_count") != len(records):
        raise CalibrationError("calibration scoring manifest block/count binding is invalid")
    record_ids = [record.get("problem_id") for record in records]
    if record_ids != list(expected_problem_ids) or len(record_ids) != len(set(record_ids)):
        raise CalibrationError("calibration scoring IDs/order do not match the expected calibration input")
    expected_bindings = {
        "input_manifest_sha256": _sha256(input_manifest_path),
        "wp9a_manifest_sha256": input_manifest.get("wp9a_manifest_sha256"),
        "wp9a_public_training_sha256": _sha256(public_training_path),
        "wp9a_hidden_training_sha256": _sha256(hidden_training_path),
    }
    if any(manifest.get(key) != value for key, value in expected_bindings.items()):
        raise CalibrationError("calibration scoring provenance does not match the active input/WP9-a artifacts")
    for field in (
        "records_sha256",
        "retry_problem_ids_sha256",
        "generation_run_manifest_sha256",
        "generation_records_sha256",
        "input_manifest_sha256",
        "wp9a_manifest_sha256",
        "wp9a_public_training_sha256",
        "wp9a_hidden_training_sha256",
    ):
        if not _is_sha256_text(manifest.get(field)):
            raise CalibrationError("calibration scoring manifest contains an invalid SHA256 identity")
    sft_checkpoint = manifest.get("sft_checkpoint")
    expected_sft_fields = {
        "run_id",
        "model_id",
        "model_revision",
        "dataset_hash",
        "config_hash",
        "dependency_lock_hash",
        "seed",
        "checkpoint_sha256",
    }
    if not isinstance(sft_checkpoint, Mapping) or set(sft_checkpoint) != expected_sft_fields:
        raise CalibrationError("calibration scoring SFT checkpoint identity is invalid")
    for field in ("run_id", "model_id", "model_revision", "dataset_hash", "config_hash", "dependency_lock_hash"):
        if not isinstance(sft_checkpoint.get(field), str) or not sft_checkpoint[field]:
            raise CalibrationError("calibration scoring SFT checkpoint identity is invalid")
    if not _is_sha256_text(sft_checkpoint.get("checkpoint_sha256")):
        raise CalibrationError("calibration scoring SFT checkpoint hash is invalid")
    seed = sft_checkpoint.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise CalibrationError("calibration scoring SFT checkpoint seed is invalid")
    if expected_sft_checkpoint is not None and dict(sft_checkpoint) != dict(expected_sft_checkpoint):
        raise CalibrationError("initial/retry calibration scoring used different frozen-B identities")
    return dict(sft_checkpoint)


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


def _validate_calibration_record(
    record: Mapping[str, object],
    *,
    input_record: CalibrationInputRecord | None = None,
    expected_sample_indices: Sequence[int] | None = None,
    require_record_hash: bool = True,
) -> None:
    expected_fields = {
        "problem_id",
        "source_name",
        "difficulty",
        "overlap_origin",
        "quality_gate_required",
        "sample_indices",
        "completion_sha256",
        "public_test_rewards",
        "hidden_test_rewards",
        "public_total_rewards",
        "hidden_total_rewards",
        "public_test_reward_mean",
        "public_test_reward_std",
        "hidden_test_reward_mean",
        "hidden_test_reward_std",
        "public_total_reward_mean",
        "public_total_reward_std",
        "hidden_total_reward_mean",
        "hidden_total_reward_std",
        "public_informative",
        "hidden_informative",
        "calibration_class",
        "public_all_test_correct",
        "hidden_all_test_correct",
        "public_all_test_zero",
        "hidden_all_test_zero",
        "public_full_pass_count",
        "hidden_full_pass_count",
        "parse_failure_count",
        "execution_failure_count",
        "timeout_count",
        "infrastructure_failure_count",
        "completion_token_mean",
        "completion_token_max",
        "truncation_count",
    }
    if require_record_hash:
        expected_fields.add("calibration_record_sha256")
    if set(record) != expected_fields:
        raise CalibrationError("calibration record fields are invalid")
    for field in ("problem_id", "source_name", "difficulty", "overlap_origin"):
        if not isinstance(record.get(field), str) or not record[field]:
            raise CalibrationError("calibration record identity metadata is invalid")
    if record["overlap_origin"] not in {"sft_reuse", "external_new"}:
        raise CalibrationError("calibration record overlap origin is invalid")
    if not isinstance(record.get("quality_gate_required"), bool):
        raise CalibrationError("calibration record quality flag is invalid")
    if input_record is not None:
        expected_identity = (
            input_record.problem_id,
            input_record.source_name,
            input_record.difficulty,
            input_record.overlap_origin,
            input_record.quality_gate_required,
        )
        actual_identity = (
            record["problem_id"],
            record["source_name"],
            record["difficulty"],
            record["overlap_origin"],
            record["quality_gate_required"],
        )
        if actual_identity != expected_identity:
            raise CalibrationError("calibration scoring metadata differs from the frozen input bundle")
    sample_indices = record.get("sample_indices")
    if not isinstance(sample_indices, list) or len(sample_indices) not in {8, 16}:
        raise CalibrationError("calibration record sample indices are invalid")
    expected_indices = (
        list(range(len(sample_indices))) if expected_sample_indices is None else list(expected_sample_indices)
    )
    if sample_indices != expected_indices:
        raise CalibrationError("calibration record sample indices are not the expected contiguous 8/16 block")
    completion_hashes = record.get("completion_sha256")
    if (
        not isinstance(completion_hashes, list)
        or len(completion_hashes) != len(sample_indices)
        or any(not _is_sha256_text(value) for value in completion_hashes)
    ):
        raise CalibrationError("calibration record completion identities are invalid")
    reward_arrays: dict[str, list[float]] = {}
    for prefix in ("public_test", "hidden_test", "public_total", "hidden_total"):
        field = f"{prefix}_rewards"
        raw = record.get(field)
        if not isinstance(raw, list) or len(raw) != len(sample_indices):
            raise CalibrationError("calibration record reward arrays are invalid")
        values: list[float] = []
        for value in raw:
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(float(value)):
                raise CalibrationError("calibration record rewards must be finite numbers")
            values.append(float(value))
        reward_arrays[prefix] = values
        mean, std = _population_stats(values)
        for suffix, expected in (("mean", mean), ("std", std)):
            observed = record.get(f"{prefix}_reward_{suffix}")
            if (
                isinstance(observed, bool)
                or not isinstance(observed, int | float)
                or not math.isclose(float(observed), expected, rel_tol=0.0, abs_tol=1e-12)
            ):
                raise CalibrationError("calibration record derived reward statistics do not recompute")
    public = reward_arrays["public_test"]
    hidden = reward_arrays["hidden_test"]
    public_std = statistics.pstdev(public)
    hidden_std = statistics.pstdev(hidden)
    expected_flags = {
        "public_informative": public_std > 0.0,
        "hidden_informative": hidden_std > 0.0,
        "public_all_test_correct": all(value == 1.0 for value in public),
        "hidden_all_test_correct": all(value == 1.0 for value in hidden),
        "public_all_test_zero": all(value == 0.0 for value in public),
        "hidden_all_test_zero": all(value == 0.0 for value in hidden),
    }
    if any(record.get(field) is not value for field, value in expected_flags.items()):
        raise CalibrationError("calibration record derived boolean flags do not recompute")
    if record.get("calibration_class") != _classification(public_std, hidden_std).value:
        raise CalibrationError("calibration record class does not recompute from test-reward variance")
    if record.get("public_full_pass_count") != sum(value == 1.0 for value in public) or record.get(
        "hidden_full_pass_count"
    ) != sum(value == 1.0 for value in hidden):
        raise CalibrationError("calibration record full-pass counts do not recompute")
    for field in (
        "parse_failure_count",
        "execution_failure_count",
        "timeout_count",
        "infrastructure_failure_count",
        "completion_token_max",
        "truncation_count",
    ):
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CalibrationError("calibration record count telemetry is invalid")
    if record.get("infrastructure_failure_count") != 0:
        raise CalibrationError("calibration records may not retain infrastructure failures")
    token_mean = record.get("completion_token_mean")
    token_max = cast(int, record["completion_token_max"])
    if (
        isinstance(token_mean, bool)
        or not isinstance(token_mean, int | float)
        or not math.isfinite(float(token_mean))
        or float(token_mean) < 0.0
        or float(token_mean) > token_max
        or cast(int, record["truncation_count"]) > len(sample_indices)
    ):
        raise CalibrationError("calibration completion telemetry is invalid")
    if require_record_hash:
        record_hash = record.get("calibration_record_sha256")
        unhashed = dict(record)
        unhashed.pop("calibration_record_sha256", None)
        if not _is_sha256_text(record_hash) or record_hash != stable_json_hash(unhashed):
            raise CalibrationError("calibration record hash does not match its raw derived fields")


def _calibration_disposition(record: Mapping[str, object], *, retried: bool) -> str:
    if record.get("quality_gate_required") is True:
        return "quality_gate_required"
    if record.get("public_all_test_correct") is True and record.get("hidden_all_test_correct") is True:
        return "dual_saturated"
    if retried and record.get("calibration_class") == CalibrationClass.DUAL_UNINFORMATIVE.value:
        return "dual_uninformative_after_16"
    if record.get("calibration_class") == CalibrationClass.DUAL_UNINFORMATIVE.value:
        return "dual_uninformative"
    return "eligible"


def _selection_hash(seed: int, problem_id: str) -> str:
    return hashlib.sha256(f"wp9b-active-pool-v1|{seed}|{problem_id}".encode()).hexdigest()


def _active_selection_hash(seed: int, namespace: str, problem_id: str) -> str:
    return stable_json_hash({"namespace": namespace, "seed": seed, "problem_id": problem_id})


def _source_difficulty_groups(
    records: Sequence[dict[str, object]],
) -> dict[tuple[str, str], list[dict[str, object]]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    seen_ids: set[str] = set()
    for record in records:
        problem_id = record.get("problem_id")
        source_name = record.get("source_name")
        difficulty = record.get("difficulty")
        if (
            not isinstance(problem_id, str)
            or not problem_id
            or problem_id in seen_ids
            or not isinstance(source_name, str)
            or not source_name
            or not isinstance(difficulty, str)
            or not difficulty
        ):
            raise CalibrationError("active-pool stratified population identity is invalid")
        seen_ids.add(problem_id)
        groups.setdefault((source_name, difficulty), []).append(record)
    return groups


def _largest_remainder_allocations(
    populations: Mapping[_SelectionKey, int],
    *,
    count: int,
    seed: int,
    namespace: str,
) -> dict[_SelectionKey, int]:
    """Allocate an exact count proportionally, with deterministic stable-hash ties."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise CalibrationError("active-pool stratified selection count is invalid")
    if not populations:
        if count == 0:
            return {}
        raise CalibrationError("active-pool stratified population is empty")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in populations.values()):
        raise CalibrationError("active-pool stratified population counts are invalid")
    total = sum(populations.values())
    if count > total:
        raise CalibrationError("active-pool stratified selection count is invalid")
    if count == 0:
        return {key: 0 for key in populations}

    allocations: dict[_SelectionKey, int] = {}
    remainders: list[tuple[int, _SelectionKey]] = []
    keys = sorted(populations, key=lambda item: cast(tuple[str, ...], item))
    for key in keys:
        numerator = count * populations[key]
        base, remainder = divmod(numerator, total)
        allocations[key] = base
        remainders.append((remainder, key))
    remaining = count - sum(allocations.values())
    for _remainder, key in sorted(
        remainders,
        key=lambda item: (
            -item[0],
            _active_selection_hash(seed, namespace, "|".join(cast(tuple[str, ...], item[1]))),
            cast(tuple[str, ...], item[1]),
        ),
    )[:remaining]:
        allocations[key] += 1
    return allocations


def _stable_select_records(
    records: Sequence[dict[str, object]],
    *,
    count: int,
    seed: int,
    namespace: str,
) -> list[dict[str, object]]:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > len(records):
        raise CalibrationError("active-pool stratified selection count is invalid")
    ordered = sorted(
        records,
        key=lambda record: (
            _active_selection_hash(seed, namespace, cast(str, record["problem_id"])),
            cast(str, record["problem_id"]),
        ),
    )
    return ordered[:count]


def _source_difficulty_stratified_select(
    records: Sequence[dict[str, object]],
    *,
    count: int,
    seed: int,
    namespace: str,
) -> list[dict[str, object]]:
    """Select an exact proportional source+difficulty sample with deterministic largest remainder."""
    groups = _source_difficulty_groups(records)
    allocations = _largest_remainder_allocations(
        {stratum: len(rows) for stratum, rows in groups.items()},
        count=count,
        seed=seed,
        namespace=namespace,
    )
    selected: list[dict[str, object]] = []
    for stratum in sorted(groups):
        selected.extend(
            _stable_select_records(
                groups[stratum],
                count=allocations[stratum],
                seed=seed,
                namespace=f"{namespace}|{stratum[0]}|{stratum[1]}",
            )
        )
    return selected


def _active_selection_diagnostics(
    eligible: Sequence[dict[str, object]],
    *,
    quotas: Mapping[str, int],
    config: CalibrationConfig,
) -> str:
    populations = Counter(
        (
            "sft_reuse" if record.get("overlap_origin") == "sft_reuse" else "external_new",
            cast(str, record.get("calibration_class")),
            cast(str, record.get("source_name")),
            cast(str, record.get("difficulty")),
        )
        for record in eligible
    )
    payload = {
        "requested_overlap_quotas": dict(quotas),
        "requested_class_constraints": {
            "dual_informative_min": math.ceil(config.active_pool_size * config.dual_informative_min_fraction),
            "public_only_max": math.floor(config.active_pool_size * config.public_only_max_fraction),
            "hidden_only_max": math.floor(config.active_pool_size * config.hidden_only_max_fraction),
            "dual_uninformative_max": 0,
        },
        "population": [
            {
                "overlap_bucket": bucket,
                "calibration_class": calibration_class,
                "source_name": source_name,
                "difficulty": difficulty,
                "count": count,
            }
            for (bucket, calibration_class, source_name, difficulty), count in sorted(populations.items())
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _raise_active_selection_error(
    message: str,
    *,
    eligible: Sequence[dict[str, object]],
    quotas: Mapping[str, int],
    config: CalibrationConfig,
) -> None:
    diagnostics = _active_selection_diagnostics(eligible, quotas=quotas, config=config)
    raise CalibrationError(f"{message}; population_diagnostics={diagnostics}")


def _allocate_public_single_slots(
    single_needs: Mapping[tuple[str, str, str], int],
    public_available: Mapping[tuple[str, str, str], int],
    hidden_available: Mapping[tuple[str, str, str], int],
    *,
    public_cap: int,
    hidden_cap: int,
    eligible: Sequence[dict[str, object]],
    quotas: Mapping[str, int],
    config: CalibrationConfig,
) -> dict[tuple[str, str, str], int]:
    """Allocate residual single-arm slots while retaining each source/difficulty quota."""
    if set(single_needs) != set(public_available) or set(single_needs) != set(hidden_available):
        _raise_active_selection_error(
            "single-arm allocation strata are not aligned",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    total_single = sum(single_needs.values())
    lower: dict[tuple[str, str, str], int] = {}
    upper: dict[tuple[str, str, str], int] = {}
    for bucket in sorted(single_needs):
        need = single_needs[bucket]
        public_count = public_available[bucket]
        hidden_count = hidden_available[bucket]
        if (
            isinstance(need, bool)
            or not isinstance(need, int)
            or need < 0
            or isinstance(public_count, bool)
            or not isinstance(public_count, int)
            or public_count < 0
            or isinstance(hidden_count, bool)
            or not isinstance(hidden_count, int)
            or hidden_count < 0
        ):
            _raise_active_selection_error(
                "single-arm allocation population is invalid",
                eligible=eligible,
                quotas=quotas,
                config=config,
            )
        lower[bucket] = max(0, need - hidden_count)
        upper[bucket] = min(need, public_count)
        if lower[bucket] > upper[bucket]:
            _raise_active_selection_error(
                f"{bucket} source/difficulty stratum cannot fill its single-arm quota",
                eligible=eligible,
                quotas=quotas,
                config=config,
            )
    global_lower = max(sum(lower.values()), total_single - hidden_cap)
    global_upper = min(sum(upper.values()), public_cap)
    if global_lower > global_upper:
        _raise_active_selection_error(
            "single-arm caps cannot satisfy the requested overlap/source populations",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    if total_single == 0:
        return {bucket: 0 for bucket in single_needs}
    total_public_available = sum(public_available.values())
    total_available = total_public_available + sum(hidden_available.values())
    if total_available == 0:
        _raise_active_selection_error(
            "single-arm strata cannot fill the requested target",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    ideal_public = (2 * total_single * total_public_available + total_available) // (2 * total_available)
    target_public = min(max(ideal_public, global_lower), global_upper)
    allocations = dict(lower)
    remaining = target_public - sum(allocations.values())
    if remaining <= 0:
        return allocations
    headroom = {bucket: upper[bucket] - lower[bucket] for bucket in single_needs}
    extras = _largest_remainder_allocations(
        headroom,
        count=remaining,
        seed=0,
        namespace="active-single-arm-public",
    )
    for bucket, extra in extras.items():
        allocations[bucket] += extra
    for bucket in sorted(allocations):
        if allocations[bucket] < lower[bucket] or allocations[bucket] > upper[bucket]:
            _raise_active_selection_error(
                "single-arm allocation exceeded a source/difficulty stratum bound",
                eligible=eligible,
                quotas=quotas,
                config=config,
            )
    if sum(allocations.values()) != target_public:
        _raise_active_selection_error(
            "single-arm allocation did not produce the requested Public count",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    return allocations


def _select_active_records(
    eligible: Sequence[dict[str, object]],
    *,
    config: CalibrationConfig,
    seed: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Apply overlap quotas, whole-bucket strata, class priority, and bounded fallback."""
    overlap_target = int(round(config.active_pool_size * config.sft_overlap_fraction))
    quotas = {
        "sft_reuse": overlap_target,
        "external_new": config.active_pool_size - overlap_target,
    }
    if overlap_target / config.active_pool_size > config.sft_overlap_hard_max + 1e-12:
        _raise_active_selection_error(
            "selected SFT overlap target exceeds the frozen hard maximum",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    buckets = {
        "sft_reuse": [record for record in eligible if record.get("overlap_origin") == "sft_reuse"],
        "external_new": [record for record in eligible if record.get("overlap_origin") != "sft_reuse"],
    }
    allowed_classes = {item.value for item in CalibrationClass}
    seen_ids: set[str] = set()
    for record in eligible:
        problem_id = record.get("problem_id")
        if (
            not isinstance(problem_id, str)
            or not problem_id
            or problem_id in seen_ids
            or not isinstance(record.get("source_name"), str)
            or not cast(str, record["source_name"])
            or not isinstance(record.get("difficulty"), str)
            or not cast(str, record["difficulty"])
            or record.get("calibration_class") not in allowed_classes
            or record.get("calibration_class") == CalibrationClass.DUAL_UNINFORMATIVE.value
        ):
            _raise_active_selection_error(
                "eligible calibration population contains an invalid or uninformative record",
                eligible=eligible,
                quotas=quotas,
                config=config,
            )
        seen_ids.add(cast(str, problem_id))
    selected: list[dict[str, object]] = []
    single_needs: dict[tuple[str, str, str], int] = {}
    public_available: dict[tuple[str, str, str], int] = {}
    hidden_available: dict[tuple[str, str, str], int] = {}
    stratum_targets: dict[tuple[str, str, str], int] = {}
    public_candidates: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    hidden_candidates: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for bucket_name in ("sft_reuse", "external_new"):
        population = buckets[bucket_name]
        quota = quotas[bucket_name]
        if len(population) < quota:
            _raise_active_selection_error(
                f"insufficient {bucket_name} calibrated population for frozen quota",
                eligible=eligible,
                quotas=quotas,
                config=config,
            )
        groups = _source_difficulty_groups(population)
        allocations = _largest_remainder_allocations(
            {stratum: len(rows) for stratum, rows in groups.items()},
            count=quota,
            seed=seed,
            namespace=f"{bucket_name}|strata",
        )
        for stratum in sorted(groups):
            key = (bucket_name, stratum[0], stratum[1])
            stratum_targets[key] = allocations[stratum]
            dual = [
                record
                for record in groups[stratum]
                if record.get("calibration_class") == CalibrationClass.DUAL_INFORMATIVE.value
            ]
            public = [
                record
                for record in groups[stratum]
                if record.get("calibration_class") == CalibrationClass.PUBLIC_ONLY.value
            ]
            hidden = [
                record
                for record in groups[stratum]
                if record.get("calibration_class") == CalibrationClass.HIDDEN_ONLY.value
            ]
            public_candidates[key] = public
            hidden_candidates[key] = hidden
            dual_count = min(allocations[stratum], len(dual))
            selected.extend(
                _stable_select_records(
                    dual,
                    count=dual_count,
                    seed=seed,
                    namespace=f"{bucket_name}|{stratum[0]}|{stratum[1]}|dual",
                )
            )
            single_needs[key] = allocations[stratum] - dual_count
            public_available[key] = len(public)
            hidden_available[key] = len(hidden)

    dual_min = math.ceil(config.active_pool_size * config.dual_informative_min_fraction)
    if len(selected) < dual_min:
        _raise_active_selection_error(
            "selected pool cannot satisfy the dual-informative minimum",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    public_cap = math.floor(config.active_pool_size * config.public_only_max_fraction)
    hidden_cap = math.floor(config.active_pool_size * config.hidden_only_max_fraction)
    public_targets = _allocate_public_single_slots(
        single_needs,
        public_available,
        hidden_available,
        public_cap=public_cap,
        hidden_cap=hidden_cap,
        eligible=eligible,
        quotas=quotas,
        config=config,
    )

    for key in sorted(stratum_targets):
        public_count = public_targets[key]
        hidden_count = single_needs[key] - public_count
        selected.extend(
            _stable_select_records(
                public_candidates[key],
                count=public_count,
                seed=seed,
                namespace=f"{key[0]}|{key[1]}|{key[2]}|public-only",
            )
        )
        selected.extend(
            _stable_select_records(
                hidden_candidates[key],
                count=hidden_count,
                seed=seed,
                namespace=f"{key[0]}|{key[1]}|{key[2]}|hidden-only",
            )
        )

    counts = Counter(cast(str, record.get("calibration_class")) for record in selected)
    if len(selected) != config.active_pool_size:
        _raise_active_selection_error(
            "active-pool selector did not produce the exact requested target",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    if counts[CalibrationClass.DUAL_INFORMATIVE.value] < dual_min:
        _raise_active_selection_error(
            "selected pool cannot satisfy the dual-informative minimum",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    if (
        counts[CalibrationClass.PUBLIC_ONLY.value] > public_cap
        or counts[CalibrationClass.HIDDEN_ONLY.value] > hidden_cap
    ):
        _raise_active_selection_error(
            "selected pool cannot satisfy the single-arm informative caps",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    selected_bucket_counts = Counter(
        "sft_reuse" if record.get("overlap_origin") == "sft_reuse" else "external_new" for record in selected
    )
    if any(selected_bucket_counts[bucket] != quotas[bucket] for bucket in quotas):
        _raise_active_selection_error(
            "active-pool selector did not preserve overlap quotas",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    selected_strata = Counter(
        (
            "sft_reuse" if record.get("overlap_origin") == "sft_reuse" else "external_new",
            cast(str, record.get("source_name")),
            cast(str, record.get("difficulty")),
        )
        for record in selected
    )
    if any(selected_strata[key] != target for key, target in stratum_targets.items()):
        _raise_active_selection_error(
            "active-pool selector did not preserve source/difficulty strata quotas",
            eligible=eligible,
            quotas=quotas,
            config=config,
        )
    selected_ids = {cast(str, record["problem_id"]) for record in selected}
    if len(selected_ids) != len(selected):
        raise CalibrationError("active-pool selector produced duplicate problem IDs")
    reserve: list[dict[str, object]] = [
        {"problem_id": cast(str, record["problem_id"]), "reason": "informative_not_selected"}
        for record in eligible
        if cast(str, record["problem_id"]) not in selected_ids
    ]
    return selected, reserve


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
    input_manifest, input_records = _load_input_bundle(input_bundle_dir)
    input_ids = [record.problem_id for record in input_records]
    input_by_id = {record.problem_id: record for record in input_records}
    refresh_manifest = _load_json(refresh.root_manifest)
    expected_input_schema = CALIBRATION_TEST_SCHEMA_VERSION if allow_test_protocol else CALIBRATION_SCHEMA_VERSION
    expected_input_evidence = "engineering" if allow_test_protocol else "formal_input"
    expected_input_bindings = {
        "schema_version": expected_input_schema,
        "seed": seed,
        "wp9a_manifest_sha256": _sha256(refresh.root_manifest),
        "wp9a_selected_order_sha256": refresh_manifest.get("selected_ids_order_sha256"),
        "wp9a_public_training_sha256": _sha256(refresh.public_grpo_jsonl),
        "wp9a_hidden_training_sha256": _sha256(refresh.hidden_grpo_jsonl),
        "evidence_class": expected_input_evidence,
    }
    if any(input_manifest.get(key) != value for key, value in expected_input_bindings.items()):
        raise CalibrationError("calibration input bundle does not match the active WP9-a artifacts/seed")

    initial_manifest, initial_records = _load_scores(initial_scoring_dir)
    initial_sft_checkpoint = _validate_score_manifest_binding(
        initial_manifest,
        initial_records,
        expected_block=0,
        expected_problem_ids=input_ids,
        input_manifest_path=input_bundle_dir / "input_manifest.json",
        input_manifest=input_manifest,
        public_training_path=refresh.public_grpo_jsonl,
        hidden_training_path=refresh.hidden_grpo_jsonl,
    )
    for record in initial_records:
        problem_id = cast(str, record["problem_id"])
        _validate_calibration_record(
            record,
            input_record=input_by_id[problem_id],
            expected_sample_indices=range(8),
            require_record_hash=False,
        )
    retry_rows = _load_jsonl(initial_scoring_dir / "manifest" / "retry_problem_ids.jsonl")
    if any(set(row) != {"problem_id"} or not isinstance(row.get("problem_id"), str) for row in retry_rows):
        raise CalibrationError("initial retry manifest rows are invalid")
    expected_retry_ids = [cast(str, row["problem_id"]) for row in retry_rows]
    derived_retry_ids = sorted(
        cast(str, record["problem_id"])
        for record in initial_records
        if record["public_all_test_zero"] is True and record["hidden_all_test_zero"] is True
    )
    if expected_retry_ids != derived_retry_ids or expected_retry_ids != sorted(set(expected_retry_ids)):
        raise CalibrationError("initial retry manifest does not recompute from both-zero calibration records")

    retry_by_id: dict[str, dict[str, object]] = {}
    retry_manifest: dict[str, object] | None = None
    if expected_retry_ids:
        if retry_scoring_dir is None:
            raise CalibrationError("both-zero initial problems require retry scoring")
        retry_manifest, retry_records = _load_scores(retry_scoring_dir)
        _validate_score_manifest_binding(
            retry_manifest,
            retry_records,
            expected_block=1,
            expected_problem_ids=expected_retry_ids,
            input_manifest_path=input_bundle_dir / "input_manifest.json",
            input_manifest=input_manifest,
            public_training_path=refresh.public_grpo_jsonl,
            hidden_training_path=refresh.hidden_grpo_jsonl,
            expected_sft_checkpoint=initial_sft_checkpoint,
        )
        for record in retry_records:
            problem_id = cast(str, record["problem_id"])
            _validate_calibration_record(
                record,
                input_record=input_by_id[problem_id],
                expected_sample_indices=range(8, 16),
                require_record_hash=False,
            )
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
        _validate_calibration_record(record, input_record=input_by_id[problem_id])
        disposition = _calibration_disposition(record, retried=problem_id in retry_by_id)
        if disposition == "quality_gate_required":
            reserve.append({"problem_id": problem_id, "reason": disposition})
        elif disposition == "dual_saturated":
            easy.append({"problem_id": problem_id, "reason": disposition})
        elif disposition == "dual_uninformative_after_16":
            hard.append({"problem_id": problem_id, "reason": disposition})
        elif disposition == "dual_uninformative":
            reserve.append({"problem_id": problem_id, "reason": disposition})
        else:
            eligible.append(record)
    selected, informative_reserve = _select_active_records(
        eligible,
        config=config,
        seed=seed,
    )
    reserve.extend(informative_reserve)
    overlap_target = int(round(config.active_pool_size * config.sft_overlap_fraction))
    counts = Counter(cast(str, record["calibration_class"]) for record in selected)
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
        classification_report_path = temporary / "reports" / "classification_summary.json"
        composition_report_path = temporary / "reports" / "pool_composition.json"
        _write_json(
            classification_report_path,
            dict(Counter(cast(str, record["calibration_class"]) for record in final_records)),
        )
        _write_json(composition_report_path, composition)
        artifacts = {
            "records/calibration.jsonl": records_sha,
            "manifest/retry_problem_ids.jsonl": retry_sha,
            "manifest/active_selection.jsonl": active_selection_sha,
            "manifest/problem_order.jsonl": problem_order_sha,
            "manifest/reserve_problem_ids.jsonl": reserve_sha,
            "manifest/hard_problem_ids.jsonl": hard_sha,
            "manifest/easy_problem_ids.jsonl": easy_sha,
            "reports/classification_summary.json": _sha256(classification_report_path),
            "reports/pool_composition.json": _sha256(composition_report_path),
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
    """Recompute active-pool provenance, calibration statistics, selection, and training views."""
    refresh = check_refresh_data(
        refresh_dataset_dir,
        reference_dataset_dir=reference_dataset_dir,
        allow_test_protocol=allow_test_protocol,
    )
    refresh_manifest = _load_json(refresh.root_manifest)
    manifest = _load_json(pool_dir / "calibration_manifest.json")
    expected_schema = CALIBRATION_TEST_SCHEMA_VERSION if allow_test_protocol else CALIBRATION_SCHEMA_VERSION
    expected_evidence = "engineering" if allow_test_protocol else "formal_calibration"
    expected_manifest_fields = {
        "schema_version",
        "status",
        "evidence_class",
        "seed",
        "config",
        "wp9a_manifest_sha256",
        "wp9a_selected_order_sha256",
        "input_manifest_sha256",
        "initial_scoring_manifest_sha256",
        "retry_scoring_manifest_sha256",
        "sft_checkpoint",
        "active_order_sha256",
        "composition",
        "artifacts",
    }
    if (
        set(manifest) != expected_manifest_fields
        or manifest.get("schema_version") != expected_schema
        or manifest.get("status") != "completed"
        or manifest.get("evidence_class") != expected_evidence
    ):
        raise CalibrationError("calibrated active-pool manifest identity/schema is invalid")
    seed = manifest.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise CalibrationError("calibrated active-pool seed is invalid")
    if manifest.get("wp9a_manifest_sha256") != _sha256(refresh.root_manifest) or manifest.get(
        "wp9a_selected_order_sha256"
    ) != refresh_manifest.get("selected_ids_order_sha256"):
        raise CalibrationError("calibrated active pool is not bound to the current WP9-a artifact")
    for field in ("input_manifest_sha256", "initial_scoring_manifest_sha256"):
        if not _is_sha256_text(manifest.get(field)):
            raise CalibrationError("calibrated active-pool source manifest SHA is invalid")
    retry_scoring_sha = manifest.get("retry_scoring_manifest_sha256")
    if retry_scoring_sha is not None and not _is_sha256_text(retry_scoring_sha):
        raise CalibrationError("calibrated active-pool retry scoring SHA is invalid")

    config_mapping = manifest.get("config")
    config_fields = {
        "initial_generations",
        "retry_generations",
        "temperature",
        "top_p",
        "max_new_tokens",
        "active_pool_size",
        "sft_overlap_fraction",
        "sft_overlap_hard_max",
        "dual_informative_min_fraction",
        "public_only_max_fraction",
        "hidden_only_max_fraction",
    }
    if not isinstance(config_mapping, Mapping) or set(config_mapping) != config_fields:
        raise CalibrationError("calibrated active-pool config is invalid")
    try:
        config = CalibrationConfig(
            initial_generations=cast(int, config_mapping["initial_generations"]),
            retry_generations=cast(int, config_mapping["retry_generations"]),
            temperature=cast(float, config_mapping["temperature"]),
            top_p=cast(float, config_mapping["top_p"]),
            max_new_tokens=cast(int, config_mapping["max_new_tokens"]),
            active_pool_size=cast(int, config_mapping["active_pool_size"]),
            sft_overlap_fraction=cast(float, config_mapping["sft_overlap_fraction"]),
            sft_overlap_hard_max=cast(float, config_mapping["sft_overlap_hard_max"]),
            dual_informative_min_fraction=cast(float, config_mapping["dual_informative_min_fraction"]),
            public_only_max_fraction=cast(float, config_mapping["public_only_max_fraction"]),
            hidden_only_max_fraction=cast(float, config_mapping["hidden_only_max_fraction"]),
        )
    except (CalibrationError, KeyError, TypeError, ValueError) as error:
        raise CalibrationError("calibrated active-pool config is invalid") from error
    if not allow_test_protocol:
        frozen = CalibrationConfig(8, 8, 0.8, 0.95, 512, 3000, 0.075, 0.15, 0.70, 0.15, 0.15)
        if config != frozen:
            raise CalibrationError("formal calibrated active-pool config differs from the frozen WP9 protocol")

    sft_checkpoint = manifest.get("sft_checkpoint")
    expected_sft_fields = {
        "run_id",
        "model_id",
        "model_revision",
        "dataset_hash",
        "config_hash",
        "dependency_lock_hash",
        "seed",
        "checkpoint_sha256",
    }
    if not isinstance(sft_checkpoint, Mapping) or set(sft_checkpoint) != expected_sft_fields:
        raise CalibrationError("calibrated active-pool SFT checkpoint identity is invalid")
    if any(
        not isinstance(sft_checkpoint.get(field), str) or not cast(str, sft_checkpoint[field])
        for field in ("run_id", "model_id", "model_revision", "dataset_hash", "config_hash", "dependency_lock_hash")
    ):
        raise CalibrationError("calibrated active-pool SFT checkpoint identity is invalid")
    if not _is_sha256_text(sft_checkpoint.get("checkpoint_sha256")):
        raise CalibrationError("calibrated active-pool SFT checkpoint hash is invalid")
    sft_seed = sft_checkpoint.get("seed")
    if isinstance(sft_seed, bool) or not isinstance(sft_seed, int):
        raise CalibrationError("calibrated active-pool SFT checkpoint seed is invalid")

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
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != expected_artifacts:
        raise CalibrationError("calibrated active-pool artifact inventory is invalid")
    for relative in sorted(expected_artifacts):
        expected_sha = artifacts.get(relative)
        if not _is_sha256_text(expected_sha) or _sha256(pool_dir / relative) != expected_sha:
            raise CalibrationError("calibrated active-pool artifact hash mismatch")

    source_public = load_training_artifact(refresh.public_grpo_jsonl, kind=TrainingArtifactKind.PUBLIC_GRPO)
    source_hidden = load_training_artifact(refresh.hidden_grpo_jsonl, kind=TrainingArtifactKind.HIDDEN_GRPO)
    source_public_ids = [cast(str, row["problem_id"]) for row in source_public]
    source_hidden_ids = [cast(str, row["problem_id"]) for row in source_hidden]
    if source_public_ids != source_hidden_ids:
        raise CalibrationError("WP9-a Public/Hidden source training views have different IDs/order")
    source_public_by_id = {cast(str, row["problem_id"]): row for row in source_public}
    source_hidden_by_id = {cast(str, row["problem_id"]): row for row in source_hidden}
    refresh_selection_rows = _load_jsonl(refresh_dataset_dir / "manifest" / "selection.jsonl")
    refresh_selection_by_id = {cast(str, row["problem_id"]): row for row in refresh_selection_rows}
    if [cast(str, row["problem_id"]) for row in refresh_selection_rows] != source_public_ids:
        raise CalibrationError("WP9-a selection order differs from its Public/Hidden training views")

    records = _load_jsonl(pool_dir / "records" / "calibration.jsonl")
    record_ids = [record.get("problem_id") for record in records]
    if record_ids != source_public_ids or len(record_ids) != len(set(record_ids)):
        raise CalibrationError("calibration records do not cover the frozen WP9-a pool exactly once in order")
    record_by_id: dict[str, dict[str, object]] = {}
    for record in records:
        problem_id = cast(str, record["problem_id"])
        selection_source = refresh_selection_by_id[problem_id]
        public_source = source_public_by_id[problem_id]
        public_metadata = public_source.get("metadata")
        if not isinstance(public_metadata, Mapping) or not isinstance(public_metadata.get("difficulty"), str):
            raise CalibrationError("WP9-a source difficulty metadata is invalid")
        input_identity = CalibrationInputRecord(
            problem_id=problem_id,
            prompt="checker-does-not-consume-prompt",
            function_name=cast(str, public_source["function_name"]),
            source_name=cast(str, selection_source["source"]),
            difficulty=cast(str, public_metadata["difficulty"]),
            overlap_origin=cast(str, selection_source["overlap_origin"]),
            quality_gate_required=cast(bool, selection_source["quality_gate_required"]),
        )
        _validate_calibration_record(record, input_record=input_identity)
        record_by_id[problem_id] = record

    retry_rows = _load_jsonl(pool_dir / "manifest" / "retry_problem_ids.jsonl")
    if any(set(row) != {"problem_id"} or not isinstance(row.get("problem_id"), str) for row in retry_rows):
        raise CalibrationError("calibrated retry manifest rows are invalid")
    retry_ids = [cast(str, row["problem_id"]) for row in retry_rows]
    derived_retry_ids = sorted(
        cast(str, record["problem_id"])
        for record in records
        if len(cast(list[object], record["sample_indices"])) == 16
    )
    if retry_ids != derived_retry_ids or retry_ids != sorted(set(retry_ids)):
        raise CalibrationError("calibrated retry manifest does not match the 16-sample records")
    if bool(retry_ids) != (retry_scoring_sha is not None):
        raise CalibrationError("calibrated retry manifest and retry scoring provenance disagree")

    eligible: list[dict[str, object]] = []
    base_reserve: list[dict[str, object]] = []
    hard: list[dict[str, object]] = []
    easy: list[dict[str, object]] = []
    retry_id_set = set(retry_ids)
    for record in records:
        problem_id = cast(str, record["problem_id"])
        disposition = _calibration_disposition(record, retried=problem_id in retry_id_set)
        if disposition == "quality_gate_required":
            base_reserve.append({"problem_id": problem_id, "reason": disposition})
        elif disposition == "dual_saturated":
            easy.append({"problem_id": problem_id, "reason": disposition})
        elif disposition == "dual_uninformative_after_16":
            hard.append({"problem_id": problem_id, "reason": disposition})
        elif disposition == "dual_uninformative":
            base_reserve.append({"problem_id": problem_id, "reason": disposition})
        else:
            eligible.append(record)

    selected_records, informative_reserve = _select_active_records(
        eligible,
        config=config,
        seed=seed,
    )
    reserve = [*base_reserve, *informative_reserve]
    overlap_target = int(round(config.active_pool_size * config.sft_overlap_fraction))
    selected_counts = Counter(cast(str, record["calibration_class"]) for record in selected_records)
    if selected_counts[CalibrationClass.DUAL_UNINFORMATIVE.value] != 0:
        raise CalibrationError("calibrated active pool contains dual-uninformative problems")
    selected_records.sort(key=lambda record: _selection_hash(seed + 1, cast(str, record["problem_id"])))
    selected_ids = [cast(str, record["problem_id"]) for record in selected_records]

    order_rows = _load_jsonl(pool_dir / "manifest" / "problem_order.jsonl")
    expected_order_rows = [
        {"ordinal": ordinal, "problem_id": problem_id} for ordinal, problem_id in enumerate(selected_ids)
    ]
    if order_rows != expected_order_rows:
        raise CalibrationError("calibrated active-pool order does not recompute from records/config/seed")
    selection_rows = _load_jsonl(pool_dir / "manifest" / "active_selection.jsonl")
    expected_selection_rows = [
        {
            "ordinal": ordinal,
            "problem_id": problem_id,
            "calibration_class": record_by_id[problem_id]["calibration_class"],
            "calibration_record_sha256": record_by_id[problem_id]["calibration_record_sha256"],
            "overlap_origin": record_by_id[problem_id]["overlap_origin"],
        }
        for ordinal, problem_id in enumerate(selected_ids)
    ]
    if selection_rows != expected_selection_rows:
        raise CalibrationError("active selection metadata does not recompute from calibration records")
    expected_reserve = sorted(reserve, key=lambda row: cast(str, row["problem_id"]))
    if _load_jsonl(pool_dir / "manifest" / "reserve_problem_ids.jsonl") != expected_reserve:
        raise CalibrationError("calibrated reserve manifest does not recompute")
    if _load_jsonl(pool_dir / "manifest" / "hard_problem_ids.jsonl") != hard:
        raise CalibrationError("calibrated hard manifest does not recompute")
    if _load_jsonl(pool_dir / "manifest" / "easy_problem_ids.jsonl") != easy:
        raise CalibrationError("calibrated easy manifest does not recompute")

    public = load_training_artifact(pool_dir / "training" / "public_grpo.jsonl", kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden = load_training_artifact(pool_dir / "training" / "hidden_grpo.jsonl", kind=TrainingArtifactKind.HIDDEN_GRPO)
    if [row["problem_id"] for row in public] != selected_ids or [row["problem_id"] for row in hidden] != selected_ids:
        raise CalibrationError("active Public/Hidden training views have different IDs/order")
    for mode_rows, source in ((public, source_public_by_id), (hidden, source_hidden_by_id)):
        for row in mode_rows:
            problem_id = cast(str, row["problem_id"])
            expected = dict(source[problem_id])
            metadata = expected.get("metadata")
            if not isinstance(metadata, Mapping):
                raise CalibrationError("WP9-a source training metadata is invalid")
            calibrated = record_by_id[problem_id]
            expected["metadata"] = {
                **dict(metadata),
                "calibration_class": cast(str, calibrated["calibration_class"]),
                "calibration_record_sha256": cast(str, calibrated["calibration_record_sha256"]),
                "overlap_origin": cast(str, calibrated["overlap_origin"]),
            }
            if row != expected:
                raise CalibrationError(
                    "active training view differs from the frozen WP9-a row plus calibration metadata"
                )

    class_counts = {item.value: selected_counts[item.value] for item in CalibrationClass}
    overlap_count = sum(record["overlap_origin"] == "sft_reuse" for record in selected_records)
    composition = {
        "selected_problems": len(selected_ids),
        "class_counts": class_counts,
        "class_fractions": {key: value / len(selected_ids) for key, value in class_counts.items()},
        "sft_overlap_count": overlap_count,
        "sft_overlap_fraction": overlap_count / len(selected_ids),
        "quality_excluded_count": sum(record["quality_gate_required"] is True for record in records),
    }
    if (
        manifest.get("composition") != composition
        or _load_json(pool_dir / "reports" / "pool_composition.json") != composition
    ):
        raise CalibrationError("active-pool composition does not recompute from raw calibration records")
    classification_summary = dict(Counter(cast(str, record["calibration_class"]) for record in records))
    if _load_json(pool_dir / "reports" / "classification_summary.json") != classification_summary:
        raise CalibrationError("calibration classification summary does not recompute")
    active_order_sha = stable_json_hash(selected_ids)
    if manifest.get("active_order_sha256") != active_order_sha:
        raise CalibrationError("active pool order hash mismatch")
    if overlap_count != overlap_target or overlap_count / len(selected_ids) > config.sft_overlap_hard_max + 1e-12:
        raise CalibrationError("active-pool SFT overlap does not satisfy the frozen target/hard max")

    return CalibrationPoolSummary(
        pool_dir=pool_dir,
        selected_problems=len(selected_ids),
        dual_informative=selected_counts[CalibrationClass.DUAL_INFORMATIVE.value],
        public_only=selected_counts[CalibrationClass.PUBLIC_ONLY.value],
        hidden_only=selected_counts[CalibrationClass.HIDDEN_ONLY.value],
        sft_overlap_count=overlap_count,
        active_order_sha256=active_order_sha,
        calibration_manifest=pool_dir / "calibration_manifest.json",
        public_grpo_jsonl=pool_dir / "training" / "public_grpo.jsonl",
        hidden_grpo_jsonl=pool_dir / "training" / "hidden_grpo.jsonl",
    )
