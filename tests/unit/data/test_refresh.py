"""Tests for WP9-a refresh selection, materialization, manifests, and strict readback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import code_verifier.data.refresh as refresh_module
from code_verifier.config import ConfigError
from code_verifier.data.prepare import write_jsonl
from code_verifier.data.refresh import (
    RefreshDataConfig,
    RefreshDataError,
    RefreshSelectionConfig,
    deterministic_stratified_select,
    load_refresh_data_config,
    prepare_refresh_data,
    refresh_data_config_from_mapping,
    select_refresh_pool,
)
from code_verifier.data.refresh_sources import (
    OverlapReference,
    RefreshCandidate,
    RefreshSourceSnapshot,
    RefreshSourceSpec,
)
from code_verifier.data.schema import CodeProblem, ProblemMetadata, problem_to_mapping
from code_verifier.data.schema import TestCase as CodeTestCase

HUMANEVAL_DATASET_ID = "evalplus/humanevalplus"
HUMANEVAL_REVISION = "aa0d916268b1c17e84e881e9bd460508dd2fd308"


def _metadata(*, difficulty: str = "easy") -> ProblemMetadata:
    return ProblemMetadata(
        difficulty=cast(object, difficulty),  # type: ignore[arg-type]
        category=("fixture",),
        time_limit_seconds=1.0,
        memory_limit_mb=128,
        license="MIT",
        source_url_hash=None,
    )


def _problem(problem_id: str, split: str, *, source: str = "formal", difficulty: str = "easy") -> CodeProblem:
    tests = tuple(CodeTestCase(input=[index], expected=f"{problem_id}:{index}") for index in range(6))
    return CodeProblem(
        problem_id=problem_id,
        source=source,
        split=cast(object, split),  # type: ignore[arg-type]
        prompt=f"Formal fixture statement for {problem_id} with unique stable wording.",
        function_name="identity",
        function_signature="def identity(value: int) -> int:",
        starter_code=None,
        visible_tests=tests[:2],
        train_hidden_tests=tests[2:4],
        eval_hidden_tests=tests[4:],
        reference_solution=f"def identity(value): return value  # {problem_id}",
        sft_response=f"def identity(value): return value  # {problem_id}" if split == "train" else None,
        metadata=_metadata(difficulty=difficulty),
    )


def _candidate(candidate_id: str, *, source: str = "source-a", difficulty: str = "unknown") -> RefreshCandidate:
    return RefreshCandidate(
        candidate_id=candidate_id,
        source_name=source,
        source_record_id=f"{source}/train/{candidate_id}",
        prompt=(
            f"External task {candidate_id}: transform a complete input text using a distinct deterministic rule "
            f"specific only to identifier {candidate_id}."
        ),
        function_name="solve_io",
        function_signature="def solve_io(input_text: str) -> str:",
        tests=tuple(
            CodeTestCase(input=f"{candidate_id}-input-{index}\n", expected=f"{candidate_id}-output-{index}\n")
            for index in range(8)
        ),
        source_url_hash=None,
        raw_reference_solution_hash=None,
        difficulty=cast(object, difficulty),  # type: ignore[arg-type]
        category=("stdio",),
        raw_record_sha256=(candidate_id.encode().hex() + "0" * 64)[:64],
    )


def _selection_config(*, target_size: int = 8) -> RefreshSelectionConfig:
    return RefreshSelectionConfig(
        target_size=target_size,
        sft_overlap_fraction=0.125,
        sft_overlap_hard_max=0.15,
        token_ngram_size=5,
        near_jaccard_threshold=0.90,
    )


def _source_spec() -> RefreshSourceSpec:
    return RefreshSourceSpec(
        source_name="source-a",
        dataset_id="fixture/deepcoder",
        revision="1" * 40,
        config_name="primeintellect",
        split="train",
        declared_license="MIT",
        adapter="deepcoder",
    )


def _data_config(*, target_size: int = 8) -> RefreshDataConfig:
    return RefreshDataConfig(
        sources=(_source_spec(),),
        external_eval_dataset_id=HUMANEVAL_DATASET_ID,
        external_eval_revision=HUMANEVAL_REVISION,
        selection=_selection_config(target_size=target_size),
    )


def _write_reference_dataset(path: Path) -> list[CodeProblem]:
    problems = [
        _problem("train-a", "train", difficulty="easy"),
        _problem("train-b", "train", difficulty="hard"),
        _problem("train-c", "train", difficulty="medium"),
        _problem("validation-a", "validation"),
        _problem("test-a", "test"),
    ]
    write_jsonl((problem_to_mapping(problem) for problem in problems), path / "canonical" / "problems.jsonl")
    return problems


def _fake_source_snapshot(candidate_count: int) -> RefreshSourceSnapshot:
    return RefreshSourceSnapshot(
        source_name="source-a",
        dataset_id="fixture/deepcoder",
        revision="1" * 40,
        config_name="primeintellect",
        split="train",
        declared_license="MIT",
        scanned_rows=candidate_count,
        accepted_rows=candidate_count,
        projection_fingerprint_sha256="a" * 64,
    )


def _fake_external_snapshot() -> RefreshSourceSnapshot:
    return RefreshSourceSnapshot(
        source_name="humanevalplus",
        dataset_id=HUMANEVAL_DATASET_ID,
        revision=HUMANEVAL_REVISION,
        config_name=None,
        split="test",
        declared_license="Apache-2.0",
        scanned_rows=1,
        accepted_rows=1,
        projection_fingerprint_sha256="b" * 64,
    )


def _patch_pipeline_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidates: list[RefreshCandidate],
) -> None:
    monkeypatch.setattr(
        refresh_module,
        "load_refresh_source",
        lambda spec, cache_dir: (_fake_source_snapshot(len(candidates)), list(candidates)),
    )
    monkeypatch.setattr(
        refresh_module,
        "load_humanevalplus_references",
        lambda dataset_id, revision, cache_dir: (
            _fake_external_snapshot(),
            [
                OverlapReference(
                    reference_id="external-eval-1",
                    reference_class="external_eval",
                    prompt="Completely unrelated external evaluation function with unique reference wording.",
                    function_signature="def external_eval(value: int) -> int:",
                    source_url_hash=None,
                    reference_solution_hash=None,
                    test_fingerprint=None,
                )
            ],
        ),
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_refresh_config_loads_exact_tracked_shape_and_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "refresh.yaml"
    path.write_text(
        "\n".join(
            [
                "version: wp9a-refresh-v1",
                "sources:",
                "  - source_name: source-a",
                "    dataset_id: fixture/deepcoder",
                f'    revision: "{"1" * 40}"',
                "    config_name: primeintellect",
                "    split: train",
                "    declared_license: MIT",
                "    adapter: deepcoder",
                "external_eval:",
                f"  dataset_id: {HUMANEVAL_DATASET_ID}",
                f'  revision: "{HUMANEVAL_REVISION}"',
                "selection:",
                "  target_size: 10000",
                "  sft_overlap_fraction: 0.075",
                "  sft_overlap_hard_max: 0.15",
                "  token_ngram_size: 5",
                "  near_jaccard_threshold: 0.90",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config = load_refresh_data_config(path)
    assert config.selection.target_size == 10000
    assert config.selection.sft_overlap_fraction == 0.075
    assert config.sources[0].revision == "1" * 40

    path.write_text(path.read_text(encoding="utf-8") + "unknown: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown"):
        load_refresh_data_config(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("token_ngram_size", 1), ("near_jaccard_threshold", 1.0)],
)
def test_refresh_config_rejects_wp9a_dedup_protocol_variants(
    tmp_path: Path,
    field: str,
    value: int | float,
) -> None:
    selection: dict[str, object] = {
        "target_size": 10000,
        "sft_overlap_fraction": 0.075,
        "sft_overlap_hard_max": 0.15,
        "token_ngram_size": 5,
        "near_jaccard_threshold": 0.90,
    }
    selection[field] = value
    config: dict[str, object] = {
        "version": "wp9a-refresh-v1",
        "sources": [
            {
                "source_name": "source-a",
                "dataset_id": "fixture/deepcoder",
                "revision": "1" * 40,
                "config_name": "primeintellect",
                "split": "train",
                "declared_license": "MIT",
                "adapter": "deepcoder",
            }
        ],
        "external_eval": {"dataset_id": HUMANEVAL_DATASET_ID, "revision": HUMANEVAL_REVISION},
        "selection": selection,
    }
    with pytest.raises(ConfigError, match="freezes"):
        refresh_data_config_from_mapping(config, config_path=tmp_path / "refresh.yaml")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_size", 9999),
        ("sft_overlap_fraction", 0.10),
        ("sft_overlap_hard_max", 0.20),
        ("sft_overlap_hard_max", 0.50),
    ],
)
def test_refresh_config_rejects_wp9a_selection_protocol_variants(
    tmp_path: Path,
    field: str,
    value: int | float,
) -> None:
    selection: dict[str, object] = {
        "target_size": 10000,
        "sft_overlap_fraction": 0.075,
        "sft_overlap_hard_max": 0.15,
        "token_ngram_size": 5,
        "near_jaccard_threshold": 0.90,
    }
    selection[field] = value
    config: dict[str, object] = {
        "version": "wp9a-refresh-v1",
        "sources": [
            {
                "source_name": "source-a",
                "dataset_id": "fixture/deepcoder",
                "revision": "1" * 40,
                "config_name": "primeintellect",
                "split": "train",
                "declared_license": "MIT",
                "adapter": "deepcoder",
            }
        ],
        "external_eval": {"dataset_id": HUMANEVAL_DATASET_ID, "revision": HUMANEVAL_REVISION},
        "selection": selection,
    }
    with pytest.raises(ConfigError, match="freezes"):
        refresh_data_config_from_mapping(config, config_path=tmp_path / "refresh.yaml")


def test_deterministic_stratified_select_is_permutation_invariant() -> None:
    candidates = [_candidate(f"a-{index}", source="source-a") for index in range(6)] + [
        _candidate(f"b-{index}", source="source-b") for index in range(4)
    ]
    first = deterministic_stratified_select(candidates, count=5, seed=42, namespace="fixture")
    second = deterministic_stratified_select(list(reversed(candidates)), count=5, seed=42, namespace="fixture")
    first_ids = [_selection_id(item) for item in first]
    second_ids = [_selection_id(item) for item in second]
    assert first_ids == second_ids
    assert sum(identifier.startswith("a-") for identifier in first_ids) == 3
    assert sum(identifier.startswith("b-") for identifier in first_ids) == 2


def _selection_id(value: object) -> str:
    if isinstance(value, RefreshCandidate):
        return value.candidate_id
    if isinstance(value, CodeProblem):
        return value.problem_id
    raise AssertionError(type(value))


def test_select_refresh_pool_enforces_explicit_overlap_and_frozen_order() -> None:
    sft = [_problem(f"train-{index}", "train") for index in range(3)]
    external = [_candidate(f"external-{index}") for index in range(8)]
    first_problems, first_manifest = select_refresh_pool(
        sft_problems=sft,
        new_candidates=external,
        config=_selection_config(),
        seed=42,
    )
    second_problems, second_manifest = select_refresh_pool(
        sft_problems=list(reversed(sft)),
        new_candidates=list(reversed(external)),
        config=_selection_config(),
        seed=42,
    )
    assert [problem.problem_id for problem in first_problems] == [problem.problem_id for problem in second_problems]
    assert first_manifest == second_manifest
    assert sum(record["overlap_origin"] == "sft_reuse" for record in first_manifest) == 1
    assert sum(record["overlap_origin"] == "external_new" for record in first_manifest) == 7


def test_select_refresh_pool_fails_closed_when_external_population_is_short() -> None:
    with pytest.raises(RefreshDataError, match="quota requires 7"):
        select_refresh_pool(
            sft_problems=[_problem("train-a", "train"), _problem("train-b", "train")],
            new_candidates=[_candidate(f"external-{index}") for index in range(5)],
            config=_selection_config(),
            seed=42,
        )


def test_prepare_check_is_byte_deterministic_and_views_are_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference"
    _write_reference_dataset(reference)
    candidates = [_candidate(f"external-{index}") for index in range(8)]
    _patch_pipeline_sources(monkeypatch, candidates=candidates)

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_summary = prepare_refresh_data(
        _data_config(),
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=None,
        output_dir=first,
    )
    second_summary = prepare_refresh_data(
        _data_config(),
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=None,
        output_dir=second,
    )
    assert first_summary.selected_problems == second_summary.selected_problems == 8
    assert first_summary.sft_overlap_count == second_summary.sft_overlap_count == 1
    assert first_summary.sft_overlap_fraction == second_summary.sft_overlap_fraction == 0.125
    assert _tree_bytes(first) == _tree_bytes(second)

    public = (first / "training" / "public_grpo.jsonl").read_bytes()
    hidden = (first / "training" / "hidden_grpo.jsonl").read_bytes()
    assert b'"eval_hidden_tests"' not in public + hidden
    assert b'"reference_solution"' not in public + hidden
    assert b'"sft_response"' not in public + hidden
    assert b'"starter_code"' not in public + hidden
    assert b'"train_hidden_tests"' not in public
    assert b'"train_hidden_tests"' in hidden


def test_check_refresh_data_rejects_tampered_selection_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference"
    _write_reference_dataset(reference)
    _patch_pipeline_sources(monkeypatch, candidates=[_candidate(f"external-{index}") for index in range(8)])
    output = tmp_path / "prepared"
    prepare_refresh_data(
        _data_config(),
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=None,
        output_dir=output,
    )
    selection = output / "manifest" / "selection.jsonl"
    records = [json.loads(line) for line in selection.read_text(encoding="utf-8").splitlines()]
    records.reverse()
    selection.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    with pytest.raises(RefreshDataError, match="hash/row-count mismatch"):
        refresh_module.check_refresh_data(output, reference_dataset_dir=reference)


def test_failed_prepare_does_not_publish_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference"
    _write_reference_dataset(reference)
    monkeypatch.setattr(
        refresh_module,
        "load_humanevalplus_references",
        lambda dataset_id, revision, cache_dir: (_fake_external_snapshot(), []),
    )

    def fail_source(spec: RefreshSourceSpec, *, cache_dir: Path | None) -> object:
        raise RefreshDataError("fixture source failure")

    monkeypatch.setattr(refresh_module, "load_refresh_source", fail_source)
    output = tmp_path / "failed"
    with pytest.raises(RefreshDataError, match="fixture source failure"):
        prepare_refresh_data(
            _data_config(),
            seed=42,
            reference_dataset_dir=reference,
            source_cache_dir=None,
            output_dir=output,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".failed.*"))
