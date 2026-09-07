#!/usr/bin/env python3
"""C16 exact SYNTHETIC-1 response lineage plus raw-VCP problem_id rejoin."""

from __future__ import annotations

import argparse
import ast
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
from code_verifier.data.deduplicate import canonical_json, normalize_text
from code_verifier.parsing.code_extractor import extract_python_code

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CONFIG = ROOT / "configs/data/wp9c-synthetic1-response-lineage-rejoin.yaml"


@dataclass(frozen=True)
class Target:
    candidate_id: str
    source_record_id: str
    prompt_norm: str
    prompt_sha256: str
    function_name: str
    deepcoder_solution: str
    deepcoder_solution_sha256: str
    deepcoder_code: str
    deepcoder_code_sha256: str


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _value_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


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


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for row in rows:
            payload = (canonical_json(row) + "\n").encode()
            handle.write(payload)
            digest.update(payload)
    return digest.hexdigest()


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _require_str(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string field {key}")
    return value


def _verified_json(path: Path, expected_sha: object, *, schema: str) -> dict[str, object]:
    if not isinstance(expected_sha, str) or _sha(path) != expected_sha:
        raise ValueError(f"digest mismatch: {path}")
    value = _json(path)
    if value.get("schema_version") != schema:
        raise ValueError(f"schema mismatch: {path}")
    return value


def _validate_config(config: Mapping[str, object]) -> None:
    if config.get("version") != "wp9c-synthetic1-response-lineage-rejoin-v1":
        raise ValueError("C16 config version drift")
    if config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1":
        raise ValueError("C16 active-pool protocol drift")
    targets = _mapping(config.get("targets"), context="C16 targets")
    if dict(targets) != {
        "deepcoder_primeintellect_exact": 541,
        "fixed_candidate_universe": 2505,
        "ready_before_final_piston": 1276,
        "under8_total": 1229,
        "external_new_exact": 2275,
        "minimum_primeintellect_successes_required": 311,
    }:
        raise ValueError("C16 target contract drift")
    isolation = _mapping(config.get("isolation"), context="C16 isolation")
    expected_isolation = {
        "incremental_candidate_supply_allowed": False,
        "source_expansion_allowed": False,
        "score_use_allowed": False,
        "execute_source_code": False,
        "generate_tests": False,
        "run_piston": False,
        "run_calibration": False,
        "run_grpo": False,
        "use_gpu": False,
        "threshold_relaxation_allowed": False,
    }
    if dict(isolation) != expected_isolation:
        raise ValueError("C16 isolation contract drift")
    lineage = _mapping(config.get("lineage"), context="C16 lineage")
    if dict(lineage) != {
        "prompt_match": "normalize_text_exact",
        "assistant_response_extractor": "code_verifier_extract_python_code_final_python_block_v1",
        "assistant_code_match": "exact_extracted_code_bytes",
        "unique_lineage_unit": "problem_id",
        "prompt_only_admissible": False,
        "fuzzy_prompt_allowed": False,
        "fuzzy_code_allowed": False,
    }:
        raise ValueError("C16 lineage contract drift")
    rejoin = _mapping(config.get("raw_vcp_rejoin"), context="C16 raw-VCP rejoin")
    if (
        rejoin.get("key") != "problem_id_exact"
        or rejoin.get("expected_rows") != 35735
        or rejoin.get("expected_shards") != 11
        or rejoin.get("require_unique_raw_row_per_problem_id") is not True
        or rejoin.get("gold_extractor") != "fenced_final_python_else_exact_plain_python"
        or rejoin.get("project_piston_required_later") is not True
        or rejoin.get("source_solution_transformation_required_later") is not True
        or rejoin.get("upstream_terms_review_required_later") is not True
    ):
        raise ValueError("C16 raw-VCP rejoin contract drift")


def _validate_sft_manifest(config: Mapping[str, object]) -> tuple[list[Path], str]:
    bindings = _mapping(config.get("bindings"), context="C16 bindings")
    sft = _mapping(config.get("sft_source"), context="C16 SFT source")
    checkpoint_path = ROOT / _require_str(bindings, "c15_checkpoint")
    if _sha(checkpoint_path) != bindings.get("c15_checkpoint_sha256"):
        raise ValueError("C16 C15 checkpoint digest drift")
    checkpoint = _json(checkpoint_path)
    verified_download = _mapping(checkpoint.get("verified_download"), context="C15 verified download")
    if (
        checkpoint.get("status") != "completed_download_verified"
        or checkpoint.get("candidate_supply_increment_allowed") is not False
        or verified_download.get("response_lineage_scan_run") is not False
        or verified_download.get("incremental_candidate_supply") != 0
    ):
        raise ValueError("C15 completed-download state drift")

    manifest_path = Path(_require_str(bindings, "c15_manifest"))
    manifest_sha = _sha(manifest_path)
    if manifest_sha != bindings.get("c15_manifest_sha256"):
        raise ValueError("C16 C15 manifest digest drift")
    sidecar = manifest_path.with_name("manifest.sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="ascii").strip() != manifest_sha:
        raise ValueError("C16 C15 manifest sidecar drift")
    manifest = _json(manifest_path)
    if (
        manifest.get("schema_version") != "wp9c-synthetic1-provenance-download-v1"
        or manifest.get("dataset_id") != sft.get("dataset_id")
        or manifest.get("revision") != sft.get("revision")
        or manifest.get("use_class") != "provenance_index_only"
        or manifest.get("incremental_candidate_supply") != 0
        or manifest.get("shard_count") != sft.get("expected_shards")
        or manifest.get("total_rows") != sft.get("expected_rows")
    ):
        raise ValueError("C16 C15 manifest identity drift")
    snapshot_value = manifest.get("snapshot_path")
    shard_values = manifest.get("shards")
    if not isinstance(snapshot_value, str) or not isinstance(shard_values, list):
        raise ValueError("C16 C15 manifest schema drift")
    snapshot = Path(snapshot_value).resolve()
    if snapshot.name != sft.get("revision"):
        raise ValueError("C16 SFT snapshot revision drift")
    expected_paths = [f"data/train-{index:05d}-of-00017.parquet" for index in range(17)]
    paths: list[Path] = []
    observed_paths: list[str] = []
    total_rows = 0
    for index, raw in enumerate(shard_values):
        row = _mapping(raw, context=f"C16 SFT shard {index}")
        relative = row.get("path")
        if set(row) != {"shard_index", "path", "sha256", "size", "rows"}:
            raise ValueError("C16 SFT shard manifest schema drift")
        if row.get("shard_index") != index or not isinstance(relative, str):
            raise ValueError("C16 SFT shard ordering drift")
        observed_paths.append(relative)
        path = snapshot / relative
        if not path.is_file() or path.stat().st_size != row.get("size"):
            raise ValueError(f"C16 SFT shard missing/size drift: {relative}")
        if _sha(path) != row.get("sha256"):
            raise ValueError(f"C16 SFT shard digest drift: {relative}")
        parquet_rows = pq.ParquetFile(path).metadata.num_rows
        if parquet_rows != row.get("rows"):
            raise ValueError(f"C16 SFT shard row drift: {relative}")
        total_rows += parquet_rows
        paths.append(path)
    if observed_paths != expected_paths or total_rows != sft.get("expected_rows"):
        raise ValueError("C16 SFT shard set/row-total drift")
    return paths, manifest_sha


def _validate_bound_evidence(config: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    bindings = _mapping(config.get("bindings"), context="C16 bindings")
    c8 = _verified_json(
        Path(_require_str(bindings, "c8_report")),
        bindings.get("c8_report_sha256"),
        schema="wp9c-deepcoder-function-supply-audit-v1",
    )
    c13 = _verified_json(
        Path(_require_str(bindings, "c13_report")),
        bindings.get("c13_report_sha256"),
        schema="wp9c-under8-augmentation-design-v1",
    )
    _verified_json(
        Path(_require_str(bindings, "c14_report")),
        bindings.get("c14_report_sha256"),
        schema="wp9c-local-vcp-lineage-recovery-v1",
    )
    c10 = _verified_json(
        Path(_require_str(bindings, "c10_report")),
        bindings.get("c10_report_sha256"),
        schema="wp9c-openr1-raw-python-provenance-audit-v1",
    )
    c11_path = ROOT / _require_str(bindings, "c11_checkpoint")
    c11 = _json(c11_path)
    pause = _mapping(c11.get("pause_directive"), context="historical C11 pause directive")
    if c11.get("status") != bindings.get("c11_required_status") or pause.get("download_authorized") is not False:
        raise ValueError("historical C11 pause state drift")
    c13_jobs = Path(_require_str(bindings, "c13_jobs"))
    if _sha(c13_jobs) != bindings.get("c13_jobs_sha256") or c13.get("jobs_sha256") != bindings.get("c13_jobs_sha256"):
        raise ValueError("C16 C13 jobs binding drift")
    return c8, c10


def _load_targets(config: Mapping[str, object], c8: Mapping[str, object]) -> list[Target]:
    bindings = _mapping(config.get("bindings"), context="C16 bindings")
    path = Path(_require_str(bindings, "c8_deepcoder_under8_candidates"))
    expected_sha = bindings.get("c8_deepcoder_under8_candidates_sha256")
    artifacts = _mapping(c8.get("artifact_sha256"), context="C8 artifact hashes")
    if _sha(path) != expected_sha or artifacts.get("deepcoder_under8_candidates") != expected_sha:
        raise ValueError("C16 frozen C8 target artifact digest drift")

    c13_jobs = {
        _require_str(row, "candidate_id"): row
        for row in _jsonl(Path(_require_str(bindings, "c13_jobs")))
        if row.get("source_name") == "deepcoder-primeintellect"
    }
    targets: list[Target] = []
    seen: set[str] = set()
    for row in _jsonl(path):
        if row.get("source_name") != "deepcoder-primeintellect":
            continue
        candidate_id = _require_str(row, "candidate_id")
        source_record_id = _require_str(row, "source_record_id")
        prompt = _require_str(row, "prompt")
        function_name = _require_str(row, "function_name")
        solutions = row.get("accepted_source_solutions")
        declared_count = row.get("accepted_source_solution_count")
        if (
            not isinstance(solutions, list)
            or len(solutions) != 1
            or not isinstance(solutions[0], str)
            or not solutions[0].strip()
            or declared_count != 1
        ):
            raise ValueError(f"C16 target must have exactly one accepted solution: {candidate_id}")
        if candidate_id in seen:
            raise ValueError("C16 duplicate DeepCoder candidate ID")
        seen.add(candidate_id)
        job = c13_jobs.get(candidate_id)
        if job is None or job.get("accepted_source_solution_count") != 1 or job.get("function_name") != function_name:
            raise ValueError(f"C16 C13 job binding drift: {candidate_id}")
        parsed = extract_python_code(solutions[0])
        if not parsed.success:
            raise ValueError(f"C16 target solution parse drift: {candidate_id}:{parsed.error_type}")
        prompt_norm = normalize_text(prompt)
        if not prompt_norm:
            raise ValueError(f"C16 empty normalized prompt: {candidate_id}")
        targets.append(
            Target(
                candidate_id=candidate_id,
                source_record_id=source_record_id,
                prompt_norm=prompt_norm,
                prompt_sha256=_text_sha(prompt_norm),
                function_name=function_name,
                deepcoder_solution=solutions[0],
                deepcoder_solution_sha256=_text_sha(solutions[0]),
                deepcoder_code=parsed.code,
                deepcoder_code_sha256=_text_sha(parsed.code),
            )
        )
    if len(targets) != 541 or len(c13_jobs) != 541:
        raise ValueError(f"C16 expected 541 targets/jobs, got {len(targets)}/{len(c13_jobs)}")
    return sorted(targets, key=lambda item: item.candidate_id)


def _message_pair(value: object, *, context: str) -> tuple[str, str]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{context}: messages must contain exactly two items")
    first, second = value
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise ValueError(f"{context}: message rows must be objects")
    if set(first) != {"role", "content"} or set(second) != {"role", "content"}:
        raise ValueError(f"{context}: message schema drift")
    if first.get("role") != "user" or second.get("role") != "assistant":
        raise ValueError(f"{context}: expected user/assistant roles")
    user_content = first.get("content")
    assistant_content = second.get("content")
    if (
        not isinstance(user_content, str)
        or not user_content.strip()
        or not isinstance(assistant_content, str)
        or not assistant_content.strip()
    ):
        raise ValueError(f"{context}: empty/non-string content")
    return user_content, assistant_content


def _scan_sft(
    paths: Sequence[Path],
    targets: Sequence[Target],
    *,
    required_task_type: str,
    expected_fields: set[str],
    scan_columns: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    prompt_index: dict[str, list[Target]] = defaultdict(list)
    for target in targets:
        prompt_index[target.prompt_norm].append(target)
    exact_hits: list[dict[str, object]] = []
    prompt_diagnostics: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    task_types: Counter[str] = Counter()

    for shard_index, path in enumerate(paths):
        parquet = pq.ParquetFile(path)
        if set(parquet.schema_arrow.names) != expected_fields:
            raise ValueError(f"C16 SFT source schema drift: {path.name}")
        local_row = 0
        for batch in parquet.iter_batches(batch_size=512, columns=scan_columns):
            for raw_row in cast(list[object], batch.to_pylist()):
                current_local = local_row
                local_row += 1
                counts["scanned_rows"] += 1
                if not isinstance(raw_row, dict) or set(raw_row) != set(scan_columns):
                    raise ValueError(f"C16 SFT projected schema drift: shard{shard_index}/{current_local}")
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
                    raise ValueError(f"C16 SFT identifier/task type drift: shard{shard_index}/{current_local}")
                task_types[task_type] += 1
                user_content, assistant_content = _message_pair(
                    row["messages"], context=f"C16 SFT shard{shard_index}/{current_local}"
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
                        if extracted_sha == target.deepcoder_code_sha256 and parsed.code == target.deepcoder_code:
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
            "score_field_used": False,
        },
    )


def _classify_lineage(
    targets: Sequence[Target],
    exact_hits: Sequence[Mapping[str, object]],
    prompt_diagnostics: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, str]]:
    hits_by_target: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    prompt_response_ids: dict[str, set[str]] = defaultdict(set)
    for hit in exact_hits:
        hits_by_target[_require_str(hit, "deepcoder_candidate_id")].append(hit)
    for diagnostic in prompt_diagnostics:
        response_id = _require_str(diagnostic, "response_id")
        candidate_ids = diagnostic.get("deepcoder_prompt_candidate_ids")
        if not isinstance(candidate_ids, list) or any(not isinstance(item, str) for item in candidate_ids):
            raise ValueError("C16 prompt diagnostic candidate IDs drift")
        for candidate_id in cast(list[str], candidate_ids):
            prompt_response_ids[candidate_id].add(response_id)

    rows: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    unique_problem_by_candidate: dict[str, str] = {}
    partition_ids: dict[str, list[str]] = defaultdict(list)
    for target in targets:
        hits = hits_by_target.get(target.candidate_id, [])
        response_ids = sorted({_require_str(hit, "response_id") for hit in hits})
        problem_ids = sorted({_require_str(hit, "problem_id") for hit in hits})
        if len(problem_ids) == 1:
            status = "unique_problem_id"
            unique_problem_by_candidate[target.candidate_id] = problem_ids[0]
            counts["unique_problem_id_rows"] += 1
            if len(response_ids) == 1:
                counts["unique_response_id_rows"] += 1
            else:
                counts["duplicate_response_same_problem_id_rows"] += 1
        elif len(problem_ids) > 1:
            status = "ambiguous_problem_id"
            counts["ambiguous_problem_id_rows"] += 1
        else:
            status = "unmatched"
            counts["unmatched_rows"] += 1
        partition_ids[status].append(target.candidate_id)
        rows.append(
            {
                "deepcoder_candidate_id": target.candidate_id,
                "deepcoder_source_record_id": target.source_record_id,
                "prompt_sha256": target.prompt_sha256,
                "function_name": target.function_name,
                "deepcoder_source_solution_sha256": target.deepcoder_solution_sha256,
                "deepcoder_extracted_code_sha256": target.deepcoder_code_sha256,
                "prompt_match_response_count": len(prompt_response_ids.get(target.candidate_id, set())),
                "exact_response_hit_count": len(hits),
                "exact_response_id_count": len(response_ids),
                "exact_problem_id_count": len(problem_ids),
                "lineage_status": status,
                "problem_ids": problem_ids,
                "response_ids": response_ids,
            }
        )
    if sum(counts[key] for key in ("unique_problem_id_rows", "ambiguous_problem_id_rows", "unmatched_rows")) != 541:
        raise ValueError("C16 lineage partition does not cover 541 targets")
    summary: dict[str, object] = {
        **dict(sorted(counts.items())),
        "target_count": len(targets),
        "unique_candidate_ids_sha256": _value_sha(sorted(partition_ids["unique_problem_id"])),
        "ambiguous_candidate_ids_sha256": _value_sha(sorted(partition_ids["ambiguous_problem_id"])),
        "unmatched_candidate_ids_sha256": _value_sha(sorted(partition_ids["unmatched"])),
    }
    return rows, summary, unique_problem_by_candidate


def _validate_raw_vcp_manifest(config: Mapping[str, object]) -> tuple[list[Path], str]:
    bindings = _mapping(config.get("bindings"), context="C16 bindings")
    c10_config_path = ROOT / _require_str(bindings, "c10_config")
    c10_config = load_yaml_mapping(c10_config_path)
    source = _mapping(c10_config.get("source"), context="C10 source config")
    manifest_path = Path(_require_str(bindings, "c10_download_manifest"))
    manifest_sha = _sha(manifest_path)
    if manifest_sha != bindings.get("c10_download_manifest_sha256"):
        raise ValueError("C16 C10 raw-VCP manifest digest drift")
    sidecar = manifest_path.with_name("manifest.sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="ascii").strip() != manifest_sha:
        raise ValueError("C16 C10 raw-VCP manifest sidecar drift")
    manifest = _json(manifest_path)
    if (
        manifest.get("schema_version") != "wp9c-openr1-raw-python-download-v1"
        or manifest.get("dataset_id") != source.get("dataset_id")
        or manifest.get("revision") != source.get("revision")
        or manifest.get("shard_count") != 11
        or manifest.get("total_rows") != 35735
    ):
        raise ValueError("C16 C10 raw-VCP manifest identity drift")
    snapshot_value = manifest.get("snapshot_path")
    shard_values = manifest.get("shards")
    if not isinstance(snapshot_value, str) or not isinstance(shard_values, list) or len(shard_values) != 11:
        raise ValueError("C16 C10 raw-VCP manifest schema drift")
    snapshot = Path(snapshot_value).resolve()
    if snapshot.name != source.get("revision"):
        raise ValueError("C16 raw-VCP snapshot revision drift")
    paths: list[Path] = []
    total_rows = 0
    for index, raw in enumerate(shard_values):
        row = _mapping(raw, context=f"C16 raw-VCP shard {index}")
        relative = row.get("path")
        if set(row) != {"shard_index", "path", "sha256", "size", "rows"}:
            raise ValueError("C16 raw-VCP shard manifest schema drift")
        if row.get("shard_index") != index or not isinstance(relative, str):
            raise ValueError("C16 raw-VCP shard ordering drift")
        path = snapshot / relative
        if not path.is_file() or path.stat().st_size != row.get("size"):
            raise ValueError(f"C16 raw-VCP shard missing/size drift: {relative}")
        if _sha(path) != row.get("sha256"):
            raise ValueError(f"C16 raw-VCP shard digest drift: {relative}")
        parquet_rows = pq.ParquetFile(path).metadata.num_rows
        if parquet_rows != row.get("rows"):
            raise ValueError(f"C16 raw-VCP shard row drift: {relative}")
        total_rows += parquet_rows
        paths.append(path)
    if total_rows != 35735:
        raise ValueError("C16 raw-VCP row total drift")
    return paths, manifest_sha


def _extract_gold_code(gold: str) -> tuple[str | None, str | None]:
    if not gold.strip():
        return None, "empty_gold"
    if "```" in gold:
        parsed = extract_python_code(gold)
        if not parsed.success:
            return None, f"fenced_extract:{parsed.error_type}"
        return parsed.code, None
    plain = gold.strip()
    try:
        ast.parse(plain)
    except (SyntaxError, ValueError, UnicodeError, MemoryError, RecursionError):
        return None, "plain_invalid_python"
    return plain, None


def _problem_url(metadata: object) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("problem_url")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _scan_raw_vcp_rejoin(
    paths: Sequence[Path],
    problem_ids: set[str],
    *,
    collect_fields: list[str],
) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    expected_fields = {
        "source",
        "task_type",
        "in_source_id",
        "problem_statement",
        "gold_standard_solution",
        "problem_id",
        "metadata",
        "verification_info",
    }
    hits: dict[str, list[dict[str, object]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for shard_index, path in enumerate(paths):
        parquet = pq.ParquetFile(path)
        if set(parquet.schema_arrow.names) != expected_fields:
            raise ValueError(f"C16 raw-VCP schema drift: {path.name}")
        local_row = 0
        for batch in parquet.iter_batches(batch_size=256, columns=collect_fields):
            for raw_row in cast(list[object], batch.to_pylist()):
                current_local = local_row
                local_row += 1
                counts["scanned_rows"] += 1
                if not isinstance(raw_row, dict) or set(raw_row) != set(collect_fields):
                    raise ValueError(f"C16 raw-VCP projected schema drift: shard{shard_index}/{current_local}")
                row = cast(Mapping[str, object], raw_row)
                problem_id = row.get("problem_id")
                if not isinstance(problem_id, str) or not problem_id:
                    raise ValueError(f"C16 raw-VCP problem_id drift: shard{shard_index}/{current_local}")
                if problem_id not in problem_ids:
                    continue
                counts["rejoin_hit_rows"] += 1
                source = row.get("source")
                in_source_id = row.get("in_source_id")
                problem_statement = row.get("problem_statement")
                gold = row.get("gold_standard_solution")
                if not isinstance(source, str) or not isinstance(problem_statement, str) or not isinstance(gold, str):
                    raise ValueError(f"C16 raw-VCP rejoin row schema drift: {problem_id}")
                url = _problem_url(row.get("metadata"))
                hits[problem_id].append(
                    {
                        "problem_id": problem_id,
                        "raw_vcp_shard_index": shard_index,
                        "raw_vcp_local_row": current_local,
                        "upstream_source": source,
                        "in_source_id": in_source_id,
                        "problem_statement_sha256": _text_sha(problem_statement),
                        "problem_url_hash": None if url is None else _text_sha(url),
                        "gold_standard_solution": gold,
                        "gold_standard_solution_sha256": _text_sha(gold),
                    }
                )
    return hits, {"scanned_rows": counts["scanned_rows"], "rejoin_hit_rows": counts["rejoin_hit_rows"]}


def _build_rejoin_rows(
    targets: Sequence[Target],
    unique_problem_by_candidate: Mapping[str, str],
    raw_hits: Mapping[str, Sequence[Mapping[str, object]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    target_by_id = {target.candidate_id: target for target in targets}
    rows: list[dict[str, object]] = []
    second_oracle_candidates: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    status_ids: dict[str, list[str]] = defaultdict(list)
    source_counts: Counter[str] = Counter()

    for candidate_id in sorted(unique_problem_by_candidate):
        target = target_by_id[candidate_id]
        problem_id = unique_problem_by_candidate[candidate_id]
        hits = list(raw_hits.get(problem_id, []))
        if len(hits) == 1:
            status = "unique_raw_vcp_row"
            counts["unique_raw_vcp_rejoin_rows"] += 1
            hit = hits[0]
            gold = _require_str(hit, "gold_standard_solution")
            gold_code, extract_error = _extract_gold_code(gold)
            gold_code_sha = None if gold_code is None else _text_sha(gold_code)
            distinct = gold_code_sha is not None and gold_code_sha != target.deepcoder_code_sha256
            if gold_code is None:
                counts[f"gold_extract_error:{extract_error}"] += 1
            else:
                counts["extractable_raw_gold_rows"] += 1
                if distinct:
                    counts["distinct_raw_gold_code_rows"] += 1
                else:
                    counts["same_code_bytes_as_deepcoder_rows"] += 1
            static_candidate = gold_code is not None and distinct
            if static_candidate:
                counts["second_oracle_static_candidate_rows"] += 1
                second_oracle_candidates.append(
                    {
                        "deepcoder_candidate_id": candidate_id,
                        "deepcoder_source_record_id": target.source_record_id,
                        "function_name": target.function_name,
                        "problem_id": problem_id,
                        "deepcoder_source_solution_sha256": target.deepcoder_solution_sha256,
                        "deepcoder_extracted_code_sha256": target.deepcoder_code_sha256,
                        "raw_vcp_upstream_source": hit.get("upstream_source"),
                        "raw_vcp_in_source_id": hit.get("in_source_id"),
                        "raw_vcp_problem_url_hash": hit.get("problem_url_hash"),
                        "raw_gold_standard_solution": gold,
                        "raw_gold_standard_solution_sha256": hit.get("gold_standard_solution_sha256"),
                        "raw_gold_extracted_code_sha256": gold_code_sha,
                        "source_solution_transformation_required": True,
                        "project_piston_qualification_required": True,
                        "upstream_terms_review_required": True,
                        "formal_admitted": False,
                    }
                )
            source = hit.get("upstream_source")
            if isinstance(source, str):
                source_counts[source] += 1
            row = {
                "deepcoder_candidate_id": candidate_id,
                "deepcoder_source_record_id": target.source_record_id,
                "function_name": target.function_name,
                "problem_id": problem_id,
                "raw_vcp_rejoin_status": status,
                "raw_vcp_hit_count": 1,
                "raw_vcp_upstream_source": hit.get("upstream_source"),
                "raw_vcp_in_source_id": hit.get("in_source_id"),
                "raw_vcp_problem_url_hash": hit.get("problem_url_hash"),
                "raw_gold_standard_solution_sha256": hit.get("gold_standard_solution_sha256"),
                "raw_gold_extract_success": gold_code is not None,
                "raw_gold_extract_error": extract_error,
                "raw_gold_extracted_code_sha256": gold_code_sha,
                "raw_gold_code_distinct_from_deepcoder": distinct,
                "second_oracle_static_candidate": static_candidate,
                "project_piston_qualification_run": False,
                "formal_admitted": False,
            }
        elif len(hits) > 1:
            status = "ambiguous_raw_vcp_rows"
            counts["ambiguous_raw_vcp_rejoin_rows"] += 1
            row = {
                "deepcoder_candidate_id": candidate_id,
                "deepcoder_source_record_id": target.source_record_id,
                "function_name": target.function_name,
                "problem_id": problem_id,
                "raw_vcp_rejoin_status": status,
                "raw_vcp_hit_count": len(hits),
                "second_oracle_static_candidate": False,
                "project_piston_qualification_run": False,
                "formal_admitted": False,
            }
        else:
            status = "missing_raw_vcp_row"
            counts["missing_raw_vcp_rejoin_rows"] += 1
            row = {
                "deepcoder_candidate_id": candidate_id,
                "deepcoder_source_record_id": target.source_record_id,
                "function_name": target.function_name,
                "problem_id": problem_id,
                "raw_vcp_rejoin_status": status,
                "raw_vcp_hit_count": 0,
                "second_oracle_static_candidate": False,
                "project_piston_qualification_run": False,
                "formal_admitted": False,
            }
        status_ids[status].append(candidate_id)
        rows.append(row)

    summary: dict[str, object] = {
        **dict(sorted(counts.items())),
        "unique_lineage_candidates_submitted_for_rejoin": len(unique_problem_by_candidate),
        "raw_vcp_upstream_source_counts": dict(sorted(source_counts.items())),
        "unique_rejoin_candidate_ids_sha256": _value_sha(sorted(status_ids["unique_raw_vcp_row"])),
        "ambiguous_rejoin_candidate_ids_sha256": _value_sha(sorted(status_ids["ambiguous_raw_vcp_rows"])),
        "missing_rejoin_candidate_ids_sha256": _value_sha(sorted(status_ids["missing_raw_vcp_row"])),
        "second_oracle_static_candidate_ids_sha256": _value_sha(
            sorted(cast(str, row["deepcoder_candidate_id"]) for row in second_oracle_candidates)
        ),
    }
    return rows, second_oracle_candidates, summary


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C16 output: {output_dir}")
    temporary = Path(f"{output_dir}.tmp")
    if temporary.exists():
        raise FileExistsError(f"refusing to overwrite C16 temporary output: {temporary}")

    config = load_yaml_mapping(config_path)
    _validate_config(config)
    c8, c10 = _validate_bound_evidence(config)
    sft_paths, sft_manifest_sha = _validate_sft_manifest(config)
    raw_paths, raw_manifest_sha = _validate_raw_vcp_manifest(config)
    targets = _load_targets(config, c8)

    sft = _mapping(config.get("sft_source"), context="C16 SFT source")
    expected_fields_value = sft.get("expected_schema_fields")
    scan_columns_value = sft.get("scan_columns")
    if (
        not isinstance(expected_fields_value, list)
        or any(not isinstance(item, str) for item in expected_fields_value)
        or not isinstance(scan_columns_value, list)
        or any(not isinstance(item, str) for item in scan_columns_value)
        or "score" in scan_columns_value
        or "score" not in expected_fields_value
        or sft.get("score_field_must_not_be_loaded") is not True
    ):
        raise ValueError("C16 SFT score/schema isolation drift")
    exact_hits, prompt_diagnostics, sft_scan_summary = _scan_sft(
        sft_paths,
        targets,
        required_task_type=_require_str(sft, "required_task_type"),
        expected_fields=set(cast(list[str], expected_fields_value)),
        scan_columns=cast(list[str], scan_columns_value),
    )
    if sft_scan_summary["scanned_rows"] != 894086:
        raise ValueError("C16 SFT scanned row count drift")
    lineage_rows, lineage_summary, unique_problem_by_candidate = _classify_lineage(
        targets, exact_hits, prompt_diagnostics
    )

    rejoin = _mapping(config.get("raw_vcp_rejoin"), context="C16 raw-VCP rejoin")
    collect_fields_value = rejoin.get("collect_fields")
    if not isinstance(collect_fields_value, list) or any(not isinstance(item, str) for item in collect_fields_value):
        raise ValueError("C16 raw-VCP collect field contract drift")
    raw_hits, raw_scan_summary = _scan_raw_vcp_rejoin(
        raw_paths,
        set(unique_problem_by_candidate.values()),
        collect_fields=cast(list[str], collect_fields_value),
    )
    if raw_scan_summary["scanned_rows"] != 35735:
        raise ValueError("C16 raw-VCP scanned row count drift")
    rejoin_rows, second_oracle_candidates, rejoin_summary = _build_rejoin_rows(
        targets, unique_problem_by_candidate, raw_hits
    )

    minimum_required = cast(
        int, _mapping(config.get("targets"), context="C16 targets")["minimum_primeintellect_successes_required"]
    )
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()
    try:
        artifacts = {
            "target_lineage": _write_jsonl(temporary / "target_lineage.jsonl", lineage_rows),
            "response_hits": _write_jsonl(temporary / "response_hits.jsonl", exact_hits),
            "prompt_diagnostics": _write_jsonl(temporary / "prompt_diagnostics.jsonl", prompt_diagnostics),
            "raw_vcp_rejoin": _write_jsonl(temporary / "raw_vcp_rejoin.jsonl", rejoin_rows),
            "second_oracle_candidates": _write_jsonl(
                temporary / "second_oracle_candidates.jsonl", second_oracle_candidates
            ),
        }
        report: dict[str, object] = {
            "schema_version": "wp9c-synthetic1-response-lineage-rejoin-v1",
            "protocol_amendment": "wp9c-active-pool-2500-amendment-v1",
            "evidence_class": "engineering_provenance_and_static_oracle_rejoin",
            "formal_eligible": False,
            "candidate_supply_increment": 0,
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "audit_script_sha256": _sha(Path(__file__)),
            "sft_manifest_sha256": sft_manifest_sha,
            "raw_vcp_manifest_sha256": raw_manifest_sha,
            "target_count": len(targets),
            "sft_scan_summary": sft_scan_summary,
            "lineage_summary": lineage_summary,
            "raw_vcp_scan_summary": raw_scan_summary,
            "raw_vcp_rejoin_summary": rejoin_summary,
            "minimum_primeintellect_successes_required": minimum_required,
            "second_oracle_static_candidate_count": len(second_oracle_candidates),
            "minimum_required_static_oracle_candidate_count_met": len(second_oracle_candidates) >= minimum_required,
            "score_isolation": {
                "score_field_present_in_source_schema": True,
                "score_field_loaded_into_scan_batches": False,
                "score_value_used_for_matching": False,
                "score_value_used_for_selection": False,
                "score_value_used_for_supply": False,
            },
            "execution_boundaries": {
                "source_solution_execution_run": False,
                "test_generation_run": False,
                "piston_run": False,
                "calibration_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "baseline": {
                "c10_strict_provenance_result": c10.get("deepcoder_provenance_recovery"),
                "fixed_candidate_universe": 2505,
                "ready_before_final_piston": 1276,
                "under8_total": 1229,
            },
            "formal_blockers": [
                "C16_is_provenance_and_static_oracle_rejoin_only",
                "unmatched_or_ambiguous_response_lineage_must_remain_excluded",
                "missing_or_ambiguous_raw_VCP_rejoin_must_remain_excluded",
                "raw_VCP_upstream_terms_review_not_completed",
                "source_solution_transformation_not_frozen_for_rejoined_gold",
                "project_Piston_source_solution_qualification_not_run",
                "under8_test_augmentation_not_run",
                "final_augmented_Exact_B_context_recheck_not_run",
                "final_formal_function_level_Piston_not_run",
            ],
            "next_gate": "C17-manual-source-solution-transformation-and-project-piston-qualification",
            "artifact_sha256": artifacts,
            "notes": [
                "Exact response lineage requires normalized-prompt equality and exact shared-extractor code bytes.",
                "Only unique lineage problem_id values are rejoined to raw VCP, using exact problem_id equality.",
                "A distinct extractable raw gold solution is only a static second-oracle candidate at C16.",
                (
                    "No rejoined solution is trusted until later source-solution transformation and project "
                    "Piston qualification."
                ),
                "The SFT score column is present in schema but excluded from scan batches and unused.",
            ],
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii")
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
