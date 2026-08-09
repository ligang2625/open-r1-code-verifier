"""Tests for the strict raw JSONL adapter."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from code_verifier.data.adapters import InputAdapterError, load_raw_jsonl, raw_problem_from_mapping


def _raw_mapping() -> dict[str, object]:
    return {
        "problem_id": "p1",
        "source": "fixture",
        "split": "train",
        "prompt": "Return the input.",
        "function_name": "identity",
        "function_signature": "def identity(value):",
        "starter_code": None,
        "tests": [{"input": index, "expected": index} for index in range(6)],
        "reference_solution": "def identity(value): return value",
        "sft_response": "def identity(value): return value",
        "metadata": {
            "difficulty": "easy",
            "category": ["basics"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "MIT",
            "source_url_hash": None,
        },
    }


def test_load_raw_jsonl_reads_valid_records(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    first = _raw_mapping()
    second = _raw_mapping()
    second["problem_id"] = "p2"
    path.write_text(f"{json.dumps(first)}\r\n\r\n{json.dumps(second)}\r\n", encoding="utf-8")
    assert [problem.problem_id for problem in load_raw_jsonl(path)] == ["p1", "p2"]


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
def test_load_raw_jsonl_preserves_unicode_line_separator_inside_physical_line(
    tmp_path: Path,
    separator: str,
) -> None:
    path = tmp_path / "raw.jsonl"
    record = _raw_mapping()
    record["prompt"] = f"before{separator}after"
    path.write_text(f"{json.dumps(record, ensure_ascii=False)}\n", encoding="utf-8")

    assert load_raw_jsonl(path)[0].prompt == f"before{separator}after"


def test_load_raw_jsonl_reports_malformed_line_number(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    path.write_text(f"{json.dumps(_raw_mapping())}\n{{broken\n", encoding="utf-8")
    with pytest.raises(InputAdapterError, match=r"line 2"):
        load_raw_jsonl(path)


def test_load_raw_jsonl_rejects_duplicate_json_key(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    path.write_text('{"problem_id":"p1","problem_id":"p2"}\n', encoding="utf-8")
    with pytest.raises(InputAdapterError, match="duplicate JSON key"):
        load_raw_jsonl(path)


def test_load_raw_jsonl_rejects_nested_duplicate_json_key(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    path.write_text('{"tests":[{"input":1,"input":2,"expected":3}]}\n', encoding="utf-8")
    with pytest.raises(InputAdapterError, match="duplicate JSON key"):
        load_raw_jsonl(path)


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_raw_adapter_rejects_missing_or_unknown_fields(mutation: str) -> None:
    mapping = _raw_mapping()
    if mutation == "missing":
        del mapping["prompt"]
    else:
        mapping["unknown"] = True
    with pytest.raises(InputAdapterError):
        raw_problem_from_mapping(mapping)


def test_raw_adapter_rejects_pre_split_fields() -> None:
    mapping = _raw_mapping()
    mapping["visible_tests"] = mapping["tests"]
    with pytest.raises(InputAdapterError, match="pre-split"):
        raw_problem_from_mapping(mapping)


def test_load_raw_jsonl_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    path.write_text("\n  \n", encoding="utf-8")
    with pytest.raises(InputAdapterError, match="no records"):
        load_raw_jsonl(path)


def test_committed_fixture_has_expected_shape() -> None:
    """The committed smoke fixture has the exact WP1 size and split contract."""
    problems = load_raw_jsonl(Path("tests/fixtures/wp1/raw_problems.jsonl"))

    assert len(problems) == 20
    assert len({problem.problem_id for problem in problems}) == 20
    assert Counter(problem.split for problem in problems) == Counter({"train": 12, "validation": 4, "test": 4})
    assert all(len(problem.tests) == 6 for problem in problems)
