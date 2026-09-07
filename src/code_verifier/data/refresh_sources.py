"""Pinned-source ingestion and stdio canonicalization for the WP9-a refresh pool."""

from __future__ import annotations

import ast
import hashlib
import json
import keyword
import re
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Literal, cast

from code_verifier.data.deduplicate import (
    DuplicateDataError,
    canonical_json,
    normalize_text,
    stable_json_hash,
    test_case_hash,
)
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.schema import (
    CodeProblem,
    FrozenJsonValue,
    ProblemMetadata,
    TestCase,
    validate_json_value,
    validate_problem,
)
from code_verifier.data.split_tests import _split_refresh_test_cases_prevalidated, split_refresh_test_cases

Difficulty = Literal["easy", "medium", "hard", "unknown"]
ReferenceClass = Literal["sft", "validation", "project_test", "external_eval"]


class RefreshSourceError(RuntimeError):
    """Raised when a pinned refresh source cannot be validated or mapped safely."""


@dataclass(frozen=True)
class RefreshSourceSpec:
    """Immutable identity and adapter contract for one refresh source projection."""

    source_name: str
    dataset_id: str
    revision: str
    config_name: str | None
    split: str
    declared_license: str
    adapter: Literal["deepcoder"]


@dataclass(frozen=True)
class RefreshSourceSnapshot:
    """Machine-readable summary of the exact source projection consumed by a run."""

    source_name: str
    dataset_id: str
    revision: str
    config_name: str | None
    split: str
    declared_license: str
    scanned_rows: int
    accepted_rows: int
    projection_fingerprint_sha256: str


@dataclass(frozen=True)
class RefreshCandidate:
    """Validated fixed-output candidate before canonical test-layer assignment."""

    candidate_id: str
    source_name: str
    source_record_id: str
    prompt: str
    function_name: str
    function_signature: str
    tests: tuple[TestCase, ...]
    source_url_hash: str | None
    raw_reference_solution_hash: str | None
    difficulty: Difficulty
    category: tuple[str, ...]
    raw_record_sha256: str
    test_fingerprint: str | None = None
    test_validation_guard: str | None = None


@dataclass(frozen=True)
class OverlapReference:
    """Minimal non-training representation used only for refresh overlap exclusion."""

    reference_id: str
    reference_class: ReferenceClass
    prompt: str
    function_signature: str | None
    source_url_hash: str | None
    reference_solution_hash: str | None
    test_fingerprint: str | None


def _require_nonempty(value: str, *, field: str) -> str:
    if not value.strip():
        raise RefreshSourceError(f"{field} must be non-empty")
    return value.strip()


def _license_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _snapshot_cache_dir(cache_dir: Path | None) -> str | None:
    if cache_dir is None:
        return None
    hub_dir = cache_dir / "hub"
    return str(hub_dir if hub_dir.is_dir() else cache_dir)


def _resolve_snapshot(dataset_id: str, revision: str, *, cache_dir: Path | None) -> Path:
    """Resolve an exact dataset snapshot; HF offline mode is honored by huggingface_hub."""
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision.casefold()):
        raise RefreshSourceError("source revision must be a full 40-character hexadecimal commit SHA")
    try:
        from huggingface_hub import snapshot_download

        snapshot = Path(
            snapshot_download(
                repo_id=dataset_id,
                repo_type="dataset",
                revision=revision,
                cache_dir=_snapshot_cache_dir(cache_dir),
            )
        ).resolve()
    except Exception as error:
        raise RefreshSourceError(f"could not resolve pinned dataset {dataset_id}@{revision}: {error}") from error
    if snapshot.name != revision:
        raise RefreshSourceError(
            f"resolved snapshot identity mismatch for {dataset_id}: expected {revision}, got {snapshot.name}"
        )
    return snapshot


def _snapshot_license(snapshot: Path) -> str:
    readme = snapshot / "README.md"
    try:
        text = readme.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RefreshSourceError(f"could not read dataset card {readme}: {error}") from error
    if not text.startswith("---"):
        raise RefreshSourceError(f"dataset card {readme} has no YAML front matter")
    pieces = text.split("---", 2)
    if len(pieces) != 3:
        raise RefreshSourceError(f"dataset card {readme} has malformed YAML front matter")
    try:
        import yaml

        card = yaml.safe_load(pieces[1])
    except Exception as error:
        raise RefreshSourceError(f"dataset card {readme} has invalid YAML front matter: {error}") from error
    if not isinstance(card, Mapping):
        raise RefreshSourceError(f"dataset card {readme} front matter must be a mapping")
    license_value = card.get("license")
    if not isinstance(license_value, str) or not license_value.strip():
        raise RefreshSourceError(f"dataset card {readme} must declare a non-empty license")
    return license_value.strip()


def _validate_license(snapshot: Path, declared_license: str) -> None:
    actual = _snapshot_license(snapshot)
    expected = _require_nonempty(declared_license, field="declared_license")
    if _license_key(actual) != _license_key(expected):
        raise RefreshSourceError(f"dataset-card license {actual!r} does not match declared license {expected!r}")


