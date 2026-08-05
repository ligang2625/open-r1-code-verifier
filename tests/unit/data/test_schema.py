"""Tests for the canonical code-problem schema."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from code_verifier.data.schema import (
    CodeProblem,
    SchemaError,
    problem_from_mapping,
    problem_to_mapping,
    validate_json_value,
)


def _problem_mapping() -> dict[str, object]:
    return {
        "problem_id": "sum-two",
        "source": "fixture",
        "split": "train",
        "prompt": "Add two integers.",
        "function_name": "add",
        "function_signature": "def add(a: int, b: int) -> int:",
        "starter_code": None,
        "visible_tests": [{"input": [1, 2], "expected": 3}],
        "train_hidden_tests": [{"input": [-1, 2], "expected": 1}],
        "eval_hidden_tests": [{"input": [0, 0], "expected": 0}],
        "reference_solution": "def add(a, b): return a + b",
        "sft_response": "def add(a, b): return a + b",
        "metadata": {
            "difficulty": "easy",
            "category": ["math"],
            "time_limit_seconds": 2.0,
            "memory_limit_mb": 512,
            "license": "MIT",
            "source_url_hash": None,
        },
    }


def test_problem_round_trip_preserves_spec_fields() -> None:
    mapping = _problem_mapping()
    assert problem_to_mapping(problem_from_mapping(mapping)) == mapping


@pytest.mark.parametrize("field", sorted(_problem_mapping()))
def test_problem_from_mapping_rejects_missing_required_field(field: str) -> None:
    mapping = _problem_mapping()
    del mapping[field]
    with pytest.raises(SchemaError, match=field):
        problem_from_mapping(mapping)


def test_problem_from_mapping_rejects_unknown_field() -> None:
    mapping = _problem_mapping()
    mapping["promt"] = "typo"
    with pytest.raises(SchemaError, match="promt"):
        problem_from_mapping(mapping)


def test_problem_from_mapping_rejects_invalid_split() -> None:
    mapping = _problem_mapping()
    mapping["split"] = "dev"
    with pytest.raises(SchemaError, match="split"):
        problem_from_mapping(mapping)


@pytest.mark.parametrize(
    ("field", "value"),
    [("difficulty", "impossible"), ("time_limit_seconds", 0), ("memory_limit_mb", -1)],
)
def test_metadata_rejects_invalid_limits_and_difficulty(field: str, value: object) -> None:
    mapping = _problem_mapping()
    metadata = cast(dict[str, object], mapping["metadata"])
    metadata[field] = value
    with pytest.raises(SchemaError, match=field):
        problem_from_mapping(mapping)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "bad"}])
def test_json_value_rejects_nan_inf_and_non_string_keys(value: object) -> None:
    with pytest.raises(SchemaError):
        validate_json_value(value, field_path="value")


def test_frozen_schema_is_immutable() -> None:
    problem = problem_from_mapping(_problem_mapping())
    with pytest.raises(FrozenInstanceError):
        problem.problem_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_test_case_requires_exact_input_expected_fields(mutation: str) -> None:
    mapping = _problem_mapping()
    test_case = cast(list[dict[str, object]], mapping["visible_tests"])[0]
    if mutation == "missing":
        del test_case["expected"]
    else:
        test_case["extra"] = 1
    with pytest.raises(SchemaError):
        problem_from_mapping(mapping)


def test_json_containers_are_copied_on_input() -> None:
    mapping = _problem_mapping()
    original_input = cast(list[dict[str, object]], mapping["visible_tests"])[0]["input"]
    problem = problem_from_mapping(mapping)
    cast(list[int], original_input).append(99)
    assert problem.visible_tests[0].input == (1, 2)
    assert problem_to_mapping(problem)["visible_tests"] == [{"input": [1, 2], "expected": 3}]


def test_nested_json_containers_cannot_be_mutated_after_validation() -> None:
    mapping = _problem_mapping()
    cast(list[dict[str, object]], mapping["visible_tests"])[0]["input"] = {"values": [1, 2]}
    problem = problem_from_mapping(mapping)
    frozen_input = cast(object, problem.visible_tests[0].input)

    with pytest.raises(TypeError):
        cast(dict[str, object], frozen_input)["extra"] = 1
    values = cast(dict[str, object], frozen_input)["values"]
    with pytest.raises(TypeError):
        cast(list[int], values)[0] = 99

    assert problem_to_mapping(problem)["visible_tests"] == [{"input": {"values": [1, 2]}, "expected": 3}]


def test_direct_test_case_construction_freezes_json_containers() -> None:
    from code_verifier.data.schema import TestCase

    test_case = TestCase(input=[1, {"nested": [2]}], expected={"ok": True})
    with pytest.raises(TypeError):
        cast(list[object], test_case.input)[0] = 9
    nested = cast(dict[str, object], cast(tuple[object, ...], test_case.input)[1])["nested"]
    with pytest.raises(TypeError):
        cast(list[int], nested)[0] = 9


def test_problem_type_is_exported() -> None:
    assert isinstance(problem_from_mapping(_problem_mapping()), CodeProblem)
