#!/usr/bin/env python3
"""Prepare the frozen 638-row under8 source-oracle Piston qualification jobs."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CONFIG = ROOT / "configs/data/wp9c-under8-oracle-qualification.yaml"


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
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _json(path: Path) -> dict[str, object]:
    value = loads_strict(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


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


def _verify(path: Path, expected: object, *, context: str) -> None:
    if not isinstance(expected, str) or _sha(path) != expected:
        raise ValueError(f"{context} digest mismatch: {path}")


def _validate_config(config: Mapping[str, object]) -> None:
    if config.get("version") != "wp9c-under8-existing-test-oracle-qualification-v1":
        raise ValueError("C20 config version drift")
    if config.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("C20 protocol drift")
    decision = _mapping(config.get("user_decision"), context="C20 user decision")
    if (
        decision.get("keep_only_remaining_gate_passers") is not True
        or decision.get("backfill_failed_candidates") is not False
        or decision.get("source_expansion_allowed") is not False
        or decision.get("minimum_under8_pass_count") is not None
        or decision.get("threshold_relaxation_allowed") is not False
    ):
        raise ValueError("C20 user decision drift")
    protocol = _mapping(config.get("qualification_protocol"), context="C20 qualification protocol")
    if (
        protocol.get("solution_order") != "transformed_code_sha256_ascending"
        or protocol.get("required_qualified_solutions") != 2
        or protocol.get("stop_after_required_qualified_solutions") is not True
        or protocol.get("correctness_retry_allowed") is not False
        or protocol.get("transport_safe_retry_only") is not True
    ):
        raise ValueError("C20 qualification protocol drift")
    isolation = _mapping(config.get("isolation"), context="C20 isolation")
    if isolation.get("use_existing_frozen_tests_only") is not True:
        raise ValueError("C20 must use existing frozen tests only")
    for key, value in isolation.items():
        if key != "use_existing_frozen_tests_only" and value is not False:
            raise ValueError(f"C20 isolation drift: {key}")


def prepare(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C20 preparation output: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    bindings = _mapping(config.get("bindings"), context="C20 bindings")
    expected = _mapping(config.get("expected"), context="C20 expected")
    protocol = _mapping(config.get("qualification_protocol"), context="C20 qualification protocol")

    c19_path = ROOT / _require_str(bindings, "c19_checkpoint")
    _verify(c19_path, bindings.get("c19_checkpoint_sha256"), context="C19 checkpoint")
    c19 = _json(c19_path)
    if (
        c19.get("status") != "completed_verified"
        or c19.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1"
        or _mapping(c19.get("verified_result"), context="C19 result").get("ready_lane_final_formal_survivors") != 1030
    ):
        raise ValueError("C19 prerequisite drift")

    for key in ("c13_report", "c13_jobs", "c17_viable_candidates"):
        path = Path(_require_str(bindings, key))
        _verify(path, bindings.get(f"{key}_sha256"), context=key)
    for key in ("piston_config", "piston_transport_policy"):
        path = ROOT / _require_str(bindings, key)
        _verify(path, bindings.get(f"{key}_sha256"), context=key)

    c13_report = _json(Path(_require_str(bindings, "c13_report")))
    if c13_report.get("schema_version") != "wp9c-under8-augmentation-design-v1":
        raise ValueError("C13 report schema drift")
    if (
        c13_report.get("formal_eligible") is not False
        or c13_report.get("generation_or_solution_execution_run") is not False
        or c13_report.get("piston_run") is not False
        or c13_report.get("quality_gate_passed_count") != 0
        or c13_report.get("under8_formal_context_eligible_count") is not None
        or c13_report.get("static_augmentation_ready_count") != 638
    ):
        raise ValueError("C13 execution/gate state drift")

    c13_rows = _jsonl(Path(_require_str(bindings, "c13_jobs")))
    c17_rows = _jsonl(Path(_require_str(bindings, "c17_viable_candidates")))
    selected = [row for row in c13_rows if row.get("static_augmentation_ready") is True]
    c17_under8 = [row for row in c17_rows if row.get("reduced_pool_lane") == "ready_for_augmentation_execution"]
    expected_count = _require_int(expected, "under8_lane")
    if len(selected) != expected_count or len(c17_under8) != expected_count or expected_count != 638:
        raise ValueError("C20 under8 count drift")
    selected_by_id = {_require_str(row, "candidate_id"): row for row in selected}
    c17_by_id = {_require_str(row, "candidate_id"): row for row in c17_under8}
    if len(selected_by_id) != 638 or len(c17_by_id) != 638 or set(selected_by_id) != set(c17_by_id):
        raise ValueError("C13/C17 under8 ID set drift")

    expected_sources = _mapping(expected.get("source_counts"), context="C20 expected sources")
    source_counts = Counter(_require_str(row, "source_name") for row in selected)
    expected_source_counts = {key: _require_int(expected_sources, key) for key in expected_sources}
    if dict(sorted(source_counts.items())) != dict(sorted(expected_source_counts.items())):
        raise ValueError(f"C20 source-count drift: {dict(source_counts)}")

    jobs: list[dict[str, object]] = []
    transformed_hist: Counter[int] = Counter()
    test_hist: Counter[int] = Counter()
    for candidate_id in sorted(selected_by_id):
        row = selected_by_id[candidate_id]
        c17_row = c17_by_id[candidate_id]
        if row.get("candidate_binding_sha256") != c17_row.get("candidate_binding_sha256"):
            raise ValueError(f"candidate binding drift: {candidate_id}")
        if row.get("formal_admission_provenance_blocked") is not False:
            raise ValueError(f"provenance is not closed for C20 candidate: {candidate_id}")
        if row.get("quality_gate_passed") is not False or row.get("under8_formal_context_eligible") is not None:
            raise ValueError(f"C20 candidate unexpectedly already passed later gates: {candidate_id}")
        blockers = row.get("static_blockers")
        if blockers != []:
            raise ValueError(f"C20 static blockers are not empty: {candidate_id}")
        existing_tests = row.get("existing_tests")
        existing_test_count = _require_int(row, "existing_test_count")
        if not isinstance(existing_tests, list) or len(existing_tests) != existing_test_count:
            raise ValueError(f"existing test payload drift: {candidate_id}")
        if (
            not _require_int(expected, "existing_test_count_min")
            <= existing_test_count
            <= _require_int(expected, "existing_test_count_max")
        ):
            raise ValueError(f"existing test count outside frozen under8 bounds: {candidate_id}")
        solutions = row.get("transformed_source_solutions")
        transform_count = _require_int(row, "transformable_source_solution_count")
        if not isinstance(solutions, list) or len(solutions) != transform_count:
            raise ValueError(f"transformed solution count drift: {candidate_id}")
        if transform_count < _require_int(expected, "minimum_transformable_source_solutions_per_candidate"):
            raise ValueError(f"C20 candidate lacks two transformable source solutions: {candidate_id}")
        normalized_solutions: list[dict[str, object]] = []
        for value in solutions:
            solution = _mapping(value, context=f"{candidate_id} transformed solution")
            code = _require_str(solution, "transformed_code")
            digest = _require_str(solution, "transformed_code_sha256")
            if hashlib.sha256(code.encode("utf-8")).hexdigest() != digest:
                raise ValueError(f"transformed solution digest drift: {candidate_id}")
            normalized_solutions.append(
                {
                    "transformed_code_sha256": digest,
                    "source_code_sha256": solution.get("source_code_sha256"),
                    "raw_solution_sha256": solution.get("raw_solution_sha256"),
                    "target_kind": solution.get("target_kind"),
                    "target_owner": solution.get("target_owner"),
                    "extraction_mode": solution.get("extraction_mode"),
                    "code": code,
                }
            )
        normalized_solutions.sort(key=lambda item: cast(str, item["transformed_code_sha256"]))
        hashes = [cast(str, item["transformed_code_sha256"]) for item in normalized_solutions]
        if len(hashes) != len(set(hashes)):
            raise ValueError(f"duplicate transformed solution SHA: {candidate_id}")
        proposals = row.get("input_proposals")
        proposal_count = _require_int(row, "proposal_count")
        if not isinstance(proposals, list) or len(proposals) != proposal_count:
            raise ValueError(f"proposal payload drift: {candidate_id}")
        if proposal_count < _require_int(row, "additional_tests_required"):
            raise ValueError(f"insufficient proposals slipped into C20: {candidate_id}")

        c13_job_sha = stable_json_hash(row)
        jobs.append(
            {
                "candidate_id": candidate_id,
                "candidate_binding_sha256": row.get("candidate_binding_sha256"),
                "source_name": _require_str(row, "source_name"),
                "source_record_id": _require_str(row, "source_record_id"),
                "function_name": _require_str(row, "function_name"),
                "execution_function_name": "__wp9c_reference_entry__",
                "existing_test_count": existing_test_count,
                "existing_tests": existing_tests,
                "transformed_source_solution_count": len(normalized_solutions),
                "transformed_source_solutions": normalized_solutions,
                "additional_tests_required": _require_int(row, "additional_tests_required"),
                "proposal_count": proposal_count,
                "input_proposals_sha256": stable_json_hash(proposals),
                "c13_job_sha256": c13_job_sha,
                "qualification_protocol": dict(protocol),
                "backfill_on_failure": False,
            }
        )
        transformed_hist[len(normalized_solutions)] += 1
        test_hist[existing_test_count] += 1

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        jobs_sha = _write_jsonl(temporary / "qualification_jobs.jsonl", jobs)
        report: dict[str, object] = {
            "schema_version": "wp9c-under8-oracle-qualification-preparation-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "formal_eligible": False,
            "under8_input_count": 638,
            "qualification_job_count": len(jobs),
            "source_counts": dict(sorted(source_counts.items())),
            "existing_test_count_histogram": {str(k): v for k, v in sorted(test_hist.items())},
            "transformed_solution_count_histogram": {str(k): v for k, v in sorted(transformed_hist.items())},
            "qualification_protocol": dict(protocol),
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "preparation_script_sha256": _sha(Path(__file__)),
            "artifact_sha256": {"qualification_jobs": jobs_sha},
            "execution_boundaries": {
                "source_solution_execution_run": False,
                "piston_run": False,
                "input_proposals_executed": False,
                "tests_generated": False,
                "final_exact_b_run": False,
                "final_formal_piston_run": False,
                "calibration_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "next_gate": "manual_existing_test_piston_qualification_until_two_oracles_per_candidate",
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(
            hashlib.sha256(payload.encode("utf-8")).hexdigest() + "\n", encoding="ascii"
        )
        temporary.rename(output_dir)
        print(payload, end="")
        return report
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.config.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