def _iter_lcbv5_parquet_rows(
    snapshot: Path,
    split: str,
    *,
    shard_index: int | None = None,
) -> Iterable[tuple[int, Mapping[str, object]]]:
    config_dir = snapshot / "lcbv5"
    files = sorted(config_dir.glob(f"{split}-*.parquet"))
    if not files:
        raise RefreshSourceError(f"pinned snapshot has no parquet files for lcbv5/{split}")
    if shard_index is not None and not 0 <= shard_index < len(files):
        raise RefreshSourceError(f"lcbv5 shard index must be in [0, {len(files) - 1}]")
    expected = {"problem", "starter_code", "tests", "metadata"}
    try:
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        offsets: list[int] = []
        running = 0
        for path in files:
            offsets.append(running)
            running += pq.ParquetFile(path).metadata.num_rows
        selected = range(len(files)) if shard_index is None else (shard_index,)
        for file_index in selected:
            path = files[file_index]
            parquet_file = pq.ParquetFile(path)
            column_names = parquet_file.schema_arrow.names
            if set(column_names) != expected:
                raise RefreshSourceError(
                    f"DeepCoder lcbv5 schema drift in {path.name}: expected {sorted(expected)}, got {column_names}"
                )
            local_index = 0
            for batch in parquet_file.iter_batches(batch_size=128, columns=column_names):
                for row in batch.to_pylist():
                    if not isinstance(row, Mapping):
                        raise RefreshSourceError(f"DeepCoder row in {path.name} is not a mapping")
                    yield offsets[file_index] + local_index, cast(Mapping[str, object], row)
                    local_index += 1
    except RefreshSourceError:
        raise
    except Exception as error:
        raise RefreshSourceError(f"could not read DeepCoder parquet projection lcbv5/{split}: {error}") from error


def _iter_parquet_rows(snapshot: Path, config_name: str, split: str) -> Iterable[Mapping[str, object]]:
    config_dir = snapshot / config_name
    files = sorted(config_dir.glob(f"{split}-*.parquet"))
    if not files:
        raise RefreshSourceError(f"pinned snapshot has no parquet files for {config_name}/{split}")
    try:
        import pyarrow.parquet as pq

        for path in files:
            parquet_file = pq.ParquetFile(path)
            column_names = parquet_file.schema_arrow.names
            if set(column_names) != {"problem", "solutions", "tests"}:
                raise RefreshSourceError(
                    f"DeepCoder schema drift in {path.name}: expected problem/solutions/tests, got {column_names}"
                )
            for batch in parquet_file.iter_batches(
                batch_size=128,
                columns=["problem", "solutions", "tests"],
            ):
                for row in batch.to_pylist():
                    if not isinstance(row, Mapping):
                        raise RefreshSourceError(f"DeepCoder row in {path.name} is not a mapping")
                    yield cast(Mapping[str, object], row)
    except RefreshSourceError:
        raise
    except Exception as error:
        message = f"could not read DeepCoder parquet projection {config_name}/{split}: {error}"
        raise RefreshSourceError(message) from error


def _strict_tests_json(text: object, *, record_id: str) -> object:
    if not isinstance(text, str):
        raise RefreshSourceError(f"{record_id}: tests must be a JSON string")
    try:
        return loads_strict(text)
    except StrictJsonError as error:
        raise ValueError(f"{record_id}: malformed tests JSON: {error}") from error


def _primeintellect_tests(value: object, *, record_id: str) -> tuple[TestCase, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{record_id}: primeintellect tests must be a list")
    tests: list[TestCase] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"type", "input", "output"}:
            raise ValueError(f"{record_id}: unsupported primeintellect test schema at index {index}")
        if item["type"] != "stdin_stdout":
            raise ValueError(f"{record_id}: only stdin_stdout tests are supported")
        input_text = item["input"]
        output_text = item["output"]
        if not isinstance(input_text, str) or not isinstance(output_text, str):
            raise ValueError(f"{record_id}: stdin/stdout test values must be strings")
        tests.append(TestCase(input=input_text, expected=output_text))
    return tuple(tests)


def _taco_tests(value: object, *, record_id: str) -> tuple[TestCase, ...]:
    if not isinstance(value, dict):
        raise ValueError(f"{record_id}: taco tests must be an object")
    if "fn_name" in value:
        raise ValueError(f"{record_id}: function-call TACO tests are outside the WP9-a stdio adapter")
    if set(value) != {"inputs", "outputs"}:
        raise ValueError(f"{record_id}: unsupported taco test schema")
    inputs = value["inputs"]
    outputs = value["outputs"]
    if not isinstance(inputs, list) or not isinstance(outputs, list) or len(inputs) != len(outputs):
        raise ValueError(f"{record_id}: taco inputs/outputs must be equal-length lists")
    if any(not isinstance(item, str) for item in inputs) or any(not isinstance(item, str) for item in outputs):
        raise ValueError(f"{record_id}: only string stdin/stdout TACO tests are supported")
    return tuple(
        TestCase(input=input_text, expected=output_text)
        for input_text, output_text in zip(inputs, outputs, strict=True)
    )


def _json_object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = item
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


def _decode_concatenated_json_values(value: object, *, record_id: str, field: str) -> tuple[object, ...]:
    if not isinstance(value, str):
        raise ValueError(f"{record_id}: {field} must be a JSON text string")
    decoder = json.JSONDecoder(
        object_pairs_hook=_json_object_without_duplicate_keys,
        parse_constant=_reject_json_constant,
    )
    values: list[object] = []
    index = 0
    while index < len(value):
        while index < len(value) and value[index].isspace():
            index += 1
        if index == len(value):
            break
        try:
            decoded, next_index = decoder.raw_decode(value, index)
        except (json.JSONDecodeError, ValueError, RecursionError) as error:
            raise ValueError(f"{record_id}: {field} contains invalid JSON values") from error
        values.append(decoded)
        index = next_index
    if not values:
        raise ValueError(f"{record_id}: {field} contains no JSON values")
    return tuple(values)


def _function_call_expected(value: object, *, record_id: str) -> FrozenJsonValue:
    """Unwrap and validate the DeepCoder function-call output envelope without guessing lists."""
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError(f"{record_id}: function-call output envelope must contain exactly one value")
        value = value[0]
    return validate_json_value(value, field_path=f"{record_id}.expected")


