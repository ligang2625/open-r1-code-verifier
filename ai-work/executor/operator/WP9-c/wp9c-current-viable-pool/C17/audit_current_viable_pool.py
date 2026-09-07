#!/usr/bin/env python3
"""Freeze the reduced-quota WP9-c pool from already-published C12/C13/C16 evidence."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.json_strict import loads_strict

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CONFIG = ROOT / "configs/data/wp9c-current-viable-pool-freeze.yaml"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
    return _sha(path)


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _require_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string field {key}")
    return value


def _verified_report(path: Path, expected_sha: object, schema: str) -> dict[str, object]:
    if not isinstance(expected_sha, str) or _sha(path) != expected_sha:
        raise ValueError(f"report digest mismatch: {path}")
    report = _json(path)
    if report.get("schema_version") != schema:
        raise ValueError(f"report schema mismatch: {path}")
    return report


def _validate_policy(config: Mapping[str, object]) -> None:
    if config.get("version") != "wp9c-current-viable-pool-freeze-v1":
        raise ValueError("reduced-pool config version drift")
    if config.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("reduced-pool protocol drift")
    decision = _mapping(config.get("user_decision"), context="user decision")
    if (
        decision.get("fixed_external_new_exact_quota_withdrawn") is not True
        or decision.get("keep_all_currently_viable_candidates") is not True
        or decision.get("minimum_external_new_count") is not None
        or decision.get("unresolved_or_unavailable_candidates_may_be_dropped") is not True
        or decision.get("backfill_required") is not False
        or decision.get("source_expansion_allowed") is not False
    ):
        raise ValueError("reduced-quota user decision drift")
    for key in (
        "single_oracle_relaxation_allowed",
        "quality_threshold_relaxation_allowed",
        "provenance_threshold_relaxation_allowed",
        "context_threshold_relaxation_allowed",
        "piston_threshold_relaxation_allowed",
        "informativeness_threshold_relaxation_allowed",
    ):
        if decision.get(key) is not False:
            raise ValueError(f"forbidden relaxation enabled: {key}")
    isolation = _mapping(config.get("isolation"), context="isolation")
    if any(value is not False for value in isolation.values()):
        raise ValueError("C17 freeze must not execute, download, generate, train, or add supply")


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C17 output: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_policy(config)
    bindings = _mapping(config.get("bindings"), context="bindings")
    expected = _mapping(config.get("expected"), context="expected")

    c12_report_path = Path(_require_str(bindings, "c12_report"))
    c12 = _verified_report(
        c12_report_path,
        bindings.get("c12_report_sha256"),
        "wp9c-fixed-2505-candidate-freeze-v1",
    )
    c12_candidates_path = Path(_require_str(bindings, "c12_candidates"))
    if _sha(c12_candidates_path) != bindings.get("c12_candidates_sha256"):
        raise ValueError("C12 candidate manifest digest drift")
    if c12.get("manifest_sha256") != bindings.get("c12_candidates_sha256"):
        raise ValueError("C12 report/manifest binding drift")

    c13_report_path = Path(_require_str(bindings, "c13_report"))
    c13 = _verified_report(
        c13_report_path,
        bindings.get("c13_report_sha256"),
        "wp9c-under8-augmentation-design-v1",
    )
    c13_jobs_path = Path(_require_str(bindings, "c13_jobs"))
    if _sha(c13_jobs_path) != bindings.get("c13_jobs_sha256"):
        raise ValueError("C13 jobs digest drift")
    if c13.get("jobs_sha256") != bindings.get("c13_jobs_sha256"):
        raise ValueError("C13 report/jobs binding drift")

    c16_path = ROOT / _require_str(bindings, "c16_checkpoint")
    if _sha(c16_path) != bindings.get("c16_checkpoint_sha256"):
        raise ValueError("C16 checkpoint digest drift")
    c16 = _json(c16_path)
    c16_output = _mapping(c16.get("verified_output"), context="C16 verified output")
    if (
        c16.get("status") != "completed_no_exact_lineage"
        or c16_output.get("lineage_unmatched") != 541
        or c16_output.get("second_oracle_static_candidate_count") != 0
    ):
        raise ValueError("C16 completed no-lineage evidence drift")

    candidates = _jsonl(c12_candidates_path)
    if len(candidates) != expected.get("frozen_candidate_universe") or len(candidates) != 2505:
        raise ValueError("C12 frozen-universe count drift")
    candidate_by_id: dict[str, dict[str, object]] = {}
    class_counts: Counter[str] = Counter()
    for row in candidates:
        candidate_id = _require_str(row, "candidate_id")
        if candidate_id in candidate_by_id:
            raise ValueError(f"duplicate C12 candidate ID: {candidate_id}")
        candidate_by_id[candidate_id] = row
        class_counts[_require_str(row, "supply_class")] += 1
    if class_counts != Counter({"ready": 1276, "under8": 1229}):
        raise ValueError(f"C12 class count drift: {dict(class_counts)}")

    jobs = _jsonl(c13_jobs_path)
    if len(jobs) != expected.get("under8_total") or len(jobs) != 1229:
        raise ValueError("C13 under8 job count drift")
    jobs_by_id: dict[str, dict[str, object]] = {}
    for job in jobs:
        candidate_id = _require_str(job, "candidate_id")
        if candidate_id in jobs_by_id:
            raise ValueError(f"duplicate C13 job ID: {candidate_id}")
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None or candidate.get("supply_class") != "under8":
            raise ValueError(f"C13 job not bound to C12 under8 row: {candidate_id}")
        if job.get("candidate_binding_sha256") != candidate.get("candidate_binding_sha256"):
            raise ValueError(f"C13/C12 candidate binding drift: {candidate_id}")
        jobs_by_id[candidate_id] = job
    under8_ids = {candidate_id for candidate_id, row in candidate_by_id.items() if row["supply_class"] == "under8"}
    if set(jobs_by_id) != under8_ids:
        raise ValueError("C13 jobs do not exactly cover C12 under8 IDs")

    viable: list[dict[str, object]] = []
    dropped: list[dict[str, object]] = []
    ready_gates = list(cast(list[object], _mapping(config["remaining_gates"], context="remaining gates")["ready"]))
    under8_gates = list(cast(list[object], _mapping(config["remaining_gates"], context="remaining gates")["under8"]))

    for candidate_id in sorted(candidate_by_id):
        row = candidate_by_id[candidate_id]
        supply_class = _require_str(row, "supply_class")
        source_name = str(row.get("source_name"))
        if supply_class == "ready":
            if (
                row.get("formal_context_eligible") is not True
                or row.get("requires_test_augmentation") is not False
                or row.get("requires_final_piston") is not True
            ):
                raise ValueError(f"ready row contract drift: {candidate_id}")
            viable.append(
                {
                    **row,
                    "reduced_pool_lane": "ready_for_final_piston",
                    "formal_eligible": False,
                    "remaining_gates": ready_gates,
                    "no_backfill_if_later_gate_fails": True,
                }
            )
            continue

        job = jobs_by_id[candidate_id]
        blockers = job.get("static_blockers")
        if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
            raise ValueError(f"C13 blocker schema drift: {candidate_id}")
        static_ready = job.get("static_augmentation_ready") is True
        provenance_blocked = job.get("formal_admission_provenance_blocked") is True
        if static_ready and not provenance_blocked and blockers == []:
            viable.append(
                {
                    **row,
                    "reduced_pool_lane": "ready_for_augmentation_execution",
                    "formal_eligible": False,
                    "c13_job_sha256": hashlib.sha256(canonical_json(job).encode()).hexdigest(),
                    "transformable_source_solution_count": job.get("transformable_source_solution_count"),
                    "proposal_count": job.get("proposal_count"),
                    "additional_tests_required": job.get("additional_tests_required"),
                    "remaining_gates": under8_gates,
                    "no_backfill_if_later_gate_fails": True,
                }
            )
            continue

        reasons = list(cast(list[str], blockers))
        if provenance_blocked:
            reasons.append("formal_admission_provenance_not_closed")
            if source_name == "deepcoder-primeintellect":
                reasons.append("c16_exact_response_lineage_unmatched")
        if not reasons:
            reasons.append("c13_static_augmentation_not_ready")
        dropped.append(
            {
                "candidate_id": candidate_id,
                "candidate_binding_sha256": row.get("candidate_binding_sha256"),
                "source_name": row.get("source_name"),
                "source_record_id": row.get("source_record_id"),
                "supply_class": supply_class,
                "drop_reasons": sorted(set(reasons)),
                "dropped_by_reduced_quota_protocol": True,
                "backfill_required": False,
            }
        )

    lane_counts = Counter(_require_str(row, "reduced_pool_lane") for row in viable)
    source_counts = Counter(str(row.get("source_name")) for row in viable)
    dropped_source_counts = Counter(str(row.get("source_name")) for row in dropped)
    dropped_reason_counts: Counter[str] = Counter()
    for row in dropped:
        for reason in cast(list[str], row["drop_reasons"]):
            dropped_reason_counts[reason] += 1

    if lane_counts != Counter({"ready_for_final_piston": 1276, "ready_for_augmentation_execution": 638}):
        raise ValueError(f"reduced viable lane count drift: {dict(lane_counts)}")
    if len(viable) != expected.get("current_viable_pool") or len(viable) != 1914:
        raise ValueError("reduced viable pool count drift")
    if len(dropped) != expected.get("under8_dropped") or len(dropped) != 591:
        raise ValueError("reduced dropped count drift")
    if any(
        row.get("supply_class") == "under8" and row.get("source_name") == "deepcoder-primeintellect"
        for row in viable
    ):
        raise ValueError("unresolved DeepCoder-PrimeIntellect under8 row entered reduced viable pool")
    if dropped_source_counts["deepcoder-primeintellect"] != expected.get("deepcoder_primeintellect_dropped"):
        raise ValueError("DeepCoder-PrimeIntellect dropped count drift")
    viable_ids = {_require_str(row, "candidate_id") for row in viable}
    dropped_ids = {_require_str(row, "candidate_id") for row in dropped}
    if viable_ids & dropped_ids or viable_ids | dropped_ids != set(candidate_by_id):
        raise ValueError("reduced pool partition does not cover C12 exactly")

    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        viable_sha = _write_jsonl(temporary / "viable_candidates.jsonl", viable)
        dropped_sha = _write_jsonl(temporary / "dropped_candidates.jsonl", dropped)
        report: dict[str, object] = {
            "schema_version": "wp9c-current-viable-pool-freeze-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "evidence_class": "engineering_reduced_quota_candidate_freeze",
            "formal_eligible": False,
            "source_expansion_stopped": True,
            "fixed_exact_external_new_quota_withdrawn": True,
            "minimum_external_new_count": None,
            "backfill_required": False,
            "current_viable_pipeline_count": len(viable),
            "final_formally_usable_count": 0,
            "lane_counts": dict(sorted(lane_counts.items())),
            "viable_source_counts": dict(sorted(source_counts.items())),
            "dropped_count": len(dropped),
            "dropped_source_counts": dict(sorted(dropped_source_counts.items())),
            "dropped_reason_counts": dict(sorted(dropped_reason_counts.items())),
            "c16_primeintellect_lineage_result": {
                "target_count": 541,
                "unique_lineage": 0,
                "unmatched": 541,
                "second_oracle_static_candidates": 0,
                "action": "drop_from_current_route_without_backfill",
            },
            "remaining_gate_policy": {
                "keep_every_candidate_that_passes_remaining_gates": True,
                "drop_candidate_on_later_gate_failure": True,
                "replace_failed_candidate": False,
                "lower_quality_threshold_to_preserve_count": False,
            },
            "execution_boundaries": {
                "source_solution_execution_run": False,
                "test_generation_run": False,
                "piston_run": False,
                "calibration_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "bindings": {
                "c12_report_sha256": bindings["c12_report_sha256"],
                "c12_candidates_sha256": bindings["c12_candidates_sha256"],
                "c13_report_sha256": bindings["c13_report_sha256"],
                "c13_jobs_sha256": bindings["c13_jobs_sha256"],
                "c16_checkpoint_sha256": bindings["c16_checkpoint_sha256"],
            },
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "audit_script_sha256": _sha(Path(__file__)),
            "artifact_sha256": {
                "viable_candidates": viable_sha,
                "dropped_candidates": dropped_sha,
            },
            "notes": [
                "1914 is the current viable pipeline pool, not the final formally usable count.",
                "1276 ready rows still require final formal function-level Piston.",
                "638 under8 rows still require multi-solution augmentation, final Exact-B, and final Piston.",
                "The 591 dropped under8 rows are not backfilled and no new sources are searched.",
                "No quality, provenance, context, Piston, informativeness, dedup, or multi-oracle gate is relaxed.",
            ],
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(
            hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii"
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
    audit(args.config.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
