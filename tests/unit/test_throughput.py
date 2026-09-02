from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from code_verifier.throughput import compare_generation_bundle_parity, summarize_refresh_benchmarks


def _bundle(root: Path, *, batch_size: int, latency_ms: float, completion: str = "same") -> Path:
    run = root / f"batch-{batch_size}-{latency_ms}-{completion}"
    samples = run / "samples"
    samples.mkdir(parents=True)
    rows = [
        {
            "run_id": run.name,
            "model_id": "model",
            "checkpoint": "base",
            "dataset_hash": "a" * 64,
            "evaluation_contract_sha256": "b" * 64,
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
    metadata = {
        "schema_version": 2,
        "artifact_type": "evaluation_generation_bundle",
        "status": "completed",
        "model_id": "model",
        "model_revision": "r",
        "checkpoint": "base",
        "dataset_hash": "a" * 64,
        "seed": 42,
        "batch_size": batch_size,
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
