"""CPU-only integration tests for WP4-b reward pipelines and source isolation."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from code_verifier.execution import (
    ExecutionResult,
    ExecutionStatus,
    MockExecutor,
    PistonExecutor,
    PistonExecutorConfig,
)
from code_verifier.execution import (
    TestCaseResult as ExecutionTestCaseResult,
)
from code_verifier.rewards import (
    RewardContractError,
    compute_code_rewards,
    hidden_code_reward,
    public_code_reward,
)


def _test_result(status: ExecutionStatus) -> ExecutionTestCaseResult:
    return ExecutionTestCaseResult(
        status=status,
        passed=status is ExecutionStatus.PASSED,
        runtime_ms=1.0,
        stdout="STDOUT_SECRET",
        stderr="STDERR_SECRET",
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


def _completion(body: str = "return value") -> str:
    return f"```python\ndef solve(value):\n    {body}\n```\n"


def _chat_completion(body: str = "return value") -> list[dict[str, str]]:
    return [
        {"role": "assistant", "content": "discarded earlier message"},
        {"role": "assistant", "content": _completion(body)},
    ]


def _tests(*values: int, marker: str = "") -> list[dict[str, object]]:
    return [{"input": [value, marker], "expected": {"value": value, "marker": marker}} for value in values]


def _simple_tests(*values: int) -> list[dict[str, object]]:
    return [{"input": [value], "expected": value} for value in values]


def _metadata() -> dict[str, object]:
    return {
        "time_limit_seconds": 1.5,
        "memory_limit_mb": 128,
        "private_metadata": "METADATA_SECRET",
    }


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


class _RaisingExecutor:
    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        raise RuntimeError("EXECUTOR_EXCEPTION_SECRET")


class _SequencePistonTransport:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.execute_calls = 0

    def list_runtimes(self, *, timeout_seconds: float, max_response_bytes: int) -> object:
        return [{"language": "python", "version": "3.10.0", "aliases": ["py3"], "runtime": "python"}]

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        response = self._responses[self.execute_calls]
        self.execute_calls += 1
        return response


def _piston_response(*, outcome: str = "passed", status: str | None = None, code: int | None = 0) -> dict[str, object]:
    marker = "fixedmarker123"
    report = json.dumps(
        {"outcome": outcome, "runtime_ms": 1.0, "stdout": "", "stderr": ""},
        separators=(",", ":"),
    )
    stdout = f"__CODE_VERIFIER_RESULT__:{marker}:{report}\n" if status is None else ""
    return {
        "language": "python",
        "version": "3.10.0",
        "run": {
            "stdout": stdout,
            "stderr": "",
            "code": code,
            "signal": None,
            "message": None,
            "status": status,
            "cpu_time": 1.0,
            "wall_time": 2.0,
            "memory": 1024,
        },
    }


def _piston_executor(responses: list[object]) -> tuple[PistonExecutor, _SequencePistonTransport]:
    transport = _SequencePistonTransport(responses)
    config = PistonExecutorConfig(
        base_url="http://127.0.0.1:2000",
        language="python",
        version="3.10.0",
        request_timeout_margin_seconds=2.0,
        max_response_bytes=131072,
        max_output_bytes=65536,
        stop_on_first_failure=False,
    )
    return PistonExecutor(config, transport=transport, marker_factory=lambda: "fixedmarker123"), transport


def test_wp4b_public_reward_chat_completion_visible_test_pipeline() -> None:
    visible_tests = _simple_tests(1, 2)
    result = _execution_result(
        status=ExecutionStatus.PASSED,
        total_tests=2,
        returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.PASSED],
    )
    executor = MockExecutor([result])

    rewards = public_code_reward(
        [_chat_completion()],
        [visible_tests],
        ["solve"],
        [_metadata()],
        executor=executor,
        problem_id=["problem-public"],
    )

    assert rewards == pytest.approx([1.1])
    assert len(executor.calls) == 1
    assert executor.calls[0].tests == visible_tests
    assert executor.calls[0].code == "def solve(value):\n    return value\n"


def test_wp4b_hidden_reward_uses_train_hidden_and_ignores_visible_column() -> None:
    visible_tests = _tests(1, marker="VISIBLE_SENTINEL")
    train_hidden_tests = _tests(1, marker="TRAIN_HIDDEN_SENTINEL")
    result = _execution_result(
        status=ExecutionStatus.PASSED,
        total_tests=1,
        returned_statuses=[ExecutionStatus.PASSED],
    )
    executor = MockExecutor([result])

    rewards = hidden_code_reward(
        [_chat_completion()],
        [train_hidden_tests],
        ["solve"],
        [_metadata()],
        executor=executor,
        visible_tests=[visible_tests],
    )

    assert rewards == pytest.approx([1.1])
    assert len(executor.calls) == 1
    assert executor.calls[0].tests == train_hidden_tests
    assert executor.calls[0].tests != visible_tests


def test_wp4b_reward_failure_statuses_and_component_records_match_spec() -> None:
    selected_tests = [
        _simple_tests(1, 2),
        _simple_tests(3, 4),
        _simple_tests(5, 6),
        _simple_tests(7),
        _simple_tests(8, 9),
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
                total_tests=2,
                returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.TIMEOUT],
            ),
            _execution_result(
                status=ExecutionStatus.SANDBOX_ERROR,
                total_tests=2,
                returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.SANDBOX_ERROR],
            ),
        ]
    )
    completions: list[object] = [
        _chat_completion(),
        _chat_completion("return value + 1"),
        _completion("while True: pass"),
        "```python\ndef other(value):\n    return value\n```\n",
        _chat_completion('raise AssertionError("MUST_NOT_EXECUTE")'),
    ]

    rewards, records = compute_code_rewards(
        completions,
        selected_tests,
        ["solve"] * 5,
        [_metadata()] * 5,
        executor,
        "public",
    )

    assert rewards == pytest.approx([1.1, 0.6, 0.4, -0.1, 0.0])
    assert [record["status"] for record in records] == [
        "passed",
        "wrong_answer",
        "timeout",
        "parse_error",
        "sandbox_error",
    ]
    assert records[2]["timeout_penalty"] == -0.2
    assert records[3]["invalid_format_penalty"] == -0.1
    assert records[4]["infrastructure_failure"] is True
    assert records[4]["passed_tests"] == 1
    assert records[4]["test_reward"] == 0.0
    assert records[4]["executable_reward"] == 0.0
    assert len(executor.calls) == 4

    exception_rewards, exception_records = compute_code_rewards(
        [_completion()],
        [_simple_tests(1)],
        ["solve"],
        [_metadata()],
        _RaisingExecutor(),
        "hidden",
    )
    assert exception_rewards == [0.0]
    assert exception_records[0]["status"] == "sandbox_error"


def test_wp4b_piston_nested_sandbox_failure_clears_positive_reward() -> None:
    executor, transport = _piston_executor(
        [
            _piston_response(outcome="wrong_answer"),
            _piston_response(outcome="passed"),
            _piston_response(status="XX", code=None),
        ]
    )
    rewards, records = compute_code_rewards(
        [_completion()],
        [_simple_tests(1, 2, 3)],
        ["solve"],
        [_metadata()],
        executor,
        "public",
    )

    assert rewards == [0.0]
    assert transport.execute_calls == 3
    assert records[0]["status"] == "sandbox_error"
    assert records[0]["passed_tests"] == 1
    assert records[0]["failure_counts"] == {"sandbox_error": 1, "wrong_answer": 1}
    assert records[0]["infrastructure_failure"] is True
    assert records[0]["infrastructure_failure_kind"] == "piston_internal"
    assert records[0]["test_reward"] == 0.0
    assert records[0]["executable_reward"] == 0.0


def test_wp4b_piston_nested_timeout_applies_timeout_penalty() -> None:
    executor, transport = _piston_executor(
        [
            _piston_response(outcome="wrong_answer"),
            _piston_response(status="TO", code=None),
        ]
    )
    rewards, records = compute_code_rewards(
        [_completion()],
        [_simple_tests(1, 2)],
        ["solve"],
        [_metadata()],
        executor,
        "hidden",
    )

    assert rewards == pytest.approx([-0.1])
    assert transport.execute_calls == 2
    assert records[0]["status"] == "wrong_answer"
    assert records[0]["failure_counts"] == {"timeout": 1, "wrong_answer": 1}
    assert records[0]["infrastructure_failure"] is False
    assert records[0]["test_reward"] == 0.0
    assert records[0]["executable_reward"] == 0.1
    assert records[0]["timeout_penalty"] == -0.2


def test_wp4b_training_reward_paths_reject_eval_hidden_before_execution() -> None:
    eval_hidden = [[{"input": ["EVAL_HIDDEN_SECRET"], "expected": "EVAL_HIDDEN_SECRET"}]]

    public_executor = MockExecutor([])
    with pytest.raises(RewardContractError):
        public_code_reward(
            [_completion()],
            [_simple_tests(1)],
            ["solve"],
            [_metadata()],
            executor=public_executor,
            eval_hidden_tests=eval_hidden,
        )
    assert public_executor.calls == ()

    hidden_executor = MockExecutor([])
    with pytest.raises(RewardContractError):
        hidden_code_reward(
            [_completion()],
            [_simple_tests(1)],
            ["solve"],
            [_metadata()],
            executor=hidden_executor,
            eval_hidden_tests=eval_hidden,
        )
    assert hidden_executor.calls == ()


def test_wp4b_rewards_and_component_records_align_exactly_with_batch() -> None:
    results = [
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=1,
            returned_statuses=[ExecutionStatus.PASSED],
        ),
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            total_tests=1,
            returned_statuses=[ExecutionStatus.WRONG_ANSWER],
        ),
        _execution_result(
            status=ExecutionStatus.RUNTIME_ERROR,
            total_tests=1,
            returned_statuses=[ExecutionStatus.RUNTIME_ERROR],
        ),
    ]
    rewards, records = compute_code_rewards(
        [_completion(), _chat_completion(), _completion("raise ValueError()")],
        [_simple_tests(1), _simple_tests(2), _simple_tests(3)],
        ["solve", "solve", "solve"],
        [_metadata(), _metadata(), _metadata()],
        MockExecutor(results),
        "hidden",
    )
    assert len(rewards) == len(records) == 3
    for reward, record in zip(rewards, records, strict=True):
        assert reward == record["total_reward"]
        assert math.isfinite(reward)


def test_wp4b_component_records_are_finite_json_safe_and_payload_free() -> None:
    completion_sentinel = "COMPLETION_SECRET"
    test_sentinel = "TEST_SECRET"
    completion = _completion(f"return value  # {completion_sentinel}")
    tests = [{"input": [test_sentinel], "expected": test_sentinel}]
    result = _execution_result(
        status=ExecutionStatus.WRONG_ANSWER,
        total_tests=1,
        returned_statuses=[ExecutionStatus.WRONG_ANSWER],
    )
    rewards, records = compute_code_rewards(
        [completion],
        [tests],
        ["solve"],
        [_metadata()],
        MockExecutor([result]),
        "public",
    )
    serialized = json.dumps(records, allow_nan=False)
    forbidden_keys = {"completion", "code", "tests", "function_name", "metadata", "execution_result"}

    assert math.isfinite(rewards[0])
    assert forbidden_keys.isdisjoint(_all_mapping_keys(records))
    for sentinel in (
        completion_sentinel,
        test_sentinel,
        "METADATA_SECRET",
        "STDOUT_SECRET",
        "STDERR_SECRET",
    ):
        assert sentinel not in serialized
