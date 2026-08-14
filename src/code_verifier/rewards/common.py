"""Shared reward input contracts, scoring, and component records."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import cast

from code_verifier.execution.base import CodeExecutor, ExecutionStatus
from code_verifier.verification import (
    VerificationContractError,
    VerificationResult,
    validate_verification_result,
    verify_completion,
)


class RewardContractError(ValueError):
    """Raised when reward callback inputs or computed components violate the public contract."""


def _batch_length(value: object, *, field_name: str) -> int:
    """Return the length of one non-string batch sequence or raise a sanitized contract error."""
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
        raise RewardContractError(f"{field_name} must be a non-string sequence")
    return len(value)


def _extract_completion_text(item: object) -> str:
    """Extract exact completion text from a raw string or pinned Open-R1 chat-style item."""
    if isinstance(item, str):
        return item
    if isinstance(item, bytes | bytearray | Mapping) or not isinstance(item, Sequence) or not item:
        raise RewardContractError("completion item must be a string or non-empty chat sequence")
    last_message = item[-1]
    if not isinstance(last_message, Mapping):
        raise RewardContractError("chat completion must end with a message mapping")
    content = last_message.get("content")
    if not isinstance(content, str):
        raise RewardContractError("chat completion final content must be a string")
    return content


def _completion_texts(completions: object) -> list[str]:
    """Validate and extract every completion before any verifier/executor side effect."""
    _batch_length(completions, field_name="completions")
    batch = cast(Sequence[object], completions)
    return [_extract_completion_text(item) for item in batch]


def _validate_batch_alignment(
    completions: object,
    tests_batch: object,
    function_names: object,
    metadata_batch: object,
) -> int:
    """Require four equal batch lengths without zip-based truncation."""
    lengths = {
        "completions": _batch_length(completions, field_name="completions"),
        "tests_batch": _batch_length(tests_batch, field_name="tests_batch"),
        "function_names": _batch_length(function_names, field_name="function_names"),
        "metadata_batch": _batch_length(metadata_batch, field_name="metadata_batch"),
    }
    expected = lengths["completions"]
    if any(length != expected for length in lengths.values()):
        details = ", ".join(f"{name}={length}" for name, length in lengths.items())
        raise RewardContractError(f"reward batch lengths must match: {details}")
    return expected


def _require_executor(value: object) -> CodeExecutor:
    """Return an executor-like object with callable execute, or raise before scoring."""
    execute = getattr(value, "execute", None)
    if not callable(execute):
        raise RewardContractError("executor must provide a callable execute method")
    return cast(CodeExecutor, value)


_COMPONENT_FIELDS = {
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
    "passed_tests",
    "total_tests",
    "parse_error_type",
    "failure_counts",
}
_NUMERIC_COMPONENT_FIELDS = {
    "test_reward",
    "executable_reward",
    "timeout_penalty",
    "invalid_format_penalty",
    "total_reward",
    "executor_runtime_ms",
}


def _reward_components_from_verification(
    result: VerificationResult,
    *,
    mode: str,
) -> dict[str, object]:
    """Map one validated verification result to the exact specification reward components."""
    validate_verification_result(result)
    if mode not in {"public", "hidden"}:
        raise RewardContractError("reward mode must be public or hidden")

    failure_counts = {key: count for key, count in result.failure_counts}
    infrastructure_failure = result.infrastructure_failure or ExecutionStatus.SANDBOX_ERROR.value in failure_counts
    timed_out = result.status is ExecutionStatus.TIMEOUT or ExecutionStatus.TIMEOUT.value in failure_counts

    test_reward = 0.0 if infrastructure_failure else float(result.pass_rate)
    executable_reward = 0.1 if result.parsed and result.executed and not infrastructure_failure else 0.0
    timeout_penalty = -0.2 if timed_out and not infrastructure_failure else 0.0
    invalid_format_penalty = -0.1 if result.status is ExecutionStatus.PARSE_ERROR else 0.0
    total_reward = test_reward + executable_reward + timeout_penalty + invalid_format_penalty
    executor_runtime_ms = 0.0 if result.execution_result is None else float(result.execution_result.runtime_ms)
    record: dict[str, object] = {
        "mode": mode,
        "test_reward": test_reward,
        "executable_reward": executable_reward,
        "timeout_penalty": timeout_penalty,
        "invalid_format_penalty": invalid_format_penalty,
        "total_reward": total_reward,
        "executor_runtime_ms": executor_runtime_ms,
        "status": result.status.value,
        "parsed": result.parsed,
        "executed": result.executed,
        "infrastructure_failure": infrastructure_failure,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "parse_error_type": result.parse_error_type,
        "failure_counts": failure_counts,
    }
    _validate_component_record(record)
    return record


def _validate_component_record(record: Mapping[str, object]) -> None:
    """Require exact component fields, finite numeric values, and total=sum(components)."""
    if set(record) != _COMPONENT_FIELDS:
        raise RewardContractError("reward component record fields are invalid")
    mode = record["mode"]
    if not isinstance(mode, str) or mode not in {"public", "hidden"}:
        raise RewardContractError("reward component mode is invalid")

    numeric_values: dict[str, float] = {}
    for field_name in _NUMERIC_COMPONENT_FIELDS:
        value = record[field_name]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise RewardContractError("reward component values must be finite numbers")
        try:
            normalized = float(value)
        except OverflowError:
            raise RewardContractError("reward component values must be finite numbers") from None
        if not math.isfinite(normalized):
            raise RewardContractError("reward component values must be finite numbers")
        numeric_values[field_name] = normalized

    component_sum = (
        numeric_values["test_reward"]
        + numeric_values["executable_reward"]
        + numeric_values["timeout_penalty"]
        + numeric_values["invalid_format_penalty"]
    )
    if not math.isclose(numeric_values["total_reward"], component_sum, rel_tol=0.0, abs_tol=1e-12):
        raise RewardContractError("total_reward must equal the sum of reward components")
    if numeric_values["executor_runtime_ms"] < 0.0:
        raise RewardContractError("executor_runtime_ms must be non-negative")

    status = record["status"]
    if not isinstance(status, str) or status not in {item.value for item in ExecutionStatus}:
        raise RewardContractError("reward component status is invalid")
    for field_name in ("parsed", "executed", "infrastructure_failure"):
        if not isinstance(record[field_name], bool):
            raise RewardContractError("reward component flags must be booleans")
    for field_name in ("passed_tests", "total_tests"):
        value = record[field_name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RewardContractError("reward component counts must be non-negative integers")
    parse_error_type = record["parse_error_type"]
    if parse_error_type is not None and not isinstance(parse_error_type, str):
        raise RewardContractError("reward component parse_error_type is invalid")
    failure_counts = record["failure_counts"]
    if not isinstance(failure_counts, Mapping) or any(
        not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for key, value in failure_counts.items()
    ):
        raise RewardContractError("reward component failure_counts is invalid")
    try:
        json.dumps(dict(record), allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise RewardContractError("reward component record must be JSON safe") from None


def compute_code_rewards(
    completions: object,
    tests_batch: object,
    function_names: object,
    metadata_batch: object,
    executor: CodeExecutor,
    mode: str,
) -> tuple[list[float], list[dict[str, object]]]:
    """Compute aligned code rewards and sanitized component records for one selected test source."""
    if mode not in {"public", "hidden"}:
        raise RewardContractError("reward mode must be public or hidden")
    batch_size = _validate_batch_alignment(completions, tests_batch, function_names, metadata_batch)
    completion_texts = _completion_texts(completions)
    validated_executor = _require_executor(executor)
    if batch_size == 0:
        return [], []

    test_values = cast(Sequence[object], tests_batch)
    function_values = cast(Sequence[object], function_names)
    metadata_values = cast(Sequence[object], metadata_batch)
    rewards: list[float] = []
    component_records: list[dict[str, object]] = []
    for index in range(batch_size):
        try:
            verification = verify_completion(
                completion_texts[index],
                cast(Sequence[Mapping[str, object]], test_values[index]),
                cast(str, function_values[index]),
                cast(Mapping[str, object], metadata_values[index]),
                validated_executor,
            )
        except VerificationContractError:
            raise RewardContractError("reward item violates verification input contract") from None
        record = _reward_components_from_verification(verification, mode=mode)
        _validate_component_record(record)
        total_reward = record["total_reward"]
        if isinstance(total_reward, bool) or not isinstance(total_reward, int | float):
            raise RewardContractError("total reward must be a finite number")
        reward = float(total_reward)
        if not math.isfinite(reward):
            raise RewardContractError("total reward must be a finite number")
        rewards.append(reward)
        component_records.append(dict(record))
    return rewards, component_records
