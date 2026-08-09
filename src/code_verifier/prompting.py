"""Shared visible-only prompt contracts for code generation."""

from __future__ import annotations

import json

from code_verifier.data.schema import CodeProblem, test_case_to_mapping


def build_code_prompt(problem: CodeProblem) -> str:
    """Build the fixed §7.2 code prompt from visible problem fields only."""
    visible_examples = json.dumps(
        [test_case_to_mapping(test_case) for test_case in problem.visible_tests],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        "You are given a Python programming problem.\n\n"
        "Problem:\n"
        f"{problem.prompt}\n\n"
        "Function signature:\n"
        f"{problem.function_signature}\n\n"
        "Visible examples:\n"
        f"{visible_examples}\n\n"
        "Return a correct implementation.\n"
        "The final answer must contain exactly one Python code block.\n"
        "Do not read from stdin unless the problem explicitly requires it.\n"
        "Do not print debugging information."
    )
