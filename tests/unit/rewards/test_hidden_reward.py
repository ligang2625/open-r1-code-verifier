"""Unit tests for the Hidden-RLVR reward wrapper."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

import code_verifier.rewards.hidden_reward as hidden_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.rewards.common import RewardContractError, compute_code_rewards
from code_verifier.rewards.hidden_reward import hidden_code_reward


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


def test_hidden_reward_passes_train_hidden_tests_to_common_with_hidden_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    executor = MockExecutor([])
    hidden = [_tests()]

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
        return [0.75], [{"mode": mode}]

    monkeypatch.setattr(hidden_module, "compute_code_rewards", fake_compute)
    rewards = hidden_code_reward(
        [_completion()],
        hidden,
        ["solve"],
        [_metadata()],
        executor=executor,
    )
    assert rewards == [0.75]
    assert captured["tests_batch"] is hidden
    assert captured["executor"] is executor
    assert captured["mode"] == "hidden"


def test_hidden_reward_rejects_eval_hidden_tests_before_any_execution() -> None:
    executor = MockExecutor([])
    with pytest.raises(RewardContractError):
        hidden_code_reward(
            [_completion()],
            [_tests()],
            ["solve"],
            [_metadata()],
            executor=executor,
            eval_hidden_tests=[[{"input": [99], "expected": 99}]],
        )
    assert executor.calls == ()


def test_hidden_reward_ignores_visible_tests_column_and_never_uses_it_for_scoring() -> None:
    hidden_tests = _tests(expected="HIDDEN_EXPECTED")
    visible_tests = _tests(expected="VISIBLE_SENTINEL")
    executor = MockExecutor([_result()])
    rewards = hidden_code_reward(
        [_completion()],
        [hidden_tests],
        ["solve"],
        [_metadata()],
        executor=executor,
        visible_tests=[visible_tests],
    )
    assert rewards == pytest.approx([1.1])
    assert executor.calls[0].tests == hidden_tests
    assert executor.calls[0].tests != visible_tests


def test_hidden_reward_requires_bound_executor() -> None:
    with pytest.raises(RewardContractError):
        hidden_code_reward([_completion()], [_tests()], ["solve"], [_metadata()])
    with pytest.raises(RewardContractError):
        hidden_code_reward([_completion()], [_tests()], ["solve"], [_metadata()], executor=object())


def test_hidden_reward_returns_only_float_list_and_preserves_batch_length() -> None:
    results: Sequence[ExecutionResult] = [_result(), _result(ExecutionStatus.WRONG_ANSWER)]
    executor = MockExecutor(results)
    rewards = hidden_code_reward(
        [_completion(), _completion()],
        [_tests(), _tests()],
        ["solve", "solve"],
        [_metadata(), _metadata()],
        executor=executor,
        visible_tests=[_tests("VISIBLE_A"), _tests("VISIBLE_B")],
    )
    assert len(rewards) == 2
    assert all(isinstance(value, float) for value in rewards)
    assert rewards == pytest.approx([1.1, 0.1])


def test_public_and_hidden_common_auxiliary_components_are_identical_for_same_verification_result() -> None:
    result = _result(ExecutionStatus.WRONG_ANSWER)
    public_rewards, public_records = compute_code_rewards(
        [_completion()],
        [_tests()],
        ["solve"],
        [_metadata()],
        MockExecutor([result]),
        "public",
    )
    hidden_rewards, hidden_records = compute_code_rewards(
        [_completion()],
        [_tests()],
        ["solve"],
        [_metadata()],
        MockExecutor([result]),
        "hidden",
    )
    assert public_rewards == hidden_rewards
    public_record = dict(public_records[0])
    hidden_record = dict(hidden_records[0])
    assert public_record.pop("mode") == "public"
    assert hidden_record.pop("mode") == "hidden"
    assert public_record == hidden_record


def test_hidden_reward_eval_hidden_error_does_not_echo_payload() -> None:
    sentinel = "EVAL_HIDDEN_SECRET"
    executor = MockExecutor([])
    with pytest.raises(RewardContractError) as exc_info:
        hidden_code_reward(
            [_completion()],
            [_tests()],
            ["solve"],
            [_metadata()],
            executor=executor,
            eval_hidden_tests=[[{"input": [sentinel], "expected": sentinel}]],
        )
    assert sentinel not in str(exc_info.value)
    assert executor.calls == ()
