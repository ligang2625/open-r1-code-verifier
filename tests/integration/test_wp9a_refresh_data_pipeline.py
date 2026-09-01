"""End-to-end fixture acceptance for the WP9-a refresh data foundation."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

import code_verifier.data.refresh as refresh_module
import code_verifier.data.refresh_sources as refresh_sources_module
from code_verifier.data.leakage_checks import LeakageError, TrainingArtifactKind, build_training_record
from code_verifier.data.prepare import (
    check_prepared_data,
    export_training_artifacts,
    load_canonical_jsonl,
    write_jsonl,
)
from code_verifier.data.refresh import (
    RefreshDataConfig,
    RefreshDataError,
    RefreshSelectionConfig,
    check_refresh_data,
    prepare_refresh_data,
)
from code_verifier.data.refresh_sources import RefreshSourceSpec
from code_verifier.data.schema import problem_to_mapping

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "wp9a"
DEEP_REVISION = "1" * 40
HUMANEVAL_REVISION = "2" * 40


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [cast(dict[str, object], json.loads(line)) for line in lines if line]


def _write_formal_reference(root: Path) -> None:
    problems = load_canonical_jsonl(FIXTURE_DIR / "formal_problems.jsonl")
    write_jsonl((problem_to_mapping(problem) for problem in problems), root / "canonical" / "problems.jsonl")
    export_training_artifacts(problems, root / "training")
    summary = check_prepared_data(root)
    assert summary.total_problems == 6
    assert summary.split_counts == {"train": 4, "validation": 1, "test": 1}


def _write_deepcoder_snapshot(root: Path) -> Path:
    snapshot = root / DEEP_REVISION
    snapshot.mkdir(parents=True)
    (snapshot / "README.md").write_text("---\nlicense: mit\n---\n# fixture\n", encoding="utf-8")
    for config_name, filename in (("primeintellect", "prime_rows.jsonl"), ("taco", "taco_rows.jsonl")):
        rows = _read_jsonl(FIXTURE_DIR / filename)
        config_dir = snapshot / config_name
        config_dir.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist(rows), config_dir / "train-00000-of-00001.parquet")
    return snapshot


def _write_humanevalplus_snapshot(root: Path) -> Path:
    snapshot = root / HUMANEVAL_REVISION
    snapshot.mkdir(parents=True)
    (snapshot / "README.md").write_text("---\nlicense: apache-2.0\n---\n# fixture\n", encoding="utf-8")
    shutil.copyfile(FIXTURE_DIR / "humanevalplus.jsonl", snapshot / "test.jsonl")
    return snapshot


def _patch_snapshot_resolution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    deepcoder_snapshot: Path,
    humaneval_snapshot: Path,
) -> None:
    def resolve(dataset_id: str, revision: str, *, cache_dir: Path | None) -> Path:
        del cache_dir
        if dataset_id == "fixture/deepcoder" and revision == DEEP_REVISION:
            return deepcoder_snapshot
        if dataset_id == "fixture/humanevalplus" and revision == HUMANEVAL_REVISION:
            return humaneval_snapshot
        raise AssertionError(f"unexpected fixture snapshot request {dataset_id}@{revision}")

    monkeypatch.setattr(refresh_sources_module, "_resolve_snapshot", resolve)


def _config() -> RefreshDataConfig:
    return RefreshDataConfig(
        sources=(
            RefreshSourceSpec(
                source_name="fixture-prime",
                dataset_id="fixture/deepcoder",
                revision=DEEP_REVISION,
                config_name="primeintellect",
                split="train",
                declared_license="MIT",
                adapter="deepcoder",
            ),
            RefreshSourceSpec(
                source_name="fixture-taco",
                dataset_id="fixture/deepcoder",
                revision=DEEP_REVISION,
                config_name="taco",
                split="train",
                declared_license="MIT",
                adapter="deepcoder",
            ),
        ),
        external_eval_dataset_id="fixture/humanevalplus",
        external_eval_revision=HUMANEVAL_REVISION,
        selection=RefreshSelectionConfig(
            target_size=8,
            sft_overlap_fraction=0.25,
            sft_overlap_hard_max=0.25,
            token_ngram_size=5,
            near_jaccard_threshold=0.90,
        ),
    )


def _setup_fixture_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[RefreshDataConfig, Path]:
    reference = tmp_path / "formal"
    _write_formal_reference(reference)
    deepcoder_snapshot = _write_deepcoder_snapshot(tmp_path / "deepcoder-snapshots")
    humaneval_snapshot = _write_humanevalplus_snapshot(tmp_path / "humaneval-snapshots")
    _patch_snapshot_resolution(
        monkeypatch,
        deepcoder_snapshot=deepcoder_snapshot,
        humaneval_snapshot=humaneval_snapshot,
    )
    return _config(), reference


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _jsonl_ids(path: Path) -> list[str]:
    records = _read_jsonl(path)
    result: list[str] = []
    for record in records:
        problem_id = record.get("problem_id")
        assert isinstance(problem_id, str)
        result.append(problem_id)
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rewrite_root_artifact_hash(root: Path, relative: str) -> None:
    manifest_path = root / "refresh_manifest.json"
    manifest = cast(dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8")))
    artifacts = cast(dict[str, object], manifest["artifacts"])
    record = cast(dict[str, object], artifacts[relative])
    record["sha256"] = _sha256(root / relative)
    record["rows"] = sum(bool(line) for line in (root / relative).read_text(encoding="utf-8").splitlines())
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl_records(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def test_wp9a_fixture_prepare_check_is_deterministic_and_leakage_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, reference = _setup_fixture_environment(tmp_path, monkeypatch)
    first = tmp_path / "refresh-first"
    second = tmp_path / "refresh-second"

    first_summary = prepare_refresh_data(
        config,
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=tmp_path / "cache",
        output_dir=first,
    )
    second_summary = prepare_refresh_data(
        config,
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=tmp_path / "cache",
        output_dir=second,
    )

    assert first_summary.total_candidates_scanned == second_summary.total_candidates_scanned == 12
    assert first_summary.external_candidates_retained == second_summary.external_candidates_retained == 6
    assert first_summary.selected_problems == second_summary.selected_problems == 8
    assert first_summary.sft_overlap_count == second_summary.sft_overlap_count == 2
    assert first_summary.sft_overlap_fraction == second_summary.sft_overlap_fraction == 0.25
    assert first_summary.quality_gate_required_count == second_summary.quality_gate_required_count == 3
    assert _tree_bytes(first) == _tree_bytes(second)
    assert check_refresh_data(first, reference_dataset_dir=reference).selected_problems == 8

    decisions = _read_jsonl(first / "manifest" / "dedup_decisions.jsonl")
    overlap_counts = Counter(str(record["overlap_class"]) for record in decisions)
    assert overlap_counts == {
        "none": 6,
        "evaluation_overlap": 3,
        "incidental_sft_overlap": 1,
        "cross_source_duplicate": 2,
    }
    assert all(record.get("source_name") in {"fixture-prime", "fixture-taco"} for record in decisions)
    assert all(isinstance(record.get("source_record_id"), str) for record in decisions)
    assert all(isinstance(record.get("raw_record_sha256"), str) for record in decisions)
    reasons = {str(record["rejection_reason"]) for record in decisions if record["rejection_reason"] is not None}
    assert "near_external_eval" in reasons
    assert "near_external_duplicate" in reasons
    assert any(reason.startswith("exact_validation") for reason in reasons)
    assert any(reason.startswith("exact_project_test") for reason in reasons)
    assert any(reason.startswith("exact_sft") for reason in reasons)

    selection = _read_jsonl(first / "manifest" / "selection.jsonl")
    assert Counter(str(record["overlap_origin"]) for record in selection) == {"sft_reuse": 2, "external_new": 6}
    assert sum(record["quality_gate_required"] is True for record in selection) == 3

    canonical_ids = _jsonl_ids(first / "canonical" / "problems.jsonl")
    public_ids = _jsonl_ids(first / "training" / "public_grpo.jsonl")
    hidden_ids = _jsonl_ids(first / "training" / "hidden_grpo.jsonl")
    assert canonical_ids == public_ids == hidden_ids
    public_bytes = (first / "training" / "public_grpo.jsonl").read_bytes()
    hidden_bytes = (first / "training" / "hidden_grpo.jsonl").read_bytes()
    assert b'"train_hidden_tests"' not in public_bytes
    for forbidden in (b'"eval_hidden_tests"', b'"reference_solution"', b'"sft_response"', b'"starter_code"'):
        assert forbidden not in public_bytes
        assert forbidden not in hidden_bytes
    assert b'"train_hidden_tests"' in hidden_bytes
    assert str(tmp_path).encode() not in (first / "refresh_manifest.json").read_bytes()


@pytest.mark.parametrize("tamper", ["root_manifest", "artifact_hash", "selection_order", "hidden_field"])
def test_wp9a_fixture_strict_readback_rejects_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    config, reference = _setup_fixture_environment(tmp_path, monkeypatch)
    pristine = tmp_path / "refresh-pristine"
    prepare_refresh_data(
        config,
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=None,
        output_dir=pristine,
    )
    root = tmp_path / f"tampered-{tamper}"
    shutil.copytree(pristine, root)

    expected: type[Exception]
    if tamper == "root_manifest":
        manifest_path = root / "refresh_manifest.json"
        manifest = cast(dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8")))
        manifest["selected_ids_order_sha256"] = "0" * 64
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        expected = RefreshDataError
    elif tamper == "artifact_hash":
        path = root / "reports" / "dedup_summary.json"
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + " \n", encoding="utf-8")
        expected = RefreshDataError
    elif tamper == "selection_order":
        path = root / "manifest" / "selection.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
        _rewrite_root_artifact_hash(root, "manifest/selection.jsonl")
        expected = RefreshDataError
    else:
        path = root / "training" / "hidden_grpo.jsonl"
        records = _read_jsonl(path)
        records[0]["eval_hidden_tests"] = []
        path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        _rewrite_root_artifact_hash(root, "training/hidden_grpo.jsonl")
        expected = LeakageError

    with pytest.raises(expected):
        check_refresh_data(root, reference_dataset_dir=reference)


def test_wp9a_strict_readback_recomputes_quality_gate_from_canonical_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, reference = _setup_fixture_environment(tmp_path, monkeypatch)
    root = tmp_path / "quality-tamper"
    prepare_refresh_data(
        config,
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=None,
        output_dir=root,
    )

    selection_path = root / "manifest" / "selection.jsonl"
    selection = _read_jsonl(selection_path)
    selected = next(record for record in selection if record.get("quality_gate_required") is True)
    selected["quality_gate_required"] = False
    _write_jsonl_records(selection_path, selection)
    _rewrite_root_artifact_hash(root, "manifest/selection.jsonl")

    leakage_path = root / "reports" / "test_layer_leakage.json"
    leakage = cast(dict[str, object], json.loads(leakage_path.read_text(encoding="utf-8")))
    leakage["quality_gate_required_count"] = cast(int, leakage["quality_gate_required_count"]) - 1
    leakage_path.write_text(
        json.dumps(leakage, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _rewrite_root_artifact_hash(root, "reports/test_layer_leakage.json")

    manifest_path = root / "refresh_manifest.json"
    manifest = cast(dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8")))
    counts = cast(dict[str, object], manifest["counts"])
    counts["quality_gate_required_count"] = cast(int, counts["quality_gate_required_count"]) - 1
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RefreshDataError, match="quality_gate_required"):
        check_refresh_data(root, reference_dataset_dir=reference)


def test_wp9a_strict_readback_binds_stored_fingerprint_to_canonical_and_training_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, reference = _setup_fixture_environment(tmp_path, monkeypatch)
    root = tmp_path / "canonical-tamper"
    prepare_refresh_data(
        config,
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=None,
        output_dir=root,
    )

    selection = _read_jsonl(root / "manifest" / "selection.jsonl")
    external_record = next(record for record in selection if record["overlap_origin"] == "external_new")
    external_id = cast(str, external_record["problem_id"])
    canonical_path = root / "canonical" / "problems.jsonl"
    canonical = _read_jsonl(canonical_path)
    record = next(item for item in canonical if item["problem_id"] == external_id)
    prompt = cast(str, record["prompt"])
    suffix = f"\n\n{refresh_sources_module._REFRESH_INTERFACE_NOTE}"
    assert prompt.endswith(suffix)
    record["prompt"] = f"{prompt[: -len(suffix)]} semantically-tampered{suffix}"
    _write_jsonl_records(canonical_path, canonical)

    problems = load_canonical_jsonl(canonical_path)
    write_jsonl(
        (build_training_record(problem, kind=TrainingArtifactKind.PUBLIC_GRPO) for problem in problems),
        root / "training" / "public_grpo.jsonl",
    )
    write_jsonl(
        (build_training_record(problem, kind=TrainingArtifactKind.HIDDEN_GRPO) for problem in problems),
        root / "training" / "hidden_grpo.jsonl",
    )
    for relative in (
        "canonical/problems.jsonl",
        "training/public_grpo.jsonl",
        "training/hidden_grpo.jsonl",
    ):
        _rewrite_root_artifact_hash(root, relative)

    with pytest.raises(RefreshDataError, match="stored external fingerprint"):
        check_refresh_data(root, reference_dataset_dir=reference)


def test_wp9a_strict_readback_recomputes_report_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, reference = _setup_fixture_environment(tmp_path, monkeypatch)
    root = tmp_path / "report-tamper"
    prepare_refresh_data(
        config,
        seed=42,
        reference_dataset_dir=reference,
        source_cache_dir=None,
        output_dir=root,
    )
    report_path = root / "reports" / "evaluation_overlap.json"
    report = cast(dict[str, object], json.loads(report_path.read_text(encoding="utf-8")))
    report["external_eval_exact_or_near_overlap"] = 1
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _rewrite_root_artifact_hash(root, "reports/evaluation_overlap.json")

    with pytest.raises(RefreshDataError, match="evaluation_overlap.json"):
        check_refresh_data(root, reference_dataset_dir=reference)


def test_wp9a_fixture_failed_atomic_write_leaves_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, reference = _setup_fixture_environment(tmp_path, monkeypatch)
    output = tmp_path / "refresh-failed"
    original = refresh_module._write_json

    def fail_mid_publish(path: Path, value: object) -> None:
        if path.name == "dedup_summary.json":
            raise OSError("fixture mid-publish failure")
        original(path, value)

    monkeypatch.setattr(refresh_module, "_write_json", fail_mid_publish)
    with pytest.raises(RefreshDataError, match="mid-publish failure"):
        prepare_refresh_data(
            config,
            seed=42,
            reference_dataset_dir=reference,
            source_cache_dir=None,
            output_dir=output,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".refresh-failed.*"))
