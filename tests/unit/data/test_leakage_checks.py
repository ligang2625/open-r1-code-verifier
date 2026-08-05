"""Tests for dataset isolation and training record whitelists."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from code_verifier.data.leakage_checks import (
    LeakageError,
    TrainingArtifactKind,
    build_training_record,
    check_dataset,
    check_no_test_layer_overlap,
    check_training_record,
    load_training_artifact,
)
from code_verifier.data.schema import CodeProblem, JsonValue, problem_from_mapping
from code_verifier.data.schema import TestCase as CodeTestCase


def _problem(*, problem_id: str, split: str, prompt: str, sft_response: str | None = "solution") -> CodeProblem:
    return problem_from_mapping(
        {
            "problem_id": problem_id,
            "source": "fixture",
            "split": split,
            "prompt": prompt,
            "function_name": f"fn_{problem_id}",
            "function_signature": f"def fn_{problem_id}(value):",
            "starter_code": None,
            "visible_tests": [{"input": [problem_id, 0], "expected": 0}],
            "train_hidden_tests": [{"input": [problem_id, 1], "expected": 1}],
            "eval_hidden_tests": [{"input": [problem_id, 2], "expected": 2}],
            "reference_solution": f"def fn_{problem_id}(value): return value",
            "sft_response": sft_response,
            "metadata": {
                "difficulty": "easy",
                "category": ["fixture"],
                "time_limit_seconds": 1.0,
                "memory_limit_mb": 128,
                "license": "MIT",
                "source_url_hash": None,
            },
        }
    )


def _dataset() -> list[CodeProblem]:
    return [
        _problem(problem_id="train", split="train", prompt="Train task"),
        _problem(problem_id="validation", split="validation", prompt="Validation task"),
        _problem(problem_id="test", split="test", prompt="Test task"),
    ]


def test_layer_overlap_rejects_same_case_within_layer() -> None:
    problem = _dataset()[0]
    duplicate_layer = (problem.visible_tests[0], problem.visible_tests[0])
    with pytest.raises(LeakageError, match="visible_tests"):
        check_no_test_layer_overlap(replace(problem, visible_tests=duplicate_layer))


def test_layer_overlap_rejects_same_case_across_layers() -> None:
    problem = _dataset()[0]
    with pytest.raises(LeakageError, match="visible_tests.*eval_hidden_tests"):
        check_no_test_layer_overlap(replace(problem, eval_hidden_tests=problem.visible_tests))


def test_check_dataset_rejects_duplicate_problem_id() -> None:
    dataset = _dataset()
    dataset[1] = replace(dataset[1], problem_id="train")
    with pytest.raises(LeakageError, match="duplicate problem_id"):
        check_dataset(dataset)


def test_check_dataset_rejects_cross_split_problem_content() -> None:
    dataset = _dataset()
    dataset[1] = replace(dataset[0], problem_id="other", split="validation", source="other")
    with pytest.raises(LeakageError, match="overlaps across splits"):
        check_dataset(dataset)


def test_check_dataset_requires_all_three_splits() -> None:
    with pytest.raises(LeakageError, match="test"):
        check_dataset(_dataset()[:2])


def test_sft_record_contains_no_test_fields() -> None:
    record = build_training_record(_dataset()[0], kind=TrainingArtifactKind.SFT)
    assert set(record) == {"problem_id", "prompt", "sft_response", "metadata"}


def test_public_record_contains_visible_tests_only() -> None:
    record = build_training_record(_dataset()[0], kind=TrainingArtifactKind.PUBLIC_GRPO)
    assert "visible_tests" in record
    assert "train_hidden_tests" not in record
    assert "eval_hidden_tests" not in record


def test_hidden_record_contains_no_eval_hidden_tests() -> None:
    record = build_training_record(_dataset()[0], kind=TrainingArtifactKind.HIDDEN_GRPO)
    assert "train_hidden_tests" in record
    assert "eval_hidden_tests" not in record


@pytest.mark.parametrize("kind", list(TrainingArtifactKind))
def test_training_record_rejects_deleted_required_field(kind: TrainingArtifactKind) -> None:
    record = build_training_record(_dataset()[0], kind=kind)
    del record[next(iter(record))]
    with pytest.raises(LeakageError, match="missing"):
        check_training_record(record, kind=kind)


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        (TrainingArtifactKind.SFT, "visible_tests"),
        (TrainingArtifactKind.PUBLIC_GRPO, "train_hidden_tests"),
        (TrainingArtifactKind.HIDDEN_GRPO, "eval_hidden_tests"),
    ],
)
def test_training_record_rejects_mixed_forbidden_field(kind: TrainingArtifactKind, field: str) -> None:
    record = build_training_record(_dataset()[0], kind=kind)
    record[field] = []
    with pytest.raises(LeakageError):
        check_training_record(record, kind=kind)


def test_training_record_rejects_nested_eval_hidden_key() -> None:
    record = build_training_record(_dataset()[0], kind=TrainingArtifactKind.SFT)
    metadata = cast(dict[str, JsonValue], record["metadata"])
    metadata["nested"] = {"eval_hidden_tests": []}
    with pytest.raises(LeakageError, match="eval_hidden_tests"):
        check_training_record(record, kind=TrainingArtifactKind.SFT)


def test_sft_record_requires_response() -> None:
    problem = _problem(problem_id="train", split="train", prompt="Train", sft_response=None)
    with pytest.raises(LeakageError, match="sft_response"):
        build_training_record(problem, kind=TrainingArtifactKind.SFT)


def test_overlap_hashes_normalized_test_values() -> None:
    problem = _dataset()[0]
    normalized_duplicate = CodeTestCase(input=["same  value"], expected=1)
    whitespace_variant = CodeTestCase(input=["same value"], expected=1)
    with pytest.raises(LeakageError):
        check_no_test_layer_overlap(
            replace(
                problem,
                visible_tests=(normalized_duplicate,),
                eval_hidden_tests=(whitespace_variant,),
            )
        )


def test_load_training_artifact_rejects_duplicate_json_key(tmp_path: Path) -> None:
    path = tmp_path / "public_grpo.jsonl"
    path.write_text('{"problem_id":"p1","problem_id":"p2"}\n', encoding="utf-8")
    with pytest.raises(LeakageError, match="duplicate JSON key"):
        load_training_artifact(path, kind=TrainingArtifactKind.PUBLIC_GRPO)


def test_load_training_artifact_rejects_nested_duplicate_json_key(tmp_path: Path) -> None:
    path = tmp_path / "public_grpo.jsonl"
    path.write_text('{"visible_tests":[{"input":1,"input":2,"expected":3}]}\n', encoding="utf-8")
    with pytest.raises(LeakageError, match="duplicate JSON key"):
        load_training_artifact(path, kind=TrainingArtifactKind.PUBLIC_GRPO)


def test_load_training_artifact_duplicate_key_cannot_hide_eval_content(tmp_path: Path) -> None:
    path = tmp_path / "public_grpo.jsonl"
    path.write_text(
        '{"visible_tests":[{"input":"HIDDEN_MARKER","expected":0}],"visible_tests":[{"input":1,"expected":2}]}\n',
        encoding="utf-8",
    )
    with pytest.raises(LeakageError) as excinfo:
        load_training_artifact(path, kind=TrainingArtifactKind.PUBLIC_GRPO)
    assert "duplicate JSON key" in str(excinfo.value)
    assert "HIDDEN_MARKER" not in str(excinfo.value)
