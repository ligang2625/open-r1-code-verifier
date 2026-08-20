"""Two-stage deterministic evaluation: GPU generation, then Piston verification.

The generation stage persists irrecoverable model outputs without contacting Piston.
The verification stage consumes that immutable bundle and writes the existing WP5
per-problem evaluation schema, so downstream aggregation and analysis stay unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

import yaml

from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.schema import CodeProblem
from code_verifier.environment import collect_environment
from code_verifier.evaluation.evaluate import (
    EvaluationConfig,
    EvaluationError,
    EvaluationRecord,
    _append_progress,
    _read_json_object,
    _run_context,
    _update_run_status,
    _write_json,
    append_evaluation_record,
    dataset_hash,
    evaluate_completion,
    evaluation_config_hash,
    initialize_or_resume_run,
    load_evaluation_problems,
    prompt_hash,
)
from code_verifier.evaluation.generate import CompletionGenerator, GenerationResult, build_evaluation_prompt
from code_verifier.execution.base import CodeExecutor

_BUNDLE_VERSION = 1
_BUNDLE_TYPE = "evaluation_generation_bundle"
_GPU_HOURS_SEMANTICS = "persisted_generation_latency_ms_x_gpu_count_used"
_RECORD_FIELDS = {
    "run_id",
    "model_id",
    "checkpoint",
    "dataset_hash",
    "evaluation_contract_sha256",
    "problem_id",
    "prompt_hash",
    "completion",
    "completion_tokens",
    "generation_latency_ms",
    "hit_max_new_tokens",
}


@dataclass(frozen=True)
class GenerationBundleRecord:
    """One generated completion persisted before any untrusted-code execution."""

    run_id: str
    model_id: str
    checkpoint: str
    dataset_hash: str
    evaluation_contract_sha256: str
    problem_id: str
    prompt_hash: str
    completion: str
    completion_tokens: int
    generation_latency_ms: float
    hit_max_new_tokens: bool


@dataclass(frozen=True)
class GenerationBundleIdentity:
    """Validated identity of one completed, transferable generation bundle."""

    run_dir: Path
    run_id: str
    model_id: str
    model_revision: str | None
    checkpoint: str
    dataset_hash: str
    evaluation_contract_sha256: str
    piston_config_sha256: str
    seed: int
    total_problems: int
    records_sha256: str
    ordered_problem_ids_sha256: str
    environment_sha256: str
    gpu_count_used: int
    gpu_hours: float
    start_time: str
    end_time: str


@dataclass(frozen=True)
class GenerationBundleSource:
    """Minimal completed-bundle source identity needed before local verification."""

    run_id: str
    model_id: str
    model_revision: str | None
    checkpoint: str
    seed: int


@dataclass(frozen=True)
class GenerationBundleSummary:
    """Non-sensitive generation-stage progress summary."""

    run_id: str
    total_problems: int
    completed_before_run: int
    generated_this_run: int
    run_dir: Path
    records_path: Path


@dataclass(frozen=True)
class EvaluationVerificationSummary:
    """Non-sensitive verification-stage progress summary."""

    run_id: str
    total_problems: int
    completed_before_run: int
    verified_this_run: int
    results_path: Path
    generation_records_sha256: str


@dataclass(frozen=True)
class _BundleContext:
    run_dir: Path
    records_path: Path
    metrics_path: Path
    stdout_path: Path
    stderr_path: Path
    run_json_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{field} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise EvaluationError(f"{field} must contain valid UTF-8") from None
    return value


def _sha(value: object, field: str) -> str:
    text = _nonempty(value, field)
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise EvaluationError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"{field} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise EvaluationError(f"{field} must be a finite non-negative number")
    return number


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise EvaluationError(f"artifact is unreadable: {type(error).__name__}") from None


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _context(output_root: Path, run_id: str) -> _BundleContext:
    run_dir = output_root / "generation" / run_id
    return _BundleContext(
        run_dir=run_dir,
        records_path=run_dir / "samples" / "generations.jsonl",
        metrics_path=run_dir / "metrics.jsonl",
        stdout_path=run_dir / "stdout.log",
        stderr_path=run_dir / "stderr.log",
        run_json_path=run_dir / "run.json",
    )


def _validate_run_id(run_id: str) -> None:
    if re.fullmatch(r"[A-Za-z0-9._-]+", run_id) is None or ".." in run_id:
        raise EvaluationError("run_id contains unsupported characters")


def _ordered_ids_sha(problems: Sequence[CodeProblem]) -> str:
    text = json.dumps([problem.problem_id for problem in problems], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evaluation_contract(
    config: EvaluationConfig,
    *,
    run_id: str,
    model_id: str,
    seed: int,
    problems: Sequence[CodeProblem],
) -> dict[str, object]:
    """Return a cross-machine evaluation identity without local absolute paths."""
    return {
        "schema_version": _BUNDLE_VERSION,
        "run_id": run_id,
        "model_id": model_id,
        "model_revision": config.model_revision,
        "checkpoint": config.checkpoint,
        "seed": seed,
        "split": config.split,
        "device": config.device,
        "generation": asdict(config.generation),
        "dataset_hash": dataset_hash(problems),
        "piston_config_sha256": _file_sha(config.piston_config),
    }


def _evaluation_contract_sha256(
    config: EvaluationConfig,
    *,
    run_id: str,
    model_id: str,
    seed: int,
    problems: Sequence[CodeProblem],
) -> str:
    payload = _evaluation_contract(config, run_id=run_id, model_id=model_id, seed=seed, problems=problems)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _gpu_count(config: EvaluationConfig, environment: Mapping[str, object]) -> int:
    value = environment.get("gpu_count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationError("environment gpu_count is invalid")
    if config.device == "cpu" or value == 0:
        return 0
    return 1 if config.device == "cuda" else value


def generation_bundle_record_from_mapping(value: object) -> GenerationBundleRecord:
    """Parse one exact generation-bundle row."""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EvaluationError("generation bundle record must be a string-keyed mapping")
    mapping = cast(Mapping[str, object], value)
    if set(mapping) != _RECORD_FIELDS:
        raise EvaluationError("generation bundle record fields do not match the required schema")
    completion = mapping["completion"]
    if not isinstance(completion, str):
        raise EvaluationError("generation bundle completion must be a string")
    try:
        completion.encode("utf-8")
    except UnicodeEncodeError:
        raise EvaluationError("generation bundle completion must contain valid UTF-8") from None
    tokens = mapping["completion_tokens"]
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise EvaluationError("generation bundle completion_tokens must be a non-negative integer")
    hit_limit = mapping["hit_max_new_tokens"]
    if not isinstance(hit_limit, bool):
        raise EvaluationError("generation bundle hit_max_new_tokens must be a boolean")
    record = GenerationBundleRecord(
        run_id=_nonempty(mapping["run_id"], "generation run_id"),
        model_id=_nonempty(mapping["model_id"], "generation model_id"),
        checkpoint=_nonempty(mapping["checkpoint"], "generation checkpoint"),
        dataset_hash=_sha(mapping["dataset_hash"], "generation dataset_hash"),
        evaluation_contract_sha256=_sha(
            mapping["evaluation_contract_sha256"], "generation evaluation_contract_sha256"
        ),
        problem_id=_nonempty(mapping["problem_id"], "generation problem_id"),
        prompt_hash=_sha(mapping["prompt_hash"], "generation prompt_hash"),
        completion=completion,
        completion_tokens=tokens,
        generation_latency_ms=_finite_nonnegative(mapping["generation_latency_ms"], "generation latency"),
        hit_max_new_tokens=hit_limit,
    )
    GenerationResult(
        completion=record.completion,
        completion_tokens=record.completion_tokens,
        latency_ms=record.generation_latency_ms,
        hit_max_new_tokens=record.hit_max_new_tokens,
    )
    return record


def generation_bundle_record_to_mapping(record: GenerationBundleRecord) -> dict[str, object]:
    """Serialize one exact generation-bundle row."""
    mapping = dict(record.__dict__)
    if generation_bundle_record_from_mapping(mapping) != record:
        raise EvaluationError("generation bundle record is outside the serialized contract")
    return mapping


def load_generation_bundle_records(path: Path) -> list[GenerationBundleRecord]:
    """Strictly deserialize one UTF-8 generation JSONL file."""
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeError) as error:
        raise EvaluationError(f"generation JSONL is unreadable: {type(error).__name__}") from None
    if lines and lines[-1] == "":
        lines.pop()
    records: list[GenerationBundleRecord] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise EvaluationError("generation JSONL must not contain blank rows")
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise EvaluationError(f"generation JSONL row {line_number} is invalid: {type(error).__name__}") from None
        records.append(generation_bundle_record_from_mapping(value))
    return records


def _gpu_hours(records: Sequence[GenerationBundleRecord], gpu_count_used: int) -> float:
    return sum(record.generation_latency_ms for record in records) * gpu_count_used / 3_600_000.0


def _rewrite_generation_metrics(context: _BundleContext, records: Sequence[GenerationBundleRecord]) -> None:
    """Atomically rebuild payload-free progress telemetry from durable generation rows."""
    content = "".join(
        json.dumps(
            {
                "problem_id": record.problem_id,
                "generation_latency_ms": record.generation_latency_ms,
                "completion_tokens": record.completion_tokens,
                "hit_max_new_tokens": record.hit_max_new_tokens,
                "completed": index,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for index, record in enumerate(records, start=1)
    )
    _atomic_text(context.metrics_path, content)


def _update_bundle_status(context: _BundleContext, status: Literal["running", "failed", "completed"]) -> None:
    metadata = dict(_read_json_object(context.run_json_path, artifact_name="generation run.json"))
    gpu_count_used = metadata.get("gpu_count_used")
    if isinstance(gpu_count_used, bool) or not isinstance(gpu_count_used, int) or gpu_count_used < 0:
        raise EvaluationError("generation gpu_count_used is invalid")
    records = load_generation_bundle_records(context.records_path)
    _rewrite_generation_metrics(context, records)
    metadata["completed_records"] = len(records)
    metadata["gpu_hours"] = _gpu_hours(records, gpu_count_used)
    metadata["status"] = status
    metadata["end_time"] = _now() if status == "completed" else None
    metadata["records_sha256"] = _file_sha(context.records_path) if status == "completed" else None
    _write_json(context.run_json_path, metadata)


def _new_bundle(
    *,
    output_root: Path,
    run_id: str,
    config: EvaluationConfig,
    model_id: str,
    seed: int,
    problems: Sequence[CodeProblem],
) -> _BundleContext:
    context = _context(output_root, run_id)
    environment = collect_environment()
    dataset_identity = dataset_hash(problems)
    contract = _evaluation_contract(config, run_id=run_id, model_id=model_id, seed=seed, problems=problems)
    contract_identity = _evaluation_contract_sha256(
        config, run_id=run_id, model_id=model_id, seed=seed, problems=problems
    )
    context.run_dir.mkdir(parents=True, exist_ok=False)
    context.records_path.parent.mkdir(parents=True, exist_ok=False)
    try:
        started = _now()
        resolved_path = context.run_dir / "resolved_config.yaml"
        environment_path = context.run_dir / "environment.json"
        _atomic_text(resolved_path, yaml.safe_dump(contract, sort_keys=True, allow_unicode=True))
        _write_json(environment_path, environment)
        metadata: dict[str, object] = {
            "schema_version": _BUNDLE_VERSION,
            "artifact_type": _BUNDLE_TYPE,
            "run_id": run_id,
            "created_at": started,
            "start_time": started,
            "end_time": None,
            "status": "running",
            "command": "code-verifier generate-eval",
            "model_id": model_id,
            "model_revision": config.model_revision,
            "checkpoint": config.checkpoint,
            "dataset_hash": dataset_identity,
            "evaluation_contract_sha256": contract_identity,
            "piston_config_sha256": _file_sha(config.piston_config),
            "seed": seed,
            "total_problems": len(problems),
            "completed_records": 0,
            "ordered_problem_ids_sha256": _ordered_ids_sha(problems),
            "records_sha256": None,
            "resolved_config_sha256": _file_sha(resolved_path),
            "environment_sha256": _file_sha(environment_path),
            "gpu_hours": 0.0,
            "gpu_count_used": _gpu_count(config, environment),
            "gpu_hours_semantics": _GPU_HOURS_SEMANTICS,
            "project_commit": environment["project_commit"],
            "open_r1_commit": environment["open_r1_commit"],
            "dependency_lock_hash": environment["dependency_lock_hash"],
        }
        _write_json(context.run_json_path, metadata)
        for path in (context.records_path, context.metrics_path, context.stdout_path, context.stderr_path):
            path.touch(exist_ok=False)
    except Exception:
        shutil.rmtree(context.run_dir, ignore_errors=True)
        raise
    return context


def _load_yaml_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise EvaluationError(f"generation resolved config is invalid: {type(error).__name__}") from None
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EvaluationError("generation resolved config must be a string-keyed mapping")
    return cast(Mapping[str, object], value)


def _validate_rows(
    records: Sequence[GenerationBundleRecord],
    *,
    run_id: str,
    model_id: str,
    config: EvaluationConfig,
    seed: int,
    problems: Sequence[CodeProblem],
) -> None:
    if len(records) > len(problems):
        raise EvaluationError("generation bundle contains more rows than the selected split")
    dataset_identity = dataset_hash(problems)
    contract_identity = _evaluation_contract_sha256(
        config, run_id=run_id, model_id=model_id, seed=seed, problems=problems
    )
    for index, record in enumerate(records):
        problem = problems[index]
        expected = {
            "run_id": run_id,
            "model_id": model_id,
            "checkpoint": config.checkpoint,
            "dataset_hash": dataset_identity,
            "evaluation_contract_sha256": contract_identity,
            "problem_id": problem.problem_id,
            "prompt_hash": prompt_hash(build_evaluation_prompt(problem)),
        }
        actual = {field: getattr(record, field) for field in expected}
        if actual != expected:
            raise EvaluationError(f"generation row {index + 1} is not the exact expected prefix")


def _resume_bundle(
    *,
    output_root: Path,
    run_id: str,
    config: EvaluationConfig,
    model_id: str,
    seed: int,
    problems: Sequence[CodeProblem],
) -> tuple[_BundleContext, list[GenerationBundleRecord]]:
    context = _context(output_root, run_id)
    expected_names = {
        "run.json",
        "resolved_config.yaml",
        "environment.json",
        "metrics.jsonl",
        "stdout.log",
        "stderr.log",
        "samples",
    }
    if {path.name for path in context.run_dir.iterdir()} != expected_names:
        raise EvaluationError("existing generation directory has an unexpected artifact layout")
    if {path.name for path in (context.run_dir / "samples").iterdir()} != {"generations.jsonl"}:
        raise EvaluationError("existing generation samples directory has unexpected artifacts")
    contract = _evaluation_contract(config, run_id=run_id, model_id=model_id, seed=seed, problems=problems)
    resolved_path = context.run_dir / "resolved_config.yaml"
    environment_path = context.run_dir / "environment.json"
    if dict(_load_yaml_mapping(resolved_path)) != contract:
        raise EvaluationError("generation resolved config identity mismatch")
    metadata = _read_json_object(context.run_json_path, artifact_name="generation run.json")
    expected_identity: dict[str, object] = {
        "schema_version": _BUNDLE_VERSION,
        "artifact_type": _BUNDLE_TYPE,
        "run_id": run_id,
        "model_id": model_id,
        "model_revision": config.model_revision,
        "checkpoint": config.checkpoint,
        "dataset_hash": dataset_hash(problems),
        "evaluation_contract_sha256": _evaluation_contract_sha256(
            config, run_id=run_id, model_id=model_id, seed=seed, problems=problems
        ),
        "piston_config_sha256": _file_sha(config.piston_config),
        "seed": seed,
        "total_problems": len(problems),
        "ordered_problem_ids_sha256": _ordered_ids_sha(problems),
        "resolved_config_sha256": _file_sha(resolved_path),
        "environment_sha256": _file_sha(environment_path),
        "gpu_hours_semantics": _GPU_HOURS_SEMANTICS,
    }
    for key, expected in expected_identity.items():
        if metadata.get(key) != expected:
            raise EvaluationError(f"generation run identity mismatch for {key}")
    status = metadata.get("status")
    if status not in {"running", "failed", "completed"}:
        raise EvaluationError("generation run status is invalid")
    environment = _read_json_object(environment_path, artifact_name="generation environment.json")
    for key in ("project_commit", "open_r1_commit", "dependency_lock_hash"):
        if environment.get(key) != metadata.get(key):
            raise EvaluationError(f"generation environment identity mismatch for {key}")
    current = collect_environment()
    for key in (
        "project_commit",
        "open_r1_commit",
        "dependency_lock_hash",
        "cuda_version",
        "gpu_name",
        "gpu_count",
    ):
        if current.get(key) != environment.get(key):
            raise EvaluationError(f"current generation environment mismatch for {key}")
    records = load_generation_bundle_records(context.records_path)
    _validate_rows(records, run_id=run_id, model_id=model_id, config=config, seed=seed, problems=problems)
    completed = metadata.get("completed_records")
    if isinstance(completed, bool) or not isinstance(completed, int) or not 0 <= completed <= len(records):
        raise EvaluationError("generation completed_records is invalid for persisted rows")
    gpu_count_used = metadata.get("gpu_count_used")
    if isinstance(gpu_count_used, bool) or not isinstance(gpu_count_used, int) or gpu_count_used < 0:
        raise EvaluationError("generation gpu_count_used is invalid")
    stored_gpu_hours = _finite_nonnegative(metadata.get("gpu_hours"), "generation gpu_hours")
    exact_gpu_hours = _gpu_hours(records, gpu_count_used)
    if status in {"failed", "completed"} and (
        completed != len(records) or not math.isclose(stored_gpu_hours, exact_gpu_hours, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise EvaluationError("terminal generation accounting does not match persisted rows")
    if status == "completed":
        if len(records) != len(problems) or metadata.get("records_sha256") != _file_sha(context.records_path):
            raise EvaluationError("completed generation bundle is incomplete or has a hash mismatch")
        if not isinstance(metadata.get("end_time"), str):
            raise EvaluationError("completed generation bundle requires end_time")
    elif metadata.get("records_sha256") is not None or metadata.get("end_time") is not None:
        raise EvaluationError("incomplete generation bundle must not have final hash/end_time")
    return context, records


def run_generation_bundle(
    *,
    config: EvaluationConfig,
    model_id: str,
    generator: CompletionGenerator,
    run_id: str,
    output_root: Path,
    seed: int,
) -> GenerationBundleSummary:
    """Generate an exact-prefix bundle without constructing or contacting Piston."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise EvaluationError("seed must be an integer")
    model_id = _nonempty(model_id, "model_id")
    _validate_run_id(run_id)
    problems = load_evaluation_problems(config)
    run_dir = output_root / "generation" / run_id
    if run_dir.exists():
        if not run_dir.is_dir():
            raise EvaluationError("generation run path exists but is not a directory")
        context, records = _resume_bundle(
            output_root=output_root,
            run_id=run_id,
            config=config,
            model_id=model_id,
            seed=seed,
            problems=problems,
        )
    else:
        context = _new_bundle(
            output_root=output_root,
            run_id=run_id,
            config=config,
            model_id=model_id,
            seed=seed,
            problems=problems,
        )
        records = []
    if len(records) == len(problems):
        return GenerationBundleSummary(
            run_id=run_id,
            total_problems=len(problems),
            completed_before_run=len(records),
            generated_this_run=0,
            run_dir=context.run_dir,
            records_path=context.records_path,
        )
    _update_bundle_status(context, "running")
    generated = 0
    dataset_identity = dataset_hash(problems)
    contract_identity = _evaluation_contract_sha256(
        config, run_id=run_id, model_id=model_id, seed=seed, problems=problems
    )
    try:
        for index, problem in enumerate(problems[len(records) :], start=len(records) + 1):
            prompt = build_evaluation_prompt(problem)
            result = generator.generate(prompt, seed=seed)
            record = GenerationBundleRecord(
                run_id=run_id,
                model_id=model_id,
                checkpoint=config.checkpoint,
                dataset_hash=dataset_identity,
                evaluation_contract_sha256=contract_identity,
                problem_id=problem.problem_id,
                prompt_hash=prompt_hash(prompt),
                completion=result.completion,
                completion_tokens=result.completion_tokens,
                generation_latency_ms=result.latency_ms,
                hit_max_new_tokens=result.hit_max_new_tokens,
            )
            _append_jsonl(context.records_path, generation_bundle_record_to_mapping(record))
            _append_jsonl(
                context.metrics_path,
                {
                    "problem_id": record.problem_id,
                    "generation_latency_ms": record.generation_latency_ms,
                    "completion_tokens": record.completion_tokens,
                    "hit_max_new_tokens": record.hit_max_new_tokens,
                    "completed": index,
                },
            )
            generated += 1
    except BaseException as error:
        _update_bundle_status(context, "failed")
        with context.stderr_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{type(error).__name__}\n")
        raise
    _update_bundle_status(context, "completed")
    with context.stdout_path.open("a", encoding="utf-8") as handle:
        handle.write(f"completed={len(problems)} generated_this_run={generated}\n")
    return GenerationBundleSummary(
        run_id=run_id,
        total_problems=len(problems),
        completed_before_run=len(records),
        generated_this_run=generated,
        run_dir=context.run_dir,
        records_path=context.records_path,
    )


