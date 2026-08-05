"""Strict immutable representation of the canonical code-problem schema."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeAlias, cast

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
FrozenJsonValue: TypeAlias = JsonScalar | tuple["FrozenJsonValue", ...] | Mapping[str, "FrozenJsonValue"]
JsonInputValue: TypeAlias = JsonValue | FrozenJsonValue


class SchemaError(ValueError):
    """Raised when a record does not satisfy the canonical problem schema."""


@dataclass(frozen=True)
class TestCase:
    """One JSON-serializable function input and expected output."""

    input: JsonInputValue
    expected: JsonInputValue

    def __post_init__(self) -> None:
        """Recursively freeze direct constructor inputs as well as parsed inputs."""
        object.__setattr__(self, "input", validate_json_value(self.input, field_path="test_case.input"))
        object.__setattr__(self, "expected", validate_json_value(self.expected, field_path="test_case.expected"))


@dataclass(frozen=True)
class ProblemMetadata:
    """Auditable provenance and execution limits for one problem."""

    difficulty: Literal["easy", "medium", "hard", "unknown"]
    category: tuple[str, ...]
    time_limit_seconds: float
    memory_limit_mb: int
    license: str
    source_url_hash: str | None


@dataclass(frozen=True)
class CodeProblem:
    """Canonical function-level Python problem with three isolated test layers."""

    problem_id: str
    source: str
    split: Literal["train", "validation", "test"]
    prompt: str
    function_name: str
    function_signature: str
    starter_code: str | None
    visible_tests: tuple[TestCase, ...]
    train_hidden_tests: tuple[TestCase, ...]
    eval_hidden_tests: tuple[TestCase, ...]
    reference_solution: str | None
    sft_response: str | None
    metadata: ProblemMetadata


_PROBLEM_FIELDS = {
    "problem_id",
    "source",
    "split",
    "prompt",
    "function_name",
    "function_signature",
    "starter_code",
    "visible_tests",
    "train_hidden_tests",
    "eval_hidden_tests",
    "reference_solution",
    "sft_response",
    "metadata",
}
_METADATA_FIELDS = {
    "difficulty",
    "category",
    "time_limit_seconds",
    "memory_limit_mb",
    "license",
    "source_url_hash",
}
_TEST_CASE_FIELDS = {"input", "expected"}


def _require_exact_fields(value: dict[object, object], expected: set[str], *, field_path: str) -> None:
    missing = {field for field in expected if field not in value}
    unknown = {key for key in value if key not in expected}
    if missing:
        raise SchemaError(f"{field_path} is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        rendered = ", ".join(sorted(str(key) for key in unknown))
        raise SchemaError(f"{field_path} contains unknown field(s): {rendered}")


def _require_nonempty_string(value: object, *, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{field_path} must be a non-empty string")
    return value.strip()


def _optional_string(value: object, *, field_path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise SchemaError(f"{field_path} must be a string or null")
    return value


def validate_json_value(value: object, *, field_path: str) -> FrozenJsonValue:
    """Validate and recursively freeze a JSON-compatible value without coercion."""
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SchemaError(f"{field_path} must not contain NaN or infinity")
        return value
    if isinstance(value, list | tuple):
        return tuple(
            validate_json_value(item, field_path=f"{field_path}[{index}]") for index, item in enumerate(value)
        )
    if isinstance(value, Mapping):
        result: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SchemaError(f"{field_path} must use string object keys")
            result[key] = validate_json_value(item, field_path=f"{field_path}.{key}")
        return MappingProxyType(result)
    raise SchemaError(f"{field_path} contains unsupported JSON value type {type(value).__name__}")


def json_value_to_mutable(value: object, *, field_path: str) -> JsonValue:
    """Validate a JSON value and return an independent list/dict representation for serialization."""
    return _thaw_json_value(validate_json_value(value, field_path=field_path))


def _thaw_json_value(value: FrozenJsonValue) -> JsonValue:
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _thaw_json_value(item) for key, item in value.items()}
    return value


def test_case_from_mapping(value: object, *, field_path: str) -> TestCase:
    """Parse one exact {input, expected} mapping into an immutable test case."""
    if not isinstance(value, dict):
        raise SchemaError(f"{field_path} must be an object")
    _require_exact_fields(value, _TEST_CASE_FIELDS, field_path=field_path)
    return TestCase(
        input=validate_json_value(value["input"], field_path=f"{field_path}.input"),
        expected=validate_json_value(value["expected"], field_path=f"{field_path}.expected"),
    )


def metadata_from_mapping(value: object) -> ProblemMetadata:
    """Parse and validate the exact §7.1 metadata object."""
    if not isinstance(value, dict):
        raise SchemaError("metadata must be an object")
    _require_exact_fields(value, _METADATA_FIELDS, field_path="metadata")

    difficulty = value["difficulty"]
    if difficulty not in {"easy", "medium", "hard", "unknown"}:
        raise SchemaError("metadata.difficulty must be easy, medium, hard, or unknown")
    category = value["category"]
    if not isinstance(category, list):
        raise SchemaError("metadata.category must be a list")
    categories = tuple(_require_nonempty_string(item, field_path="metadata.category") for item in category)
    if len(categories) != len(set(categories)):
        raise SchemaError("metadata.category must not contain duplicates")

    time_limit = value["time_limit_seconds"]
    if isinstance(time_limit, bool) or not isinstance(time_limit, int | float) or not math.isfinite(time_limit):
        raise SchemaError("metadata.time_limit_seconds must be a finite number")
    if time_limit <= 0:
        raise SchemaError("metadata.time_limit_seconds must be positive")
    memory_limit = value["memory_limit_mb"]
    if isinstance(memory_limit, bool) or not isinstance(memory_limit, int) or memory_limit <= 0:
        raise SchemaError("metadata.memory_limit_mb must be a positive integer")

    return ProblemMetadata(
        difficulty=cast(Literal["easy", "medium", "hard", "unknown"], difficulty),
        category=categories,
        time_limit_seconds=float(time_limit),
        memory_limit_mb=memory_limit,
        license=_require_nonempty_string(value["license"], field_path="metadata.license"),
        source_url_hash=_optional_string(value["source_url_hash"], field_path="metadata.source_url_hash"),
    )


def _parse_test_layer(value: object, *, field_path: str) -> tuple[TestCase, ...]:
    if not isinstance(value, list) or not value:
        raise SchemaError(f"{field_path} must be a non-empty list")
    return tuple(test_case_from_mapping(item, field_path=f"{field_path}[{index}]") for index, item in enumerate(value))


def problem_from_mapping(value: object) -> CodeProblem:
    """Parse one exact canonical §7.1 record and validate every field."""
    if not isinstance(value, dict):
        raise SchemaError("problem must be an object")
    _require_exact_fields(value, _PROBLEM_FIELDS, field_path="problem")
    split = value["split"]
    if split not in {"train", "validation", "test"}:
        raise SchemaError("split must be train, validation, or test")
    problem = CodeProblem(
        problem_id=_require_nonempty_string(value["problem_id"], field_path="problem_id"),
        source=_require_nonempty_string(value["source"], field_path="source"),
        split=cast(Literal["train", "validation", "test"], split),
        prompt=_require_nonempty_string(value["prompt"], field_path="prompt"),
        function_name=_require_nonempty_string(value["function_name"], field_path="function_name"),
        function_signature=_require_nonempty_string(value["function_signature"], field_path="function_signature"),
        starter_code=_optional_string(value["starter_code"], field_path="starter_code"),
        visible_tests=_parse_test_layer(value["visible_tests"], field_path="visible_tests"),
        train_hidden_tests=_parse_test_layer(value["train_hidden_tests"], field_path="train_hidden_tests"),
        eval_hidden_tests=_parse_test_layer(value["eval_hidden_tests"], field_path="eval_hidden_tests"),
        reference_solution=_optional_string(value["reference_solution"], field_path="reference_solution"),
        sft_response=_optional_string(value["sft_response"], field_path="sft_response"),
        metadata=metadata_from_mapping(value["metadata"]),
    )
    validate_problem(problem)
    return problem


def test_case_to_mapping(test_case: TestCase) -> dict[str, JsonValue]:
    """Serialize a test case with exact §7.1 field names."""
    return {
        "input": json_value_to_mutable(test_case.input, field_path="test_case.input"),
        "expected": json_value_to_mutable(test_case.expected, field_path="test_case.expected"),
    }


def _metadata_to_mapping(metadata: ProblemMetadata) -> dict[str, JsonValue]:
    return {
        "difficulty": metadata.difficulty,
        "category": list(metadata.category),
        "time_limit_seconds": metadata.time_limit_seconds,
        "memory_limit_mb": metadata.memory_limit_mb,
        "license": metadata.license,
        "source_url_hash": metadata.source_url_hash,
    }


def problem_to_mapping(problem: CodeProblem) -> dict[str, JsonValue]:
    """Serialize an immutable problem to the exact §7.1 JSON structure."""
    validate_problem(problem)
    return {
        "problem_id": problem.problem_id,
        "source": problem.source,
        "split": problem.split,
        "prompt": problem.prompt,
        "function_name": problem.function_name,
        "function_signature": problem.function_signature,
        "starter_code": problem.starter_code,
        "visible_tests": [test_case_to_mapping(item) for item in problem.visible_tests],
        "train_hidden_tests": [test_case_to_mapping(item) for item in problem.train_hidden_tests],
        "eval_hidden_tests": [test_case_to_mapping(item) for item in problem.eval_hidden_tests],
        "reference_solution": problem.reference_solution,
        "sft_response": problem.sft_response,
        "metadata": _metadata_to_mapping(problem.metadata),
    }


def validate_problem(problem: CodeProblem) -> None:
    """Validate semantic invariants that are local to one canonical problem."""
    _require_nonempty_string(problem.problem_id, field_path="problem_id")
    _require_nonempty_string(problem.source, field_path="source")
    _require_nonempty_string(problem.prompt, field_path="prompt")
    _require_nonempty_string(problem.function_name, field_path="function_name")
    _require_nonempty_string(problem.function_signature, field_path="function_signature")
    if problem.split not in {"train", "validation", "test"}:
        raise SchemaError("split must be train, validation, or test")
    if not problem.visible_tests or not problem.train_hidden_tests or not problem.eval_hidden_tests:
        raise SchemaError("all three test layers must be non-empty")
    for layer in (problem.visible_tests, problem.train_hidden_tests, problem.eval_hidden_tests):
        for test_case in layer:
            test_case_to_mapping(test_case)
    metadata_from_mapping(_metadata_to_mapping(problem.metadata))
