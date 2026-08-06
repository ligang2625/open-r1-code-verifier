"""Unified verification helpers and completion verification orchestration."""

from __future__ import annotations

import keyword
import math
from collections.abc import Mapping, Sequence
from typing import Any

from code_verifier.data.schema import SchemaError, json_value_to_mutable, validate_json_value
from code_verifier.verification.result_types import VerificationContractError


def _validate_utf8_text(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise VerificationContractError("verification input contains invalid UTF-8 text") from None


def _validate_utf8_json_value(value: object) -> None:
    if isinstance(value, str):
        _validate_utf8_text(value)
        return
    if isinstance(value, list):
        for item in value:
            _validate_utf8_json_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_utf8_text(key)
            _validate_utf8_json_value(item)


def _validate_function_name(function_name: object) -> str:
    """Return one non-keyword Python identifier or raise a sanitized contract error."""
    if not isinstance(function_name, str):
        raise VerificationContractError("function_name must be a non-keyword Python identifier")
    _validate_utf8_text(function_name)
    if not function_name or not function_name.isidentifier() or keyword.iskeyword(function_name):
        raise VerificationContractError("function_name must be a non-keyword Python identifier")
    return function_name


def _normalize_tests(tests: object) -> list[dict[str, Any]]:
    """Validate one non-empty ordered test layer and return a defensive mutable copy."""
    if isinstance(tests, str | bytes | bytearray) or not isinstance(tests, Sequence) or not tests:
        raise VerificationContractError("tests must be a non-empty sequence")

    normalized: list[dict[str, Any]] = []
    try:
        for item in tests:
            if not isinstance(item, Mapping):
                raise VerificationContractError("each test must be an input/expected mapping")
            if any(type(key) is not str for key in item) or set(item) != {"input", "expected"}:
                raise VerificationContractError("each test must contain exactly input and expected")
            validated_input = validate_json_value(item["input"], field_path="test.input")
            validated_expected = validate_json_value(item["expected"], field_path="test.expected")
            mutable_input = json_value_to_mutable(validated_input, field_path="test.input")
            mutable_expected = json_value_to_mutable(validated_expected, field_path="test.expected")
            _validate_utf8_json_value(mutable_input)
            _validate_utf8_json_value(mutable_expected)
            normalized.append({"input": mutable_input, "expected": mutable_expected})
    except VerificationContractError:
        raise
    except (MemoryError, RecursionError, SchemaError, UnicodeError):
        raise VerificationContractError("tests contain an invalid JSON value") from None
    return normalized


def _resource_limits_from_metadata(metadata: object) -> tuple[float, int]:
    """Read and validate only time_limit_seconds and memory_limit_mb from metadata."""
    if not isinstance(metadata, Mapping) or any(type(key) is not str for key in metadata):
        raise VerificationContractError("metadata must be a string-keyed mapping")
    if "time_limit_seconds" not in metadata or "memory_limit_mb" not in metadata:
        raise VerificationContractError("metadata must include execution resource limits")

    time_limit = metadata["time_limit_seconds"]
    if isinstance(time_limit, bool) or not isinstance(time_limit, int | float):
        raise VerificationContractError("time_limit_seconds must be a finite positive number")
    try:
        normalized_time_limit = float(time_limit)
    except OverflowError:
        raise VerificationContractError("time_limit_seconds must be a finite positive number") from None
    if not math.isfinite(normalized_time_limit) or normalized_time_limit <= 0:
        raise VerificationContractError("time_limit_seconds must be a finite positive number")

    memory_limit = metadata["memory_limit_mb"]
    if isinstance(memory_limit, bool) or not isinstance(memory_limit, int) or memory_limit <= 0:
        raise VerificationContractError("memory_limit_mb must be a positive integer")
    return normalized_time_limit, memory_limit
