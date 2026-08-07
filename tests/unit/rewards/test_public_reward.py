"""Unit tests for the Public-RLVR reward wrapper."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

import code_verifier.rewards.public_reward as public_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.rewards.common import RewardContractError
from code_verifier.rewards.public_reward import public_code_reward


def _result(status: ExecutionStatus = ExecutionStatus.PASSED) -> ExecutionResult:
    test_result = ExecutionTestCaseResult(
        status=status,
        passed=status is ExecutionStatus.PASSED,
        runtime_ms=1.0,
        stdout="",
        stderr="",
    )
    passed = 1 if test_result.passed else 0
    return ExecutionResult(
        status=status,
        passed_tests=passed,
        total_tests=1,
        pass_rate=float(passed),
        runtime_ms=1.0,
        test_results=[test_result],
    )


def _completion() -> str:
    return "```python\ndef solve(value):\n    return value\n```\n"


def _tests(expected: object = 1) -> list[dict[str, object]]:
    return [{"input": [1], "expected": expected}]


def _metadata() -> dict[str, object]:
    return {"time_limit_seconds": 1.0, "memory_limit_mb": 64}


def test_public_reward_passes_visible_tests_to_common_with_public_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    executor = MockExecutor([])
    visible = [_tests()]

    def fake_compute(
        completions: object,
        tests_batch: object,
        function_names: object,
        metadata_batch: object,
        received_executor: object,
        mode: str,
    ) -> tuple[list[float], list[dict[str, object]]]:
        captured.update(
            completions=completions,
            tests_batch=tests_batch,
            function_names=function_names,
            metadata_batch=metadata_batch,
            executor=received_executor,
            mode=mode,
        )
        return [0.25], [{"mode": mode}]

    monkeypatch.setattr(public_module, "compute_code_rewards", fake_compute)
    rewards = public_code_reward(
        [_completion()],
        visible,
        ["solve"],
        [_metadata()],
        executor=executor,
    )
    assert rewards == [0.25]
    assert captured["tests_batch"] is visible
    assert captured["executor"] is executor
    assert captured["mode"] == "public"


@pytest.mark.parametrize("forbidden_field", ["train_hidden_tests", "eval_hidden_tests"])
def test_public_reward_rejects_hidden_fields_before_any_execution(forbidden_field: str) -> None:
    executor = MockExecutor([])
    kwargs = {"executor": executor, forbidden_field: [[{"input": [9], "expected": 9}]]}
    with pytest.raises(RewardContractError):
        public_code_reward([_completion()], [_tests()], ["solve"], [_metadata()], **kwargs)
    assert executor.calls == ()


def test_public_reward_ignores_non_test_dataset_columns() -> None:
    executor = MockExecutor([_result()])
    rewards = public_code_reward(
        [_completion()],
        [_tests()],
        ["solve"],
        [_metadata()],
        executor=executor,
        problem_id=["problem-1"],
        prompt=[[{"role": "user", "content": "PROMPT_SECRET"}]],
        function_signature=["solve(value)"],
    )
    assert rewards == [pytest.approx(1.1)]
    assert executor.calls[0].tests == _tests()


def test_public_reward_requires_bound_executor() -> None:
    with pytest.raises(RewardContractError):
        public_code_reward([_completion()], [_tests()], ["solve"], [_metadata()])
    with pytest.raises(RewardContractError):
        public_code_reward([_completion()], [_tests()], ["solve"], [_metadata()], executor=object())


def test_public_reward_returns_only_float_list_and_preserves_batch_length() -> None:
    results: Sequence[ExecutionResult] = [_result(), _result(ExecutionStatus.WRONG_ANSWER)]
    executor = MockExecutor(results)
    rewards = public_code_reward(
        [_completion(), _completion()],
        [_tests(), _tests()],
        ["solve", "solve"],
        [_metadata(), _metadata()],
        executor=executor,
    )
    assert len(rewards) == 2
    assert all(isinstance(value, float) for value in rewards)
    assert rewards == pytest.approx([1.1, 0.1])


def test_public_reward_forbidden_field_error_does_not_echo_hidden_payload() -> None:
    sentinel = "HIDDEN_TEST_SECRET"
    executor = MockExecutor([])
    with pytest.raises(RewardContractError) as exc_info:
        public_code_reward(
            [_completion()],
            [_tests()],
            ["solve"],
            [_metadata()],
            executor=executor,
            train_hidden_tests=[[{"input": [sentinel], "expected": sentinel}]],
        )
    assert sentinel not in str(exc_info.value)
    assert executor.calls == ()
