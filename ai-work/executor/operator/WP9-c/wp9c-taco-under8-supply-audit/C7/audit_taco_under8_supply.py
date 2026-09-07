#!/usr/bin/env python3
"""Static TACO 1-7-test incremental planning-supply audit for WP9-c C7."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from types import ModuleType
from typing import cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.refresh_dedup import RefreshDedupPolicy, classify_refresh_candidates
from code_verifier.data.refresh_sources import (
    Difficulty,
    RefreshCandidate,
    _function_signature_from_row,
    _raw_reference_solution_hash,
    _taco_function_call_tests,
    refresh_test_set_fingerprint,
)
from code_verifier.data.schema import test_case_to_mapping

ROOT = Path(__file__).resolve().parents[6]
C6_FULL_SCRIPT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/audit_full_taco_supply.py"
C6_CORRECTION_SCRIPT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/audit_context_correction.py"
)
LEGACY_TACO_SCRIPT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_taco_shard.py"
JSON_STRICT_MODULE = ROOT / "src/code_verifier/data/json_strict.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load C7 dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_url_hash(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _difficulty(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    return normalized if normalized in {"easy", "medium", "hard"} else "unknown"


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    payload = "".join(canonical_json(row) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_baseline(config: Mapping[str, object]) -> dict[str, object]:
    baseline = cast(Mapping[str, object], config["baseline"])
    report_path = Path(cast(str, baseline["full_taco_ge8_report"]))
    if _sha(report_path) != baseline["full_taco_ge8_report_sha256"]:
        raise ValueError("C6 full-TACO report SHA256 mismatch")
    report = loads_strict(report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != "wp9c-taco-full-supply-audit-v1"
        or report.get("formal_eligible") is not False
        or report.get("incremental_taco_context_eligible") != 0
    ):
        raise ValueError("C6 full-TACO baseline identity/result mismatch")
    supply = report.get("supply_projection")
    if (
        not isinstance(supply, dict)
        or supply.get("current_ready_context_eligible_before_piston") != baseline["ready_context_eligible_count"]
        or supply.get("apps_under8_preaugmentation_planning_after_taco_dedup")
        != baseline["under8_preaugmentation_planning_count"]
        or supply.get("zero_attrition_planning_ready_plus_taco_plus_under8")
        != baseline["zero_attrition_planning_potential_count"]
    ):
        raise ValueError("C6 full-TACO supply baseline mismatch")
    return cast(dict[str, object], report)


def _taco_under8_candidates(
    snapshot: Path,
    shards: Sequence[Mapping[str, object]],
    taco_module: ModuleType,
) -> tuple[list[RefreshCandidate], dict[str, list[str]], Counter[str]]:
    import pyarrow.parquet as pq

    expected_fields = taco_module.EXPECTED_FIELDS
    solutions_fn = taco_module._solutions
    candidates: list[RefreshCandidate] = []
    solutions_by_id: dict[str, list[str]] = {}
    counts: Counter[str] = Counter()
    for shard in shards:
        relative = cast(str, shard["path"])
        path = snapshot / relative
        parquet = pq.ParquetFile(path)
        columns = parquet.schema_arrow.names
        if set(columns) != expected_fields:
            raise ValueError(f"TACO schema drift in {relative}")
        row_index = 0
        for batch in parquet.iter_batches(batch_size=128, columns=columns):
            for row in batch.to_pylist():
                current = row_index
                row_index += 1
                counts["total_rows"] += 1
                if not isinstance(row, Mapping) or set(row) != expected_fields:
                    raise ValueError(f"TACO row schema drift: {relative}:{current}")
                question = row["question"]
                input_output_text = row["input_output"]
                if not isinstance(question, str) or not question.strip() or not isinstance(input_output_text, str):
                    counts["invalid_basic_rows"] += 1
                    continue
                try:
                    input_output = loads_strict(input_output_text)
                except StrictJsonError:
                    counts["invalid_input_output_rows"] += 1
                    continue
                if not isinstance(input_output, dict) or "fn_name" not in input_output:
                    counts["non_function_rows"] += 1
                    continue
                counts["function_call_rows"] += 1
                record_id = f"BAAI/TACO@{cast(str, shard['sha256'])[:12]}/{current}"
                try:
                    parsed = _taco_function_call_tests(input_output, record_id=record_id)
                except ValueError:
                    counts["invalid_function_tests"] += 1
                    continue
                if parsed is None:
                    counts["invalid_function_tests"] += 1
                    continue
                function_name, tests = parsed
                if len(tests) >= 8:
                    counts["ge8_rows"] += 1
                    continue
                if not tests:
                    counts["zero_test_rows"] += 1
                    continue
                counts["under8_rows"] += 1
                try:
                    test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
                except ValueError:
                    counts["duplicate_normalized_test_rows"] += 1
                    continue
                source_solutions = solutions_fn(row["solutions"])
                if source_solutions is None:
                    counts["missing_solution_rows"] += 1
                    continue
                arities = {len(cast(Sequence[object], test.input)) for test in tests}
                starter = row["starter_code"] if isinstance(row["starter_code"], str) else ""
                signature = _function_signature_from_row(
                    {"problem": f"{question}\n{starter}", "solutions": source_solutions},
                    function_name=function_name,
                    arities=arities,
                )
                if signature is None:
                    counts["non_direct_signature_rows"] += 1
                    continue
                candidate_id = f"baai-taco-{cast(str, shard['path']).split('/')[-1]}-{current}"
                raw_hash = stable_json_hash(
                    {
                        "dataset_revision": snapshot.name,
                        "shard_sha256": shard["sha256"],
                        "row_index": current,
                        "question": question,
                        "starter_code": starter,
                        "input_output": input_output_text,
                        "solutions": row["solutions"],
                        "source": row["source"],
                        "url": row["url"],
                    }
                )
                candidate = RefreshCandidate(
                    candidate_id=candidate_id,
                    source_name="BAAI/TACO",
                    source_record_id=f"{cast(str, shard['path'])}:{current}",
                    prompt=question.rstrip(),
                    function_name=function_name,
                    function_signature=signature,
                    tests=tuple(tests),
                    source_url_hash=_source_url_hash(row["url"]),
                    raw_reference_solution_hash=_raw_reference_solution_hash(source_solutions, record_id=record_id),
                    difficulty=cast(Difficulty, _difficulty(row["difficulty"])),
                    category=(f"taco_source:{row['source']}",),
                    raw_record_sha256=raw_hash,
                    test_fingerprint=test_fingerprint,
                    test_validation_guard=None,
                )
                candidates.append(candidate)
                solutions_by_id[candidate_id] = source_solutions
                counts["structural_under8_direct_signature_rows"] += 1
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("TACO under8 candidate IDs are not unique")
    return candidates, solutions_by_id, counts


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    if (
        config.get("version") != "wp9c-taco-under8-supply-audit-v1"
        or config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
        or config.get("seed") != 42
    ):
        raise ValueError("C7 TACO-under8 protocol mismatch")

    targets = cast(Mapping[str, object], config["targets"])
    baseline = cast(Mapping[str, object], config["baseline"])
    source = cast(Mapping[str, object], config["source"])
    selection = cast(Mapping[str, object], config["selection"])
    quality = cast(Mapping[str, object], config["quality"])
    if dict(targets) != {
        "active_pool": 2500,
        "sft_reuse_exact": 225,
        "external_new_exact": 2275,
        "pre_piston_external_new_buffer_min": 2600,
        "pre_piston_external_new_buffer_target": 2800,
    }:
        raise ValueError("C7 target drift")
    if dict(selection) != {
        "minimum_unique_tests": 1,
        "maximum_unique_tests": 7,
        "max_prompt_tokens": 2048,
        "preaugmentation_prompt_protocol": "build_code_prompt_from_fields_preaugmentation_visible_proxy_v1",
        "token_ngram_size": 5,
        "near_jaccard_threshold": 0.90,
        "priority": "current_ready_then_taco_under8_then_apps_under8",
    }:
        raise ValueError("C7 selection policy drift")
    if any(
        quality.get(key) is not False
        for key in ("execute_source_code", "generate_tests", "run_piston", "threshold_relaxation_allowed")
    ) or any(
        quality.get(key) is not True
        for key in (
            "require_reference_solution_execution_validation",
            "exclude_unresolved_quality_gate",
            "final_augmented_context_recheck_required",
        )
    ):
        raise ValueError("C7 quality policy drift")
    if dict(source) != {
        "source_name": "BAAI/TACO",
        "dataset_id": "BAAI/TACO",
        "revision": "d593ed0a2becbbc952230bb89be09189bf1056dc",
        "config_name": "ALL",
        "split": "train",
        "declared_license": "Apache-2.0",
        "provenance_note": (
            "mixed upstream material; preserve source/url and review upstream terms before formal admission"
        ),
        "shard_glob": "ALL/train-*-of-00009.parquet",
        "expected_shard_count": 9,
        "download_manifest": "/home/dzy/wp9c-taco-full-download-C6/manifest.json",
        "download_manifest_sha256": "a99df00663ac0d84c5f162901e1f8316164d866188df16313e4e5102946c4646",
        "adapter": "taco_function_call_under8_audit_v1",
    }:
        raise ValueError("C7 source identity drift")

    c6_full = _load_module(C6_FULL_SCRIPT, "wp9c_c6_full_taco_for_c7")
    correction = _load_module(C6_CORRECTION_SCRIPT, "wp9c_c6_correction_for_c7")
    taco_module = _load_module(LEGACY_TACO_SCRIPT, "wp9c_taco_shard_for_c7")
    c6_report = _validate_baseline(config)
    snapshot, shards, download_manifest_sha = c6_full._validate_download_manifest(config)
    if download_manifest_sha != source["download_manifest_sha256"]:
        raise ValueError("C7 download manifest differs from frozen config")

    candidates, solutions_by_id, structural_counts = _taco_under8_candidates(snapshot, shards, taco_module)
    aggregate_module = _load_module(c6_full.AGGREGATE_SCRIPT, "wp9c_aggregate_for_c7")
    sft_refs, validation_refs, project_refs, humaneval_refs, ready_refs, tokenizer, correction_report = (
        c6_full._current_ready_references(config, aggregate_module)
    )

    policy = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)
    decisions = classify_refresh_candidates(
        [replace(candidate, tests=()) for candidate in candidates],
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_refs,
        external_eval_references=[*humaneval_refs, *ready_refs],
        policy=policy,
    )
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    retained = [by_id[item.candidate_id] for item in decisions if item.retained]
    origins = {candidate.candidate_id: "baai_taco_full_under8" for candidate in retained}
    taco_planning, context_rows, context_summary = correction._under8_preaugmentation_context_filter(
        retained,
        tokenizer=tokenizer,
        cap=2048,
        origin_by_id=origins,
    )
    context_by_id = {cast(str, row["candidate_id"]): row for row in context_rows}
    taco_planning_ids = {candidate.candidate_id for candidate in taco_planning}

    apps_baseline = c6_full._baseline_under8_candidates(config, aggregate_module, correction_report)
    taco_refs = [
        aggregate_module._candidate_reference(candidate, prefix="taco-under8-planning") for candidate in taco_planning
    ]
    apps_decisions = classify_refresh_candidates(
        [replace(candidate, tests=()) for candidate in apps_baseline],
        sft_references=[],
        validation_references=[],
        project_test_references=[],
        external_eval_references=taco_refs,
        policy=policy,
    )
    unexpected_apps_rejections = [
        item
        for item in apps_decisions
        if not item.retained
        and (item.matched_record_id is None or not item.matched_record_id.startswith("taco-under8-planning:"))
    ]
    if unexpected_apps_rejections:
        raise ValueError("C7 TACO-aware APPS dedup changed the corrected baseline for a non-TACO reason")
    apps_by_id = {candidate.candidate_id: candidate for candidate in apps_baseline}
    apps_after_taco = [apps_by_id[item.candidate_id] for item in apps_decisions if item.retained]

    shard_sha_by_path = {cast(str, row["path"]): cast(str, row["sha256"]) for row in shards}
    staged_rows: list[dict[str, object]] = []
    for candidate in candidates:
        if candidate.candidate_id not in taco_planning_ids:
            continue
        shard_path, separator, row_index_text = candidate.source_record_id.rpartition(":")
        if not separator or shard_path not in shard_sha_by_path:
            raise ValueError(f"invalid C7 retained TACO identity: {candidate.source_record_id}")
        context_row = context_by_id[candidate.candidate_id]
        staged_rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "dataset_id": source["dataset_id"],
                "dataset_revision": source["revision"],
                "declared_dataset_license": source["declared_license"],
                "provenance_note": source["provenance_note"],
                "source_shard_path": shard_path,
                "source_shard_sha256": shard_sha_by_path[shard_path],
                "source_row_index": int(row_index_text),
                "upstream_source": candidate.category[0].removeprefix("taco_source:"),
                "prompt": candidate.prompt,
                "function_name": candidate.function_name,
                "function_signature": candidate.function_signature,
                "tests": [test_case_to_mapping(test) for test in candidate.tests],
                "source_test_count": len(candidate.tests),
                "accepted_source_solutions": solutions_by_id[candidate.candidate_id],
                "accepted_source_solution_count": len(solutions_by_id[candidate.candidate_id]),
                "source_url_hash": candidate.source_url_hash,
                "raw_reference_solution_hash": candidate.raw_reference_solution_hash,
                "difficulty": candidate.difficulty,
                "category": list(candidate.category),
                "raw_record_sha256": candidate.raw_record_sha256,
                "test_fingerprint": candidate.test_fingerprint,
                "preaugmentation_prompt_sha256": context_row["prompt_sha256"],
                "preaugmentation_prompt_tokens": context_row["prompt_tokens"],
                "projection_exact_for_current_test_set": context_row["projection_exact_for_current_test_set"],
                "requires_post_augmentation_context_recheck": True,
                "quality_gate_required": True,
                "formal_ready": False,
            }
        )

    taco_count = len(taco_planning)
    apps_after_count = len(apps_after_taco)
    ready_count = cast(int, baseline["ready_context_eligible_count"])
    planning_union = ready_count + taco_count + apps_after_count
    under8_union = taco_count + apps_after_count
    under8_successes_needed = max(0, cast(int, targets["external_new_exact"]) - ready_count)
    success_fraction = under8_successes_needed / under8_union if under8_union else None
    taco_hist = Counter(len(candidate.tests) for candidate in taco_planning)
    apps_hist = Counter(len(candidate.tests) for candidate in apps_after_taco)
    taco_slots = sum(8 - len(candidate.tests) for candidate in taco_planning)
    apps_slots = sum(8 - len(candidate.tests) for candidate in apps_after_taco)

    report: dict[str, object] = {
        "schema_version": "wp9c-taco-under8-supply-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "protocol_amendment": config["protocol_amendment"],
        "formal_blockers": [
            "taco_mixed_upstream_provenance_requires_preservation_and_review",
            "taco_under8_test_augmentation_not_run",
            "apps_under8_test_augmentation_not_run",
            "final_augmented_context_recheck_not_run",
            "reference_solution_transformation_not_frozen",
            "project_piston_reference_solution_validation_not_run",
        ],
        "config_path": str(config_path),
        "config_sha256": _sha(config_path),
        "download_manifest_sha256": download_manifest_sha,
        "dependency_sha256": {
            "audit_script": _sha(Path(__file__)),
            "c6_full_taco_script": _sha(C6_FULL_SCRIPT),
            "c6_context_correction_script": _sha(C6_CORRECTION_SCRIPT),
            "legacy_taco_script": _sha(LEGACY_TACO_SCRIPT),
            "json_strict_module": _sha(JSON_STRICT_MODULE),
        },
        "baseline": {
            "c6_full_taco_report_sha256": baseline["full_taco_ge8_report_sha256"],
            "c6_incremental_ge8_context_eligible": c6_report["incremental_taco_context_eligible"],
            "corrected_ready_context_eligible_before_piston": ready_count,
            "corrected_apps_under8_preaugmentation_planning": baseline["under8_preaugmentation_planning_count"],
            "corrected_apps_under8_formal_context_eligible": None,
            "zero_attrition_planning_potential_before_c7": baseline["zero_attrition_planning_potential_count"],
        },
        "source_identity": config["source"],
        "structural_counts": dict(sorted(structural_counts.items())),
        "dedup": {
            "input_under8_direct_signature": len(candidates),
            "retained_after_formal_current_ready_and_intra_taco_dedup": len(retained),
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in decisions).items())
            ),
        },
        "taco_under8_preaugmentation_context": context_summary,
        "incremental_taco_under8_preaugmentation_planning": taco_count,
        "taco_under8_planning_existing_test_count_histogram": {
            str(key): value for key, value in sorted(taco_hist.items())
        },
        "taco_under8_minimum_added_test_slots_to_reach_8": taco_slots,
        "apps_under8_after_taco_under8_dedup": {
            "baseline_preaugmentation_planning_count": len(apps_baseline),
            "formal_context_eligible_count": None,
            "post_augmentation_context_recheck_required": True,
            "taco_overlap_rejected": len(apps_baseline) - apps_after_count,
            "retained_preaugmentation_planning_count": apps_after_count,
            "retained_existing_test_count_histogram": {str(key): value for key, value in sorted(apps_hist.items())},
            "minimum_added_test_slots_to_reach_8": apps_slots,
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in apps_decisions).items())
            ),
        },
        "supply_projection": {
            "current_ready_context_eligible_before_piston": ready_count,
            "taco_under8_preaugmentation_planning": taco_count,
            "apps_under8_preaugmentation_planning_after_taco_dedup": apps_after_count,
            "under8_preaugmentation_planning_union": under8_union,
            "zero_attrition_planning_union": planning_union,
            "incremental_planning_union_vs_c6": planning_union
            - cast(int, baseline["zero_attrition_planning_potential_count"]),
            "under8_planning_successes_needed_for_exact_2275": under8_successes_needed,
            "under8_planning_success_fraction_needed": success_fraction,
            "pre_piston_buffer_min_met_under_zero_attrition_planning": planning_union
            >= cast(int, targets["pre_piston_external_new_buffer_min"]),
            "pre_piston_buffer_target_met_under_zero_attrition_planning": planning_union
            >= cast(int, targets["pre_piston_external_new_buffer_target"]),
        },
        "notes": [
            "No source solution or testcase payload is executed, no tests are generated, and Piston is not run.",
            (
                "TACO under8 planning rows have priority over the corrected APPS-under8 planning baseline only for "
                "union dedup."
            ),
            (
                "Every TACO/APPS under8 row remains non-formal and requires final post-augmentation Exact-B "
                "context recheck."
            ),
            (
                "For 4-7-test rows the pre-augmentation prompt is byte-crosschecked against production "
                "canonicalization; 1-3-test rows use the explicit non-formal proxy."
            ),
            "Mixed TACO upstream provenance must still be preserved and reviewed before formal admission.",
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        report["artifact_sha256"] = {
            "taco_under8_candidates": _write_jsonl(temporary / "taco_under8_candidates.jsonl", staged_rows),
            "taco_under8_context": _write_jsonl(temporary / "taco_under8_context.jsonl", context_rows),
            "taco_under8_dedup_decisions": _write_jsonl(
                temporary / "taco_under8_dedup_decisions.jsonl", [asdict(item) for item in decisions]
            ),
            "apps_under8_after_taco_decisions": _write_jsonl(
                temporary / "apps_under8_after_taco_decisions.jsonl", [asdict(item) for item in apps_decisions]
            ),
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii")
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
    print(canonical_json(report))


if __name__ == "__main__":
    main()
