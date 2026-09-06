"""Contracts for the frozen C29 active-1354 GRPO configs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from code_verifier.training.grpo import (
    GRPOTrainingConfig,
    load_grpo_training_config,
    validate_grpo_config_pair,
)


def _load(name: str) -> GRPOTrainingConfig:
    return load_grpo_training_config(Path("configs/grpo") / name)


def test_c29_formal_pair_uses_frozen_k8_contract_without_prompt_truncation() -> None:
    public = _load("wp9c-c29-active1354-public.yaml")
    hidden = _load("wp9c-c29-active1354-hidden.yaml")

    validate_grpo_config_pair(public, hidden)
    assert public.num_generations == hidden.num_generations == 8
    assert public.max_prompt_length == hidden.max_prompt_length == 2048
    assert public.max_completion_length == hidden.max_completion_length == 512
    assert public.max_steps == hidden.max_steps == 300
    assert public.seed == hidden.seed == 42


def test_c29_benchmark_pair_is_bounded_formal_scientific_variant() -> None:
    public = _load("wp9c-c29-active1354-public.yaml")
    hidden = _load("wp9c-c29-active1354-hidden.yaml")
    benchmark_public = _load("wp9c-c29-active1354-benchmark-public.yaml")
    benchmark_hidden = _load("wp9c-c29-active1354-benchmark-hidden.yaml")

    validate_grpo_config_pair(benchmark_public, benchmark_hidden)
    assert benchmark_public.max_steps == benchmark_hidden.max_steps == 20
    assert (
        replace(
            benchmark_public,
            run_name=public.run_name,
            max_steps=public.max_steps,
        )
        == public
    )
    assert (
        replace(
            benchmark_hidden,
            run_name=hidden.run_name,
            max_steps=hidden.max_steps,
        )
        == hidden
    )


def test_c29_k4_diagnostic_changes_only_group_size_and_run_identity() -> None:
    k8_public = _load("wp9c-c29-active1354-benchmark-public.yaml")
    k8_hidden = _load("wp9c-c29-active1354-benchmark-hidden.yaml")
    k4_public = _load("wp9c-c29-active1354-benchmark-k4-public.yaml")
    k4_hidden = _load("wp9c-c29-active1354-benchmark-k4-hidden.yaml")

    validate_grpo_config_pair(k4_public, k4_hidden)
    assert k4_public.num_generations == k4_hidden.num_generations == 4
    assert replace(k4_public, run_name=k8_public.run_name, num_generations=8) == k8_public
    assert replace(k4_hidden, run_name=k8_hidden.run_name, num_generations=8) == k8_hidden


def test_c29_pilot_pair_changes_only_bounded_budget_and_run_identity() -> None:
    public = _load("wp9c-c29-active1354-public.yaml")
    hidden = _load("wp9c-c29-active1354-hidden.yaml")
    pilot_public = _load("wp9c-c29-active1354-pilot-public.yaml")
    pilot_hidden = _load("wp9c-c29-active1354-pilot-hidden.yaml")

    validate_grpo_config_pair(pilot_public, pilot_hidden)
    assert pilot_public.max_steps == pilot_hidden.max_steps == 100
    assert replace(pilot_public, run_name=public.run_name, max_steps=public.max_steps) == public
    assert replace(pilot_hidden, run_name=hidden.run_name, max_steps=hidden.max_steps) == hidden
