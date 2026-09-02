from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.training.grpo import (
    GRPOTrainingError,
    _validate_refresh_active_records,
    load_grpo_refresh_binding,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_engineering_binding_artifacts(root: Path, *, workers: int = 16) -> tuple[Path, Path]:
    training = root / "training"
    training.mkdir(parents=True)
    public_path = training / "public_grpo.jsonl"
    hidden_path = training / "hidden_grpo.jsonl"
    public_path.write_text('{"problem_id":"p1"}\n', encoding="utf-8")
    hidden_path.write_text('{"problem_id":"p1"}\n', encoding="utf-8")
    calibration_path = root / "calibration_manifest.json"
    calibration_path.write_text(
        json.dumps(
            {
                "schema_version": "wp9b-calibration-test-v1",
                "status": "completed",
                "evidence_class": "engineering",
                "active_order_sha256": stable_json_hash(["p1"]),
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


def test_refresh_binding_is_derived_from_artifact_hashes_and_worker_selection(tmp_path: Path) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)

    binding = load_grpo_refresh_binding(
        calibration_manifest_path=calibration_path,
        benchmark_report_path=benchmark_path,
        verification_workers=16,
        allow_engineering=True,
    )

    assert binding.calibration_manifest_sha256 == _sha256(calibration_path)
    assert binding.benchmark_report_sha256 == _sha256(benchmark_path)
    assert binding.verification_workers == 16
    assert binding.active_order_sha256 == stable_json_hash(["p1"])


def test_refresh_binding_rejects_dataset_tamper_and_worker_drift(tmp_path: Path) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    (tmp_path / "training" / "public_grpo.jsonl").write_text('{"problem_id":"tampered"}\n', encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="hash mismatch"):
        load_grpo_refresh_binding(
            calibration_manifest_path=calibration_path,
            benchmark_report_path=benchmark_path,
            verification_workers=16,
            allow_engineering=True,
        )

    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path / "workers")
    with pytest.raises(GRPOTrainingError, match="differs from the benchmark selection"):
        load_grpo_refresh_binding(
            calibration_manifest_path=calibration_path,
            benchmark_report_path=benchmark_path,
            verification_workers=32,
            allow_engineering=True,
        )


def test_refresh_active_records_require_bound_order_and_matching_calibration_class(tmp_path: Path) -> None:
    calibration_path, benchmark_path = _write_engineering_binding_artifacts(tmp_path)
    binding = load_grpo_refresh_binding(
        calibration_manifest_path=calibration_path,
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
