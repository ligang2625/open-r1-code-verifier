"""Tests for verification input normalization and orchestration."""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Any, cast

import pytest

from code_verifier.verification.result_types import VerificationContractError
from code_verifier.verification.verifier import (
    _normalize_tests,
    _resource_limits_from_metadata,
    _validate_function_name,
)


def test_validate_function_name_accepts_identifier_and_rejects_keyword_invalid_utf8_and_wrong_type() -> None:
    assert _validate_function_name("solve_问题") == "solve_问题"

    invalid_names = ["", "not-valid", "class", " solve", "\ud800", 1, None]
    for invalid_name in invalid_names:
        with pytest.raises(VerificationContractError):
            _validate_function_name(invalid_name)


def test_normalize_tests_preserves_order_and_returns_deep_mutable_copy() -> None:
    nested_input = MappingProxyType({"values": (1, MappingProxyType({"flag": True}))})
    tests = (
        MappingProxyType({"input": nested_input, "expected": (1, 2)}),
        MappingProxyType({"input": "second", "expected": None}),
    )

    normalized = _normalize_tests(tests)

    assert normalized == [
        {"input": {"values": [1, {"flag": True}]}, "expected": [1, 2]},
        {"input": "second", "expected": None},
    ]
    assert isinstance(normalized, list)
    assert isinstance(normalized[0], dict)
    assert isinstance(normalized[0]["input"], dict)
    cast(dict[str, Any], normalized[0]["input"])["values"] = []
    assert nested_input["values"] == (1, MappingProxyType({"flag": True}))


def test_normalize_tests_rejects_empty_wrong_shape_unknown_fields_and_non_json_values() -> None:
    recursive: list[Any] = []
    recursive.append(recursive)
    invalid_tests: list[object] = [
        [],
        "tests",
        b"tests",
        {"input": 1, "expected": 1},
        [1],
        [{"input": 1}],
        [{"input": 1, "expected": 1, "extra": 2}],
        [{cast(object, 1): 1, "expected": 1}],
        [{"input": object(), "expected": 1}],
        [{"input": recursive, "expected": 1}],
        [{"input": "\ud800", "expected": 1}],
        [{"input": {"\ud800": 1}, "expected": 1}],
    ]

    for invalid in invalid_tests:
        with pytest.raises(VerificationContractError):
            _normalize_tests(invalid)


def test_normalize_tests_preserves_bool_int_float_type_distinctions() -> None:
    normalized = _normalize_tests(
        [
            {"input": True, "expected": False},
            {"input": 1, "expected": 0},
            {"input": 1.0, "expected": 0.0},
        ]
    )

    assert type(normalized[0]["input"]) is bool
    assert type(normalized[0]["expected"]) is bool
    assert type(normalized[1]["input"]) is int
    assert type(normalized[1]["expected"]) is int
    assert type(normalized[2]["input"]) is float
    assert type(normalized[2]["expected"]) is float


def test_resource_limits_accept_wp1_metadata_and_ignore_unrelated_fields() -> None:
    unrelated = object()
    metadata = MappingProxyType(
        {
            "difficulty": "medium",
            "category": unrelated,
            "time_limit_seconds": 1,
            "memory_limit_mb": 256,
            "license": unrelated,
            "source_url_hash": unrelated,
        }
    )

    assert _resource_limits_from_metadata(metadata) == (1.0, 256)


def test_resource_limits_reject_missing_non_finite_non_positive_and_bool_values() -> None:
    invalid_metadata: list[object] = [
        None,
        [],
        {1: 2, "time_limit_seconds": 1.0, "memory_limit_mb": 64},
        {},
        {"time_limit_seconds": 1.0},
        {"memory_limit_mb": 64},
        {"time_limit_seconds": 0.0, "memory_limit_mb": 64},
        {"time_limit_seconds": -1.0, "memory_limit_mb": 64},
        {"time_limit_seconds": float("nan"), "memory_limit_mb": 64},
        {"time_limit_seconds": float("inf"), "memory_limit_mb": 64},
        {"time_limit_seconds": True, "memory_limit_mb": 64},
        {"time_limit_seconds": 10**1000, "memory_limit_mb": 64},
        {"time_limit_seconds": 1.0, "memory_limit_mb": 0},
        {"time_limit_seconds": 1.0, "memory_limit_mb": -1},
        {"time_limit_seconds": 1.0, "memory_limit_mb": True},
        {"time_limit_seconds": 1.0, "memory_limit_mb": 64.0},
    ]

    for invalid in invalid_metadata:
        with pytest.raises(VerificationContractError):
            _resource_limits_from_metadata(invalid)


def test_input_contract_errors_do_not_echo_sentinel_values() -> None:
    sentinel = "PRIVATE_INPUT_SENTINEL_314159"
    invalid_inputs: list[Callable[[], object]] = [
        lambda: _validate_function_name(f"not-valid-{sentinel}"),
        lambda: _normalize_tests([{"input": {sentinel: object()}, "expected": sentinel}]),
        lambda: _resource_limits_from_metadata(
            {"time_limit_seconds": sentinel, "memory_limit_mb": 64, "unrelated": sentinel}
        ),
    ]

    for invalid_call in invalid_inputs:
        with pytest.raises(VerificationContractError) as exc_info:
            invalid_call()
        assert sentinel not in str(exc_info.value)


def test_invalid_inputs_do_not_call_parser_or_executor() -> None:
    parser_calls = 0
    executor_calls = 0

    def validate_then_call(function_name: object, tests: object, metadata: object) -> None:
        nonlocal parser_calls, executor_calls
        _validate_function_name(function_name)
        _normalize_tests(tests)
        _resource_limits_from_metadata(metadata)
        parser_calls += 1
        executor_calls += 1

    invalid_cases = [
        ("not-valid", [{"input": 1, "expected": 1}], {"time_limit_seconds": 1.0, "memory_limit_mb": 64}),
        ("solve", [], {"time_limit_seconds": 1.0, "memory_limit_mb": 64}),
        ("solve", [{"input": 1, "expected": 1}], {"time_limit_seconds": 0.0, "memory_limit_mb": 64}),
    ]
    for function_name, tests, metadata in invalid_cases:
        with pytest.raises(VerificationContractError):
            validate_then_call(function_name, tests, metadata)

    assert parser_calls == 0
    assert executor_calls == 0
