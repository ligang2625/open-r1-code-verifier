"""Deterministic WP9-a refresh selection, materialization, manifests, and strict readback."""

from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.deduplicate import (
    DuplicateDataError,
    problem_reference_solution_hash,
    stable_json_hash,
)
from code_verifier.data.json_strict import json_values_equal, loads_strict
from code_verifier.data.leakage_checks import (
    TrainingArtifactKind,
    _build_training_record_unchecked,
    load_training_artifact,
)
from code_verifier.data.prepare import DataPreparationError, load_canonical_jsonl, write_jsonl_with_stats
from code_verifier.data.refresh_dedup import (
    RefreshDedupDecision,
    RefreshDedupPolicy,
    RefreshFingerprint,
    _build_near_index_context,
    _NearIndexContext,
    build_refresh_fingerprint,
    candidate_fingerprint,
    classify_refresh_candidates,
    find_exact_duplicate_matches,
    find_near_duplicate_matches,
    reference_fingerprint,
    validate_refresh_dedup_policy,
)
from code_verifier.data.refresh_sources import (
    _REFRESH_INTERFACE_NOTE,
    OverlapReference,
    RefreshCandidate,
    RefreshSourceSnapshot,
    RefreshSourceSpec,
    canonicalize_refresh_candidate,
    load_humanevalplus_references,
    load_refresh_source,
    refresh_problem_test_set_fingerprint,
)
from code_verifier.data.schema import (
    CodeProblem,
    JsonValue,
    json_value_to_mutable,
    problem_to_mapping,
)

REFRESH_SCHEMA_VERSION = "wp9a-refresh-v1"
REFRESH_TEST_SCHEMA_VERSION = "wp9a-refresh-test-v1"
REFERENCE_SNAPSHOT_SCHEMA_VERSION = "wp9a-reference-snapshots-v1"
SELECTION_SCHEMA_VERSION = "wp9a-selection-v1"

_WP9A_PRODUCTION_TARGET_SIZE = 10_000
_WP9A_PRODUCTION_SFT_OVERLAP_FRACTION = 0.075
_WP9A_SFT_OVERLAP_HARD_MAX = 0.15
_WP9A_EXTERNAL_EVAL_DATASET_ID = "evalplus/humanevalplus"
_WP9A_EXTERNAL_EVAL_REVISION = "aa0d916268b1c17e84e881e9bd460508dd2fd308"
_WP9A_EXTERNAL_EVAL_LICENSE = "Apache-2.0"
_WP9A_EXTERNAL_EVAL_COUNT = 164
_WP9A_EXTERNAL_EVAL_PROJECTION_SHA256 = "d538bb58cbf89c74001c7e60b21a38552af6666da695e27182d66c97297b0314"
_WP9A_EXTERNAL_EVAL_INVENTORY_SHA256 = "b9cf681ddf22f2195ff1a74added578b0dd58108031d93fd4c9a560fd58f5dac"
_WP9A_DEEPCODER_DATASET_ID = "agentica-org/DeepCoder-Preview-Dataset"
_WP9A_DEEPCODER_REVISION = "177913a7bd43791646ef6a43645caa3c871ab3db"
_WP9A_PRODUCTION_SOURCES = (
    RefreshSourceSpec(
        source_name="deepcoder-primeintellect",
        dataset_id=_WP9A_DEEPCODER_DATASET_ID,
        revision=_WP9A_DEEPCODER_REVISION,
        config_name="primeintellect",
        split="train",
        declared_license="MIT",
        adapter="deepcoder",
    ),
    RefreshSourceSpec(
        source_name="deepcoder-taco",
        dataset_id=_WP9A_DEEPCODER_DATASET_ID,
        revision=_WP9A_DEEPCODER_REVISION,
        config_name="taco",
        split="train",
        declared_license="MIT",
        adapter="deepcoder",
    ),
)
_WP9A_PRODUCTION_SOURCE_SNAPSHOTS = {
    "deepcoder-primeintellect": (16_252, 11_323, "6241f5c56810008cf12cb94b47d9ec8fd49f5048fa2900d77b3ce87531f2480c"),
    "deepcoder-taco": (7_436, 2_642, "d5b1242810ec37f9a524a7e2c7b3731595e269544b7add719cccfea51e2fe6de"),
}

_REQUIRED_ARTIFACTS = (
    "manifest/source_snapshots.json",
    "manifest/reference_snapshots.json",
    "manifest/dedup_decisions.jsonl",
    "manifest/selection.jsonl",
    "manifest/problem_order.jsonl",
    "reports/dedup_summary.json",
    "reports/sft_overlap.json",
    "reports/evaluation_overlap.json",
    "reports/test_layer_leakage.json",
    "canonical/problems.jsonl",
    "training/public_grpo.jsonl",
    "training/hidden_grpo.jsonl",
)


class RefreshDataError(RuntimeError):
    """Raised when WP9-a refresh preparation or strict readback fails closed."""


@dataclass(frozen=True)
class RefreshSelectionConfig:
    target_size: int
    sft_overlap_fraction: float
    sft_overlap_hard_max: float
    token_ngram_size: int
    near_jaccard_threshold: float


@dataclass(frozen=True)
class RefreshDataConfig:
    sources: tuple[RefreshSourceSpec, ...]
    external_eval_dataset_id: str
    external_eval_revision: str
    selection: RefreshSelectionConfig


@dataclass(frozen=True)
class RefreshPreparationSummary:
    total_candidates_scanned: int
    external_candidates_retained: int
    selected_problems: int
    sft_overlap_count: int
    sft_overlap_fraction: float
    quality_gate_required_count: int
    canonical_jsonl: Path
    public_grpo_jsonl: Path
    hidden_grpo_jsonl: Path
    root_manifest: Path


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


def _nonempty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a non-empty string")
    return value.strip()


def _full_sha(value: object, *, field: str) -> str:
    text = _nonempty_string(value, field=field).casefold()
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        raise ConfigError(f"{field} must be a full 40-character hexadecimal commit SHA")
    return text


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{field} must be a positive integer")
    return value


def _finite_float(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ConfigError(f"{field} must be a finite number")
    return float(value)


def refresh_data_config_from_mapping(value: Mapping[str, object], *, config_path: Path) -> RefreshDataConfig:
    root = _exact_mapping(value, {"version", "sources", "external_eval", "selection"}, field=str(config_path))
    if root["version"] != REFRESH_SCHEMA_VERSION:
        raise ConfigError(f"{config_path}.version must be {REFRESH_SCHEMA_VERSION}")
    sources_value = root["sources"]
    if not isinstance(sources_value, list) or not sources_value:
        raise ConfigError("sources must be a non-empty list")
    sources: list[RefreshSourceSpec] = []
    for index, item in enumerate(sources_value):
        source = _exact_mapping(
            item,
            {"source_name", "dataset_id", "revision", "config_name", "split", "declared_license", "adapter"},
            field=f"sources[{index}]",
        )
        config_name = source["config_name"]
        if config_name is not None and (not isinstance(config_name, str) or not config_name.strip()):
            raise ConfigError(f"sources[{index}].config_name must be a non-empty string or null")
        if source["adapter"] != "deepcoder":
            raise ConfigError(f"sources[{index}].adapter must be deepcoder")
        sources.append(
            RefreshSourceSpec(
                source_name=_nonempty_string(source["source_name"], field=f"sources[{index}].source_name"),
                dataset_id=_nonempty_string(source["dataset_id"], field=f"sources[{index}].dataset_id"),
                revision=_full_sha(source["revision"], field=f"sources[{index}].revision"),
                config_name=None if config_name is None else config_name.strip(),
                split=_nonempty_string(source["split"], field=f"sources[{index}].split"),
                declared_license=_nonempty_string(
                    source["declared_license"], field=f"sources[{index}].declared_license"
                ),
                adapter="deepcoder",
            )
        )
    names = [source.source_name for source in sources]
    if len(names) != len(set(names)):
        raise ConfigError("sources.source_name values must be unique")
    if tuple(sources) != _WP9A_PRODUCTION_SOURCES:
        raise ConfigError(
            f"{config_path}.sources: {REFRESH_SCHEMA_VERSION} freezes the two approved DeepCoder projections"
        )
    external = _exact_mapping(root["external_eval"], {"dataset_id", "revision"}, field="external_eval")
    selection = _exact_mapping(
        root["selection"],
        {"target_size", "sft_overlap_fraction", "sft_overlap_hard_max", "token_ngram_size", "near_jaccard_threshold"},
        field="selection",
    )
    selection_config = RefreshSelectionConfig(
        target_size=_positive_int(selection["target_size"], field="selection.target_size"),
        sft_overlap_fraction=_finite_float(selection["sft_overlap_fraction"], field="selection.sft_overlap_fraction"),
        sft_overlap_hard_max=_finite_float(selection["sft_overlap_hard_max"], field="selection.sft_overlap_hard_max"),
        token_ngram_size=_positive_int(selection["token_ngram_size"], field="selection.token_ngram_size"),
        near_jaccard_threshold=_finite_float(
            selection["near_jaccard_threshold"], field="selection.near_jaccard_threshold"
        ),
    )
    try:
        _validate_selection_config(selection_config)
    except ValueError as error:
        raise ConfigError(f"{config_path}.selection: {error}") from error
    frozen_selection = {
        "target_size": (_WP9A_PRODUCTION_TARGET_SIZE, selection_config.target_size),
        "sft_overlap_fraction": (_WP9A_PRODUCTION_SFT_OVERLAP_FRACTION, selection_config.sft_overlap_fraction),
        "sft_overlap_hard_max": (_WP9A_SFT_OVERLAP_HARD_MAX, selection_config.sft_overlap_hard_max),
    }
    for field, (expected, actual) in frozen_selection.items():
        if isinstance(expected, float):
            matches = math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1e-12)
        else:
            matches = actual == expected
        if not matches:
            raise ConfigError(
                f"{config_path}.selection.{field}: {REFRESH_SCHEMA_VERSION} freezes this value to {expected}"
            )
    external_dataset_id = _nonempty_string(external["dataset_id"], field="external_eval.dataset_id")
    external_revision = _full_sha(external["revision"], field="external_eval.revision")
    if external_dataset_id != _WP9A_EXTERNAL_EVAL_DATASET_ID or external_revision != _WP9A_EXTERNAL_EVAL_REVISION:
        raise ConfigError(
            f"{config_path}.external_eval: {REFRESH_SCHEMA_VERSION} freezes HumanEvalPlus to "
            f"{_WP9A_EXTERNAL_EVAL_DATASET_ID}@{_WP9A_EXTERNAL_EVAL_REVISION}"
        )
    return RefreshDataConfig(
        sources=tuple(sources),
        external_eval_dataset_id=external_dataset_id,
        external_eval_revision=external_revision,
        selection=selection_config,
    )


