"""CPU-only integration tests for the WP4-a parser/verifier/mock pipeline."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.verification import VerificationResult, verification_result_to_mapping, verify_completion


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


def _completion(body: str) -> str:
    return f"analysis before code\n```python\ndef solve(value):\n    {body}\n```\n"


def _tests(*values: int) -> list[dict[str, object]]:
    return [{"input": [value], "expected": value} for value in values]


def _metadata(timeout: float, memory: int) -> dict[str, object]:
    return {
        "time_limit_seconds": timeout,
        "memory_limit_mb": memory,
        "difficulty": "unknown",
        "ignored_private_field": object(),
    }


def _run_five_scenarios() -> tuple[list[VerificationResult], MockExecutor, list[list[dict[str, object]]]]:
    selected_tests = [
        _tests(1, 2),
        _tests(3, 4),
        _tests(5, 6, 7),
        _tests(8, 9),
        _tests(10),
    ]
    executor = MockExecutor(
        [
            _execution_result(
                status=ExecutionStatus.PASSED,
                total_tests=2,
                returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.PASSED],
            ),
            _execution_result(
                status=ExecutionStatus.WRONG_ANSWER,
                total_tests=2,
                returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.WRONG_ANSWER],
            ),
            _execution_result(
                status=ExecutionStatus.TIMEOUT,
                total_tests=3,
                returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.TIMEOUT],
            ),
            _execution_result(
                status=ExecutionStatus.SANDBOX_ERROR,
                total_tests=1,
                returned_statuses=[ExecutionStatus.SANDBOX_ERROR],
            ),
        ]
    )
    completions = [
        _completion('raise AssertionError("MOCK_MUST_NOT_EXECUTE_1")'),
        _completion("return value + 1"),
        _completion("while True: pass"),
        "```python\ndef other(value):\n    return value\n```\n",
        _completion('raise AssertionError("MOCK_MUST_NOT_EXECUTE_5")'),
    ]
    metadata = [
        _metadata(1.0, 64),
        _metadata(1.5, 128),
        _metadata(2.0, 256),
        _metadata(2.5, 512),
        _metadata(3.0, 1024),
    ]

    results = [
        verify_completion(completions[index], selected_tests[index], "solve", metadata[index], executor)
        for index in range(5)
    ]
    return results, executor, selected_tests


def _all_mapping_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                keys.add(key)
            keys.update(_all_mapping_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_all_mapping_keys(item))
    return keys


def test_wp4a_completion_parser_verifier_mock_pipeline_preserves_contracts() -> None:
    results, executor, selected_tests = _run_five_scenarios()

    assert [result.status for result in results] == [
        ExecutionStatus.PASSED,
        ExecutionStatus.WRONG_ANSWER,
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.PARSE_ERROR,
        ExecutionStatus.SANDBOX_ERROR,
    ]
    assert [result.pass_rate for result in results] == [1.0, 0.5, 1 / 3, 0.0, 0.0]
    assert results[2].failure_counts == (("timeout", 2),)
    assert results[3].parse_error_type == "missing_target_function"
    assert results[4].infrastructure_failure is True

    calls = executor.calls
    assert len(calls) == 4
    assert executor.remaining_results == 0
    assert calls[0].code == 'def solve(value):\n    raise AssertionError("MOCK_MUST_NOT_EXECUTE_1")\n'
    assert calls[1].code == "def solve(value):\n    return value + 1\n"
    assert calls[2].code == "def solve(value):\n    while True: pass\n"
    assert calls[3].code == 'def solve(value):\n    raise AssertionError("MOCK_MUST_NOT_EXECUTE_5")\n'
    assert [call.function_name for call in calls] == ["solve"] * 4
    assert [call.tests for call in calls] == [
        selected_tests[0],
        selected_tests[1],
        selected_tests[2],
        selected_tests[4],
    ]
    assert [(call.timeout_seconds, call.memory_limit_mb) for call in calls] == [
        (1.0, 64),
        (1.5, 128),
        (2.0, 256),
        (3.0, 1024),
    ]


def test_wp4a_verifier_results_are_finite_json_safe_and_payload_free() -> None:
    results, _, _ = _run_five_scenarios()
    forbidden_keys = {"completion", "code", "tests", "metadata", "function_name"}

    for result in results:
        mapping = verification_result_to_mapping(result)
        serialized = json.dumps(mapping, allow_nan=False)
        assert math.isfinite(result.pass_rate)
        assert sum(count for _, count in result.failure_counts) == result.total_tests - result.passed_tests
        assert forbidden_keys.isdisjoint(_all_mapping_keys(mapping))
        assert "MOCK_MUST_NOT_EXECUTE" not in serialized
        assert "ignored_private_field" not in serialized


def test_wp4a_parse_failure_does_not_consume_mock_result() -> None:
    executor = MockExecutor(
        [
            _execution_result(
                status=ExecutionStatus.PASSED,
                total_tests=1,
                returned_statuses=[ExecutionStatus.PASSED],
            )
        ]
    )
    tests: list[dict[str, Any]] = [{"input": [1], "expected": 1}]
    metadata = _metadata(1.0, 64)

    parse_failure = verify_completion(
        "```python\ndef other(value):\n    return value\n```\n",
        tests,
        "solve",
        metadata,
        executor,
    )

    assert parse_failure.status is ExecutionStatus.PARSE_ERROR
    assert executor.remaining_results == 1
    assert executor.calls == ()

    passed = verify_completion(_completion("return value"), tests, "solve", metadata, executor)

    assert passed.status is ExecutionStatus.PASSED
    assert executor.remaining_results == 0
    assert len(executor.calls) == 1
