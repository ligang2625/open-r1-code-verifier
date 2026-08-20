"""Visible-only SFT trajectory validation and TRL dataset mapping."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from datasets import Dataset  # type: ignore[import-untyped]

from code_verifier.data.leakage_checks import (
    LeakageError,
    TrainingArtifactKind,
    check_training_record,
)
from code_verifier.execution.base import CodeExecutor, ExecutionStatus
from code_verifier.parsing.code_extractor import extract_python_code
from code_verifier.verification.result_types import VerificationContractError
from code_verifier.verification.verifier import verify_completion


@dataclass(frozen=True)
class SFTExample:
    """One validated prompt and normalized assistant completion."""

    problem_id: str
    prompt: str
    completion: str


@dataclass(frozen=True)
class _PreparedSFTRecord:
    """Validated non-executed SFT record used by both inline and manifest paths."""

    example: SFTExample
    function_name: str
    tests: Sequence[Mapping[str, object]]
    metadata: Mapping[str, object]


class SFTDataError(ValueError):
    """Raised when an SFT record cannot satisfy the training-data contract."""


def _validate_utf8(value: str, *, field_name: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise SFTDataError(f"{field_name} must contain valid UTF-8 text") from None
    return value


def _parse_raw_python(response: str, *, expected_function_name: str) -> str:
    try:
        module = ast.parse(response)
    except (SyntaxError, ValueError, UnicodeError, MemoryError, RecursionError):
        raise SFTDataError("sft_response must be valid Python or one supported fenced block") from None
    targets = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == expected_function_name
    ]
    if len(targets) != 1:
        raise SFTDataError("sft_response must define the expected top-level function exactly once")
    return response


def _has_excessive_repetition(code: str) -> bool:
    repeated_line: str | None = None
    repeated_count = 0
    for line in code.splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        if normalized == repeated_line:
            repeated_count += 1
        else:
            repeated_line = normalized
            repeated_count = 1
        if repeated_count >= 4:
            return True
    return False


def normalize_sft_completion(response: str, *, expected_function_name: str) -> str:
    """Normalize raw or singly fenced Python into exactly one closed Python block."""
    if not isinstance(response, str):
        raise SFTDataError("sft_response must be a string")
    _validate_utf8(response, field_name="sft_response")
    if not response.strip():
        raise SFTDataError("sft_response must be non-empty")
    if not isinstance(expected_function_name, str) or not expected_function_name.strip():
        raise SFTDataError("expected_function_name must be non-empty")

    normalized_response = response.replace("\r\n", "\n").replace("\r", "\n")
    parsed = extract_python_code(normalized_response, expected_function_name=expected_function_name)
    if parsed.success:
        if parsed.num_code_blocks != 1:
            raise SFTDataError("sft_response must contain exactly one code block")
        code = parsed.code
    else:
        if parsed.num_code_blocks != 0:
            raise SFTDataError("sft_response contains an invalid, duplicate, or truncated code block")
        code = _parse_raw_python(normalized_response, expected_function_name=expected_function_name)

    code = code.strip()
    validated = extract_python_code(
        f"```python\n{code}\n```",
        expected_function_name=expected_function_name,
    )
    if not validated.success:
        raise SFTDataError("normalized sft_response does not contain the expected function")
    if _has_excessive_repetition(code):
        raise SFTDataError("sft_response contains excessive repeated code")
    return f"```python\n{code}\n```"


def _prepare_sft_record(record: Mapping[str, object]) -> _PreparedSFTRecord:
    """Validate payload shape/leakage and normalize one SFT completion without execution."""
    try:
        check_training_record(record, kind=TrainingArtifactKind.SFT)
    except LeakageError as error:
        raise SFTDataError(str(error)) from None

    problem_id = record["problem_id"]
    prompt = record["prompt"]
    function_name = record["function_name"]
    response = record["sft_response"]
    tests = record["visible_tests"]
    metadata = record["metadata"]
    if not isinstance(problem_id, str) or not problem_id.strip():
        raise SFTDataError("sft record requires a non-empty problem_id")
    if not isinstance(prompt, str) or not prompt.strip():
        raise SFTDataError("sft record requires a non-empty prompt")
    _validate_utf8(problem_id, field_name="problem_id")
    _validate_utf8(prompt, field_name="prompt")
    if not isinstance(function_name, str):
        raise SFTDataError("sft record requires a valid function_name")
    if not isinstance(response, str):
        raise SFTDataError("sft record requires a string sft_response")
    if not isinstance(tests, Sequence) or isinstance(tests, str | bytes | bytearray):
        raise SFTDataError("sft record requires visible_tests")
    if not isinstance(metadata, Mapping):
        raise SFTDataError("sft record requires metadata")

    completion = normalize_sft_completion(response, expected_function_name=function_name)
    return _PreparedSFTRecord(
        example=SFTExample(problem_id=problem_id, prompt=prompt, completion=completion),
        function_name=function_name,
        tests=cast(Sequence[Mapping[str, object]], tests),
        metadata=metadata,
    )


def validate_sft_record(record: Mapping[str, object], *, executor: CodeExecutor) -> SFTExample:
    """Validate one training artifact row using only its caller-selected visible tests."""
    prepared = _prepare_sft_record(record)
    try:
        result = verify_completion(
            prepared.example.completion,
            prepared.tests,
            prepared.function_name,
            prepared.metadata,
            executor,
        )
    except VerificationContractError as error:
        raise SFTDataError(str(error)) from None
    if result.status is not ExecutionStatus.PASSED or result.passed_tests != result.total_tests:
        raise SFTDataError(f"SFT trajectory failed visible verification with status {result.status.value}")
    return prepared.example


def _chat_token_count(tokenizer: Any, example: SFTExample) -> int:
    chat_template = getattr(tokenizer, "chat_template", None)
    if not isinstance(chat_template, str) or not chat_template:
        raise SFTDataError("tokenizer must provide a chat template")
    messages = [
        {"role": "user", "content": example.prompt},
        {"role": "assistant", "content": example.completion},
    ]
    try:
        token_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
        length = len(token_ids)
    except Exception as error:
        raise SFTDataError(f"could not encode SFT chat sequence: {type(error).__name__}") from None
    if length <= 0:
        raise SFTDataError("tokenizer produced an empty SFT chat sequence")
    return length


def sft_example_token_count(tokenizer: Any, example: SFTExample) -> int:
    """Return the exact chat-template token count used by the SFT prevalidation contract."""
    return _chat_token_count(tokenizer, example)


def build_prevalidated_sft_dataset(records: Sequence[Mapping[str, object]]) -> Dataset:
    """Map manifest-validated SFT rows to the payload-minimal TRL dataset.

    No Piston call or token-length recomputation occurs here. Those properties
    are bound by the consumed prevalidation manifest; lightweight schema,
    leakage, and completion-normalization checks are repeated before training.
    """
    if isinstance(records, str | bytes | bytearray) or not isinstance(records, Sequence) or not records:
        raise SFTDataError("SFT records must be a non-empty sequence")
    trainer_rows: list[dict[str, list[dict[str, str]]]] = []
    for index, record in enumerate(records, start=1):
        try:
            prepared = _prepare_sft_record(record)
        except SFTDataError as error:
            raise SFTDataError(f"SFT record {index}: {error}") from None
        trainer_rows.append(
            {
                "prompt": [{"role": "user", "content": prepared.example.prompt}],
                "completion": [{"role": "assistant", "content": prepared.example.completion}],
            }
        )
    return Dataset.from_list(trainer_rows)


def build_sft_dataset(
    records: Sequence[Mapping[str, object]],
    *,
    executor: CodeExecutor,
    tokenizer: Any,
    max_seq_length: int,
) -> Dataset:
    """Validate SFT rows and return a payload-minimal conversational TRL dataset."""
    if isinstance(records, str | bytes | bytearray) or not isinstance(records, Sequence) or not records:
        raise SFTDataError("SFT records must be a non-empty sequence")
    if isinstance(max_seq_length, bool) or not isinstance(max_seq_length, int) or max_seq_length <= 0:
        raise SFTDataError("max_seq_length must be a positive integer")

    trainer_rows: list[dict[str, list[dict[str, str]]]] = []
    for index, record in enumerate(records, start=1):
        try:
            example = validate_sft_record(record, executor=executor)
            if _chat_token_count(tokenizer, example) > max_seq_length:
                raise SFTDataError("SFT sequence exceeds max_seq_length; target truncation is forbidden")
        except SFTDataError as error:
            raise SFTDataError(f"SFT record {index}: {error}") from None
        trainer_rows.append(
            {
                "prompt": [{"role": "user", "content": example.prompt}],
                "completion": [{"role": "assistant", "content": example.completion}],
            }
        )
    return Dataset.from_list(trainer_rows)