def load_refresh_data_config(path: Path) -> RefreshDataConfig:
    return refresh_data_config_from_mapping(load_yaml_mapping(path), config_path=path)


def _validate_selection_config(config: RefreshSelectionConfig) -> None:
    if config.target_size <= 0:
        raise ValueError("target_size must be positive")
    if not 0.0 <= config.sft_overlap_fraction <= 1.0:
        raise ValueError("sft_overlap_fraction must be in [0, 1]")
    if not 0.0 <= config.sft_overlap_hard_max <= 1.0:
        raise ValueError("sft_overlap_hard_max must be in [0, 1]")
    if config.sft_overlap_hard_max > _WP9A_SFT_OVERLAP_HARD_MAX:
        raise ValueError(
            f"{REFRESH_SCHEMA_VERSION} freezes the SFT overlap hard maximum at {_WP9A_SFT_OVERLAP_HARD_MAX}"
        )
    if config.sft_overlap_fraction > config.sft_overlap_hard_max:
        raise ValueError("sft_overlap_fraction must not exceed sft_overlap_hard_max")
    validate_refresh_dedup_policy(RefreshDedupPolicy(config.token_ngram_size, config.near_jaccard_threshold))


def _is_production_config(config: RefreshDataConfig) -> bool:
    return (
        config.sources == _WP9A_PRODUCTION_SOURCES
        and config.external_eval_dataset_id == _WP9A_EXTERNAL_EVAL_DATASET_ID
        and config.external_eval_revision == _WP9A_EXTERNAL_EVAL_REVISION
        and config.selection.target_size == _WP9A_PRODUCTION_TARGET_SIZE
        and math.isclose(
            config.selection.sft_overlap_fraction,
            _WP9A_PRODUCTION_SFT_OVERLAP_FRACTION,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        and math.isclose(
            config.selection.sft_overlap_hard_max,
            _WP9A_SFT_OVERLAP_HARD_MAX,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )


def _selection_identity(value: object) -> tuple[str, str, str]:
    if isinstance(value, CodeProblem):
        return value.source, value.metadata.difficulty, value.problem_id
    if isinstance(value, RefreshCandidate):
        return value.source_name, value.difficulty, value.candidate_id
    raise TypeError(f"unsupported stratified selection value {type(value).__name__}")


def _selection_sort_hash(value: object, *, seed: int, namespace: str) -> str:
    source, difficulty, record_id = _selection_identity(value)
    return stable_json_hash(
        {
            "namespace": namespace,
            "seed": seed,
            "source": source,
            "difficulty": difficulty,
            "record_id": record_id,
        }
    )


def deterministic_stratified_select(
    candidates: Sequence[object],
    *,
    count: int,
    seed: int,
    namespace: str,
) -> list[object]:
    """Select exact proportional source+difficulty quotas using largest remainder and stable hashes."""
    if isinstance(count, bool) or count < 0:
        raise ValueError("count must be a non-negative integer")
    if count > len(candidates):
        raise RefreshDataError(f"selection requires {count} records but population contains only {len(candidates)}")
    if count == 0:
        return []
    if not namespace.strip():
        raise ValueError("selection namespace must be non-empty")

    groups: dict[tuple[str, str], list[object]] = defaultdict(list)
    seen_ids: set[str] = set()
    for candidate in candidates:
        source, difficulty, record_id = _selection_identity(candidate)
        if record_id in seen_ids:
            raise RefreshDataError(f"selection population contains duplicate record id {record_id}")
        seen_ids.add(record_id)
        groups[(source, difficulty)].append(candidate)

    total = len(candidates)
    allocations: dict[tuple[str, str], int] = {}
    remainders: list[tuple[float, tuple[str, str]]] = []
    for stratum in sorted(groups):
        quota = count * len(groups[stratum]) / total
        base = math.floor(quota)
        allocations[stratum] = base
        remainders.append((quota - base, stratum))
    remaining = count - sum(allocations.values())
    for _remainder, stratum in sorted(remainders, key=lambda item: (-item[0], item[1]))[:remaining]:
        allocations[stratum] += 1

    selected: list[object] = []
    for stratum in sorted(groups):
        ordered = sorted(
            groups[stratum],
            key=lambda item: (
                _selection_sort_hash(item, seed=seed, namespace=namespace),
                _selection_identity(item)[2],
            ),
        )
        selected.extend(ordered[: allocations[stratum]])
    return sorted(
        selected,
        key=lambda item: (
            _selection_sort_hash(item, seed=seed, namespace=f"{namespace}|merge"),
            _selection_identity(item)[2],
        ),
    )


def _quality_gate_required(problem: CodeProblem) -> bool:
    return len(problem.visible_tests) + len(problem.train_hidden_tests) + len(problem.eval_hidden_tests) < 8


def _candidate_problem_and_manifest(
    candidate: RefreshCandidate,
    *,
    seed: int,
) -> tuple[CodeProblem, dict[str, JsonValue]]:
    problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=seed)
    return problem, {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "problem_id": problem.problem_id,
        "source": problem.source,
        "difficulty": problem.metadata.difficulty,
        "overlap_origin": "external_new",
        "quality_gate_required": quality_gate_required,
        "source_record_id": candidate.source_record_id,
        "raw_record_sha256": candidate.raw_record_sha256,
    }


def select_refresh_pool(
    *,
    sft_problems: Sequence[CodeProblem],
    new_candidates: Sequence[RefreshCandidate],
    config: RefreshSelectionConfig,
    seed: int,
) -> tuple[list[CodeProblem], list[dict[str, JsonValue]]]:
    """Select explicit SFT reuse plus deduplicated new candidates and freeze one canonical order."""
    _validate_selection_config(config)
    if any(problem.split != "train" for problem in sft_problems):
        raise RefreshDataError("SFT overlap population must contain only canonical train problems")
    overlap_count = int(round(config.target_size * config.sft_overlap_fraction))
    actual_fraction = overlap_count / config.target_size
    if actual_fraction > config.sft_overlap_hard_max:
        raise RefreshDataError("rounded SFT overlap count exceeds the configured hard maximum")
    external_count = config.target_size - overlap_count
    if len(sft_problems) < overlap_count:
        raise RefreshDataError(
            f"SFT population contains {len(sft_problems)} records but overlap quota requires {overlap_count}"
        )
    if len(new_candidates) < external_count:
        by_source = Counter(candidate.source_name for candidate in new_candidates)
        raise RefreshDataError(
            "external retained population contains "
            f"{len(new_candidates)} records but quota requires {external_count}; "
            f"by_source={dict(sorted(by_source.items()))}"
        )

    selected_sft = cast(
        list[CodeProblem],
        deterministic_stratified_select(
            list(sft_problems),
            count=overlap_count,
            seed=seed,
            namespace="wp9a-sft-reuse-v1",
        ),
    )
    selected_external = cast(
        list[RefreshCandidate],
        deterministic_stratified_select(
            list(new_candidates),
            count=external_count,
            seed=seed,
            namespace="wp9a-external-new-v1",
        ),
    )

    problems: list[CodeProblem] = []
    manifest_by_id: dict[str, dict[str, JsonValue]] = {}
    for problem in selected_sft:
        problems.append(problem)
        manifest_by_id[problem.problem_id] = {
            "schema_version": SELECTION_SCHEMA_VERSION,
            "problem_id": problem.problem_id,
            "source": problem.source,
            "difficulty": problem.metadata.difficulty,
            "overlap_origin": "sft_reuse",
            "quality_gate_required": _quality_gate_required(problem),
            "source_record_id": None,
            "raw_record_sha256": None,
        }
    for candidate in selected_external:
        problem, manifest = _candidate_problem_and_manifest(candidate, seed=seed)
        problems.append(problem)
        manifest_by_id[problem.problem_id] = manifest

    if len(manifest_by_id) != config.target_size:
        raise RefreshDataError("selected pool contains duplicate problem IDs")
    problems.sort(
        key=lambda problem: (
            stable_json_hash({"namespace": "wp9a-problem-order-v1", "seed": seed, "problem_id": problem.problem_id}),
            problem.problem_id,
        )
    )
    return problems, [manifest_by_id[problem.problem_id] for problem in problems]


def _problem_reference(
    problem: CodeProblem,
    reference_class: Literal["sft", "validation", "project_test"],
) -> OverlapReference:
    return OverlapReference(
        reference_id=f"{reference_class}:{problem.problem_id}",
        reference_class=reference_class,
        prompt=problem.prompt,
        function_signature=problem.function_signature,
        source_url_hash=problem.metadata.source_url_hash,
        reference_solution_hash=problem_reference_solution_hash(problem),
        test_fingerprint=refresh_problem_test_set_fingerprint(problem),
    )


def _reference_sets(
    problems: Sequence[CodeProblem],
) -> tuple[list[OverlapReference], list[OverlapReference], list[OverlapReference]]:
    sft = [_problem_reference(problem, "sft") for problem in problems if problem.split == "train"]
    validation = [_problem_reference(problem, "validation") for problem in problems if problem.split == "validation"]
    project_test = [_problem_reference(problem, "project_test") for problem in problems if problem.split == "test"]
    return sft, validation, project_test


def _checked_selected_test_fingerprint(problem: CodeProblem) -> str:
    """Compute the selected-row test fingerprint while enforcing all-layer normalized uniqueness once."""
    try:
        return refresh_problem_test_set_fingerprint(problem)
    except DuplicateDataError as error:
        raise RefreshDataError(f"canonical selected problem {problem.problem_id} repeats a normalized test") from error


def _selected_sft_fingerprint(problem: CodeProblem, *, policy: RefreshDedupPolicy) -> RefreshFingerprint:
    return build_refresh_fingerprint(
        record_id=problem.problem_id,
        record_class="candidate",
        prompt=problem.prompt,
        function_signature=problem.function_signature,
        source_url_hash=problem.metadata.source_url_hash,
        reference_solution_hash=problem_reference_solution_hash(problem),
        test_fingerprint=_checked_selected_test_fingerprint(problem),
        policy=policy,
    )


def _canonical_selection_fingerprint(
    problem: CodeProblem,
    record: Mapping[str, object],
    *,
    policy: RefreshDedupPolicy,
) -> RefreshFingerprint:
    """Rebuild the dedup-relevant fingerprint from canonical bytes and bind it to selection provenance."""
    stored = _fingerprint_from_mapping(record.get("fingerprint"))
    if stored.record_id != problem.problem_id or stored.record_class != "candidate":
        raise RefreshDataError("selection fingerprint identity does not match canonical problem")
    if record.get("source") != problem.source or record.get("difficulty") != problem.metadata.difficulty:
        raise RefreshDataError("selection source/difficulty does not match canonical problem")

    origin = record.get("overlap_origin")
    if origin == "sft_reuse":
        rebuilt = _selected_sft_fingerprint(problem, policy=policy)
        if stored != rebuilt:
            raise RefreshDataError("stored SFT-reuse fingerprint does not match canonical problem bytes")
        return rebuilt
    if origin != "external_new":
        raise RefreshDataError("selection overlap_origin must be sft_reuse or external_new")

    suffix = f"\n\n{_REFRESH_INTERFACE_NOTE}"
    if not problem.prompt.endswith(suffix):
        raise RefreshDataError("external canonical prompt is missing the frozen solve_io interface note")
    source_prompt = problem.prompt[: -len(suffix)]
    rebuilt = build_refresh_fingerprint(
        record_id=problem.problem_id,
        record_class="candidate",
        prompt=source_prompt,
        function_signature=problem.function_signature,
        source_url_hash=problem.metadata.source_url_hash,
        reference_solution_hash=None,
        test_fingerprint=_checked_selected_test_fingerprint(problem),
        policy=policy,
    )
    comparable_fields = (
        "record_id",
        "record_class",
        "normalized_statement_hash",
        "contract_hash",
        "source_url_hash",
        "test_fingerprint",
        "token_ngrams",
    )
    if any(getattr(stored, field) != getattr(rebuilt, field) for field in comparable_fields):
        raise RefreshDataError("stored external fingerprint does not match canonical problem bytes")
    return rebuilt


def _eligible_sft_reuse_problems(
    problems: Sequence[CodeProblem],
    *,
    validation_references: Sequence[OverlapReference],
    project_test_references: Sequence[OverlapReference],
    external_eval_references: Sequence[OverlapReference],
    policy: RefreshDedupPolicy,
) -> list[CodeProblem]:
    """Exclude frozen SFT train records that overlap any evaluation reference."""
    train_problems = [problem for problem in problems if problem.split == "train"]
    fingerprints = [_selected_sft_fingerprint(problem, policy=policy) for problem in train_problems]
    rejected_ids: set[str] = set()
    for references in (validation_references, project_test_references, external_eval_references):
        reference_fingerprints = [reference_fingerprint(reference, policy=policy) for reference in references]
        rejected_ids.update(find_exact_duplicate_matches(fingerprints, reference_fingerprints))
        rejected_ids.update(find_near_duplicate_matches(fingerprints, reference_fingerprints, policy=policy))
    return [problem for problem in train_problems if problem.problem_id not in rejected_ids]


def _fingerprint_to_mapping(fingerprint: RefreshFingerprint) -> dict[str, JsonValue]:
    return {
        "record_id": fingerprint.record_id,
        "record_class": fingerprint.record_class,
        "normalized_statement_hash": fingerprint.normalized_statement_hash,
        "contract_hash": fingerprint.contract_hash,
        "source_url_hash": fingerprint.source_url_hash,
        "reference_solution_hash": fingerprint.reference_solution_hash,
        "test_fingerprint": fingerprint.test_fingerprint,
        "token_ngrams": list(fingerprint.token_ngrams),
    }


def _fingerprint_from_mapping(value: object) -> RefreshFingerprint:
    expected = {
        "record_id",
        "record_class",
        "normalized_statement_hash",
        "contract_hash",
        "source_url_hash",
        "reference_solution_hash",
        "test_fingerprint",
        "token_ngrams",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise RefreshDataError("stored refresh fingerprint has an invalid shape")
    record_class = value["record_class"]
    classes = {"candidate", "sft", "validation", "project_test", "external_eval"}
    if record_class not in classes:
        raise RefreshDataError("stored refresh fingerprint has an invalid record_class")
    token_ngrams = value["token_ngrams"]
    if not isinstance(token_ngrams, list) or any(not isinstance(item, str) for item in token_ngrams):
        raise RefreshDataError("stored refresh fingerprint token_ngrams must be a string list")
    for field in ("record_id", "normalized_statement_hash"):
        if not isinstance(value[field], str) or not cast(str, value[field]).strip():
            raise RefreshDataError("stored refresh fingerprint identity fields must be non-empty strings")
    for field in ("contract_hash", "source_url_hash", "reference_solution_hash", "test_fingerprint"):
        if value[field] is not None and not isinstance(value[field], str):
            raise RefreshDataError(f"stored refresh fingerprint {field} must be a string or null")
    return RefreshFingerprint(
        record_id=cast(str, value["record_id"]),
        record_class=cast(
            Literal["candidate", "sft", "validation", "project_test", "external_eval"],
            record_class,
        ),
        normalized_statement_hash=cast(str, value["normalized_statement_hash"]),
        contract_hash=cast(str | None, value["contract_hash"]),
        source_url_hash=cast(str | None, value["source_url_hash"]),
        reference_solution_hash=cast(str | None, value["reference_solution_hash"]),
        test_fingerprint=cast(str | None, value["test_fingerprint"]),
        token_ngrams=tuple(cast(list[str], token_ngrams)),
    )


def _decision_to_mapping(
    decision: RefreshDedupDecision,
    candidate: RefreshCandidate,
) -> dict[str, JsonValue]:
    if decision.candidate_id != candidate.candidate_id:
        raise RefreshDataError("dedup decision/candidate identity mismatch")
    return {
        "candidate_id": decision.candidate_id,
        "source_name": candidate.source_name,
        "source_record_id": candidate.source_record_id,
        "raw_record_sha256": candidate.raw_record_sha256,
        "retained": decision.retained,
        "rejection_reason": decision.rejection_reason,
        "overlap_class": decision.overlap_class,
        "matched_record_id": decision.matched_record_id,
        "similarity": decision.similarity,
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    validated = json_value_to_mutable(value, field_path=str(path))
    temporary: Path | None = None
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
            json.dump(
                validated,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _load_json(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RefreshDataError(f"could not read {path}: {error}") from error
    try:
        return loads_strict(text)
    except ValueError as error:
        raise RefreshDataError(f"invalid strict JSON in {path}: {error}") from error


def _check_exact_json_report(path: Path, expected: Mapping[str, JsonValue]) -> None:
    actual = _load_json(path)
    if not json_values_equal(actual, expected):
        raise RefreshDataError(f"{path.name} does not match recomputed refresh semantics")


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise RefreshDataError(f"could not read {path}: {error}") from error
    result: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = loads_strict(line)
        except ValueError as error:
            raise RefreshDataError(f"{path}, line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise RefreshDataError(f"{path}, line {line_number}: record must be an object")
        result.append(value)
    if not result:
        raise RefreshDataError(f"{path} contains no records")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_stats(path: Path) -> tuple[str, int]:
    """Return SHA256 and logical row count in one bounded-memory streaming pass."""
    digest = hashlib.sha256()
    if path.suffix == ".jsonl":
        rows = 0
        with path.open("rb") as handle:
            for line in handle:
                digest.update(line)
                if line.strip():
                    rows += 1
        return digest.hexdigest(), rows

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), 1


def _artifact_inventory(
    root: Path,
    *,
    precomputed_jsonl: Mapping[str, tuple[int, str]] | None = None,
) -> dict[str, JsonValue]:
    inventory: dict[str, JsonValue] = {}
    precomputed = {} if precomputed_jsonl is None else precomputed_jsonl
    for relative in _REQUIRED_ARTIFACTS:
        path = root / relative
        if not path.is_file():
            raise RefreshDataError(f"required refresh artifact is missing: {relative}")
        cached = precomputed.get(relative)
        if cached is None:
            digest, rows = _artifact_stats(path)
        else:
            rows, digest = cached
        inventory[relative] = {"sha256": digest, "rows": rows}
    return inventory


def _snapshot_mapping(snapshot: RefreshSourceSnapshot) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], json_value_to_mutable(asdict(snapshot), field_path="source snapshot"))


def _attach_selection_fingerprints(
    problems: Sequence[CodeProblem],
    selection: list[dict[str, JsonValue]],
    selected_external: Mapping[str, RefreshCandidate],
    *,
    policy: RefreshDedupPolicy,
    external_fingerprints: Mapping[str, RefreshFingerprint] | None = None,
) -> None:
    for problem, record in zip(problems, selection, strict=True):
        if record["overlap_origin"] == "sft_reuse":
            fingerprint = _selected_sft_fingerprint(problem, policy=policy)
        else:
            candidate = selected_external.get(problem.problem_id)
            if candidate is None:
                raise RefreshDataError(f"missing selected external candidate {problem.problem_id}")
            cached_fingerprint = (
                None if external_fingerprints is None else external_fingerprints.get(problem.problem_id)
            )
            fingerprint = (
                cached_fingerprint
                if cached_fingerprint is not None
                else candidate_fingerprint(candidate, policy=policy)
            )
        record["fingerprint"] = _fingerprint_to_mapping(fingerprint)


def _audit_selected_evaluation_overlap(
    selection: Sequence[dict[str, JsonValue]],
    reference_fingerprints: Mapping[str, Sequence[RefreshFingerprint]],
    *,
    policy: RefreshDedupPolicy,
    near_context: _NearIndexContext | None = None,
    selected_fingerprints: Sequence[RefreshFingerprint] | None = None,
) -> None:
    selected = (
        list(selected_fingerprints)
        if selected_fingerprints is not None
        else [_fingerprint_from_mapping(record["fingerprint"]) for record in selection]
    )
    if len(selected) != len(selection):
        raise RefreshDataError("selected fingerprint count does not match selection records")
    for reference_class in ("validation", "project_test", "external_eval"):
        references = reference_fingerprints[reference_class]
        exact = find_exact_duplicate_matches(selected, references)
        near = find_near_duplicate_matches(selected, references, policy=policy, context=near_context)
        if exact or near:
            raise RefreshDataError(
                f"selected refresh pool overlaps {reference_class}: exact={len(exact)}, near={len(near)}"
            )


def _audit_sft_overlap(
    selection: Sequence[dict[str, JsonValue]],
    sft_references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
    expected_count: int,
    hard_max: float,
    near_context: _NearIndexContext | None = None,
    selected_fingerprints: Sequence[RefreshFingerprint] | None = None,
) -> None:
    selected = (
        list(selected_fingerprints)
        if selected_fingerprints is not None
        else [_fingerprint_from_mapping(record["fingerprint"]) for record in selection]
    )
    if len(selected) != len(selection):
        raise RefreshDataError("selected fingerprint count does not match selection records")
    reuse: list[RefreshFingerprint] = []
    external: list[RefreshFingerprint] = []
    for record, fingerprint in zip(selection, selected, strict=True):
        if record["overlap_origin"] == "sft_reuse":
            reuse.append(fingerprint)
        elif record["overlap_origin"] == "external_new":
            external.append(fingerprint)
        else:
            raise RefreshDataError("selection overlap_origin must be sft_reuse or external_new")
    if len(reuse) != expected_count:
        raise RefreshDataError(f"SFT reuse count is {len(reuse)}, expected {expected_count}")
    exact_reuse = find_exact_duplicate_matches(reuse, sft_references)
    if len(exact_reuse) != len(reuse):
        raise RefreshDataError("every explicit SFT reuse record must exact-match the frozen SFT reference split")
    if find_exact_duplicate_matches(external, sft_references):
        raise RefreshDataError("external selected records contain exact incidental SFT overlap")
    if find_near_duplicate_matches(external, sft_references, policy=policy, context=near_context):
        raise RefreshDataError("external selected records contain accepted-near incidental SFT overlap")
    fraction = len(reuse) / len(selection)
    if fraction > hard_max:
        raise RefreshDataError(f"SFT overlap fraction {fraction:.6f} exceeds hard max {hard_max:.6f}")


def _build_reference_snapshot(
    reference_dataset_dir: Path,
    formal_problems: Sequence[CodeProblem],
    external_snapshot: RefreshSourceSnapshot,
    reference_sets: Mapping[str, Sequence[OverlapReference]],
    *,
    policy: RefreshDedupPolicy,
) -> dict[str, JsonValue]:
    canonical_path = reference_dataset_dir / "canonical" / "problems.jsonl"
    fingerprints = {
        name: [_fingerprint_to_mapping(reference_fingerprint(reference, policy=policy)) for reference in references]
        for name, references in reference_sets.items()
    }
    split_counts = {
        split: sum(problem.split == split for problem in formal_problems) for split in ("train", "validation", "test")
    }
    snapshot_value = {
        "schema_version": REFERENCE_SNAPSHOT_SCHEMA_VERSION,
        "formal": {"canonical_sha256": _sha256(canonical_path), "split_counts": split_counts},
        "external_eval_snapshot": _snapshot_mapping(external_snapshot),
        "fingerprints": fingerprints,
    }
    return cast(
        dict[str, JsonValue],
        json_value_to_mutable(snapshot_value, field_path="reference snapshot"),
    )


def _reference_fingerprints_from_snapshot(value: object) -> dict[str, list[RefreshFingerprint]]:
    expected_fields = {"schema_version", "formal", "external_eval_snapshot", "fingerprints"}
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("schema_version") != REFERENCE_SNAPSHOT_SCHEMA_VERSION
    ):
        raise RefreshDataError("reference snapshot schema/version is invalid")
    fingerprints = value.get("fingerprints")
    expected_classes = {"sft", "validation", "project_test", "external_eval"}
    if not isinstance(fingerprints, dict) or set(fingerprints) != expected_classes:
        raise RefreshDataError("reference snapshot fingerprint classes are invalid")
    result: dict[str, list[RefreshFingerprint]] = {}
    for name, records in fingerprints.items():
        if not isinstance(name, str) or not isinstance(records, list):
            raise RefreshDataError("reference snapshot fingerprints must be lists")
        result[name] = [_fingerprint_from_mapping(record) for record in records]
    return result


def _summary_from_manifest(dataset_dir: Path, manifest: Mapping[str, object]) -> RefreshPreparationSummary:
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        raise RefreshDataError("refresh manifest counts must be a mapping")
    required = {
        "total_candidates_scanned",
        "external_candidates_retained",
        "selected_problems",
        "sft_overlap_count",
        "sft_overlap_fraction",
        "quality_gate_required_count",
    }
    if set(counts) != required:
        raise RefreshDataError("refresh manifest count fields are invalid")
    integer_fields = (
        "total_candidates_scanned",
        "external_candidates_retained",
        "selected_problems",
        "sft_overlap_count",
        "quality_gate_required_count",
    )
    if any(isinstance(counts[field], bool) or not isinstance(counts[field], int) for field in integer_fields):
        raise RefreshDataError("refresh manifest integer counts are invalid")
    fraction = counts["sft_overlap_fraction"]
    if isinstance(fraction, bool) or not isinstance(fraction, int | float):
        raise RefreshDataError("refresh manifest sft_overlap_fraction is invalid")
    return RefreshPreparationSummary(
        total_candidates_scanned=cast(int, counts["total_candidates_scanned"]),
        external_candidates_retained=cast(int, counts["external_candidates_retained"]),
        selected_problems=cast(int, counts["selected_problems"]),
        sft_overlap_count=cast(int, counts["sft_overlap_count"]),
        sft_overlap_fraction=float(fraction),
        quality_gate_required_count=cast(int, counts["quality_gate_required_count"]),
        canonical_jsonl=dataset_dir / "canonical" / "problems.jsonl",
        public_grpo_jsonl=dataset_dir / "training" / "public_grpo.jsonl",
        hidden_grpo_jsonl=dataset_dir / "training" / "hidden_grpo.jsonl",
        root_manifest=dataset_dir / "refresh_manifest.json",
    )


def _check_artifact_hashes(dataset_dir: Path, manifest: Mapping[str, object]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(_REQUIRED_ARTIFACTS):
        raise RefreshDataError("refresh manifest artifact inventory is incomplete or contains unknown paths")
    expected_files = {Path(relative) for relative in _REQUIRED_ARTIFACTS} | {Path("refresh_manifest.json")}
    actual_files = {path.relative_to(dataset_dir) for path in dataset_dir.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise RefreshDataError(
            f"refresh artifact tree differs from exact contract; missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )
    for relative in _REQUIRED_ARTIFACTS:
        record = artifacts[relative]
        if not isinstance(record, Mapping) or set(record) != {"sha256", "rows"}:
            raise RefreshDataError(f"artifact inventory record for {relative} has an invalid shape")

    def collect_stats(relative: str) -> tuple[str, int]:
        return _artifact_stats(dataset_dir / relative)

    with ThreadPoolExecutor(max_workers=2) as pool:
        actual_stats = dict(zip(_REQUIRED_ARTIFACTS, pool.map(collect_stats, _REQUIRED_ARTIFACTS), strict=True))
    for relative in _REQUIRED_ARTIFACTS:
        record = cast(Mapping[str, object], artifacts[relative])
        actual_sha256, actual_rows = actual_stats[relative]
        if record["sha256"] != actual_sha256 or record["rows"] != actual_rows:
            raise RefreshDataError(f"artifact hash/row-count mismatch for {relative}")


def _check_training_views(problems: Sequence[CodeProblem], dataset_dir: Path) -> None:
    public_path = dataset_dir / "training" / "public_grpo.jsonl"
    hidden_path = dataset_dir / "training" / "hidden_grpo.jsonl"
    public = load_training_artifact(public_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden = load_training_artifact(hidden_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
    expected_public = [
        _build_training_record_unchecked(problem, kind=TrainingArtifactKind.PUBLIC_GRPO) for problem in problems
    ]
    expected_hidden = [
        _build_training_record_unchecked(problem, kind=TrainingArtifactKind.HIDDEN_GRPO) for problem in problems
    ]
    if len(public) != len(problems) or len(hidden) != len(problems):
        raise RefreshDataError("Public/Hidden training views must have the same row count as canonical")
    for index, (actual, expected) in enumerate(zip(public, expected_public, strict=True)):
        if not json_values_equal(actual, expected):
            raise RefreshDataError(f"Public GRPO row {index} does not match the canonical whitelist view")
    for index, (actual, expected) in enumerate(zip(hidden, expected_hidden, strict=True)):
        if not json_values_equal(actual, expected):
            raise RefreshDataError(f"Hidden GRPO row {index} does not match the canonical whitelist view")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.casefold())
    )


def _check_source_provenance(
    dataset_dir: Path,
    manifest: Mapping[str, object],
    *,
    production: bool,
) -> None:
    snapshots_value = _load_json(dataset_dir / "manifest" / "source_snapshots.json")
    if not isinstance(snapshots_value, list) or not snapshots_value:
        raise RefreshDataError("source_snapshots.json must contain a non-empty list")
    snapshot_fields = {
        "source_name",
        "dataset_id",
        "revision",
        "config_name",
        "split",
        "declared_license",
        "scanned_rows",
        "accepted_rows",
        "projection_fingerprint_sha256",
    }
    snapshots: list[Mapping[str, object]] = []
    for value in snapshots_value:
        if not isinstance(value, Mapping) or set(value) != snapshot_fields:
            raise RefreshDataError("source snapshot shape is invalid")
        for field in ("source_name", "dataset_id", "revision", "split", "declared_license"):
            if not isinstance(value[field], str) or not value[field].strip():
                raise RefreshDataError(f"source snapshot {field} is invalid")
        if value["config_name"] is not None and (
            not isinstance(value["config_name"], str) or not value["config_name"].strip()
        ):
            raise RefreshDataError("source snapshot config_name is invalid")
        scanned = value["scanned_rows"]
        accepted = value["accepted_rows"]
        if (
            isinstance(scanned, bool)
            or not isinstance(scanned, int)
            or scanned <= 0
            or isinstance(accepted, bool)
            or not isinstance(accepted, int)
            or accepted <= 0
            or accepted > scanned
        ):
            raise RefreshDataError("source snapshot row counts are invalid")
        if not _is_sha256(value["projection_fingerprint_sha256"]):
            raise RefreshDataError("source snapshot projection fingerprint is invalid")
        snapshots.append(value)
    names = [cast(str, snapshot["source_name"]) for snapshot in snapshots]
    if len(names) != len(set(names)):
        raise RefreshDataError("source snapshot identities must be unique")

    root_sources = manifest.get("sources")
    expected_root_sources = [
        {
            field: snapshot[field]
            for field in (
                "source_name",
                "dataset_id",
                "revision",
                "config_name",
                "split",
                "declared_license",
            )
        }
        | {"adapter": "deepcoder"}
        for snapshot in snapshots
    ]
    if root_sources != expected_root_sources:
        raise RefreshDataError("root source specifications do not match source snapshots")
    root_projections = manifest.get("source_projection_fingerprints")
    expected_projections = {
        cast(str, snapshot["source_name"]): snapshot["projection_fingerprint_sha256"] for snapshot in snapshots
    }
    if root_projections != expected_projections:
        raise RefreshDataError("root source projection fingerprints do not match source snapshots")

    if production:
        expected_snapshots = []
        for source in _WP9A_PRODUCTION_SOURCES:
            scanned, accepted, projection = _WP9A_PRODUCTION_SOURCE_SNAPSHOTS[source.source_name]
            expected_snapshots.append(
                _snapshot_mapping(
                    RefreshSourceSnapshot(
                        source_name=source.source_name,
                        dataset_id=source.dataset_id,
                        revision=source.revision,
                        config_name=source.config_name,
                        split=source.split,
                        declared_license=source.declared_license,
                        scanned_rows=scanned,
                        accepted_rows=accepted,
                        projection_fingerprint_sha256=projection,
                    )
                )
            )
        if snapshots_value != expected_snapshots:
            raise RefreshDataError("source snapshots do not match the frozen WP9-a production projections")


def _check_frozen_fingerprint_inventory(
    fingerprints: Sequence[RefreshFingerprint],
    *,
    expected_count: int,
    expected_sha256: str,
    label: str,
) -> None:
    inventory_sha256 = stable_json_hash([_fingerprint_to_mapping(fingerprint) for fingerprint in fingerprints])
    if len(fingerprints) != expected_count or inventory_sha256 != expected_sha256:
        raise RefreshDataError(f"{label} fingerprints do not match the frozen inventory")


def check_refresh_data(
    dataset_dir: Path,
    *,
    reference_dataset_dir: Path,
    allow_test_protocol: bool = False,
) -> RefreshPreparationSummary:
    """Strictly reload and recompute every deterministic WP9-a artifact invariant."""
    manifest_value = _load_json(dataset_dir / "refresh_manifest.json")
    if not isinstance(manifest_value, dict):
        raise RefreshDataError("refresh_manifest.json must contain an object")
    manifest = cast(dict[str, object], manifest_value)
    schema_version = manifest.get("schema_version")
    if schema_version == REFRESH_SCHEMA_VERSION:
        production = True
    elif schema_version == REFRESH_TEST_SCHEMA_VERSION and allow_test_protocol:
        production = False
    else:
        raise RefreshDataError("refresh manifest schema_version is invalid")
    _check_artifact_hashes(dataset_dir, manifest)
    _check_source_provenance(dataset_dir, manifest, production=production)

    policy_value = manifest.get("dedup_policy")
    if not isinstance(policy_value, Mapping) or set(policy_value) != {
        "token_ngram_size",
        "near_jaccard_threshold",
    }:
        raise RefreshDataError("refresh manifest dedup_policy is invalid")
    token_ngram_size = policy_value["token_ngram_size"]
    threshold = policy_value["near_jaccard_threshold"]
    if isinstance(token_ngram_size, bool) or not isinstance(token_ngram_size, int):
        raise RefreshDataError("refresh manifest token_ngram_size is invalid")
    if isinstance(threshold, bool) or not isinstance(threshold, int | float):
        raise RefreshDataError("refresh manifest near_jaccard_threshold is invalid")
    policy = RefreshDedupPolicy(
        token_ngram_size=token_ngram_size,
        near_jaccard_threshold=float(threshold),
    )
    validate_refresh_dedup_policy(policy)

    selection_protocol = manifest.get("selection_protocol")
    expected_protocol_fields = {
        "target_size",
        "sft_overlap_fraction",
        "sft_overlap_hard_max",
        "sft_overlap_count",
        "external_new_count",
        "sft_namespace",
        "external_namespace",
        "order_namespace",
    }
    if not isinstance(selection_protocol, Mapping) or set(selection_protocol) != expected_protocol_fields:
        raise RefreshDataError("refresh manifest selection_protocol is invalid")
    target_size = selection_protocol.get("target_size")
    overlap_fraction = selection_protocol.get("sft_overlap_fraction")
    expected_overlap_count = selection_protocol.get("sft_overlap_count")
    expected_external_count = selection_protocol.get("external_new_count")
    hard_max = selection_protocol.get("sft_overlap_hard_max")
    if isinstance(target_size, bool) or not isinstance(target_size, int) or target_size <= 0:
        raise RefreshDataError("refresh manifest target_size is invalid")
    if isinstance(overlap_fraction, bool) or not isinstance(overlap_fraction, int | float):
        raise RefreshDataError("refresh manifest sft_overlap_fraction is invalid")
    if isinstance(expected_overlap_count, bool) or not isinstance(expected_overlap_count, int):
        raise RefreshDataError("refresh manifest sft_overlap_count is invalid")
    if isinstance(expected_external_count, bool) or not isinstance(expected_external_count, int):
        raise RefreshDataError("refresh manifest external_new_count is invalid")
    if isinstance(hard_max, bool) or not isinstance(hard_max, int | float):
        raise RefreshDataError("refresh manifest sft_overlap_hard_max is invalid")
    hard_max_value = float(hard_max)
    overlap_fraction_value = float(overlap_fraction)
    if hard_max_value > _WP9A_SFT_OVERLAP_HARD_MAX:
        raise RefreshDataError(
            f"refresh manifest SFT overlap hard max exceeds frozen {_WP9A_SFT_OVERLAP_HARD_MAX:.2f} ceiling"
        )
    if overlap_fraction_value > _WP9A_SFT_OVERLAP_HARD_MAX:
        raise RefreshDataError(
            f"refresh manifest configured SFT overlap exceeds frozen {_WP9A_SFT_OVERLAP_HARD_MAX:.2f} ceiling"
        )
    if overlap_fraction_value > hard_max_value:
        raise RefreshDataError("refresh manifest configured SFT overlap exceeds its hard max")
    if selection_protocol.get("sft_namespace") != "wp9a-sft-reuse-v1":
        raise RefreshDataError("refresh manifest sft selection namespace is invalid")
    if selection_protocol.get("external_namespace") != "wp9a-external-new-v1":
        raise RefreshDataError("refresh manifest external selection namespace is invalid")
    if selection_protocol.get("order_namespace") != "wp9a-problem-order-v1":
        raise RefreshDataError("refresh manifest problem-order namespace is invalid")
    if expected_overlap_count != int(round(target_size * float(overlap_fraction))):
        raise RefreshDataError("refresh manifest SFT overlap count is inconsistent with configured fraction")
    if expected_external_count != target_size - expected_overlap_count:
        raise RefreshDataError("refresh manifest external-new count is inconsistent")
    if production and (
        target_size != _WP9A_PRODUCTION_TARGET_SIZE
        or not math.isclose(
            overlap_fraction_value,
            _WP9A_PRODUCTION_SFT_OVERLAP_FRACTION,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        or not math.isclose(hard_max_value, _WP9A_SFT_OVERLAP_HARD_MAX, rel_tol=0.0, abs_tol=1e-12)
        or expected_overlap_count != 750
        or expected_external_count != 9_250
    ):
        raise RefreshDataError("refresh manifest does not match the frozen WP9-a production pool protocol")

    reference_snapshot = _load_json(dataset_dir / "manifest" / "reference_snapshots.json")
    if not isinstance(reference_snapshot, dict):
        raise RefreshDataError("reference_snapshots.json must contain an object")
    reference_fingerprints = _reference_fingerprints_from_snapshot(reference_snapshot)

    formal = reference_snapshot.get("formal")
    if not isinstance(formal, Mapping) or set(formal) != {"canonical_sha256", "split_counts"}:
        raise RefreshDataError("reference snapshot formal identity is invalid")
    reference_canonical = reference_dataset_dir / "canonical" / "problems.jsonl"
    actual_formal_sha256 = _sha256(reference_canonical)
    if formal.get("canonical_sha256") != actual_formal_sha256:
        raise RefreshDataError("frozen formal reference canonical SHA256 does not match refresh provenance")
    if manifest.get("formal_reference_canonical_sha256") != actual_formal_sha256:
        raise RefreshDataError(
            "root manifest formal reference canonical SHA256 does not match authoritative reference"
        )
    try:
        formal_problems = load_canonical_jsonl(reference_canonical)
    except DataPreparationError as error:
        raise RefreshDataError(f"formal reference dataset is invalid: {error}") from error
    actual_split_counts = {
        split: sum(problem.split == split for problem in formal_problems) for split in ("train", "validation", "test")
    }
    split_counts = formal.get("split_counts")
    if (
        not isinstance(split_counts, Mapping)
        or set(split_counts) != {"train", "validation", "test"}
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in split_counts.values())
        or dict(split_counts) != actual_split_counts
    ):
        raise RefreshDataError("reference snapshot formal split_counts do not match authoritative reference canonical")
    sft_references, validation_references, project_test_references = _reference_sets(formal_problems)
    rebuilt_formal_references = {
        "sft": sft_references,
        "validation": validation_references,
        "project_test": project_test_references,
    }
    for reference_class, references in rebuilt_formal_references.items():
        rebuilt = [reference_fingerprint(reference, policy=policy) for reference in references]
        if reference_fingerprints[reference_class] != rebuilt:
            raise RefreshDataError(
                f"reference snapshot {reference_class} fingerprints do not match authoritative formal canonical"
            )
        reference_fingerprints[reference_class] = rebuilt

    external_snapshot = reference_snapshot.get("external_eval_snapshot")
    expected_external_snapshot_fields = {
        "source_name",
        "dataset_id",
        "revision",
        "config_name",
        "split",
        "declared_license",
        "scanned_rows",
        "accepted_rows",
        "projection_fingerprint_sha256",
    }
    if not isinstance(external_snapshot, Mapping) or set(external_snapshot) != expected_external_snapshot_fields:
        raise RefreshDataError("reference snapshot external-eval identity is invalid")
    external_count = len(reference_fingerprints["external_eval"])
    if (
        external_snapshot.get("source_name") != "humanevalplus"
        or external_snapshot.get("dataset_id") != _WP9A_EXTERNAL_EVAL_DATASET_ID
        or external_snapshot.get("revision") != _WP9A_EXTERNAL_EVAL_REVISION
        or external_snapshot.get("config_name") is not None
        or external_snapshot.get("split") != "test"
        or external_snapshot.get("declared_license") != _WP9A_EXTERNAL_EVAL_LICENSE
        or external_snapshot.get("scanned_rows") != external_count
        or external_snapshot.get("accepted_rows") != external_count
        or external_count <= 0
    ):
        raise RefreshDataError("reference snapshot external-eval contract is invalid")
    external_projection = external_snapshot.get("projection_fingerprint_sha256")
    if not _is_sha256(external_projection):
        raise RefreshDataError("reference snapshot external-eval projection fingerprint is invalid")
    if production:
        if external_projection != _WP9A_EXTERNAL_EVAL_PROJECTION_SHA256:
            raise RefreshDataError("external-eval projection does not match frozen HumanEvalPlus provenance")
        _check_frozen_fingerprint_inventory(
            reference_fingerprints["external_eval"],
            expected_count=_WP9A_EXTERNAL_EVAL_COUNT,
            expected_sha256=_WP9A_EXTERNAL_EVAL_INVENTORY_SHA256,
            label="external-eval",
        )
    root_external = manifest.get("external_eval")
    if not isinstance(root_external, Mapping) or set(root_external) != {
        "dataset_id",
        "revision",
        "projection_fingerprint_sha256",
    }:
        raise RefreshDataError("root manifest external_eval identity is invalid")
    if (
        root_external.get("dataset_id") != _WP9A_EXTERNAL_EVAL_DATASET_ID
        or root_external.get("revision") != _WP9A_EXTERNAL_EVAL_REVISION
        or root_external.get("projection_fingerprint_sha256") != external_projection
    ):
        raise RefreshDataError("root manifest external_eval identity does not match reference snapshot")

    problems = load_canonical_jsonl(dataset_dir / "canonical" / "problems.jsonl")
    if len(problems) != target_size or any(problem.split != "train" for problem in problems):
        raise RefreshDataError("refresh canonical must contain exactly target_size train problems")
    ids = [problem.problem_id for problem in problems]
    if len(ids) != len(set(ids)):
        raise RefreshDataError("refresh canonical contains duplicate problem IDs")

    selection_records = _load_jsonl(dataset_dir / "manifest" / "selection.jsonl")
    if [record.get("problem_id") for record in selection_records] != ids:
        raise RefreshDataError("selection manifest problem IDs/order do not match canonical")
    order_records = _load_jsonl(dataset_dir / "manifest" / "problem_order.jsonl")
    if [record.get("problem_id") for record in order_records] != ids:
        raise RefreshDataError("problem_order IDs do not match canonical order")
    if [record.get("ordinal") for record in order_records] != list(range(len(ids))):
        raise RefreshDataError("problem_order ordinals are not contiguous from zero")
    if manifest.get("selected_ids_order_sha256") != stable_json_hash(ids):
        raise RefreshDataError("selected problem order hash does not match canonical order")

    _check_training_views(problems, dataset_dir)
    typed_selection = cast(list[dict[str, JsonValue]], selection_records)
    selected_fingerprints: list[RefreshFingerprint] = []
    quality_count = 0
    overlap_count = 0
    for problem, record in zip(problems, typed_selection, strict=True):
        quality_required = _quality_gate_required(problem)
        recorded_quality = record.get("quality_gate_required")
        if not isinstance(recorded_quality, bool) or recorded_quality != quality_required:
            raise RefreshDataError("selection quality_gate_required does not match canonical test count")
        quality_count += int(quality_required)
        overlap_count += int(record.get("overlap_origin") == "sft_reuse")
        selected_fingerprints.append(_canonical_selection_fingerprint(problem, record, policy=policy))
    actual_overlap_fraction = overlap_count / len(problems)
    if actual_overlap_fraction > _WP9A_SFT_OVERLAP_HARD_MAX:
        raise RefreshDataError(
            f"actual selected SFT overlap {actual_overlap_fraction:.6f} exceeds frozen "
            f"{_WP9A_SFT_OVERLAP_HARD_MAX:.2f} ceiling"
        )
    if overlap_count != expected_overlap_count:
        raise RefreshDataError("selection SFT overlap count does not match selection protocol")
    if len(problems) - overlap_count != expected_external_count:
        raise RefreshDataError("selection external-new count does not match selection protocol")

    all_reference_fingerprints = [
        fingerprint
        for reference_class in ("sft", "validation", "project_test", "external_eval")
        for fingerprint in reference_fingerprints[reference_class]
    ]
    near_context = _build_near_index_context(
        [*selected_fingerprints, *all_reference_fingerprints],
        threshold=policy.near_jaccard_threshold,
    )
    _audit_selected_evaluation_overlap(
        typed_selection,
        reference_fingerprints,
        policy=policy,
        near_context=near_context,
        selected_fingerprints=selected_fingerprints,
    )
    _audit_sft_overlap(
        typed_selection,
        reference_fingerprints["sft"],
        policy=policy,
        expected_count=expected_overlap_count,
        hard_max=float(hard_max),
        near_context=near_context,
        selected_fingerprints=selected_fingerprints,
    )
    _check_exact_json_report(
        dataset_dir / "reports" / "sft_overlap.json",
        {
            "selected_problems": len(problems),
            "sft_overlap_count": overlap_count,
            "sft_overlap_fraction": overlap_count / len(problems),
            "sft_overlap_hard_max": float(hard_max),
            "external_new_count": len(problems) - overlap_count,
            "status": "passed",
        },
    )
    _check_exact_json_report(
        dataset_dir / "reports" / "evaluation_overlap.json",
        {
            "validation_exact_or_near_overlap": 0,
            "project_test_exact_or_near_overlap": 0,
            "external_eval_exact_or_near_overlap": 0,
            "status": "passed",
        },
    )
    _check_exact_json_report(
        dataset_dir / "reports" / "test_layer_leakage.json",
        {
            "checked_problems": len(problems),
            "quality_gate_required_count": quality_count,
            "cross_layer_duplicate_count": 0,
            "public_contains_train_hidden": False,
            "public_or_hidden_contains_eval_hidden": False,
            "status": "passed",
        },
    )
    summary = _summary_from_manifest(dataset_dir, manifest)
    if summary.selected_problems != len(problems):
        raise RefreshDataError("refresh manifest selected_problems does not match canonical")
    if summary.sft_overlap_count != expected_overlap_count:
        raise RefreshDataError("refresh manifest SFT overlap count does not match selection protocol")
    if summary.quality_gate_required_count != quality_count:
        raise RefreshDataError("refresh manifest quality-gate count does not match selection manifest")
    if not math.isclose(
        summary.sft_overlap_fraction,
        expected_overlap_count / target_size,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise RefreshDataError("refresh manifest SFT overlap fraction is inconsistent")
    return summary


def _load_refresh_source_projections(
    sources: Sequence[RefreshSourceSpec],
    *,
    cache_dir: Path | None,
) -> list[tuple[RefreshSourceSnapshot, list[RefreshCandidate]]]:
    """Load independent pinned source projections concurrently while preserving tracked source order."""
    if len(sources) <= 1:
        return [load_refresh_source(source, cache_dir=cache_dir) for source in sources]

    def load_one(source: RefreshSourceSpec) -> tuple[RefreshSourceSnapshot, list[RefreshCandidate]]:
        return load_refresh_source(source, cache_dir=cache_dir)

    with ThreadPoolExecutor(max_workers=min(4, len(sources))) as pool:
        return list(pool.map(load_one, sources))


def prepare_refresh_data(
    config: RefreshDataConfig,
    *,
    seed: int,
    reference_dataset_dir: Path,
    source_cache_dir: Path | None,
    output_dir: Path,
) -> RefreshPreparationSummary:
    """Build the complete WP9-a artifact tree and publish it atomically after strict readback."""
    _validate_selection_config(config.selection)
    production = _is_production_config(config)
    if output_dir.exists():
        raise RefreshDataError(f"refresh output directory must not already exist: {output_dir}")
    try:
        formal_problems = load_canonical_jsonl(reference_dataset_dir / "canonical" / "problems.jsonl")
    except DataPreparationError as error:
        raise RefreshDataError(f"formal reference dataset is invalid: {error}") from error
    present_splits = {problem.split for problem in formal_problems}
    missing_splits = {"train", "validation", "test"} - present_splits
    if missing_splits:
        raise RefreshDataError(
            f"formal reference canonical is missing required split(s): {', '.join(sorted(missing_splits))}"
        )
    sft_references, validation_references, project_test_references = _reference_sets(formal_problems)
    policy = RefreshDedupPolicy(
        config.selection.token_ngram_size,
        config.selection.near_jaccard_threshold,
    )
    external_snapshot, external_eval_references = load_humanevalplus_references(
        dataset_id=config.external_eval_dataset_id,
        revision=config.external_eval_revision,
        cache_dir=source_cache_dir,
    )
    source_snapshots: list[RefreshSourceSnapshot] = []
    all_candidates: list[RefreshCandidate] = []
    for snapshot, candidates in _load_refresh_source_projections(config.sources, cache_dir=source_cache_dir):
        source_snapshots.append(snapshot)
        all_candidates.extend(candidates)
    del candidates
    if len({candidate.candidate_id for candidate in all_candidates}) != len(all_candidates):
        raise RefreshDataError("source ingestion produced duplicate candidate IDs")
    candidate_by_id = {candidate.candidate_id: candidate for candidate in all_candidates}
    candidate_fingerprints = [candidate_fingerprint(candidate, policy=policy) for candidate in all_candidates]
    candidate_fingerprint_by_id = {fingerprint.record_id: fingerprint for fingerprint in candidate_fingerprints}
    decisions = classify_refresh_candidates(
        all_candidates,
        sft_references=sft_references,
        validation_references=validation_references,
        project_test_references=project_test_references,
        external_eval_references=external_eval_references,
        policy=policy,
        candidate_fingerprints=candidate_fingerprints,
    )
    retained_ids = {decision.candidate_id for decision in decisions if decision.retained}
    retained_candidates = [candidate for candidate in all_candidates if candidate.candidate_id in retained_ids]
    sft_problems = _eligible_sft_reuse_problems(
        formal_problems,
        validation_references=validation_references,
        project_test_references=project_test_references,
        external_eval_references=external_eval_references,
        policy=policy,
    )
    problems, selection = select_refresh_pool(
        sft_problems=sft_problems,
        new_candidates=retained_candidates,
        config=config.selection,
        seed=seed,
    )
    selected_external_ids = {
        cast(str, record["problem_id"]) for record in selection if record["overlap_origin"] == "external_new"
    }
    selected_external = {
        candidate.candidate_id: candidate
        for candidate in retained_candidates
        if candidate.candidate_id in selected_external_ids
    }
    _attach_selection_fingerprints(
        problems,
        selection,
        selected_external,
        policy=policy,
        external_fingerprints=candidate_fingerprint_by_id,
    )
    reference_sets: dict[str, Sequence[OverlapReference]] = {
        "sft": sft_references,
        "validation": validation_references,
        "project_test": project_test_references,
        "external_eval": external_eval_references,
    }
    reference_snapshot = _build_reference_snapshot(
        reference_dataset_dir,
        formal_problems,
        external_snapshot,
        reference_sets,
        policy=policy,
    )
    overlap_count = int(round(config.selection.target_size * config.selection.sft_overlap_fraction))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        _write_json(
            temporary / "manifest" / "source_snapshots.json",
            [_snapshot_mapping(item) for item in source_snapshots],
        )
        _write_json(temporary / "manifest" / "reference_snapshots.json", reference_snapshot)
        precomputed_jsonl: dict[str, tuple[int, str]] = {}
        precomputed_jsonl["manifest/dedup_decisions.jsonl"] = write_jsonl_with_stats(
            (_decision_to_mapping(decision, candidate_by_id[decision.candidate_id]) for decision in decisions),
            temporary / "manifest" / "dedup_decisions.jsonl",
            validate_records=False,
        )
        precomputed_jsonl["manifest/selection.jsonl"] = write_jsonl_with_stats(
            selection,
            temporary / "manifest" / "selection.jsonl",
            validate_records=False,
        )
        precomputed_jsonl["manifest/problem_order.jsonl"] = write_jsonl_with_stats(
            ({"ordinal": index, "problem_id": problem.problem_id} for index, problem in enumerate(problems)),
            temporary / "manifest" / "problem_order.jsonl",
            validate_records=False,
        )
        precomputed_jsonl["canonical/problems.jsonl"] = write_jsonl_with_stats(
            (problem_to_mapping(problem) for problem in problems),
            temporary / "canonical" / "problems.jsonl",
            validate_records=False,
        )
        precomputed_jsonl["training/public_grpo.jsonl"] = write_jsonl_with_stats(
            (_build_training_record_unchecked(problem, kind=TrainingArtifactKind.PUBLIC_GRPO) for problem in problems),
            temporary / "training" / "public_grpo.jsonl",
            validate_records=False,
        )
        precomputed_jsonl["training/hidden_grpo.jsonl"] = write_jsonl_with_stats(
            (_build_training_record_unchecked(problem, kind=TrainingArtifactKind.HIDDEN_GRPO) for problem in problems),
            temporary / "training" / "hidden_grpo.jsonl",
            validate_records=False,
        )
        rejection_counts = Counter(decision.rejection_reason for decision in decisions if not decision.retained)
        _write_json(
            temporary / "reports" / "dedup_summary.json",
            {
                "total_source_rows_scanned": sum(snapshot.scanned_rows for snapshot in source_snapshots),
                "adapter_accepted_candidates": len(all_candidates),
                "dedup_retained_candidates": len(retained_candidates),
                "source_adapter_rejected_rows": {
                    snapshot.source_name: snapshot.scanned_rows - snapshot.accepted_rows
                    for snapshot in source_snapshots
                },
                "dedup_rejection_counts": {
                    str(reason): count
                    for reason, count in sorted(rejection_counts.items(), key=lambda item: str(item[0]))
                },
            },
        )
        actual_fraction = overlap_count / len(problems)
        _write_json(
            temporary / "reports" / "sft_overlap.json",
            {
                "selected_problems": len(problems),
                "sft_overlap_count": overlap_count,
                "sft_overlap_fraction": actual_fraction,
                "sft_overlap_hard_max": config.selection.sft_overlap_hard_max,
                "external_new_count": len(problems) - overlap_count,
                "status": "passed",
            },
        )
        _write_json(
            temporary / "reports" / "evaluation_overlap.json",
            {
                "validation_exact_or_near_overlap": 0,
                "project_test_exact_or_near_overlap": 0,
                "external_eval_exact_or_near_overlap": 0,
                "status": "passed",
            },
        )
        quality_count = sum(record["quality_gate_required"] is True for record in selection)
        _write_json(
            temporary / "reports" / "test_layer_leakage.json",
            {
                "checked_problems": len(problems),
                "quality_gate_required_count": quality_count,
                "cross_layer_duplicate_count": 0,
                "public_contains_train_hidden": False,
                "public_or_hidden_contains_eval_hidden": False,
                "status": "passed",
            },
        )
        artifacts = _artifact_inventory(temporary, precomputed_jsonl=precomputed_jsonl)
        root_manifest: dict[str, JsonValue] = {
            "schema_version": REFRESH_SCHEMA_VERSION if production else REFRESH_TEST_SCHEMA_VERSION,
            "seed": seed,
            "sources": [
                cast(dict[str, JsonValue], json_value_to_mutable(asdict(source), field_path="source"))
                for source in config.sources
            ],
            "source_projection_fingerprints": {
                snapshot.source_name: snapshot.projection_fingerprint_sha256 for snapshot in source_snapshots
            },
            "formal_reference_canonical_sha256": _sha256(reference_dataset_dir / "canonical" / "problems.jsonl"),
            "external_eval": {
                "dataset_id": config.external_eval_dataset_id,
                "revision": config.external_eval_revision,
                "projection_fingerprint_sha256": external_snapshot.projection_fingerprint_sha256,
            },
        }
        root_manifest["dedup_policy"] = cast(
            dict[str, JsonValue],
            json_value_to_mutable(asdict(policy), field_path="dedup policy"),
        )
        root_manifest["selection_protocol"] = {
            "target_size": config.selection.target_size,
            "sft_overlap_fraction": config.selection.sft_overlap_fraction,
            "sft_overlap_hard_max": config.selection.sft_overlap_hard_max,
            "sft_overlap_count": overlap_count,
            "external_new_count": config.selection.target_size - overlap_count,
            "sft_namespace": "wp9a-sft-reuse-v1",
            "external_namespace": "wp9a-external-new-v1",
            "order_namespace": "wp9a-problem-order-v1",
        }
        root_manifest["artifacts"] = artifacts
        root_manifest["selected_ids_order_sha256"] = stable_json_hash([problem.problem_id for problem in problems])
        root_manifest["counts"] = {
            "total_candidates_scanned": sum(snapshot.scanned_rows for snapshot in source_snapshots),
            "external_candidates_retained": len(retained_candidates),
            "selected_problems": len(problems),
            "sft_overlap_count": overlap_count,
            "sft_overlap_fraction": actual_fraction,
            "quality_gate_required_count": quality_count,
        }
        _write_json(temporary / "refresh_manifest.json", root_manifest)

        # Strict readback reloads the multi-gigabyte canonical/training artifacts. Release
        # construction-only objects first so the validation pass does not duplicate the
        # full candidate/test payload in memory on the control-plane machine.
        del all_candidates
        del candidate_by_id
        del candidate_fingerprints
        del candidate_fingerprint_by_id
        del decisions
        del retained_candidates
        del sft_problems
        del problems
        del selection
        del selected_external
        del reference_snapshot
        del reference_sets
        del sft_references
        del validation_references
        del project_test_references
        del external_eval_references
        del formal_problems
        gc.collect()

        check_refresh_data(
            temporary,
            reference_dataset_dir=reference_dataset_dir,
            allow_test_protocol=not production,
        )
        os.replace(temporary, output_dir)
        return _summary_from_manifest(output_dir, root_manifest)
    except Exception as error:
        shutil.rmtree(temporary, ignore_errors=True)
        if isinstance(error, RefreshDataError):
            raise
        raise RefreshDataError(f"refresh data preparation failed: {error}") from error
