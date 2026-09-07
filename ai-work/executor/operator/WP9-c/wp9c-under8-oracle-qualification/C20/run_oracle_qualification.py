#!/usr/bin/env python3
"""Qualify two independent source-solution oracles per frozen under8 candidate."""

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
REQUIRED_QUALIFIED = 2


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


def _name(row: Mapping[str, object]) -> str:
    value = row.get("candidate_id")
    return value if isinstance(value, str) and value else "row"


def _require_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{_name(row)}.{key} must be a non-empty string")
    return value


def _require_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{_name(row)}.{key} must be an integer")
    return value


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


def _sanitize(result: ExecutionResult, solution_sha: str) -> dict[str, object]:
    infrastructure_kinds = _infra_kinds(result)
    return {
        "transformed_code_sha256": solution_sha,
        "status": result.status.value,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "pass_rate": result.pass_rate,
        "runtime_ms": result.runtime_ms,
        "test_status_counts": dict(sorted(Counter(item.status.value for item in result.test_results).items())),
        "infrastructure_failure_kinds": infrastructure_kinds,
        "qualifies_on_existing_tests": (
            result.status is ExecutionStatus.PASSED and result.passed_tests == result.total_tests
        ),
        "infrastructure_failure": bool(infrastructure_kinds),
    }


def _validate_job(job: Mapping[str, object]) -> None:
    _require_str(job, "candidate_id")
    _require_str(job, "candidate_binding_sha256")
    _require_str(job, "source_name")
    if _require_str(job, "execution_function_name") != "__wp9c_reference_entry__":
        raise ValueError(f"{_name(job)} execution entry drift")
    tests = job.get("existing_tests")
    test_count = _require_int(job, "existing_test_count")
    if not isinstance(tests, list) or len(tests) != test_count or not 1 <= test_count <= 7:
        raise ValueError(f"{_name(job)} existing test payload drift")
    for test in tests:
        if not isinstance(test, dict) or set(test) != {"input", "expected"}:
            raise ValueError(f"{_name(job)} existing test schema drift")
    solutions = job.get("transformed_source_solutions")
    solution_count = _require_int(job, "transformed_source_solution_count")
    if not isinstance(solutions, list) or len(solutions) != solution_count or solution_count < REQUIRED_QUALIFIED:
        raise ValueError(f"{_name(job)} transformed solution payload drift")
    hashes: list[str] = []
    for value in solutions:
        solution = _mapping(value, context=f"{_name(job)} transformed solution")
        code = _require_str(solution, "code")
        digest = _require_str(solution, "transformed_code_sha256")
        if hashlib.sha256(code.encode("utf-8")).hexdigest() != digest:
            raise ValueError(f"{_name(job)} transformed solution digest drift")
        hashes.append(digest)
    if hashes != sorted(set(hashes)):
        raise ValueError(f"{_name(job)} transformed solution ordering/uniqueness drift")
    protocol = _mapping(job.get("qualification_protocol"), context=f"{_name(job)} qualification protocol")
    if (
        protocol.get("required_qualified_solutions") != REQUIRED_QUALIFIED
        or protocol.get("stop_after_required_qualified_solutions") is not True
        or protocol.get("solution_order") != "transformed_code_sha256_ascending"
        or protocol.get("correctness_retry_allowed") is not False
    ):
        raise ValueError(f"{_name(job)} qualification protocol drift")


