"""Tests for the public execution contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from code_verifier.execution import ExecutionResult, ExecutionStatus
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult


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
    result = ExecutionTestCaseResult(
        status=ExecutionStatus.PASSED,
        passed=True,
        runtime_ms=1.0,
        stdout="",
        stderr="",
    )

    with pytest.raises(FrozenInstanceError):
        cast(Any, result).runtime_ms = 2.0


def test_execution_result_is_frozen() -> None:
    result = ExecutionResult(
        status=ExecutionStatus.PASSED,
        passed_tests=1,
        total_tests=1,
        pass_rate=1.0,
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(
                status=ExecutionStatus.PASSED,
                passed=True,
                runtime_ms=1.0,
                stdout="",
                stderr="",
            )
        ],
    )

    with pytest.raises(FrozenInstanceError):
        cast(Any, result).pass_rate = 0.0
