"""Tests for the shared visible-only code prompt."""

from __future__ import annotations

from code_verifier.data.schema import CodeProblem, ProblemMetadata
from code_verifier.data.schema import TestCase as CodeTestCase
from code_verifier.data.schema import test_case_to_mapping as case_to_mapping
from code_verifier.prompting import build_code_prompt, build_code_prompt_from_fields


def _problem() -> CodeProblem:
    return CodeProblem(
        problem_id="prompt-1",
        source="unit",
        split="train",
        prompt="Add one to the input.",
        function_name="add_one",
        function_signature="def add_one(x: int) -> int:",
        starter_code="STARTER_SENTINEL",
        visible_tests=(CodeTestCase(input=1, expected=2),),
        train_hidden_tests=(CodeTestCase(input="TRAIN_HIDDEN_SENTINEL", expected=0),),
        eval_hidden_tests=(CodeTestCase(input="EVAL_HIDDEN_SENTINEL", expected=0),),
        reference_solution="REFERENCE_SOLUTION_SENTINEL",
        sft_response="SFT_RESPONSE_SENTINEL",
        metadata=ProblemMetadata(
            difficulty="easy",
            category=("math",),
            time_limit_seconds=1.0,
            memory_limit_mb=128,
            license="test",
            source_url_hash=None,
        ),
    )


def test_build_code_prompt_matches_section_7_2_contract() -> None:
    assert build_code_prompt(_problem()) == (
        "You are given a Python programming problem.\n\n"
        "Problem:\n"
        "Add one to the input.\n\n"
        "Function signature:\n"
        "def add_one(x: int) -> int:\n\n"
        "Visible examples:\n"
        '[{"expected":2,"input":1}]\n\n'
        "Return a correct implementation.\n"
        "The final answer must contain exactly one Python code block.\n"
        "Do not read from stdin unless the problem explicitly requires it.\n"
        "Do not print debugging information."
    )


def test_build_code_prompt_uses_visible_examples_only() -> None:
    prompt = build_code_prompt(_problem())
    assert '"input":1' in prompt
    for sentinel in (
        "STARTER_SENTINEL",
        "TRAIN_HIDDEN_SENTINEL",
        "EVAL_HIDDEN_SENTINEL",
        "REFERENCE_SOLUTION_SENTINEL",
        "SFT_RESPONSE_SENTINEL",
    ):
        assert sentinel not in prompt


def test_build_code_prompt_from_fields_matches_existing_problem_prompt() -> None:
    problem = _problem()
    assert build_code_prompt_from_fields(
        problem.prompt,
        problem.function_signature,
        [case_to_mapping(test) for test in problem.visible_tests],
    ) == build_code_prompt(problem)
