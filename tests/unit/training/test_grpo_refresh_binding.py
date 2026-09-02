from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import code_verifier.training.grpo as grpo_module
from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.throughput import RefreshBenchmarkSummary, check_refresh_benchmark_report
from code_verifier.training.calibration import CalibrationPoolSummary
from code_verifier.training.grpo import (
    GRPOTrainingError,
    _validate_refresh_active_records,
    load_grpo_benchmark_binding,
    load_grpo_refresh_binding,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_engineering_binding_artifacts(
    root: Path,
    *,
    workers: int = 16,
    problem_id: str = "p1",
) -> tuple[Path, Path]:
    training = root / "training"
    training.mkdir(parents=True)
    public_path = training / "public_grpo.jsonl"
    hidden_path = training / "hidden_grpo.jsonl"
    public_path.write_text(json.dumps({"problem_id": problem_id}) + "\n", encoding="utf-8")
    hidden_path.write_text(json.dumps({"problem_id": problem_id}) + "\n", encoding="utf-8")
    calibration_path = root / "calibration_manifest.json"
    calibration_path.write_text(
        json.dumps(
            {
                "schema_version": "wp9b-calibration-test-v1",
                "status": "completed",
                "evidence_class": "engineering",
                "active_order_sha256": stable_json_hash([problem_id]),
                "artifacts": {
                    "training/public_grpo.jsonl": _sha256(public_path),
                    "training/hidden_grpo.jsonl": _sha256(hidden_path),
                },
            }
        ),
        encoding="utf-8",
    )
    benchmark_path = root / "refresh_benchmark_report.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "version": "wp9b-refresh-benchmark-v1",
                "evidence_class": "engineering",
                "selected_grpo_verification_workers": workers,
            }
        ),
        encoding="utf-8",
    )
    return calibration_path, benchmark_path


def _patch_strict_checkers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    calibration_path: Path,
    benchmark_path: Path,
    workers: int = 16,
) -> None:
    public_path = root / "training" / "public_grpo.jsonl"
    hidden_path = root / "training" / "hidden_grpo.jsonl"

    def check_pool(
        pool_dir: Path,
        *,
        refresh_dataset_dir: Path,
        reference_dataset_dir: Path,
        allow_test_protocol: bool = False,
    ) -> CalibrationPoolSummary:
        assert pool_dir == root
        assert refresh_dataset_dir.name == "refresh"
        assert reference_dataset_dir.name == "reference"
        assert allow_test_protocol is True
        return CalibrationPoolSummary(
            pool_dir=root,
            selected_problems=1,
            dual_informative=1,
            public_only=0,
            hidden_only=0,
            sft_overlap_count=0,
            active_order_sha256=stable_json_hash(["p1"]),
            calibration_manifest=calibration_path,
            public_grpo_jsonl=public_path,
            hidden_grpo_jsonl=hidden_path,
        )

    def check_benchmark(path: Path, *, allow_engineering: bool = False) -> RefreshBenchmarkSummary:
        assert path == benchmark_path
        assert allow_engineering is True
        return RefreshBenchmarkSummary(
            report_dir=benchmark_path.parent,
            report_path=benchmark_path,
            selected_eval_generation_batch_size=2,
            evidence_class="engineering",
            selected_grpo_verification_workers=workers,
            calibration_manifest_sha256=_sha256(calibration_path),
            active_order_sha256=stable_json_hash(["p1"]),
            active_public_training_sha256=_sha256(public_path),
            active_hidden_training_sha256=_sha256(hidden_path),
        )

    monkeypatch.setattr(grpo_module, "check_calibrated_active_pool", check_pool)
    monkeypatch.setattr(grpo_module, "check_refresh_benchmark_report", check_benchmark)


def test_refresh_binding_is_derived_from_strict_checker_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    _patch_strict_checkers(
        monkeypatch,
        root=tmp_path,
        calibration_path=calibration_path,
        benchmark_path=benchmark_path,
    )

    binding = load_grpo_refresh_binding(
        calibration_manifest_path=calibration_path,
        refresh_dataset_dir=tmp_path / "refresh",
        reference_dataset_dir=tmp_path / "reference",
        benchmark_report_path=benchmark_path,
        verification_workers=16,
        allow_engineering=True,
    )

    assert binding.calibration_manifest_sha256 == _sha256(calibration_path)
    assert binding.benchmark_report_sha256 == _sha256(benchmark_path)
    assert binding.verification_workers == 16
    assert binding.active_order_sha256 == stable_json_hash(["p1"])


def test_benchmark_binding_bootstraps_without_final_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    _patch_strict_checkers(
        monkeypatch,
        root=tmp_path,
        calibration_path=calibration_path,
        benchmark_path=benchmark_path,
    )

    binding = load_grpo_benchmark_binding(
        calibration_manifest_path=calibration_path,
        refresh_dataset_dir=tmp_path / "refresh",
        reference_dataset_dir=tmp_path / "reference",
        verification_workers=16,
        role="k8_candidate",
        allow_engineering=True,
    )

    assert binding.role == "k8_candidate"
    assert binding.verification_workers == 16
    assert binding.calibration_manifest_sha256 == _sha256(calibration_path)
    assert binding.active_order_sha256 == stable_json_hash(["p1"])
    assert not hasattr(binding, "benchmark_report_path")


