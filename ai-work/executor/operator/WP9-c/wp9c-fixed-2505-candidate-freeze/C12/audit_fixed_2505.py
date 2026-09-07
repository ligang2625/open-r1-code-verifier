#!/usr/bin/env python3
"""Freeze the existing WP9-c 2505 planning universe without rescanning sources."""

from __future__ import annotations

import argparse
import hashlib
import json
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
C11_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/checkpoint.json"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            value = loads_strict(raw_line.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
    return _sha(path)


def _verified_report(path: Path, expected_sha: object, *, schema: str) -> dict[str, object]:
    if not isinstance(expected_sha, str) or _sha(path) != expected_sha:
        raise ValueError(f"report digest mismatch: {path}")
    report = _json(path)
    if report.get("schema_version") != schema:
        raise ValueError(f"report schema mismatch: {path}")
    return report


def _verify_artifact(report: Mapping[str, object], report_path: Path, key: str, name: str) -> Path:
    digests = report.get("artifact_sha256")
    if not isinstance(digests, dict) or not isinstance(digests.get(key), str):
        raise ValueError(f"missing artifact digest {key}: {report_path}")
    path = report_path.parent / name
    if _sha(path) != digests[key]:
        raise ValueError(f"artifact digest mismatch: {path}")
    return path


def _binding(fields: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json(dict(fields)).encode("utf-8")).hexdigest()


