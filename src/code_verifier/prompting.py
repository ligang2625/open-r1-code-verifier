"""Shared visible-only prompt contracts for code generation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from code_verifier.data.schema import CodeProblem, test_case_to_mapping


def build_code_prompt_from_fields(
    problem_statement: str,
    function_signature: str,
    visible_tests: Sequence[Mapping[str, object]],
) -> str:
    """Build the fixed §7.2 code prompt from its visible fields."""
    visible_examples = json.dumps(
        [dict(test_case) for test_case in visible_tests],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        "You are given a Python programming problem.\n\n"
        "Problem:\n"
        f"{problem_statement}\n\n"
        "Function signature:\n"
        f"{function_signature}\n\n"
        "Visible examples:\n"
        f"{visible_examples}\n\n"
        "Return a correct implementation.\n"
        "The final answer must contain exactly one Python code block.\n"
        "Do not read from stdin unless the problem explicitly requires it.\n"
        "Do not print debugging information."
    )


def build_code_prompt(problem: CodeProblem) -> str:
    """Build the fixed §7.2 code prompt from visible problem fields only."""
    return build_code_prompt_from_fields(
        problem.prompt,
        problem.function_signature,
        [test_case_to_mapping(test_case) for test_case in problem.visible_tests],
    )
