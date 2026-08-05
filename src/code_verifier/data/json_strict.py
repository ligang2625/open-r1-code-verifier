"""Strict JSON loading and comparison shared by every trusted JSONL path."""

from __future__ import annotations

import json
from typing import cast


class StrictJsonError(ValueError):
    """Raised when JSON is malformed or repeats an object key at any depth."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def loads_strict(text: str) -> object:
    """Parse one JSON value and reject duplicate keys at every nesting level."""
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise StrictJsonError(f"invalid JSON: {error}") from error


def json_values_equal(left: object, right: object) -> bool:
    """Compare JSON values with exact type sensitivity (bool != 1 != 1.0)."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        right_dict = cast(dict[object, object], right)
        return set(left) == set(right_dict) and all(json_values_equal(left[key], right_dict[key]) for key in left)
    if isinstance(left, list):
        right_list = cast(list[object], right)
        return len(left) == len(right_list) and all(
            json_values_equal(left_item, right_item) for left_item, right_item in zip(left, right_list, strict=True)
        )
    return left == right
