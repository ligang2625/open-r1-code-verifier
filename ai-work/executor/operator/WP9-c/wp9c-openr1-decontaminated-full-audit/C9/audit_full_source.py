#!/usr/bin/env python3
"""C9 full Open-R1 decontaminated audit for provenance recovery and incremental supply."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from types import ModuleType
from typing import cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, normalize_text, stable_json_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.data.refresh_dedup import RefreshDedupPolicy, classify_refresh_candidates
from code_verifier.data.refresh_sources import (
    Difficulty,
    RefreshCandidate,
    _function_signature_from_row,
    refresh_test_set_fingerprint,
)
from code_verifier.data.schema import test_case_to_mapping

ROOT = Path(__file__).resolve().parents[6]
C6_FULL_SCRIPT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/audit_full_taco_supply.py"
C6_CORRECTION_SCRIPT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/audit_context_correction.py"
)
C8_SCRIPT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-deepcoder-function-supply-audit/C8/audit_deepcoder_function_supply.py"
)
SAMPLE_SCRIPT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_openr1_decontaminated_sample.py"
)
C8_DIR = Path("/home/dzy/wp9c-deepcoder-function-supply-audit-C8")
C7_DIR = Path("/home/dzy/wp9c-taco-under8-supply-audit-C7")


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load C9 dependency: {path}")
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


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = loads_strict(line)
            if not isinstance(value, dict):
                raise ValueError(f"non-object JSONL row: {path}")
            rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    payload = "".join(canonical_json(row) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_config(config: Mapping[str, object]) -> None:
    if (
        config.get("version") != "wp9c-openr1-decontaminated-full-audit-v1"
        or config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
        or config.get("seed") != 42
    ):
        raise ValueError("C9 protocol/seed drift")
    targets = cast(Mapping[str, object], config["targets"])
    if dict(targets) != {
        "active_pool": 2500,
        "sft_reuse_exact": 225,
        "external_new_exact": 2275,
        "pre_piston_external_new_buffer_min": 2600,
        "pre_piston_external_new_buffer_target": 2800,
    }:
        raise ValueError("C9 target drift")
    selection = cast(Mapping[str, object], config["selection"])
    if dict(selection) != {
        "minimum_unique_tests": 1,
        "under8_maximum_unique_tests": 7,
        "ready_minimum_unique_tests": 8,
        "max_prompt_tokens": 2048,
        "formal_prompt_protocol": "canonicalize_refresh_candidate_seed42_then_build_code_prompt_v1",
        "preaugmentation_prompt_protocol": "build_code_prompt_from_fields_preaugmentation_visible_proxy_v1",
        "token_ngram_size": 5,
        "near_jaccard_threshold": 0.90,
        "priority": "current_ready_then_c8_union_then_openr1_new",
        "deepcoder_provenance_match": "normalized_problem_plus_exact_gold_solution_hash",
    }:
        raise ValueError("C9 selection drift")
    quality = cast(Mapping[str, object], config["quality"])
    if any(
        quality.get(key) is not False
        for key in ("execute_source_code", "generate_tests", "run_piston", "threshold_relaxation_allowed")
    ) or any(
        quality.get(key) is not True
        for key in (
            "require_reference_solution_execution_validation",
            "exclude_unresolved_quality_gate",
            "final_augmented_context_recheck_required",
            "unresolved_upstream_license_blocks_formal_admission",
        )
    ):
        raise ValueError("C9 quality drift")
    source = cast(Mapping[str, object], config["source"])
    if dict(source) != {
        "source_name": "open-r1-vcp-python-decontaminated",
        "dataset_id": "open-r1/verifiable-coding-problems-python_decontaminated",
        "revision": "0d251c23dcff7f7e525e7a4e184be5232bf63db6",
        "config_name": "default",
        "split": "train",
        "declared_license": "NOT_DECLARED",
        "license_status": "unresolved_upstream",
        "provenance_note": (
            "non-reward-tested Python decontaminated projection; per-row upstream source/in_source_id/problem_url "
            "must be preserved and reviewed before formal admission"
        ),
        "shard_glob": "data/train-*-of-00006.parquet",
        "expected_shard_count": 6,
        "expected_total_rows": 27839,
        "download_manifest": "/home/dzy/wp9c-openr1-decontaminated-full-download-C9/manifest.json",
    }:
        raise ValueError("C9 source identity drift")


def _validate_baselines(config: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    baseline = cast(Mapping[str, object], config["baseline"])
    c8_path = Path(cast(str, baseline["c8_report"]))
    if _sha(c8_path) != baseline["c8_report_sha256"]:
        raise ValueError("C8 report SHA mismatch")
    c8 = loads_strict(c8_path.read_text(encoding="utf-8"))
    if not isinstance(c8, dict) or c8.get("schema_version") != "wp9c-deepcoder-function-supply-audit-v1":
        raise ValueError("C8 report identity mismatch")
    supply = c8.get("supply_projection")
    if (
        c8.get("formal_eligible") is not False
        or not isinstance(supply, dict)
        or supply.get("current_ready_context_eligible_before_piston") != baseline["ready_context_eligible_count"]
        or supply.get("under8_preaugmentation_planning_union") != baseline["c8_under8_preaugmentation_planning_union"]
        or supply.get("zero_attrition_planning_union") != baseline["c8_zero_attrition_planning_union"]
    ):
        raise ValueError("C8 baseline supply mismatch")
    sample_path = Path(cast(str, baseline["historical_openr1_sample_report"]))
    if _sha(sample_path) != baseline["historical_openr1_sample_report_sha256"]:
        raise ValueError("historical Open-R1 sample report SHA mismatch")
    sample = loads_strict(sample_path.read_text(encoding="utf-8"))
    if (
        not isinstance(sample, dict)
        or sample.get("schema_version") != "wp9c-openr1-decontaminated-sample-audit-v1"
        or sample.get("formal_eligible") is not False
    ):
        raise ValueError("historical Open-R1 sample identity mismatch")
    return cast(dict[str, object], c8), cast(dict[str, object], sample)


def _validate_manifest(config: Mapping[str, object]) -> tuple[Path, list[dict[str, object]], str]:
    source = cast(Mapping[str, object], config["source"])
    path = Path(cast(str, source["download_manifest"]))
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    sidecar = path.with_name("manifest.sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="ascii").strip() != digest:
        raise ValueError("C9 download manifest digest mismatch")
    manifest = loads_strict(payload.decode("utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "wp9c-openr1-decontaminated-full-download-v1"
        or manifest.get("dataset_id") != source["dataset_id"]
        or manifest.get("revision") != source["revision"]
        or manifest.get("shard_count") != 6
        or manifest.get("total_rows") != 27839
    ):
        raise ValueError("C9 download manifest identity mismatch")
    snapshot = Path(cast(str, manifest["snapshot_path"]))
    if snapshot.name != source["revision"]:
        raise ValueError("C9 snapshot identity mismatch")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or len(shards) != 6:
        raise ValueError("C9 manifest must contain six shards")
    verified: list[dict[str, object]] = []
    total = 0
    for index, row in enumerate(shards):
        if not isinstance(row, dict) or set(row) != {"shard_index", "path", "sha256", "size", "rows"}:
            raise ValueError("C9 manifest shard schema mismatch")
        if row["shard_index"] != index:
            raise ValueError("C9 manifest shard ordering mismatch")
        file_path = snapshot / cast(str, row["path"])
        if not file_path.is_file() or file_path.stat().st_size != row["size"] or _sha(file_path) != row["sha256"]:
            raise ValueError(f"C9 shard content mismatch: {file_path}")
        total += cast(int, row["rows"])
        verified.append(cast(dict[str, object], row))
    if total != 27839:
        raise ValueError("C9 manifest row total mismatch")
    return snapshot, verified, digest


def _source_url(metadata: object) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("problem_url")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _source_url_hash(metadata: object) -> str | None:
    value = _source_url(metadata)
    return hashlib.sha256(value.encode()).hexdigest() if value is not None else None


def _scan_source(
    snapshot: Path,
    shards: Sequence[Mapping[str, object]],
    sample_module: ModuleType,
    *,
    deepcoder_match_index: Mapping[tuple[str, str], set[str]],
) -> tuple[list[RefreshCandidate], dict[str, str], list[dict[str, object]], dict[str, object]]:
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    expected_fields = sample_module.EXPECTED_FIELDS
    test_fields = sample_module.TEST_FIELDS
    parse_tests = sample_module._parse_function_tests
    candidates: list[RefreshCandidate] = []
    solutions: dict[str, str] = {}
    provenance_rows: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    function_source_counts: Counter[str] = Counter()
    candidate_source_counts: Counter[str] = Counter()
    test_hist: Counter[int] = Counter()
    matched_deepcoder_ids: set[str] = set()
    ambiguous_match_keys = 0
    global_row = 0

    for shard in shards:
        shard_index = cast(int, shard["shard_index"])
        path = snapshot / cast(str, shard["path"])
        parquet = pq.ParquetFile(path)
        columns = parquet.schema_arrow.names
        if set(columns) != expected_fields:
            raise ValueError(f"C9 schema drift in shard {shard_index}")
        local_row = 0
        for batch in parquet.iter_batches(batch_size=128, columns=columns):
            for row in batch.to_pylist():
                current_local = local_row
                local_row += 1
                current_global = global_row
                global_row += 1
                counts["total_rows"] += 1
                if not isinstance(row, Mapping) or set(row) != expected_fields:
                    raise ValueError(f"C9 row schema drift: shard {shard_index}:{current_local}")
                source_name = row["source"] if isinstance(row["source"], str) else "<invalid>"
                source_counts[source_name] += 1
                problem = row["problem"]
                gold = row["gold_standard_solution"]
                if isinstance(problem, str) and problem.strip() and isinstance(gold, str) and gold.strip():
                    key = (normalize_text(problem), stable_json_hash([gold]))
                    matched = deepcoder_match_index.get(key, set())
                    if len(matched) > 1:
                        ambiguous_match_keys += 1
                    elif len(matched) == 1:
                        candidate_id = next(iter(matched))
                        if candidate_id not in matched_deepcoder_ids:
                            matched_deepcoder_ids.add(candidate_id)
                            provenance_rows.append(
                                {
                                    "deepcoder_candidate_id": candidate_id,
                                    "match_protocol": "normalized_problem_plus_exact_gold_solution_hash",
                                    "openr1_shard_index": shard_index,
                                    "openr1_local_row": current_local,
                                    "openr1_global_row": current_global,
                                    "upstream_source": source_name,
                                    "in_source_id": row["in_source_id"],
                                    "problem_id": row["problem_id"],
                                    "problem_url": _source_url(row["metadata"]),
                                    "problem_url_hash": _source_url_hash(row["metadata"]),
                                }
                            )

                verification = row["verification_info"]
                if not isinstance(verification, Mapping) or set(verification) != {"language", "test_cases"}:
                    counts["invalid_verification_info"] += 1
                    continue
                if verification["language"] != "python":
                    counts["non_python_rows"] += 1
                    continue
                tests_raw = verification["test_cases"]
                if not isinstance(tests_raw, list) or not tests_raw:
                    counts["missing_tests"] += 1
                    continue
                if any(not isinstance(item, Mapping) or set(item) != test_fields for item in tests_raw):
                    counts["invalid_test_schema"] += 1
                    continue
                tests_mapping = cast(list[Mapping[str, object]], tests_raw)
                types = {test["type"] for test in tests_mapping}
                if types != {"function_call"}:
                    counts["mixed_function_call_rows" if "function_call" in types else "non_function_call_rows"] += 1
                    continue
                counts["pure_function_call_rows"] += 1
                function_source_counts[source_name] += 1
                record_id = f"openr1-decontaminated/shard{shard_index}/{current_local}"
                strict_parsed = parse_tests(tests_mapping, parser="strict_json", record_id=record_id)
                literal_parsed = parse_tests(tests_mapping, parser="safe_literal", record_id=record_id)
                parsed = strict_parsed or literal_parsed
                if parsed is None:
                    counts["unparseable_function_rows"] += 1
                    continue
                function_name, tests = parsed
                if not tests:
                    counts["zero_test_rows"] += 1
                    continue
                try:
                    test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
                except ValueError:
                    counts["duplicate_normalized_test_rows"] += 1
                    continue
                if (
                    not isinstance(problem, str)
                    or not problem.strip()
                    or not isinstance(gold, str)
                    or not gold.strip()
                ):
                    counts["missing_problem_or_solution"] += 1
                    continue
                arities = {len(cast(Sequence[object], test.input)) for test in tests}
                signature = _function_signature_from_row(
                    {"problem": problem, "solutions": [gold]}, function_name=function_name, arities=arities
                )
                if signature is None:
                    counts["non_direct_signature_rows"] += 1
                    continue
                candidate_id = stable_json_hash(
                    {
                        "protocol": "wp9c-openr1-decontaminated-candidate-v1",
                        "revision": snapshot.name,
                        "shard_index": shard_index,
                        "row_index": current_local,
                        "problem_id": row["problem_id"],
                    }
                )
                difficulty: Difficulty = "unknown"
                metadata = row["metadata"]
                if isinstance(metadata, Mapping):
                    raw_difficulty = metadata.get("difficulty")
                    if isinstance(raw_difficulty, str) and raw_difficulty.lower() in {"easy", "medium", "hard"}:
                        difficulty = cast(Difficulty, raw_difficulty.lower())
                candidate = RefreshCandidate(
                    candidate_id=candidate_id,
                    source_name="open-r1-vcp-python-decontaminated",
                    source_record_id=f"data/train-shard-{shard_index}:{current_local}",
                    prompt=problem.strip(),
                    function_name=function_name,
                    function_signature=signature,
                    tests=tuple(tests),
                    source_url_hash=_source_url_hash(metadata),
                    raw_reference_solution_hash=stable_json_hash([gold]),
                    difficulty=difficulty,
                    category=("function_call", f"openr1_upstream_source:{source_name}"),
                    raw_record_sha256=stable_json_hash(
                        {
                            "source": row["source"],
                            "in_source_id": row["in_source_id"],
                            "problem_id": row["problem_id"],
                            "problem": problem,
                            "gold_standard_solution": gold,
                            "metadata": row["metadata"],
                            "verification_info": row["verification_info"],
                        }
                    ),
                    test_fingerprint=test_fingerprint,
                    test_validation_guard=None,
                )
                candidates.append(candidate)
                solutions[candidate_id] = gold
                candidate_source_counts[source_name] += 1
                test_hist[len(tests)] += 1
                counts["structural_direct_signature_rows"] += 1

    if global_row != 27839:
        raise ValueError(f"C9 expected 27839 scanned rows, got {global_row}")
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("C9 candidate IDs are not unique")
    return (
        candidates,
        solutions,
        provenance_rows,
        {
            "scanned_rows": global_row,
            "reason_counts": dict(sorted(counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "function_source_counts": dict(sorted(function_source_counts.items())),
            "candidate_source_counts": dict(sorted(candidate_source_counts.items())),
            "candidate_test_count_histogram": {str(k): v for k, v in sorted(test_hist.items())},
            "deepcoder_provenance_matches": len(matched_deepcoder_ids),
            "ambiguous_deepcoder_match_keys": ambiguous_match_keys,
        },
    )


def _c8_union(
    config: Mapping[str, object],
    c8_report: Mapping[str, object],
    c8_module: ModuleType,
    c6_full: ModuleType,
    aggregate: ModuleType,
) -> tuple[list[RefreshCandidate], list[dict[str, object]]]:
    artifacts = c8_report.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise ValueError("C8 artifact map missing")
    deepcoder_path = C8_DIR / "deepcoder_under8_candidates.jsonl"
    c7_decisions_path = C8_DIR / "c7_under8_after_deepcoder_decisions.jsonl"
    if artifacts.get("deepcoder_under8_candidates") != _sha(deepcoder_path):
        raise ValueError("C8 DeepCoder-under8 artifact mismatch")
    if artifacts.get("c7_under8_after_deepcoder_decisions") != _sha(c7_decisions_path):
        raise ValueError("C8 C7-decision artifact mismatch")
    deepcoder_rows = _jsonl(deepcoder_path)
    deepcoder = [c8_module._candidate_from_c7_row(row) for row in deepcoder_rows]
    correction_report = loads_strict(
        Path(cast(str, cast(Mapping[str, object], config["baseline"])["correction_report"])).read_text()
    )
    if not isinstance(correction_report, dict):
        raise ValueError("C9 correction report invalid")
    c7_report = loads_strict(
        Path(cast(str, cast(Mapping[str, object], config["baseline"])["c7_taco_under8_report"])).read_text()
    )
    if not isinstance(c7_report, dict):
        raise ValueError("C9 C7 report invalid")
    c7_union = c8_module._load_c7_under8_union(
        config=config,
        c7_report=c7_report,
        c6_full=c6_full,
        aggregate_module=aggregate,
        correction_report=correction_report,
    )
    decisions = _jsonl(c7_decisions_path)
    retained_ids = {cast(str, row["candidate_id"]) for row in decisions if row.get("retained") is True}
    retained_c7 = [candidate for candidate in c7_union if candidate.candidate_id in retained_ids]
    union = [*deepcoder, *retained_c7]
    baseline = cast(Mapping[str, object], config["baseline"])
    if len(union) != baseline["c8_under8_preaugmentation_planning_union"]:
        raise ValueError("C9 reconstructed C8 under8 union count mismatch")
    return union, deepcoder_rows


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    c8_report, sample_report = _validate_baselines(config)
    snapshot, shards, manifest_sha = _validate_manifest(config)
    targets = cast(Mapping[str, object], config["targets"])
    baseline = cast(Mapping[str, object], config["baseline"])
    source = cast(Mapping[str, object], config["source"])

    c6_full = _load_module(C6_FULL_SCRIPT, "wp9c_c6_full_for_c9")
    correction = _load_module(C6_CORRECTION_SCRIPT, "wp9c_c6_correction_for_c9")
    c8_module = _load_module(C8_SCRIPT, "wp9c_c8_for_c9")
    sample_module = _load_module(SAMPLE_SCRIPT, "wp9c_openr1_sample_for_c9")
    aggregate = _load_module(c6_full.AGGREGATE_SCRIPT, "wp9c_aggregate_for_c9")
    sft_refs, validation_refs, project_refs, humaneval_refs, ready_refs, tokenizer, _ = (
        c6_full._current_ready_references(config, aggregate)
    )
    c8_union, deepcoder_rows = _c8_union(config, c8_report, c8_module, c6_full, aggregate)
    c8_refs = [aggregate._candidate_reference(candidate, prefix="c8-under8") for candidate in c8_union]

    match_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    primeintellect_ids: set[str] = set()
    for row in deepcoder_rows:
        if row.get("source_name") != "deepcoder-primeintellect":
            continue
        candidate_id = row.get("candidate_id")
        prompt = row.get("prompt")
        solutions = row.get("accepted_source_solutions")
        if not isinstance(candidate_id, str) or not isinstance(prompt, str) or not isinstance(solutions, list):
            raise ValueError("C9 DeepCoder provenance input schema mismatch")
        primeintellect_ids.add(candidate_id)
        for solution in solutions:
            if isinstance(solution, str) and solution.strip():
                match_index[(normalize_text(prompt), stable_json_hash([solution]))].add(candidate_id)
    if len(primeintellect_ids) != 541:
        raise ValueError(f"C9 expected 541 DeepCoder-primeintellect rows, got {len(primeintellect_ids)}")

    candidates, solutions_by_id, provenance_rows, scan_summary = _scan_source(
        snapshot, shards, sample_module, deepcoder_match_index=match_index
    )
    provenance_matched_ids = {cast(str, row["deepcoder_candidate_id"]) for row in provenance_rows}
    provenance_unmatched_ids = sorted(primeintellect_ids - provenance_matched_ids)

    policy = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)
    decisions = classify_refresh_candidates(
        [replace(candidate, tests=()) for candidate in candidates],
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_refs,
        external_eval_references=[*humaneval_refs, *ready_refs, *c8_refs],
        policy=policy,
    )
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    retained = [by_id[item.candidate_id] for item in decisions if item.retained]
    ready_input = [candidate for candidate in retained if len(candidate.tests) >= 8]
    under8_input = [candidate for candidate in retained if 1 <= len(candidate.tests) <= 7]
    if len(ready_input) + len(under8_input) != len(retained):
        raise ValueError("C9 retained test-count partition mismatch")

    ready_context, ready_context_rows, ready_context_summary = c6_full._formal_context_filter(
        ready_input, tokenizer=tokenizer, cap=2048
    )
    origins = {candidate.candidate_id: "openr1_decontaminated_new" for candidate in under8_input}
    under8_context, under8_context_rows, under8_context_summary = correction._under8_preaugmentation_context_filter(
        under8_input, tokenizer=tokenizer, cap=2048, origin_by_id=origins
    )
    ready_context_by_id = {cast(str, row["candidate_id"]): row for row in ready_context_rows}
    under8_context_by_id = {cast(str, row["candidate_id"]): row for row in under8_context_rows}

    ready_stage = []
    for candidate in ready_context:
        row = ready_context_by_id[candidate.candidate_id]
        ready_stage.append(
            {
                "candidate_id": candidate.candidate_id,
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "dataset_id": source["dataset_id"],
                "dataset_revision": source["revision"],
                "license_status": source["license_status"],
                "prompt": candidate.prompt,
                "function_name": candidate.function_name,
                "function_signature": candidate.function_signature,
                "tests": [test_case_to_mapping(test) for test in candidate.tests],
                "source_test_count": len(candidate.tests),
                "gold_standard_solution": solutions_by_id[candidate.candidate_id],
                "source_url_hash": candidate.source_url_hash,
                "raw_reference_solution_hash": candidate.raw_reference_solution_hash,
                "category": list(candidate.category),
                "test_fingerprint": candidate.test_fingerprint,
                "formal_prompt_sha256": row["prompt_sha256"],
                "formal_prompt_tokens": row["prompt_tokens"],
                "formal_ready": False,
            }
        )
    under8_stage = []
    for candidate in under8_context:
        row = under8_context_by_id[candidate.candidate_id]
        under8_stage.append(
            {
                "candidate_id": candidate.candidate_id,
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "dataset_id": source["dataset_id"],
                "dataset_revision": source["revision"],
                "license_status": source["license_status"],
                "prompt": candidate.prompt,
                "function_name": candidate.function_name,
                "function_signature": candidate.function_signature,
                "tests": [test_case_to_mapping(test) for test in candidate.tests],
                "source_test_count": len(candidate.tests),
                "gold_standard_solution": solutions_by_id[candidate.candidate_id],
                "source_url_hash": candidate.source_url_hash,
                "raw_reference_solution_hash": candidate.raw_reference_solution_hash,
                "category": list(candidate.category),
                "test_fingerprint": candidate.test_fingerprint,
                "preaugmentation_prompt_sha256": row["prompt_sha256"],
                "preaugmentation_prompt_tokens": row["prompt_tokens"],
                "requires_post_augmentation_context_recheck": True,
                "formal_ready": False,
            }
        )

    added_ready = len(ready_context)
    added_under8 = len(under8_context)
    ready_union = cast(int, baseline["ready_context_eligible_count"]) + added_ready
    under8_union = cast(int, baseline["c8_under8_preaugmentation_planning_union"]) + added_under8
    planning_union = ready_union + under8_union
    under8_needed = max(0, cast(int, targets["external_new_exact"]) - ready_union)
    success_fraction = under8_needed / under8_union if under8_union else None
    retained_sources = Counter(
        candidate.category[-1].removeprefix("openr1_upstream_source:") for candidate in retained
    )
    added_ready_sources = Counter(
        candidate.category[-1].removeprefix("openr1_upstream_source:") for candidate in ready_context
    )
    added_under8_sources = Counter(
        candidate.category[-1].removeprefix("openr1_upstream_source:") for candidate in under8_context
    )

    report: dict[str, object] = {
        "schema_version": "wp9c-openr1-decontaminated-full-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "protocol_amendment": config["protocol_amendment"],
        "formal_blockers": [
            "dataset_license_not_declared_and_per_source_terms_require_review",
            "deepcoder_provenance_unmatched_rows_require_resolution_if_nonzero",
            "reference_solution_execution_validation_not_run",
            "under8_test_augmentation_not_run",
            "final_augmented_context_recheck_not_run",
            "project_piston_reference_solution_validation_not_run",
        ],
        "config_path": str(config_path),
        "config_sha256": _sha(config_path),
        "download_manifest_sha256": manifest_sha,
        "dependency_sha256": {
            "audit_script": _sha(Path(__file__)),
            "c6_full_taco_script": _sha(C6_FULL_SCRIPT),
            "c6_context_correction_script": _sha(C6_CORRECTION_SCRIPT),
            "c8_script": _sha(C8_SCRIPT),
            "historical_sample_script": _sha(SAMPLE_SCRIPT),
        },
        "baseline": {
            "c8_report_sha256": baseline["c8_report_sha256"],
            "historical_openr1_sample_report_sha256": baseline["historical_openr1_sample_report_sha256"],
            "historical_sample_aggregate_counts": sample_report["aggregate_counts"],
            "ready_context_eligible_before_piston": baseline["ready_context_eligible_count"],
            "c8_under8_preaugmentation_planning_union": baseline["c8_under8_preaugmentation_planning_union"],
            "c8_zero_attrition_planning_union": baseline["c8_zero_attrition_planning_union"],
        },
        "source_identity": config["source"],
        "verified_shards": shards,
        "scan_summary": scan_summary,
        "deepcoder_provenance_recovery": {
            "target_deepcoder_primeintellect_rows": 541,
            "uniquely_matched_rows": len(provenance_matched_ids),
            "unmatched_rows": len(provenance_unmatched_ids),
            "unmatched_candidate_ids_sha256": stable_json_hash(provenance_unmatched_ids),
            "match_protocol": "normalized_problem_plus_exact_gold_solution_hash",
        },
        "raw_function_dedup": {
            "input_structural_direct_signature": len(candidates),
            "retained_after_current_ready_and_c8_union": len(retained),
            "retained_upstream_source_counts": dict(sorted(retained_sources.items())),
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in decisions).items())
            ),
        },
        "new_ready_context": ready_context_summary,
        "incremental_openr1_ready_context_eligible": added_ready,
        "incremental_openr1_ready_upstream_source_counts": dict(sorted(added_ready_sources.items())),
        "new_under8_preaugmentation_context": under8_context_summary,
        "incremental_openr1_under8_preaugmentation_planning": added_under8,
        "incremental_openr1_under8_upstream_source_counts": dict(sorted(added_under8_sources.items())),
        "supply_projection": {
            "current_ready_context_eligible_before_piston": baseline["ready_context_eligible_count"],
            "incremental_openr1_ready_context_eligible": added_ready,
            "ready_context_eligible_union_before_piston": ready_union,
            "c8_under8_preaugmentation_planning_union": baseline["c8_under8_preaugmentation_planning_union"],
            "incremental_openr1_under8_preaugmentation_planning": added_under8,
            "under8_preaugmentation_planning_union": under8_union,
            "zero_attrition_planning_union": planning_union,
            "incremental_planning_union_vs_c8": planning_union
            - cast(int, baseline["c8_zero_attrition_planning_union"]),
            "under8_planning_successes_needed_for_exact_2275": under8_needed,
            "under8_planning_success_fraction_needed": success_fraction,
            "pre_piston_buffer_min_met_under_zero_attrition_planning": planning_union
            >= cast(int, targets["pre_piston_external_new_buffer_min"]),
            "pre_piston_buffer_target_met_under_zero_attrition_planning": planning_union
            >= cast(int, targets["pre_piston_external_new_buffer_target"]),
        },
        "notes": [
            "No source solution or testcase payload is executed, no tests are generated, and Piston is not run.",
            (
                "The source is the non-reward-tested decontaminated Python projection; no historical reward outcome "
                "is used for selection."
            ),
            (
                "Raw Open-R1 candidates have lower priority than the frozen C8 union and only count when dedup says "
                "they are genuinely new."
            ),
            (
                "DeepCoder provenance recovery requires normalized-problem equality plus an exact single-solution "
                "hash match."
            ),
            "All under8 rows remain planning-only until augmentation and final Exact-B context recheck.",
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        report["artifact_sha256"] = {
            "deepcoder_provenance_recovery": _write_jsonl(
                temporary / "deepcoder_provenance_recovery.jsonl", provenance_rows
            ),
            "raw_candidates": _write_jsonl(
                temporary / "raw_candidates.jsonl",
                [
                    {
                        "candidate_id": candidate.candidate_id,
                        "source_record_id": candidate.source_record_id,
                        "prompt": candidate.prompt,
                        "function_name": candidate.function_name,
                        "function_signature": candidate.function_signature,
                        "tests": [test_case_to_mapping(test) for test in candidate.tests],
                        "source_url_hash": candidate.source_url_hash,
                        "raw_reference_solution_hash": candidate.raw_reference_solution_hash,
                        "category": list(candidate.category),
                        "raw_record_sha256": candidate.raw_record_sha256,
                        "test_fingerprint": candidate.test_fingerprint,
                    }
                    for candidate in candidates
                ],
            ),
            "dedup_decisions": _write_jsonl(temporary / "dedup_decisions.jsonl", [asdict(item) for item in decisions]),
            "ready_context": _write_jsonl(temporary / "ready_context.jsonl", ready_context_rows),
            "under8_context": _write_jsonl(temporary / "under8_context.jsonl", under8_context_rows),
            "incremental_ready_candidates": _write_jsonl(
                temporary / "incremental_ready_candidates.jsonl", ready_stage
            ),
            "incremental_under8_candidates": _write_jsonl(
                temporary / "incremental_under8_candidates.jsonl", under8_stage
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
