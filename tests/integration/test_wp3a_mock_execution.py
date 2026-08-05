"""WP3-a integration test for parser output and the non-executing contract."""

from __future__ import annotations

import json
from typing import Any

from code_verifier.data import TestCase as DataTestCase
from code_verifier.data.schema import test_case_to_mapping as data_test_case_to_mapping
from code_verifier.execution import (
    CodeExecutor,
    ExecutionResult,
    ExecutionStatus,
    MockExecutor,
    execution_result_to_mapping,
)
from code_verifier.execution import (
    TestCaseResult as ExecutionTestCaseResult,
)
from code_verifier.parsing import extract_python_code


def test_parser_output_flows_through_code_executor_contract() -> None:
    """Parse one completion, send its code to a typed MockExecutor, and serialize the result."""
    completion = """Reasoning before the answer.
```python
def solve(value):
    return value + 1
```
"""
    parsed = extract_python_code(completion, expected_function_name="solve")
    assert parsed.success

    tests: list[dict[str, Any]] = [data_test_case_to_mapping(DataTestCase(input=1, expected=2))]
    configured_result = ExecutionResult(
        status=ExecutionStatus.PASSED,
        passed_tests=1,
        total_tests=1,
        pass_rate=1.0,
        runtime_ms=0.5,
        test_results=[
            ExecutionTestCaseResult(
                status=ExecutionStatus.PASSED,
                passed=True,
                runtime_ms=0.5,
                stdout="",
                stderr="",
            )
        ],
    )
    mock = MockExecutor([configured_result])
    executor: CodeExecutor = mock

    result = executor.execute(parsed.code, "solve", tests, timeout_seconds=1.0, memory_limit_mb=64)

    assert mock.calls[0].code == parsed.code
    assert mock.calls[0].tests == tests
    mapping = execution_result_to_mapping(result)
    assert json.loads(json.dumps(mapping, allow_nan=False)) == mapping
