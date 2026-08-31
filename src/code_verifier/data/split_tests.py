"""Deterministic assignment of tests to visible and hidden layers."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass

from code_verifier.data.adapters import RawCodeProblem
from code_verifier.data.deduplicate import ensure_unique_test_cases
from code_verifier.data.schema import CodeProblem, TestCase, validate_problem


@dataclass(frozen=True)
class TestSplitConfig:
    """Required size of each test layer."""

    visible_count: int
    train_hidden_count: int
    eval_hidden_count: int


def validate_test_split_config(config: TestSplitConfig) -> None:
    """Require positive layer sizes and visible_count within the §7.3 recommendation of 2-5."""
    counts = (config.visible_count, config.train_hidden_count, config.eval_hidden_count)
    if any(isinstance(count, bool) or not isinstance(count, int) or count <= 0 for count in counts):
        raise ValueError("all test split counts must be positive integers")
    if not 2 <= config.visible_count <= 5:
        raise ValueError("visible_count must be between 2 and 5")


def split_test_cases(
    tests: Sequence[TestCase],
    *,
    problem_id: str,
    seed: int,
    config: TestSplitConfig,
) -> tuple[tuple[TestCase, ...], tuple[TestCase, ...], tuple[TestCase, ...]]:
    """Deterministically shuffle unique tests and return visible/train-hidden/eval-hidden layers."""
    validate_test_split_config(config)
    ensure_unique_test_cases(tests, context=f"problem {problem_id}")
    expected_count = config.visible_count + config.train_hidden_count + config.eval_hidden_count
    if len(tests) != expected_count:
        raise ValueError(f"problem {problem_id} requires exactly {expected_count} tests, got {len(tests)}")

    digest = hashlib.sha256(f"{seed}:{problem_id}".encode()).digest()
    local_seed = int.from_bytes(digest, byteorder="big")
    shuffled = list(tests)
    random.Random(local_seed).shuffle(shuffled)

    visible_end = config.visible_count
    hidden_end = visible_end + config.train_hidden_count
    return (
        tuple(shuffled[:visible_end]),
        tuple(shuffled[visible_end:hidden_end]),
        tuple(shuffled[hidden_end:]),
    )


def split_refresh_test_cases(
    tests: Sequence[TestCase],
    *,
    problem_id: str,
    seed: int,
) -> tuple[tuple[TestCase, ...], tuple[TestCase, ...], tuple[TestCase, ...]]:
    """Split one WP9-a candidate into deterministic non-empty visible/hidden layers."""
    ensure_unique_test_cases(tests, context=f"refresh problem {problem_id}")
    if len(tests) < 4:
        raise ValueError(f"refresh problem {problem_id} requires at least 4 unique tests, got {len(tests)}")

    digest = hashlib.sha256(f"wp9a-refresh-tests-v1|{seed}|{problem_id}".encode()).digest()
    shuffled = list(tests)
    random.Random(int.from_bytes(digest, byteorder="big")).shuffle(shuffled)

    visible_count = 2
    if len(shuffled) >= 8:
        train_hidden_count = 3
    else:
        remaining = len(shuffled) - visible_count
        train_hidden_count = remaining // 2
    hidden_end = visible_count + train_hidden_count
    return (
        tuple(shuffled[:visible_count]),
        tuple(shuffled[visible_count:hidden_end]),
        tuple(shuffled[hidden_end:]),
    )


def adapt_raw_problem(raw: RawCodeProblem, *, seed: int, config: TestSplitConfig) -> CodeProblem:
    """Split one raw problem and build a validated canonical problem."""
    visible, train_hidden, eval_hidden = split_test_cases(
        raw.tests,
        problem_id=raw.problem_id,
        seed=seed,
        config=config,
    )
    problem = CodeProblem(
        problem_id=raw.problem_id,
        source=raw.source,
        split=raw.split,
        prompt=raw.prompt,
        function_name=raw.function_name,
        function_signature=raw.function_signature,
        starter_code=raw.starter_code,
        visible_tests=visible,
        train_hidden_tests=train_hidden,
        eval_hidden_tests=eval_hidden,
        reference_solution=raw.reference_solution,
        sft_response=raw.sft_response,
        metadata=raw.metadata,
    )
    validate_problem(problem)
    return problem
