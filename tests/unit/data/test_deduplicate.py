"""Tests for deterministic hashes and dataset duplicate checks."""

from __future__ import annotations

from dataclasses import replace

import pytest

from code_verifier.data.deduplicate import (
    DuplicateDataError,
    canonical_json,
    ensure_no_problem_overlap_across_splits,
    ensure_unique_problem_ids,
    ensure_unique_test_cases,
    normalize_text,
    problem_content_hash,
    stable_json_hash,
)
from code_verifier.data.deduplicate import (
    test_case_hash as hash_test_case,
)
from code_verifier.data.schema import CodeProblem, problem_from_mapping, problem_to_mapping
from code_verifier.data.schema import TestCase as CodeTestCase


def _problem(*, problem_id: str = "p1", split: str = "train", prompt: str = "Add values.") -> CodeProblem:
    return problem_from_mapping(
        {
            "problem_id": problem_id,
            "source": "fixture",
            "split": split,
            "prompt": prompt,
            "function_name": "add",
            "function_signature": "def add(a, b):",
            "starter_code": None,
            "visible_tests": [{"input": [1, 2], "expected": 3}],
            "train_hidden_tests": [{"input": [2, 3], "expected": 5}],
            "eval_hidden_tests": [{"input": [-1, 1], "expected": 0}],
            "reference_solution": "def add(a, b): return a + b",
            "sft_response": "def add(a, b): return a + b",
            "metadata": {
                "difficulty": "easy",
                "category": ["math"],
                "time_limit_seconds": 1.0,
                "memory_limit_mb": 128,
                "license": "MIT",
                "source_url_hash": None,
            },
        }
    )


def _distinct_problem(*, problem_id: str, split: str) -> CodeProblem:
    mapping = problem_to_mapping(_problem(problem_id=problem_id, split=split, prompt="Subtract values."))
    mapping["function_name"] = "subtract"
    mapping["function_signature"] = "def subtract(a, b):"
    mapping["visible_tests"] = [{"input": [9, 4], "expected": 5}]
    mapping["train_hidden_tests"] = [{"input": [2, 7], "expected": -5}]
    mapping["eval_hidden_tests"] = [{"input": [-1, -3], "expected": 2}]
    mapping["reference_solution"] = "def subtract(a, b): return a - b"
    mapping["sft_response"] = "def subtract(a, b): return a - b"
    return problem_from_mapping(mapping)


def test_canonical_json_ignores_mapping_insertion_order() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_stable_json_hash_has_sha256_shape_and_repeatability() -> None:
    first = stable_json_hash({"value": [1, 2, 3]})
    assert len(first) == 64
    assert first == stable_json_hash({"value": [1, 2, 3]})
    assert set(first) <= set("0123456789abcdef")


def test_normalize_text_equates_newline_unicode_and_spacing_variants() -> None:
    assert normalize_text("\uff21  B\r\nC   \n") == normalize_text("A B C")


def test_test_case_hash_uses_expected_value() -> None:
    first = CodeTestCase(input=["same"], expected=1)
    second = CodeTestCase(input=["same"], expected=2)
    assert hash_test_case(first) != hash_test_case(second)


def test_unique_test_cases_reject_normalized_duplicate() -> None:
    tests = [CodeTestCase(input="\uff21  B", expected=1), CodeTestCase(input="A B", expected=1)]
    with pytest.raises(DuplicateDataError, match="indexes 0 and 1"):
        ensure_unique_test_cases(tests, context="problem p1")


def test_unique_problem_ids_reject_duplicate_id() -> None:
    with pytest.raises(DuplicateDataError, match="p1"):
        ensure_unique_problem_ids([_problem(), replace(_problem(prompt="Different"), problem_id="p1")])


def test_problem_overlap_rejects_same_content_with_different_ids_across_splits() -> None:
    train = _problem(problem_id="train-id", split="train")
    test = replace(train, problem_id="test-id", split="test", source="other")
    assert problem_content_hash(train) == problem_content_hash(test)
    with pytest.raises(DuplicateDataError, match="train-id.*test-id"):
        ensure_no_problem_overlap_across_splits([train, test])


def test_problem_overlap_rejects_same_prompt_signature_with_different_tests() -> None:
    train = _problem(problem_id="train-id", split="train")
    mapping = problem_to_mapping(train)
    mapping["problem_id"] = "validation-id"
    mapping["split"] = "validation"
    mapping["visible_tests"] = [{"input": [10, 2], "expected": 12}]
    mapping["train_hidden_tests"] = [{"input": [4, 6], "expected": 10}]
    mapping["eval_hidden_tests"] = [{"input": [8, 1], "expected": 9}]
    mapping["reference_solution"] = "def add(a, b):\n    return sum((a, b))"

    with pytest.raises(DuplicateDataError, match="prompt/signature.*train-id.*validation-id"):
        ensure_no_problem_overlap_across_splits([train, problem_from_mapping(mapping)])


def test_problem_overlap_rejects_same_reference_solution_with_rewritten_prompt() -> None:
    train = _problem(problem_id="train-id", split="train")
    mapping = problem_to_mapping(_distinct_problem(problem_id="test-id", split="test"))
    mapping["reference_solution"] = train.reference_solution

    with pytest.raises(DuplicateDataError, match="reference solution.*train-id.*test-id"):
        ensure_no_problem_overlap_across_splits([train, problem_from_mapping(mapping)])


def test_problem_overlap_rejects_shared_test_for_matching_signature() -> None:
    train = _problem(problem_id="train-id", split="train")
    mapping = problem_to_mapping(_distinct_problem(problem_id="test-id", split="test"))
    mapping["function_signature"] = train.function_signature
    mapping["visible_tests"] = problem_to_mapping(train)["visible_tests"]

    with pytest.raises(DuplicateDataError, match="test case for matching signature.*train-id.*test-id"):
        ensure_no_problem_overlap_across_splits([train, problem_from_mapping(mapping)])


def test_problem_overlap_allows_distinct_content() -> None:
    ensure_no_problem_overlap_across_splits(
        [_problem(problem_id="train-id", split="train"), _distinct_problem(problem_id="test-id", split="test")]
    )
