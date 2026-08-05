"""Tests for the deterministic non-executing MockExecutor."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from code_verifier.execution import (
    CodeExecutor,
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    MockExecutor,
)
from code_verifier.execution import (
    TestCaseResult as ExecutionTestCaseResult,
)


def _test_result(status: ExecutionStatus = ExecutionStatus.PASSED) -> ExecutionTestCaseResult:
    return ExecutionTestCaseResult(
        status=status,
        passed=status is ExecutionStatus.PASSED,
        runtime_ms=1.0,
        stdout="",
        stderr="",
    )


def _execution_result(status: ExecutionStatus = ExecutionStatus.PASSED) -> ExecutionResult:
    if status is ExecutionStatus.PASSED:
        return ExecutionResult(
            status=status,
            passed_tests=1,
            total_tests=1,
            pass_rate=1.0,
            runtime_ms=1.0,
            test_results=[_test_result()],
        )
    return ExecutionResult(
        status=status,
        passed_tests=0,
        total_tests=1,
        pass_rate=0.0,
        runtime_ms=1.0,
        test_results=[_test_result(status)],
    )


def _execute(
    executor: MockExecutor,
    *,
    code: str = "def solve(value):\n    return value\n",
    tests: list[dict[str, Any]] | None = None,
) -> ExecutionResult:
    return executor.execute(
        code=code,
        function_name="solve",
        tests=[{"input": 1, "expected": 1}] if tests is None else tests,
        timeout_seconds=1.0,
        memory_limit_mb=64,
    )


def test_mock_executor_consumes_results_in_fifo_order() -> None:
    first = _execution_result()
    second = _execution_result(ExecutionStatus.TIMEOUT)
    executor = MockExecutor([first, second])

    assert _execute(executor) == first
    assert _execute(executor) == second


def test_mock_executor_records_every_valid_call() -> None:
    executor = MockExecutor([_execution_result(), _execution_result()])

    _execute(executor, code="first code", tests=[{"input": [1], "expected": 1}])
    _execute(executor, code="second code", tests=[{"input": [2], "expected": 2}])

    assert [call.code for call in executor.calls] == ["first code", "second code"]
    assert [call.tests for call in executor.calls] == [
        [{"input": [1], "expected": 1}],
        [{"input": [2], "expected": 2}],
    ]


def test_mock_executor_remaining_results_tracks_queue() -> None:
    executor = MockExecutor([_execution_result(), _execution_result(ExecutionStatus.TIMEOUT)])

    assert executor.remaining_results == 2
    _execute(executor)
    assert executor.remaining_results == 1
    _execute(executor)
    assert executor.remaining_results == 0


def test_mock_executor_rejects_invalid_preconfigured_result() -> None:
    invalid_result = replace(_execution_result(), pass_rate=0.5)

    with pytest.raises(ExecutionContractError):
        MockExecutor([invalid_result])


def test_mock_executor_rejects_invalid_request_without_consuming_result() -> None:
    executor = MockExecutor([_execution_result()])

    with pytest.raises(ExecutionContractError):
        executor.execute("", "solve", [], 1.0, 64)

    assert executor.remaining_results == 1
    assert executor.calls == ()


def test_mock_executor_exhaustion_raises_without_recording_call() -> None:
    executor = MockExecutor([])

    with pytest.raises(AssertionError, match="no configured results remaining"):
        _execute(executor)

    assert executor.calls == ()


def test_mock_executor_defensively_copies_request_tests() -> None:
    executor = MockExecutor([_execution_result()])
    tests: list[dict[str, Any]] = [{"input": {"items": [1, 2]}, "expected": 2}]

    _execute(executor, tests=tests)
    cast(list[int], cast(dict[str, Any], tests[0]["input"])["items"]).append(3)

    assert executor.calls[0].tests == [{"input": {"items": [1, 2]}, "expected": 2}]


def test_mock_executor_defensively_copies_returned_result() -> None:
    source = _execution_result()
    executor = MockExecutor([source, source])

    first = _execute(executor)
    first.test_results.clear()
    second = _execute(executor)

    assert len(second.test_results) == 1
    assert len(source.test_results) == 1


def test_mock_executor_calls_property_cannot_mutate_history() -> None:
    executor = MockExecutor([_execution_result()])
    _execute(executor, tests=[{"input": {"items": [1]}, "expected": 1}])

    calls = executor.calls
    cast(list[int], cast(dict[str, Any], calls[0].tests[0]["input"])["items"]).append(2)

    assert executor.calls[0].tests == [{"input": {"items": [1]}, "expected": 1}]


def test_mock_executor_never_executes_code_string(tmp_path: Path) -> None:
    sentinel_path = tmp_path / "mock-must-not-create.txt"
    code = f"from pathlib import Path\nPath({str(sentinel_path)!r}).write_text('created')\n"
    executor = MockExecutor([_execution_result()])

    _execute(executor, code=code)

    assert not sentinel_path.exists()


def _run_through_protocol(executor: CodeExecutor) -> ExecutionResult:
    return executor.execute(
        code="def solve(value):\n    return value\n",
        function_name="solve",
        tests=[{"input": 1, "expected": 1}],
        timeout_seconds=1.0,
        memory_limit_mb=64,
    )


def test_mock_executor_satisfies_code_executor_protocol_under_mypy() -> None:
    executor: CodeExecutor = MockExecutor([_execution_result()])

    assert _run_through_protocol(executor).status is ExecutionStatus.PASSED