def load_generation_bundle_source(run_dir: Path) -> GenerationBundleSource:
    """Read the minimal completed source identity without requiring model files locally."""
    try:
        resolved_dir = run_dir.resolve(strict=True)
    except OSError as error:
        raise EvaluationError(f"generation bundle path is unavailable: {type(error).__name__}") from None
    metadata = _read_json_object(resolved_dir / "run.json", artifact_name="generation run.json")
    if metadata.get("schema_version") != _BUNDLE_VERSION or metadata.get("artifact_type") != _BUNDLE_TYPE:
        raise EvaluationError("generation bundle schema identity is invalid")
    if metadata.get("status") != "completed":
        raise EvaluationError("generation bundle must be completed before verification")
    model_revision = metadata.get("model_revision")
    if model_revision is not None and (not isinstance(model_revision, str) or not model_revision.strip()):
        raise EvaluationError("generation model_revision is invalid")
    seed = metadata.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise EvaluationError("generation seed must be an integer")
    return GenerationBundleSource(
        run_id=_nonempty(metadata.get("run_id"), "generation run_id"),
        model_id=_nonempty(metadata.get("model_id"), "generation model_id"),
        model_revision=model_revision,
        checkpoint=_nonempty(metadata.get("checkpoint"), "generation checkpoint"),
        seed=seed,
    )


