#!/usr/bin/env python3
"""Run the audited C19 final formal Piston gate for the reduced ready lane."""

from __future__ import annotations

import argparse
import hashlib
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.json_strict import loads_strict
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.piston import PistonExecutor, PistonTransportError, load_piston_executor_config
from code_verifier.execution.piston_resilience import load_piston_transport_policy

ROOT = Path(__file__).resolve().parents[6]
PISTON_CONFIG = ROOT / "configs/execution/piston-local.yaml"
TRANSPORT_POLICY = ROOT / "configs/execution/piston-transport-resilience.yaml"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _require_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context_name(row)}.{key} must be a non-empty string")
    return value


def context_name(row: Mapping[str, object]) -> str:
    value = row.get("candidate_id")
    return value if isinstance(value, str) and value else "row"


def _require_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context_name(row)}.{key} must be an integer")
    return value


def _require_float(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context_name(row)}.{key} must be numeric")
    return float(value)


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            value = loads_strict(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = canonical_json(row) + "\n"
            handle.write(payload)
            digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def _job_sha(job: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json(job).encode("utf-8")).hexdigest()


def _infra_kinds(result: ExecutionResult) -> list[str]:
    return sorted(
        {
            item.infrastructure_failure_kind.value
            for item in result.test_results
            if item.infrastructure_failure_kind is not None
        }
    )


def _sanitize_result(result: ExecutionResult, solution_sha: str) -> dict[str, object]:
    status_counts = Counter(item.status.value for item in result.test_results)
    infrastructure_kinds = _infra_kinds(result)
    return {
        "transformed_code_sha256": solution_sha,
        "status": result.status.value,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "pass_rate": result.pass_rate,
        "runtime_ms": result.runtime_ms,
        "test_status_counts": dict(sorted(status_counts.items())),
        "infrastructure_failure_kinds": infrastructure_kinds,
        "formal_solution_pass": (
            result.status is ExecutionStatus.PASSED and result.passed_tests == result.total_tests
        ),
        "infrastructure_failure": bool(infrastructure_kinds),
    }


def _validate_job(job: Mapping[str, object]) -> None:
    _require_str(job, "candidate_id")
    _require_str(job, "candidate_binding_sha256")
    _require_str(job, "source_name")
    _require_str(job, "canonical_problem_sha256")
    if _require_str(job, "execution_function_name") != "__wp9c_reference_entry__":
        raise ValueError("C19 execution function drift")
    tests = job.get("tests")
    if not isinstance(tests, list) or len(tests) != _require_int(job, "test_count") or len(tests) < 8:
        raise ValueError(f"{context_name(job)} test payload drift")
    for test in tests:
        if not isinstance(test, dict) or set(test) != {"input", "expected"}:
            raise ValueError(f"{context_name(job)} test schema drift")
    solutions = job.get("transformed_source_solutions")
    if not isinstance(solutions, list) or not solutions:
        raise ValueError(f"{context_name(job)} has no transformed source solutions")
    expected_count = _require_int(job, "transformed_source_solution_count")
    if len(solutions) != expected_count:
        raise ValueError(f"{context_name(job)} transformed solution count drift")
    hashes: list[str] = []
    for value in solutions:
        solution = _mapping(value, context=f"{context_name(job)} solution")
        code = _require_str(solution, "code")
        digest = _require_str(solution, "transformed_code_sha256")
        if hashlib.sha256(code.encode("utf-8")).hexdigest() != digest:
            raise ValueError(f"{context_name(job)} transformed solution digest drift")
        hashes.append(digest)
    if hashes != sorted(set(hashes)):
        raise ValueError(f"{context_name(job)} transformed solution order/uniqueness drift")
    _require_float(job, "timeout_seconds")
    if _require_int(job, "memory_limit_mb") <= 0:
        raise ValueError(f"{context_name(job)} invalid memory limit")


def _run_candidate(job: Mapping[str, object]) -> dict[str, object]:
    _validate_job(job)
    config = load_piston_executor_config(PISTON_CONFIG)
    policy = load_piston_transport_policy(TRANSPORT_POLICY)
    executor = PistonExecutor(config, transport_policy=policy)
    tests = cast(list[dict[str, Any]], job["tests"])
    timeout_seconds = _require_float(job, "timeout_seconds")
    memory_limit_mb = _require_int(job, "memory_limit_mb")
    function_name = _require_str(job, "execution_function_name")
    solution_results: list[dict[str, object]] = []
    for value in cast(list[object], job["transformed_source_solutions"]):
        solution = _mapping(value, context="transformed source solution")
        solution_sha = _require_str(solution, "transformed_code_sha256")
        code = _require_str(solution, "code")
        try:
            result = executor.execute(code, function_name, tests, timeout_seconds, memory_limit_mb)
            solution_results.append(_sanitize_result(result, solution_sha))
        except PistonTransportError as error:
            solution_results.append(
                {
                    "transformed_code_sha256": solution_sha,
                    "status": "piston_transport_exception",
                    "passed_tests": 0,
                    "total_tests": len(tests),
                    "pass_rate": 0.0,
                    "runtime_ms": 0.0,
                    "test_status_counts": {},
                    "infrastructure_failure_kinds": [f"transport_exception:{error.kind.value}"],
                    "formal_solution_pass": False,
                    "infrastructure_failure": True,
                }
            )
    any_pass = any(result.get("formal_solution_pass") is True for result in solution_results)
    any_infrastructure = any(result.get("infrastructure_failure") is True for result in solution_results)
    if any_pass:
        classification = "formal_pass"
    elif any_infrastructure:
        classification = "infrastructure_blocked"
    else:
        classification = "formal_fail"
    return {
        "candidate_id": _require_str(job, "candidate_id"),
        "candidate_binding_sha256": _require_str(job, "candidate_binding_sha256"),
        "source_name": _require_str(job, "source_name"),
        "canonical_problem_sha256": _require_str(job, "canonical_problem_sha256"),
        "job_sha256": _job_sha(job),
        "test_count": len(tests),
        "solution_count": len(solution_results),
        "classification": classification,
        "solution_results": solution_results,
        "backfill_required": False,
    }


def _read_checkpoint(path: Path, jobs: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    rows = _jsonl(path)
    completed: dict[str, dict[str, object]] = {}
    for row in rows:
        candidate_id = _require_str(row, "candidate_id")
        job = jobs.get(candidate_id)
        if job is None:
            raise ValueError(f"checkpoint contains unknown candidate: {candidate_id}")
        if row.get("job_sha256") != _job_sha(job):
            raise ValueError(f"checkpoint job binding drift: {candidate_id}")
        if candidate_id in completed:
            raise ValueError(f"duplicate checkpoint result: {candidate_id}")
        completed[candidate_id] = row
    return completed


def _compact_manifest(row: Mapping[str, object]) -> dict[str, object]:
    solution_results = row.get("solution_results")
    if not isinstance(solution_results, list):
        raise ValueError("candidate result solution_results drift")
    passing = sorted(
        _require_str(_mapping(value, context="solution result"), "transformed_code_sha256")
        for value in solution_results
        if isinstance(value, dict) and value.get("formal_solution_pass") is True
    )
    infrastructure_kinds = sorted(
        {
            kind
            for value in solution_results
            if isinstance(value, dict)
            for kind in cast(list[object], value.get("infrastructure_failure_kinds", []))
            if isinstance(kind, str)
        }
    )
    return {
        "candidate_id": _require_str(row, "candidate_id"),
        "candidate_binding_sha256": _require_str(row, "candidate_binding_sha256"),
        "source_name": _require_str(row, "source_name"),
        "canonical_problem_sha256": _require_str(row, "canonical_problem_sha256"),
        "classification": _require_str(row, "classification"),
        "passing_solution_sha256": passing,
        "infrastructure_failure_kinds": infrastructure_kinds,
        "backfill_required": False,
    }


def run(jobs_path: Path, output_dir: Path, workers: int) -> dict[str, object]:
    if workers <= 0 or workers > 32:
        raise ValueError("workers must be in [1, 32]")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite completed C19 report: {report_path}")

    job_rows = _jsonl(jobs_path)
    if len(job_rows) != 1167:
        raise ValueError(f"C19 expected 1167 jobs, got {len(job_rows)}")
    jobs: dict[str, Mapping[str, object]] = {}
    for row in job_rows:
        _validate_job(row)
        candidate_id = _require_str(row, "candidate_id")
        if candidate_id in jobs:
            raise ValueError(f"duplicate C19 candidate: {candidate_id}")
        jobs[candidate_id] = row

    probe = PistonExecutor(
        load_piston_executor_config(PISTON_CONFIG),
        transport_policy=load_piston_transport_policy(TRANSPORT_POLICY),
    )
    runtime = probe.validate_runtime()

    checkpoint_path = output_dir / "checkpoint_results.jsonl"
    completed = _read_checkpoint(checkpoint_path, jobs)
    pending = [candidate_id for candidate_id in sorted(jobs) if candidate_id not in completed]
    if pending:
        with (
            checkpoint_path.open("a", encoding="utf-8") as checkpoint_handle,
            ThreadPoolExecutor(max_workers=workers) as pool,
        ):
            future_map: dict[Future[dict[str, object]], str] = {
                pool.submit(_run_candidate, jobs[candidate_id]): candidate_id for candidate_id in pending
            }
            for future in as_completed(future_map):
                candidate_id = future_map[future]
                result = future.result()
                if result.get("candidate_id") != candidate_id:
                    raise ValueError("C19 worker candidate identity drift")
                payload = canonical_json(result) + "\n"
                checkpoint_handle.write(payload)
                checkpoint_handle.flush()
                os.fsync(checkpoint_handle.fileno())
                completed[candidate_id] = result
                print(
                    canonical_json(
                        {
                            "candidate_id": candidate_id,
                            "classification": result["classification"],
                            "completed": len(completed),
                            "total": len(jobs),
                        }
                    ),
                    flush=True,
                )

    if set(completed) != set(jobs):
        raise ValueError("C19 checkpoint does not cover all jobs")
    ordered = [completed[candidate_id] for candidate_id in sorted(completed)]
    counts = Counter(_require_str(row, "classification") for row in ordered)
    if set(counts) - {"formal_pass", "formal_fail", "infrastructure_blocked"}:
        raise ValueError("C19 result classification drift")

    passers = [_compact_manifest(row) for row in ordered if row.get("classification") == "formal_pass"]
    failures = [_compact_manifest(row) for row in ordered if row.get("classification") == "formal_fail"]
    blocked = [_compact_manifest(row) for row in ordered if row.get("classification") == "infrastructure_blocked"]
    source_pass_counts = Counter(_require_str(row, "source_name") for row in passers)
    source_fail_counts = Counter(_require_str(row, "source_name") for row in failures)
    source_blocked_counts = Counter(_require_str(row, "source_name") for row in blocked)

    results_sha = _write_jsonl(output_dir / "candidate_results.jsonl", ordered)
    passers_sha = _write_jsonl(output_dir / "formal_passers.jsonl", passers)
    failures_sha = _write_jsonl(output_dir / "formal_failures.jsonl", failures)
    blocked_sha = _write_jsonl(output_dir / "infrastructure_blocked.jsonl", blocked)
    checkpoint_sha = _sha(checkpoint_path)
    report: dict[str, object] = {
        "schema_version": "wp9c-ready-final-formal-piston-v1",
        "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
        "formal_gate": True,
        "jobs_input_count": len(jobs),
        "formal_pass_count": counts["formal_pass"],
        "formal_fail_count": counts["formal_fail"],
        "infrastructure_blocked_count": counts["infrastructure_blocked"],
        "formal_admitted_ready_count": counts["formal_pass"],
        "correctness_failures_dropped_without_backfill": counts["formal_fail"],
        "infrastructure_blocked_not_counted_as_correctness_failure": counts["infrastructure_blocked"],
        "source_pass_counts": dict(sorted(source_pass_counts.items())),
        "source_fail_counts": dict(sorted(source_fail_counts.items())),
        "source_infrastructure_blocked_counts": dict(sorted(source_blocked_counts.items())),
        "piston_runtime": runtime,
        "workers": workers,
        "candidate_pass_rule": "any_transformable_accepted_source_solution_passes_all_frozen_tests",
        "correctness_failure_rule": (
            "all_transformable_source_solutions_complete_without_infrastructure_failure_and_none_pass"
        ),
        "infrastructure_block_rule": "no_solution_passes_and_at_least_one_source_solution_has_infrastructure_failure",
        "backfill_required": False,
        "minimum_pass_count": None,
        "artifact_sha256": {
            "checkpoint_results": checkpoint_sha,
            "candidate_results": results_sha,
            "formal_passers": passers_sha,
            "formal_failures": failures_sha,
            "infrastructure_blocked": blocked_sha,
        },
        "input_bindings": {
            "piston_jobs_sha256": _sha(jobs_path),
            "piston_config_sha256": _sha(PISTON_CONFIG),
            "piston_transport_policy_sha256": _sha(TRANSPORT_POLICY),
            "runner_sha256": _sha(Path(__file__)),
        },
    }
    payload = canonical_json(report) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    (output_dir / "report.sha256").write_text(
        hashlib.sha256(payload.encode("utf-8")).hexdigest() + "\n",
        encoding="ascii",
    )
    print(payload, end="")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(args.jobs.resolve(), args.output.resolve(), args.workers)


if __name__ == "__main__":
    main()