def _primeintellect_function_call_tests(
    value: object,
    *,
    record_id: str,
) -> tuple[str, tuple[TestCase, ...]] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, dict) and item.get("type") == "function_call" for item in value):
        return None
    if any(set(item) != {"type", "fn_name", "input", "output"} for item in value):
        raise ValueError(f"{record_id}: unsupported primeintellect function-call test schema")
    function_names = {item["fn_name"] for item in value}
    if len(function_names) != 1:
        raise ValueError(f"{record_id}: function-call tests must use one function name")
    function_name = next(iter(function_names))
    if not isinstance(function_name, str) or not function_name.isidentifier() or keyword.iskeyword(function_name):
        raise ValueError(f"{record_id}: function-call function name is invalid")
    tests: list[TestCase] = []
    for item in value:
        input_value = item["input"]
        if not isinstance(input_value, list):
            raise ValueError(f"{record_id}: function-call input must be a positional-argument list")
        tests.append(
            TestCase(
                input=validate_json_value(input_value, field_path=f"{record_id}.input"),
                expected=_function_call_expected(item["output"], record_id=record_id),
            )
        )
    return function_name, tuple(tests)


def _taco_function_call_tests(
    value: object,
    *,
    record_id: str,
) -> tuple[str, tuple[TestCase, ...]] | None:
    if not isinstance(value, dict) or "fn_name" not in value:
        return None
    if set(value) != {"fn_name", "inputs", "outputs"}:
        raise ValueError(f"{record_id}: unsupported TACO function-call test schema")
    function_name = value["fn_name"]
    inputs = value["inputs"]
    outputs = value["outputs"]
    if not isinstance(function_name, str) or not function_name.isidentifier() or keyword.iskeyword(function_name):
        raise ValueError(f"{record_id}: function-call function name is invalid")
    if not isinstance(inputs, list) or not isinstance(outputs, list) or len(inputs) != len(outputs):
        raise ValueError(f"{record_id}: function-call inputs/outputs must be equal-length lists")
    if any(not isinstance(item, list) for item in inputs):
        raise ValueError(f"{record_id}: function-call input must be a positional-argument list")
    tests = tuple(
        TestCase(
            input=validate_json_value(input_value, field_path=f"{record_id}.input"),
            expected=_function_call_expected(output_value, record_id=record_id),
        )
        for input_value, output_value in zip(inputs, outputs, strict=True)
    )
    return function_name, tests


def _signature_supports_arities(signature: str, arities: set[int]) -> bool:
    try:
        parsed = ast.parse(f"{signature}\n    pass\n")
    except SyntaxError:
        return False
    if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.FunctionDef):
        return False
    arguments = parsed.body[0].args
    if any(default is None for default in arguments.kw_defaults):
        return False
    positional_count = len(arguments.posonlyargs) + len(arguments.args)
    required_count = positional_count - len(arguments.defaults)
    maximum_count = None if arguments.vararg is not None else positional_count
    return all(arity >= required_count and (maximum_count is None or arity <= maximum_count) for arity in arities)


def _function_signature_from_row(
    row: Mapping[str, object],
    *,
    function_name: str,
    arities: set[int],
) -> str | None:
    escaped = re.escape(function_name)
    pattern = re.compile(rf"(?m)^[ \t]*def[ \t]+{escaped}[ \t]*\([^\n]*\)[ \t]*(?:->[ \t]*[^:\n]+)?[ \t]*:")
    problem = row.get("problem")
    solutions = row.get("solutions")
    if (
        not isinstance(problem, str)
        or not isinstance(solutions, list)
        or any(not isinstance(item, str) for item in solutions)
    ):
        return None
    seen: set[str] = set()
    for text in (problem, *solutions):
        for match in pattern.finditer(text):
            signature = match.group(0).strip()
            if signature in seen:
                continue
            seen.add(signature)
            if _signature_supports_arities(signature, arities):
                return signature
    return None


def _framed_text(value: str) -> bytes:
    data = value.encode("utf-8")
    return len(data).to_bytes(8, byteorder="big") + data


def refresh_test_set_fingerprint(test_cases: Sequence[TestCase], *, context: str) -> str:
    """Hash a normalized test set once while rejecting normalized duplicates."""
    keys: list[tuple[str, str, str]] = []
    first_index: dict[tuple[str, str, str], int] = {}
    for index, test_case in enumerate(test_cases):
        if isinstance(test_case.input, str) and isinstance(test_case.expected, str):
            key = ("stdio", normalize_text(test_case.input), normalize_text(test_case.expected))
        else:
            key = ("generic", test_case_hash(test_case), "")
        previous = first_index.get(key)
        if previous is not None:
            raise DuplicateDataError(
                f"{context} contains duplicate normalized tests at indexes {previous} and {index}"
            )
        first_index[key] = index
        keys.append(key)

    digest = hashlib.sha256()
    for key in sorted(keys):
        for part in key:
            digest.update(_framed_text(part))
    return digest.hexdigest()


def refresh_problem_test_set_fingerprint(problem: CodeProblem) -> str:
    """Hash all canonical problem tests with the WP9-a refresh fingerprint protocol."""
    tests = (*problem.visible_tests, *problem.train_hidden_tests, *problem.eval_hidden_tests)
    return refresh_test_set_fingerprint(tests, context=f"problem {problem.problem_id}")


def _stdio_test_payload_sha256(test_cases: Sequence[TestCase]) -> str:
    """Hash exact ordered stdio test payloads for cheap frozen-candidate integrity checks."""
    digest = hashlib.sha256()
    for test_case in test_cases:
        if not isinstance(test_case.input, str) or not isinstance(test_case.expected, str):
            raise ValueError("prevalidated refresh test payloads must remain string stdio pairs")
        digest.update(_framed_text(test_case.input))
        digest.update(_framed_text(test_case.expected))
    return digest.hexdigest()


