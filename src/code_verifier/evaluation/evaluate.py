"""Strict per-problem pass@1 evaluation records and run contracts."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.schema import CodeProblem, problem_to_mapping, test_case_to_mapping
from code_verifier.evaluation.generate import GenerationConfig, GenerationError, GenerationResult
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