def load_completed_generation_bundle(
    run_dir: Path,
    *,
    config: EvaluationConfig,
    problems: Sequence[CodeProblem],
    seed: int,
    require_current_code_identity: bool = True,
) -> tuple[GenerationBundleIdentity, tuple[GenerationBundleRecord, ...]]:
    """Load a completed transferred bundle and bind it to local data/config/code identity."""
    try:
        resolved_dir = run_dir.resolve(strict=True)
    except OSError as error:
        raise EvaluationError(f"generation bundle path is unavailable: {type(error).__name__}") from None
    if not resolved_dir.is_dir():
        raise EvaluationError("generation bundle path must be a directory")
    expected_names = {
        "run.json",
        "resolved_config.yaml",
        "environment.json",
        "metrics.jsonl",
        "stdout.log",
        "stderr.log",
        "samples",
    }
    if {path.name for path in resolved_dir.iterdir()} != expected_names:
        raise EvaluationError("generation bundle has an unexpected artifact layout")
    if {path.name for path in (resolved_dir / "samples").iterdir()} != {"generations.jsonl"}:
        raise EvaluationError("generation bundle samples directory has unexpected artifacts")
    source = load_generation_bundle_source(resolved_dir)
    if source.seed != seed:
        raise EvaluationError("generation bundle seed does not match verification seed")
    if config.model_revision != source.model_revision or config.checkpoint != source.checkpoint:
        raise EvaluationError("generation model revision/checkpoint does not match verification config")
    metadata = _read_json_object(resolved_dir / "run.json", artifact_name="generation run.json")
    contract = _evaluation_contract(
        config, run_id=source.run_id, model_id=source.model_id, seed=seed, problems=problems
    )
    contract_sha = _evaluation_contract_sha256(
        config, run_id=source.run_id, model_id=source.model_id, seed=seed, problems=problems
    )
    resolved_path = resolved_dir / "resolved_config.yaml"
    environment_path = resolved_dir / "environment.json"
    expected_identity: dict[str, object] = {
        "dataset_hash": dataset_hash(problems),
        "evaluation_contract_sha256": contract_sha,
        "piston_config_sha256": _file_sha(config.piston_config),
        "seed": seed,
        "total_problems": len(problems),
        "completed_records": len(problems),
        "ordered_problem_ids_sha256": _ordered_ids_sha(problems),
        "resolved_config_sha256": _file_sha(resolved_path),
        "environment_sha256": _file_sha(environment_path),
        "gpu_hours_semantics": _GPU_HOURS_SEMANTICS,
    }
    for key, expected in expected_identity.items():
        if metadata.get(key) != expected:
            raise EvaluationError(f"generation bundle identity mismatch for {key}")
    if dict(_load_yaml_mapping(resolved_path)) != contract:
        raise EvaluationError("generation bundle resolved config does not match verification contract")
    records_path = resolved_dir / "samples" / "generations.jsonl"
    records = tuple(load_generation_bundle_records(records_path))
    if len(records) != len(problems):
        raise EvaluationError("completed generation bundle does not contain the full split")
    _validate_rows(
        records,
        run_id=source.run_id,
        model_id=source.model_id,
        config=config,
        seed=seed,
        problems=problems,
    )
    records_sha = _sha(metadata.get("records_sha256"), "generation records_sha256")
    if records_sha != _file_sha(records_path):
        raise EvaluationError("generation bundle records hash mismatch")
    environment = _read_json_object(environment_path, artifact_name="generation environment.json")
    for key in ("project_commit", "open_r1_commit", "dependency_lock_hash"):
        if environment.get(key) != metadata.get(key):
            raise EvaluationError(f"generation environment identity mismatch for {key}")
    if require_current_code_identity:
        current = collect_environment()
        for key in ("project_commit", "open_r1_commit", "dependency_lock_hash"):
            if current.get(key) != environment.get(key):
                raise EvaluationError(f"verification code identity does not match generation bundle for {key}")
    gpu_count_used = metadata.get("gpu_count_used")
    if isinstance(gpu_count_used, bool) or not isinstance(gpu_count_used, int) or gpu_count_used < 0:
        raise EvaluationError("generation gpu_count_used is invalid")
    gpu_hours = _finite_nonnegative(metadata.get("gpu_hours"), "generation gpu_hours")
    if not math.isclose(gpu_hours, _gpu_hours(records, gpu_count_used), rel_tol=0.0, abs_tol=1e-12):
        raise EvaluationError("generation gpu_hours does not match persisted latency")
    start_time = _nonempty(metadata.get("start_time"), "generation start_time")
    end_time = _nonempty(metadata.get("end_time"), "generation end_time")
    identity = GenerationBundleIdentity(
        run_dir=resolved_dir,
        run_id=source.run_id,
        model_id=source.model_id,
        model_revision=source.model_revision,
        checkpoint=source.checkpoint,
        dataset_hash=cast(str, expected_identity["dataset_hash"]),
        evaluation_contract_sha256=contract_sha,
        piston_config_sha256=cast(str, expected_identity["piston_config_sha256"]),
        seed=seed,
        total_problems=len(problems),
        records_sha256=records_sha,
        ordered_problem_ids_sha256=cast(str, expected_identity["ordered_problem_ids_sha256"]),
        environment_sha256=cast(str, expected_identity["environment_sha256"]),
        gpu_count_used=gpu_count_used,
        gpu_hours=gpu_hours,
        start_time=start_time,
        end_time=end_time,
    )
    return identity, records


