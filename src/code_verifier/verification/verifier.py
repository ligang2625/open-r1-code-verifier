"""Unified verification helpers and completion verification orchestration."""

from __future__ import annotations

import keyword
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from code_verifier.data.schema import SchemaError, json_value_to_mutable, validate_json_value
from code_verifier.execution.base import (
    CodeExecutor,
    ExecutionResult,
    ExecutionStatus,
    TestCaseResult,
    validate_execution_result,
)
from code_verifier.parsing.code_extractor import ParseResult, extract_python_code
from code_verifier.verification.result_types import (
    FailureCounts,
    VerificationContractError,
    VerificationResult,
    validate_verification_result,
)


@dataclass(frozen=True)
class VerificationRequest:
    """Side-effect-free, normalized input for one completion verification."""

    completion: object
    tests: list[dict[str, Any]]
    function_name: str
    timeout_seconds: float
    memory_limit_mb: int
    parse_result: ParseResult


def _validate_utf8_text(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise VerificationContractError("verification input contains invalid UTF-8 text") from None


def _validate_utf8_json_value(value: object) -> None:
    if isinstance(value, str):
        _validate_utf8_text(value)
        return
    if isinstance(value, list):
        for item in value:
            _validate_utf8_json_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_utf8_text(key)
            _validate_utf8_json_value(item)


def _validate_function_name(function_name: object) -> str:
    """Return one non-keyword Python identifier or raise a sanitized contract error."""
    if not isinstance(function_name, str):
        raise VerificationContractError("function_name must be a non-keyword Python identifier")
    _validate_utf8_text(function_name)
    if not function_name or not function_name.isidentifier() or keyword.iskeyword(function_name):
        raise VerificationContractError("function_name must be a non-keyword Python identifier")
    return function_name


def _normalize_tests(tests: object) -> list[dict[str, Any]]:
    """Validate one non-empty ordered test layer and return a defensive mutable copy."""
    if isinstance(tests, str | bytes | bytearray) or not isinstance(tests, Sequence) or not tests:
        raise VerificationContractError("tests must be a non-empty sequence")

    normalized: list[dict[str, Any]] = []
    try:
        for item in tests:
            if not isinstance(item, Mapping):
                raise VerificationContractError("each test must be an input/expected mapping")
            if any(type(key) is not str for key in item) or set(item) != {"input", "expected"}:
                raise VerificationContractError("each test must contain exactly input and expected")
            validated_input = validate_json_value(item["input"], field_path="test.input")
            validated_expected = validate_json_value(item["expected"], field_path="test.expected")
            mutable_input = json_value_to_mutable(validated_input, field_path="test.input")
            mutable_expected = json_value_to_mutable(validated_expected, field_path="test.expected")
            _validate_utf8_json_value(mutable_input)
            _validate_utf8_json_value(mutable_expected)
            normalized.append({"input": mutable_input, "expected": mutable_expected})
    except VerificationContractError:
        raise
    except (MemoryError, RecursionError, SchemaError, UnicodeError):
        raise VerificationContractError("tests contain an invalid JSON value") from None
    return normalized


def _resource_limits_from_metadata(metadata: object) -> tuple[float, int]:
    """Read and validate only time_limit_seconds and memory_limit_mb from metadata."""
    if not isinstance(metadata, Mapping) or any(type(key) is not str for key in metadata):
        raise VerificationContractError("metadata must be a string-keyed mapping")
    if "time_limit_seconds" not in metadata or "memory_limit_mb" not in metadata:
        raise VerificationContractError("metadata must include execution resource limits")

    time_limit = metadata["time_limit_seconds"]
    if isinstance(time_limit, bool) or not isinstance(time_limit, int | float):
        raise VerificationContractError("time_limit_seconds must be a finite positive number")
    try:
        normalized_time_limit = float(time_limit)
    except OverflowError:
        raise VerificationContractError("time_limit_seconds must be a finite positive number") from None
    if not math.isfinite(normalized_time_limit) or normalized_time_limit <= 0:
        raise VerificationContractError("time_limit_seconds must be a finite positive number")

    memory_limit = metadata["memory_limit_mb"]
    if isinstance(memory_limit, bool) or not isinstance(memory_limit, int) or memory_limit <= 0:
        raise VerificationContractError("memory_limit_mb must be a positive integer")
    return normalized_time_limit, memory_limit


def prevalidate_verification_input(
    completion: object,
    tests: object,
    function_name: object,
    metadata: object,
) -> VerificationRequest:
    """Normalize and parse one request without creating or using an executor."""
    validated_function_name = _validate_function_name(function_name)
    normalized_tests = _normalize_tests(tests)
    timeout_seconds, memory_limit_mb = _resource_limits_from_metadata(metadata)
    parse_result = extract_python_code(cast(str, completion), expected_function_name=validated_function_name)
    return VerificationRequest(
        completion=completion,
        tests=normalized_tests,
        function_name=validated_function_name,
        timeout_seconds=timeout_seconds,
        memory_limit_mb=memory_limit_mb,
        parse_result=parse_result,
    )


def _summarize_failure_counts(
    *,
    status: ExecutionStatus,
    passed_tests: int,
    total_tests: int,
    test_results: Sequence[TestCaseResult],
) -> FailureCounts:
    """Return sorted failure counts, assigning unexecuted tests to the aggregate status."""
    counts: dict[str, int] = {}
    for test_result in test_results:
        if test_result.status is ExecutionStatus.PASSED:
            continue
        key = test_result.status.value
        counts[key] = counts.get(key, 0) + 1

    unexecuted_tests = total_tests - len(test_results)
    if unexecuted_tests > 0:
        if status is ExecutionStatus.PASSED:
            raise VerificationContractError("unexecuted tests require a failure status")
        counts[status.value] = counts.get(status.value, 0) + unexecuted_tests

    expected_failed = total_tests - passed_tests
    if sum(counts.values()) != expected_failed:
        raise VerificationContractError("failure counts do not match failed tests")
    return tuple(sorted(counts.items()))


def _parse_failure_result(*, error_type: str, num_code_blocks: int, total_tests: int) -> VerificationResult:
    """Build one validated fail-closed parse result."""
    result = VerificationResult(
        status=ExecutionStatus.PARSE_ERROR,
        parsed=False,
        executed=False,
        infrastructure_failure=False,
        passed_tests=0,
        total_tests=total_tests,
        pass_rate=0.0,
        parse_error_type=error_type,
        num_code_blocks=num_code_blocks,
        failure_counts=((ExecutionStatus.PARSE_ERROR.value, total_tests),),
        execution_result=None,
    )
    validate_verification_result(result)
    return result


def _executor_exception_result(*, num_code_blocks: int, total_tests: int) -> VerificationResult:
    """Build one sanitized sandbox failure for an executor-side ordinary exception."""
    result = VerificationResult(
        status=ExecutionStatus.SANDBOX_ERROR,
        parsed=True,
        executed=False,
        infrastructure_failure=True,
        passed_tests=0,
        total_tests=total_tests,
        pass_rate=0.0,
        parse_error_type=None,
        num_code_blocks=num_code_blocks,
        failure_counts=((ExecutionStatus.SANDBOX_ERROR.value, total_tests),),
        execution_result=None,
    )
    validate_verification_result(result)
    return result


def _copy_execution_result(result: ExecutionResult) -> ExecutionResult:
    return ExecutionResult(
        status=result.status,
        passed_tests=result.passed_tests,
        total_tests=result.total_tests,
        pass_rate=result.pass_rate,
        runtime_ms=result.runtime_ms,
        test_results=list(result.test_results),
    )


def _executed_result(*, num_code_blocks: int, execution_result: ExecutionResult) -> VerificationResult:
    """Copy one validated ExecutionResult into the verifier result contract."""
    validate_execution_result(execution_result)
    copied_execution_result = _copy_execution_result(execution_result)
    failure_counts = _summarize_failure_counts(
        status=copied_execution_result.status,
        passed_tests=copied_execution_result.passed_tests,
        total_tests=copied_execution_result.total_tests,
        test_results=copied_execution_result.test_results,
    )
    result = VerificationResult(
        status=copied_execution_result.status,
        parsed=True,
        executed=True,
        infrastructure_failure=copied_execution_result.status is ExecutionStatus.SANDBOX_ERROR,
        passed_tests=copied_execution_result.passed_tests,
        total_tests=copied_execution_result.total_tests,
        pass_rate=copied_execution_result.pass_rate,
        parse_error_type=None,
        num_code_blocks=num_code_blocks,
        failure_counts=failure_counts,
        execution_result=copied_execution_result,
    )
    validate_verification_result(result)
    return result


def verify_prevalidated_request(
    request: VerificationRequest,
    executor: CodeExecutor | None,
) -> VerificationResult:
    """Verify one request returned by :func:`prevalidate_verification_input`."""
    if not isinstance(request, VerificationRequest):
        raise VerificationContractError("request must be a VerificationRequest")

    parse_result = request.parse_result
    if not isinstance(parse_result, ParseResult):
        raise VerificationContractError("request parse result is invalid")
    if not parse_result.success:
        if parse_result.error_type is None:
            raise VerificationContractError("parser failure must include an error type")
        return _parse_failure_result(
            error_type=parse_result.error_type,
            num_code_blocks=parse_result.num_code_blocks,
            total_tests=len(request.tests),
        )
    if executor is None:
        raise VerificationContractError("parsed verification requests require an executor")

    try:
        execution_result = executor.execute(
            parse_result.code,
            request.function_name,
            request.tests,
            request.timeout_seconds,
            request.memory_limit_mb,
        )
        validate_execution_result(execution_result)
        if execution_result.status is ExecutionStatus.PARSE_ERROR or any(
            test_result.status is ExecutionStatus.PARSE_ERROR for test_result in execution_result.test_results
        ):
            raise VerificationContractError("executor result must not contain parse_error status")
        if execution_result.total_tests != len(request.tests):
            raise VerificationContractError("executor total_tests does not match the selected test layer")
    except Exception:
        return _executor_exception_result(
            num_code_blocks=parse_result.num_code_blocks,
            total_tests=len(request.tests),
        )

    return _executed_result(
        num_code_blocks=parse_result.num_code_blocks,
        execution_result=execution_result,
    )


def verify_completion(
    completion: str,
    tests: Sequence[Mapping[str, object]],
    function_name: str,
    metadata: Mapping[str, object],
    executor: CodeExecutor,
) -> VerificationResult:
    """Parse and verify one completion against exactly one caller-selected test layer."""
    request = prevalidate_verification_input(completion, tests, function_name, metadata)
    return verify_prevalidated_request(request, executor)
