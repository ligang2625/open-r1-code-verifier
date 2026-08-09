"""Tests for visible-only SFT trajectory validation and dataset mapping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.sft_data import (
    SFTDataError,
    build_sft_dataset,
    normalize_sft_completion,
    validate_sft_record,
)


class _Tokenizer:
    chat_template = "fake-template"

    def __init__(self, *, token_count: int = 8) -> None:
        self.token_count = token_count
        self.messages: list[list[dict[str, str]]] = []

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> list[int]:
        assert tokenize is True
        assert add_generation_prompt is False
        self.messages.append(messages)
        return list(range(self.token_count))


def _execution_result(status: ExecutionStatus = ExecutionStatus.PASSED) -> ExecutionResult:
    passed = status is ExecutionStatus.PASSED
    return ExecutionResult(
        status=status,
        passed_tests=int(passed),
        total_tests=1,
        pass_rate=float(passed),
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(
                status=status,
                passed=passed,
                runtime_ms=1.0,
                stdout="",
                stderr="",
            )
        ],
    )


def _record(response: str = "def solve(value):\n    return value") -> dict[str, object]:
    return {
        "problem_id": "sft-1",
        "prompt": "VISIBLE_PROMPT",
        "function_name": "solve",
        "visible_tests": [{"input": "VISIBLE_INPUT", "expected": "VISIBLE_INPUT"}],
        "sft_response": response,
        "metadata": {
            "difficulty": "easy",
            "category": ["unit"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "test",
            "source_url_hash": None,
        },
    }


def test_normalize_raw_python_to_single_fenced_completion() -> None:
    assert normalize_sft_completion(
        "def solve(value):\r\n    return value\r\n",
        expected_function_name="solve",
    ) == "```python\ndef solve(value):\n    return value\n```"


@pytest.mark.parametrize(
    "response",
    [
        "def other(value):\n    return value",
        "```python\ndef solve(value):\n    return value",
        "```python\ndef solve(value):\n    return value\n```\n```python\ndef helper():\n    return 1\n```",
        "def solve(value):\n    pass\n    pass\n    pass\n    pass",
    ],
)
def test_normalize_rejects_missing_target_and_duplicate_or_truncated_blocks(response: str) -> None:
    with pytest.raises(SFTDataError):
        normalize_sft_completion(response, expected_function_name="solve")


def test_validate_sft_record_uses_visible_tests_only() -> None:
    executor = MockExecutor([_execution_result()])
    example = validate_sft_record(_record(), executor=executor)

    assert example.problem_id == "sft-1"
    assert example.prompt == "VISIBLE_PROMPT"
    assert executor.calls[0].tests == [{"input": "VISIBLE_INPUT", "expected": "VISIBLE_INPUT"}]


@pytest.mark.parametrize("status", [ExecutionStatus.WRONG_ANSWER, ExecutionStatus.SANDBOX_ERROR])
def test_validate_sft_record_fails_closed_on_wrong_answer_and_sandbox_error(status: ExecutionStatus) -> None:
    with pytest.raises(SFTDataError, match=status.value):
        validate_sft_record(_record(), executor=MockExecutor([_execution_result(status)]))


def test_build_sft_dataset_drops_validation_payloads_before_trainer() -> None:
    tokenizer = _Tokenizer()
    dataset = build_sft_dataset(
        [_record()],
        executor=MockExecutor([_execution_result()]),
        tokenizer=tokenizer,
        max_seq_length=32,
    )

    assert dataset.column_names == ["prompt", "completion"]
    assert dataset[0] == {
        "prompt": [{"role": "user", "content": "VISIBLE_PROMPT"}],
        "completion": [
            {
                "role": "assistant",
                "content": "```python\ndef solve(value):\n    return value\n```",
            }
        ],
    }
    serialized = repr(dataset[0])
    for forbidden in ("visible_tests", "function_name", "metadata", "VISIBLE_INPUT"):
        assert forbidden not in serialized


def test_build_sft_dataset_rejects_over_max_sequence_length_without_truncation() -> None:
    tokenizer = _Tokenizer(token_count=33)
    with pytest.raises(SFTDataError, match="truncation is forbidden"):
        build_sft_dataset(
            [_record()],
            executor=MockExecutor([_execution_result()]),
            tokenizer=tokenizer,
            max_seq_length=32,
        )


def test_hidden_payload_is_rejected_before_executor_or_tokenizer() -> None:
    record = _record()
    record["train_hidden_tests"] = [{"input": "HIDDEN_SENTINEL", "expected": 0}]
    executor = MockExecutor([_execution_result()])
    tokenizer = _Tokenizer()

    with pytest.raises(SFTDataError):
        build_sft_dataset([record], executor=executor, tokenizer=tokenizer, max_seq_length=32)

    assert executor.calls == ()
    assert tokenizer.messages == []


def test_sft_dataset_requires_mapping_records() -> None:
    executor = MockExecutor([_execution_result()])
    records = cast(list[Mapping[str, object]], ["not-a-record"])
    with pytest.raises(SFTDataError):
        build_sft_dataset(
            records,
            executor=executor,
            tokenizer=_Tokenizer(),
            max_seq_length=32,
        )


def test_metadata_mapping_type_is_required() -> None:
    record: Mapping[str, Any] = {**_record(), "metadata": []}
    with pytest.raises(SFTDataError):
        validate_sft_record(record, executor=MockExecutor([_execution_result()]))