def _bind_generation_provenance(
    run_dir: Path,
    *,
    identity: GenerationBundleIdentity,
    workers: int,
    fresh: bool,
) -> None:
    metadata = dict(_read_json_object(run_dir / "run.json", artifact_name="run.json"))
    expected = {
        "generation_bundle_schema_version": _BUNDLE_VERSION,
        "generation_bundle_run_id": identity.run_id,
        "generation_bundle_records_sha256": identity.records_sha256,
        "generation_bundle_contract_sha256": identity.evaluation_contract_sha256,
        "generation_gpu_hours": identity.gpu_hours,
        "generation_bundle_ordered_problem_ids_sha256": identity.ordered_problem_ids_sha256,
        "generation_environment_sha256": identity.environment_sha256,
        "generation_start_time": identity.start_time,
        "generation_end_time": identity.end_time,
        "verification_workers": workers,
    }
    if fresh:
        metadata["command"] = "code-verifier verify-eval"
        metadata["gpu_count_used"] = identity.gpu_count_used
        for key, value in expected.items():
            metadata[key] = value
        _write_json(run_dir / "run.json", metadata)
        return
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise EvaluationError(f"existing verification provenance mismatch for {key}")
    if (
        metadata.get("command") != "code-verifier verify-eval"
        or metadata.get("gpu_count_used") != identity.gpu_count_used
    ):
        raise EvaluationError("existing verification command/GPU-hour provenance mismatch")


