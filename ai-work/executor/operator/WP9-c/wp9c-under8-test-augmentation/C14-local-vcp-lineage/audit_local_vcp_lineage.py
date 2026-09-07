#!/usr/bin/env python3
"""Audit local raw-VCP task lineage for frozen DeepCoder-PrimeIntellect rows."""

from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, normalize_text
from code_verifier.data.json_strict import loads_strict
from code_verifier.parsing.code_extractor import extract_python_code

ROOT = Path(__file__).resolve().parents[6]
C11_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/checkpoint.json"
C8_TARGETS = Path("/home/dzy/wp9c-deepcoder-function-supply-audit-C8/deepcoder_under8_candidates.jsonl")
EXPECTED_RAW_FIELDS = {
    "source",
    "task_type",
    "in_source_id",
    "problem_statement",
    "gold_standard_solution",
    "problem_id",
    "metadata",
    "verification_info",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
    return _sha(path)


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


def _extract_raw_gold_code(gold: str) -> tuple[str | None, str]:
    if not gold.strip():
        return None, "empty"
    if "```" in gold:
        parsed = extract_python_code(gold)
        if not parsed.success:
            return None, f"fenced_parse:{parsed.error_type}"
        return parsed.code, "final_fenced_python"
    plain = gold.strip()
    try:
        ast.parse(plain)
    except (SyntaxError, ValueError, UnicodeError, MemoryError, RecursionError):
        return None, "plain_invalid_python"
    return plain, "plain_python_stripped"


def _problem_url(metadata: object) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("problem_url")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _validate_config(config: Mapping[str, object]) -> None:
    if config.get("version") != "wp9c-local-vcp-lineage-recovery-v1":
        raise ValueError("local lineage config version mismatch")
    if config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1":
        raise ValueError("active-pool protocol mismatch")
    matching = config.get("matching")
    isolation = config.get("isolation")
    if not isinstance(matching, dict) or not isinstance(isolation, dict):
        raise ValueError("local lineage config structure is invalid")
    if matching != {
        "prompt": "normalize_text_exact",
        "deepcoder_solution": "shared_final_python_block_exact",
        "raw_gold_solution": "fenced_final_python_else_exact_plain_python",
        "strict_lineage_key": "normalized_prompt_plus_exact_code_bytes",
        "prompt_only_is_formal_lineage": False,
        "fuzzy_prompt_allowed": False,
        "fuzzy_code_allowed": False,
        "incremental_candidate_supply_allowed": False,
    }:
        raise ValueError("local lineage matching contract drift")
    for key in (
        "source_expansion_allowed",
        "download_allowed",
        "generate_tests",
        "execute_source_code",
        "run_piston",
        "threshold_relaxation_allowed",
    ):
        if isolation.get(key) is not False:
            raise ValueError(f"local lineage isolation drift: {key}")
    if isolation.get("c11_must_remain_paused") is not True:
        raise ValueError("C11 pause requirement drift")


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    design = cast(Mapping[str, object], config["augmentation_design"])
    c8_cfg = cast(Mapping[str, object], config["c8"])
    c10_cfg = cast(Mapping[str, object], config["c10"])

    c13_report_path = Path(_require_str(design, "c13_report"))
    c13_jobs_path = Path(_require_str(design, "c13_jobs"))
    c13 = _verified_json(
        c13_report_path,
        design.get("c13_report_sha256"),
        schema="wp9c-under8-augmentation-design-v1",
    )
    if _sha(c13_jobs_path) != design.get("c13_jobs_sha256") or c13.get("jobs_sha256") != design.get("c13_jobs_sha256"):
        raise ValueError("C13 jobs binding drift")
    jobs = _jsonl(c13_jobs_path)
    prime_jobs = [row for row in jobs if row.get("source_name") == "deepcoder-primeintellect"]
    if len(prime_jobs) != design.get("deepcoder_primeintellect_targets"):
        raise ValueError("C13 DeepCoder-PrimeIntellect target count drift")
    if any(
        row.get("accepted_source_solution_count")
        != design.get("deepcoder_primeintellect_accepted_solutions_per_target")
        for row in prime_jobs
    ):
        raise ValueError("C13 DeepCoder-PrimeIntellect accepted-solution count drift")

    c8_report_path = Path(_require_str(c8_cfg, "report"))
    c8 = _verified_json(c8_report_path, c8_cfg.get("report_sha256"), schema="wp9c-deepcoder-function-supply-audit-v1")
    c8_artifacts = c8.get("artifact_sha256")
    if not isinstance(c8_artifacts, dict) or c8_artifacts.get("deepcoder_under8_candidates") != _sha(C8_TARGETS):
        raise ValueError("C8 frozen target artifact digest drift")

    c10_report_path = Path(_require_str(c10_cfg, "report"))
    c10 = _verified_json(
        c10_report_path,
        c10_cfg.get("report_sha256"),
        schema="wp9c-openr1-raw-python-provenance-audit-v1",
    )
    c10_config_path = ROOT / _require_str(c10_cfg, "config")
    c10_source_config = load_yaml_mapping(c10_config_path)
    c10_source = c10_source_config.get("source")
    if not isinstance(c10_source, dict):
        raise ValueError("C10 source config missing")
    manifest_path = Path(_require_str(c10_cfg, "download_manifest"))
    manifest_sha = _sha(manifest_path)
    if manifest_sha != c10_cfg.get("download_manifest_sha256") or c10.get("download_manifest_sha256") != manifest_sha:
        raise ValueError("C10 download manifest binding drift")
    manifest = _json(manifest_path)
    if (
        manifest.get("schema_version") != "wp9c-openr1-raw-python-download-v1"
        or manifest.get("dataset_id") != c10_source.get("dataset_id")
        or manifest.get("revision") != c10_source.get("revision")
        or manifest.get("shard_count") != c10_cfg.get("expected_shards")
        or manifest.get("total_rows") != c10_cfg.get("expected_rows")
    ):
        raise ValueError("C10 download manifest identity drift")
    snapshot = Path(_require_str(manifest, "snapshot_path"))
    shard_rows = manifest.get("shards")
    if not isinstance(shard_rows, list) or len(shard_rows) != c10_cfg.get("expected_shards"):
        raise ValueError("C10 shard inventory drift")
    for index, shard in enumerate(shard_rows):
        if not isinstance(shard, dict) or set(shard) != {"shard_index", "path", "sha256", "size", "rows"}:
            raise ValueError("C10 shard manifest schema drift")
        if shard.get("shard_index") != index:
            raise ValueError("C10 shard ordering drift")
        shard_path = snapshot / _require_str(shard, "path")
        if not shard_path.is_file() or shard_path.stat().st_size != shard.get("size"):
            raise ValueError(f"C10 local shard missing/size drift: {shard_path}")

    c11 = _json(C11_CHECKPOINT)
    if c11.get("status") != "paused_by_user":
        raise ValueError("C11 must remain paused")
    pause = c11.get("pause_directive")
    if not isinstance(pause, dict) or pause.get("download_authorized") is not False:
        raise ValueError("C11 pause directive drift")

    targets: dict[str, dict[str, object]] = {}
    strict_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    prompt_index: dict[str, set[str]] = defaultdict(set)
    for row in _jsonl(C8_TARGETS):
        if row.get("source_name") != "deepcoder-primeintellect":
            continue
        candidate_id = _require_str(row, "candidate_id")
        prompt = _require_str(row, "prompt")
        solutions = row.get("accepted_source_solutions")
        if not isinstance(solutions, list) or len(solutions) != 1 or not isinstance(solutions[0], str):
            raise ValueError(f"DeepCoder target must have exactly one source solution: {candidate_id}")
        parsed = extract_python_code(solutions[0])
        if not parsed.success:
            raise ValueError(f"DeepCoder target solution no longer parses: {candidate_id}:{parsed.error_type}")
        prompt_norm = normalize_text(prompt)
        code_sha = _text_sha(parsed.code)
        strict_index[(prompt_norm, code_sha)].add(candidate_id)
        prompt_index[prompt_norm].add(candidate_id)
        targets[candidate_id] = {
            "candidate_id": candidate_id,
            "source_record_id": row.get("source_record_id"),
            "prompt_sha256": _text_sha(prompt),
            "normalized_prompt_sha256": _text_sha(prompt_norm),
            "deepcoder_extracted_code_sha256": code_sha,
            "deepcoder_source_solution_sha256": _text_sha(solutions[0]),
        }
    if len(targets) != design.get("deepcoder_primeintellect_targets"):
        raise ValueError("DeepCoder target reconstruction drift")

    prompt_hits: dict[str, list[dict[str, object]]] = defaultdict(list)
    strict_hits: dict[str, list[dict[str, object]]] = defaultdict(list)
    raw_reason_counts: Counter[str] = Counter()
    scanned_rows = 0
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    scan_columns = ["source", "in_source_id", "problem_statement", "gold_standard_solution", "problem_id", "metadata"]
    for shard in cast(list[dict[str, object]], shard_rows):
        shard_index = cast(int, shard["shard_index"])
        shard_path = snapshot / cast(str, shard["path"])
        parquet = pq.ParquetFile(shard_path)
        if set(parquet.schema_arrow.names) != EXPECTED_RAW_FIELDS:
            raise ValueError(f"raw VCP schema drift: shard {shard_index}")
        local_row = 0
        for batch in parquet.iter_batches(batch_size=256, columns=scan_columns):
            for raw_row in batch.to_pylist():
                current_local = local_row
                local_row += 1
                scanned_rows += 1
                if not isinstance(raw_row, Mapping):
                    raise ValueError(f"raw VCP row is not a mapping: shard {shard_index}:{current_local}")
                problem = raw_row.get("problem_statement")
                if not isinstance(problem, str) or not problem.strip():
                    continue
                prompt_norm = normalize_text(problem)
                candidate_ids = prompt_index.get(prompt_norm)
                if not candidate_ids:
                    continue
                raw_reason_counts["prompt_match_rows"] += 1
                gold = raw_row.get("gold_standard_solution")
                raw_code: str | None = None
                extraction_mode = "missing_gold"
                if isinstance(gold, str):
                    raw_code, extraction_mode = _extract_raw_gold_code(gold)
                if raw_code is None:
                    raw_reason_counts[f"gold_extract:{extraction_mode}"] += 1
                    raw_code_sha: str | None = None
                else:
                    raw_reason_counts[f"gold_extract:{extraction_mode}"] += 1
                    raw_code_sha = _text_sha(raw_code)
                raw_problem_id = raw_row.get("problem_id")
                if not isinstance(raw_problem_id, str) or not raw_problem_id:
                    raise ValueError(f"prompt-matched raw row lacks problem_id: shard {shard_index}:{current_local}")
                problem_url = _problem_url(raw_row.get("metadata"))
                hit = {
                    "raw_problem_id": raw_problem_id,
                    "raw_source": raw_row.get("source"),
                    "raw_in_source_id": raw_row.get("in_source_id"),
                    "raw_shard_index": shard_index,
                    "raw_local_row": current_local,
                    "raw_problem_url_hash": None if problem_url is None else _text_sha(problem_url),
                    "raw_gold_solution_sha256": None if not isinstance(gold, str) else _text_sha(gold),
                    "raw_gold_code_sha256": raw_code_sha,
                    "raw_gold_extraction_mode": extraction_mode,
                }
                for candidate_id in sorted(candidate_ids):
                    prompt_hits[candidate_id].append(hit)
                if raw_code_sha is not None:
                    strict_candidate_ids = strict_index.get((prompt_norm, raw_code_sha), set())
                    for candidate_id in sorted(strict_candidate_ids):
                        strict_hits[candidate_id].append(hit)

    if scanned_rows != c10_cfg.get("expected_rows"):
        raise ValueError(f"raw VCP scanned row count drift: {scanned_rows}")

    lineage_rows: list[dict[str, object]] = []
    strict_partition: Counter[str] = Counter()
    prompt_partition: Counter[str] = Counter()
    distinct_gold_prompt_unique_extractable = 0
    for candidate_id in sorted(targets):
        target = targets[candidate_id]
        candidate_prompt_hits = prompt_hits.get(candidate_id, [])
        candidate_strict_hits = strict_hits.get(candidate_id, [])
        prompt_problem_ids = sorted({_require_str(hit, "raw_problem_id") for hit in candidate_prompt_hits})
        strict_problem_ids = sorted({_require_str(hit, "raw_problem_id") for hit in candidate_strict_hits})
        prompt_status = (
            "unmatched"
            if not prompt_problem_ids
            else "unique_problem_id"
            if len(prompt_problem_ids) == 1
            else "ambiguous_problem_id"
        )
        strict_status = (
            "unmatched"
            if not strict_problem_ids
            else "unique_problem_id"
            if len(strict_problem_ids) == 1
            else "ambiguous_problem_id"
        )
        prompt_partition[prompt_status] += 1
        strict_partition[strict_status] += 1
        prompt_unique_distinct_hits: list[dict[str, object]] = []
        if prompt_status == "unique_problem_id":
            deep_code_sha = cast(str, target["deepcoder_extracted_code_sha256"])
            for hit in candidate_prompt_hits:
                hit_code_sha = hit.get("raw_gold_code_sha256")
                if isinstance(hit_code_sha, str) and hit_code_sha != deep_code_sha:
                    prompt_unique_distinct_hits.append(hit)
            if prompt_unique_distinct_hits:
                distinct_gold_prompt_unique_extractable += 1
        lineage_rows.append(
            {
                **target,
                "strict_lineage_status": strict_status,
                "strict_problem_ids": strict_problem_ids,
                "strict_hit_count": len(candidate_strict_hits),
                "prompt_lineage_status_diagnostic_only": prompt_status,
                "prompt_problem_ids_diagnostic_only": prompt_problem_ids,
                "prompt_hit_count": len(candidate_prompt_hits),
                "prompt_unique_distinct_gold_code_hit_count": len(prompt_unique_distinct_hits),
                "prompt_unique_distinct_gold_code_problem_ids": sorted(
                    {_require_str(hit, "raw_problem_id") for hit in prompt_unique_distinct_hits}
                ),
                "formal_lineage_admitted": strict_status == "unique_problem_id",
                "independent_second_oracle_established": False,
                "independent_second_oracle_reason": (
                    "strict_exact_code_match_is_not_code_independent"
                    if strict_status == "unique_problem_id"
                    else "prompt_only_or_unmatched_does_not_establish_formal_lineage"
                ),
            }
        )

    strict_unique = strict_partition["unique_problem_id"]
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        lineage_sha = _write_jsonl(temporary / "lineage.jsonl", lineage_rows)
        strict_hit_rows = [
            {"candidate_id": candidate_id, **hit}
            for candidate_id in sorted(strict_hits)
            for hit in strict_hits[candidate_id]
        ]
        prompt_hit_rows = [
            {"candidate_id": candidate_id, **hit}
            for candidate_id in sorted(prompt_hits)
            for hit in prompt_hits[candidate_id]
        ]
        strict_hits_sha = _write_jsonl(temporary / "strict_hits.jsonl", strict_hit_rows)
        prompt_hits_sha = _write_jsonl(temporary / "prompt_hits.jsonl", prompt_hit_rows)
        report: dict[str, object] = {
            "schema_version": "wp9c-local-vcp-lineage-recovery-v1",
            "evidence_class": "engineering_local_provenance_audit",
            "formal_eligible": False,
            "active_pool_protocol": "wp9c-active-pool-2500-amendment-v1",
            "target_count": len(targets),
            "raw_rows_scanned": scanned_rows,
            "raw_reason_counts": dict(sorted(raw_reason_counts.items())),
            "strict_lineage_partition": dict(sorted(strict_partition.items())),
            "prompt_lineage_partition_diagnostic_only": dict(sorted(prompt_partition.items())),
            "strict_unique_lineage_count": strict_unique,
            "prompt_unique_with_distinct_extractable_gold_code_count": distinct_gold_prompt_unique_extractable,
            "independent_second_oracle_established_count": 0,
            "candidate_supply_increment": 0,
            "c11_status_after_audit": c11.get("status"),
            "c11_download_run": False,
            "source_solution_execution_run": False,
            "piston_run": False,
            "test_generation_run": False,
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "audit_script_sha256": _sha(Path(__file__)),
            "artifact_sha256": {
                "lineage": lineage_sha,
                "strict_hits": strict_hits_sha,
                "prompt_hits": prompt_hits_sha,
            },
            "bindings": {
                "c13_report_sha256": design["c13_report_sha256"],
                "c13_jobs_sha256": design["c13_jobs_sha256"],
                "c8_report_sha256": c8_cfg["report_sha256"],
                "c10_report_sha256": c10_cfg["report_sha256"],
                "c10_download_manifest_sha256": manifest_sha,
                "c11_checkpoint_sha256": _sha(C11_CHECKPOINT),
            },
            "decision": {
                "local_exact_code_lineage_can_close_provenance_for_strict_unique_rows": strict_unique > 0,
                "local_exact_code_lineage_provides_independent_second_oracle": False,
                "prompt_unique_distinct_gold_is_diagnostic_only": True,
                "provenance_only_response_lineage_gate_still_required_for_unresolved_rows": strict_unique
                < len(targets),
                "additional_independent_solution_source_required_for_multi_solution_consensus": True,
            },
            "notes": [
                (
                    "This audit scans only the already-downloaded C10 raw-VCP snapshot and does not download "
                    "or add candidates."
                ),
                "Strict lineage requires exact normalized prompt plus exact extracted code bytes.",
                "Prompt-only matches remain diagnostic and are never formal lineage under the frozen contract.",
                (
                    "Even strict exact-code lineage does not create an independent second oracle because the "
                    "code bytes are identical."
                ),
            ],
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
    print(canonical_json(audit(Path(args.config).resolve(), Path(args.output_dir).resolve())))


if __name__ == "__main__":
    main()
