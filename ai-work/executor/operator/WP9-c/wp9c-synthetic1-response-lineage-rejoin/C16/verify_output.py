#!/usr/bin/env python3
"""Verify C16 offline lineage/rejoin outputs without executing source solutions."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from code_verifier.data.deduplicate import canonical_json

ROOT = Path(__file__).resolve().parents[6]
CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/C16/checkpoint.json"
OUT = Path("/home/dzy/wp9c-synthetic1-response-lineage-rejoin-C16")
LOG = Path("/home/dzy/wp9c-synthetic1-response-lineage-rejoin-C16.log")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            rows.append(cast(dict[str, object], value))
    return rows


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _require_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string {key}")
    return value


def _artifact_rows(
    report: Mapping[str, object], name: str, filename: str
) -> list[dict[str, object]]:
    artifacts = _mapping(report.get("artifact_sha256"), context="C16 artifact hashes")
    path = OUT / filename
    expected = artifacts.get(name)
    if not isinstance(expected, str) or _sha(path) != expected:
        raise ValueError(f"C16 artifact digest mismatch: {name}")
    return _jsonl(path)


def _ids(rows: Sequence[Mapping[str, object]], key: str) -> list[str]:
    values = [_require_str(row, key) for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate IDs in {key}")
    return values


def verify() -> dict[str, object]:
    checkpoint = _json(CHECKPOINT)
    if checkpoint.get("status") != "awaiting_operator":
        raise ValueError("C16 checkpoint must still be awaiting_operator before verification")
    if checkpoint.get("candidate_supply_increment_allowed") is not False:
        raise ValueError("C16 candidate supply freeze drift")
    if checkpoint.get("source_solution_execution_frozen") is not True:
        raise ValueError("C16 source-solution execution freeze drift")
    if checkpoint.get("piston_frozen") is not True or checkpoint.get("test_generation_frozen") is not True:
        raise ValueError("C16 execution/generation freeze drift")

    if not OUT.is_dir() or not LOG.is_file():
        raise ValueError("C16 output directory/log is missing")
    report_path = OUT / "report.json"
    sidecar = OUT / "report.sha256"
    if not report_path.is_file() or not sidecar.is_file():
        raise ValueError("C16 report or report sidecar is missing")
    report_sha = _sha(report_path)
    if sidecar.read_text(encoding="ascii").strip() != report_sha:
        raise ValueError("C16 report sidecar digest mismatch")
    report = _json(report_path)

    if report.get("schema_version") != "wp9c-synthetic1-response-lineage-rejoin-v1":
        raise ValueError("C16 report schema drift")
    if report.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1":
        raise ValueError("C16 report protocol drift")
    if report.get("formal_eligible") is not False or report.get("candidate_supply_increment") != 0:
        raise ValueError("C16 report formal/supply boundary drift")
    if report.get("target_count") != 541 or report.get("minimum_primeintellect_successes_required") != 311:
        raise ValueError("C16 target/necessity count drift")

    bindings = _mapping(checkpoint.get("bindings"), context="C16 checkpoint bindings")
    config_path = ROOT / "configs/data/wp9c-synthetic1-response-lineage-rejoin.yaml"
    audit_path = ROOT / (
        "ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/"
        "C16/audit_response_lineage_rejoin.py"
    )
    runner_path = ROOT / (
        "ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/"
        "C16/01-run-lineage-rejoin.sh"
    )
    for key, path in (
        ("config_sha256", config_path),
        ("audit_script_sha256", audit_path),
        ("runner_sha256", runner_path),
    ):
        if _sha(path) != bindings.get(key):
            raise ValueError(f"C16 checkpoint binding drift: {key}")
    if report.get("config_sha256") != bindings.get("config_sha256"):
        raise ValueError("C16 report config binding drift")
    if report.get("audit_script_sha256") != bindings.get("audit_script_sha256"):
        raise ValueError("C16 report audit-script binding drift")
    if report.get("sft_manifest_sha256") != bindings.get("c15_manifest_sha256"):
        raise ValueError("C16 SFT manifest binding drift")
    if report.get("raw_vcp_manifest_sha256") != bindings.get("c10_download_manifest_sha256"):
        raise ValueError("C16 raw-VCP manifest binding drift")

    score = _mapping(report.get("score_isolation"), context="C16 score isolation")
    if dict(score) != {
        "score_field_present_in_source_schema": True,
        "score_field_loaded_into_scan_batches": False,
        "score_value_used_for_matching": False,
        "score_value_used_for_selection": False,
        "score_value_used_for_supply": False,
    }:
        raise ValueError("C16 score isolation drift")
    boundaries = _mapping(report.get("execution_boundaries"), context="C16 execution boundaries")
    if any(value is not False for value in boundaries.values()):
        raise ValueError("C16 execution boundary was crossed")

    sft = _mapping(report.get("sft_scan_summary"), context="C16 SFT scan summary")
    if sft.get("scanned_rows") != 894086:
        raise ValueError("C16 SFT scanned row count drift")
    if sft.get("score_field_loaded_into_scan_batches") is not False or sft.get("score_field_used") is not False:
        raise ValueError("C16 SFT score use drift")
    raw_scan = _mapping(report.get("raw_vcp_scan_summary"), context="C16 raw-VCP scan summary")
    if raw_scan.get("scanned_rows") != 35735:
        raise ValueError("C16 raw-VCP scanned row count drift")

    lineage_rows = _artifact_rows(report, "target_lineage", "target_lineage.jsonl")
    response_hits = _artifact_rows(report, "response_hits", "response_hits.jsonl")
    prompt_diagnostics = _artifact_rows(report, "prompt_diagnostics", "prompt_diagnostics.jsonl")
    rejoin_rows = _artifact_rows(report, "raw_vcp_rejoin", "raw_vcp_rejoin.jsonl")
    oracle_rows = _artifact_rows(report, "second_oracle_candidates", "second_oracle_candidates.jsonl")

    if len(lineage_rows) != 541:
        raise ValueError("C16 lineage artifact must contain exactly 541 rows")
    lineage_ids = _ids(lineage_rows, "deepcoder_candidate_id")
    lineage_status = Counter(_require_str(row, "lineage_status") for row in lineage_rows)
    if set(lineage_status) - {"unique_problem_id", "ambiguous_problem_id", "unmatched"}:
        raise ValueError("C16 unexpected lineage status")
    lineage_summary = _mapping(report.get("lineage_summary"), context="C16 lineage summary")
    if lineage_summary.get("unique_problem_id_rows", 0) != lineage_status["unique_problem_id"]:
        raise ValueError("C16 unique lineage count mismatch")
    if lineage_summary.get("ambiguous_problem_id_rows", 0) != lineage_status["ambiguous_problem_id"]:
        raise ValueError("C16 ambiguous lineage count mismatch")
    if lineage_summary.get("unmatched_rows", 0) != lineage_status["unmatched"]:
        raise ValueError("C16 unmatched lineage count mismatch")
    if sum(lineage_status.values()) != 541:
        raise ValueError("C16 lineage partition mismatch")
    if len(response_hits) != sft.get("exact_candidate_response_hits"):
        raise ValueError("C16 response-hit count mismatch")
    if len(prompt_diagnostics) != sft.get("prompt_hit_source_rows"):
        raise ValueError("C16 prompt-diagnostic count mismatch")

    unique_lineage_ids = {
        _require_str(row, "deepcoder_candidate_id")
        for row in lineage_rows
        if row.get("lineage_status") == "unique_problem_id"
    }
    rejoin_ids = set(_ids(rejoin_rows, "deepcoder_candidate_id"))
    if rejoin_ids != unique_lineage_ids:
        raise ValueError("C16 rejoin artifact does not exactly cover unique-lineage candidates")

    rejoin_status = Counter(_require_str(row, "raw_vcp_rejoin_status") for row in rejoin_rows)
    rejoin_summary = _mapping(report.get("raw_vcp_rejoin_summary"), context="C16 raw-VCP rejoin summary")
    expected_rejoin_counts = {
        "unique_raw_vcp_row": cast(int, rejoin_summary.get("unique_raw_vcp_rejoin_rows", 0)),
        "ambiguous_raw_vcp_rows": cast(int, rejoin_summary.get("ambiguous_raw_vcp_rejoin_rows", 0)),
        "missing_raw_vcp_row": cast(int, rejoin_summary.get("missing_raw_vcp_rejoin_rows", 0)),
    }
    for status, expected in expected_rejoin_counts.items():
        if rejoin_status[status] != expected:
            raise ValueError(f"C16 rejoin count mismatch: {status}")

    oracle_ids = set(_ids(oracle_rows, "deepcoder_candidate_id"))
    if len(oracle_rows) != report.get("second_oracle_static_candidate_count"):
        raise ValueError("C16 static-oracle count mismatch")
    if len(oracle_rows) != rejoin_summary.get("second_oracle_static_candidate_rows", 0):
        raise ValueError("C16 static-oracle rejoin summary mismatch")
    rejoin_static_ids = {
        _require_str(row, "deepcoder_candidate_id")
        for row in rejoin_rows
        if row.get("second_oracle_static_candidate") is True
    }
    if oracle_ids != rejoin_static_ids:
        raise ValueError("C16 static-oracle artifact ID mismatch")
    for row in oracle_rows:
        if row.get("formal_admitted") is not False:
            raise ValueError("C16 static-oracle row was formal-admitted")
        if row.get("source_solution_transformation_required") is not True:
            raise ValueError("C16 static-oracle transformation requirement drift")
        if row.get("project_piston_qualification_required") is not True:
            raise ValueError("C16 static-oracle Piston requirement drift")
        if row.get("upstream_terms_review_required") is not True:
            raise ValueError("C16 static-oracle terms-review requirement drift")
        if row.get("raw_gold_extracted_code_sha256") == row.get("deepcoder_extracted_code_sha256"):
            raise ValueError("C16 static-oracle code is not independent by bytes")

    count = len(oracle_rows)
    if report.get("minimum_required_static_oracle_candidate_count_met") is not (count >= 311):
        raise ValueError("C16 minimum-static-oracle decision drift")

    log_text = LOG.read_text(encoding="utf-8", errors="replace")
    report_line = canonical_json(report)
    if report_line not in log_text:
        raise ValueError("C16 log does not contain the published report")
    if "Traceback (most recent call last)" in log_text:
        raise ValueError("C16 log contains a Python traceback")

    return {
        "schema_version": "wp9c-c16-output-verification-v1",
        "verified": True,
        "report_sha256": report_sha,
        "log_sha256": _sha(LOG),
        "artifact_sha256": dict(_mapping(report.get("artifact_sha256"), context="C16 artifact hashes")),
        "target_count": len(lineage_rows),
        "lineage_unique_problem_id": lineage_status["unique_problem_id"],
        "lineage_ambiguous_problem_id": lineage_status["ambiguous_problem_id"],
        "lineage_unmatched": lineage_status["unmatched"],
        "exact_response_hits": len(response_hits),
        "prompt_hit_source_rows": len(prompt_diagnostics),
        "raw_vcp_rejoin_rows": len(rejoin_rows),
        "raw_vcp_unique_rejoin": rejoin_status["unique_raw_vcp_row"],
        "raw_vcp_ambiguous_rejoin": rejoin_status["ambiguous_raw_vcp_rows"],
        "raw_vcp_missing_rejoin": rejoin_status["missing_raw_vcp_row"],
        "second_oracle_static_candidate_count": count,
        "minimum_311_static_candidates_met": count >= 311,
        "candidate_supply_increment": 0,
        "source_solution_execution_run": False,
        "piston_run": False,
        "generation_run": False,
        "lineage_candidate_ids_sha256": hashlib.sha256(
            json.dumps(sorted(lineage_ids), separators=(",", ":")).encode()
        ).hexdigest(),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