def _verify_one(
    *,
    problem: CodeProblem,
    generation: GenerationBundleRecord,
    run_id: str,
    config: EvaluationConfig,
    evaluation_config_hash_value: str,
    executor_factory: Callable[[], CodeExecutor],
) -> EvaluationRecord:
    prompt = build_evaluation_prompt(problem)
    if prompt_hash(prompt) != generation.prompt_hash:
        raise EvaluationError("generation prompt hash drifted before verification")
    result = GenerationResult(
        completion=generation.completion,
        completion_tokens=generation.completion_tokens,
        latency_ms=generation.generation_latency_ms,
        hit_max_new_tokens=generation.hit_max_new_tokens,
    )
    return evaluate_completion(
        run_id=run_id,
        model_id=generation.model_id,
        checkpoint=config.checkpoint,
        dataset_hash_value=generation.dataset_hash,
        config_hash=evaluation_config_hash_value,
        problem=problem,
        prompt=prompt,
        generation=result,
        executor=executor_factory(),
    )


def run_verification_from_generation_bundle(
    *,
    config: EvaluationConfig,
    generation_run_dir: Path,
    executor_factory: Callable[[], CodeExecutor],
    run_id: str,
    output_root: Path,
    seed: int,
    workers: int = 4,
) -> EvaluationVerificationSummary:
    """Verify a completed bundle with bounded concurrency and exact-prefix result ordering."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise EvaluationError("seed must be an integer")
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 32:
        raise EvaluationError("verification workers must be an integer between 1 and 32")
    _validate_run_id(run_id)
    problems = load_evaluation_problems(config)
    identity, generations = load_completed_generation_bundle(
        generation_run_dir,
        config=config,
        problems=problems,
        seed=seed,
        require_current_code_identity=True,
    )
    if run_id != identity.run_id:
        raise EvaluationError("verification run_id must equal generation run_id")
    target = output_root / "evaluation" / run_id
    fresh = not target.exists()
    run_dir, completed_records = initialize_or_resume_run(
        output_root=output_root,
        run_id=run_id,
        model_id=identity.model_id,
        seed=seed,
        config=config,
        problems=problems,
    )
    _bind_generation_provenance(run_dir, identity=identity, workers=workers, fresh=fresh)
    final_config_hash = evaluation_config_hash(config, model_id=identity.model_id, seed=seed)
    context = _run_context(output_root, run_id, completed=len(completed_records))
    if len(completed_records) == len(problems):
        return EvaluationVerificationSummary(
            run_id=run_id,
            total_problems=len(problems),
            completed_before_run=len(completed_records),
            verified_this_run=0,
            results_path=context.results_path,
            generation_records_sha256=identity.records_sha256,
        )
    _update_run_status(context, "running")
    verified = 0
    futures: list[Future[EvaluationRecord]] = []
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="evaluation-piston")
    try:
        start = len(completed_records)
        for chunk_start in range(start, len(problems), workers):
            chunk_end = min(chunk_start + workers, len(problems))
            futures = [
                pool.submit(
                    _verify_one,
                    problem=problems[index],
                    generation=generations[index],
                    run_id=run_id,
                    config=config,
                    evaluation_config_hash_value=final_config_hash,
                    executor_factory=executor_factory,
                )
                for index in range(chunk_start, chunk_end)
            ]
            for offset, future in enumerate(futures):
                record = future.result()
                completed = chunk_start + offset + 1
                append_evaluation_record(context.results_path, record)
                _append_progress(context, record, completed=completed)
                verified += 1
    except BaseException as error:
        for future in futures:
            future.cancel()
        _update_run_status(context, "failed")
        with context.stderr_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{type(error).__name__}\n")
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    _update_run_status(context, "completed")
    with context.stdout_path.open("a", encoding="utf-8") as handle:
        handle.write(f"completed={len(problems)} verified_this_run={verified}\n")
    return EvaluationVerificationSummary(
        run_id=run_id,
        total_problems=len(problems),
        completed_before_run=len(completed_records),
        verified_this_run=verified,
        results_path=context.results_path,
        generation_records_sha256=identity.records_sha256,
    )