def _run_candidate(job: Mapping[str, object]) -> dict[str, object]:
    _validate_job(job)
    executor = PistonExecutor(
        load_piston_executor_config(PISTON_CONFIG),
        transport_policy=load_piston_transport_policy(TRANSPORT_POLICY),
    )
    tests = cast(list[dict[str, Any]], job["existing_tests"])
    solutions = cast(list[object], job["transformed_source_solutions"])
    results: list[dict[str, object]] = []
    qualified: list[str] = []
    any_infrastructure = False
    for solution_value in solutions:
        solution = _mapping(solution_value, context="transformed source solution")
        solution_sha = _require_str(solution, "transformed_code_sha256")
        code = _require_str(solution, "code")
        try:
            execution = executor.execute(code, "__wp9c_reference_entry__", tests, 2.0, 512)
            result = _sanitize(execution, solution_sha)
        except PistonTransportError as error:
            result = {
                "transformed_code_sha256": solution_sha,
                "status": "piston_transport_exception",
                "passed_tests": 0,
                "total_tests": len(tests),
                "pass_rate": 0.0,
                "runtime_ms": 0.0,
                "test_status_counts": {},
                "infrastructure_failure_kinds": [f"transport_exception:{error.kind.value}"],
                "qualifies_on_existing_tests": False,
                "infrastructure_failure": True,
            }
        results.append(result)
        if result["infrastructure_failure"] is True:
            any_infrastructure = True
        if result["qualifies_on_existing_tests"] is True:
            qualified.append(solution_sha)
            if len(qualified) == REQUIRED_QUALIFIED:
                break

    if len(qualified) == REQUIRED_QUALIFIED:
        classification = "oracle_pair_qualified"
    elif any_infrastructure:
        classification = "infrastructure_blocked"
    else:
        classification = "oracle_pair_fail"
    exhausted_all_solutions = len(results) == len(solutions)
    if classification != "oracle_pair_qualified" and not exhausted_all_solutions:
        raise ValueError(f"{_name(job)} non-qualified candidate did not exhaust all solutions")
    return {
        "candidate_id": _require_str(job, "candidate_id"),
        "candidate_binding_sha256": _require_str(job, "candidate_binding_sha256"),
        "source_name": _require_str(job, "source_name"),
        "c13_job_sha256": _require_str(job, "c13_job_sha256"),
        "job_sha256": _job_sha(job),
        "existing_test_count": len(tests),
        "available_solution_count": len(solutions),
        "attempted_solution_count": len(results),
        "qualified_solution_sha256": qualified,
        "classification": classification,
        "exhausted_all_solutions": exhausted_all_solutions,
        "solution_results": results,
        "additional_tests_required": _require_int(job, "additional_tests_required"),
        "proposal_count": _require_int(job, "proposal_count"),
        "input_proposals_sha256": _require_str(job, "input_proposals_sha256"),
        "backfill_required": False,
    }


def _read_checkpoint(path: Path, jobs: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    completed: dict[str, dict[str, object]] = {}
    for row in _jsonl(path):
        candidate_id = _require_str(row, "candidate_id")
        job = jobs.get(candidate_id)
        if job is None or row.get("job_sha256") != _job_sha(job):
            raise ValueError(f"checkpoint job binding drift: {candidate_id}")
        if candidate_id in completed:
            raise ValueError(f"duplicate checkpoint candidate: {candidate_id}")
        completed[candidate_id] = row
    return completed


def _compact(row: Mapping[str, object]) -> dict[str, object]:
    qualified = row.get("qualified_solution_sha256")
    if not isinstance(qualified, list) or any(not isinstance(value, str) for value in qualified):
        raise ValueError("qualified solution SHA payload drift")
    solution_results = row.get("solution_results")
    if not isinstance(solution_results, list):
        raise ValueError("solution result payload drift")
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
        "c13_job_sha256": _require_str(row, "c13_job_sha256"),
        "classification": _require_str(row, "classification"),
        "qualified_solution_sha256": qualified,
        "attempted_solution_count": _require_int(row, "attempted_solution_count"),
        "available_solution_count": _require_int(row, "available_solution_count"),
        "existing_test_count": _require_int(row, "existing_test_count"),
        "additional_tests_required": _require_int(row, "additional_tests_required"),
        "proposal_count": _require_int(row, "proposal_count"),
        "input_proposals_sha256": _require_str(row, "input_proposals_sha256"),
        "infrastructure_failure_kinds": infrastructure_kinds,
        "backfill_required": False,
    }


