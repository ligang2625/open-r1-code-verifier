from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

from code_verifier import throughput
from code_verifier.evaluation.evaluate import EvaluationRecord, evaluation_record_to_mapping
from code_verifier.runtime_telemetry import RuntimeUtilizationSampler
from code_verifier.throughput import ThroughputError


def _evaluation_record(problem_id: str, *, runtime_ms: float, completion: str = "same") -> EvaluationRecord:
    return EvaluationRecord(
        run_id="eval",
        model_id="model",
        checkpoint="base",
        dataset_hash="a" * 64,
        config_hash="b" * 64,
        problem_id=problem_id,
        prompt_hash=("c" if problem_id == "p1" else "d") * 64,
        completion=completion,
        extracted_code="def solve(value):\n    return value\n",
        parse_success=True,
        target_function_found=True,
        visible_pass_rate=1.0,
        train_hidden_pass_rate=1.0,
        eval_hidden_pass_rate=1.0,
        execution_status="passed",
        visible_execution_status="passed",
        train_hidden_execution_status="passed",
        eval_hidden_execution_status="passed",
        visible_failure_counts={},
        train_hidden_failure_counts={},
        eval_hidden_failure_counts={},
        parse_error_type=None,
        runtime_ms=runtime_ms,
        generation_latency_ms=1.0,
        completion_tokens=4,
        error_category_auto="passed",
    )


def _verification_run(
    root: Path,
    *,
    name: str,
    workers: int,
    duration_seconds: float,
    completion: str = "same",
    host_telemetry: bool = False,
) -> Path:
    run = root / name
    samples = run / "samples"
    samples.mkdir(parents=True)
    records = [
        _evaluation_record("p1", runtime_ms=1.0, completion=completion),
        _evaluation_record("p2", runtime_ms=9.0, completion=completion),
    ]
    results_path = samples / "results.jsonl"
    results_path.write_text(
        "".join(
            json.dumps(evaluation_record_to_mapping(record), sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    start = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)
    metadata: dict[str, object] = {
        "status": "completed",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(seconds=duration_seconds)).isoformat(),
        "verification_workers": workers,
        "generation_bundle_schema_version": 2,
        "generation_bundle_run_id": "eval",
        "generation_bundle_records_sha256": "e" * 64,
        "generation_bundle_contract_sha256": "f" * 64,
        "generation_bundle_ordered_problem_ids_sha256": "1" * 64,
        "generation_environment_sha256": "2" * 64,
        "generation_batch_size": 4,
    }
    if host_telemetry:
        metadata["runtime_utilization"] = RuntimeUtilizationSampler().snapshot()
    (run / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    return run


def test_eval_verification_worker_selection_requires_exact_results_and_reports_latency(tmp_path: Path) -> None:
    baseline = _verification_run(tmp_path, name="baseline", workers=1, duration_seconds=10.0)
    worker8 = _verification_run(tmp_path, name="worker8", workers=8, duration_seconds=5.0)
    worker32_bad = _verification_run(
        tmp_path,
        name="worker32-bad",
        workers=32,
        duration_seconds=1.0,
        completion="drift",
    )
    worker64 = _verification_run(tmp_path, name="worker64", workers=64, duration_seconds=2.0)

    selected, report = throughput._select_eval_verification(
        {"baseline": str(baseline), "candidates": [str(worker8), str(worker32_bad), str(worker64)]}
    )

    assert selected == 64
    candidates = report["candidates"]
    assert isinstance(candidates, list)
    assert candidates[1]["rejection"] == "verification_result_mismatch"
    assert candidates[2]["mean_verifier_latency_ms"] == 5.0
    assert candidates[2]["p95_verifier_latency_ms"] == 9.0


def test_formal_eval_verification_requires_host_cpu_and_rss_telemetry(tmp_path: Path) -> None:
    run = _verification_run(tmp_path, name="formal", workers=64, duration_seconds=2.0)

    with pytest.raises(ThroughputError, match="formal verification host telemetry is incomplete"):
        throughput._evaluation_verification_probe(run, require_formal_host_telemetry=True)

    metadata_path = run / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["runtime_utilization"] = RuntimeUtilizationSampler().snapshot()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    probe = throughput._evaluation_verification_probe(run, require_formal_host_telemetry=True)
    assert probe.host_runtime is not None
    assert probe.host_runtime["status"] == "unavailable"
    assert cast(int, probe.host_runtime["host_cpu_count"]) > 0
    assert probe.mean_latency_ms == 5.0
    assert probe.p95_latency_ms == 9.0
