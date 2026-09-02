from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from code_verifier import throughput
from code_verifier.runtime_telemetry import RuntimeUtilizationSampler
from code_verifier.throughput import ThroughputError, compare_generation_bundle_parity, summarize_refresh_benchmarks


def _bundle(
    root: Path,
    *,
    batch_size: int,
    latency_ms: float,
    completion: str = "same",
    max_new_tokens: int = 512,
) -> Path:
    run = root / f"batch-{batch_size}-{latency_ms}-{completion}-{max_new_tokens}"
    samples = run / "samples"
    samples.mkdir(parents=True)
    resolved = {
        "schema_version": 2,
        "run_id": run.name,
        "model_id": "model",
        "model_revision": "r",
        "checkpoint": "base",
        "seed": 42,
        "split": "test",
        "device": "cuda",
        "generation": {"do_sample": False, "max_new_tokens": max_new_tokens},
        "dataset_hash": "a" * 64,
        "piston_config_sha256": "e" * 64,
        "batch_size": batch_size,
    }
    contract_sha256 = throughput._stable_hash(resolved)
    rows = [
        {
            "run_id": run.name,
            "model_id": "model",
            "checkpoint": "base",
            "dataset_hash": "a" * 64,
            "evaluation_contract_sha256": contract_sha256,
            "problem_id": f"p{index}",
            "prompt_hash": ("c" if index == 0 else "d") * 64,
            "completion": completion,
            "completion_tokens": 10,
            "generation_latency_ms": latency_ms,
            "hit_max_new_tokens": False,
        }
        for index in range(2)
    ]
    records_path = samples / "generations.jsonl"
    records_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    resolved_path = run / "resolved_config.yaml"
    resolved_path.write_text(yaml.safe_dump(resolved, sort_keys=True), encoding="utf-8")
    metadata = {
        "schema_version": 2,
        "artifact_type": "evaluation_generation_bundle",
        "status": "completed",
        "run_id": run.name,
        "model_id": "model",
        "model_revision": "r",
        "checkpoint": "base",
        "dataset_hash": "a" * 64,
        "seed": 42,
        "batch_size": batch_size,
        "evaluation_contract_sha256": contract_sha256,
        "ordered_problem_ids_sha256": throughput._stable_hash([row["problem_id"] for row in rows]),
        "resolved_config_sha256": hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
        "completed_records": 2,
        "total_problems": 2,
        "records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
    }
    (run / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    return run


def test_generation_parity_ignores_operational_batch_identity(tmp_path: Path) -> None:
    baseline = _bundle(tmp_path, batch_size=1, latency_ms=4.0)
    candidate = _bundle(tmp_path, batch_size=2, latency_ms=2.0)
    assert compare_generation_bundle_parity(baseline, candidate).exact is True


def test_generation_parity_rejects_resolved_config_drift(tmp_path: Path) -> None:
    baseline = _bundle(tmp_path, batch_size=1, latency_ms=4.0)
    candidate = _bundle(tmp_path, batch_size=2, latency_ms=2.0, max_new_tokens=256)

    parity = compare_generation_bundle_parity(baseline, candidate)
    assert parity.exact is False
    assert parity.reason == "source_identity_mismatch"


def test_benchmark_selects_fastest_exact_artifact_and_rejects_drift(tmp_path: Path) -> None:
    baseline = _bundle(tmp_path, batch_size=1, latency_ms=4.0)
    batch2 = _bundle(tmp_path, batch_size=2, latency_ms=2.0)
    batch4_bad = _bundle(tmp_path, batch_size=4, latency_ms=1.0, completion="drift")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "version": "wp9b-refresh-benchmark-v1",
                "evidence_class": "engineering",
                "eval_generation": {
                    "baseline": str(baseline),
                    "candidates": [str(batch2), str(batch4_bad)],
                },
            }
        ),
        encoding="utf-8",
    )
    summary = summarize_refresh_benchmarks(manifest, output_dir=tmp_path / "report")
    report = json.loads(summary.report_path.read_text(encoding="utf-8"))
    assert summary.selected_eval_generation_batch_size == 2
    assert report["candidates"][1]["rejection"] == "generation_output_mismatch"
    assert report["source_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    checked = throughput.check_refresh_benchmark_report(summary.report_path, allow_engineering=True)
    assert checked.selected_eval_generation_batch_size == 2

    report["selected_eval_generation_batch_size"] = 4
    summary.report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ThroughputError, match="does not recompute"):
        throughput.check_refresh_benchmark_report(summary.report_path, allow_engineering=True)


def test_formal_generation_benchmark_requires_available_runtime_utilization(tmp_path: Path) -> None:
    baseline = _bundle(tmp_path, batch_size=1, latency_ms=4.0)

    with pytest.raises(ThroughputError, match="formal generation runtime telemetry is incomplete"):
        throughput._bundle_metrics(baseline, require_formal_telemetry=True)

    sampler = RuntimeUtilizationSampler(sample_fn=lambda: (35.0, 1024.0))
    sampler.sample_once()
    metadata_path = baseline / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["runtime_utilization"] = sampler.snapshot()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    metrics = throughput._bundle_metrics(baseline, require_formal_telemetry=True)
    utilization = metrics["runtime_utilization"]
    assert isinstance(utilization, dict)
    assert utilization["status"] == "available"
    assert utilization["gpu_utilization_mean_percent"] == 35.0


def test_formal_summary_does_not_close_when_generation_utilization_is_missing(tmp_path: Path) -> None:
    baseline = _bundle(tmp_path, batch_size=1, latency_ms=4.0)
    batch2 = _bundle(tmp_path, batch_size=2, latency_ms=2.0)
    manifest = tmp_path / "formal-manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "version": "wp9b-refresh-benchmark-v1",
                "evidence_class": "formal",
                "eval_generation": {"baseline": str(baseline), "candidates": [str(batch2)]},
                "eval_verification": {"baseline": "unused", "candidates": ["unused"]},
                "grpo_verification": {"baseline": "unused", "candidates": ["unused"]},
                "grpo_group_size_diagnostic": {"k4": "unused", "k8": "unused"},
                "paired_grpo": {
                    "sequential": {"public": "unused", "hidden": "unused"},
                    "concurrent": {"public": "unused", "hidden": "unused"},
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ThroughputError, match="formal generation runtime telemetry is incomplete"):
        summarize_refresh_benchmarks(manifest, output_dir=tmp_path / "formal-report")
