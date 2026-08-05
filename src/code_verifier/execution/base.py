"""Public execution contracts shared by sandbox implementations and test doubles."""

from __future__ import annotations

import keyword
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from code_verifier.data.schema import SchemaError, validate_json_value


class ExecutionStatus(str, Enum):
    PASSED = "passed"
    WRONG_ANSWER = "wrong_answer"
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    MEMORY_LIMIT = "memory_limit"
    OUTPUT_LIMIT = "output_limit"
    SANDBOX_ERROR = "sandbox_error"
    PARSE_ERROR = "parse_error"


@dataclass(frozen=True)
class TestCaseResult:
    """Structured outcome for one executed test case."""

    status: ExecutionStatus
    passed: bool
    runtime_ms: float
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ExecutionResult:
    """Structured aggregate outcome for one code execution request.

    The dataclass is shallowly frozen because the specification requires
    ``test_results`` to remain a list. Implementations must defensively copy
    mutable members at public boundaries.
    """

    status: ExecutionStatus
    passed_tests: int
    total_tests: int
    pass_rate: float
    runtime_ms: float
    test_results: list[TestCaseResult]


class CodeExecutor(Protocol):
    """Synchronous interface implemented by real executors and test doubles."""

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult: ...


class ExecutionContractError(ValueError):
    """Raised when an execution request or structured result violates the public contract."""


def _is_finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and math.isfinite(value)


def validate_execution_request(
    code: str,
    function_name: str,
    tests: list[dict[str, Any]],
    timeout_seconds: float,
    memory_limit_mb: int,
) -> None:
    """Validate one executor request without executing or transforming code."""
    if not isinstance(code, str) or not code.strip():
        raise ExecutionContractError("code must be a non-empty string")
    if (
        not isinstance(function_name, str)
        or not function_name
        or not function_name.isidentifier()
        or keyword.iskeyword(function_name)
    ):
        raise ExecutionContractError("function_name must be a non-keyword Python identifier")
    if not isinstance(tests, list):
        raise ExecutionContractError("tests must be a list")

    for index, test in enumerate(tests):
        field_path = f"tests[{index}]"
        if not isinstance(test, dict):
            raise ExecutionContractError(f"{field_path} must be an object")
        if set(test) != {"input", "expected"}:
            raise ExecutionContractError(f"{field_path} fields must be exactly input and expected")
        try:
            validate_json_value(test["input"], field_path=f"{field_path}.input")
            validate_json_value(test["expected"], field_path=f"{field_path}.expected")
        except SchemaError as exc:
            raise ExecutionContractError(str(exc)) from None

    if not _is_finite_number(timeout_seconds) or timeout_seconds <= 0:
        raise ExecutionContractError("timeout_seconds must be a finite positive number")
    if isinstance(memory_limit_mb, bool) or not isinstance(memory_limit_mb, int) or memory_limit_mb <= 0:
        raise ExecutionContractError("memory_limit_mb must be a positive integer")


def validate_test_case_result(result: TestCaseResult) -> None:
    """Validate one per-test status, runtime, and captured output record."""
    if not isinstance(result, TestCaseResult):
        raise ExecutionContractError("test result must be a TestCaseResult")
    if not isinstance(result.status, ExecutionStatus):
        raise ExecutionContractError("test result status must be an ExecutionStatus")
    if not isinstance(result.passed, bool):
        raise ExecutionContractError("test result passed must be a boolean")
    if not _is_finite_number(result.runtime_ms) or result.runtime_ms < 0:
        raise ExecutionContractError("test result runtime_ms must be a finite non-negative number")
    if not isinstance(result.stdout, str):
        raise ExecutionContractError("test result stdout must be a string")
    if not isinstance(result.stderr, str):
        raise ExecutionContractError("test result stderr must be a string")
    if result.passed is not (result.status is ExecutionStatus.PASSED):
        raise ExecutionContractError("test result passed must match whether status is passed")


def _validate_count(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionContractError(f"{field_name} must be a non-negative integer")
    return value


def validate_execution_result(result: ExecutionResult) -> None:
    """Validate counts, pass rate, status consistency, and per-test records."""
    if not isinstance(result, ExecutionResult):
        raise ExecutionContractError("execution result must be an ExecutionResult")
    if not isinstance(result.status, ExecutionStatus):
        raise ExecutionContractError("status must be an ExecutionStatus")

    passed_tests = _validate_count(result.passed_tests, field_name="passed_tests")
    total_tests = _validate_count(result.total_tests, field_name="total_tests")
    if passed_tests > total_tests:
        raise ExecutionContractError("passed_tests must not exceed total_tests")
    if not isinstance(result.test_results, list):
        raise ExecutionContractError("test_results must be a list")
    if len(result.test_results) > total_tests:
        raise ExecutionContractError("test_results must not contain more entries than total_tests")

    for test_result in result.test_results:
        validate_test_case_result(test_result)
    actual_passed = sum(test_result.passed for test_result in result.test_results)
    if passed_tests != actual_passed:
        raise ExecutionContractError("passed_tests must equal the number of returned passed test results")

    if not _is_finite_number(result.pass_rate) or not 0 <= result.pass_rate <= 1:
        raise ExecutionContractError("pass_rate must be a finite number between 0 and 1")
    expected_pass_rate = 0.0 if total_tests == 0 else passed_tests / total_tests
    if not math.isclose(result.pass_rate, expected_pass_rate, rel_tol=0.0, abs_tol=1e-12):
        raise ExecutionContractError("pass_rate must equal passed_tests divided by total_tests")
    if not _is_finite_number(result.runtime_ms) or result.runtime_ms < 0:
        raise ExecutionContractError("runtime_ms must be a finite non-negative number")

    complete_pass = len(result.test_results) == total_tests and passed_tests == total_tests
    if result.status is ExecutionStatus.PASSED and not complete_pass:
        raise ExecutionContractError("passed status requires a complete set of passed test results")
    if total_tests > 0 and complete_pass and result.status is not ExecutionStatus.PASSED:
        raise ExecutionContractError("a complete set of passed test results requires passed status")


def execution_result_to_mapping(result: ExecutionResult) -> dict[str, object]:
    """Return a validated JSON-safe mapping with enum values serialized as strings."""
    validate_execution_result(result)
    return {
        "status": result.status.value,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "pass_rate": float(result.pass_rate),
        "runtime_ms": float(result.runtime_ms),
        "test_results": [
            {
                "status": test_result.status.value,
                "passed": test_result.passed,
                "runtime_ms": float(test_result.runtime_ms),
                "stdout": test_result.stdout,
                "stderr": test_result.stderr,
            }
            for test_result in result.test_results
        ],
    }
