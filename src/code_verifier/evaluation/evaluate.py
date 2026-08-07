"""Strict per-problem pass@1 evaluation records and run contracts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

import yaml

from code_verifier.config import load_yaml_mapping
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.prepare import check_prepared_data, load_hf_dataset
from code_verifier.data.schema import CodeProblem, problem_to_mapping, test_case_to_mapping
from code_verifier.environment import collect_environment
from code_verifier.evaluation.generate import (
    CompletionGenerator,
    GenerationConfig,
    GenerationError,
    GenerationResult,
    build_evaluation_prompt,
)
from code_verifier.execution.base import CodeExecutor, ExecutionStatus
from code_verifier.parsing import extract_python_code
from code_verifier.verification import VerificationContractError, verify_completion


class EvaluationError(RuntimeError):
    """Raised when an evaluation run violates configuration, artifact, or resume contracts."""


@dataclass(frozen=True)
class EvaluationConfig:
    """Resolved strict configuration for deterministic pass@1 evaluation."""

    dataset_dir: Path
    split: Literal["validation", "test"]
    piston_config: Path
    model_revision: str | None
    checkpoint: str
    device: str
    generation: GenerationConfig


@dataclass(frozen=True)
class EvaluationRecord:
    """One strict, JSON-safe per-problem evaluation row."""

    run_id: str
    model_id: str
    checkpoint: str
    dataset_hash: str
    config_hash: str
    problem_id: str
    prompt_hash: str
    completion: str
    extracted_code: str
    parse_success: bool
    target_function_found: bool
    visible_pass_rate: float
    train_hidden_pass_rate: float
    eval_hidden_pass_rate: float
    execution_status: str
    visible_execution_status: str
    train_hidden_execution_status: str
    eval_hidden_execution_status: str
    visible_failure_counts: dict[str, int]
    train_hidden_failure_counts: dict[str, int]
    eval_hidden_failure_counts: dict[str, int]
    parse_error_type: str | None
    runtime_ms: float
    generation_latency_ms: float
    completion_tokens: int
    error_category_auto: str


@dataclass(frozen=True)
class EvaluationRunSummary:
    """Non-sensitive summary returned after one new or resumed run."""

    run_id: str
    total_problems: int
    completed_before_run: int
    generated_this_run: int
    results_path: Path


_CONFIG_FIELDS = {
    "dataset_dir",
    "split",
    "piston_config",
    "model_revision",
    "checkpoint",
    "device",
    "generation",
}
_GENERATION_FIELDS = {"do_sample", "temperature", "top_p", "max_new_tokens"}
_RECORD_FIELDS = {
    "run_id",
    "model_id",
    "checkpoint",
    "dataset_hash",
    "config_hash",
    "problem_id",
    "prompt_hash",
    "completion",
    "extracted_code",
    "parse_success",
    "target_function_found",
    "visible_pass_rate",
    "train_hidden_pass_rate",
    "eval_hidden_pass_rate",
    "execution_status",
    "visible_execution_status",
    "train_hidden_execution_status",
    "eval_hidden_execution_status",
    "visible_failure_counts",
    "train_hidden_failure_counts",
    "eval_hidden_failure_counts",
    "parse_error_type",
    "runtime_ms",
    "generation_latency_ms",
    "completion_tokens",
    "error_category_auto",
}
_ALLOWED_STATUSES = {status.value for status in ExecutionStatus}
_ALLOWED_FAILURE_STATUSES = _ALLOWED_STATUSES - {ExecutionStatus.PASSED.value}


def _exact_mapping(value: object, expected: set[str], *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EvaluationError(f"{field_name} must be a mapping with string keys")
    keys = set(value)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise EvaluationError(f"{field_name} is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise EvaluationError(f"{field_name} contains unknown field(s): {', '.join(sorted(unknown))}")
    return cast(Mapping[str, object], value)


def _utf8_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise EvaluationError(f"{field_name} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise EvaluationError(f"{field_name} must contain valid UTF-8 text") from None
    return value


def _nonempty_string(value: object, *, field_name: str) -> str:
    text = _utf8_string(value, field_name=field_name)
    if not text.strip():
        raise EvaluationError(f"{field_name} must be a non-empty string")
    return text


def _resolved_path(value: object, *, field_name: str) -> Path:
    text = _nonempty_string(value, field_name=field_name)
    path = Path(text)
    return path if path.is_absolute() else Path.cwd() / path


def evaluation_config_from_mapping(value: object) -> EvaluationConfig:
    """Parse one exact evaluation config mapping and resolve paths from the current working directory."""
    root = _exact_mapping(value, _CONFIG_FIELDS, field_name="evaluation config")
    generation_mapping = _exact_mapping(root["generation"], _GENERATION_FIELDS, field_name="generation")
    split = root["split"]
    if split not in {"validation", "test"}:
        raise EvaluationError("split must be validation or test")
    revision = root["model_revision"]
    if revision is not None:
        revision = _nonempty_string(revision, field_name="model_revision")
    device = _nonempty_string(root["device"], field_name="device")
    if device not in {"cpu", "cuda", "auto"}:
        raise EvaluationError("device must be cpu, cuda, or auto")
    try:
        generation = GenerationConfig(
            do_sample=generation_mapping["do_sample"],  # type: ignore[arg-type]
            temperature=generation_mapping["temperature"],  # type: ignore[arg-type]
            top_p=generation_mapping["top_p"],  # type: ignore[arg-type]
            max_new_tokens=generation_mapping["max_new_tokens"],  # type: ignore[arg-type]
        )
    except GenerationError as error:
        raise EvaluationError(str(error)) from None
    return EvaluationConfig(
        dataset_dir=_resolved_path(root["dataset_dir"], field_name="dataset_dir"),
        split=cast(Literal["validation", "test"], split),
        piston_config=_resolved_path(root["piston_config"], field_name="piston_config"),
        model_revision=revision,
        checkpoint=_nonempty_string(root["checkpoint"], field_name="checkpoint"),
        device=device,
        generation=generation,
    )


def load_evaluation_config(path: Path) -> EvaluationConfig:
    """Load and strictly validate one deterministic pass@1 YAML configuration."""
    return evaluation_config_from_mapping(load_yaml_mapping(path))


def _finite_rate(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"{field_name} must be a finite number between 0 and 1")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise EvaluationError(f"{field_name} must be a finite number between 0 and 1")
    return number


def _finite_nonnegative(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"{field_name} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise EvaluationError(f"{field_name} must be a finite non-negative number")
    return number


def _failure_counts(value: object, *, field_name: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EvaluationError(f"{field_name} must be a status-to-count mapping")
    result: dict[str, int] = {}
    for key, raw_count in value.items():
        if key not in _ALLOWED_FAILURE_STATUSES:
            raise EvaluationError(f"{field_name} contains an unsupported failure status")
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count <= 0:
            raise EvaluationError(f"{field_name} counts must be positive integers")
        result[key] = raw_count
    return dict(sorted(result.items()))


def _status(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or value not in _ALLOWED_STATUSES:
        raise EvaluationError(f"{field_name} must be a known execution status")
    return value


def _record_from_fields(mapping: Mapping[str, object]) -> EvaluationRecord:
    parse_success = mapping["parse_success"]
    target_function_found = mapping["target_function_found"]
    if not isinstance(parse_success, bool) or not isinstance(target_function_found, bool):
        raise EvaluationError("parse_success and target_function_found must be booleans")
    if target_function_found is not parse_success:
        raise EvaluationError("target_function_found must equal parse_success for the current parser contract")
    parse_error_type = mapping["parse_error_type"]
    if parse_success:
        if parse_error_type is not None:
            raise EvaluationError("parse_success records must have null parse_error_type")
    else:
        parse_error_type = _nonempty_string(parse_error_type, field_name="parse_error_type")
    completion_tokens = mapping["completion_tokens"]
    if isinstance(completion_tokens, bool) or not isinstance(completion_tokens, int) or completion_tokens < 0:
        raise EvaluationError("completion_tokens must be a non-negative integer")
    execution_status = _status(mapping["execution_status"], field_name="execution_status")
    eval_status = _status(mapping["eval_hidden_execution_status"], field_name="eval_hidden_execution_status")
    if execution_status != eval_status:
        raise EvaluationError("execution_status must equal eval_hidden_execution_status")
    return EvaluationRecord(
        run_id=_nonempty_string(mapping["run_id"], field_name="run_id"),
        model_id=_nonempty_string(mapping["model_id"], field_name="model_id"),
        checkpoint=_nonempty_string(mapping["checkpoint"], field_name="checkpoint"),
        dataset_hash=_nonempty_string(mapping["dataset_hash"], field_name="dataset_hash"),
        config_hash=_nonempty_string(mapping["config_hash"], field_name="config_hash"),
        problem_id=_nonempty_string(mapping["problem_id"], field_name="problem_id"),
        prompt_hash=_nonempty_string(mapping["prompt_hash"], field_name="prompt_hash"),
        completion=_utf8_string(mapping["completion"], field_name="completion"),
        extracted_code=_utf8_string(mapping["extracted_code"], field_name="extracted_code"),
        parse_success=parse_success,
        target_function_found=target_function_found,
        visible_pass_rate=_finite_rate(mapping["visible_pass_rate"], field_name="visible_pass_rate"),
        train_hidden_pass_rate=_finite_rate(mapping["train_hidden_pass_rate"], field_name="train_hidden_pass_rate"),
        eval_hidden_pass_rate=_finite_rate(mapping["eval_hidden_pass_rate"], field_name="eval_hidden_pass_rate"),
        execution_status=execution_status,
        visible_execution_status=_status(mapping["visible_execution_status"], field_name="visible_execution_status"),
        train_hidden_execution_status=_status(
            mapping["train_hidden_execution_status"], field_name="train_hidden_execution_status"
        ),
        eval_hidden_execution_status=eval_status,
        visible_failure_counts=_failure_counts(mapping["visible_failure_counts"], field_name="visible_failure_counts"),
        train_hidden_failure_counts=_failure_counts(
            mapping["train_hidden_failure_counts"], field_name="train_hidden_failure_counts"
        ),
        eval_hidden_failure_counts=_failure_counts(
            mapping["eval_hidden_failure_counts"], field_name="eval_hidden_failure_counts"
        ),
        parse_error_type=parse_error_type,
        runtime_ms=_finite_nonnegative(mapping["runtime_ms"], field_name="runtime_ms"),
        generation_latency_ms=_finite_nonnegative(
            mapping["generation_latency_ms"], field_name="generation_latency_ms"
        ),
        completion_tokens=completion_tokens,
        error_category_auto=_nonempty_string(mapping["error_category_auto"], field_name="error_category_auto"),
    )


def evaluation_record_from_mapping(value: object) -> EvaluationRecord:
    """Parse one exact serialized row for strict resume validation."""
    mapping = _exact_mapping(value, _RECORD_FIELDS, field_name="evaluation record")
    return _record_from_fields(mapping)


def evaluation_record_to_mapping(record: EvaluationRecord) -> dict[str, object]:
    """Return an exact JSON-safe mapping without tests, metadata, or executor output payloads."""
    mapping = dict(record.__dict__)
    mapping["visible_failure_counts"] = dict(record.visible_failure_counts)
    mapping["train_hidden_failure_counts"] = dict(record.train_hidden_failure_counts)
    mapping["eval_hidden_failure_counts"] = dict(record.eval_hidden_failure_counts)
    validated = _record_from_fields(mapping)
    if validated != record:
        raise EvaluationError("evaluation record contains values outside the serialized contract")
    return mapping


def dataset_hash(problems: Sequence[CodeProblem]) -> str:
    """Hash ordered canonical problem records, including all three test-layer identities."""
    payload = json.dumps(
        [problem_to_mapping(problem) for problem in problems],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prompt_hash(prompt: str) -> str:
    """Hash the exact UTF-8 prompt passed to a completion generator."""
    if not isinstance(prompt, str):
        raise EvaluationError("prompt must be a string")
    try:
        encoded = prompt.encode("utf-8")
    except UnicodeEncodeError:
        raise EvaluationError("prompt must contain valid UTF-8 text") from None
    return hashlib.sha256(encoded).hexdigest()


def classify_evaluation_error(
    *,
    parse_error_type: str | None,
    visible_pass_rate: float,
    eval_hidden_pass_rate: float,
    eval_hidden_status: ExecutionStatus,
) -> str:
    """Assign the stable coarse WP5-a automatic failure category."""
    if parse_error_type is not None:
        return f"parse_error:{parse_error_type}"
    if eval_hidden_status is ExecutionStatus.SANDBOX_ERROR:
        return "sandbox_failure"
    if eval_hidden_status is ExecutionStatus.TIMEOUT:
        return "timeout"
    if eval_hidden_status in {
        ExecutionStatus.RUNTIME_ERROR,
        ExecutionStatus.MEMORY_LIMIT,
        ExecutionStatus.OUTPUT_LIMIT,
        ExecutionStatus.SYNTAX_ERROR,
    }:
        return "runtime_error"
    if visible_pass_rate == 1.0 and eval_hidden_pass_rate < 1.0:
        return "visible_only_success"
    if visible_pass_rate - eval_hidden_pass_rate >= 0.5:
        return "large_public_eval_gap"
    if eval_hidden_status is ExecutionStatus.PASSED and eval_hidden_pass_rate == 1.0:
        return "passed"
    if eval_hidden_status is ExecutionStatus.WRONG_ANSWER or eval_hidden_pass_rate < 1.0:
        return "wrong_answer"
    return "other"


def _verification_runtime_ms(result: object) -> float:
    execution_result = getattr(result, "execution_result", None)
    return 0.0 if execution_result is None else float(execution_result.runtime_ms)


def evaluate_completion(
    *,
    run_id: str,
    model_id: str,
    checkpoint: str,
    dataset_hash_value: str,
    config_hash: str,
    problem: CodeProblem,
    prompt: str,
    generation: GenerationResult,
    executor: CodeExecutor,
) -> EvaluationRecord:
    """Verify one generated completion against each isolated test layer in fixed order."""
    parse_result = extract_python_code(generation.completion, expected_function_name=problem.function_name)
    metadata: dict[str, object] = {
        "time_limit_seconds": problem.metadata.time_limit_seconds,
        "memory_limit_mb": problem.metadata.memory_limit_mb,
    }
    visible_tests = [test_case_to_mapping(test_case) for test_case in problem.visible_tests]
    train_hidden_tests = [test_case_to_mapping(test_case) for test_case in problem.train_hidden_tests]
    eval_hidden_tests = [test_case_to_mapping(test_case) for test_case in problem.eval_hidden_tests]
    try:
        visible_result = verify_completion(
            generation.completion, visible_tests, problem.function_name, metadata, executor
        )
        train_result = verify_completion(
            generation.completion, train_hidden_tests, problem.function_name, metadata, executor
        )
        eval_result = verify_completion(
            generation.completion, eval_hidden_tests, problem.function_name, metadata, executor
        )
    except VerificationContractError as error:
        raise EvaluationError(f"verification contract failed: {type(error).__name__}") from None
    runtime_ms = sum(_verification_runtime_ms(result) for result in (visible_result, train_result, eval_result))
    category = classify_evaluation_error(
        parse_error_type=parse_result.error_type,
        visible_pass_rate=visible_result.pass_rate,
        eval_hidden_pass_rate=eval_result.pass_rate,
        eval_hidden_status=eval_result.status,
    )
    values: dict[str, object] = {
        "run_id": run_id,
        "model_id": model_id,
        "checkpoint": checkpoint,
        "dataset_hash": dataset_hash_value,
        "config_hash": config_hash,
        "problem_id": problem.problem_id,
        "prompt_hash": prompt_hash(prompt),
    }
    values.update(
        {
            "completion": generation.completion,
            "extracted_code": parse_result.code,
            "parse_success": parse_result.success,
            "target_function_found": parse_result.success,
            "visible_pass_rate": visible_result.pass_rate,
            "train_hidden_pass_rate": train_result.pass_rate,
            "eval_hidden_pass_rate": eval_result.pass_rate,
        }
    )
    values.update(
        {
            "execution_status": eval_result.status.value,
            "visible_execution_status": visible_result.status.value,
            "train_hidden_execution_status": train_result.status.value,
            "eval_hidden_execution_status": eval_result.status.value,
            "visible_failure_counts": dict(visible_result.failure_counts),
            "train_hidden_failure_counts": dict(train_result.failure_counts),
            "eval_hidden_failure_counts": dict(eval_result.failure_counts),
        }
    )
    values["parse_error_type"] = parse_result.error_type
    values["runtime_ms"] = runtime_ms
    values["generation_latency_ms"] = generation.latency_ms
    values["completion_tokens"] = generation.completion_tokens
    values["error_category_auto"] = category
    return evaluation_record_from_mapping(values)


def load_evaluation_problems(config: EvaluationConfig) -> list[CodeProblem]:
    """Load only a validated WP1 HF Dataset artifact and preserve canonical row order."""
    summary = check_prepared_data(config.dataset_dir)
    if summary.hf_dataset_dir is None:
        raise EvaluationError("prepared dataset does not contain the required hf_dataset artifact")
    problems = [problem for problem in load_hf_dataset(summary.hf_dataset_dir) if problem.split == config.split]
    if not problems:
        raise EvaluationError(f"prepared dataset contains no {config.split} problems")
    problem_ids = [problem.problem_id for problem in problems]
    if len(problem_ids) != len(set(problem_ids)):
        raise EvaluationError("evaluation split contains duplicate problem_id values")
    return problems


def _resolved_config_mapping(config: EvaluationConfig) -> dict[str, object]:
    return {
        "dataset_dir": str(config.dataset_dir),
        "split": config.split,
        "piston_config": str(config.piston_config),
        "model_revision": config.model_revision,
        "checkpoint": config.checkpoint,
        "device": config.device,
        "generation": asdict(config.generation),
    }


def evaluation_config_hash(config: EvaluationConfig, *, model_id: str, seed: int) -> str:
    """Hash resolved evaluation/model/seed settings plus the exact Piston YAML identity."""
    if not config.piston_config.is_file():
        raise EvaluationError(f"piston config does not exist: {config.piston_config}")
    piston_digest = hashlib.sha256(config.piston_config.read_bytes()).hexdigest()
    payload = {
        "evaluation": _resolved_config_mapping(config),
        "model_id": _nonempty_string(model_id, field_name="model_id"),
        "seed": seed,
        "piston_config_hash": piston_digest,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _RunContext:
    run_dir: Path
    results_path: Path
    metrics_path: Path
    stdout_path: Path
    stderr_path: Path
    run_json_path: Path
    completed: int


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
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


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n")


def _read_json_object(path: Path, *, artifact_name: str) -> Mapping[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise EvaluationError(f"{artifact_name} is unreadable or invalid: {type(error).__name__}") from None
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EvaluationError(f"{artifact_name} must contain one JSON object")
    return cast(Mapping[str, object], value)


def _append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", run_id) or ".." in run_id:
        raise EvaluationError(
            "run_id must use only A-Z, a-z, 0-9, dot, underscore, or hyphen and must not contain '..'"
        )
    return run_id


def _run_context(output_root: Path, run_id: str, *, completed: int) -> _RunContext:
    run_dir = output_root / "evaluation" / run_id
    return _RunContext(
        run_dir=run_dir,
        results_path=run_dir / "samples" / "results.jsonl",
        metrics_path=run_dir / "metrics.jsonl",
        stdout_path=run_dir / "stdout.log",
        stderr_path=run_dir / "stderr.log",
        run_json_path=run_dir / "run.json",
        completed=completed,
    )


def _populate_new_run_artifacts(
    *,
    output_root: Path,
    run_id: str,
    config: EvaluationConfig,
    model_id: str,
    seed: int,
    dataset_hash_value: str,
    config_hash_value: str,
) -> _RunContext:
    context = _run_context(output_root, run_id, completed=0)
    context.run_dir.mkdir(parents=True, exist_ok=False)
    context.results_path.parent.mkdir(parents=True, exist_ok=False)
    environment = collect_environment()
    resolved = _resolved_config_mapping(config)
    resolved["run_id"] = run_id
    resolved["model_id"] = model_id
    resolved["seed"] = seed
    run_metadata: dict[str, object] = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_commit": environment["project_commit"],
        "open_r1_commit": environment["open_r1_commit"],
        "model_id": model_id,
        "model_revision": config.model_revision,
        "checkpoint": config.checkpoint,
        "dataset_hash": dataset_hash_value,
        "config_hash": config_hash_value,
        "seed": seed,
        "command": "code-verifier evaluate",
        "status": "running",
        "dependency_identity_source": "uv.lock" if Path("uv.lock").is_file() else "pyproject+installed-versions",
        "dependency_lock_hash": environment["dependency_lock_hash"],
    }
    _atomic_write_text(
        context.run_dir / "resolved_config.yaml",
        yaml.safe_dump(resolved, sort_keys=True, allow_unicode=True),
    )
    _write_json(context.run_dir / "environment.json", environment)
    _write_json(context.run_json_path, run_metadata)
    for path in (context.metrics_path, context.stdout_path, context.stderr_path, context.results_path):
        path.touch(exist_ok=False)
    return context


def _new_run_artifacts(
    *,
    output_root: Path,
    run_id: str,
    config: EvaluationConfig,
    model_id: str,
    seed: int,
    dataset_hash_value: str,
    config_hash_value: str,
) -> _RunContext:
    run_dir = output_root / "evaluation" / run_id
    try:
        return _populate_new_run_artifacts(
            output_root=output_root,
            run_id=run_id,
            config=config,
            model_id=model_id,
            seed=seed,
            dataset_hash_value=dataset_hash_value,
            config_hash_value=config_hash_value,
        )
    except Exception:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise


def _resume_run_artifacts(
    *,
    output_root: Path,
    run_id: str,
    config: EvaluationConfig,
    model_id: str,
    seed: int,
    dataset_hash_value: str,
    config_hash_value: str,
    problems: Sequence[CodeProblem],
) -> tuple[_RunContext, list[EvaluationRecord]]:
    context = _run_context(output_root, run_id, completed=0)
    expected_names = {
        "resolved_config.yaml",
        "environment.json",
        "run.json",
        "metrics.jsonl",
        "stdout.log",
        "stderr.log",
        "samples",
    }
    if {path.name for path in context.run_dir.iterdir()} != expected_names:
        raise EvaluationError("existing run directory does not match the strict WP5-a artifact layout")
    if {path.name for path in (context.run_dir / "samples").iterdir()} != {"results.jsonl"}:
        raise EvaluationError("existing samples directory contains unexpected artifacts")
    resolved_expected = _resolved_config_mapping(config)
    resolved_expected["run_id"] = run_id
    resolved_expected["model_id"] = model_id
    resolved_expected["seed"] = seed
    try:
        resolved_actual = yaml.safe_load((context.run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise EvaluationError(f"resolved_config.yaml is unreadable or invalid: {type(error).__name__}") from None
    if resolved_actual != resolved_expected:
        raise EvaluationError("resolved_config.yaml identity does not match the requested run")
    run_metadata = _read_json_object(context.run_json_path, artifact_name="run.json")
    expected_identity: dict[str, object] = {
        "run_id": run_id,
        "model_id": model_id,
        "model_revision": config.model_revision,
        "checkpoint": config.checkpoint,
        "dataset_hash": dataset_hash_value,
        "config_hash": config_hash_value,
        "seed": seed,
    }
    for key, expected in expected_identity.items():
        if run_metadata.get(key) != expected:
            raise EvaluationError(f"run.json identity mismatch for {key}")
    environment = _read_json_object(context.run_dir / "environment.json", artifact_name="environment.json")
    for key in ("project_commit", "open_r1_commit", "dependency_lock_hash"):
        if environment.get(key) != run_metadata.get(key):
            raise EvaluationError(f"environment.json identity mismatch for {key}")
    current_environment = collect_environment()
    for key in (
        "project_commit",
        "open_r1_commit",
        "dependency_lock_hash",
        "cuda_version",
        "gpu_name",
        "gpu_count",
    ):
        if environment.get(key) != current_environment.get(key):
            raise EvaluationError(f"current environment identity mismatch for {key}")
    try:
        lines = context.results_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise EvaluationError(f"results.jsonl is unreadable: {type(error).__name__}") from None
    if len(lines) > len(problems):
        raise EvaluationError("results.jsonl contains more rows than the selected evaluation split")
    records: list[EvaluationRecord] = []
    for index, line in enumerate(lines):
        if not line.strip():
            raise EvaluationError("results.jsonl must not contain blank rows")
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise EvaluationError(f"results.jsonl row {index + 1} is invalid: {type(error).__name__}") from None
        record = evaluation_record_from_mapping(value)
        records.append(record)
        problem = problems[index]
        expected_prompt_hash = prompt_hash(build_evaluation_prompt(problem))
        row_identity = {
            "run_id": record.run_id,
            "model_id": record.model_id,
            "checkpoint": record.checkpoint,
            "dataset_hash": record.dataset_hash,
            "config_hash": record.config_hash,
            "problem_id": record.problem_id,
            "prompt_hash": record.prompt_hash,
        }
        expected_row_identity = {
            "run_id": run_id,
            "model_id": model_id,
            "checkpoint": config.checkpoint,
            "dataset_hash": dataset_hash_value,
            "config_hash": config_hash_value,
            "problem_id": problem.problem_id,
            "prompt_hash": expected_prompt_hash,
        }
        if row_identity != expected_row_identity:
            raise EvaluationError(f"results.jsonl row {index + 1} is not the exact expected resume prefix")
    return _run_context(output_root, run_id, completed=len(lines)), records


def initialize_or_resume_run(
    *,
    output_root: Path,
    run_id: str,
    model_id: str,
    seed: int,
    config: EvaluationConfig,
    problems: Sequence[CodeProblem],
) -> tuple[Path, list[EvaluationRecord]]:
    """Create a fresh run or validate an existing exact-prefix resume and return completed records."""
    _validate_run_id(run_id)
    dataset_hash_value = dataset_hash(problems)
    config_hash_value = evaluation_config_hash(config, model_id=model_id, seed=seed)
    run_dir = output_root / "evaluation" / run_id
    if run_dir.exists():
        if not run_dir.is_dir():
            raise EvaluationError("run path exists but is not a directory")
        context, records = _resume_run_artifacts(
            output_root=output_root,
            run_id=run_id,
            config=config,
            model_id=model_id,
            seed=seed,
            dataset_hash_value=dataset_hash_value,
            config_hash_value=config_hash_value,
            problems=problems,
        )
        return context.run_dir, records
    context = _new_run_artifacts(
        output_root=output_root,
        run_id=run_id,
        config=config,
        model_id=model_id,
        seed=seed,
        dataset_hash_value=dataset_hash_value,
        config_hash_value=config_hash_value,
    )
    return context.run_dir, []


def _update_run_status(context: _RunContext, status: Literal["running", "failed", "completed"]) -> None:
    metadata = dict(_read_json_object(context.run_json_path, artifact_name="run.json"))
    metadata["status"] = status
    _write_json(context.run_json_path, metadata)


def append_evaluation_record(path: Path, record: EvaluationRecord) -> None:
    """Durably append one strict evaluation record to a JSONL results path."""
    _append_jsonl(path, evaluation_record_to_mapping(record))


def _append_progress(context: _RunContext, record: EvaluationRecord, *, completed: int) -> None:
    """Append one completion/code-free progress event for a persisted evaluation record."""
    _append_jsonl(
        context.metrics_path,
        {
            "problem_id": record.problem_id,
            "execution_status": record.execution_status,
            "error_category_auto": record.error_category_auto,
            "runtime_ms": record.runtime_ms,
            "generation_latency_ms": record.generation_latency_ms,
            "completed": completed,
        },
    )


def run_pass1_evaluation(
    *,
    config: EvaluationConfig,
    model_id: str,
    generator: CompletionGenerator,
    executor: CodeExecutor,
    run_id: str,
    output_root: Path,
    seed: int,
) -> EvaluationRunSummary:
    """Run or strictly resume one deterministic pass@1 evaluation without aggregation."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise EvaluationError("seed must be an integer")
    model_id = _nonempty_string(model_id, field_name="model_id")
    problems = load_evaluation_problems(config)
    dataset_identity = dataset_hash(problems)
    config_identity = evaluation_config_hash(config, model_id=model_id, seed=seed)
    run_dir, completed_records = initialize_or_resume_run(
        output_root=output_root,
        run_id=run_id,
        model_id=model_id,
        seed=seed,
        config=config,
        problems=problems,
    )
    context = _run_context(output_root, run_id, completed=len(completed_records))
    if context.run_dir != run_dir:
        raise EvaluationError("initialized run directory does not match the requested run")
    _update_run_status(context, "running")
    generated = 0
    try:
        for index, problem in enumerate(problems[context.completed :], start=context.completed + 1):
            prompt = build_evaluation_prompt(problem)
            generation = generator.generate(prompt, seed=seed)
            record = evaluate_completion(
                run_id=run_id,
                model_id=model_id,
                checkpoint=config.checkpoint,
                dataset_hash_value=dataset_identity,
                config_hash=config_identity,
                problem=problem,
                prompt=prompt,
                generation=generation,
                executor=executor,
            )
            append_evaluation_record(context.results_path, record)
            _append_progress(context, record, completed=index)
            generated += 1
    except Exception as error:
        _update_run_status(context, "failed")
        with context.stderr_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{type(error).__name__}\n")
        raise
    _update_run_status(context, "completed")
    with context.stdout_path.open("a", encoding="utf-8") as handle:
        handle.write(f"completed={len(problems)} generated_this_run={generated}\n")
    return EvaluationRunSummary(
        run_id=run_id,
        total_problems=len(problems),
        completed_before_run=context.completed,
        generated_this_run=generated,
        results_path=context.results_path,
    )