def test_refresh_binding_rejects_unchecked_minimal_calibration(tmp_path: Path) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    (tmp_path / "refresh").mkdir()
    (tmp_path / "reference").mkdir()

    with pytest.raises(GRPOTrainingError, match="calibration artifact failed strict check"):
        load_grpo_refresh_binding(
            calibration_manifest_path=calibration_path,
            refresh_dataset_dir=tmp_path / "refresh",
            reference_dataset_dir=tmp_path / "reference",
            benchmark_report_path=benchmark_path,
            verification_workers=16,
            allow_engineering=True,
        )


def test_refresh_binding_rejects_handcrafted_benchmark_recommendation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    _patch_strict_checkers(
        monkeypatch,
        root=tmp_path,
        calibration_path=calibration_path,
        benchmark_path=benchmark_path,
    )
    monkeypatch.setattr(grpo_module, "check_refresh_benchmark_report", check_refresh_benchmark_report)

    with pytest.raises(GRPOTrainingError, match="refresh benchmark artifact failed strict check"):
        load_grpo_refresh_binding(
            calibration_manifest_path=calibration_path,
            refresh_dataset_dir=tmp_path / "refresh",
            reference_dataset_dir=tmp_path / "reference",
            benchmark_report_path=benchmark_path,
            verification_workers=16,
            allow_engineering=True,
        )


def test_refresh_binding_rejects_dataset_tamper_and_worker_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    _patch_strict_checkers(
        monkeypatch,
        root=tmp_path,
        calibration_path=calibration_path,
        benchmark_path=benchmark_path,
    )
    (tmp_path / "training" / "public_grpo.jsonl").write_text('{"problem_id":"tampered"}\n', encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="hash mismatch"):
        load_grpo_refresh_binding(
            calibration_manifest_path=calibration_path,
            refresh_dataset_dir=tmp_path / "refresh",
            reference_dataset_dir=tmp_path / "reference",
            benchmark_report_path=benchmark_path,
            verification_workers=16,
            allow_engineering=True,
        )

    workers_root = tmp_path / "workers"
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(workers_root)
    _patch_strict_checkers(
        monkeypatch,
        root=workers_root,
        calibration_path=calibration_path,
        benchmark_path=benchmark_path,
        workers=16,
    )
    with pytest.raises(GRPOTrainingError, match="differs from the benchmark selection"):
        load_grpo_refresh_binding(
            calibration_manifest_path=calibration_path,
            refresh_dataset_dir=workers_root / "refresh",
            reference_dataset_dir=workers_root / "reference",
            benchmark_report_path=benchmark_path,
            verification_workers=32,
            allow_engineering=True,
        )


def test_refresh_binding_rejects_different_valid_calibration_and_benchmark_sets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration_root = tmp_path / "calibration-a"
    benchmark_root = tmp_path / "calibration-b"
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(calibration_root)
    other_calibration_path, other_benchmark_path = _write_engineering_binding_artifacts(
        benchmark_root,
        problem_id="p2",
    )
    other_public = benchmark_root / "training" / "public_grpo.jsonl"
    other_hidden = benchmark_root / "training" / "hidden_grpo.jsonl"

    _patch_strict_checkers(
        monkeypatch,
        root=calibration_root,
        calibration_path=calibration_path,
        benchmark_path=benchmark_path,
    )

    def check_other_benchmark(path: Path, *, allow_engineering: bool = False) -> RefreshBenchmarkSummary:
        assert path == other_benchmark_path
        assert allow_engineering is True
        return RefreshBenchmarkSummary(
            report_dir=other_benchmark_path.parent,
            report_path=other_benchmark_path,
            selected_eval_generation_batch_size=2,
            evidence_class="engineering",
            selected_grpo_verification_workers=16,
            calibration_manifest_sha256=_sha256(other_calibration_path),
            active_order_sha256=stable_json_hash(["p2"]),
            active_public_training_sha256=_sha256(other_public),
            active_hidden_training_sha256=_sha256(other_hidden),
        )

    monkeypatch.setattr(grpo_module, "check_refresh_benchmark_report", check_other_benchmark)

    with pytest.raises(GRPOTrainingError, match="benchmark calibration identity differs"):
        load_grpo_refresh_binding(
            calibration_manifest_path=calibration_path,
            refresh_dataset_dir=calibration_root / "refresh",
            reference_dataset_dir=calibration_root / "reference",
            benchmark_report_path=other_benchmark_path,
            verification_workers=16,
            allow_engineering=True,
        )


def test_refresh_active_records_require_bound_order_and_matching_calibration_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    _patch_strict_checkers(
        monkeypatch,
        root=tmp_path,
        calibration_path=calibration_path,
        benchmark_path=benchmark_path,
    )
    binding = load_grpo_refresh_binding(
        calibration_manifest_path=calibration_path,
        refresh_dataset_dir=tmp_path / "refresh",
        reference_dataset_dir=tmp_path / "reference",
        benchmark_report_path=benchmark_path,
        verification_workers=16,
        allow_engineering=True,
    )
    public = [{"problem_id": "p1", "metadata": {"calibration_class": "dual_informative"}}]
    hidden = [{"problem_id": "p1", "metadata": {"calibration_class": "dual_informative"}}]

    _validate_refresh_active_records(public, hidden, binding)

    hidden[0] = {"problem_id": "p1", "metadata": {"calibration_class": "hidden_only"}}
    with pytest.raises(GRPOTrainingError, match="metadata differs"):
        _validate_refresh_active_records(public, hidden, binding)

    with pytest.raises(GRPOTrainingError, match="order differs"):
        _validate_refresh_active_records(
            [{"problem_id": "p2", "metadata": {"calibration_class": "dual_informative"}}],
            [{"problem_id": "p2", "metadata": {"calibration_class": "dual_informative"}}],
            binding,
        )
