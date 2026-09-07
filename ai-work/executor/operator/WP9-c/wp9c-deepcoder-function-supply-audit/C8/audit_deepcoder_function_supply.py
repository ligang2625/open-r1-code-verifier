#!/usr/bin/env python3
"""Static DeepCoder function-call supply audit for the WP9-c 2500-pool amendment."""

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
from code_verifier.data.deduplicate import DuplicateDataError, canonical_json, stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.refresh_dedup import RefreshDedupPolicy, classify_refresh_candidates
from code_verifier.data.refresh_sources import (
    Difficulty,
    RefreshCandidate,
    RefreshSourceError,
    RefreshSourceSpec,
    _deepcoder_raw_record_hash,
    _function_signature_from_row,
    _primeintellect_function_call_tests,
    _raw_reference_solution_hash,
    _resolve_snapshot,
    _strict_tests_json,
    _taco_function_call_tests,
    _validate_license,
    refresh_test_set_fingerprint,
)
from code_verifier.data.schema import test_case_from_mapping, test_case_to_mapping

ROOT = Path(__file__).resolve().parents[6]
C6_FULL_SCRIPT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/audit_full_taco_supply.py"
C6_CORRECTION_SCRIPT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/audit_context_correction.py"
)
C7_REPORT_DIR = Path("/home/dzy/wp9c-taco-under8-supply-audit-C7")
REFRESH_SOURCES_MODULE = ROOT / "src/code_verifier/data/refresh_sources.py"
JSON_STRICT_MODULE = ROOT / "src/code_verifier/data/json_strict.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load C8 dependency: {path}")
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
        config.get("version") != "wp9c-deepcoder-function-supply-audit-v1"
        or config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
        or config.get("seed") != 42
    ):
        raise ValueError("C8 protocol/seed drift")
    targets = cast(Mapping[str, object], config["targets"])
    if dict(targets) != {
        "active_pool": 2500,
        "sft_reuse_exact": 225,
        "external_new_exact": 2275,
        "pre_piston_external_new_buffer_min": 2600,
        "pre_piston_external_new_buffer_target": 2800,
    }:
        raise ValueError("C8 target drift")
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
        "priority": "current_ready_then_deepcoder_ready_then_deepcoder_under8_then_c7_under8_union",
    }:
        raise ValueError("C8 selection policy drift")
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
        )
    ):
        raise ValueError("C8 quality policy drift")


def _validate_baseline(config: Mapping[str, object]) -> dict[str, object]:
    baseline = cast(Mapping[str, object], config["baseline"])
    c7_path = Path(cast(str, baseline["c7_taco_under8_report"]))
    if _sha(c7_path) != baseline["c7_taco_under8_report_sha256"]:
        raise ValueError("C7 report SHA256 mismatch")
    report = loads_strict(c7_path.read_text(encoding="utf-8"))
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != "wp9c-taco-under8-supply-audit-v1"
        or report.get("formal_eligible") is not False
    ):
        raise ValueError("C7 report identity/status mismatch")
    supply = report.get("supply_projection")
    if (
        not isinstance(supply, dict)
        or supply.get("current_ready_context_eligible_before_piston") != baseline["ready_context_eligible_count"]
        or supply.get("under8_preaugmentation_planning_union") != baseline["c7_under8_preaugmentation_planning_union"]
        or supply.get("zero_attrition_planning_union") != baseline["c7_zero_attrition_planning_union"]
    ):
        raise ValueError("C7 supply baseline mismatch")
    return cast(dict[str, object], report)


