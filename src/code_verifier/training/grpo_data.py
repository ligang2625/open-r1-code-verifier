"""Payload-minimal conversational datasets for Public and Hidden GRPO."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from datasets import Dataset  # type: ignore[import-untyped]

from code_verifier.data.leakage_checks import LeakageError, TrainingArtifactKind, check_training_record
from code_verifier.prompting import build_code_prompt_from_fields


class GRPODataError(ValueError):
    """Raised when a GRPO artifact cannot satisfy the trainer-data contract."""


def _nonempty_utf8(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GRPODataError(f"{field_name} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise GRPODataError(f"{field_name} must contain valid UTF-8 text") from None
    return value


def _sequence(value: object, *, field_name: str) -> Sequence[object]:
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence) or not value:
        raise GRPODataError(f"{field_name} must be a non-empty sequence")
    return cast(Sequence[object], value)


def _mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise GRPODataError(f"{field_name} must be a mapping with string keys")
    return cast(Mapping[str, object], value)


def _encoded_test_case(value: Mapping[str, object], *, field_name: str) -> str:
    """Encode one heterogeneous JSON test case into an Arrow-stable scalar string."""
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError):
        raise GRPODataError(f"{field_name} must be finite and JSON serializable") from None


def _contains_forbidden_key(value: object) -> bool:
    forbidden = {"eval_hidden_tests", "reference_solution", "starter_code", "sft_response"}
    if isinstance(value, Mapping):
        return any(key in forbidden or _contains_forbidden_key(item) for key, item in value.items())
    if isinstance(value, list | tuple):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def build_grpo_dataset(
    records: Sequence[Mapping[str, object]],
    *,
    reward_mode: str,
) -> Dataset:
    """Validate one training artifact and build exact TRL conversational rows."""
    if reward_mode not in {"public", "hidden"}:
        raise GRPODataError("reward_mode must be public or hidden")
    if isinstance(records, str | bytes | bytearray) or not isinstance(records, Sequence) or not records:
        raise GRPODataError("GRPO records must be a non-empty sequence")
    kind = TrainingArtifactKind.PUBLIC_GRPO if reward_mode == "public" else TrainingArtifactKind.HIDDEN_GRPO
    rows: list[dict[str, Any]] = []
    problem_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise GRPODataError(f"GRPO record {index} must be a mapping")
        try:
            check_training_record(record, kind=kind)
        except LeakageError as error:
            raise GRPODataError(str(error)) from None
        if _contains_forbidden_key(record):
            raise GRPODataError("GRPO record contains a forbidden training-data key")

        problem_id = _nonempty_utf8(record["problem_id"], field_name="problem_id")
        if problem_id in problem_ids:
            raise GRPODataError("GRPO records contain duplicate problem_id values")
        problem_ids.add(problem_id)
        problem_statement = _nonempty_utf8(record["prompt"], field_name="prompt")
        function_signature = _nonempty_utf8(record["function_signature"], field_name="function_signature")
        function_name = _nonempty_utf8(record["function_name"], field_name="function_name")
        visible_tests = _sequence(record["visible_tests"], field_name="visible_tests")
        metadata = _mapping(record["metadata"], field_name="metadata")
        visible_mappings = [
            _mapping(test, field_name=f"visible_tests[{test_index}]") for test_index, test in enumerate(visible_tests)
        ]
        row: dict[str, Any] = {
            "prompt": [
                {
                    "role": "user",
                    "content": build_code_prompt_from_fields(
                        problem_statement,
                        function_signature,
                        visible_mappings,
                    ),
                }
            ],
            "problem_id": problem_id,
            "function_name": function_name,
            "metadata": dict(metadata),
            "visible_tests": [
                _encoded_test_case(test, field_name=f"visible_tests[{test_index}]")
                for test_index, test in enumerate(visible_mappings)
            ],
        }
        if reward_mode == "hidden":
            hidden_tests = _sequence(record["train_hidden_tests"], field_name="train_hidden_tests")
            row["train_hidden_tests"] = [
                _encoded_test_case(
                    _mapping(test, field_name=f"train_hidden_tests[{test_index}]"),
                    field_name=f"train_hidden_tests[{test_index}]",
                )
                for test_index, test in enumerate(hidden_tests)
            ]
        rows.append(row)
    return Dataset.from_list(rows)
