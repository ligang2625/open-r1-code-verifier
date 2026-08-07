"""Deterministic completion generation contracts for WP5 evaluation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Protocol

from code_verifier.data.schema import CodeProblem, test_case_to_mapping


class GenerationError(RuntimeError):
    """Raised when model generation cannot satisfy the configured inference contract."""


@dataclass(frozen=True)
class GenerationConfig:
    """Frozen deterministic pass@1 decoding settings."""

    do_sample: bool
    temperature: float | None
    top_p: float | None
    max_new_tokens: int

    def __post_init__(self) -> None:
        validate_generation_config(self)


@dataclass(frozen=True)
class GenerationResult:
    """One generated completion plus bounded reproducibility metadata."""

    completion: str
    completion_tokens: int
    latency_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.completion, str):
            raise GenerationError("completion must be a string")
        try:
            self.completion.encode("utf-8")
        except UnicodeEncodeError:
            raise GenerationError("completion must contain valid UTF-8 text") from None
        if isinstance(self.completion_tokens, bool) or not isinstance(self.completion_tokens, int):
            raise GenerationError("completion_tokens must be a non-negative integer")
        if self.completion_tokens < 0:
            raise GenerationError("completion_tokens must be a non-negative integer")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int | float):
            raise GenerationError("latency_ms must be a finite non-negative number")
        try:
            latency = float(self.latency_ms)
        except OverflowError:
            raise GenerationError("latency_ms must be a finite non-negative number") from None
        if not math.isfinite(latency) or latency < 0:
            raise GenerationError("latency_ms must be a finite non-negative number")
        object.__setattr__(self, "latency_ms", latency)


class CompletionGenerator(Protocol):
    """Minimal generation interface consumed by the pass@1 evaluator."""

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        """Generate exactly one completion for one prompt and deterministic seed."""
        ...


def validate_generation_config(config: GenerationConfig) -> None:
    """Require the deterministic pass@1 decoding contract from the project specification."""
    if not isinstance(config.do_sample, bool) or config.do_sample:
        raise GenerationError("generation.do_sample must be false for deterministic pass@1")
    if config.temperature is not None:
        if isinstance(config.temperature, bool) or not isinstance(config.temperature, int | float):
            raise GenerationError("generation.temperature must be null for deterministic pass@1")
        try:
            finite_temperature = math.isfinite(float(config.temperature))
        except OverflowError:
            finite_temperature = False
        if not finite_temperature:
            raise GenerationError("generation.temperature must be finite when provided")
        raise GenerationError("generation.temperature must be null for deterministic pass@1")
    if config.top_p is not None:
        if isinstance(config.top_p, bool) or not isinstance(config.top_p, int | float):
            raise GenerationError("generation.top_p must be null for deterministic pass@1")
        try:
            finite_top_p = math.isfinite(float(config.top_p))
        except OverflowError:
            finite_top_p = False
        if not finite_top_p:
            raise GenerationError("generation.top_p must be finite when provided")
        raise GenerationError("generation.top_p must be null for deterministic pass@1")
    if isinstance(config.max_new_tokens, bool) or not isinstance(config.max_new_tokens, int):
        raise GenerationError("generation.max_new_tokens must be a positive integer")
    if not 1 <= config.max_new_tokens <= 4096:
        raise GenerationError("generation.max_new_tokens must be between 1 and 4096")


def build_evaluation_prompt(problem: CodeProblem) -> str:
    """Build the fixed §7.2 prompt using only the problem statement, signature, and visible tests."""
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
