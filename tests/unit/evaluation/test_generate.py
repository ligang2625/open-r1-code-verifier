"""Tests for deterministic evaluation prompt and generation contracts."""

from __future__ import annotations

import math

import pytest

from code_verifier.data.schema import CodeProblem, ProblemMetadata
from code_verifier.data.schema import TestCase as CodeTestCase
from code_verifier.evaluation.generate import (
    GenerationConfig,
    GenerationError,
    GenerationResult,
    build_evaluation_prompt,
)


def _problem() -> CodeProblem:
    return CodeProblem(
        problem_id="prompt-1",
        source="unit",
        split="test",
        prompt="Add one to the input.",
        function_name="add_one",
        function_signature="def add_one(x: int) -> int:",
        starter_code=None,
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


def test_build_evaluation_prompt_matches_spec_template() -> None:
    prompt = build_evaluation_prompt(_problem())
    assert prompt == (
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


def test_build_evaluation_prompt_contains_visible_examples_only() -> None:
    prompt = build_evaluation_prompt(_problem())
    assert '"input":1' in prompt
    assert '"expected":2' in prompt


def test_build_evaluation_prompt_excludes_hidden_sentinels() -> None:
    prompt = build_evaluation_prompt(_problem())
    for sentinel in (
        "TRAIN_HIDDEN_SENTINEL",
        "EVAL_HIDDEN_SENTINEL",
        "REFERENCE_SOLUTION_SENTINEL",
        "SFT_RESPONSE_SENTINEL",
    ):
        assert sentinel not in prompt


def test_generation_config_accepts_exact_pass1_defaults() -> None:
    config = GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=512)
    assert config.max_new_tokens == 512


@pytest.mark.parametrize(
    "kwargs",
    [
        {"do_sample": True, "temperature": None, "top_p": None, "max_new_tokens": 512},
        {"do_sample": False, "temperature": 0.0, "top_p": None, "max_new_tokens": 512},
        {"do_sample": False, "temperature": math.nan, "top_p": None, "max_new_tokens": 512},
        {"do_sample": False, "temperature": None, "top_p": 1.0, "max_new_tokens": 512},
        {"do_sample": False, "temperature": None, "top_p": math.inf, "max_new_tokens": 512},
        {"do_sample": False, "temperature": None, "top_p": None, "max_new_tokens": 0},
        {"do_sample": False, "temperature": None, "top_p": None, "max_new_tokens": 4097},
    ],
)
def test_generation_config_rejects_sampling_or_nonfinite_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(GenerationError):
        GenerationConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("completion", "tokens", "latency"),
    [
        ("ok", -1, 0.0),
        ("ok", 1, -1.0),
        ("ok", 1, math.nan),
        ("ok", 1, math.inf),
        ("\ud800", 1, 0.0),
    ],
)
def test_generation_result_contract_rejects_invalid_values(completion: str, tokens: int, latency: float) -> None:
    with pytest.raises(GenerationError):
        GenerationResult(completion=completion, completion_tokens=tokens, latency_ms=latency)
