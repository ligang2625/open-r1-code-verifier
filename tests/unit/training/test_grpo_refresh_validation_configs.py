"""Static contracts for the bounded WP9-c GRPO validation configs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from code_verifier.training.grpo import load_grpo_training_config, validate_grpo_config_pair


def _load(name: str):
    return load_grpo_training_config(Path("configs/grpo") / name)


def test_wp9c_benchmark_pairs_are_bounded_and_match_refresh_settings() -> None:
    public = _load("refresh-benchmark-public.yaml")
    hidden = _load("refresh-benchmark-hidden.yaml")
    formal_public = _load("refresh-public.yaml")
    formal_hidden = _load("refresh-hidden.yaml")

    validate_grpo_config_pair(public, hidden)
    assert public.num_generations == hidden.num_generations == 8
    assert public.max_steps == hidden.max_steps == 20
    assert replace(public, run_name=formal_public.run_name, max_steps=formal_public.max_steps) == formal_public
    assert replace(hidden, run_name=formal_hidden.run_name, max_steps=formal_hidden.max_steps) == formal_hidden


def test_wp9c_k4_diagnostic_is_only_a_group_size_variant() -> None:
    k8_public = _load("refresh-benchmark-public.yaml")
    k8_hidden = _load("refresh-benchmark-hidden.yaml")
    k4_public = _load("refresh-benchmark-k4-public.yaml")
    k4_hidden = _load("refresh-benchmark-k4-hidden.yaml")

    validate_grpo_config_pair(k4_public, k4_hidden)
    assert k4_public.num_generations == k4_hidden.num_generations == 4
    assert replace(k4_public, run_name=k8_public.run_name, num_generations=8) == k8_public
    assert replace(k4_hidden, run_name=k8_hidden.run_name, num_generations=8) == k8_hidden


def test_wp9c_pilot_pair_is_bounded_k8() -> None:
    public = _load("refresh-pilot-public.yaml")
    hidden = _load("refresh-pilot-hidden.yaml")

    validate_grpo_config_pair(public, hidden)
    assert public.num_generations == hidden.num_generations == 8
    assert public.max_steps == hidden.max_steps == 100


def test_wp9c_keeps_legacy_and_formal_contracts() -> None:
    legacy_public = _load("public.yaml")
    legacy_hidden = _load("hidden.yaml")
    formal_public = _load("refresh-public.yaml")
    formal_hidden = _load("refresh-hidden.yaml")

    validate_grpo_config_pair(legacy_public, legacy_hidden)
    validate_grpo_config_pair(formal_public, formal_hidden)
    assert legacy_public.num_generations == legacy_hidden.num_generations == 4
    assert formal_public.num_generations == formal_hidden.num_generations == 8
    assert formal_public.max_steps == formal_hidden.max_steps == 300