def _refresh_stdio_test_fingerprints(test_cases: Sequence[TestCase], *, context: str) -> tuple[str, str]:
    """Compute normalized set fingerprint and exact payload SHA in one stdio-only pass."""
    keys: list[tuple[str, str, str]] = []
    first_index: dict[tuple[str, str, str], int] = {}
    payload_digest = hashlib.sha256()
    for index, test_case in enumerate(test_cases):
        if not isinstance(test_case.input, str) or not isinstance(test_case.expected, str):
            raise ValueError("refresh source tests must remain string stdio pairs")
        key = ("stdio", normalize_text(test_case.input), normalize_text(test_case.expected))
        previous = first_index.get(key)
        if previous is not None:
            raise DuplicateDataError(
                f"{context} contains duplicate normalized tests at indexes {previous} and {index}"
            )
        first_index[key] = index
        keys.append(key)
        payload_digest.update(_framed_text(test_case.input))
        payload_digest.update(_framed_text(test_case.expected))

    normalized_digest = hashlib.sha256()
    for key in sorted(keys):
        for part in key:
            normalized_digest.update(_framed_text(part))
    return normalized_digest.hexdigest(), payload_digest.hexdigest()


def _test_validation_guard(test_fingerprint: str, payload_sha256: str) -> str:
    return stable_json_hash(
        {
            "protocol": "wp9a-prevalidated-tests-v1",
            "test_fingerprint": test_fingerprint,
            "payload_sha256": payload_sha256,
        }
    )


def _raw_reference_solution_hash(value: object, *, record_id: str) -> str | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RefreshSourceError(f"{record_id}: solutions must be a list of strings")
    normalized = [item for item in value if item.strip()]
    return None if not normalized else stable_json_hash(normalized)


def _deepcoder_raw_record_hash(row: Mapping[str, object]) -> str:
    """Hash the fixed DeepCoder projection using the exact canonical-JSON byte contract."""
    if set(row) != {"problem", "solutions", "tests"}:
        raise RefreshSourceError("DeepCoder row has unexpected top-level schema")
    problem = row["problem"]
    solutions = row["solutions"]
    tests = row["tests"]
    if not isinstance(problem, str) or not isinstance(tests, str):
        raise RefreshSourceError("DeepCoder problem/tests projection fields must be strings")
    if not isinstance(solutions, list) or any(not isinstance(item, str) for item in solutions):
        raise RefreshSourceError("DeepCoder solutions projection field must be a list of strings")

    encode = json.encoder.encode_basestring
    payload = (
        '{"problem":'
        + encode(problem)
        + ',"solutions":['
        + ",".join(encode(item) for item in solutions)
        + '],"tests":'
        + encode(tests)
        + "}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate_from_row(
    spec: RefreshSourceSpec,
    row: Mapping[str, object],
    *,
    row_index: int,
    raw_hash: str | None = None,
) -> RefreshCandidate | None:
    if set(row) != {"problem", "solutions", "tests"}:
        raise RefreshSourceError(f"{spec.source_name} row {row_index}: unexpected top-level schema")
    prompt = row["problem"]
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    record_id = f"{spec.config_name}/{spec.split}/{row_index}"
    resolved_raw_hash = _deepcoder_raw_record_hash(row) if raw_hash is None else raw_hash
    solution_hash = _raw_reference_solution_hash(row["solutions"], record_id=record_id)
    try:
        parsed_tests = _strict_tests_json(row["tests"], record_id=record_id)
        if spec.config_name == "primeintellect":
            tests = _primeintellect_tests(parsed_tests, record_id=record_id)
        elif spec.config_name == "taco":
            tests = _taco_tests(parsed_tests, record_id=record_id)
        else:
            raise RefreshSourceError(f"unsupported DeepCoder config {spec.config_name!r}")
        if len(tests) < 4:
            return None
        test_fingerprint, payload_sha256 = _refresh_stdio_test_fingerprints(tests, context=record_id)
    except ValueError:
        return None
    validation_guard = _test_validation_guard(test_fingerprint, payload_sha256)
    candidate_id = stable_json_hash(
        {
            "protocol": "wp9a-refresh-candidate-v1",
            "source_name": spec.source_name,
            "dataset_id": spec.dataset_id,
            "revision": spec.revision,
            "config_name": spec.config_name,
            "split": spec.split,
            "row_index": row_index,
            "raw_record_sha256": resolved_raw_hash,
        }
    )
    return RefreshCandidate(
        candidate_id=candidate_id,
        source_name=spec.source_name,
        source_record_id=record_id,
        prompt=prompt.strip(),
        function_name="solve_io",
        function_signature="def solve_io(input_text: str) -> str:",
        tests=tests,
        source_url_hash=None,
        raw_reference_solution_hash=solution_hash,
        difficulty="unknown",
        category=("stdio",),
        raw_record_sha256=resolved_raw_hash,
        test_fingerprint=test_fingerprint,
        test_validation_guard=validation_guard,
    )


