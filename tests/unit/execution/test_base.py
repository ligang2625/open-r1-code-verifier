"""Tests for execution contracts, validation, and serialization."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import Any, cast

import pytest

from code_verifier.execution import (
    CodeExecutor,
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    MockExecutor,
    execution_result_from_mapping,
    execution_result_to_mapping,
    validate_execution_request,
    validate_execution_result,
    validate_test_case_result,
)
from code_verifier.execution import (
    TestCaseResult as ExecutionTestCaseResult,
)


def _test_result(
    status: ExecutionStatus = ExecutionStatus.PASSED,
    *,
    runtime_ms: float = 1.0,
    stdout: str = "",
    stderr: str = "",
) -> ExecutionTestCaseResult:
    return ExecutionTestCaseResult(
        status=status,
        passed=status is ExecutionStatus.PASSED,
        runtime_ms=runtime_ms,
        stdout=stdout,
        stderr=stderr,
    )


def _execution_result(
    *,
    status: ExecutionStatus = ExecutionStatus.PASSED,
    passed_tests: int = 1,
    total_tests: int = 1,
    pass_rate: float = 1.0,
    runtime_ms: float = 1.0,
    test_results: list[ExecutionTestCaseResult] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        status=status,
        passed_tests=passed_tests,
        total_tests=total_tests,
        pass_rate=pass_rate,
        runtime_ms=runtime_ms,
        test_results=[_test_result()] if test_results is None else test_results,
    )


def test_execution_status_values_match_spec() -> None:
    assert [(status.name, status.value) for status in ExecutionStatus] == [
        ("PASSED", "passed"),
        ("WRONG_ANSWER", "wrong_answer"),
        ("SYNTAX_ERROR", "syntax_error"),
        ("RUNTIME_ERROR", "runtime_error"),
        ("TIMEOUT", "timeout"),
        ("MEMORY_LIMIT", "memory_limit"),
        ("OUTPUT_LIMIT", "output_limit"),
        ("SANDBOX_ERROR", "sandbox_error"),
        ("PARSE_ERROR", "parse_error"),
    ]


def test_test_case_result_is_frozen() -> None:
    result = _test_result()

    with pytest.raises(FrozenInstanceError):
        cast(Any, result).runtime_ms = 2.0


def test_execution_result_is_frozen() -> None:
    result = _execution_result()

    with pytest.raises(FrozenInstanceError):
        cast(Any, result).pass_rate = 0.0


def test_validate_execution_request_accepts_valid_json_tests() -> None:
    validate_execution_request(
        "def solve(value):\n    return value\n",
        "solve",
        [
            {"input": [1, {"nested": [True, None, 2.5]}], "expected": {"value": 1}},
            {"input": "text", "expected": ["text"]},
        ],
        1.5,
        256,
    )


def test_validate_execution_request_allows_empty_test_list() -> None:
    validate_execution_request("def solve():\n    return None\n", "solve", [], 1, 64)


@pytest.mark.parametrize(
    ("code", "function_name"),
    [
        ("", "solve"),
        ("   ", "solve"),
        (cast(str, None), "solve"),
        ("def solve():\n    pass\n", ""),
        ("def solve():\n    pass\n", "not-valid"),
        ("def solve():\n    pass\n", "class"),
    ],
)
def test_validate_execution_request_rejects_invalid_code_and_function_name(code: str, function_name: str) -> None:
    with pytest.raises(ExecutionContractError):
        validate_execution_request(code, function_name, [], 1.0, 64)


@pytest.mark.parametrize(
    "tests",
    [
        [{"input": 1}],
        [{"input": 1, "expected": 1, "extra": 1}],
        [cast(dict[str, Any], {"input": 1, 2: 3})],
        cast(list[dict[str, Any]], ({"input": 1, "expected": 1},)),
        cast(list[dict[str, Any]], [1]),
    ],
)
def test_validate_execution_request_rejects_unknown_or_missing_test_fields(tests: list[dict[str, Any]]) -> None:
    with pytest.raises(ExecutionContractError):
        validate_execution_request("def solve():\n    pass\n", "solve", tests, 1.0, 64)


@pytest.mark.parametrize(
    ("invalid_field", "sentinel_key"),
    [("input", "UNTRUSTED_KEY_SENTINEL"), ("expected", "EXPECTED_KEY_SENTINEL")],
)
def test_validate_execution_request_rejects_non_json_values_without_echoing_payload(
    invalid_field: str,
    sentinel_key: str,
) -> None:
    sentinel_value = "PAYLOAD_VALUE_SENTINEL_314159"
    tests: list[dict[str, Any]] = [{"input": sentinel_value, "expected": sentinel_value}]
    tests[0][invalid_field] = {sentinel_key: object()}

    with pytest.raises(ExecutionContractError) as exc_info:
        validate_execution_request("def solve():\n    pass\n", "solve", tests, 1.0, 64)

    assert str(exc_info.value) == f"tests[0].{invalid_field} contains an invalid JSON value"
    assert sentinel_key not in str(exc_info.value)
    assert sentinel_value not in str(exc_info.value)


def test_validate_execution_request_rejects_recursive_json_value_as_contract_error() -> None:
    recursive_value: list[Any] = []
    recursive_value.append(recursive_value)

    with pytest.raises(ExecutionContractError, match=r"^tests\[0\]\.input contains an invalid JSON value$"):
        validate_execution_request(
            "def solve():\n    pass\n",
            "solve",
            [{"input": recursive_value, "expected": None}],
            1.0,
            64,
        )


@pytest.mark.parametrize(
    ("timeout_seconds", "memory_limit_mb"),
    [
        (0.0, 64),
        (-1.0, 64),
        (float("nan"), 64),
        (float("inf"), 64),
        (cast(float, True), 64),
        (cast(float, 10**1000), 64),
        (1.0, 0),
        (1.0, -1),
        (1.0, cast(int, True)),
        (1.0, cast(int, 1.5)),
    ],
)
def test_validate_execution_request_rejects_nonfinite_or_nonpositive_limits(
    timeout_seconds: float,
    memory_limit_mb: int,
) -> None:
    with pytest.raises(ExecutionContractError):
        validate_execution_request("def solve():\n    pass\n", "solve", [], timeout_seconds, memory_limit_mb)


@pytest.mark.parametrize("status", [status for status in ExecutionStatus if status is not ExecutionStatus.PASSED])
def test_validate_test_case_result_accepts_each_failure_status(status: ExecutionStatus) -> None:
    validate_test_case_result(_test_result(status))


@pytest.mark.parametrize(
    "result",
    [
        replace(_test_result(), passed=False),
        replace(_test_result(ExecutionStatus.TIMEOUT), passed=True),
    ],
)
def test_validate_test_case_result_rejects_passed_status_mismatch(result: ExecutionTestCaseResult) -> None:
    with pytest.raises(ExecutionContractError):
        validate_test_case_result(result)


@pytest.mark.parametrize(
    "result",
    [
        replace(_test_result(), status=cast(ExecutionStatus, "passed")),
        replace(_test_result(), passed=cast(bool, 1)),
        replace(_test_result(), runtime_ms=cast(float, True)),
        replace(_test_result(), runtime_ms=-0.1),
        replace(_test_result(), runtime_ms=float("nan")),
        replace(_test_result(), runtime_ms=cast(float, 10**1000)),
        replace(_test_result(), stdout=cast(str, 1)),
        replace(_test_result(), stderr=cast(str, None)),
    ],
)
def test_validate_test_case_result_rejects_invalid_field_types(result: ExecutionTestCaseResult) -> None:
    with pytest.raises(ExecutionContractError):
        validate_test_case_result(result)


def test_validate_execution_result_accepts_full_pass() -> None:
    validate_execution_result(
        _execution_result(
            passed_tests=2,
            total_tests=2,
            pass_rate=1.0,
            runtime_ms=2.5,
            test_results=[_test_result(runtime_ms=1.0), _test_result(runtime_ms=1.5)],
        )
    )


def test_validate_execution_result_accepts_early_stop_failure() -> None:
    validate_execution_result(
        _execution_result(
            status=ExecutionStatus.TIMEOUT,
            passed_tests=1,
            total_tests=3,
            pass_rate=1 / 3,
            test_results=[_test_result(), _test_result(ExecutionStatus.TIMEOUT)],
        )
    )


@pytest.mark.parametrize("status", [ExecutionStatus.PASSED, ExecutionStatus.SANDBOX_ERROR])
def test_validate_execution_result_accepts_zero_tests_with_zero_rate(status: ExecutionStatus) -> None:
    validate_execution_result(
        _execution_result(status=status, passed_tests=0, total_tests=0, pass_rate=0.0, test_results=[])
    )


@pytest.mark.parametrize(
    "result",
    [
        _execution_result(passed_tests=-1),
        _execution_result(total_tests=-1),
        _execution_result(passed_tests=2, total_tests=1),
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            passed_tests=0,
            total_tests=1,
            pass_rate=0.0,
            test_results=[_test_result(ExecutionStatus.WRONG_ANSWER), _test_result(ExecutionStatus.TIMEOUT)],
        ),
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            passed_tests=1,
            total_tests=2,
            pass_rate=0.5,
            test_results=[_test_result(ExecutionStatus.WRONG_ANSWER)],
        ),
        replace(_execution_result(), passed_tests=cast(int, True)),
        replace(_execution_result(), test_results=cast(list[ExecutionTestCaseResult], ())),
    ],
)
def test_validate_execution_result_rejects_count_and_result_mismatches(result: ExecutionResult) -> None:
    with pytest.raises(ExecutionContractError):
        validate_execution_result(result)


@pytest.mark.parametrize(
    "pass_rate",
    [float("nan"), float("inf"), -0.1, 1.1, 0.5, cast(float, True), cast(float, 10**1000)],
)
def test_validate_execution_result_rejects_invalid_pass_rate(pass_rate: float) -> None:
    with pytest.raises(ExecutionContractError):
        validate_execution_result(_execution_result(pass_rate=pass_rate))


@pytest.mark.parametrize(
    "result",
    [
        _execution_result(
            status=ExecutionStatus.PASSED,
            passed_tests=1,
            total_tests=2,
            pass_rate=0.5,
            test_results=[_test_result()],
        ),
        _execution_result(status=ExecutionStatus.WRONG_ANSWER),
    ],
)
def test_validate_execution_result_rejects_inconsistent_overall_status(result: ExecutionResult) -> None:
    with pytest.raises(ExecutionContractError):
        validate_execution_result(result)


@pytest.mark.parametrize(
    "runtime_ms",
    [-0.1, float("nan"), float("inf"), cast(float, True), cast(float, 10**1000)],
)
def test_validate_execution_result_rejects_invalid_runtime(runtime_ms: float) -> None:
    with pytest.raises(ExecutionContractError):
        validate_execution_result(_execution_result(runtime_ms=runtime_ms))


def test_execution_result_to_mapping_is_exact_and_json_serializable() -> None:
    result = _execution_result(
        passed_tests=2,
        total_tests=2,
        pass_rate=1,
        runtime_ms=3,
        test_results=[
            _test_result(runtime_ms=1, stdout="ok"),
            _test_result(runtime_ms=2, stderr="warning"),
        ],
    )

    mapping = execution_result_to_mapping(result)

    assert mapping == {
        "status": "passed",
        "passed_tests": 2,
        "total_tests": 2,
        "pass_rate": 1.0,
        "runtime_ms": 3.0,
        "test_results": [
            {"status": "passed", "passed": True, "runtime_ms": 1.0, "stdout": "ok", "stderr": ""},
            {"status": "passed", "passed": True, "runtime_ms": 2.0, "stdout": "", "stderr": "warning"},
        ],
    }
    assert json.loads(json.dumps(mapping, allow_nan=False)) == mapping


def test_execution_result_from_mapping_round_trips_exact_mapping() -> None:
    mapping = execution_result_to_mapping(_execution_result())
    parsed = execution_result_from_mapping(mapping)
    assert execution_result_to_mapping(parsed) == mapping


@pytest.mark.parametrize(
    "mapping",
    [
        {},
        {
            "status": "passed",
            "passed_tests": 1,
            "total_tests": 1,
            "pass_rate": 1.0,
            "runtime_ms": 1.0,
            "test_results": [],
            "extra": 1,
        },
        {
            "status": "passed",
            "passed_tests": True,
            "total_tests": 1,
            "pass_rate": 1.0,
            "runtime_ms": 1.0,
            "test_results": [],
        },
        {
            "status": "passed",
            "passed_tests": 1,
            "total_tests": 1,
            "pass_rate": 1.0,
            "runtime_ms": 1.0,
            "test_results": [{"status": "passed", "passed": True, "runtime_ms": 1.0, "stdout": ""}],
        },
    ],
)
def test_execution_result_from_mapping_rejects_missing_unknown_and_wrong_typed_fields(mapping: object) -> None:
    with pytest.raises(ExecutionContractError):
        execution_result_from_mapping(mapping)


@pytest.mark.parametrize(
    "mapping",
    [
        {
            "status": "unknown",
            "passed_tests": 0,
            "total_tests": 0,
            "pass_rate": 0.0,
            "runtime_ms": 0.0,
            "test_results": [],
        },
        {
            "status": "passed",
            "passed_tests": 0,
            "total_tests": 1,
            "pass_rate": 0.0,
            "runtime_ms": 0.0,
            "test_results": [],
        },
    ],
)
def test_execution_result_from_mapping_rejects_invalid_status_and_result_invariants(mapping: object) -> None:
    with pytest.raises(ExecutionContractError):
        execution_result_from_mapping(mapping)


def test_execution_result_from_mapping_returns_independent_test_result_list() -> None:
    mapping = execution_result_to_mapping(_execution_result())
    parsed = execution_result_from_mapping(mapping)
    raw_items = cast(list[dict[str, object]], mapping["test_results"])
    raw_items.clear()
    assert len(parsed.test_results) == 1


def test_execution_result_from_mapping_error_does_not_echo_sentinel() -> None:
    sentinel = "PRIVATE_MAPPING_SENTINEL"
    mapping = {
        "status": sentinel,
        "passed_tests": 0,
        "total_tests": 0,
        "pass_rate": 0.0,
        "runtime_ms": 0.0,
        "test_results": [],
    }
    with pytest.raises(ExecutionContractError) as exc_info:
        execution_result_from_mapping(mapping)
    assert sentinel not in str(exc_info.value)


def test_mock_implementation_is_assignable_to_code_executor() -> None:
    executor: CodeExecutor = MockExecutor([_execution_result()])

    assert executor.execute("def solve():\n    return 1\n", "solve", [], 1.0, 64).status is ExecutionStatus.PASSED
