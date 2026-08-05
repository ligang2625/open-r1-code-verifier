"""Public execution contracts shared by sandbox implementations and test doubles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


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
