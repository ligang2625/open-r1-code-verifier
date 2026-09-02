"""Unit tests for shared reward contracts, scoring, and component records."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from typing import Any

import pytest

import code_verifier.rewards.common as common_module
from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.rewards.common import (
    RewardContractError,
    _extract_completion_text,
    _require_executor,
    _validate_batch_alignment,
    compute_code_rewards,
    compute_code_rewards_concurrent,
)


class _ExecutorLike:
    def execute(self, *args: object, **kwargs: object) -> object:
        return object()


class _RaisingExecutor:
    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        raise RuntimeError("EXECUTOR_SECRET")


class _DelayedByCodeExecutor:
    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        del function_name, timeout_seconds, memory_limit_mb
        if "+ 1" not in code:
            time.sleep(0.01)
        status = ExecutionStatus.WRONG_ANSWER if "+ 1" in code else ExecutionStatus.PASSED
        return _execution_result(status=status, total_tests=len(tests), returned_statuses=[status] * len(tests))


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


def _completion(body: str = "return value") -> str:
    return f"```python\ndef solve(value):\n    {body}\n```\n"


def _tests(count: int = 2) -> list[dict[str, object]]:
    return [{"input": [index], "expected": index} for index in range(count)]


def _metadata() -> dict[str, object]:
    return {"time_limit_seconds": 1.0, "memory_limit_mb": 64, "ignored": "DATASET_SECRET"}


def _compute_one(
    execution_result: ExecutionResult,
    *,
    completion: object | None = None,
    mode: str = "public",
) -> tuple[float, dict[str, object], MockExecutor]:
    executor = MockExecutor([execution_result])
    reward_values, records = compute_code_rewards(
        [_completion() if completion is None else completion],
        [_tests(execution_result.total_tests)],
        ["solve"],
        [_metadata()],
        executor,
        mode,
    )
    return reward_values[0], records[0], executor


@pytest.mark.parametrize(
    ("tests_batch", "function_names", "metadata_batch"),
    [
        ([], [], []),
        ([[{"input": [1], "expected": 1}]], ["solve"], [{"time_limit_seconds": 1.0}]),
    ],
)
def test_batch_alignment_accepts_equal_lengths_and_empty_batch(
    tests_batch: Sequence[object],
    function_names: Sequence[object],
    metadata_batch: Sequence[object],
) -> None:
    completions = [] if not tests_batch else ["completion"]
    assert _validate_batch_alignment(completions, tests_batch, function_names, metadata_batch) == len(completions)


@pytest.mark.parametrize(
    ("tests_batch", "function_names", "metadata_batch"),
    [
        ([], ["solve"], [{}]),
        ([[{"input": [1], "expected": 1}]], [], [{}]),
        ([[{"input": [1], "expected": 1}]], ["solve"], []),
        ([[{"input": [1], "expected": 1}], [{"input": [2], "expected": 2}]], ["solve"], [{}]),
    ],
)
def test_batch_alignment_rejects_each_length_mismatch_without_zip_truncation(
    tests_batch: Sequence[object],
    function_names: Sequence[object],
    metadata_batch: Sequence[object],
) -> None:
    with pytest.raises(RewardContractError):
        _validate_batch_alignment(["completion"], tests_batch, function_names, metadata_batch)


def test_completion_text_accepts_raw_string_without_normalization() -> None:
    raw = "  你好\r\n```python\ndef solve():\n    return 1\n```  "
    assert _extract_completion_text(raw) == raw


def test_completion_text_accepts_pinned_open_r1_chat_shape_and_uses_last_message_content() -> None:
    item = [
        {"role": "assistant", "content": "old"},
        {"role": "assistant", "content": "final\r\ncontent"},
    ]
    assert _extract_completion_text(item) == "final\r\ncontent"


@pytest.mark.parametrize(
    "item",
    [
        [],
        [{"role": "assistant"}],
        [{"role": "assistant", "content": 123}],
        {"role": "assistant", "content": "direct mapping"},
        ["not a mapping"],
    ],
)
def test_completion_text_rejects_empty_chat_missing_content_non_string_content_and_direct_mapping(
    item: object,
) -> None:
    with pytest.raises(RewardContractError):
        _extract_completion_text(item)


def test_completion_batch_is_fully_validated_before_any_verifier_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fail_if_called(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("verifier must not be called")

    monkeypatch.setattr(common_module, "verify_completion", fail_if_called)
    valid = [{"role": "assistant", "content": _completion()}]
    invalid = [{"role": "assistant", "content": object()}]
    with pytest.raises(RewardContractError):
        compute_code_rewards(
            [valid, invalid],
            [_tests(), _tests()],
            ["solve", "solve"],
            [_metadata(), _metadata()],
            MockExecutor([]),
            "public",
        )
    assert calls == 0


def test_require_executor_rejects_missing_and_non_callable_execute() -> None:
    assert _require_executor(_ExecutorLike()).execute is not None
    with pytest.raises(RewardContractError):
        _require_executor(object())
    with pytest.raises(RewardContractError):
        _require_executor(type("BadExecutor", (), {"execute": 1})())


def test_input_errors_do_not_echo_completion_or_dataset_sentinels() -> None:
    sentinel = "TOP_SECRET_SENTINEL"
    bad_item = [{"content": object(), "secret": sentinel}]
    with pytest.raises(RewardContractError) as completion_error:
        _extract_completion_text(bad_item)
    assert sentinel not in str(completion_error.value)

    with pytest.raises(RewardContractError) as batch_error:
        _validate_batch_alignment([sentinel], [], ["solve"], [{}])
    assert sentinel not in str(batch_error.value)


def test_reward_formula_all_pass_partial_fail_and_all_fail_is_monotonic() -> None:
    passed, _, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=2,
            returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.PASSED],
        )
    )
    partial, _, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            total_tests=2,
            returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.WRONG_ANSWER],
        )
    )
    failed, _, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            total_tests=2,
            returned_statuses=[ExecutionStatus.WRONG_ANSWER, ExecutionStatus.WRONG_ANSWER],
        )
    )
    assert passed == pytest.approx(1.1)
    assert partial == pytest.approx(0.6)
    assert failed == pytest.approx(0.1)
    assert passed > partial > failed


def test_parse_failure_has_invalid_format_penalty_and_no_executable_reward() -> None:
    rewards, records = compute_code_rewards(
        ["explanation only"],
        [_tests(1)],
        ["solve"],
        [_metadata()],
        MockExecutor([]),
        "public",
    )
    assert rewards == [-0.1]
    assert records[0]["status"] == ExecutionStatus.PARSE_ERROR.value
    assert records[0]["executable_reward"] == 0.0
    assert records[0]["invalid_format_penalty"] == -0.1
    assert records[0]["executor_runtime_ms"] == 0.0


def test_reward_component_records_include_executor_runtime_without_payload() -> None:
    _, record, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=1,
            returned_statuses=[ExecutionStatus.PASSED],
        )
    )

    assert record["executor_runtime_ms"] == 1.0
    assert "execution_result" not in record


def test_reward_component_runtime_is_zero_without_execution_result() -> None:
    _, records = compute_code_rewards(
        ["explanation only"],
        [_tests(1)],
        ["solve"],
        [_metadata()],
        MockExecutor([]),
        "public",
    )

    assert records[0]["executor_runtime_ms"] == 0.0


def test_missing_target_function_uses_same_invalid_format_penalty() -> None:
    completion = "```python\ndef other(value):\n    return value\n```\n"
    rewards, records = compute_code_rewards(
        [completion],
        [_tests(1)],
        ["solve"],
        [_metadata()],
        MockExecutor([]),
        "hidden",
    )
    assert rewards == [-0.1]
    assert records[0]["parse_error_type"] == "missing_target_function"


def test_timeout_keeps_pass_rate_adds_executable_and_applies_minus_point_two() -> None:
    reward, record, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.TIMEOUT,
            total_tests=2,
            returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.TIMEOUT],
        )
    )
    assert reward == pytest.approx(0.4)
    assert record["test_reward"] == 0.5
    assert record["executable_reward"] == 0.1
    assert record["timeout_penalty"] == -0.2


@pytest.mark.parametrize("status", [ExecutionStatus.RUNTIME_ERROR, ExecutionStatus.WRONG_ANSWER])
def test_runtime_and_wrong_answer_keep_executable_reward_without_extra_penalty(status: ExecutionStatus) -> None:
    reward, record, _ = _compute_one(_execution_result(status=status, total_tests=1, returned_statuses=[status]))
    assert reward == pytest.approx(0.1)
    assert record["executable_reward"] == 0.1
    assert record["timeout_penalty"] == 0.0
    assert record["invalid_format_penalty"] == 0.0


def test_sandbox_error_and_executor_exception_receive_no_positive_executable_or_test_reward() -> None:
    sandbox_reward, sandbox_record, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.SANDBOX_ERROR,
            total_tests=2,
            returned_statuses=[ExecutionStatus.PASSED, ExecutionStatus.SANDBOX_ERROR],
        )
    )
    exception_rewards, exception_records = compute_code_rewards(
        [_completion()],
        [_tests(1)],
        ["solve"],
        [_metadata()],
        _RaisingExecutor(),
        "public",
    )
    assert sandbox_reward == 0.0
    assert sandbox_record["infrastructure_failure"] is True
    assert sandbox_record["passed_tests"] == 1
    assert sandbox_record["test_reward"] == 0.0
    assert sandbox_record["executable_reward"] == 0.0
    assert exception_rewards == [0.0]
    assert exception_records[0]["status"] == ExecutionStatus.SANDBOX_ERROR.value
    assert exception_records[0]["executable_reward"] == 0.0


def test_nested_sandbox_failure_overrides_earlier_model_failure_for_reward() -> None:
    reward, record, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            total_tests=3,
            returned_statuses=[
                ExecutionStatus.WRONG_ANSWER,
                ExecutionStatus.PASSED,
                ExecutionStatus.SANDBOX_ERROR,
            ],
        )
    )
    assert reward == 0.0
    assert record["status"] == ExecutionStatus.WRONG_ANSWER.value
    assert record["infrastructure_failure"] is True
    assert record["passed_tests"] == 1
    assert record["test_reward"] == 0.0
    assert record["executable_reward"] == 0.0
    assert record["timeout_penalty"] == 0.0
    assert record["failure_counts"] == {"sandbox_error": 1, "wrong_answer": 1}


def test_nested_timeout_applies_penalty_when_earlier_model_failure_is_top_level() -> None:
    reward, record, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            total_tests=2,
            returned_statuses=[ExecutionStatus.WRONG_ANSWER, ExecutionStatus.TIMEOUT],
        )
    )
    assert reward == pytest.approx(-0.1)
    assert record["status"] == ExecutionStatus.WRONG_ANSWER.value
    assert record["infrastructure_failure"] is False
    assert record["test_reward"] == 0.0
    assert record["executable_reward"] == 0.1
    assert record["timeout_penalty"] == -0.2
    assert record["failure_counts"] == {"timeout": 1, "wrong_answer": 1}


def test_all_reward_numbers_are_finite_and_component_total_matches_sum() -> None:
    reward, record, _ = _compute_one(
        _execution_result(
            status=ExecutionStatus.PASSED,
            total_tests=1,
            returned_statuses=[ExecutionStatus.PASSED],
        )
    )
    numeric_fields = [
        "test_reward",
        "executable_reward",
        "timeout_penalty",
        "invalid_format_penalty",
        "total_reward",
        "executor_runtime_ms",
    ]
    assert math.isfinite(reward)
    numeric_values: list[float] = []
    for field in numeric_fields:
        value = record[field]
        assert not isinstance(value, bool)
        assert isinstance(value, int | float)
        numeric_values.append(float(value))
    assert all(math.isfinite(value) for value in numeric_values)
    component_sum = sum(numeric_values[:4], 0.0)
    assert numeric_values[4] == pytest.approx(component_sum)


def test_component_record_is_json_safe_payload_free_and_aligned_with_rewards() -> None:
    completion_sentinel = "COMPLETION_SECRET"
    test_sentinel = "TEST_SECRET"
    completion = f"```python\ndef solve(value):\n    return value  # {completion_sentinel}\n```\n"
    tests = [{"input": [test_sentinel], "expected": test_sentinel}]
    result = _execution_result(
        status=ExecutionStatus.PASSED,
        total_tests=1,
        returned_statuses=[ExecutionStatus.PASSED],
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
    assert len(rewards) == len(records) == 1
    assert completion_sentinel not in serialized
    assert test_sentinel not in serialized
    assert "DATASET_SECRET" not in serialized
    assert "execution_result" not in records[0]


def test_invalid_mode_fails_before_verifier_or_executor_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fail_if_called(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("verifier must not be called")

    monkeypatch.setattr(common_module, "verify_completion", fail_if_called)
    executor = MockExecutor([])
    with pytest.raises(RewardContractError):
        compute_code_rewards([_completion()], [_tests()], ["solve"], [_metadata()], executor, "invalid")
    assert calls == 0
    assert executor.calls == ()


@pytest.mark.parametrize("batch_size", [0, 1])
def test_compute_rejects_invalid_executor_for_empty_and_nonempty_batches(batch_size: int) -> None:
    completions = [_completion()] * batch_size
    tests_batch = [_tests()] * batch_size
    function_names = ["solve"] * batch_size
    metadata_batch = [_metadata()] * batch_size

    with pytest.raises(RewardContractError, match="executor must provide a callable execute method"):
        compute_code_rewards(
            completions,
            tests_batch,
            function_names,
            metadata_batch,
            object(),  # type: ignore[arg-type]
            "public",
        )


def test_verification_input_contract_error_becomes_sanitized_reward_contract_error() -> None:
    sentinel = "BAD_METADATA_SECRET"
    metadata = {"time_limit_seconds": sentinel, "memory_limit_mb": 64}
    with pytest.raises(RewardContractError) as exc_info:
        compute_code_rewards([_completion()], [_tests()], ["solve"], [metadata], MockExecutor([]), "public")
    assert str(exc_info.value) == "reward item violates verification input contract"
    assert sentinel not in str(exc_info.value)


def test_compute_returns_exactly_one_reward_and_component_record_per_completion() -> None:
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
    ]
    rewards, records = compute_code_rewards(
        [_completion(), _completion("return value + 1")],
        [_tests(1), _tests(1)],
        ["solve", "solve"],
        [_metadata(), _metadata()],
        MockExecutor(results),
        "hidden",
    )
    assert len(rewards) == len(records) == 2
    assert all(isinstance(reward, float) for reward in rewards)


def test_compute_uses_indexing_not_silent_zip_truncation() -> None:
    executor = MockExecutor([])
    with pytest.raises(RewardContractError):
        compute_code_rewards(
            [_completion(), _completion()],
            [_tests()],
            ["solve", "solve"],
            [_metadata(), _metadata()],
            executor,
            "public",
        )
    assert executor.calls == ()


def test_concurrent_rewards_match_serial_and_preserve_input_order() -> None:
    completions = [_completion(), _completion("return value + 1")]
    tests_batch = [_tests(1), _tests(1)]
    functions = ["solve", "solve"]
    metadata = [_metadata(), _metadata()]
    concurrent_rewards, concurrent_records = compute_code_rewards_concurrent(
        completions,
        tests_batch,
        functions,
        metadata,
        executor_factory=_DelayedByCodeExecutor,
        mode="public",
        max_concurrency=2,
    )
    serial_rewards, serial_records = compute_code_rewards(
        completions,
        tests_batch,
        functions,
        metadata,
        MockExecutor(
            [
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
            ]
        ),
        "public",
    )
    assert concurrent_rewards == serial_rewards
    assert concurrent_records == serial_records


def test_concurrent_rewards_validate_alignment_before_factory_side_effect() -> None:
    calls = 0

    def factory() -> _DelayedByCodeExecutor:
        nonlocal calls
        calls += 1
        return _DelayedByCodeExecutor()

    with pytest.raises(RewardContractError, match="lengths must match"):
        compute_code_rewards_concurrent(
            [_completion()],
            [],
            ["solve"],
            [_metadata()],
            executor_factory=factory,
            mode="public",
            max_concurrency=2,
        )
    assert calls == 0


def test_concurrent_rewards_validate_every_item_before_factory_or_execute_side_effect() -> None:
    calls = {"factory": 0, "execute": 0}

    class CountingExecutor:
        def execute(
            self,
            code: str,
            function_name: str,
            tests: list[dict[str, Any]],
            timeout_seconds: float,
            memory_limit_mb: int,
        ) -> ExecutionResult:
            del code, function_name, timeout_seconds, memory_limit_mb
            calls["execute"] += 1
            return _execution_result(
                status=ExecutionStatus.PASSED,
                total_tests=len(tests),
                returned_statuses=[ExecutionStatus.PASSED] * len(tests),
            )

    def factory() -> CountingExecutor:
        calls["factory"] += 1
        return CountingExecutor()

    invalid_metadata = {**_metadata(), "time_limit_seconds": 0.0}
    with pytest.raises(RewardContractError, match="verification input contract"):
        compute_code_rewards_concurrent(
            [_completion(), _completion("return value + 1")],
            [_tests(), _tests()],
            ["solve", "solve"],
            [_metadata(), invalid_metadata],
            executor_factory=factory,
            mode="public",
            max_concurrency=2,
        )

    assert calls == {"factory": 0, "execute": 0}
