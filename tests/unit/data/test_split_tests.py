"""Tests for deterministic three-layer test assignment."""

from __future__ import annotations

from itertools import chain

import pytest

from code_verifier.data.adapters import raw_problem_from_mapping
from code_verifier.data.deduplicate import DuplicateDataError
from code_verifier.data.deduplicate import test_case_hash as hash_test_case
from code_verifier.data.schema import TestCase as CodeTestCase
from code_verifier.data.split_tests import (
    TestSplitConfig as SplitConfig,
)
from code_verifier.data.split_tests import (
    adapt_raw_problem,
    split_test_cases,
    validate_test_split_config,
)


def _tests() -> tuple[CodeTestCase, ...]:
    return tuple(CodeTestCase(input=index, expected=index * 2) for index in range(6))


def _config() -> SplitConfig:
    return SplitConfig(visible_count=2, train_hidden_count=2, eval_hidden_count=2)


def _raw_mapping() -> dict[str, object]:
    return {
        "problem_id": "double",
        "source": "fixture",
        "split": "train",
        "prompt": "Double an integer.",
        "function_name": "double",
        "function_signature": "def double(value: int) -> int:",
        "starter_code": None,
        "tests": [{"input": index, "expected": index * 2} for index in range(6)],
        "reference_solution": "def double(value): return value * 2",
        "sft_response": "def double(value): return value * 2",
        "metadata": {
            "difficulty": "easy",
            "category": ["math"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "MIT",
            "source_url_hash": None,
        },
    }


def test_split_is_deterministic_for_same_seed() -> None:
    assert split_test_cases(_tests(), problem_id="double", seed=42, config=_config()) == split_test_cases(
        _tests(), problem_id="double", seed=42, config=_config()
    )


def test_split_changes_for_different_seed() -> None:
    assert split_test_cases(_tests(), problem_id="double", seed=1, config=_config()) != split_test_cases(
        _tests(), problem_id="double", seed=2, config=_config()
    )


def test_split_preserves_every_test_exactly_once() -> None:
    layers = split_test_cases(_tests(), problem_id="double", seed=42, config=_config())
    original = {hash_test_case(test_case) for test_case in _tests()}
    assigned = [hash_test_case(test_case) for test_case in chain.from_iterable(layers)]
    assert set(assigned) == original
    assert len(assigned) == len(set(assigned)) == 6


def test_split_rejects_duplicate_tests() -> None:
    tests = (*_tests()[:-1], _tests()[0])
    with pytest.raises(DuplicateDataError):
        split_test_cases(tests, problem_id="double", seed=42, config=_config())


def test_split_rejects_wrong_total_count() -> None:
    with pytest.raises(ValueError, match="exactly 6"):
        split_test_cases(_tests()[:-1], problem_id="double", seed=42, config=_config())


@pytest.mark.parametrize(
    "config",
    [
        SplitConfig(visible_count=1, train_hidden_count=2, eval_hidden_count=2),
        SplitConfig(visible_count=6, train_hidden_count=2, eval_hidden_count=2),
        SplitConfig(visible_count=2, train_hidden_count=0, eval_hidden_count=2),
        SplitConfig(visible_count=2, train_hidden_count=2, eval_hidden_count=-1),
    ],
)
def test_split_config_rejects_invalid_counts(config: SplitConfig) -> None:
    with pytest.raises(ValueError):
        validate_test_split_config(config)


def test_adapt_raw_problem_produces_valid_canonical_problem() -> None:
    raw = raw_problem_from_mapping(_raw_mapping())
    problem = adapt_raw_problem(raw, seed=42, config=_config())
    assert problem.problem_id == raw.problem_id
    assert [len(problem.visible_tests), len(problem.train_hidden_tests), len(problem.eval_hidden_tests)] == [2, 2, 2]
