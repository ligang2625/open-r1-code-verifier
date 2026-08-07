"""Tests for strict WP5 evaluation configuration and records."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from code_verifier.evaluation.evaluate import (
    EvaluationError,
    EvaluationRecord,
    evaluation_config_from_mapping,
    evaluation_record_from_mapping,
    evaluation_record_to_mapping,
    load_evaluation_config,
)


def _config_mapping() -> dict[str, object]:
    return {
        "dataset_dir": "data/processed/wp1-smoke",
        "split": "test",
        "piston_config": "configs/execution/piston-local.yaml",
        "model_revision": None,
        "checkpoint": "base",
        "device": "auto",
        "generation": {
            "do_sample": False,
            "temperature": None,
            "top_p": None,
            "max_new_tokens": 512,
        },
    }


def _record() -> EvaluationRecord:
    return EvaluationRecord(
        run_id="run-1",
        model_id="model-1",
        checkpoint="base",
        dataset_hash="d" * 64,
        config_hash="c" * 64,
        problem_id="problem-1",
        prompt_hash="p" * 64,
        completion="```python\ndef solve(x):\n    return x\n```",
        extracted_code="def solve(x):\n    return x\n",
        parse_success=True,
        target_function_found=True,
        visible_pass_rate=1.0,
        train_hidden_pass_rate=0.5,
        eval_hidden_pass_rate=0.0,
        execution_status="wrong_answer",
        visible_execution_status="passed",
        train_hidden_execution_status="wrong_answer",
        eval_hidden_execution_status="wrong_answer",
        visible_failure_counts={},
        train_hidden_failure_counts={"wrong_answer": 1},
        eval_hidden_failure_counts={"wrong_answer": 2},
        parse_error_type=None,
        runtime_ms=3.5,
        generation_latency_ms=10.0,
        completion_tokens=12,
        error_category_auto="visible_only_success",
    )


def test_load_evaluation_config_accepts_pass1_yaml() -> None:
    config = load_evaluation_config(Path("configs/eval/pass1.yaml"))
    assert config.split == "test"
    assert config.generation.max_new_tokens == 512
    assert config.dataset_dir == Path.cwd() / "data/processed/wp1-smoke"


@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_evaluation_config_rejects_unknown_or_missing_keys(mutation: str) -> None:
    mapping = _config_mapping()
    if mutation == "unknown":
        mapping["extra"] = True
    else:
        del mapping["checkpoint"]
    with pytest.raises(EvaluationError):
        evaluation_config_from_mapping(mapping)


def test_evaluation_config_rejects_training_split() -> None:
    mapping = _config_mapping()
    mapping["split"] = "train"
    with pytest.raises(EvaluationError, match="validation or test"):
        evaluation_config_from_mapping(mapping)


def test_evaluation_record_round_trip_is_exact_and_json_safe() -> None:
    record = _record()
    mapping = evaluation_record_to_mapping(record)
    assert evaluation_record_from_mapping(mapping) == record
    json.dumps(mapping, allow_nan=False)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("visible_pass_rate", math.nan),
        ("train_hidden_pass_rate", math.inf),
        ("eval_hidden_pass_rate", 1.1),
        ("runtime_ms", -1.0),
        ("generation_latency_ms", math.inf),
    ],
)
def test_evaluation_record_rejects_nan_inf_and_out_of_range_rates(field: str, value: float) -> None:
    mapping = evaluation_record_to_mapping(_record())
    mapping[field] = value
    with pytest.raises(EvaluationError):
        evaluation_record_from_mapping(mapping)


def test_evaluation_record_rejects_unknown_status_or_failure_count() -> None:
    mapping = evaluation_record_to_mapping(_record())
    mapping["execution_status"] = "mystery"
    with pytest.raises(EvaluationError):
        evaluation_record_from_mapping(mapping)

    mapping = evaluation_record_to_mapping(_record())
    mapping["eval_hidden_failure_counts"] = {"passed": 1}
    with pytest.raises(EvaluationError):
        evaluation_record_from_mapping(mapping)


def test_evaluation_record_mapping_contains_no_test_payload_keys() -> None:
    mapping = evaluation_record_to_mapping(replace(_record(), completion="VISIBLE_COMPLETION_SENTINEL"))
    forbidden = {"tests", "expected", "metadata", "reference_solution", "stdout", "stderr"}
    assert forbidden.isdisjoint(mapping)
