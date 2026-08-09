"""Strict offline raw-JSONL input adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.schema import (
    ProblemMetadata,
    SchemaError,
    TestCase,
    metadata_from_mapping,
    test_case_from_mapping,
)


class InputAdapterError(ValueError):
    """Raised when a raw input file or record cannot be adapted."""


@dataclass(frozen=True)
class RawCodeProblem:
    """One validated problem before its tests have been assigned to layers."""

    problem_id: str
    source: str
    split: Literal["train", "validation", "test"]
    prompt: str
    function_name: str
    function_signature: str
    starter_code: str | None
    tests: tuple[TestCase, ...]
    reference_solution: str | None
    sft_response: str | None
    metadata: ProblemMetadata


_RAW_FIELDS = {
    "problem_id",
    "source",
    "split",
    "prompt",
    "function_name",
    "function_signature",
    "starter_code",
    "tests",
    "reference_solution",
    "sft_response",
    "metadata",
}
_PRE_SPLIT_FIELDS = {"visible_tests", "train_hidden_tests", "eval_hidden_tests"}


def _context(line_number: int | None) -> str:
    return "" if line_number is None else f"line {line_number}: "


def _nonempty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputAdapterError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_string(value: object, *, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise InputAdapterError(f"{field} must be a string or null")
    return value


def raw_problem_from_mapping(value: object, *, line_number: int | None = None) -> RawCodeProblem:
    """Parse one exact raw JSONL record and attach line context to errors."""
    prefix = _context(line_number)
    try:
        if not isinstance(value, dict):
            raise InputAdapterError("raw problem must be an object")
        actual = set(value)
        forbidden = actual & _PRE_SPLIT_FIELDS
        if forbidden:
            raise InputAdapterError(f"pre-split field(s) are forbidden: {', '.join(sorted(forbidden))}")
        missing = _RAW_FIELDS - actual
        unknown = actual - _RAW_FIELDS
        if missing:
            raise InputAdapterError(f"missing required field(s): {', '.join(sorted(missing))}")
        if unknown:
            raise InputAdapterError(f"unknown field(s): {', '.join(sorted(str(key) for key in unknown))}")

        split = value["split"]
        if split not in {"train", "validation", "test"}:
            raise InputAdapterError("split must be train, validation, or test")
        tests = value["tests"]
        if not isinstance(tests, list) or not tests:
            raise InputAdapterError("tests must be a non-empty list")
        parsed_tests = tuple(
            test_case_from_mapping(test_case, field_path=f"tests[{index}]") for index, test_case in enumerate(tests)
        )
        return RawCodeProblem(
            problem_id=_nonempty_string(value["problem_id"], field="problem_id"),
            source=_nonempty_string(value["source"], field="source"),
            split=cast(Literal["train", "validation", "test"], split),
            prompt=_nonempty_string(value["prompt"], field="prompt"),
            function_name=_nonempty_string(value["function_name"], field="function_name"),
            function_signature=_nonempty_string(value["function_signature"], field="function_signature"),
            starter_code=_optional_string(value["starter_code"], field="starter_code"),
            tests=parsed_tests,
            reference_solution=_optional_string(value["reference_solution"], field="reference_solution"),
            sft_response=_optional_string(value["sft_response"], field="sft_response"),
            metadata=metadata_from_mapping(value["metadata"]),
        )
    except (InputAdapterError, SchemaError) as error:
        raise InputAdapterError(f"{prefix}{error}") from error


def load_raw_jsonl(path: Path) -> list[RawCodeProblem]:
    """Load physical-LF JSONL, accepting CRLF and ignoring blank/trailing lines."""
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeError) as error:
        raise InputAdapterError(f"Could not read raw JSONL {path}: {error}") from error

    problems: list[RawCodeProblem] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = loads_strict(line)
            problems.append(raw_problem_from_mapping(value, line_number=line_number))
        except (StrictJsonError, InputAdapterError) as error:
            raise InputAdapterError(f"{path}, line {line_number}: {error}") from error
    if not problems:
        raise InputAdapterError(f"Raw JSONL {path} contains no records")
    return problems