def run(jobs_path: Path, output_dir: Path, workers: int) -> dict[str, object]:
    if not 1 <= workers <= 32:
        raise ValueError("workers must be in [1, 32]")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite completed C20 report: {report_path}")

    job_rows = _jsonl(jobs_path)
    if len(job_rows) != 638:
        raise ValueError(f"C20 expected 638 jobs, got {len(job_rows)}")
    jobs: dict[str, Mapping[str, object]] = {}
    for row in job_rows:
        _validate_job(row)
        candidate_id = _require_str(row, "candidate_id")
        if candidate_id in jobs:
            raise ValueError(f"duplicate C20 candidate: {candidate_id}")
        jobs[candidate_id] = row

    runtime = PistonExecutor(
        load_piston_executor_config(PISTON_CONFIG),
        transport_policy=load_piston_transport_policy(TRANSPORT_POLICY),
    ).validate_runtime()

    checkpoint_path = output_dir / "checkpoint_results.jsonl"
    completed = _read_checkpoint(checkpoint_path, jobs)
    pending = [candidate_id for candidate_id in sorted(jobs) if candidate_id not in completed]
    if pending:
        with (
            checkpoint_path.open("a", encoding="utf-8") as checkpoint_handle,
            ThreadPoolExecutor(max_workers=workers) as pool,
        ):
            futures: dict[Future[dict[str, object]], str] = {
                pool.submit(_run_candidate, jobs[candidate_id]): candidate_id for candidate_id in pending
            }
            for future in as_completed(futures):
                candidate_id = futures[future]
                result = future.result()
                if result.get("candidate_id") != candidate_id:
                    raise ValueError("C20 worker candidate identity drift")
                checkpoint_handle.write(canonical_json(result) + "\n")
                checkpoint_handle.flush()
                os.fsync(checkpoint_handle.fileno())
                completed[candidate_id] = result
                print(
                    canonical_json(
                        {
                            "candidate_id": candidate_id,
                            "classification": result["classification"],
                            "attempted_solution_count": result["attempted_solution_count"],
                            "completed": len(completed),
                            "total": len(jobs),
                        }
                    ),
                    flush=True,
                )

    if set(completed) != set(jobs):
        raise ValueError("C20 checkpoint does not cover all jobs")
    ordered = [completed[candidate_id] for candidate_id in sorted(completed)]
    counts = Counter(_require_str(row, "classification") for row in ordered)
    if set(counts) - {"oracle_pair_qualified", "oracle_pair_fail", "infrastructure_blocked"}:
        raise ValueError("C20 classification drift")
    qualified = [_compact(row) for row in ordered if row.get("classification") == "oracle_pair_qualified"]
    failures = [_compact(row) for row in ordered if row.get("classification") == "oracle_pair_fail"]
    blocked = [_compact(row) for row in ordered if row.get("classification") == "infrastructure_blocked"]
    for row in qualified:
        pair = cast(list[str], row["qualified_solution_sha256"])
        if len(pair) != REQUIRED_QUALIFIED or pair != sorted(pair):
            raise ValueError("qualified oracle pair is not the frozen first-two SHA pair")

    source_qualified = Counter(_require_str(row, "source_name") for row in qualified)
    source_failed = Counter(_require_str(row, "source_name") for row in failures)
    source_blocked = Counter(_require_str(row, "source_name") for row in blocked)
    attempted_hist = Counter(_require_int(row, "attempted_solution_count") for row in ordered)
    total_solution_executions = sum(_require_int(row, "attempted_solution_count") for row in ordered)

    results_sha = _write_jsonl(output_dir / "candidate_results.jsonl", ordered)
    qualified_sha = _write_jsonl(output_dir / "oracle_pair_qualified.jsonl", qualified)
    failures_sha = _write_jsonl(output_dir / "oracle_pair_failures.jsonl", failures)
    blocked_sha = _write_jsonl(output_dir / "infrastructure_blocked.jsonl", blocked)
    report: dict[str, object] = {
        "schema_version": "wp9c-under8-existing-test-oracle-qualification-v1",
        "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
        "formal_eligible": False,
        "jobs_input_count": 638,
        "oracle_pair_qualified_count": counts["oracle_pair_qualified"],
        "oracle_pair_fail_count": counts["oracle_pair_fail"],
        "infrastructure_blocked_count": counts["infrastructure_blocked"],
        "source_qualified_counts": dict(sorted(source_qualified.items())),
        "source_fail_counts": dict(sorted(source_failed.items())),
        "source_infrastructure_blocked_counts": dict(sorted(source_blocked.items())),
        "total_solution_executions": total_solution_executions,
        "attempted_solution_count_histogram": {str(k): v for k, v in sorted(attempted_hist.items())},
        "piston_runtime": runtime,
        "workers": workers,
        "required_qualified_solutions": REQUIRED_QUALIFIED,
        "qualified_pair_rule": "first_two_qualifying_solutions_in_frozen_sha_order",
        "candidate_pass_rule": "at_least_two_distinct_accepted_source_solutions_qualify",
        "correctness_retry_allowed": False,
        "backfill_required": False,
        "next_gate": "deterministic_proposal_consensus_for_oracle_pair_qualified_candidates",
        "artifact_sha256": {
            "checkpoint_results": _sha(checkpoint_path),
            "candidate_results": results_sha,
            "oracle_pair_qualified": qualified_sha,
            "oracle_pair_failures": failures_sha,
            "infrastructure_blocked": blocked_sha,
        },
        "input_bindings": {
            "qualification_jobs_sha256": _sha(jobs_path),
            "piston_config_sha256": _sha(PISTON_CONFIG),
            "piston_transport_policy_sha256": _sha(TRANSPORT_POLICY),
            "runner_sha256": _sha(Path(__file__)),
        },
    }
    payload = canonical_json(report) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    (output_dir / "report.sha256").write_text(
        hashlib.sha256(payload.encode("utf-8")).hexdigest() + "\n", encoding="ascii"
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
