"""Shared reward input contracts and batch helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from code_verifier.execution.base import CodeExecutor


class RewardContractError(ValueError):
    """Raised when reward callback inputs or computed components violate the public contract."""


def _batch_length(value: object, *, field_name: str) -> int:
    """Return the length of one non-string batch sequence or raise a sanitized contract error."""
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
        raise RewardContractError(f"{field_name} must be a non-string sequence")
    return len(value)


def _extract_completion_text(item: object) -> str:
    """Extract exact completion text from a raw string or pinned Open-R1 chat-style item."""
    if isinstance(item, str):
        return item
    if isinstance(item, bytes | bytearray | Mapping) or not isinstance(item, Sequence) or not item:
        raise RewardContractError("completion item must be a string or non-empty chat sequence")
    last_message = item[-1]
    if not isinstance(last_message, Mapping):
        raise RewardContractError("chat completion must end with a message mapping")
    content = last_message.get("content")
    if not isinstance(content, str):
        raise RewardContractError("chat completion final content must be a string")
    return content


def _completion_texts(completions: object) -> list[str]:
    """Validate and extract every completion before any verifier/executor side effect."""
    _batch_length(completions, field_name="completions")
    batch = cast(Sequence[object], completions)
    return [_extract_completion_text(item) for item in batch]


def _validate_batch_alignment(
    completions: object,
    tests_batch: object,
    function_names: object,
    metadata_batch: object,
) -> int:
    """Require four equal batch lengths without zip-based truncation."""
    lengths = {
        "completions": _batch_length(completions, field_name="completions"),
        "tests_batch": _batch_length(tests_batch, field_name="tests_batch"),
        "function_names": _batch_length(function_names, field_name="function_names"),
        "metadata_batch": _batch_length(metadata_batch, field_name="metadata_batch"),
    }
    expected = lengths["completions"]
    if any(length != expected for length in lengths.values()):
        details = ", ".join(f"{name}={length}" for name, length in lengths.items())
        raise RewardContractError(f"reward batch lengths must match: {details}")
    return expected


def _require_executor(value: object) -> CodeExecutor:
    """Return an executor-like object with callable execute, or raise before scoring."""
    execute = getattr(value, "execute", None)
    if not callable(execute):
        raise RewardContractError("executor must provide a callable execute method")
    return cast(CodeExecutor, value)
