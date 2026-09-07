#!/usr/bin/env python3
"""C11 provenance-only response-lineage audit for DeepCoder PrimeIntellect rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import normalize_text
from code_verifier.parsing.code_extractor import extract_python_code

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CONFIG = ROOT / "configs/data/wp9c-synthetic1-sft-lineage-audit.yaml"


@dataclass(frozen=True)
class Target:
    """One frozen DeepCoder-PrimeIntellect provenance target."""

    candidate_id: str
    source_record_id: str
    prompt_norm: str
    prompt_sha256: str
    function_name: str
    code_by_sha256: Mapping[str, str]
    accepted_solution_count: int
    parsed_solution_count: int


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _value_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(Mapping[str, object], value)


def _jsonl(path: Path) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            rows.append(cast(Mapping[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for row in rows:
            payload = (
                json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
            )
            handle.write(payload)
            digest.update(payload)
    return digest.hexdigest()


def _validate_config(config: Mapping[str, object]) -> None:
    if (
        config.get("version") != "wp9c-synthetic1-sft-lineage-audit-v1"
        or config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
        or config.get("seed") != 42
    ):
        raise ValueError("C11 protocol identity drift")
    targets = cast(Mapping[str, object], config.get("targets"))
    if dict(targets) != {
        "deepcoder_primeintellect_rows": 541,
        "active_pool": 2500,
        "sft_reuse_exact": 225,
        "external_new_exact": 2275,
    }:
        raise ValueError("C11 target drift")
    source = cast(Mapping[str, object], config.get("source"))
    if dict(source) != {
        "source_name": "primeintellect-synthetic1-sft-lineage",
        "dataset_id": "PrimeIntellect/SYNTHETIC-1-SFT-Data",
        "revision": "e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8",
        "config_name": "default",
        "split": "train",
        "declared_license": "Apache-2.0",
        "use_class": "provenance_index_only",
        "score_policy": "excluded_from_scan_columns_and_never_used_for_matching_selection_or_supply",
        "shard_glob": "data/train-*-of-00017.parquet",
        "expected_shard_count": 17,
        "expected_total_rows": 894086,
        "download_manifest": "/home/dzy/wp9c-synthetic1-sft-lineage-download-C11/manifest.json",
    }:
        raise ValueError("C11 source identity drift")
    matching = cast(Mapping[str, object], config.get("matching"))
    if dict(matching) != {
        "target_source_name": "deepcoder-primeintellect",
        "required_task_type": "verifiable_code",
        "prompt_match": "normalize_text_exact",
        "response_extractor": "code_verifier_extract_python_code_final_python_block_v1",
        "response_code_match": "exact_extracted_code_bytes",
        "unique_lineage_unit": "problem_id",
        "prompt_only_match_is_admissible": False,
        "fuzzy_prompt_match_allowed": False,
        "fuzzy_code_match_allowed": False,
    }:
        raise ValueError("C11 matching contract drift")
    quality = cast(Mapping[str, object], config.get("quality"))
    if dict(quality) != {
        "provenance_only": True,
        "incremental_supply_allowed": False,
        "execute_source_code": False,
        "generate_tests": False,
        "run_piston": False,
        "run_calibration": False,
        "run_grpo": False,
        "use_gpu": False,
        "threshold_relaxation_allowed": False,
        "unresolved_lineage_blocks_formal_admission": True,
        "final_augmented_context_recheck_required": True,
    }:
        raise ValueError("C11 quality/frozen-boundary drift")


def _validate_baselines(config: Mapping[str, object]) -> tuple[Mapping[str, object], Mapping[str, object]]:
    baseline = cast(Mapping[str, object], config["baseline"])
    c8_path = Path(cast(str, baseline["c8_report"]))
    c10_path = Path(cast(str, baseline["c10_report"]))
    if _sha(c8_path) != baseline["c8_report_sha256"]:
        raise ValueError("C11 C8 report digest mismatch")
    if _sha(c10_path) != baseline["c10_report_sha256"]:
        raise ValueError("C11 C10 report digest mismatch")
    c8 = _load_json(c8_path)
    c10 = _load_json(c10_path)
    c8_supply = cast(Mapping[str, object], c8.get("supply_projection"))
    c10_supply = cast(Mapping[str, object], c10.get("supply_projection"))
    c10_provenance = cast(Mapping[str, object], c10.get("deepcoder_provenance_recovery"))
    if (
        c8.get("schema_version") != "wp9c-deepcoder-function-supply-audit-v1"
        or c8_supply.get("under8_preaugmentation_planning_union") != 1229
        or c8_supply.get("zero_attrition_planning_union") != 2505
        or c10.get("schema_version") != "wp9c-openr1-raw-python-provenance-audit-v1"
        or c10.get("formal_eligible") is not False
        or c10_supply.get("ready_context_eligible_union_before_piston") != 1276
        or c10_supply.get("under8_preaugmentation_planning_union") != 1229
        or c10_supply.get("zero_attrition_planning_union") != 2505
        or c10_provenance.get("target_deepcoder_primeintellect_rows") != 541
        or c10_provenance.get("uniquely_matched_rows") != 0
        or c10_provenance.get("ambiguous_rows") != 0
        or c10_provenance.get("unmatched_rows") != 541
    ):
        raise ValueError("C11 frozen C8/C10 baseline semantics mismatch")
    return c8, c10


def _validate_manifest(config: Mapping[str, object]) -> tuple[Path, list[Path], str]:
    source = cast(Mapping[str, object], config["source"])
    manifest_path = Path(cast(str, source["download_manifest"]))
    manifest_sha = _sha(manifest_path)
    manifest = _load_json(manifest_path)
    if (
        manifest.get("schema_version") != "wp9c-synthetic1-sft-lineage-download-v1"
        or manifest.get("dataset_id") != source["dataset_id"]
        or manifest.get("revision") != source["revision"]
        or manifest.get("shard_count") != source["expected_shard_count"]
        or manifest.get("total_rows") != source["expected_total_rows"]
    ):
        raise ValueError("C11 download manifest identity mismatch")
    snapshot_value = manifest.get("snapshot_path")
    shard_rows = manifest.get("shards")
    if not isinstance(snapshot_value, str) or not isinstance(shard_rows, list):
        raise ValueError("C11 download manifest schema mismatch")
    snapshot = Path(snapshot_value).resolve()
    if snapshot.name != source["revision"]:
        raise ValueError("C11 snapshot revision mismatch")
    expected_paths = [f"data/train-{index:05d}-of-00017.parquet" for index in range(17)]
    paths: list[Path] = []
    total_rows = 0
    observed_paths: list[str] = []
    for index, raw in enumerate(shard_rows):
        if not isinstance(raw, dict):
            raise ValueError("C11 shard manifest row is invalid")
        row = cast(Mapping[str, object], raw)
        relative = row.get("path")
        if row.get("shard_index") != index or not isinstance(relative, str):
            raise ValueError("C11 shard ordering/path schema mismatch")
        observed_paths.append(relative)
        path = snapshot / relative
        if not path.is_file() or path.stat().st_size != row.get("size"):
            raise ValueError(f"C11 shard missing/size drift: {relative}")
        if _sha(path) != row.get("sha256"):
            raise ValueError(f"C11 shard digest drift: {relative}")
        parquet_rows = pq.ParquetFile(path).metadata.num_rows
        if parquet_rows != row.get("rows"):
            raise ValueError(f"C11 shard row-count drift: {relative}")
        total_rows += parquet_rows
        paths.append(path)
    if observed_paths != expected_paths or total_rows != source["expected_total_rows"]:
        raise ValueError("C11 shard set/total row-count drift")
    return snapshot, paths, manifest_sha


def _load_targets(
    config: Mapping[str, object], c8_report: Mapping[str, object]
) -> tuple[list[Target], Mapping[str, int]]:
    baseline = cast(Mapping[str, object], config["baseline"])
    path = Path(cast(str, baseline["c8_deepcoder_under8_candidates"]))
    expected_sha = cast(str, baseline["c8_deepcoder_under8_candidates_sha256"])
    artifacts = cast(Mapping[str, object], c8_report.get("artifact_sha256"))
    if _sha(path) != expected_sha or artifacts.get("deepcoder_under8_candidates") != expected_sha:
        raise ValueError("C11 frozen C8 target artifact digest mismatch")
    rows = _jsonl(path)
    targets: list[Target] = []
    candidate_ids: set[str] = set()
    counts: Counter[str] = Counter()
    for row in rows:
        if row.get("source_name") != "deepcoder-primeintellect":
            continue
        counts["target_rows"] += 1
        candidate_id = row.get("candidate_id")
        source_record_id = row.get("source_record_id")
        prompt = row.get("prompt")
        function_name = row.get("function_name")
        solutions = row.get("accepted_source_solutions")
        declared_count = row.get("accepted_source_solution_count")
        if (
            not isinstance(candidate_id, str)
            or not isinstance(source_record_id, str)
            or not isinstance(prompt, str)
            or not isinstance(function_name, str)
            or not isinstance(solutions, list)
            or any(not isinstance(item, str) for item in solutions)
            or declared_count != len(solutions)
        ):
            raise ValueError("C11 DeepCoder target row schema mismatch")
        if candidate_id in candidate_ids:
            raise ValueError("C11 duplicate DeepCoder target candidate_id")
        candidate_ids.add(candidate_id)
        code_by_sha: dict[str, str] = {}
        for solution_object in solutions:
            solution = cast(str, solution_object)
            parsed = extract_python_code(solution)
            if not parsed.success:
                counts[f"target_solution_parse_error:{parsed.error_type}"] += 1
                continue
            code_sha = _text_sha(parsed.code)
            existing = code_by_sha.get(code_sha)
            if existing is not None and existing != parsed.code:
                raise ValueError("C11 impossible target code SHA collision")
            code_by_sha[code_sha] = parsed.code
            counts["parsed_target_solutions"] += 1
        if code_by_sha:
            counts["targets_with_parsed_solution"] += 1
        else:
            counts["targets_without_parsed_solution"] += 1
        prompt_norm = normalize_text(prompt)
        if not prompt_norm:
            raise ValueError("C11 empty normalized target prompt")
        targets.append(
            Target(
                candidate_id=candidate_id,
                source_record_id=source_record_id,
                prompt_norm=prompt_norm,
                prompt_sha256=_text_sha(prompt_norm),
                function_name=function_name,
                code_by_sha256=code_by_sha,
                accepted_solution_count=len(solutions),
                parsed_solution_count=len(code_by_sha),
            )
        )
    if len(rows) != 542 or len(targets) != 541:
        raise ValueError(
            "C11 expected 542 staged DeepCoder under8 rows / 541 PrimeIntellect targets, "
            f"got {len(rows)}/{len(targets)}"
        )
    return sorted(targets, key=lambda item: item.candidate_id), dict(sorted(counts.items()))


def _message_pair(value: object, *, context: str) -> tuple[str, str]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{context}: messages must contain exactly two items")
    first, second = value
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise ValueError(f"{context}: messages items must be objects")
    if set(first) != {"role", "content"} or set(second) != {"role", "content"}:
        raise ValueError(f"{context}: message schema drift")
    if first.get("role") != "user" or second.get("role") != "assistant":
        raise ValueError(f"{context}: expected user/assistant message roles")
    user_content = first.get("content")
    assistant_content = second.get("content")
    if (
        not isinstance(user_content, str)
        or not user_content.strip()
        or not isinstance(assistant_content, str)
        or not assistant_content.strip()
    ):
        raise ValueError(f"{context}: empty/non-string message content")
    return user_content, assistant_content


def _scan_source(
    paths: Sequence[Path],
    targets: Sequence[Target],
    *,
    required_task_type: str,
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]], Mapping[str, object]]:
    prompt_index: dict[str, list[Target]] = defaultdict(list)
    for target in targets:
        prompt_index[target.prompt_norm].append(target)

    exact_hits: list[Mapping[str, object]] = []
    prompt_diagnostics: list[Mapping[str, object]] = []
    counts: Counter[str] = Counter()
    task_types: Counter[str] = Counter()
    source_fields = {"response_id", "problem_id", "task_type", "score", "messages"}
    scan_columns = ["response_id", "problem_id", "task_type", "messages"]

    for shard_index, path in enumerate(paths):
        parquet = pq.ParquetFile(path)
        if set(parquet.schema_arrow.names) != source_fields:
            raise ValueError(f"C11 source schema drift: {path.name}")
        local_row = 0
        for batch in parquet.iter_batches(batch_size=512, columns=scan_columns):
            for raw_row in cast(list[object], batch.to_pylist()):
                current_local = local_row
                local_row += 1
                counts["scanned_rows"] += 1
                if not isinstance(raw_row, dict) or set(raw_row) != set(scan_columns):
                    raise ValueError(f"C11 projected row schema drift: shard{shard_index}/{current_local}")
                row = cast(Mapping[str, object], raw_row)
                response_id = row["response_id"]
                problem_id = row["problem_id"]
                task_type = row["task_type"]
                if (
                    not isinstance(response_id, str)
                    or not response_id
                    or not isinstance(problem_id, str)
                    or not problem_id
                    or not isinstance(task_type, str)
                    or not task_type
                ):
                    raise ValueError(f"C11 identifier/task_type schema drift: shard{shard_index}/{current_local}")
                task_types[task_type] += 1
                user_content, assistant_content = _message_pair(
                    row["messages"], context=f"C11 shard{shard_index}/{current_local}"
                )
                if task_type != required_task_type:
                    continue
                counts["required_task_type_rows"] += 1
                prompt_norm = normalize_text(user_content)
                matching_targets = prompt_index.get(prompt_norm)
                if not matching_targets:
                    continue
                counts["prompt_hit_source_rows"] += 1
                parsed = extract_python_code(assistant_content)
                extracted_sha = _text_sha(parsed.code) if parsed.success else None
                exact_candidate_ids: list[str] = []
                if parsed.success and extracted_sha is not None:
                    for target in matching_targets:
                        target_code = target.code_by_sha256.get(extracted_sha)
                        if target_code is not None and target_code == parsed.code:
                            exact_candidate_ids.append(target.candidate_id)
                            exact_hits.append(
                                {
                                    "deepcoder_candidate_id": target.candidate_id,
                                    "deepcoder_source_record_id": target.source_record_id,
                                    "response_id": response_id,
                                    "problem_id": problem_id,
                                    "sft_shard_index": shard_index,
                                    "sft_local_row": current_local,
                                    "prompt_sha256": target.prompt_sha256,
                                    "extracted_code_sha256": extracted_sha,
                                    "assistant_response_sha256": _text_sha(assistant_content),
                                }
                            )
                            counts["exact_candidate_response_hits"] += 1
                else:
                    counts[f"assistant_extract_error:{parsed.error_type}"] += 1
                prompt_diagnostics.append(
                    {
                        "response_id": response_id,
                        "problem_id": problem_id,
                        "sft_shard_index": shard_index,
                        "sft_local_row": current_local,
                        "prompt_sha256": _text_sha(prompt_norm),
                        "assistant_response_sha256": _text_sha(assistant_content),
                        "assistant_extract_success": parsed.success,
                        "assistant_extract_error_type": parsed.error_type,
                        "assistant_extracted_code_sha256": extracted_sha,
                        "deepcoder_prompt_candidate_ids": sorted(target.candidate_id for target in matching_targets),
                        "deepcoder_exact_code_candidate_ids": sorted(exact_candidate_ids),
                    }
                )
    return (
        exact_hits,
        prompt_diagnostics,
        {
            "scanned_rows": counts["scanned_rows"],
            "required_task_type_rows": counts["required_task_type_rows"],
            "prompt_hit_source_rows": counts["prompt_hit_source_rows"],
            "exact_candidate_response_hits": counts["exact_candidate_response_hits"],
            "assistant_extract_error_counts": {
                key.removeprefix("assistant_extract_error:"): value
                for key, value in sorted(counts.items())
                if key.startswith("assistant_extract_error:")
            },
            "task_type_counts": dict(sorted(task_types.items())),
            "score_field_present_in_parquet_schema": True,
            "score_field_loaded_into_scan_batches": False,
            "score_field_used_for_matching_selection_or_supply": False,
        },
    )


def _classify_targets(
    targets: Sequence[Target],
    exact_hits: Sequence[Mapping[str, object]],
    prompt_diagnostics: Sequence[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], Mapping[str, object]]:
    hits_by_target: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    prompt_response_ids: dict[str, set[str]] = defaultdict(set)
    for hit in exact_hits:
        hits_by_target[cast(str, hit["deepcoder_candidate_id"])].append(hit)
    for diagnostic in prompt_diagnostics:
        response_id = cast(str, diagnostic["response_id"])
        candidate_ids = diagnostic["deepcoder_prompt_candidate_ids"]
        if not isinstance(candidate_ids, list):
            raise ValueError("C11 prompt diagnostic candidate list drift")
        for candidate_id in candidate_ids:
            if not isinstance(candidate_id, str):
                raise ValueError("C11 prompt diagnostic candidate id drift")
            prompt_response_ids[candidate_id].add(response_id)

    rows: list[Mapping[str, object]] = []
    counts: Counter[str] = Counter()
    unique_ids: list[str] = []
    ambiguous_ids: list[str] = []
    unmatched_ids: list[str] = []
    for target in targets:
        hits = hits_by_target.get(target.candidate_id, [])
        response_ids = sorted({cast(str, hit["response_id"]) for hit in hits})
        problem_ids = sorted({cast(str, hit["problem_id"]) for hit in hits})
        if len(problem_ids) == 1:
            status = "unique_problem_id"
            unique_ids.append(target.candidate_id)
            counts["unique_problem_id_rows"] += 1
            if len(response_ids) == 1:
                counts["unique_response_id_rows"] += 1
            else:
                counts["duplicate_response_same_problem_id_rows"] += 1
        elif len(problem_ids) > 1:
            status = "ambiguous_problem_id"
            ambiguous_ids.append(target.candidate_id)
            counts["ambiguous_problem_id_rows"] += 1
        else:
            status = "unmatched"
            unmatched_ids.append(target.candidate_id)
            counts["unmatched_rows"] += 1
        rows.append(
            {
                "deepcoder_candidate_id": target.candidate_id,
                "deepcoder_source_record_id": target.source_record_id,
                "prompt_sha256": target.prompt_sha256,
                "function_name": target.function_name,
                "accepted_source_solution_count": target.accepted_solution_count,
                "parsed_target_solution_count": target.parsed_solution_count,
                "parsed_target_code_sha256": sorted(target.code_by_sha256),
                "prompt_match_response_count": len(prompt_response_ids.get(target.candidate_id, set())),
                "exact_response_hit_count": len(hits),
                "exact_response_id_count": len(response_ids),
                "exact_problem_id_count": len(problem_ids),
                "lineage_status": status,
                "problem_ids": problem_ids,
                "response_ids": response_ids,
            }
        )
    if counts["unique_problem_id_rows"] + counts["ambiguous_problem_id_rows"] + counts["unmatched_rows"] != 541:
        raise ValueError("C11 lineage partition does not cover exactly 541 targets")
    return rows, {
        **dict(sorted(counts.items())),
        "target_count": len(targets),
        "unique_candidate_ids_sha256": _value_sha(sorted(unique_ids)),
        "ambiguous_candidate_ids_sha256": _value_sha(sorted(ambiguous_ids)),
        "unmatched_candidate_ids_sha256": _value_sha(sorted(unmatched_ids)),
    }


def _run(config_path: Path, output_dir: Path) -> Mapping[str, object]:
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    c8_report, c10_report = _validate_baselines(config)
    _, shards, manifest_sha = _validate_manifest(config)
    targets, target_parse_summary = _load_targets(config, c8_report)
    matching = cast(Mapping[str, object], config["matching"])
    exact_hits, prompt_diagnostics, scan_summary = _scan_source(
        shards, targets, required_task_type=cast(str, matching["required_task_type"])
    )
    if scan_summary["scanned_rows"] != 894086:
        raise ValueError("C11 scanned row count mismatch")
    lineage_rows, lineage_summary = _classify_targets(targets, exact_hits, prompt_diagnostics)

    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing C11 output: {output_dir}")
    temporary = Path(f"{output_dir}.tmp")
    if temporary.exists():
        raise FileExistsError(f"refusing to overwrite existing C11 temporary output: {temporary}")
    temporary.mkdir(parents=True)
    try:
        artifact_sha = {
            "target_lineage": _write_jsonl(temporary / "target_lineage.jsonl", lineage_rows),
            "response_hits": _write_jsonl(temporary / "response_hits.jsonl", exact_hits),
            "prompt_diagnostics": _write_jsonl(temporary / "prompt_diagnostics.jsonl", prompt_diagnostics),
        }
        report: dict[str, object] = {
            "schema_version": "wp9c-synthetic1-sft-lineage-audit-v1",
            "protocol_amendment": "wp9c-active-pool-2500-amendment-v1",
            "evidence_class": "engineering_provenance_audit_only",
            "formal_eligible": False,
            "config_path": str(config_path.resolve()),
            "config_sha256": _sha(config_path),
            "download_manifest_sha256": manifest_sha,
            "baseline": {
                "c8_report_sha256": _sha(Path(cast(str, cast(Mapping[str, object], config["baseline"])["c8_report"]))),
                "c10_report_sha256": _sha(
                    Path(cast(str, cast(Mapping[str, object], config["baseline"])["c10_report"]))
                ),
                "c10_strict_provenance_result": c10_report["deepcoder_provenance_recovery"],
                "ready_context_eligible_before_piston": 1276,
                "under8_preaugmentation_planning_union": 1229,
                "zero_attrition_planning_union": 2505,
            },
            "source_identity": config["source"],
            "matching_contract": config["matching"],
            "score_isolation": {
                "source_derivative_is_score_filtered": True,
                "score_field_present_in_source_schema": True,
                "score_field_excluded_from_scan_columns": True,
                "score_value_read_for_matching": False,
                "score_value_used_for_selection": False,
                "score_value_used_for_supply": False,
                "provenance_match_never_adds_supply": True,
            },
            "target_parse_summary": target_parse_summary,
            "scan_summary": scan_summary,
            "lineage_summary": lineage_summary,
            "supply_projection": {
                "incremental_supply_by_protocol": 0,
                "ready_context_eligible_union_before_piston": 1276,
                "under8_preaugmentation_planning_union": 1229,
                "zero_attrition_planning_union": 2505,
                "pre_piston_buffer_min_2600_met": False,
                "pre_piston_buffer_target_2800_met": False,
                "under8_successes_needed_for_exact_2275": 999,
                "under8_success_fraction_needed": 0.8128559804719284,
            },
            "formal_blockers": [
                "C11_is_provenance_only_and_cannot_formally_admit_candidates",
                "unmatched_or_ambiguous_DeepCoder_lineage_must_remain_excluded_if_nonzero",
                "matched_problem_ids_must_be_rejoined_to_raw_VCP_source_URL_and_upstream_terms_before_formal_admission",
                "reference_solution_execution_validation_not_run",
                "under8_test_augmentation_not_run",
                "final_augmented_context_recheck_not_run",
                "project_Piston_validation_not_run",
            ],
            "notes": [
                "C10 strict 0/0/541 provenance evidence remains immutable; C11 tests a different response-level "
                "lineage contract.",
                "The SFT score column is intentionally excluded from scan batches and cannot influence matching, "
                "selection, or supply.",
                "Prompt-only matches are diagnostic and never count as lineage admission.",
                "Unique lineage requires exact normalized prompt plus exact bytes from the shared deterministic "
                "final-Python-block extractor, with all exact hits resolving to one problem_id.",
                "No source code/tests are executed, no tests are generated, and Piston/calibration/GRPO/GPU are "
                "not run.",
            ],
            "artifact_sha256": artifact_sha,
        }
        payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
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
    _run(args.config, args.output)


if __name__ == "__main__":
    main()
