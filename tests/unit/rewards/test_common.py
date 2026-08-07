"""Unit tests for shared reward contracts and helpers."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from code_verifier.rewards.common import (
    RewardContractError,
    _completion_texts,
    _extract_completion_text,
    _require_executor,
    _validate_batch_alignment,
)


class _ExecutorLike:
    def execute(self, *args: object, **kwargs: object) -> object:
        return object()


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


def test_completion_batch_is_fully_validated_before_any_verifier_call() -> None:
    valid = [{"role": "assistant", "content": "first"}]
    invalid = [{"role": "assistant", "content": object()}]
    with pytest.raises(RewardContractError):
        _completion_texts([valid, invalid])


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