def _validate_snapshot(config: Mapping[str, object]) -> tuple[Path, list[dict[str, object]]]:
    source = cast(Mapping[str, object], config["deepcoder"])
    expected_source_keys = {
        "dataset_id",
        "revision",
        "declared_license",
        "split",
        "provenance_note",
        "source_priority",
        "shards",
    }
    if set(source) != expected_source_keys:
        raise ValueError("C8 DeepCoder source config keys drift")
    if (
        source["dataset_id"] != "agentica-org/DeepCoder-Preview-Dataset"
        or source["revision"] != "177913a7bd43791646ef6a43645caa3c871ab3db"
        or source["declared_license"] != "MIT"
        or source["split"] != "train"
        or source["provenance_note"]
        != (
            "DeepCoder dataset-card MIT; primeintellect/taco projections may contain upstream-derived material and "
            "require provenance review before formal admission"
        )
    ):
        raise ValueError("C8 DeepCoder source identity drift")
    priorities = source["source_priority"]
    if priorities != [
        {
            "source_name": "deepcoder-primeintellect",
            "config_name": "primeintellect",
            "adapter": "deepcoder",
            "expected_shard_count": 5,
            "expected_row_count": 16252,
        },
        {
            "source_name": "deepcoder-taco",
            "config_name": "taco",
            "adapter": "deepcoder",
            "expected_shard_count": 4,
            "expected_row_count": 7436,
        },
    ]:
        raise ValueError("C8 DeepCoder source priority drift")

    snapshot = _resolve_snapshot(
        cast(str, source["dataset_id"]),
        cast(str, source["revision"]),
        cache_dir=None,
    )
    _validate_license(snapshot, cast(str, source["declared_license"]))
    shards = source["shards"]
    if not isinstance(shards, list) or len(shards) != 9:
        raise ValueError("C8 frozen shard inventory must contain exactly 9 rows")
    verified: list[dict[str, object]] = []
    expected_paths: dict[str, list[str]] = {"primeintellect": [], "taco": []}
    for item in shards:
        if not isinstance(item, dict) or set(item) != {"config_name", "path", "blob_sha256", "size"}:
            raise ValueError("invalid C8 shard manifest row")
        config_name = item["config_name"]
        relative = item["path"]
        blob = item["blob_sha256"]
        size = item["size"]
        if config_name not in expected_paths or not isinstance(relative, str):
            raise ValueError("invalid C8 shard config/path")
        if not isinstance(blob, str) or len(blob) != 64 or any(c not in "0123456789abcdef" for c in blob):
            raise ValueError("invalid C8 frozen blob SHA256")
        if not isinstance(size, int) or size <= 0:
            raise ValueError("invalid C8 frozen shard size")
        path = snapshot / relative
        if not path.is_file() or path.stat().st_size != size or path.resolve().name != blob:
            raise ValueError(f"C8 frozen shard identity mismatch: {path}")
        if _sha(path) != blob:
            raise ValueError(f"C8 frozen shard content SHA256 mismatch: {path}")
        expected_paths[cast(str, config_name)].append(relative)
        verified.append(cast(dict[str, object], item))
    for config_name, expected_count in (("primeintellect", 5), ("taco", 4)):
        actual = [str(path.relative_to(snapshot)) for path in sorted((snapshot / config_name).glob("train-*.parquet"))]
        if len(actual) != expected_count or actual != sorted(expected_paths[config_name]):
            raise ValueError(f"C8 local shard inventory drift: {config_name}")
    return snapshot, verified


