"""Pinned-source ingestion and stdio canonicalization for the WP9-a refresh pool."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from code_verifier.data.deduplicate import canonical_json, stable_json_hash, unique_test_case_hashes
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.schema import CodeProblem, ProblemMetadata, TestCase, validate_problem
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
    test_case_hashes: tuple[str, ...] | None = None
    test_fingerprint: str | None = None


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


def _iter_parquet_rows(snapshot: Path, config_name: str, split: str) -> Iterable[Mapping[str, object]]:
    config_dir = snapshot / config_name
    files = sorted(config_dir.glob(f"{split}-*.parquet"))
    if not files:
        raise RefreshSourceError(f"pinned snapshot has no parquet files for {config_name}/{split}")
    try:
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

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
        test_hashes = unique_test_case_hashes(tests, context=record_id)
    except ValueError:
        return None
    if len(tests) < 4:
        return None
    test_fingerprint = stable_json_hash(sorted(test_hashes))
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
        test_case_hashes=test_hashes,
        test_fingerprint=test_fingerprint,
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
    raw_hashes: list[str] = []
    scanned_rows = 0
    for row_index, row in enumerate(
        _iter_parquet_rows(snapshot_dir, spec.config_name, spec.split),
        start=0,
    ):
        scanned_rows += 1
        raw_hash = _deepcoder_raw_record_hash(row)
        raw_hashes.append(raw_hash)
        candidate = _candidate_from_row(spec, row, row_index=row_index, raw_hash=raw_hash)
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
        projection_fingerprint_sha256=_projection_fingerprint(raw_hashes),
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
    if candidate.test_case_hashes is None:
        visible, train_hidden, eval_hidden = split_refresh_test_cases(
            candidate.tests,
            problem_id=candidate.candidate_id,
            seed=seed,
        )
    else:
        expected_fingerprint = stable_json_hash(sorted(candidate.test_case_hashes))
        if candidate.test_fingerprint != expected_fingerprint:
            raise ValueError(f"refresh candidate {candidate.candidate_id} has inconsistent prevalidated test hashes")
        visible, train_hidden, eval_hidden = _split_refresh_test_cases_prevalidated(
            candidate.tests,
            problem_id=candidate.candidate_id,
            seed=seed,
            test_case_hashes=candidate.test_case_hashes,
        )
    problem = CodeProblem(
        problem_id=candidate.candidate_id,
        source=candidate.source_name,
        split="train",
        prompt=f"{candidate.prompt.rstrip()}\n\n{_REFRESH_INTERFACE_NOTE}",
        function_name="solve_io",
        function_signature="def solve_io(input_text: str) -> str:",
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
