"""Deterministic normalization, hashing, and duplicate detection."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence

from code_verifier.data.schema import (
    CodeProblem,
    FrozenJsonValue,
    JsonValue,
    TestCase,
    json_value_to_mutable,
    validate_json_value,
)


class DuplicateDataError(ValueError):
    """Raised when duplicate tests or problems would contaminate a dataset."""


def normalize_text(value: str) -> str:
    """Normalize Unicode plus all whitespace deterministically."""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def _normalize_json(value: object) -> JsonValue:
    return _normalize_frozen_json(validate_json_value(value, field_path="value"))


def _normalize_frozen_json(value: FrozenJsonValue) -> JsonValue:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, tuple):
        return [_normalize_frozen_json(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _normalize_frozen_json(item) for key, item in value.items()}
    return value


def canonical_json(value: object) -> str:
    """Serialize a JSON value with stable key ordering and separators."""
    validated = json_value_to_mutable(value, field_path="value")
    return json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stable_json_hash(value: object) -> str:
    """Return the lowercase SHA-256 hex digest of canonical JSON."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def test_case_hash(test_case: TestCase) -> str:
    """Hash one test's normalized input and expected value."""
    if isinstance(test_case.input, str) and isinstance(test_case.expected, str):
        normalized_input = json.encoder.encode_basestring(normalize_text(test_case.input))
        normalized_expected = json.encoder.encode_basestring(normalize_text(test_case.expected))
        payload = f'{{"expected":{normalized_expected},"input":{normalized_input}}}'
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    value: JsonValue = {
        "input": _normalize_json(test_case.input),
        "expected": _normalize_json(test_case.expected),
    }
    return stable_json_hash(value)


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_text(value)
    return normalized or None


def problem_prompt_signature_hash(problem: CodeProblem) -> str:
    """Hash the normalized problem statement and function contract."""
    return stable_json_hash(
        {
            "prompt": normalize_text(problem.prompt),
            "function_signature": normalize_text(problem.function_signature),
        }
    )


def problem_reference_solution_hash(problem: CodeProblem) -> str | None:
    """Hash a non-empty normalized reference solution independently of other fields."""
    normalized = _normalized_optional_text(problem.reference_solution)
    return None if normalized is None else stable_json_hash(normalized)


def problem_test_set_hash(problem: CodeProblem) -> str:
    """Hash the complete normalized test set while ignoring layer assignment."""
    test_hashes = sorted(
        test_case_hash(test_case)
        for layer in (problem.visible_tests, problem.train_hidden_tests, problem.eval_hidden_tests)
        for test_case in layer
    )
    return stable_json_hash(test_hashes)


def problem_content_hash(problem: CodeProblem) -> str:
    """Hash normalized task content while excluding ID, source, split, and layer assignment."""
    value: JsonValue = {
        "prompt_signature": problem_prompt_signature_hash(problem),
        "function_name": normalize_text(problem.function_name),
        "starter_code": _normalized_optional_text(problem.starter_code),
        "reference_solution": problem_reference_solution_hash(problem),
        "tests": problem_test_set_hash(problem),
    }
    return stable_json_hash(value)


def unique_test_case_hashes(test_cases: Sequence[TestCase], *, context: str) -> tuple[str, ...]:
    """Return normalized test hashes while rejecting duplicates in one pass."""
    first_index: dict[str, int] = {}
    hashes: list[str] = []
    for index, test_case in enumerate(test_cases):
        digest = test_case_hash(test_case)
        if digest in first_index:
            raise DuplicateDataError(
                f"{context} contains duplicate normalized tests at indexes {first_index[digest]} and {index}"
            )
        first_index[digest] = index
        hashes.append(digest)
    return tuple(hashes)


def ensure_unique_test_cases(test_cases: Sequence[TestCase], *, context: str) -> None:
    """Reject duplicate normalized test cases in one input collection."""
    unique_test_case_hashes(test_cases, context=context)


def ensure_unique_problem_ids(problems: Sequence[CodeProblem]) -> None:
    """Reject repeated problem_id values across the dataset."""
    first_index: dict[str, int] = {}
    for index, problem in enumerate(problems):
        if problem.problem_id in first_index:
            raise DuplicateDataError(
                f"duplicate problem_id {problem.problem_id!r} at indexes {first_index[problem.problem_id]} and {index}"
            )
        first_index[problem.problem_id] = index


def _raise_cross_split_overlap(previous: CodeProblem, problem: CodeProblem, *, signal: str) -> None:
    raise DuplicateDataError(
        f"normalized {signal} overlaps across splits: {previous.problem_id} ({previous.split}) and "
        f"{problem.problem_id} ({problem.split})"
    )


def _check_index(
    index: dict[str, CodeProblem],
    digest: str | None,
    problem: CodeProblem,
    *,
    signal: str,
) -> None:
    if digest is None:
        return
    previous = index.get(digest)
    if previous is not None and previous.split != problem.split:
        _raise_cross_split_overlap(previous, problem, signal=signal)
    index.setdefault(digest, problem)


def ensure_no_problem_overlap_across_splits(problems: Sequence[CodeProblem]) -> None:
    """Reject independent prompt, solution, and test contamination signals across data splits."""
    content_index: dict[str, CodeProblem] = {}
    prompt_index: dict[str, CodeProblem] = {}
    solution_index: dict[str, CodeProblem] = {}
    test_set_index: dict[str, CodeProblem] = {}
    signature_test_index: dict[tuple[str, str], CodeProblem] = {}

    for problem in problems:
        _check_index(content_index, problem_content_hash(problem), problem, signal="full content")
        _check_index(prompt_index, problem_prompt_signature_hash(problem), problem, signal="prompt/signature")
        _check_index(
            solution_index,
            problem_reference_solution_hash(problem),
            problem,
            signal="reference solution",
        )
        _check_index(test_set_index, problem_test_set_hash(problem), problem, signal="test set")

        signature = normalize_text(problem.function_signature)
        for layer in (problem.visible_tests, problem.train_hidden_tests, problem.eval_hidden_tests):
            for test_case in layer:
                key = (signature, test_case_hash(test_case))
                previous = signature_test_index.get(key)
                if previous is not None and previous.split != problem.split:
                    _raise_cross_split_overlap(previous, problem, signal="test case for matching signature")
                signature_test_index.setdefault(key, problem)
