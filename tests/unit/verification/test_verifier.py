"""Tests for verification input normalization and orchestration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
from typing import Any, cast

import pytest

import code_verifier.verification.verifier as verifier_module
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.base import TestCaseResult as ExecutionTestCaseResult
from code_verifier.parsing.code_extractor import ParseResult
from code_verifier.verification.result_types import (
    VerificationContractError,
    verification_result_to_mapping,
)
from code_verifier.verification.verifier import (
    VerificationRequest,
    _normalize_tests,
    _resource_limits_from_metadata,
    _validate_function_name,
    prevalidate_verification_input,
    verify_completion,
    verify_prevalidated_request,
)

_COMPLETION = "prefix\n```python\ndef solve(value):\n    return value\n```\n"
_EXTRACTED_CODE = "def solve(value):\n    return value\n"
_METADATA: dict[str, object] = {"time_limit_seconds": 1.5, "memory_limit_mb": 256, "ignored": object()}


def _tests(count: int = 3) -> list[dict[str, object]]:
    return [{"input": {"position": index}, "expected": index} for index in range(count)]


def _test_result(status: ExecutionStatus) -> ExecutionTestCaseResult:
    return ExecutionTestCaseResult(
        status=status,
        passed=status is ExecutionStatus.PASSED,
        runtime_ms=1.0,
        stdout="",
        stderr="",
    )


def _execution_result(
    *,
    status: ExecutionStatus,
    total_tests: int,
    returned_statuses: Sequence[ExecutionStatus],
) -> ExecutionResult:
    test_results = [_test_result(item_status) for item_status in returned_statuses]
    passed_tests = sum(item.passed for item in test_results)
    return ExecutionResult(
        status=status,
        passed_tests=passed_tests,
        total_tests=total_tests,
        pass_rate=passed_tests / total_tests,
        runtime_ms=float(len(test_results)),
        test_results=test_results,
    )


class RecordingExecutor:
    """Minimal executor double that records requests and returns one configured object."""

    def __init__(self, result: ExecutionResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str, list[dict[str, Any]], float, int]] = []

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        self.calls.append((code, function_name, deepcopy(tests), timeout_seconds, memory_limit_mb))
        return self.result


class RaisingExecutor:
    """Executor double that raises one ordinary exception containing a sentinel."""

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        del code, function_name, tests, timeout_seconds, memory_limit_mb
        raise RuntimeError("PRIVATE_EXECUTOR_EXCEPTION_SENTINEL")


class VerifierAbort(BaseException):
    """BaseException sentinel that must not be converted into a sandbox result."""


class BaseExceptionExecutor:
    """Executor double that proves BaseException is not caught."""

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        del code, function_name, tests, timeout_seconds, memory_limit_mb
        raise VerifierAbort


def test_validate_function_name_accepts_identifier_and_rejects_keyword_invalid_utf8_and_wrong_type() -> None:
    assert _validate_function_name("solve_问题") == "solve_问题"

    invalid_names = ["", "not-valid", "class", " solve", "\ud800", 1, None]
    for invalid_name in invalid_names:
        with pytest.raises(VerificationContractError):
            _validate_function_name(invalid_name)


def test_normalize_tests_preserves_order_and_returns_deep_mutable_copy() -> None:
    nested_input = MappingProxyType({"values": (1, MappingProxyType({"flag": True}))})
    tests = (
        MappingProxyType({"input": nested_input, "expected": (1, 2)}),
        MappingProxyType({"input": "second", "expected": None}),
    )

    normalized = _normalize_tests(tests)

    assert normalized == [
        {"input": {"values": [1, {"flag": True}]}, "expected": [1, 2]},
        {"input": "second", "expected": None},
    ]
    assert isinstance(normalized, list)
    assert isinstance(normalized[0], dict)
    assert isinstance(normalized[0]["input"], dict)
    cast(dict[str, Any], normalized[0]["input"])["values"] = []
    assert nested_input["values"] == (1, MappingProxyType({"flag": True}))


def test_normalize_tests_rejects_empty_wrong_shape_unknown_fields_and_non_json_values() -> None:
    recursive: list[Any] = []
    recursive.append(recursive)
    invalid_tests: list[object] = [
        [],
        "tests",
        b"tests",
        {"input": 1, "expected": 1},
        [1],
        [{"input": 1}],
        [{"input": 1, "expected": 1, "extra": 2}],
        [{cast(object, 1): 1, "expected": 1}],
        [{"input": object(), "expected": 1}],
        [{"input": recursive, "expected": 1}],
        [{"input": "\ud800", "expected": 1}],
        [{"input": {"\ud800": 1}, "expected": 1}],
    ]

    for invalid in invalid_tests:
        with pytest.raises(VerificationContractError):
            _normalize_tests(invalid)


def test_normalize_tests_preserves_bool_int_float_type_distinctions() -> None:
    normalized = _normalize_tests(
        [
            {"input": True, "expected": False},
            {"input": 1, "expected": 0},
            {"input": 1.0, "expected": 0.0},
        ]
    )

    assert type(normalized[0]["input"]) is bool
    assert type(normalized[0]["expected"]) is bool
    assert type(normalized[1]["input"]) is int
    assert type(normalized[1]["expected"]) is int
    assert type(normalized[2]["input"]) is float
    assert type(normalized[2]["expected"]) is float


def test_prevalidate_verification_input_returns_normalized_request_without_executor_side_effect() -> None:
    tests = _tests(2)
    request = prevalidate_verification_input(_COMPLETION, tests, "solve", _METADATA)

    assert isinstance(request, VerificationRequest)
    assert request.completion == _COMPLETION
    assert request.tests == tests
    assert request.function_name == "solve"
    assert request.timeout_seconds == 1.5
    assert request.memory_limit_mb == 256
    assert request.parse_result.success is True
    assert request.parse_result.code == _EXTRACTED_CODE

    tests[0]["input"] = "caller mutation"
    assert request.tests == _tests(2)


def test_verify_prevalidated_request_reuses_parser_result_and_skips_executor_for_parse_failure() -> None:
    request = prevalidate_verification_input("explanation only", _tests(1), "solve", _METADATA)

    result = verify_prevalidated_request(request, None)

    assert result.status is ExecutionStatus.PARSE_ERROR
    assert result.parse_error_type == "no_supported_code_block"


def test_resource_limits_accept_wp1_metadata_and_ignore_unrelated_fields() -> None:
    unrelated = object()
    metadata = MappingProxyType(
        {
            "difficulty": "medium",
            "category": unrelated,
            "time_limit_seconds": 1,
            "memory_limit_mb": 256,
            "license": unrelated,
            "source_url_hash": unrelated,
        }
    )

    assert _resource_limits_from_metadata(metadata) == (1.0, 256)


def test_resource_limits_reject_missing_non_finite_non_positive_and_bool_values() -> None:
    invalid_metadata: list[object] = [
        None,
        [],
        {1: 2, "time_limit_seconds": 1.0, "memory_limit_mb": 64},
        {},
        {"time_limit_seconds": 1.0},
        {"memory_limit_mb": 64},
        {"time_limit_seconds": 0.0, "memory_limit_mb": 64},
        {"time_limit_seconds": -1.0, "memory_limit_mb": 64},
        {"time_limit_seconds": float("nan"), "memory_limit_mb": 64},
        {"time_limit_seconds": float("inf"), "memory_limit_mb": 64},
        {"time_limit_seconds": True, "memory_limit_mb": 64},
        {"time_limit_seconds": 10**1000, "memory_limit_mb": 64},
        {"time_limit_seconds": 1.0, "memory_limit_mb": 0},
        {"time_limit_seconds": 1.0, "memory_limit_mb": -1},
        {"time_limit_seconds": 1.0, "memory_limit_mb": True},
        {"time_limit_seconds": 1.0, "memory_limit_mb": 64.0},
    ]

    for invalid in invalid_metadata:
        with pytest.raises(VerificationContractError):
            _resource_limits_from_metadata(invalid)


def test_input_contract_errors_do_not_echo_sentinel_values() -> None:
    sentinel = "PRIVATE_INPUT_SENTINEL_314159"
    invalid_inputs: list[Callable[[], object]] = [
        lambda: _validate_function_name(f"not-valid-{sentinel}"),
        lambda: _normalize_tests([{"input": {sentinel: object()}, "expected": sentinel}]),
        lambda: _resource_limits_from_metadata(
            {"time_limit_seconds": sentinel, "memory_limit_mb": 64, "unrelated": sentinel}
        ),
    ]

    for invalid_call in invalid_inputs:
        with pytest.raises(VerificationContractError) as exc_info:
            invalid_call()
        assert sentinel not in str(exc_info.value)


def test_invalid_inputs_do_not_call_parser_or_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    parser_calls = 0

    def parser_spy(completion: str, expected_function_name: str | None = None) -> ParseResult:
        nonlocal parser_calls
        del completion, expected_function_name
        parser_calls += 1
        return ParseResult(success=False, code="", error_type="invalid_input", num_code_blocks=0)

    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=1,
            returned_statuses=[ExecutionStatus.PASSED],
        )
    )
    monkeypatch.setattr(verifier_module, "extract_python_code", parser_spy)

    with pytest.raises(VerificationContractError):
        verify_completion(_COMPLETION, _tests(1), "not-valid", _METADATA, executor)
    with pytest.raises(VerificationContractError):
        verify_completion(_COMPLETION, [], "solve", _METADATA, executor)
    with pytest.raises(VerificationContractError):
        verify_completion(
            _COMPLETION,
            _tests(1),
            "solve",
            {"time_limit_seconds": 0.0, "memory_limit_mb": 64},
            executor,
        )

    assert parser_calls == 0
    assert executor.calls == []


def test_verify_completion_passes_exact_parser_code_ordered_tests_and_resource_limits_to_executor() -> None:
    tests = _tests(3)
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=3,
            returned_statuses=[ExecutionStatus.PASSED] * 3,
        )
    )

    result = verify_completion(_COMPLETION, tests, "solve", _METADATA, executor)

    assert result.status is ExecutionStatus.PASSED
    assert result.pass_rate == 1.0
    assert executor.calls == [(_EXTRACTED_CODE, "solve", tests, 1.5, 256)]


def test_parse_failure_returns_parse_error_and_never_calls_executor() -> None:
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=2,
            returned_statuses=[ExecutionStatus.PASSED] * 2,
        )
    )

    result = verify_completion("no fenced block", _tests(2), "solve", _METADATA, executor)

    assert result.status is ExecutionStatus.PARSE_ERROR
    assert result.parsed is False
    assert result.executed is False
    assert result.parse_error_type == "no_supported_code_block"
    assert result.failure_counts == (("parse_error", 2),)
    assert executor.calls == []


def test_missing_target_function_preserves_parser_error_taxonomy() -> None:
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=1,
            returned_statuses=[ExecutionStatus.PASSED],
        )
    )
    completion = "```python\ndef other(value):\n    return value\n```\n"

    result = verify_completion(completion, _tests(1), "solve", _METADATA, executor)

    assert result.parse_error_type == "missing_target_function"
    assert result.num_code_blocks == 1
    assert executor.calls == []


def test_full_partial_and_all_failed_results_compute_monotonic_pass_rates() -> None:
    scenarios = [
        (
            ExecutionStatus.PASSED,
            [ExecutionStatus.PASSED, ExecutionStatus.PASSED, ExecutionStatus.PASSED],
            1.0,
        ),
        (
            ExecutionStatus.WRONG_ANSWER,
            [ExecutionStatus.PASSED, ExecutionStatus.WRONG_ANSWER, ExecutionStatus.PASSED],
            2 / 3,
        ),
        (
            ExecutionStatus.WRONG_ANSWER,
            [ExecutionStatus.WRONG_ANSWER] * 3,
            0.0,
        ),
    ]

    rates: list[float] = []
    for status, returned_statuses, expected_rate in scenarios:
        executor = RecordingExecutor(
            _execution_result(status=status, total_tests=3, returned_statuses=returned_statuses)
        )
        result = verify_completion(_COMPLETION, _tests(3), "solve", _METADATA, executor)
        assert result.pass_rate == expected_rate
        rates.append(result.pass_rate)

    assert rates[0] > rates[1] > rates[2]


def test_early_stop_assigns_unexecuted_tests_to_aggregate_failure_status() -> None:
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.TIMEOUT,
            total_tests=3,
            returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.TIMEOUT],
        )
    )

    result = verify_completion(_COMPLETION, _tests(3), "solve", _METADATA, executor)

    assert result.passed_tests == 1
    assert result.pass_rate == 1 / 3
    assert result.failure_counts == (("timeout", 2),)


def test_mixed_test_statuses_are_sorted_and_counted_without_passed_entries() -> None:
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.OUTPUT_LIMIT,
            total_tests=4,
            returned_statuses=[
                ExecutionStatus.WRONG_ANSWER,
                ExecutionStatus.RUNTIME_ERROR,
                ExecutionStatus.TIMEOUT,
            ],
        )
    )

    result = verify_completion(_COMPLETION, _tests(4), "solve", _METADATA, executor)

    assert result.failure_counts == (
        ("output_limit", 1),
        ("runtime_error", 1),
        ("timeout", 1),
        ("wrong_answer", 1),
    )
    assert all(key != "passed" for key, _ in result.failure_counts)


def test_timeout_is_executed_but_not_infrastructure_failure() -> None:
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.TIMEOUT,
            total_tests=2,
            returned_statuses=[ExecutionStatus.TIMEOUT],
        )
    )

    result = verify_completion(_COMPLETION, _tests(2), "solve", _METADATA, executor)

    assert result.status is ExecutionStatus.TIMEOUT
    assert result.executed is True
    assert result.infrastructure_failure is False
    assert result.execution_result is not None


def test_returned_sandbox_error_is_infrastructure_failure() -> None:
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.SANDBOX_ERROR,
            total_tests=2,
            returned_statuses=[ExecutionStatus.SANDBOX_ERROR],
        )
    )

    result = verify_completion(_COMPLETION, _tests(2), "solve", _METADATA, executor)

    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert result.executed is True
    assert result.infrastructure_failure is True
    assert result.execution_result is not None


def test_executor_exception_is_sanitized_sandbox_failure() -> None:
    result = verify_completion(_COMPLETION, _tests(2), "solve", _METADATA, RaisingExecutor())

    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert result.parsed is True
    assert result.executed is False
    assert result.infrastructure_failure is True
    assert result.pass_rate == 0.0
    assert result.failure_counts == (("sandbox_error", 2),)
    assert result.execution_result is None
    assert "PRIVATE_EXECUTOR_EXCEPTION_SENTINEL" not in str(verification_result_to_mapping(result))


def test_malformed_execution_result_fails_closed_as_sandbox_failure() -> None:
    malformed = _execution_result(
        status=ExecutionStatus.WRONG_ANSWER,
        total_tests=2,
        returned_statuses=[ExecutionStatus.WRONG_ANSWER, ExecutionStatus.WRONG_ANSWER],
    )
    malformed = replace(malformed, pass_rate=1.0)

    result = verify_completion(_COMPLETION, _tests(2), "solve", _METADATA, RecordingExecutor(malformed))

    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert result.executed is False
    assert result.total_tests == 2
    assert result.pass_rate == 0.0


@pytest.mark.parametrize(
    ("status", "returned_statuses"),
    [
        (ExecutionStatus.PARSE_ERROR, [ExecutionStatus.PARSE_ERROR]),
        (ExecutionStatus.WRONG_ANSWER, [ExecutionStatus.PARSE_ERROR]),
    ],
)
def test_executor_parse_error_status_fails_closed_as_sandbox_failure(
    status: ExecutionStatus,
    returned_statuses: list[ExecutionStatus],
) -> None:
    malformed = _execution_result(status=status, total_tests=1, returned_statuses=returned_statuses)

    result = verify_completion(_COMPLETION, _tests(1), "solve", _METADATA, RecordingExecutor(malformed))

    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert result.parsed is True
    assert result.executed is False
    assert result.infrastructure_failure is True
    assert result.pass_rate == 0.0
    assert result.failure_counts == (("sandbox_error", 1),)
    assert result.execution_result is None


def test_executor_total_test_mismatch_fails_closed_as_sandbox_failure() -> None:
    mismatched = _execution_result(
        status=ExecutionStatus.PASSED,
        total_tests=1,
        returned_statuses=[ExecutionStatus.PASSED],
    )

    result = verify_completion(_COMPLETION, _tests(2), "solve", _METADATA, RecordingExecutor(mismatched))

    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert result.executed is False
    assert result.total_tests == 2


def test_executor_base_exception_is_not_caught() -> None:
    with pytest.raises(VerifierAbort):
        verify_completion(_COMPLETION, _tests(1), "solve", _METADATA, BaseExceptionExecutor())


def test_verifier_does_not_mutate_caller_tests_or_executor_result() -> None:
    tests = _tests(2)
    original_tests = deepcopy(tests)
    execution_result = _execution_result(
        status=ExecutionStatus.WRONG_ANSWER,
        total_tests=2,
        returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.WRONG_ANSWER],
    )
    executor = RecordingExecutor(execution_result)

    result = verify_completion(_COMPLETION, tests, "solve", _METADATA, executor)
    tests[0]["input"] = "caller mutation"
    execution_result.test_results.clear()

    assert original_tests == executor.calls[0][2]
    assert result.execution_result is not None
    assert len(result.execution_result.test_results) == 2
    assert result.failure_counts == (("wrong_answer", 1),)


def test_non_string_completion_uses_parser_invalid_input_taxonomy() -> None:
    executor = RecordingExecutor(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=1,
            returned_statuses=[ExecutionStatus.PASSED],
        )
    )

    result = verify_completion(cast(str, 123), _tests(1), "solve", _METADATA, executor)

    assert result.status is ExecutionStatus.PARSE_ERROR
    assert result.parse_error_type == "invalid_input"
    assert executor.calls == []
