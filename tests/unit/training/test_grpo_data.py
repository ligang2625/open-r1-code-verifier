"""Tests for payload-minimal Public and Hidden GRPO datasets."""

from __future__ import annotations

from typing import cast

import pytest

from code_verifier.prompting import build_code_prompt_from_fields
from code_verifier.training.grpo_data import GRPODataError, build_grpo_dataset


def _record(*, hidden: bool) -> dict[str, object]:
    record: dict[str, object] = {
        "problem_id": "grpo-1",
        "prompt": "Return the input.",
        "function_name": "solve",
        "function_signature": "def solve(value):",
        "visible_tests": [{"input": "VISIBLE_SENTINEL", "expected": "VISIBLE_SENTINEL"}],
        "metadata": {
            "difficulty": "easy",
            "category": ["unit"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "test",
            "source_url_hash": None,
        },
    }
    if hidden:
        record["train_hidden_tests"] = [{"input": "HIDDEN_SENTINEL", "expected": "HIDDEN_SENTINEL"}]
    return record


def test_build_grpo_dataset_public_uses_shared_prompt_and_visible_payload_only() -> None:
    dataset = build_grpo_dataset([_record(hidden=False)], reward_mode="public")

    assert dataset.column_names == ["prompt", "problem_id", "function_name", "metadata", "visible_tests"]
    assert dataset[0]["prompt"] == [
        {
            "role": "user",
            "content": build_code_prompt_from_fields(
                "Return the input.",
                "def solve(value):",
                [{"input": "VISIBLE_SENTINEL", "expected": "VISIBLE_SENTINEL"}],
            ),
        }
    ]
    serialized = repr(dataset[0])
    assert "VISIBLE_SENTINEL" in serialized
    assert "train_hidden_tests" not in serialized
    assert "function_signature" not in dataset.column_names


def test_build_grpo_dataset_hidden_adds_only_train_hidden_reward_payload() -> None:
    public = build_grpo_dataset([_record(hidden=False)], reward_mode="public")
    hidden = build_grpo_dataset([_record(hidden=True)], reward_mode="hidden")

    assert hidden.column_names == [
        "prompt",
        "problem_id",
        "function_name",
        "metadata",
        "visible_tests",
        "train_hidden_tests",
    ]
    for field in public.column_names:
        assert hidden[0][field] == public[0][field]
    assert hidden[0]["train_hidden_tests"] == [{"input": "HIDDEN_SENTINEL", "expected": "HIDDEN_SENTINEL"}]


def test_build_grpo_dataset_rejects_duplicate_problem_ids() -> None:
    with pytest.raises(GRPODataError, match="duplicate problem_id"):
        build_grpo_dataset([_record(hidden=False), _record(hidden=False)], reward_mode="public")


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"eval_hidden_tests": []}, "forbidden"),
        ({"sft_response": "PRIVATE"}, "unknown"),
        ({"prompt": ""}, "non-empty"),
        ({"problem_id": "bad\ud800"}, "UTF-8"),
        ({"visible_tests": []}, "non-empty"),
    ],
)
def test_build_grpo_dataset_rejects_forbidden_or_malformed_payload(
    mutation: dict[str, object],
    match: str,
) -> None:
    record = _record(hidden=False)
    record.update(mutation)
    with pytest.raises(GRPODataError, match=match):
        build_grpo_dataset([record], reward_mode="public")


def test_build_grpo_dataset_rejects_unknown_reward_mode_and_non_mapping_record() -> None:
    with pytest.raises(GRPODataError, match="public or hidden"):
        build_grpo_dataset([_record(hidden=False)], reward_mode="eval")
    with pytest.raises(GRPODataError, match="mapping"):
        build_grpo_dataset(cast(list[dict[str, object]], ["bad"]), reward_mode="public")