def _require_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string field {key}")
    return value


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    if config.get("version") != "wp9c-fixed-2505-candidate-freeze-v1":
        raise ValueError("fixed-universe config version mismatch")
    if config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1":
        raise ValueError("active-pool protocol mismatch")
    expected = cast(Mapping[str, object], config.get("expected"))
    evidence = cast(Mapping[str, object], config.get("evidence"))
    policy = cast(Mapping[str, object], config.get("policy"))
    forbidden_true = (
        "source_expansion_allowed",
        "download_allowed",
        "source_rescan_allowed",
        "execute_source_code",
        "execute_tests",
        "generate_tests",
        "run_piston",
        "run_calibration",
        "run_grpo",
        "use_gpu",
        "threshold_relaxation_allowed",
    )
    if any(policy.get(key) is not False for key in forbidden_true):
        raise ValueError("Phase-A freeze must be static-only and source-expansion-free")
    if policy.get("under8_formal_context_eligible_before_augmentation") is not None:
        raise ValueError("under8 formal context eligibility must remain null")

    c11 = _json(C11_CHECKPOINT)
    if c11.get("status") != policy.get("c11_status_required"):
        raise ValueError("C11 is not paused by the current user directive")
    pause = c11.get("pause_directive")
    if (
        not isinstance(pause, dict)
        or pause.get("download_authorized") is not False
        or pause.get("candidate_supply_must_not_change") is not True
        or pause.get("incremental_supply_if_reopened") != policy.get("c11_incremental_supply_if_reopened")
    ):
        raise ValueError("C11 pause directive drift")

    correction_path = Path(_require_str(evidence, "context_correction_report"))
    c7_path = Path(_require_str(evidence, "c7_report"))
    c8_path = Path(_require_str(evidence, "c8_report"))
    c10_path = Path(_require_str(evidence, "c10_report"))
    correction = _verified_report(
        correction_path,
        evidence.get("context_correction_report_sha256"),
        schema="wp9c-function-supply-context-correction-v1",
    )
    c7 = _verified_report(c7_path, evidence.get("c7_report_sha256"), schema="wp9c-taco-under8-supply-audit-v1")
    c8 = _verified_report(c8_path, evidence.get("c8_report_sha256"), schema="wp9c-deepcoder-function-supply-audit-v1")
    c10 = _verified_report(
        c10_path,
        evidence.get("c10_report_sha256"),
        schema="wp9c-openr1-raw-python-provenance-audit-v1",
    )

    corrected_supply = correction.get("corrected_supply")
    c8_supply = c8.get("supply_projection")
    c10_provenance = c10.get("deepcoder_provenance_recovery")
    if not isinstance(corrected_supply, dict) or not isinstance(c8_supply, dict):
        raise ValueError("supply projection is missing")
    if corrected_supply.get("corrected_ready_context_eligible_count") != expected.get("ready"):
        raise ValueError("corrected ready count drift")
    if (
        c8_supply.get("ready_context_eligible_union_before_piston") != expected.get("ready")
        or c8_supply.get("under8_preaugmentation_planning_union") != expected.get("under8")
        or c8_supply.get("zero_attrition_planning_union") != expected.get("total")
        or c8_supply.get("under8_planning_successes_needed_for_exact_2275")
        != expected.get("under8_successes_needed_for_external_new_exact")
    ):
        raise ValueError("C8 fixed-universe counts drift")
    if not isinstance(c10_provenance, dict):
        raise ValueError("C10 provenance summary missing")
    if (
        c10_provenance.get("target_deepcoder_primeintellect_rows") != expected.get("deepcoder_primeintellect_under8")
        or c10_provenance.get("uniquely_matched_rows") != 0
        or c10_provenance.get("ambiguous_rows") != 0
        or c10_provenance.get("unmatched_rows") != expected.get("deepcoder_primeintellect_under8")
    ):
        raise ValueError("C10 strict provenance partition drift")

    correction_ready_path = _verify_artifact(correction, correction_path, "ready_context", "context/ready_new.jsonl")
    correction_under8_path = _verify_artifact(correction, correction_path, "under8_context", "context/under8.jsonl")
    c7_taco_path = _verify_artifact(c7, c7_path, "taco_under8_candidates", "taco_under8_candidates.jsonl")
    c8_deep_path = _verify_artifact(c8, c8_path, "deepcoder_under8_candidates", "deepcoder_under8_candidates.jsonl")
    c8_c7_decisions_path = _verify_artifact(
        c8,
        c8_path,
        "c7_under8_after_deepcoder_decisions",
        "c7_under8_after_deepcoder_decisions.jsonl",
    )

    incumbent_binding = correction.get("incumbent_binding")
    if not isinstance(incumbent_binding, dict):
        raise ValueError("incumbent binding missing")
    incumbent_path = Path(_require_str(incumbent_binding, "canonical_path"))
    if _sha(incumbent_path) != incumbent_binding.get("canonical_digest"):
        raise ValueError("incumbent canonical digest mismatch")

    manifest: list[dict[str, object]] = []
    incumbent_rows = _jsonl(incumbent_path)
    for row in incumbent_rows:
        candidate_id = _require_str(row, "problem_id")
        source_name = _require_str(row, "source")
        fields = {
            "candidate_id": candidate_id,
            "supply_class": "ready",
            "origin": "existing_incumbent",
            "source_name": source_name,
            "parent_artifact_sha256": incumbent_binding["canonical_digest"],
            "row_sha256": _binding(row),
        }
        manifest.append(
            {
                **fields,
                "candidate_binding_sha256": _binding(fields),
                "formal_context_eligible": True,
                "requires_final_piston": True,
                "requires_test_augmentation": False,
                "provenance_status": "tracked_existing_audited_artifact",
            }
        )

    correction_ready_digest = cast(Mapping[str, object], correction["artifact_sha256"])["ready_context"]
    for row in _jsonl(correction_ready_path):
        if row.get("context_eligible") is not True:
            continue
        candidate_id = _require_str(row, "candidate_id")
        fields = {
            "candidate_id": candidate_id,
            "supply_class": "ready",
            "origin": row.get("origin"),
            "source_name": row.get("source_name"),
            "source_record_id": row.get("source_record_id"),
            "prompt_sha256": row.get("prompt_sha256"),
            "parent_artifact_sha256": correction_ready_digest,
        }
        manifest.append(
            {
                **fields,
                "candidate_binding_sha256": _binding(fields),
                "formal_context_eligible": True,
                "requires_final_piston": True,
                "requires_test_augmentation": False,
                "provenance_status": "tracked_existing_audited_artifact",
            }
        )

    ready_count = len(manifest)
    if ready_count != expected.get("ready"):
        raise ValueError(f"ready manifest count mismatch: {ready_count}")

    c7_identity: dict[str, dict[str, object]] = {}
    for row in _jsonl(c7_taco_path):
        c7_identity[_require_str(row, "candidate_id")] = row
    for row in _jsonl(correction_under8_path):
        candidate_id = _require_str(row, "candidate_id")
        c7_identity.setdefault(candidate_id, row)

    retained_c7_ids = [
        _require_str(row, "candidate_id") for row in _jsonl(c8_c7_decisions_path) if row.get("retained") is True
    ]
    if len(retained_c7_ids) != expected.get("c7_under8_after_deepcoder_dedup"):
        raise ValueError("C8 retained C7 count drift")
    for candidate_id in retained_c7_ids:
        identity_row = c7_identity.get(candidate_id)
        if identity_row is None:
            raise ValueError(f"missing evidence-bound C7 identity: {candidate_id}")
        fields = {
            "candidate_id": candidate_id,
            "supply_class": "under8",
            "origin": "c7_after_deepcoder_dedup",
            "source_name": identity_row.get("source_name"),
            "source_record_id": identity_row.get("source_record_id"),
            "raw_record_sha256": identity_row.get("raw_record_sha256"),
            "test_fingerprint": identity_row.get("test_fingerprint"),
            "existing_test_count": identity_row.get("source_test_count", identity_row.get("existing_test_count")),
            "decision_artifact_sha256": cast(Mapping[str, object], c8["artifact_sha256"])[
                "c7_under8_after_deepcoder_decisions"
            ],
        }
        manifest.append(
            {
                **fields,
                "candidate_binding_sha256": _binding(fields),
                "formal_context_eligible": None,
                "requires_final_piston": True,
                "requires_test_augmentation": True,
                "quality_gate_required": True,
                "provenance_status": "tracked_existing_evidence_formal_gate_still_required",
            }
        )

    deep_prime_count = 0
    deep_digest = cast(Mapping[str, object], c8["artifact_sha256"])["deepcoder_under8_candidates"]
    deep_rows = _jsonl(c8_deep_path)
    if len(deep_rows) != expected.get("deepcoder_under8"):
        raise ValueError("DeepCoder under8 count drift")
    for row in deep_rows:
        candidate_id = _require_str(row, "candidate_id")
        source_name = _require_str(row, "source_name")
        unresolved = source_name == "deepcoder-primeintellect"
        deep_prime_count += int(unresolved)
        fields = {
            "candidate_id": candidate_id,
            "supply_class": "under8",
            "origin": "c8_deepcoder",
            "source_name": source_name,
            "source_record_id": row.get("source_record_id"),
            "raw_record_sha256": row.get("raw_record_sha256"),
            "test_fingerprint": row.get("test_fingerprint"),
            "existing_test_count": row.get("source_test_count"),
            "parent_artifact_sha256": deep_digest,
        }
        manifest.append(
            {
                **fields,
                "candidate_binding_sha256": _binding(fields),
                "formal_context_eligible": None,
                "requires_final_piston": True,
                "requires_test_augmentation": True,
                "quality_gate_required": True,
                "provenance_status": (
                    "unresolved_c10_strict_key_formal_admission_blocked"
                    if unresolved
                    else "tracked_existing_evidence_formal_gate_still_required"
                ),
            }
        )
    if deep_prime_count != expected.get("deepcoder_primeintellect_under8"):
        raise ValueError("DeepCoder PrimeIntellect target count drift")

    if len(manifest) != expected.get("total"):
        raise ValueError(f"fixed manifest count mismatch: {len(manifest)}")
    candidate_ids = [_require_str(row, "candidate_id") for row in manifest]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("fixed candidate universe contains duplicate candidate IDs")
    binding_ids = [_require_str(row, "candidate_binding_sha256") for row in manifest]
    if len(set(binding_ids)) != len(binding_ids):
        raise ValueError("fixed candidate universe contains duplicate binding fingerprints")

    class_counts = Counter(cast(str, row["supply_class"]) for row in manifest)
    source_counts = Counter(str(row.get("source_name")) for row in manifest)
    provenance_counts = Counter(str(row.get("provenance_status")) for row in manifest)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        manifest_sha = _write_jsonl(temporary / "candidates.jsonl", manifest)
        report: dict[str, object] = {
            "schema_version": "wp9c-fixed-2505-candidate-freeze-v1",
            "evidence_class": "engineering_candidate_universe_freeze",
            "formal_eligible": False,
            "active_pool_protocol": "wp9c-active-pool-2500-amendment-v1",
            "candidate_universe_frozen": True,
            "source_expansion_stopped": True,
            "candidate_count": len(manifest),
            "class_counts": dict(sorted(class_counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "provenance_status_counts": dict(sorted(provenance_counts.items())),
            "under8_formal_context_eligible_count": None,
            "under8_successes_needed_for_external_new_exact": expected[
                "under8_successes_needed_for_external_new_exact"
            ],
            "under8_success_fraction_needed": cast(int, expected["under8_successes_needed_for_external_new_exact"])
            / cast(int, expected["under8"]),
            "manifest_sha256": manifest_sha,
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "audit_script_sha256": _sha(Path(__file__)),
            "c11_checkpoint_sha256_after_pause": _sha(C11_CHECKPOINT),
            "evidence_bindings": {
                "context_correction_report_sha256": evidence["context_correction_report_sha256"],
                "c7_report_sha256": evidence["c7_report_sha256"],
                "c8_report_sha256": evidence["c8_report_sha256"],
                "c10_report_sha256": evidence["c10_report_sha256"],
                "incumbent_canonical_sha256": incumbent_binding["canonical_digest"],
            },
            "formal_blockers": [
                "under8_test_augmentation_not_run",
                "under8_final_exact_b_context_not_run",
                "formal_function_level_piston_not_run",
                "deepcoder_primeintellect_provenance_unresolved_for_541_rows",
                "informativeness_calibration_not_run_for_new_formal_pool",
            ],
            "notes": [
                (
                    "This audit reads only already-published WP9-c evidence artifacts; it does not rescan raw "
                    "candidate sources."
                ),
                (
                    "No candidate is added, downloaded, executed, generated, Piston-validated, calibrated, or "
                    "selected by reward outcome."
                ),
                "Ready means current Exact-B context-qualified before final formal Piston, not formal admission.",
                (
                    "Under8 formal context eligibility remains null until augmented tests are frozen and production "
                    "Exact-B is rerun."
                ),
                (
                    "The 541 DeepCoder-PrimeIntellect rows remain formally blocked on provenance unless a later "
                    "provenance-only gate is explicitly reopened."
                ),
            ],
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(
            hashlib.sha256(payload.encode("utf-8")).hexdigest() + "\n", encoding="ascii"
        )
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = audit(Path(args.config).resolve(), Path(args.output_dir).resolve())
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