def _function_candidate_from_row(
    spec: RefreshSourceSpec,
    row: Mapping[str, object],
    *,
    row_index: int,
    raw_hash: str | None = None,
) -> RefreshCandidate | None:
    if set(row) != {"problem", "solutions", "tests"}:
        raise RefreshSourceError(f"{spec.source_name} row {row_index}: unexpected top-level schema")
    prompt = row["problem"]
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    record_id = f"{spec.config_name}/{spec.split}/{row_index}"
    resolved_raw_hash = _deepcoder_raw_record_hash(row) if raw_hash is None else raw_hash
    solution_hash = _raw_reference_solution_hash(row["solutions"], record_id=record_id)
    try:
        parsed_tests = _strict_tests_json(row["tests"], record_id=record_id)
        parsed_function: tuple[str, tuple[TestCase, ...]] | None
        if spec.config_name == "primeintellect":
            parsed_function = _primeintellect_function_call_tests(parsed_tests, record_id=record_id)
        elif spec.config_name == "taco":
            parsed_function = _taco_function_call_tests(parsed_tests, record_id=record_id)
        else:
            raise RefreshSourceError(f"unsupported DeepCoder config {spec.config_name!r}")
        if parsed_function is None:
            return None
        function_name, tests = parsed_function
        if len(tests) < 4:
            return None
        arities = {len(cast(Sequence[object], test.input)) for test in tests}
        function_signature = _function_signature_from_row(
            row,
            function_name=function_name,
            arities=arities,
        )
        if function_signature is None:
            return None
        test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
    except (DuplicateDataError, ValueError):
        return None
    candidate_id = stable_json_hash(
        {
            "protocol": "wp9a-refresh-candidate-v1",
            "source_name": spec.source_name,
            "dataset_id": spec.dataset_id,
            "revision": spec.revision,
            "config_name": spec.config_name,
            "split": spec.split,
            "row_index": row_index,
            "raw_record_sha256": resolved_raw_hash,
        }
    )
    return RefreshCandidate(
        candidate_id=candidate_id,
        source_name=spec.source_name,
        source_record_id=record_id,
        prompt=prompt.strip(),
        function_name=function_name,
        function_signature=function_signature,
        tests=tests,
        source_url_hash=None,
        raw_reference_solution_hash=solution_hash,
        difficulty="unknown",
        category=("function_call",),
        raw_record_sha256=resolved_raw_hash,
        test_fingerprint=test_fingerprint,
        test_validation_guard=None,
    )


def _lcbv5_function_candidate_from_row(
    spec: RefreshSourceSpec,
    row: Mapping[str, object],
    *,
    row_index: int,
    raw_hash: str | None = None,
) -> RefreshCandidate | None:
    expected_fields = {"problem", "starter_code", "tests", "metadata"}
    if set(row) != expected_fields:
        raise RefreshSourceError(f"{spec.source_name} row {row_index}: unexpected lcbv5 schema")
    prompt = row["problem"]
    starter_code = row["starter_code"]
    metadata = row["metadata"]
    tests_text = row["tests"]
    if (
        not isinstance(prompt, str)
        or not prompt.strip()
        or not isinstance(starter_code, str)
        or not isinstance(metadata, Mapping)
        or not isinstance(tests_text, str)
    ):
        return None
    function_name = metadata.get("func_name")
    if not isinstance(function_name, str) or not function_name.isidentifier() or keyword.iskeyword(function_name):
        return None
    record_id = f"lcbv5/{spec.split}/{row_index}"
    try:
        parsed = ast.parse(starter_code + "pass\n")
        methods = [
            node for node in ast.walk(parsed) if isinstance(node, ast.FunctionDef) and node.name == function_name
        ]
        if len(methods) != 1:
            return None
        arguments = methods[0].args
        positional = [*arguments.posonlyargs, *arguments.args]
        if (
            len(positional) < 2
            or positional[0].arg != "self"
            or arguments.defaults
            or arguments.vararg is not None
            or arguments.kwonlyargs
            or arguments.kwarg is not None
        ):
            return None
        parameter_names = [argument.arg for argument in positional[1:]]
        function_signature = f"def {function_name}({', '.join(parameter_names)}):"
        raw_tests = loads_strict(tests_text)
        if not isinstance(raw_tests, list) or len(raw_tests) < 4:
            return None
        tests: list[TestCase] = []
        for test_index, item in enumerate(raw_tests):
            if not isinstance(item, dict) or set(item) != {"input", "output", "testtype"}:
                return None
            if item["testtype"] != "functional":
                return None
            input_values = _decode_concatenated_json_values(
                item["input"],
                record_id=record_id,
                field=f"tests[{test_index}].input",
            )
            output_values = _decode_concatenated_json_values(
                item["output"],
                record_id=record_id,
                field=f"tests[{test_index}].output",
            )
            if len(input_values) != len(parameter_names) or len(output_values) != 1:
                return None
            tests.append(
                TestCase(
                    input=tuple(validate_json_value(value, field_path=f"{record_id}.input") for value in input_values),
                    expected=validate_json_value(output_values[0], field_path=f"{record_id}.expected"),
                )
            )
        test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
    except (DuplicateDataError, StrictJsonError, ValueError, SyntaxError):
        return None
    resolved_raw_hash = stable_json_hash(row) if raw_hash is None else raw_hash
    candidate_id = stable_json_hash(
        {
            "protocol": "wp9c-function-refresh-lcbv5-v1",
            "source_name": spec.source_name,
            "dataset_id": spec.dataset_id,
            "revision": spec.revision,
            "config_name": spec.config_name,
            "split": spec.split,
            "row_index": row_index,
            "raw_record_sha256": resolved_raw_hash,
        }
    )
    return RefreshCandidate(
        candidate_id=candidate_id,
        source_name=spec.source_name,
        source_record_id=record_id,
        prompt=prompt.strip(),
        function_name=function_name,
        function_signature=function_signature,
        tests=tuple(tests),
        source_url_hash=None,
        raw_reference_solution_hash=None,
        difficulty="unknown",
        category=("function_call", "lcbv5_train"),
        raw_record_sha256=resolved_raw_hash,
        test_fingerprint=test_fingerprint,
        test_validation_guard=None,
    )


