"""Dataset leakage checks and minimal training artifact views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path

from code_verifier.data.deduplicate import (
    DuplicateDataError,
    ensure_no_problem_overlap_across_splits,
    ensure_unique_problem_ids,
    test_case_hash,
)
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.schema import (
    CodeProblem,
    JsonValue,
    TestCase,
    test_case_to_mapping,
    validate_json_value,
    validate_problem,
)


class LeakageError(ValueError):
    """Raised when test layers, splits, or artifacts violate isolation rules."""


class TrainingArtifactKind(str, Enum):
    """Supported minimal records for later SFT and GRPO consumers."""

    SFT = "sft"
    PUBLIC_GRPO = "public_grpo"
    HIDDEN_GRPO = "hidden_grpo"


_ALLOWED_FIELDS = {
    TrainingArtifactKind.SFT: {"problem_id", "prompt", "sft_response", "metadata"},
    TrainingArtifactKind.PUBLIC_GRPO: {
        "problem_id",
        "prompt",
        "function_name",
        "function_signature",
        "visible_tests",
        "metadata",
    },
    TrainingArtifactKind.HIDDEN_GRPO: {
        "problem_id",
        "prompt",
        "function_name",
        "function_signature",
        "visible_tests",
        "train_hidden_tests",
        "metadata",
    },
}


def check_no_test_layer_overlap(problem: CodeProblem) -> None:
    """Reject normalized test reuse within or across the three layers."""
    seen: dict[str, tuple[str, int]] = {}
    layers = (
        ("visible_tests", problem.visible_tests),
        ("train_hidden_tests", problem.train_hidden_tests),
        ("eval_hidden_tests", problem.eval_hidden_tests),
    )
    for layer_name, tests in layers:
        for index, test_case in enumerate(tests):
            digest = test_case_hash(test_case)
            previous = seen.get(digest)
            if previous is not None:
                previous_layer, previous_index = previous
                raise LeakageError(
                    f"problem {problem.problem_id} repeats a normalized test in "
                    f"{previous_layer}[{previous_index}] and {layer_name}[{index}]"
                )
            seen[digest] = (layer_name, index)


def check_dataset(problems: Sequence[CodeProblem]) -> None:
    """Run schema, ID, cross-split, layer-overlap, and nonempty-split checks."""
    for problem in problems:
        validate_problem(problem)
        check_no_test_layer_overlap(problem)
    try:
        ensure_unique_problem_ids(problems)
        ensure_no_problem_overlap_across_splits(problems)
    except DuplicateDataError as error:
        raise LeakageError(str(error)) from error
    present_splits = {problem.split for problem in problems}
    missing = {"train", "validation", "test"} - present_splits
    if missing:
        raise LeakageError(f"dataset is missing required split(s): {', '.join(sorted(missing))}")


def _test_layer_to_json(tests: Sequence[TestCase]) -> list[JsonValue]:
    result: list[JsonValue] = []
    for test_case in tests:
        result.append(test_case_to_mapping(test_case))
    return result


def _metadata_to_json(problem: CodeProblem) -> dict[str, JsonValue]:
    metadata = problem.metadata
    categories: list[JsonValue] = [category for category in metadata.category]
    return {
        "difficulty": metadata.difficulty,
        "category": categories,
        "time_limit_seconds": metadata.time_limit_seconds,
        "memory_limit_mb": metadata.memory_limit_mb,
        "license": metadata.license,
        "source_url_hash": metadata.source_url_hash,
    }


def build_training_record(
    problem: CodeProblem,
    *,
    kind: TrainingArtifactKind,
) -> dict[str, JsonValue]:
    """Construct a training record from an explicit per-kind field whitelist."""
    record: dict[str, JsonValue] = {}
    record["problem_id"] = problem.problem_id
    record["prompt"] = problem.prompt
    if kind is TrainingArtifactKind.SFT:
        if not isinstance(problem.sft_response, str) or not problem.sft_response.strip():
            raise LeakageError(f"problem {problem.problem_id} has no non-empty sft_response")
        record["sft_response"] = problem.sft_response
        record["metadata"] = _metadata_to_json(problem)
    elif kind is TrainingArtifactKind.PUBLIC_GRPO:
        record["function_name"] = problem.function_name
        record["function_signature"] = problem.function_signature
        record["visible_tests"] = _test_layer_to_json(problem.visible_tests)
        record["metadata"] = _metadata_to_json(problem)
    elif kind is TrainingArtifactKind.HIDDEN_GRPO:
        record["function_name"] = problem.function_name
        record["function_signature"] = problem.function_signature
        record["visible_tests"] = _test_layer_to_json(problem.visible_tests)
        record["train_hidden_tests"] = _test_layer_to_json(problem.train_hidden_tests)
        record["metadata"] = _metadata_to_json(problem)
    else:
        raise LeakageError(f"unsupported training artifact kind {kind!r}")
    check_training_record(record, kind=kind)
    return record


def _contains_eval_hidden_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(key == "eval_hidden_tests" or _contains_eval_hidden_key(nested) for key, nested in value.items())
    if isinstance(value, list):
        return any(_contains_eval_hidden_key(item) for item in value)
    return False


def check_training_record(
    record: Mapping[str, object],
    *,
    kind: TrainingArtifactKind,
) -> None:
    """Reject missing, unknown, or forbidden fields for one training view."""
    allowed = _ALLOWED_FIELDS[kind]
    actual = set(record)
    missing = allowed - actual
    unknown = actual - allowed
    if missing:
        raise LeakageError(f"{kind.value} record is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise LeakageError(
            f"{kind.value} record contains forbidden or unknown field(s): "
            f"{', '.join(sorted(str(key) for key in unknown))}"
        )
    if _contains_eval_hidden_key(record):
        raise LeakageError(f"{kind.value} record contains forbidden eval_hidden_tests key")
    if kind is TrainingArtifactKind.SFT:
        response = record["sft_response"]
        if not isinstance(response, str) or not response.strip():
            raise LeakageError("sft record requires a non-empty sft_response")
    validate_json_value(dict(record), field_path=f"{kind.value} record")


def load_training_artifact(path: Path, *, kind: TrainingArtifactKind) -> list[dict[str, JsonValue]]:
    """Load and validate every record in one training artifact."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise LeakageError(f"Could not read {kind.value} artifact {path}: {error}") from error
    records: list[dict[str, JsonValue]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise LeakageError(f"{path}, line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise LeakageError(f"{path}, line {line_number}: record must be an object")
        try:
            check_training_record(value, kind=kind)
        except LeakageError as error:
            raise LeakageError(f"{path}, line {line_number}: {error}") from error
        records.append(value)
    if not records:
        raise LeakageError(f"training artifact {path} contains no records")
    return records


def check_training_artifact(path: Path, *, kind: TrainingArtifactKind) -> int:
    """Validate every JSONL record in one training artifact and return its row count."""
    return len(load_training_artifact(path, kind=kind))
