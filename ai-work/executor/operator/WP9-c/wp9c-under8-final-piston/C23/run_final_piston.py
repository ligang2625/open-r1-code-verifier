#!/usr/bin/env python3
"""Run C23 final formal Piston for frozen exact-8 under8 candidates."""

from __future__ import annotations

import argparse
import hashlib
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.piston import PistonExecutor, PistonTransportError, load_piston_executor_config
from code_verifier.execution.piston_resilience import load_piston_transport_policy

ROOT = Path(__file__).resolve().parents[6]
PISTON_CONFIG = ROOT / "configs/execution/piston-local.yaml"
TRANSPORT_POLICY = ROOT / "configs/execution/piston-transport-resilience.yaml"
ENTRY = "__wp9c_reference_entry__"
EXPECTED_JOBS = 572
EXPECTED_TESTS = 8
EXPECTED_ORACLES = 2


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


def _str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{_name(row)}.{key} must be a non-empty string")
    return value


def _int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{_name(row)}.{key} must be an integer")
    return value


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = loads_strict(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
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


def _sanitize(result: ExecutionResult, oracle_sha: str) -> dict[str, object]:
    infra = _infra_kinds(result)
    return {
        "transformed_code_sha256": oracle_sha,
        "status": result.status.value,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "pass_rate": result.pass_rate,
        "runtime_ms": result.runtime_ms,
        "test_status_counts": dict(sorted(Counter(item.status.value for item in result.test_results).items())),
        "infrastructure_failure_kinds": infra,
        "formal_solution_pass": (
            result.status is ExecutionStatus.PASSED
            and result.passed_tests == EXPECTED_TESTS
            and result.total_tests == EXPECTED_TESTS
        ),
        "infrastructure_failure": bool(infra),
    }


def _validate_job(job: Mapping[str, object]) -> None:
    _str(job, "candidate_id")
    _str(job, "candidate_binding_sha256")
    _str(job, "source_name")
    if _str(job, "execution_function_name") != ENTRY:
        raise ValueError(f"{_name(job)} execution entry drift")
    if _str(job, "formal_pass_rule") != "both_frozen_qualified_oracles_pass_all_final_exact8_tests":
        raise ValueError(f"{_name(job)} formal pass rule drift")
    if _int(job, "test_count") != EXPECTED_TESTS or _int(job, "oracle_pair_size") != EXPECTED_ORACLES:
        raise ValueError(f"{_name(job)} exact test/oracle count drift")
    tests = job.get("tests")
    if not isinstance(tests, list) or len(tests) != EXPECTED_TESTS:
        raise ValueError(f"{_name(job)} final tests drift")
    hashes = [stable_json_hash(value) for value in tests]
    if len(set(hashes)) != EXPECTED_TESTS or stable_json_hash(tests) != job.get("frozen_tests_sha256"):
        raise ValueError(f"{_name(job)} final test digest drift")
    pair = job.get("oracle_pair")
    if not isinstance(pair, list) or len(pair) != EXPECTED_ORACLES:
        raise ValueError(f"{_name(job)} oracle pair drift")
    oracle_hashes: list[str] = []
    for value in pair:
        oracle = _mapping(value, context=f"{_name(job)} oracle")
        code = _str(oracle, "code")
        digest = _str(oracle, "transformed_code_sha256")
        if hashlib.sha256(code.encode("utf-8")).hexdigest() != digest:
            raise ValueError(f"{_name(job)} oracle code digest drift")
        oracle_hashes.append(digest)
    if oracle_hashes != sorted(set(oracle_hashes)):
        raise ValueError(f"{_name(job)} oracle ordering/uniqueness drift")


def _run_candidate(job: Mapping[str, object]) -> dict[str, object]:
    _validate_job(job)
    executor = PistonExecutor(
        load_piston_executor_config(PISTON_CONFIG),
        transport_policy=load_piston_transport_policy(TRANSPORT_POLICY),
    )
    tests = cast(list[dict[str, Any]], job["tests"])
    pair = cast(list[object], job["oracle_pair"])
    solution_results: list[dict[str, object]] = []
    for value in pair:
        oracle = _mapping(value, context=f"{_name(job)} oracle")
        code = _str(oracle, "code")
        oracle_sha = _str(oracle, "transformed_code_sha256")
        try:
            result = executor.execute(code, ENTRY, tests, 2.0, 512)
            sanitized = _sanitize(result, oracle_sha)
        except PistonTransportError as error:
            sanitized = {
                "transformed_code_sha256": oracle_sha,
                "status": "piston_transport_exception",
                "passed_tests": 0,
                "total_tests": EXPECTED_TESTS,
                "pass_rate": 0.0,
                "runtime_ms": 0.0,
                "test_status_counts": {},
                "infrastructure_failure_kinds": [f"transport_exception:{error.kind.value}"],
                "formal_solution_pass": False,
                "infrastructure_failure": True,
            }
        solution_results.append(sanitized)

    passing = sum(value["formal_solution_pass"] is True for value in solution_results)
    any_infra = any(value["infrastructure_failure"] is True for value in solution_results)
    if passing == EXPECTED_ORACLES:
        classification = "formal_pass"
    elif any_infra:
        classification = "infrastructure_blocked"
    else:
        classification = "formal_fail"
    return {
        "candidate_id": _str(job, "candidate_id"),
        "candidate_binding_sha256": _str(job, "candidate_binding_sha256"),
        "source_name": _str(job, "source_name"),
        "job_sha256": _job_sha(job),
        "frozen_tests_sha256": _str(job, "frozen_tests_sha256"),
        "c22_context_passer_sha256": _str(job, "c22_context_passer_sha256"),
        "classification": classification,
        "test_count": EXPECTED_TESTS,
        "oracle_pair_size": EXPECTED_ORACLES,
        "passing_oracle_count": passing,
        "solution_results": solution_results,
        "backfill_required": False,
    }


def _read_checkpoint(path: Path, jobs: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    completed: dict[str, dict[str, object]] = {}
    for row in _jsonl(path):
        candidate_id = _str(row, "candidate_id")
        job = jobs.get(candidate_id)
        if job is None or row.get("job_sha256") != _job_sha(job):
            raise ValueError(f"checkpoint job binding drift: {candidate_id}")
        if candidate_id in completed:
            raise ValueError(f"duplicate checkpoint candidate: {candidate_id}")
        completed[candidate_id] = row
    return completed


def _compact(row: Mapping[str, object]) -> dict[str, object]:
    results = row.get("solution_results")
    if not isinstance(results, list):
        raise ValueError("solution results drift")
    infra = sorted(
        {
            kind
            for value in results
            if isinstance(value, dict)
            for kind in cast(list[object], value.get("infrastructure_failure_kinds", []))
            if isinstance(kind, str)
        }
    )
    return {
        "candidate_id": _str(row, "candidate_id"),
        "candidate_binding_sha256": _str(row, "candidate_binding_sha256"),
        "source_name": _str(row, "source_name"),
        "frozen_tests_sha256": _str(row, "frozen_tests_sha256"),
        "c22_context_passer_sha256": _str(row, "c22_context_passer_sha256"),
        "classification": _str(row, "classification"),
        "passing_oracle_count": _int(row, "passing_oracle_count"),
        "infrastructure_failure_kinds": infra,
        "backfill_required": False,
    }


def run(jobs_path: Path, output_dir: Path, workers: int) -> dict[str, object]:
    if not 1 <= workers <= 32:
        raise ValueError("workers must be in [1, 32]")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite completed C23 report: {report_path}")

    job_rows = _jsonl(jobs_path)
    if len(job_rows) != EXPECTED_JOBS:
        raise ValueError(f"C23 expected {EXPECTED_JOBS} jobs, got {len(job_rows)}")
    jobs: dict[str, Mapping[str, object]] = {}
    for row in job_rows:
        _validate_job(row)
        candidate_id = _str(row, "candidate_id")
        if candidate_id in jobs:
            raise ValueError(f"duplicate C23 candidate: {candidate_id}")
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
                    raise ValueError("C23 worker candidate identity drift")
                checkpoint_handle.write(canonical_json(result) + "\n")
                checkpoint_handle.flush()
                os.fsync(checkpoint_handle.fileno())
                completed[candidate_id] = result
                print(
                    canonical_json(
                        {
                            "candidate_id": candidate_id,
                            "classification": result["classification"],
                            "passing_oracles": result["passing_oracle_count"],
                            "completed": len(completed),
                            "total": len(jobs),
                        }
                    ),
                    flush=True,
                )

    if set(completed) != set(jobs):
        raise ValueError("C23 checkpoint does not cover all jobs")
    ordered = [completed[candidate_id] for candidate_id in sorted(completed)]
    counts = Counter(_str(row, "classification") for row in ordered)
    if set(counts) - {"formal_pass", "formal_fail", "infrastructure_blocked"}:
        raise ValueError("C23 classification drift")

    passers = [_compact(row) for row in ordered if row.get("classification") == "formal_pass"]
    failures = [_compact(row) for row in ordered if row.get("classification") == "formal_fail"]
    blocked = [_compact(row) for row in ordered if row.get("classification") == "infrastructure_blocked"]
    source_pass = Counter(_str(row, "source_name") for row in passers)
    source_fail = Counter(_str(row, "source_name") for row in failures)
    source_blocked = Counter(_str(row, "source_name") for row in blocked)
    passing_oracle_hist = Counter(_int(row, "passing_oracle_count") for row in ordered)
    solution_statuses = Counter(
        cast(str, value["status"])
        for row in ordered
        for value in cast(list[dict[str, object]], row["solution_results"])
    )

    candidate_sha = _write_jsonl(output_dir / "candidate_results.jsonl", ordered)
    pass_sha = _write_jsonl(output_dir / "formal_passers.jsonl", passers)
    fail_sha = _write_jsonl(output_dir / "formal_failures.jsonl", failures)
    blocked_sha = _write_jsonl(output_dir / "infrastructure_blocked.jsonl", blocked)
    report: dict[str, object] = {
        "schema_version": "wp9c-under8-final-formal-piston-v1",
        "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
        "jobs_input_count": EXPECTED_JOBS,
        "formal_pass_count": counts["formal_pass"],
        "formal_fail_count": counts["formal_fail"],
        "infrastructure_blocked_count": counts["infrastructure_blocked"],
        "source_pass_counts": dict(sorted(source_pass.items())),
        "source_fail_counts": dict(sorted(source_fail.items())),
        "source_infrastructure_blocked_counts": dict(sorted(source_blocked.items())),
        "passing_oracle_count_histogram": {str(key): value for key, value in sorted(passing_oracle_hist.items())},
        "solution_status_counts": dict(sorted(solution_statuses.items())),
        "piston_runtime": runtime,
        "workers": workers,
        "test_count_exact": EXPECTED_TESTS,
        "oracle_pair_size_exact": EXPECTED_ORACLES,
        "formal_pass_rule": "both_frozen_qualified_oracles_pass_all_final_exact8_tests",
        "correctness_retry_allowed": False,
        "backfill_required": False,
        "minimum_pass_count": None,
        "next_gate": "final_reduced_pool_assembly_and_informativeness_accounting",
        "artifact_sha256": {
            "checkpoint_results": _sha(checkpoint_path),
            "candidate_results": candidate_sha,
            "formal_passers": pass_sha,
            "formal_failures": fail_sha,
            "infrastructure_blocked": blocked_sha,
        },
        "input_bindings": {
            "final_piston_jobs_sha256": _sha(jobs_path),
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