def _opencoder_assert_test_case(
    text: object,
    *,
    record_id: str,
    function_name: str,
) -> TestCase:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{record_id}: OpenCoder testcase must be a non-empty string")
    try:
        module = ast.parse(text)
    except SyntaxError as error:
        raise ValueError(f"{record_id}: OpenCoder testcase has invalid Python syntax") from error
    if len(module.body) != 1 or not isinstance(module.body[0], ast.Assert):
        raise ValueError(f"{record_id}: OpenCoder testcase must contain exactly one assert")
    expression = module.body[0].test
    if (
        not isinstance(expression, ast.Compare)
        or len(expression.ops) != 1
        or not isinstance(expression.ops[0], ast.Eq)
        or len(expression.comparators) != 1
    ):
        raise ValueError(f"{record_id}: OpenCoder testcase must be a single equality assertion")
    sides = (expression.left, expression.comparators[0])
    call_side: ast.Call | None = None
    expected_side: ast.expr | None = None
    for left, right in (sides, sides[::-1]):
        if (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == function_name
            and not left.keywords
            and all(not isinstance(argument, ast.Starred) for argument in left.args)
        ):
            call_side = left
            expected_side = right
            break
    if call_side is None or expected_side is None:
        raise ValueError(f"{record_id}: OpenCoder testcase does not call the frozen entry point")
    try:
        arguments = [ast.literal_eval(argument) for argument in call_side.args]
        expected = ast.literal_eval(expected_side)
    except (ValueError, TypeError, MemoryError, RecursionError) as error:
        raise ValueError(f"{record_id}: OpenCoder testcase contains non-literal values") from error
    return TestCase(
        input=tuple(validate_json_value(value, field_path=f"{record_id}.input") for value in arguments),
        expected=validate_json_value(expected, field_path=f"{record_id}.expected"),
    )


def _opencoder_candidate_from_row(
    row: Mapping[str, object],
    *,
    row_index: int,
    dataset_id: str,
    revision: str,
    source_name: str = "opencoder-educational",
) -> RefreshCandidate | None:
    expected_fields = {"seq_id", "instruction", "output", "code", "entry_point", "testcase"}
    if set(row) != expected_fields:
        raise RefreshSourceError(f"{source_name} row {row_index}: unexpected schema")
    instruction = row["instruction"]
    code = row["code"]
    entry_point = row["entry_point"]
    testcases = row["testcase"]
    if (
        not isinstance(instruction, str)
        or not instruction.strip()
        or not isinstance(code, str)
        or not code.strip()
        or not isinstance(entry_point, str)
        or not entry_point.isidentifier()
        or keyword.iskeyword(entry_point)
        or not isinstance(testcases, list)
        or len(testcases) < 4
    ):
        return None
    record_id = f"educational_instruct/train/{row_index}"
    try:
        tests = tuple(
            _opencoder_assert_test_case(testcase, record_id=record_id, function_name=entry_point)
            for testcase in testcases
        )
        arities = {len(cast(Sequence[object], test.input)) for test in tests}
        function_signature = _function_signature_from_row(
            {"problem": instruction, "solutions": [code]},
            function_name=entry_point,
            arities=arities,
        )
        if function_signature is None:
            return None
        test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
    except (DuplicateDataError, ValueError):
        return None
    raw_hash = stable_json_hash(row)
    candidate_id = stable_json_hash(
        {
            "protocol": "wp9c-function-refresh-opencoder-v1",
            "source_name": source_name,
            "dataset_id": dataset_id,
            "revision": revision,
            "config_name": "educational_instruct",
            "split": "train",
            "row_index": row_index,
            "raw_record_sha256": raw_hash,
        }
    )
    return RefreshCandidate(
        candidate_id=candidate_id,
        source_name=source_name,
        source_record_id=record_id,
        prompt=instruction.strip(),
        function_name=entry_point,
        function_signature=function_signature,
        tests=tests,
        source_url_hash=None,
        raw_reference_solution_hash=stable_json_hash([code]),
        difficulty="unknown",
        category=("function_call", "opencoder_educational"),
        raw_record_sha256=raw_hash,
        test_fingerprint=test_fingerprint,
        test_validation_guard=None,
    )