def _scan_config(
    *,
    snapshot: Path,
    config_name: str,
    source_name: str,
    dataset_id: str,
    revision: str,
) -> tuple[list[RefreshCandidate], dict[str, list[str]], dict[str, object]]:
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    files = sorted((snapshot / config_name).glob("train-*.parquet"))
    candidates: list[RefreshCandidate] = []
    solutions_by_id: dict[str, list[str]] = {}
    counts: Counter[str] = Counter()
    projection = hashlib.sha256()
    test_hist: Counter[int] = Counter()
    row_index = 0
    for path in files:
        parquet = pq.ParquetFile(path)
        columns = parquet.schema_arrow.names
        if set(columns) != {"problem", "solutions", "tests"}:
            raise ValueError(f"DeepCoder schema drift: {config_name}/{path.name}")
        for batch in parquet.iter_batches(batch_size=128, columns=columns):
            for row in batch.to_pylist():
                current = row_index
                row_index += 1
                counts["total_rows"] += 1
                if not isinstance(row, Mapping) or set(row) != {"problem", "solutions", "tests"}:
                    raise ValueError(f"DeepCoder row schema drift: {config_name}/{current}")
                raw_hash = _deepcoder_raw_record_hash(row)
                projection.update(raw_hash.encode("ascii"))
                projection.update(b"\n")
                prompt = row["problem"]
                if not isinstance(prompt, str) or not prompt.strip():
                    counts["invalid_problem_rows"] += 1
                    continue
                record_id = f"{config_name}/train/{current}"
                try:
                    solution_hash = _raw_reference_solution_hash(row["solutions"], record_id=record_id)
                except (RefreshSourceError, ValueError):
                    counts["invalid_solution_rows"] += 1
                    continue
                if solution_hash is None:
                    counts["missing_solution_rows"] += 1
                    continue
                try:
                    parsed_tests = _strict_tests_json(row["tests"], record_id=record_id)
                except (RefreshSourceError, StrictJsonError, ValueError):
                    counts["invalid_tests_json_rows"] += 1
                    continue
                try:
                    if config_name == "primeintellect":
                        parsed = _primeintellect_function_call_tests(parsed_tests, record_id=record_id)
                    elif config_name == "taco":
                        parsed = _taco_function_call_tests(parsed_tests, record_id=record_id)
                    else:
                        raise ValueError(f"unsupported C8 config {config_name}")
                except ValueError:
                    counts["invalid_function_tests"] += 1
                    continue
                if parsed is None:
                    counts["non_function_rows"] += 1
                    continue
                function_name, tests = parsed
                counts["function_call_rows"] += 1
                if not tests:
                    counts["zero_test_rows"] += 1
                    continue
                try:
                    test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
                except (DuplicateDataError, ValueError):
                    counts["duplicate_normalized_test_rows"] += 1
                    continue
                arities = {len(cast(Sequence[object], test.input)) for test in tests}
                signature = _function_signature_from_row(row, function_name=function_name, arities=arities)
                if signature is None:
                    counts["non_direct_signature_rows"] += 1
                    continue
                candidate_id = stable_json_hash(
                    {
                        "protocol": "wp9a-refresh-candidate-v1",
                        "source_name": source_name,
                        "dataset_id": dataset_id,
                        "revision": revision,
                        "config_name": config_name,
                        "split": "train",
                        "row_index": current,
                        "raw_record_sha256": raw_hash,
                    }
                )
                candidate = RefreshCandidate(
                    candidate_id=candidate_id,
                    source_name=source_name,
                    source_record_id=record_id,
                    prompt=prompt.strip(),
                    function_name=function_name,
                    function_signature=signature,
                    tests=tuple(tests),
                    source_url_hash=None,
                    raw_reference_solution_hash=solution_hash,
                    difficulty="unknown",
                    category=("function_call", f"deepcoder_config:{config_name}"),
                    raw_record_sha256=raw_hash,
                    test_fingerprint=test_fingerprint,
                    test_validation_guard=None,
                )
                candidates.append(candidate)
                solutions = row["solutions"]
                if not isinstance(solutions, list) or any(not isinstance(item, str) for item in solutions):
                    raise ValueError(f"DeepCoder solution schema drift after validation: {record_id}")
                solutions_by_id[candidate_id] = [item for item in solutions if item.strip()]
                test_hist[len(tests)] += 1
                counts["structural_direct_signature_rows"] += 1
    return (
        candidates,
        solutions_by_id,
        {
            "source_name": source_name,
            "config_name": config_name,
            "scanned_rows": row_index,
            "structural_direct_signature_rows": len(candidates),
            "projection_fingerprint_sha256": projection.hexdigest(),
            "test_count_histogram": {str(k): v for k, v in sorted(test_hist.items())},
            "reason_counts": dict(sorted(counts.items())),
        },
    )


def _candidate_from_c7_row(row: Mapping[str, object]) -> RefreshCandidate:
    tests_value = row.get("tests")
    if not isinstance(tests_value, list):
        raise ValueError("C7 staged candidate tests are invalid")
    tests = tuple(test_case_from_mapping(item, field_path=f"tests[{index}]") for index, item in enumerate(tests_value))
    category_value = row.get("category")
    if not isinstance(category_value, list) or any(not isinstance(item, str) for item in category_value):
        raise ValueError("C7 staged candidate category is invalid")
    difficulty = row.get("difficulty")
    if difficulty not in {"easy", "medium", "hard", "unknown"}:
        raise ValueError("C7 staged candidate difficulty is invalid")
    required_strings = (
        "candidate_id",
        "source_name",
        "source_record_id",
        "prompt",
        "function_name",
        "function_signature",
        "raw_record_sha256",
    )
    if any(not isinstance(row.get(key), str) for key in required_strings):
        raise ValueError("C7 staged candidate string identity is invalid")
    return RefreshCandidate(
        candidate_id=cast(str, row["candidate_id"]),
        source_name=cast(str, row["source_name"]),
        source_record_id=cast(str, row["source_record_id"]),
        prompt=cast(str, row["prompt"]),
        function_name=cast(str, row["function_name"]),
        function_signature=cast(str, row["function_signature"]),
        tests=tests,
        source_url_hash=cast(str | None, row.get("source_url_hash")),
        raw_reference_solution_hash=cast(str | None, row.get("raw_reference_solution_hash")),
        difficulty=cast(Difficulty, difficulty),
        category=tuple(cast(list[str], category_value)),
        raw_record_sha256=cast(str, row["raw_record_sha256"]),
        test_fingerprint=cast(str | None, row.get("test_fingerprint")),
        test_validation_guard=None,
    )


