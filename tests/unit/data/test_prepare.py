"""Tests for atomic WP1 data preparation and disk verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from code_verifier.config import ConfigError
from code_verifier.data.json_strict import json_values_equal
from code_verifier.data.leakage_checks import LeakageError, TrainingArtifactKind, build_training_record
from code_verifier.data.prepare import (
    HF_DATASET_SCHEMA_FIELD,
    HF_DATASET_SCHEMA_VERSION,
    DataPreparationConfig,
    DataPreparationError,
    check_prepared_data,
    data_config_from_mapping,
    export_hf_dataset,
    load_canonical_jsonl,
    load_hf_dataset,
    prepare_data,
    write_jsonl,
    write_jsonl_with_stats,
)
from code_verifier.data.schema import CodeProblem, JsonValue, problem_from_mapping, problem_to_mapping


def _raw_problem(index: int, split: str) -> dict[str, object]:
    problem_id = f"problem-{index}"
    return {
        "problem_id": problem_id,
        "source": "fixture",
        "split": split,
        "prompt": f"Return {index} plus an integer.",
        "function_name": f"add_{index}",
        "function_signature": f"def add_{index}(value: int) -> int:",
        "starter_code": None,
        "tests": [{"input": [index, value], "expected": index + value} for value in range(6)],
        "reference_solution": f"def add_{index}(value): return {index} + value",
        "sft_response": f"def add_{index}(value): return {index} + value",
        "metadata": {
            "difficulty": "easy",
            "category": ["math"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "MIT",
            "source_url_hash": None,
        },
    }


def _raw_bool_int_problem(
    index: int,
    split: str,
    tests: list[dict[str, object]],
) -> dict[str, object]:
    problem_id = f"bool-problem-{index}"
    return {
        "problem_id": problem_id,
        "source": "fixture",
        "split": split,
        "prompt": f"Return {index} in the requested representation.",
        "function_name": f"boolish_{index}",
        "function_signature": f"def boolish_{index}(value):",
        "starter_code": None,
        "tests": tests,
        "reference_solution": f"def boolish_{index}(value): return value",
        "sft_response": f"def boolish_{index}(value): return value",
        "metadata": {
            "difficulty": "easy",
            "category": ["bool"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "MIT",
            "source_url_hash": None,
        },
    }


def _canonical_problem(index: int, split: str) -> CodeProblem:
    mapping = _raw_problem(index, split)
    tests = cast(list[object], mapping.pop("tests"))
    mapping["visible_tests"] = tests[:2]
    mapping["train_hidden_tests"] = tests[2:4]
    mapping["eval_hidden_tests"] = tests[4:]
    return problem_from_mapping(mapping)


def _write_raw(path: Path, *, invalid_count: bool = False) -> None:
    records = [
        _raw_problem(0, "train"),
        _raw_problem(1, "validation"),
        _raw_problem(2, "test"),
    ]
    if invalid_count:
        cast(list[object], records[0]["tests"]).pop()
    _write_json_records(path, records)


def _write_raw_with_two_train(path: Path) -> None:
    _write_json_records(
        path,
        [
            _raw_problem(0, "train"),
            _raw_problem(1, "train"),
            _raw_problem(2, "validation"),
            _raw_problem(3, "test"),
        ],
    )


def _read_json_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json_records(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")


def _load_canonical_problems(output: Path) -> list[CodeProblem]:
    return [problem_from_mapping(record) for record in _read_json_records(output / "canonical" / "problems.jsonl")]


def _config_mapping(path: Path, *, formats: list[str] | None = None) -> dict[str, object]:
    return {
        "input": {"path": str(path), "format": "raw_jsonl"},
        "test_split": {
            "visible_count": 2,
            "train_hidden_count": 2,
            "eval_hidden_count": 2,
        },
        "output": {"formats": ["jsonl"] if formats is None else formats},
    }


def _config(path: Path, *, formats: list[str] | None = None) -> DataPreparationConfig:
    return data_config_from_mapping(_config_mapping(path, formats=formats), config_path=Path("config.yaml"))


def test_data_config_parses_exact_supported_shape(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    config = _config(raw, formats=["jsonl", "hf_dataset"])
    assert config.input_path == raw
    assert config.test_split.visible_count == 2
    assert config.output_formats == ("jsonl", "hf_dataset")


def test_data_config_rejects_unknown_keys(tmp_path: Path) -> None:
    mapping = _config_mapping(tmp_path / "raw.jsonl")
    cast(dict[str, object], mapping["input"])["extra"] = True
    with pytest.raises(ConfigError, match="unknown"):
        data_config_from_mapping(mapping, config_path=Path("config.yaml"))


def test_data_config_rejects_unsupported_format(tmp_path: Path) -> None:
    mapping = _config_mapping(tmp_path / "raw.jsonl", formats=["jsonl", "csv"])
    with pytest.raises(ConfigError, match="unsupported"):
        data_config_from_mapping(mapping, config_path=Path("config.yaml"))


def test_write_jsonl_is_deterministic_and_round_trippable(tmp_path: Path) -> None:
    records: list[dict[str, JsonValue]] = [{"b": 2, "a": 1}, {"message": "你好"}]
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    third = tmp_path / "third.jsonl"
    trusted = tmp_path / "trusted.jsonl"
    assert write_jsonl(records, first) == 2
    assert write_jsonl(records, second) == 2
    rows, digest = write_jsonl_with_stats(records, third)
    trusted_rows, trusted_digest = write_jsonl_with_stats(records, trusted, validate_records=False)
    assert rows == trusted_rows == 2
    assert first.read_bytes() == second.read_bytes() == third.read_bytes() == trusted.read_bytes()
    assert digest == trusted_digest == hashlib.sha256(third.read_bytes()).hexdigest()
    assert [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()] == records


def test_public_canonical_loader_round_trips_exact_problem(tmp_path: Path) -> None:
    problem = _canonical_problem(0, "train")
    path = tmp_path / "canonical.jsonl"
    write_jsonl([problem_to_mapping(problem)], path)
    assert load_canonical_jsonl(path) == [problem]


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
def test_prepare_data_round_trips_unicode_line_separator_through_canonical_jsonl(
    tmp_path: Path,
    separator: str,
) -> None:
    raw = tmp_path / "raw.jsonl"
    records = [
        _raw_problem(0, "train"),
        _raw_problem(1, "validation"),
        _raw_problem(2, "test"),
    ]
    records[0]["prompt"] = f"before{separator}after"
    raw.write_text(
        "".join(f"{json.dumps(record, ensure_ascii=False)}\n" for record in records),
        encoding="utf-8",
    )

    output = tmp_path / "prepared"
    summary = prepare_data(_config(raw), seed=42, output_dir=output)
    canonical = output / "canonical" / "problems.jsonl"

    assert separator.encode() in canonical.read_bytes()
    assert summary.total_problems == 3
    assert check_prepared_data(output).total_problems == 3


def test_prepare_data_writes_expected_layout(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    summary = prepare_data(_config(raw), seed=42, output_dir=output)
    assert summary.total_problems == 3
    assert summary.split_counts == {"train": 1, "validation": 1, "test": 1}
    assert (output / "canonical" / "problems.jsonl").is_file()
    assert {path.name for path in (output / "training").iterdir()} == {
        "sft.jsonl",
        "sft_validation.jsonl",
        "public_grpo.jsonl",
        "hidden_grpo.jsonl",
    }
    assert summary.sft_validation_artifact == output / "training" / "sft_validation.jsonl"


def test_prepare_data_training_artifacts_exclude_eval_hidden(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)
    for path in (output / "training").iterdir():
        assert b"eval_hidden_tests" not in path.read_bytes()
        assert b"reference_solution" not in path.read_bytes()
    assert b"train_hidden_tests" not in (output / "training" / "public_grpo.jsonl").read_bytes()
    sft_bytes = (output / "training" / "sft.jsonl").read_bytes()
    assert b"train_hidden_tests" not in sft_bytes
    assert b"visible_tests" in sft_bytes
    assert b"Function signature:" in sft_bytes


def test_prepared_sft_artifact_matches_canonical_visible_view(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)

    sft_records = _read_json_records(output / "training" / "sft.jsonl")
    train_problem = next(problem for problem in _load_canonical_problems(output) if problem.split == "train")
    assert sft_records == [build_training_record(train_problem, kind=TrainingArtifactKind.SFT)]

    sft_records[0]["visible_tests"] = problem_to_mapping(train_problem)["train_hidden_tests"]
    _write_json_records(output / "training" / "sft.jsonl", sft_records)
    with pytest.raises(DataPreparationError):
        check_prepared_data(output)


def test_prepared_sft_validation_artifact_matches_only_canonical_validation_split(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)

    canonical = _load_canonical_problems(output)
    validation_problem = next(problem for problem in canonical if problem.split == "validation")
    train_problem = next(problem for problem in canonical if problem.split == "train")
    validation_path = output / "training" / "sft_validation.jsonl"
    assert _read_json_records(validation_path) == [
        build_training_record(validation_problem, kind=TrainingArtifactKind.SFT)
    ]

    _write_json_records(
        validation_path,
        [cast(dict[str, object], build_training_record(train_problem, kind=TrainingArtifactKind.SFT))],
    )
    with pytest.raises(DataPreparationError, match="canonical validation split"):
        check_prepared_data(output)


def test_prepare_data_is_byte_deterministic_for_same_seed(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    first = prepare_data(_config(raw), seed=42, output_dir=tmp_path / "first")
    second = prepare_data(_config(raw), seed=42, output_dir=tmp_path / "second")
    assert first.canonical_jsonl is not None
    assert second.canonical_jsonl is not None
    assert (
        hashlib.sha256(first.canonical_jsonl.read_bytes()).digest()
        == hashlib.sha256(second.canonical_jsonl.read_bytes()).digest()
    )


def test_prepare_data_failure_does_not_publish_partial_output(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw, invalid_count=True)
    output = tmp_path / "prepared"
    with pytest.raises(DataPreparationError):
        prepare_data(_config(raw), seed=42, output_dir=output)
    assert not output.exists()


def test_check_prepared_data_detects_deleted_required_field(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)
    canonical = output / "canonical" / "problems.jsonl"
    records = [json.loads(line) for line in canonical.read_text(encoding="utf-8").splitlines()]
    del records[0]["prompt"]
    canonical.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")
    with pytest.raises(DataPreparationError, match="prompt"):
        check_prepared_data(output)


def test_check_prepared_data_detects_mixed_eval_hidden_field(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)
    artifact = output / "training" / "hidden_grpo.jsonl"
    record = json.loads(artifact.read_text(encoding="utf-8"))
    record["eval_hidden_tests"] = []
    artifact.write_text(f"{json.dumps(record)}\n", encoding="utf-8")
    with pytest.raises(LeakageError, match="eval_hidden_tests"):
        check_prepared_data(output)


@pytest.mark.parametrize(
    "tamper",
    ["eval_as_visible", "non_train_problem", "duplicate_and_omit", "prompt", "visible_test"],
)
def test_check_prepared_data_binds_training_records_to_canonical(tmp_path: Path, tamper: str) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw_with_two_train(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)

    artifact = output / "training" / "public_grpo.jsonl"
    records = _read_json_records(artifact)
    canonical = _load_canonical_problems(output)
    train_problems = [problem for problem in canonical if problem.split == "train"]
    validation_problem = next(problem for problem in canonical if problem.split == "validation")

    if tamper == "eval_as_visible":
        records[0]["visible_tests"] = problem_to_mapping(train_problems[0])["eval_hidden_tests"]
    elif tamper == "non_train_problem":
        records[0] = cast(
            dict[str, object],
            build_training_record(validation_problem, kind=TrainingArtifactKind.PUBLIC_GRPO),
        )
    elif tamper == "duplicate_and_omit":
        records[1] = dict(records[0])
    elif tamper == "prompt":
        records[0]["prompt"] = "tampered prompt"
    else:
        visible_tests = cast(list[dict[str, object]], records[0]["visible_tests"])
        visible_tests[0]["expected"] = "tampered expected"
    _write_json_records(artifact, records)

    with pytest.raises(DataPreparationError):
        check_prepared_data(output)


def test_check_prepared_data_rejects_duplicate_key_hiding_eval_content(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)
    artifact = output / "training" / "public_grpo.jsonl"
    lines = artifact.read_text(encoding="utf-8").splitlines()
    canonical_problems = _load_canonical_problems(output)
    train_problem = next(problem for problem in canonical_problems if problem.split == "train")
    eval_layer = json.dumps(problem_to_mapping(train_problem)["eval_hidden_tests"])
    marker = '"visible_tests":'
    index = lines[0].index(marker)
    lines[0] = lines[0][:index] + marker + eval_layer + "," + lines[0][index:]
    artifact.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    with pytest.raises(LeakageError, match="duplicate JSON key"):
        check_prepared_data(output)


def test_check_prepared_data_rejects_bool_int_test_type_drift(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_json_records(
        raw,
        [
            _raw_bool_int_problem(
                3,
                "train",
                [
                    {"input": True, "expected": True},
                    {"input": 0, "expected": 0},
                    {"input": [3], "expected": [3]},
                    {"input": [4], "expected": [4]},
                    {"input": 1, "expected": 1},
                    {"input": False, "expected": False},
                ],
            ),
            _raw_bool_int_problem(
                4,
                "validation",
                [{"input": [f"v{value}"], "expected": [f"v{value}"]} for value in range(6)],
            ),
            _raw_bool_int_problem(
                5,
                "test",
                [{"input": [f"t{value}"], "expected": [f"t{value}"]} for value in range(6)],
            ),
        ],
    )
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)
    artifact = output / "training" / "public_grpo.jsonl"
    records = _read_json_records(artifact)
    records[0]["visible_tests"] = [
        {"input": 1, "expected": 1},
        {"input": 0, "expected": 0},
    ]
    _write_json_records(artifact, records)

    with pytest.raises(DataPreparationError):
        check_prepared_data(output)


def test_check_prepared_data_rejects_json_number_type_drift(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    output = tmp_path / "prepared"
    prepare_data(_config(raw), seed=42, output_dir=output)
    artifact = output / "training" / "public_grpo.jsonl"
    records = _read_json_records(artifact)
    metadata = cast(dict[str, object], records[0]["metadata"])
    metadata["memory_limit_mb"] = 128.0
    _write_json_records(artifact, records)

    with pytest.raises(DataPreparationError):
        check_prepared_data(output)


@pytest.mark.parametrize(
    ("left", "right", "equal"),
    [
        (True, 1, False),
        (False, 0, False),
        (1, 1.0, False),
        (128, 128.0, False),
        (None, None, True),
        ({"a": True}, {"a": 1}, False),
        ({"a": [1, 2]}, {"a": [1, 2]}, True),
        ([{"input": True}], [{"input": True}], True),
    ],
)
def test_json_values_equal_is_type_sensitive(left: object, right: object, equal: bool) -> None:
    assert json_values_equal(left, right) is equal


def test_export_hf_dataset_round_trips_records(tmp_path: Path) -> None:
    from datasets import load_from_disk  # type: ignore[import-untyped]

    problems = [_canonical_problem(index, split) for index, split in enumerate(("train", "validation", "test"))]
    output = tmp_path / "hf_dataset"
    assert export_hf_dataset(problems, output) == 3
    raw_dataset = load_from_disk(str(output))
    assert len(raw_dataset) == 3
    assert set(raw_dataset[HF_DATASET_SCHEMA_FIELD]) == {HF_DATASET_SCHEMA_VERSION}
    assert [problem_to_mapping(problem) for problem in load_hf_dataset(output)] == [
        problem_to_mapping(problem) for problem in problems
    ]


@pytest.mark.parametrize("kind", list(TrainingArtifactKind))
def test_summary_contains_each_training_kind(tmp_path: Path, kind: TrainingArtifactKind) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_raw(raw)
    summary = prepare_data(_config(raw), seed=42, output_dir=tmp_path / f"prepared-{kind.value}")
    assert summary.training_artifacts[kind].is_file()
