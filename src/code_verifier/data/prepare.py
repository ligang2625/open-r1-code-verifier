"""All-or-nothing WP1 data preparation and artifact verification."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.adapters import load_raw_jsonl
from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.json_strict import json_values_equal, loads_strict
from code_verifier.data.leakage_checks import (
    TrainingArtifactKind,
    build_training_record,
    check_dataset,
    check_training_artifact,
    load_training_artifact,
)
from code_verifier.data.schema import (
    CodeProblem,
    JsonValue,
    json_value_to_mutable,
    problem_from_mapping,
    problem_to_mapping,
)
from code_verifier.data.split_tests import TestSplitConfig, adapt_raw_problem, validate_test_split_config

HF_DATASET_SCHEMA_VERSION = "wp1-canonical-json-v1"
HF_DATASET_SCHEMA_FIELD = "code_verifier_schema"
SFT_VALIDATION_ARTIFACT_NAME = "sft_validation.jsonl"


class DataPreparationError(RuntimeError):
    """Raised when an all-or-nothing data preparation run cannot complete."""


@dataclass(frozen=True)
class DataPreparationConfig:
    """Validated input, split, and output settings for WP1."""

    input_path: Path
    input_format: Literal["raw_jsonl"]
    test_split: TestSplitConfig
    output_formats: tuple[Literal["jsonl", "hf_dataset"], ...]


@dataclass(frozen=True)
class PreparationSummary:
    """Counts and artifact locations produced or verified by one run."""

    total_problems: int
    split_counts: dict[str, int]
    canonical_jsonl: Path | None
    hf_dataset_dir: Path | None
    training_artifacts: dict[TrainingArtifactKind, Path]
    sft_validation_artifact: Path


def _exact_mapping(value: object, expected: set[str], *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{field} must be a mapping with string keys")
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise ConfigError(f"{field} is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ConfigError(f"{field} contains unknown field(s): {', '.join(sorted(unknown))}")
    return cast(Mapping[str, object], value)


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{field} must be a positive integer")
    return value


def data_config_from_mapping(value: Mapping[str, object], *, config_path: Path) -> DataPreparationConfig:
    """Parse exact input/test_split/output sections and resolve input relative to repository cwd."""
    root = _exact_mapping(value, {"input", "test_split", "output"}, field=str(config_path))
    input_section = _exact_mapping(root["input"], {"path", "format"}, field="input")
    split_section = _exact_mapping(
        root["test_split"],
        {"visible_count", "train_hidden_count", "eval_hidden_count"},
        field="test_split",
    )
    output_section = _exact_mapping(root["output"], {"formats"}, field="output")

    input_value = input_section["path"]
    if not isinstance(input_value, str) or not input_value.strip():
        raise ConfigError("input.path must be a non-empty string")
    input_path = Path(input_value)
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path
    input_format = input_section["format"]
    if input_format != "raw_jsonl":
        raise ConfigError("input.format must be raw_jsonl")

    split_config = TestSplitConfig(
        visible_count=_positive_int(split_section["visible_count"], field="test_split.visible_count"),
        train_hidden_count=_positive_int(
            split_section["train_hidden_count"],
            field="test_split.train_hidden_count",
        ),
        eval_hidden_count=_positive_int(
            split_section["eval_hidden_count"],
            field="test_split.eval_hidden_count",
        ),
    )
    try:
        validate_test_split_config(split_config)
    except ValueError as error:
        raise ConfigError(f"Invalid test_split in {config_path}: {error}") from error

    formats_value = output_section["formats"]
    if not isinstance(formats_value, list) or not formats_value:
        raise ConfigError("output.formats must be a non-empty list")
    formats: list[Literal["jsonl", "hf_dataset"]] = []
    for item in formats_value:
        if item not in {"jsonl", "hf_dataset"}:
            raise ConfigError(f"unsupported output format {item!r}")
        typed_item = cast(Literal["jsonl", "hf_dataset"], item)
        if typed_item in formats:
            raise ConfigError(f"duplicate output format {typed_item}")
        formats.append(typed_item)
    if "jsonl" not in formats:
        raise ConfigError("output.formats must include jsonl")

    return DataPreparationConfig(
        input_path=input_path,
        input_format="raw_jsonl",
        test_split=split_config,
        output_formats=tuple(formats),
    )


def load_data_preparation_config(path: Path) -> DataPreparationConfig:
    """Load YAML and return a validated immutable WP1 data config."""
    return data_config_from_mapping(load_yaml_mapping(path), config_path=path)


def write_jsonl(records: Iterable[Mapping[str, JsonValue]], path: Path) -> int:
    """Atomically write deterministic UTF-8 JSONL and return the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    count = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for record in records:
                validated = json_value_to_mutable(dict(record), field_path=f"{path} record {count + 1}")
                handle.write(
                    json.dumps(
                        validated,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                )
                handle.write("\n")
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return count
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def export_canonical_jsonl(problems: Sequence[CodeProblem], path: Path) -> int:
    """Write complete auditable records with all three test layers."""
    return write_jsonl((problem_to_mapping(problem) for problem in problems), path)


def _problem_to_hf_mapping(problem: CodeProblem) -> dict[str, JsonValue]:
    """Encode arbitrary JSON test values into a versioned Arrow-compatible representation."""
    record = problem_to_mapping(problem)
    record[HF_DATASET_SCHEMA_FIELD] = HF_DATASET_SCHEMA_VERSION
    for layer_name in ("visible_tests", "train_hidden_tests", "eval_hidden_tests"):
        tests = getattr(problem, layer_name)
        record[layer_name] = [
            {
                "input_json": canonical_json(test_case.input),
                "expected_json": canonical_json(test_case.expected),
            }
            for test_case in tests
        ]
    return record


def _hf_test_case_to_mapping(value: object, *, field_path: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping) or set(value) != {"input_json", "expected_json"}:
        raise DataPreparationError(f"{field_path} must contain exactly input_json and expected_json")
    input_json = value["input_json"]
    expected_json = value["expected_json"]
    if not isinstance(input_json, str) or not isinstance(expected_json, str):
        raise DataPreparationError(f"{field_path} JSON fields must be strings")
    try:
        input_value = json_value_to_mutable(json.loads(input_json), field_path=f"{field_path}.input")
        expected_value = json_value_to_mutable(json.loads(expected_json), field_path=f"{field_path}.expected")
    except (json.JSONDecodeError, ValueError) as error:
        raise DataPreparationError(f"{field_path} contains invalid encoded JSON: {error}") from error
    return {"input": input_value, "expected": expected_value}


def _hf_record_to_problem(value: object, *, row_number: int) -> CodeProblem:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise DataPreparationError(f"HF Dataset row {row_number} must be an object with string keys")
    record = dict(value)
    schema_version = record.pop(HF_DATASET_SCHEMA_FIELD, None)
    if schema_version != HF_DATASET_SCHEMA_VERSION:
        raise DataPreparationError(f"HF Dataset row {row_number} uses unsupported schema version {schema_version!r}")
    for layer_name in ("visible_tests", "train_hidden_tests", "eval_hidden_tests"):
        layer = record.get(layer_name)
        if not isinstance(layer, list):
            raise DataPreparationError(f"HF Dataset row {row_number}.{layer_name} must be a list")
        record[layer_name] = [
            _hf_test_case_to_mapping(test_case, field_path=f"HF Dataset row {row_number}.{layer_name}[{index}]")
            for index, test_case in enumerate(layer)
        ]
    try:
        return problem_from_mapping(record)
    except ValueError as error:
        raise DataPreparationError(f"HF Dataset row {row_number} is not a valid canonical problem: {error}") from error


def export_hf_dataset(problems: Sequence[CodeProblem], output_dir: Path) -> int:
    """Save complete records using the versioned WP1 Arrow-compatible encoding."""
    from datasets import Dataset  # type: ignore[import-untyped]

    records = [_problem_to_hf_mapping(problem) for problem in problems]
    dataset = Dataset.from_list(records)
    dataset.save_to_disk(str(output_dir))
    return len(dataset)


def load_hf_dataset(dataset_dir: Path) -> list[CodeProblem]:
    """Load and decode a versioned WP1 Hugging Face Dataset into canonical problems."""
    from datasets import load_from_disk

    try:
        dataset = load_from_disk(str(dataset_dir))
    except Exception as error:
        raise DataPreparationError(f"Could not load HF Dataset {dataset_dir}: {error}") from error
    return [_hf_record_to_problem(record, row_number=index) for index, record in enumerate(dataset, start=1)]


def export_training_artifacts(
    problems: Sequence[CodeProblem],
    output_dir: Path,
) -> dict[TrainingArtifactKind, Path]:
    """Write and revalidate train and independent SFT validation JSONL views."""
    train_problems = [problem for problem in problems if problem.split == "train"]
    validation_problems = [problem for problem in problems if problem.split == "validation"]
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[TrainingArtifactKind, Path] = {}
    for kind in TrainingArtifactKind:
        path = output_dir / f"{kind.value}.jsonl"
        write_jsonl((build_training_record(problem, kind=kind) for problem in train_problems), path)
        check_training_artifact(path, kind=kind)
        result[kind] = path
    validation_path = output_dir / SFT_VALIDATION_ARTIFACT_NAME
    write_jsonl(
        (build_training_record(problem, kind=TrainingArtifactKind.SFT) for problem in validation_problems),
        validation_path,
    )
    check_training_artifact(validation_path, kind=TrainingArtifactKind.SFT)
    return result


def _split_counts(problems: Sequence[CodeProblem]) -> dict[str, int]:
    return {split: sum(problem.split == split for problem in problems) for split in ("train", "validation", "test")}


def prepare_data(
    config: DataPreparationConfig,
    *,
    seed: int,
    output_dir: Path,
) -> PreparationSummary:
    """Adapt, split, check, and atomically publish all requested WP1 artifacts."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DataPreparationError(f"output directory {output_dir} already exists and is not empty")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        raw_problems = load_raw_jsonl(config.input_path)
        problems = [adapt_raw_problem(raw, seed=seed, config=config.test_split) for raw in raw_problems]
        check_dataset(problems)
        export_canonical_jsonl(problems, temporary / "canonical" / "problems.jsonl")
        if "hf_dataset" in config.output_formats:
            export_hf_dataset(problems, temporary / "hf_dataset")
        export_training_artifacts(problems, temporary / "training")
        check_prepared_data(temporary)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(temporary, output_dir)
        return check_prepared_data(output_dir)
    except Exception as error:
        shutil.rmtree(temporary, ignore_errors=True)
        if isinstance(error, DataPreparationError):
            raise
        raise DataPreparationError(f"Data preparation failed: {error}") from error


def _load_canonical(path: Path) -> list[CodeProblem]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise DataPreparationError(f"Could not read canonical JSONL {path}: {error}") from error
    problems: list[CodeProblem] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = loads_strict(line)
            problems.append(problem_from_mapping(value))
        except ValueError as error:
            raise DataPreparationError(f"{path}, line {line_number}: invalid canonical record: {error}") from error
    if not problems:
        raise DataPreparationError(f"canonical JSONL {path} contains no records")
    return problems


def _check_training_artifact_matches_canonical(
    path: Path,
    *,
    kind: TrainingArtifactKind,
    canonical_problems: Sequence[CodeProblem],
    split_name: str,
) -> None:
    """Require one serialized training view to exactly match one canonical split."""
    actual = load_training_artifact(path, kind=kind)
    expected = [build_training_record(problem, kind=kind) for problem in canonical_problems]
    actual_ids: list[str] = []
    for index, record in enumerate(actual, start=1):
        problem_id = record["problem_id"]
        if not isinstance(problem_id, str) or not problem_id.strip():
            raise DataPreparationError(f"{kind.value} artifact row {index} has an invalid problem_id")
        actual_ids.append(problem_id)
    expected_ids = [problem.problem_id for problem in canonical_problems]

    if len(actual_ids) != len(set(actual_ids)):
        raise DataPreparationError(f"{kind.value} artifact contains duplicate problem_id values")
    if set(actual_ids) != set(expected_ids):
        missing = sorted(str(value) for value in set(expected_ids) - set(actual_ids))
        extra = sorted(str(value) for value in set(actual_ids) - set(expected_ids))
        raise DataPreparationError(
            f"{kind.value} artifact problem IDs do not match canonical {split_name} split; "
            f"missing={missing}, extra={extra}"
        )
    if actual_ids != expected_ids:
        raise DataPreparationError(f"{kind.value} artifact row order does not match canonical {split_name} split")
    for actual_record, expected_record, problem_id in zip(actual, expected, expected_ids, strict=True):
        if not json_values_equal(actual_record, expected_record):
            raise DataPreparationError(
                f"{kind.value} artifact record for problem {problem_id} does not match canonical training view"
            )


def check_prepared_data(dataset_dir: Path) -> PreparationSummary:
    """Reload canonical and training artifacts and rerun all WP1 invariants."""
    canonical_path = dataset_dir / "canonical" / "problems.jsonl"
    problems = _load_canonical(canonical_path)
    check_dataset(problems)

    training_dir = dataset_dir / "training"
    training_artifacts: dict[TrainingArtifactKind, Path] = {}
    train_problems = [problem for problem in problems if problem.split == "train"]
    for kind in TrainingArtifactKind:
        path = training_dir / f"{kind.value}.jsonl"
        _check_training_artifact_matches_canonical(
            path,
            kind=kind,
            canonical_problems=train_problems,
            split_name="train",
        )
        training_artifacts[kind] = path
    sft_validation_artifact = training_dir / SFT_VALIDATION_ARTIFACT_NAME
    _check_training_artifact_matches_canonical(
        sft_validation_artifact,
        kind=TrainingArtifactKind.SFT,
        canonical_problems=[problem for problem in problems if problem.split == "validation"],
        split_name="validation",
    )

    hf_dataset_dir = dataset_dir / "hf_dataset"
    hf_path: Path | None = None
    if hf_dataset_dir.exists():
        decoded_problems = load_hf_dataset(hf_dataset_dir)
        if len(decoded_problems) != len(problems):
            raise DataPreparationError(f"HF Dataset has {len(decoded_problems)} rows, expected {len(problems)}")
        for row_number, (decoded, problem) in enumerate(zip(decoded_problems, problems, strict=True), start=1):
            if problem_to_mapping(decoded) != problem_to_mapping(problem):
                raise DataPreparationError(f"HF Dataset row {row_number} does not match canonical JSONL")
        hf_path = hf_dataset_dir

    return PreparationSummary(
        total_problems=len(problems),
        split_counts=_split_counts(problems),
        canonical_jsonl=canonical_path,
        hf_dataset_dir=hf_path,
        training_artifacts=training_artifacts,
        sft_validation_artifact=sft_validation_artifact,
    )