def _load_c7_under8_union(
    *,
    config: Mapping[str, object],
    c7_report: Mapping[str, object],
    c6_full: ModuleType,
    aggregate_module: ModuleType,
    correction_report: Mapping[str, object],
) -> list[RefreshCandidate]:
    artifacts = c7_report.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise ValueError("C7 artifact digest map is missing")
    taco_path = C7_REPORT_DIR / "taco_under8_candidates.jsonl"
    apps_decisions_path = C7_REPORT_DIR / "apps_under8_after_taco_decisions.jsonl"
    if artifacts.get("taco_under8_candidates") != _sha(taco_path):
        raise ValueError("C7 staged TACO-under8 digest mismatch")
    if artifacts.get("apps_under8_after_taco_decisions") != _sha(apps_decisions_path):
        raise ValueError("C7 APPS decision digest mismatch")
    taco = [_candidate_from_c7_row(row) for row in _jsonl(taco_path)]
    apps_decisions = _jsonl(apps_decisions_path)
    retained_apps_ids = {
        cast(str, row["candidate_id"])
        for row in apps_decisions
        if row.get("retained") is True and isinstance(row.get("candidate_id"), str)
    }
    apps_baseline = c6_full._baseline_under8_candidates(config, aggregate_module, correction_report)
    apps = [candidate for candidate in apps_baseline if candidate.candidate_id in retained_apps_ids]
    baseline = cast(Mapping[str, object], config["baseline"])
    if len(taco) != c7_report.get("incremental_taco_under8_preaugmentation_planning"):
        raise ValueError("C7 staged TACO-under8 count mismatch")
    if len(taco) + len(apps) != baseline["c7_under8_preaugmentation_planning_union"]:
        raise ValueError("C7 reconstructed under8 union count mismatch")
    union = [*taco, *apps]
    if len({candidate.candidate_id for candidate in union}) != len(union):
        raise ValueError("C7 reconstructed under8 candidate IDs are not unique")
    return union


