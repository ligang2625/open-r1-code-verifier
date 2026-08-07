"""Structured, sanitized verification results for reward and evaluation consumers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from code_verifier.execution.base import (
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    execution_result_to_mapping,
    validate_execution_result,
)


class VerificationContractError(ValueError):
    """Raised when verifier inputs or structured outputs violate the public contract."""


FailureCounts = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class VerificationResult:
    """Sanitized parser/executor summary used by reward and evaluation consumers."""

    status: ExecutionStatus
    parsed: bool
    executed: bool
    infrastructure_failure: bool
    passed_tests: int
    total_tests: int
    pass_rate: float
    parse_error_type: str | None
    num_code_blocks: int
    failure_counts: FailureCounts
    execution_result: ExecutionResult | None


def _validate_non_negative_integer(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise VerificationContractError(f"{field_name} must be a non-negative integer")
    return value


def _validate_finite_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise VerificationContractError(f"{field_name} must be a finite number")
    try:
        finite_value = float(value)
    except OverflowError:
        raise VerificationContractError(f"{field_name} must be a finite number") from None
    if not math.isfinite(finite_value):
        raise VerificationContractError(f"{field_name} must be a finite number")
    return finite_value


def _validate_failure_counts(failure_counts: object) -> FailureCounts:
    if not isinstance(failure_counts, tuple):
        raise VerificationContractError("failure_counts must be a tuple")

    allowed_statuses = {status.value for status in ExecutionStatus if status is not ExecutionStatus.PASSED}
    validated: list[tuple[str, int]] = []
    previous_key: str | None = None
    for item in failure_counts:
        if not isinstance(item, tuple) or len(item) != 2:
            raise VerificationContractError("failure_counts entries must be key/count tuples")
        key, count = item
        if not isinstance(key, str) or key not in allowed_statuses:
            raise VerificationContractError("failure_counts contains an unsupported status")
        if previous_key is not None and key <= previous_key:
            raise VerificationContractError("failure_counts keys must be unique and strictly sorted")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise VerificationContractError("failure_counts values must be positive integers")
        validated.append((key, count))
        previous_key = key
    return tuple(validated)


def validate_verification_result(result: VerificationResult) -> None:
    """Validate all cross-field, finiteness, count, parse, and execution invariants."""
    if not isinstance(result, VerificationResult):
        raise VerificationContractError("result must be a VerificationResult")
    if not isinstance(result.status, ExecutionStatus):
        raise VerificationContractError("status must be an ExecutionStatus")
    if not isinstance(result.parsed, bool):
        raise VerificationContractError("parsed must be a boolean")
    if not isinstance(result.executed, bool):
        raise VerificationContractError("executed must be a boolean")
    if not isinstance(result.infrastructure_failure, bool):
        raise VerificationContractError("infrastructure_failure must be a boolean")

    passed_tests = _validate_non_negative_integer(result.passed_tests, field_name="passed_tests")
    total_tests = _validate_non_negative_integer(result.total_tests, field_name="total_tests")
    if total_tests == 0:
        raise VerificationContractError("total_tests must be positive")
    if passed_tests > total_tests:
        raise VerificationContractError("passed_tests must not exceed total_tests")

    pass_rate = _validate_finite_number(result.pass_rate, field_name="pass_rate")
    expected_pass_rate = passed_tests / total_tests
    if not math.isclose(pass_rate, expected_pass_rate, rel_tol=0.0, abs_tol=1e-12):
        raise VerificationContractError("pass_rate must equal passed_tests divided by total_tests")

    _validate_non_negative_integer(result.num_code_blocks, field_name="num_code_blocks")
    failure_counts = _validate_failure_counts(result.failure_counts)
    failed_tests = total_tests - passed_tests
    if sum(count for _, count in failure_counts) != failed_tests:
        raise VerificationContractError("failure_counts must account for every failed test")
    if failed_tests == 0 and failure_counts:
        raise VerificationContractError("failure_counts must be empty when all tests pass")

    if not result.parsed:
        if result.status is not ExecutionStatus.PARSE_ERROR:
            raise VerificationContractError("an unparsed result must have parse_error status")
        if result.executed:
            raise VerificationContractError("an unparsed result must not be executed")
        if result.infrastructure_failure:
            raise VerificationContractError("a parse failure is not an infrastructure failure")
        if not isinstance(result.parse_error_type, str) or not result.parse_error_type:
            raise VerificationContractError("a parse failure must include a parser error type")
        try:
            result.parse_error_type.encode("utf-8")
        except UnicodeEncodeError:
            raise VerificationContractError("parse_error_type must contain valid UTF-8 text") from None
        if result.execution_result is not None:
            raise VerificationContractError("an unparsed result must not include an execution result")
        if passed_tests != 0 or pass_rate != 0.0:
            raise VerificationContractError("a parse failure must have zero passed tests and pass rate")
    else:
        if result.status is ExecutionStatus.PARSE_ERROR:
            raise VerificationContractError("parse_error status requires an unparsed result")
        if result.parse_error_type is not None:
            raise VerificationContractError("a parsed result must not include a parser error type")

    if result.executed:
        if result.execution_result is None:
            raise VerificationContractError("an executed result must include an execution result")
        try:
            validate_execution_result(result.execution_result)
        except ExecutionContractError:
            raise VerificationContractError("execution_result is invalid") from None
        execution_result = result.execution_result
        if execution_result.status is ExecutionStatus.PARSE_ERROR or any(
            test_result.status is ExecutionStatus.PARSE_ERROR for test_result in execution_result.test_results
        ):
            raise VerificationContractError("execution_result must not contain parse_error status")
        if (
            result.status is not execution_result.status
            or passed_tests != execution_result.passed_tests
            or total_tests != execution_result.total_tests
            or not math.isclose(pass_rate, float(execution_result.pass_rate), rel_tol=0.0, abs_tol=1e-12)
        ):
            raise VerificationContractError("verification summary must match execution_result")
    elif result.parsed:
        if result.status is not ExecutionStatus.SANDBOX_ERROR:
            raise VerificationContractError("a parsed but unexecuted result must have sandbox_error status")
        if not result.infrastructure_failure:
            raise VerificationContractError("a parsed but unexecuted result must be an infrastructure failure")
        if result.execution_result is not None:
            raise VerificationContractError("a parsed but unexecuted result must not include execution_result")
        if passed_tests != 0 or pass_rate != 0.0:
            raise VerificationContractError("a parsed but unexecuted result must have zero passed tests and pass rate")

    if result.infrastructure_failure is not (result.status is ExecutionStatus.SANDBOX_ERROR):
        raise VerificationContractError("infrastructure_failure must match sandbox_error status")


def verification_result_to_mapping(result: VerificationResult) -> dict[str, object]:
    """Return a validated JSON-safe summary without completion, code, tests, or metadata."""
    validate_verification_result(result)
    return {
        "status": result.status.value,
        "parsed": result.parsed,
        "executed": result.executed,
        "infrastructure_failure": result.infrastructure_failure,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "pass_rate": float(result.pass_rate),
        "parse_error_type": result.parse_error_type,
        "num_code_blocks": result.num_code_blocks,
        "failure_counts": {key: count for key, count in result.failure_counts},
        "execution_result": (
            None if result.execution_result is None else execution_result_to_mapping(result.execution_result)
        ),
    }
