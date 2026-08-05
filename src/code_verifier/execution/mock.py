"""Deterministic non-executing test double for the execution contract."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from code_verifier.execution.base import (
    ExecutionResult,
    validate_execution_request,
    validate_execution_result,
)


@dataclass(frozen=True)
class MockExecutionCall:
    """One validated request recorded by ``MockExecutor``."""

    code: str
    function_name: str
    tests: list[dict[str, Any]]
    timeout_seconds: float
    memory_limit_mb: int


class MockExecutor:
    """Return validated preconfigured results without executing supplied code."""

    def __init__(self, results: Sequence[ExecutionResult]) -> None:
        """Create a non-executing FIFO test double from validated results."""
        copied_results: list[ExecutionResult] = []
        for result in results:
            copied_result = deepcopy(result)
            validate_execution_result(copied_result)
            copied_results.append(copied_result)
        self._results = deque(copied_results)
        self._calls: list[MockExecutionCall] = []

    @property
    def calls(self) -> tuple[MockExecutionCall, ...]:
        """Return defensive copies of all successfully recorded calls."""
        return tuple(deepcopy(self._calls))

    @property
    def remaining_results(self) -> int:
        """Return the number of queued results not yet consumed."""
        return len(self._results)

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        """Validate and record one request, then return the next configured result."""
        validate_execution_request(code, function_name, tests, timeout_seconds, memory_limit_mb)
        if not self._results:
            raise AssertionError("MockExecutor has no configured results remaining")

        self._calls.append(
            MockExecutionCall(
                code=code,
                function_name=function_name,
                tests=deepcopy(tests),
                timeout_seconds=timeout_seconds,
                memory_limit_mb=memory_limit_mb,
            )
        )
        return deepcopy(self._results.popleft())