def _stage_candidate(
    candidate: RefreshCandidate,
    *,
    solutions: Sequence[str],
    context_row: Mapping[str, object],
    source: Mapping[str, object],
    formal_ready: bool,
) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "source_name": candidate.source_name,
        "source_record_id": candidate.source_record_id,
        "dataset_id": source["dataset_id"],
        "dataset_revision": source["revision"],
        "declared_dataset_license": source["declared_license"],
        "provenance_note": source["provenance_note"],
        "prompt": candidate.prompt,
        "function_name": candidate.function_name,
        "function_signature": candidate.function_signature,
        "tests": [test_case_to_mapping(test) for test in candidate.tests],
        "source_test_count": len(candidate.tests),
        "accepted_source_solutions": list(solutions),
        "accepted_source_solution_count": len(solutions),
        "raw_reference_solution_hash": candidate.raw_reference_solution_hash,
        "difficulty": candidate.difficulty,
        "category": list(candidate.category),
        "raw_record_sha256": candidate.raw_record_sha256,
        "test_fingerprint": candidate.test_fingerprint,
        "prompt_protocol": context_row.get("prompt_protocol"),
        "prompt_sha256": context_row.get("prompt_sha256"),
        "prompt_tokens": context_row.get("prompt_tokens"),
        "quality_gate_required": context_row.get("quality_gate_required"),
        "requires_post_augmentation_context_recheck": not formal_ready,
        "formal_ready": formal_ready,
    }


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    c7_report = _validate_baseline(config)
    snapshot, frozen_shards = _validate_snapshot(config)
    source = cast(Mapping[str, object], config["deepcoder"])
    targets = cast(Mapping[str, object], config["targets"])
    baseline = cast(Mapping[str, object], config["baseline"])

    c6_full = _load_module(C6_FULL_SCRIPT, "wp9c_c6_full_for_c8")
    correction = _load_module(C6_CORRECTION_SCRIPT, "wp9c_c6_correction_for_c8")
    aggregate_module = _load_module(c6_full.AGGREGATE_SCRIPT, "wp9c_aggregate_for_c8")
    sft_refs, validation_refs, project_refs, humaneval_refs, ready_refs, tokenizer, correction_report = (
        c6_full._current_ready_references(config, aggregate_module)
    )

    all_candidates: list[RefreshCandidate] = []
    solutions_by_id: dict[str, list[str]] = {}
    source_summaries: list[dict[str, object]] = []
    for item in cast(list[Mapping[str, object]], source["source_priority"]):
        spec = RefreshSourceSpec(
            source_name=cast(str, item["source_name"]),
            dataset_id=cast(str, source["dataset_id"]),
            revision=cast(str, source["revision"]),
            config_name=cast(str, item["config_name"]),
            split=cast(str, source["split"]),
            declared_license=cast(str, source["declared_license"]),
            adapter="deepcoder",
        )
        candidates, solutions, summary = _scan_config(
            snapshot=snapshot,
            config_name=cast(str, spec.config_name),
            source_name=spec.source_name,
            dataset_id=spec.dataset_id,
            revision=spec.revision,
        )
        if summary["scanned_rows"] != item["expected_row_count"]:
            raise ValueError(f"C8 DeepCoder row-count drift: {spec.config_name}")
        all_candidates.extend(candidates)
        solutions_by_id.update(solutions)
        source_summaries.append(summary)
    if len({candidate.candidate_id for candidate in all_candidates}) != len(all_candidates):
        raise ValueError("C8 DeepCoder candidate IDs are not unique")

    ready_input = [candidate for candidate in all_candidates if len(candidate.tests) >= 8]
    under8_input = [candidate for candidate in all_candidates if 1 <= len(candidate.tests) <= 7]
    if len(ready_input) + len(under8_input) != len(all_candidates):
        raise ValueError("C8 test-count partition is incomplete")
    policy = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)

    ready_decisions = classify_refresh_candidates(
        [replace(candidate, tests=()) for candidate in ready_input],
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_refs,
        external_eval_references=[*humaneval_refs, *ready_refs],
        policy=policy,
    )
    ready_by_id = {candidate.candidate_id: candidate for candidate in ready_input}
    ready_dedup = [ready_by_id[item.candidate_id] for item in ready_decisions if item.retained]
    ready_context, ready_context_rows, ready_context_summary = c6_full._formal_context_filter(
        ready_dedup,
        tokenizer=tokenizer,
        cap=2048,
    )
    ready_context_by_id = {cast(str, row["candidate_id"]): row for row in ready_context_rows}
    deepcoder_ready_refs = [
        aggregate_module._candidate_reference(candidate, prefix="deepcoder-ready") for candidate in ready_context
    ]

    under8_decisions = classify_refresh_candidates(
        [replace(candidate, tests=()) for candidate in under8_input],
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_refs,
        external_eval_references=[*humaneval_refs, *ready_refs, *deepcoder_ready_refs],
        policy=policy,
    )
    under8_by_id = {candidate.candidate_id: candidate for candidate in under8_input}
    under8_dedup = [under8_by_id[item.candidate_id] for item in under8_decisions if item.retained]
    origins = {
        candidate.candidate_id: f"deepcoder_{candidate.category[-1].removeprefix('deepcoder_config:')}"
        for candidate in under8_dedup
    }
    deepcoder_under8, under8_context_rows, under8_context_summary = correction._under8_preaugmentation_context_filter(
        under8_dedup,
        tokenizer=tokenizer,
        cap=2048,
        origin_by_id=origins,
    )
    under8_context_by_id = {cast(str, row["candidate_id"]): row for row in under8_context_rows}
    deepcoder_under8_refs = [
        aggregate_module._candidate_reference(candidate, prefix="deepcoder-under8") for candidate in deepcoder_under8
    ]

    c7_union = _load_c7_under8_union(
        config=config,
        c7_report=c7_report,
        c6_full=c6_full,
        aggregate_module=aggregate_module,
        correction_report=correction_report,
    )
    c7_decisions = classify_refresh_candidates(
        [replace(candidate, tests=()) for candidate in c7_union],
        sft_references=[],
        validation_references=[],
        project_test_references=[],
        external_eval_references=[*deepcoder_ready_refs, *deepcoder_under8_refs],
        policy=policy,
    )
    unexpected_c7_rejections = [
        item
        for item in c7_decisions
        if not item.retained
        and (
            item.matched_record_id is None
            or not item.matched_record_id.startswith(("deepcoder-ready:", "deepcoder-under8:"))
        )
    ]
    if unexpected_c7_rejections:
        raise ValueError("C8 re-dedup changed the frozen C7 union for a non-DeepCoder reason")
    c7_by_id = {candidate.candidate_id: candidate for candidate in c7_union}
    c7_after_deepcoder = [c7_by_id[item.candidate_id] for item in c7_decisions if item.retained]

    ready_stage = [
        _stage_candidate(
            candidate,
            solutions=solutions_by_id[candidate.candidate_id],
            context_row=ready_context_by_id[candidate.candidate_id],
            source=source,
            formal_ready=True,
        )
        for candidate in ready_context
    ]
    under8_stage = [
        _stage_candidate(
            candidate,
            solutions=solutions_by_id[candidate.candidate_id],
            context_row=under8_context_by_id[candidate.candidate_id],
            source=source,
            formal_ready=False,
        )
        for candidate in deepcoder_under8
    ]

    base_ready = cast(int, baseline["ready_context_eligible_count"])
    deepcoder_ready_count = len(ready_context)
    deepcoder_under8_count = len(deepcoder_under8)
    c7_after_count = len(c7_after_deepcoder)
    ready_union = base_ready + deepcoder_ready_count
    under8_union = deepcoder_under8_count + c7_after_count
    planning_union = ready_union + under8_union
    under8_needed_for_exact = max(0, cast(int, targets["external_new_exact"]) - ready_union)
    success_fraction = under8_needed_for_exact / under8_union if under8_union else None
    ready_origin = Counter(candidate.source_name for candidate in ready_context)
    under8_origin = Counter(candidate.source_name for candidate in deepcoder_under8)
    under8_hist = Counter(len(candidate.tests) for candidate in deepcoder_under8)
    c7_hist = Counter(len(candidate.tests) for candidate in c7_after_deepcoder)

    report: dict[str, object] = {
        "schema_version": "wp9c-deepcoder-function-supply-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "protocol_amendment": config["protocol_amendment"],
        "formal_blockers": [
            "deepcoder_upstream_provenance_review_required",
            "deepcoder_reference_solution_execution_validation_not_run",
            "under8_test_augmentation_not_run",
            "final_augmented_context_recheck_not_run",
            "project_piston_reference_solution_validation_not_run",
        ],
        "config_path": str(config_path),
        "config_sha256": _sha(config_path),
        "dependency_sha256": {
            "audit_script": _sha(Path(__file__)),
            "c6_full_taco_script": _sha(C6_FULL_SCRIPT),
            "c6_context_correction_script": _sha(C6_CORRECTION_SCRIPT),
            "refresh_sources_module": _sha(REFRESH_SOURCES_MODULE),
            "json_strict_module": _sha(JSON_STRICT_MODULE),
        },
        "baseline": {
            "c7_report_sha256": baseline["c7_taco_under8_report_sha256"],
            "ready_context_eligible_before_piston": base_ready,
            "c7_under8_preaugmentation_planning_union": baseline["c7_under8_preaugmentation_planning_union"],
            "c7_zero_attrition_planning_union": baseline["c7_zero_attrition_planning_union"],
            "under8_formal_context_eligible": None,
        },
        "source_identity": config["deepcoder"],
        "frozen_shards_verified": frozen_shards,
        "source_summaries": source_summaries,
        "structural": {
            "all_direct_signature_candidates": len(all_candidates),
            "ready_ge8_input": len(ready_input),
            "under8_1_to_7_input": len(under8_input),
        },
        "ready_dedup": {
            "retained_before_context": len(ready_dedup),
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in ready_decisions).items())
            ),
        },
        "ready_context": ready_context_summary,
        "incremental_deepcoder_ready_context_eligible": deepcoder_ready_count,
        "deepcoder_ready_origin_counts": dict(sorted(ready_origin.items())),
        "under8_dedup": {
            "retained_before_preaugmentation_context": len(under8_dedup),
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in under8_decisions).items())
            ),
        },
        "under8_preaugmentation_context": under8_context_summary,
        "incremental_deepcoder_under8_preaugmentation_planning": deepcoder_under8_count,
        "deepcoder_under8_origin_counts": dict(sorted(under8_origin.items())),
        "deepcoder_under8_existing_test_count_histogram": {
            str(key): value for key, value in sorted(under8_hist.items())
        },
        "c7_under8_after_deepcoder_dedup": {
            "baseline_preaugmentation_planning_union": len(c7_union),
            "formal_context_eligible_count": None,
            "post_augmentation_context_recheck_required": True,
            "deepcoder_overlap_rejected": len(c7_union) - c7_after_count,
            "retained_preaugmentation_planning_count": c7_after_count,
            "retained_existing_test_count_histogram": {str(key): value for key, value in sorted(c7_hist.items())},
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in c7_decisions).items())
            ),
        },
        "supply_projection": {
            "current_ready_context_eligible_before_piston": base_ready,
            "deepcoder_ready_context_eligible_before_piston": deepcoder_ready_count,
            "ready_context_eligible_union_before_piston": ready_union,
            "deepcoder_under8_preaugmentation_planning": deepcoder_under8_count,
            "c7_under8_preaugmentation_planning_after_deepcoder_dedup": c7_after_count,
            "under8_preaugmentation_planning_union": under8_union,
            "zero_attrition_planning_union": planning_union,
            "incremental_planning_union_vs_c7": planning_union
            - cast(int, baseline["c7_zero_attrition_planning_union"]),
            "under8_planning_successes_needed_for_exact_2275": under8_needed_for_exact,
            "under8_planning_success_fraction_needed": success_fraction,
            "pre_piston_buffer_min_met_under_zero_attrition_planning": planning_union
            >= cast(int, targets["pre_piston_external_new_buffer_min"]),
            "pre_piston_buffer_target_met_under_zero_attrition_planning": planning_union
            >= cast(int, targets["pre_piston_external_new_buffer_target"]),
        },
        "notes": [
            "No source solution or testcase payload is executed, no tests are generated, and Piston is not run.",
            (
                "DeepCoder primeintellect projection has priority over DeepCoder taco projection through "
                "deterministic input order."
            ),
            (
                "Natural >=8 DeepCoder survivors receive production Exact-B context screening before under8 "
                "planning rows."
            ),
            (
                "DeepCoder under8 rows are planning-only; 4-7-test prompts crosscheck production canonicalization "
                "and 1-3-test rows use the explicit non-formal proxy."
            ),
            (
                "The frozen C7 TACO/APPS under8 union is re-deduplicated after DeepCoder ready and DeepCoder-under8 "
                "survivors."
            ),
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        report["artifact_sha256"] = {
            "deepcoder_ready_candidates": _write_jsonl(temporary / "deepcoder_ready_candidates.jsonl", ready_stage),
            "deepcoder_under8_candidates": _write_jsonl(temporary / "deepcoder_under8_candidates.jsonl", under8_stage),
            "ready_context": _write_jsonl(temporary / "ready_context.jsonl", ready_context_rows),
            "under8_context": _write_jsonl(temporary / "under8_context.jsonl", under8_context_rows),
            "ready_dedup_decisions": _write_jsonl(
                temporary / "ready_dedup_decisions.jsonl", [asdict(item) for item in ready_decisions]
            ),
            "under8_dedup_decisions": _write_jsonl(
                temporary / "under8_dedup_decisions.jsonl", [asdict(item) for item in under8_decisions]
            ),
            "c7_under8_after_deepcoder_decisions": _write_jsonl(
                temporary / "c7_under8_after_deepcoder_decisions.jsonl", [asdict(item) for item in c7_decisions]
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