def _projection_fingerprint(raw_hashes: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for raw_hash in raw_hashes:
        digest.update(raw_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_refresh_source(
    spec: RefreshSourceSpec,
    *,
    cache_dir: Path | None,
) -> tuple[RefreshSourceSnapshot, list[RefreshCandidate]]:
    """Load one pinned DeepCoder projection and retain only safe fixed-output stdio candidates."""
    if spec.adapter != "deepcoder":
        raise RefreshSourceError(f"unsupported refresh source adapter {spec.adapter!r}")
    if spec.config_name not in {"primeintellect", "taco"} or spec.split != "train":
        raise RefreshSourceError("DeepCoder WP9-a sources must use primeintellect/train or taco/train")
    snapshot_dir = _resolve_snapshot(spec.dataset_id, spec.revision, cache_dir=cache_dir)
    _validate_license(snapshot_dir, spec.declared_license)

    candidates: list[RefreshCandidate] = []
    projection_digest = hashlib.sha256()
    scanned_rows = 0
    rows = enumerate(_iter_parquet_rows(snapshot_dir, spec.config_name, spec.split), start=0)

    def project_row(item: tuple[int, Mapping[str, object]]) -> tuple[str, RefreshCandidate | None]:
        row_index, row = item
        raw_hash = _deepcoder_raw_record_hash(row)
        return raw_hash, _candidate_from_row(spec, row, row_index=row_index, raw_hash=raw_hash)

    with ThreadPoolExecutor(max_workers=4) as pool:
        while batch := list(islice(rows, 128)):
            scanned_rows += len(batch)
            for raw_hash, candidate in pool.map(project_row, batch):
                projection_digest.update(raw_hash.encode("ascii"))
                projection_digest.update(b"\n")
                if candidate is not None:
                    candidates.append(candidate)
    snapshot = RefreshSourceSnapshot(
        source_name=spec.source_name,
        dataset_id=spec.dataset_id,
        revision=spec.revision,
        config_name=spec.config_name,
        split=spec.split,
        declared_license=spec.declared_license,
        scanned_rows=scanned_rows,
        accepted_rows=len(candidates),
        projection_fingerprint_sha256=projection_digest.hexdigest(),
    )
    return snapshot, candidates


def load_refresh_function_call_source(
    spec: RefreshSourceSpec,
    *,
    cache_dir: Path | None,
) -> tuple[RefreshSourceSnapshot, list[RefreshCandidate]]:
    """Load the pinned DeepCoder projection and retain only validated function-call candidates."""
    if spec.adapter != "deepcoder":
        raise RefreshSourceError(f"unsupported refresh source adapter {spec.adapter!r}")
    if spec.config_name not in {"primeintellect", "taco"} or spec.split != "train":
        raise RefreshSourceError("DeepCoder function-call sources must use primeintellect/train or taco/train")
    snapshot_dir = _resolve_snapshot(spec.dataset_id, spec.revision, cache_dir=cache_dir)
    _validate_license(snapshot_dir, spec.declared_license)

    candidates: list[RefreshCandidate] = []
    projection_digest = hashlib.sha256()
    scanned_rows = 0
    rows = enumerate(_iter_parquet_rows(snapshot_dir, spec.config_name, spec.split), start=0)

    def project_row(item: tuple[int, Mapping[str, object]]) -> tuple[str, RefreshCandidate | None]:
        row_index, row = item
        raw_hash = _deepcoder_raw_record_hash(row)
        return raw_hash, _function_candidate_from_row(spec, row, row_index=row_index, raw_hash=raw_hash)

    with ThreadPoolExecutor(max_workers=4) as pool:
        while batch := list(islice(rows, 128)):
            scanned_rows += len(batch)
            for raw_hash, candidate in pool.map(project_row, batch):
                projection_digest.update(raw_hash.encode("ascii"))
                projection_digest.update(b"\n")
                if candidate is not None:
                    candidates.append(candidate)
    snapshot = RefreshSourceSnapshot(
        source_name=spec.source_name,
        dataset_id=spec.dataset_id,
        revision=spec.revision,
        config_name=spec.config_name,
        split=spec.split,
        declared_license=spec.declared_license,
        scanned_rows=scanned_rows,
        accepted_rows=len(candidates),
        projection_fingerprint_sha256=projection_digest.hexdigest(),
    )
    return snapshot, candidates


def load_lcbv5_function_call_source(
    spec: RefreshSourceSpec,
    *,
    cache_dir: Path | None,
    shard_index: int | None = None,
) -> tuple[RefreshSourceSnapshot, list[RefreshCandidate]]:
    """Load the pinned DeepCoder lcbv5 train split and retain only functional-call candidates."""
    if spec.adapter != "deepcoder" or spec.config_name != "lcbv5" or spec.split != "train":
        raise RefreshSourceError("DeepCoder lcbv5 function-call source must use lcbv5/train")
    snapshot_dir = _resolve_snapshot(spec.dataset_id, spec.revision, cache_dir=cache_dir)
    _validate_license(snapshot_dir, spec.declared_license)
    candidates: list[RefreshCandidate] = []
    projection_digest = hashlib.sha256()
    scanned_rows = 0
    rows = _iter_lcbv5_parquet_rows(snapshot_dir, spec.split, shard_index=shard_index)
    for row_index, row in rows:
        scanned_rows += 1
        raw_hash = stable_json_hash(row)
        projection_digest.update(raw_hash.encode("ascii"))
        projection_digest.update(b"\n")
        candidate = _lcbv5_function_candidate_from_row(spec, row, row_index=row_index, raw_hash=raw_hash)
        if candidate is not None:
            candidates.append(candidate)
    snapshot = RefreshSourceSnapshot(
        source_name=spec.source_name,
        dataset_id=spec.dataset_id,
        revision=spec.revision,
        config_name=spec.config_name,
        split=spec.split,
        declared_license=spec.declared_license,
        scanned_rows=scanned_rows,
        accepted_rows=len(candidates),
        projection_fingerprint_sha256=projection_digest.hexdigest(),
    )
    return snapshot, candidates


def load_opencoder_educational_source(
    *,
    dataset_id: str,
    revision: str,
    declared_license: str,
    cache_dir: Path | None,
    expected_parquet_sha256: str | None = None,
) -> tuple[RefreshSourceSnapshot, list[RefreshCandidate]]:
    """Load the pinned OpenCoder educational_instruct parquet with a conservative assert-only adapter."""
    snapshot_dir = _resolve_snapshot(dataset_id, revision, cache_dir=cache_dir)
    _validate_license(snapshot_dir, declared_license)
    path = snapshot_dir / "educational_instruct" / "train-00000-of-00001.parquet"
    if not path.is_file():
        raise RefreshSourceError(f"pinned OpenCoder snapshot is missing {path.relative_to(snapshot_dir)}")
    if expected_parquet_sha256 is not None:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected_parquet_sha256:
            raise RefreshSourceError("OpenCoder educational parquet SHA256 mismatch")
    expected_fields = {"seq_id", "instruction", "output", "code", "entry_point", "testcase"}
    try:
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(path)
        column_names = parquet_file.schema_arrow.names
        if set(column_names) != expected_fields:
            raise RefreshSourceError(
                f"OpenCoder educational schema drift: expected {sorted(expected_fields)}, got {column_names}"
            )
        candidates: list[RefreshCandidate] = []
        projection_digest = hashlib.sha256()
        scanned_rows = 0
        for batch in parquet_file.iter_batches(batch_size=128, columns=column_names):
            for row in batch.to_pylist():
                if not isinstance(row, Mapping):
                    raise RefreshSourceError("OpenCoder educational row is not a mapping")
                raw_hash = stable_json_hash(row)
                projection_digest.update(raw_hash.encode("ascii"))
                projection_digest.update(b"\n")
                candidate = _opencoder_candidate_from_row(
                    row,
                    row_index=scanned_rows,
                    dataset_id=dataset_id,
                    revision=revision,
                )
                scanned_rows += 1
                if candidate is not None:
                    candidates.append(candidate)
    except RefreshSourceError:
        raise
    except Exception as error:
        raise RefreshSourceError(f"could not read OpenCoder educational parquet: {error}") from error
    snapshot = RefreshSourceSnapshot(
        source_name="opencoder-educational",
        dataset_id=dataset_id,
        revision=revision,
        config_name="educational_instruct",
        split="train",
        declared_license=declared_license,
        scanned_rows=scanned_rows,
        accepted_rows=len(candidates),
        projection_fingerprint_sha256=projection_digest.hexdigest(),
    )
    return snapshot, candidates


def load_humanevalplus_references(
    *,
    dataset_id: str,
    revision: str,
    cache_dir: Path | None,
) -> tuple[RefreshSourceSnapshot, list[OverlapReference]]:
    """Load minimal HumanEvalPlus exclusion references without retaining tests or solution text."""
    snapshot_dir = _resolve_snapshot(dataset_id, revision, cache_dir=cache_dir)
    declared_license = "Apache-2.0"
    _validate_license(snapshot_dir, declared_license)
    path = snapshot_dir / "test.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise RefreshSourceError(f"could not read HumanEvalPlus snapshot {path}: {error}") from error
    references: list[OverlapReference] = []
    raw_hashes: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise RefreshSourceError(f"{path}, line {line_number}: {error}") from error
        if not isinstance(value, dict) or set(value) != {
            "task_id",
            "prompt",
            "canonical_solution",
            "entry_point",
            "test",
        }:
            raise RefreshSourceError(f"{path}, line {line_number}: HumanEvalPlus schema drift")
        if any(not isinstance(value[field], str) for field in value):
            raise RefreshSourceError(f"{path}, line {line_number}: HumanEvalPlus fields must all be strings")
        raw_hash = stable_json_hash(value)
        raw_hashes.append(raw_hash)
        task_id = cast(str, value["task_id"])
        prompt = cast(str, value["prompt"])
        entry_point = cast(str, value["entry_point"])
        solution = cast(str, value["canonical_solution"])
        if not task_id.strip() or not prompt.strip() or not entry_point.strip():
            raise RefreshSourceError(f"{path}, line {line_number}: HumanEvalPlus identity fields must be non-empty")
        references.append(
            OverlapReference(
                reference_id=f"humanevalplus:{task_id.strip()}",
                reference_class="external_eval",
                prompt=prompt,
                function_signature=f"entry_point:{entry_point.strip()}",
                source_url_hash=None,
                reference_solution_hash=None if not solution.strip() else stable_json_hash(solution),
                test_fingerprint=None,
            )
        )
    if not references:
        raise RefreshSourceError("HumanEvalPlus snapshot contains no exclusion references")
    return (
        RefreshSourceSnapshot(
            source_name="humanevalplus",
            dataset_id=dataset_id,
            revision=revision,
            config_name=None,
            split="test",
            declared_license=declared_license,
            scanned_rows=len(references),
            accepted_rows=len(references),
            projection_fingerprint_sha256=_projection_fingerprint(raw_hashes),
        ),
        references,
    )


_REFRESH_INTERFACE_NOTE = (
    "Interface note: implement solve_io(input_text: str) -> str. The argument is the complete stdin text; "
    "return the exact stdout text. Do not read host stdin or write host stdout."
)


def canonicalize_refresh_candidate(candidate: RefreshCandidate, *, seed: int) -> tuple[CodeProblem, bool]:
    """Return a canonical train problem plus whether its test count needs a later quality gate."""
    is_stdio = (
        candidate.function_name == "solve_io"
        and candidate.function_signature == "def solve_io(input_text: str) -> str:"
    )
    if candidate.test_validation_guard is None:
        visible, train_hidden, eval_hidden = split_refresh_test_cases(
            candidate.tests,
            problem_id=candidate.candidate_id,
            seed=seed,
        )
    else:
        if not is_stdio:
            raise ValueError("prevalidated DeepCoder test guards are valid only for the frozen stdio projection")
        if candidate.test_fingerprint is None:
            raise ValueError(
                f"refresh candidate {candidate.candidate_id} is missing its prevalidated test fingerprint"
            )
        payload_sha256 = _stdio_test_payload_sha256(candidate.tests)
        expected_guard = _test_validation_guard(candidate.test_fingerprint, payload_sha256)
        if candidate.test_validation_guard != expected_guard:
            raise ValueError(f"refresh candidate {candidate.candidate_id} has inconsistent prevalidated tests")
        visible, train_hidden, eval_hidden = _split_refresh_test_cases_prevalidated(
            candidate.tests,
            problem_id=candidate.candidate_id,
            seed=seed,
        )
    canonical_prompt = (
        f"{candidate.prompt.rstrip()}\n\n{_REFRESH_INTERFACE_NOTE}" if is_stdio else candidate.prompt.rstrip()
    )
    problem = CodeProblem(
        problem_id=candidate.candidate_id,
        source=candidate.source_name,
        split="train",
        prompt=canonical_prompt,
        function_name=candidate.function_name,
        function_signature=candidate.function_signature,
        starter_code=None,
        visible_tests=visible,
        train_hidden_tests=train_hidden,
        eval_hidden_tests=eval_hidden,
        reference_solution=None,
        sft_response=None,
        metadata=ProblemMetadata(
            difficulty=candidate.difficulty,
            category=candidate.category,
            time_limit_seconds=2.0,
            memory_limit_mb=512,
            license="MIT",
            source_url_hash=candidate.source_url_hash,
        ),
    )
    validate_problem(problem)
    return problem, len(candidate.tests) < 8


def refresh_candidate_projection(candidate: RefreshCandidate) -> str:
    """Return a deterministic audit projection without exposing prompt/test contents."""
    return canonical_json(
        {
            "candidate_id": candidate.candidate_id,
            "source_name": candidate.source_name,
            "source_record_id": candidate.source_record_id,
            "raw_record_sha256": candidate.raw_record_sha256,
        }
    )
