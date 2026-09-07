#!/usr/bin/env python3
"""Static full-BAAI/TACO incremental supply audit for the WP9-c 2500-pool amendment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from types import ModuleType
from typing import cast

from transformers import AutoTokenizer

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
    canonicalize_refresh_candidate,
    load_humanevalplus_references,
    refresh_test_set_fingerprint,
)
from code_verifier.data.schema import test_case_to_mapping
from code_verifier.prompting import build_code_prompt

ROOT = Path(__file__).resolve().parents[6]
LEGACY_DIR = ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0"
AGGREGATE_SCRIPT = LEGACY_DIR / "audit_function_supply_aggregate.py"
TACO_SHARD_SCRIPT = LEGACY_DIR / "audit_taco_shard.py"
AGGREGATE_CONFIG = ROOT / "configs/data/wp9c-function-supply-aggregate-audit.yaml"
NATIVE_CONFIG = ROOT / "configs/data/wp9c-native-function-supply-audit-v2.yaml"
JSON_STRICT_MODULE = ROOT / "src/code_verifier/data/json_strict.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load dependency: {path}")
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


def _stats(counts: Sequence[int]) -> dict[str, object]:
    if not counts:
        return {"count": 0}
    ordered = sorted(counts)
    p90_index = max(0, (9 * len(ordered) + 9) // 10 - 1)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p90": ordered[p90_index],
        "max": ordered[-1],
    }


def _formal_context_filter(
    candidates: Sequence[RefreshCandidate],
    *,
    tokenizer: object,
    cap: int,
) -> tuple[list[RefreshCandidate], list[dict[str, object]], dict[str, object]]:
    survivors: list[RefreshCandidate] = []
    rows: list[dict[str, object]] = []
    token_counts: list[int] = []
    for candidate in candidates:
        problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=42)
        if quality_gate_required:
            raise ValueError(
                f"natural >=8 TACO candidate unexpectedly requires a quality gate: {candidate.candidate_id}"
            )
        prompt = build_code_prompt(problem)
        rendered = tokenizer.apply_chat_template(  # type: ignore[attr-defined]
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            tokenize=False,
        )
        encoded = tokenizer(rendered, add_special_tokens=False)  # type: ignore[operator]
        count = len(encoded["input_ids"])
        if count <= 0:
            raise ValueError(f"non-positive Formal-B prompt token count: {candidate.candidate_id}")
        eligible = count <= cap
        token_counts.append(count)
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "prompt_protocol": "canonicalize_refresh_candidate_seed42_then_build_code_prompt_v1",
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "prompt_tokens": count,
                "context_eligible": eligible,
                "quality_gate_required": False,
            }
        )
        if eligible:
            survivors.append(candidate)
    return (
        survivors,
        rows,
        {
            "source_count": len(candidates),
            "context_eligible_count": len(survivors),
            "excluded_context_count": len(candidates) - len(survivors),
            "prompt_tokens": _stats(token_counts),
        },
    )


def _jsonl(path: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = loads_strict(line)
            if not isinstance(value, dict):
                raise ValueError(f"non-object JSONL row: {path}")
            result.append(cast(dict[str, object], value))
    return result


def _source_url_hash(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _difficulty(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    return normalized if normalized in {"easy", "medium", "hard"} else "unknown"


def _validate_download_manifest(config: Mapping[str, object]) -> tuple[Path, list[dict[str, object]], str]:
    source = config.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("missing source config")
    manifest_path = Path(cast(str, source["download_manifest"]))
    digest_path = manifest_path.with_name("manifest.sha256")
    if not manifest_path.is_file() or not digest_path.is_file():
        raise ValueError("full-TACO download manifest is missing")
    payload = manifest_path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if digest_path.read_text(encoding="ascii").strip() != actual:
        raise ValueError("full-TACO download manifest digest mismatch")
    manifest = loads_strict(payload.decode("utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "wp9c-taco-full-download-v1"
        or manifest.get("dataset_id") != source.get("dataset_id")
        or manifest.get("revision") != source.get("revision")
    ):
        raise ValueError("full-TACO download identity mismatch")
    snapshot = Path(cast(str, manifest["snapshot_path"]))
    shards = manifest.get("shards")
    if not isinstance(shards, list) or len(shards) != source.get("expected_shard_count"):
        raise ValueError("full-TACO shard inventory mismatch")
    verified: list[dict[str, object]] = []
    for row in shards:
        if not isinstance(row, dict):
            raise ValueError("invalid full-TACO shard manifest row")
        path = snapshot / cast(str, row["path"])
        if not path.is_file() or path.stat().st_size != row.get("size") or _sha(path) != row.get("sha256"):
            raise ValueError(f"full-TACO shard identity mismatch: {path}")
        verified.append(cast(dict[str, object], row))
    return snapshot, verified, actual


def _taco_candidates(
    snapshot: Path, shards: Sequence[Mapping[str, object]], taco_module: ModuleType
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
                if len(tests) < 8:
                    counts["under8_rows"] += 1
                    continue
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
                prompt = question.rstrip()
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
                    prompt=prompt,
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
                counts["structural_ge8_direct_signature_rows"] += 1
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("full-TACO candidate IDs are not unique")
    return candidates, solutions_by_id, counts


def _current_ready_references(
    config: Mapping[str, object], aggregate_module: ModuleType
) -> tuple[list[object], list[object], list[object], list[object], list[object], object, dict[str, object]]:
    baseline = cast(Mapping[str, object], config["baseline"])
    correction_path = Path(cast(str, baseline["correction_report"]))
    if _sha(correction_path) != baseline["correction_report_sha256"]:
        raise ValueError("context-correction baseline report SHA256 mismatch")
    correction = loads_strict(correction_path.read_text(encoding="utf-8"))
    if (
        not isinstance(correction, dict)
        or correction.get("schema_version") != "wp9c-function-supply-context-correction-v1"
        or correction.get("formal_eligible") is not False
        or correction.get("historical_evidence_mutated") is not False
    ):
        raise ValueError("context-correction baseline report identity/status mismatch")
    corrected_supply = correction.get("corrected_supply")
    if (
        not isinstance(corrected_supply, dict)
        or corrected_supply.get("corrected_ready_context_eligible_count") != baseline["ready_context_eligible_count"]
        or corrected_supply.get("corrected_augmentable_preaugmentation_planning_count")
        != baseline["under8_preaugmentation_planning_count"]
        or corrected_supply.get("under8_formal_context_eligible_count")
        != baseline["under8_formal_context_eligible_count"]
        or corrected_supply.get("zero_attrition_planning_potential_count")
        != baseline["zero_attrition_planning_potential_count"]
    ):
        raise ValueError("context-correction baseline supply counts mismatch")

    historical = correction.get("historical_aggregate_report")
    if (
        not isinstance(historical, dict)
        or historical.get("path") != baseline["historical_aggregate_report"]
        or historical.get("sha256") != baseline["historical_aggregate_report_sha256"]
    ):
        raise ValueError("historical aggregate binding differs from correction report")
    aggregate_path = Path(cast(str, baseline["historical_aggregate_report"]))
    if _sha(aggregate_path) != baseline["historical_aggregate_report_sha256"]:
        raise ValueError("historical aggregate report SHA256 mismatch")

    agg_cfg = load_yaml_mapping(AGGREGATE_CONFIG)
    expected = cast(dict[str, object], agg_cfg["expected_counts"])
    inputs = cast(dict[str, object], agg_cfg["inputs"])
    incumbents, _, _ = aggregate_module._load_existing_incumbents(
        Path(cast(str, inputs["existing_incumbent_dir"])), expected_count=cast(int, expected["existing_incumbent"])
    )
    artifact_digests = correction.get("artifact_sha256")
    ready_context_path = correction_path.parent / "context" / "ready_new.jsonl"
    if not isinstance(artifact_digests, dict) or artifact_digests.get("ready_context") != _sha(ready_context_path):
        raise ValueError("corrected ready-context artifact digest mismatch")
    survivor_ids = {
        cast(str, row["candidate_id"]) for row in _jsonl(ready_context_path) if row.get("context_eligible") is True
    }

    native_module = _load_module(aggregate_module.NATIVE_AUDIT_SCRIPT, "wp9c_native_taco_dependency")
    native_sources = native_module._source_configs(NATIVE_CONFIG)
    _, apps_path = native_module._resolve_source_file(native_sources["apps_train"])
    _, leetcode_path = native_module._resolve_source_file(native_sources["leetcode_merged"])
    native = [*native_module._apps_candidates(apps_path)[0], *native_module._leetcode_candidates(leetcode_path)[0]]
    opencoder, _ = aggregate_module._load_opencoder_ready(
        Path(cast(str, inputs["opencoder_stage_dir"])),
        expected_total=cast(int, expected["opencoder_stage_total"]),
        expected_ge8=cast(int, expected["opencoder_ready_ge8"]),
    )
    ready = [candidate for candidate in [*native, *opencoder] if candidate.candidate_id in survivor_ids]
    if len(incumbents) + len(ready) != cast(int, baseline["ready_context_eligible_count"]):
        raise ValueError("reconstructed corrected current-ready baseline count mismatch")

    formal = cast(dict[str, object], correction["formal_references"])
    reference_dir = Path(cast(str, inputs["formal_reference_dir"]))
    sft_refs, validation_refs, project_refs, _ = aggregate_module._load_formal_references(
        reference_dir, expected_digest=cast(str, formal["canonical_sha256"])
    )
    refresh_config = Path(cast(str, inputs["refresh_config"]))
    dataset_id, revision = aggregate_module._external_eval_identity(refresh_config)
    external_snapshot, humaneval_refs = load_humanevalplus_references(
        dataset_id=dataset_id, revision=revision, cache_dir=None
    )
    if asdict(external_snapshot) != cast(dict[str, object], formal["external_eval_snapshot"]):
        raise ValueError("HumanEvalPlus identity differs from corrected baseline")
    ready_refs = [
        aggregate_module._candidate_reference(candidate, prefix="current-ready") for candidate in [*incumbents, *ready]
    ]
    context = cast(dict[str, object], correction["context_filter"])
    loader = getattr(AutoTokenizer, "from_" + "pretrained")
    tokenizer = loader(
        cast(str, context["tokenizer_model_id"]),
        revision=cast(str, context["tokenizer_revision"]),
        local_files_only=True,
    )
    return (
        sft_refs,
        validation_refs,
        project_refs,
        humaneval_refs,
        ready_refs,
        tokenizer,
        cast(dict[str, object], correction),
    )


def _baseline_under8_candidates(
    config: Mapping[str, object],
    aggregate_module: ModuleType,
    correction_report: Mapping[str, object],
) -> list[RefreshCandidate]:
    baseline = cast(Mapping[str, object], config["baseline"])
    correction_path = Path(cast(str, baseline["correction_report"]))
    artifact_digests = correction_report.get("artifact_sha256")
    context_path = correction_path.parent / "context" / "under8.jsonl"
    if not isinstance(artifact_digests, dict) or artifact_digests.get("under8_context") != _sha(context_path):
        raise ValueError("corrected under8 planning artifact digest mismatch")
    survivor_ids = {
        cast(str, row["candidate_id"])
        for row in _jsonl(context_path)
        if row.get("preaugmentation_context_proxy_pass") is True
    }

    agg_cfg = load_yaml_mapping(AGGREGATE_CONFIG)
    expected = cast(dict[str, object], agg_cfg["expected_counts"])
    inputs = cast(dict[str, object], agg_cfg["inputs"])
    under8_module = _load_module(aggregate_module.UNDER8_AUDIT_SCRIPT, "wp9c_under8_taco_dependency")
    under8_config_path = aggregate_module._resolve_path(inputs.get("under8_config"), base=ROOT)
    under8_source = under8_module._source_config(under8_config_path)
    _, under8_path = under8_module._resolve_source_file(under8_source)
    under8_full, _, _ = under8_module._apps_under8_candidates(under8_path)
    if len(under8_full) != cast(int, expected["under8_augmentable"]):
        raise ValueError("reconstructed under8 structural count mismatch")
    survivors = [candidate for candidate in under8_full if candidate.candidate_id in survivor_ids]
    if len(survivors) != cast(int, baseline["under8_preaugmentation_planning_count"]):
        raise ValueError("reconstructed corrected under8 planning count mismatch")
    if baseline["under8_formal_context_eligible_count"] is not None:
        raise ValueError("under8 formal context eligibility must remain unresolved before augmentation")
    return survivors


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    payload = "".join(canonical_json(row) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    if (
        config.get("version") != "wp9c-taco-full-supply-audit-v1"
        or config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    ):
        raise ValueError("full-TACO audit protocol mismatch")
    if config.get("seed") != 42:
        raise ValueError("full-TACO supply audit seed must remain 42")
    targets = cast(Mapping[str, object], config["targets"])
    source_config = cast(Mapping[str, object], config["source"])
    selection = cast(Mapping[str, object], config["selection"])
    quality = cast(Mapping[str, object], config["quality"])
    expected_targets = {
        "active_pool": 2500,
        "sft_reuse_exact": 225,
        "external_new_exact": 2275,
        "pre_piston_external_new_buffer_min": 2600,
        "pre_piston_external_new_buffer_target": 2800,
    }
    if dict(targets) != expected_targets:
        raise ValueError("WP9-c amended target drift")
    if (
        source_config.get("source_name") != "BAAI/TACO"
        or source_config.get("dataset_id") != "BAAI/TACO"
        or source_config.get("revision") != "d593ed0a2becbbc952230bb89be09189bf1056dc"
        or source_config.get("config_name") != "ALL"
        or source_config.get("split") != "train"
        or source_config.get("declared_license") != "Apache-2.0"
        or source_config.get("shard_glob") != "ALL/train-*-of-00009.parquet"
        or source_config.get("expected_shard_count") != 9
        or source_config.get("adapter") != "taco_function_call_full_audit_v1"
    ):
        raise ValueError("full-TACO source identity/policy drift")
    if dict(selection) != {
        "minimum_unique_tests": 8,
        "max_prompt_tokens": 2048,
        "formal_prompt_protocol": "canonicalize_refresh_candidate_seed42_then_build_code_prompt_v1",
        "token_ngram_size": 5,
        "near_jaccard_threshold": 0.90,
        "priority": "after_current_ready_before_apps_under8",
    }:
        raise ValueError("full-TACO selection/dedup/context policy drift")
    if any(
        quality.get(key) is not False
        for key in ("execute_source_code", "generate_tests", "run_piston", "threshold_relaxation_allowed")
    ) or any(
        quality.get(key) is not True
        for key in ("require_reference_solution_execution_validation", "exclude_unresolved_quality_gate")
    ):
        raise ValueError("full-TACO supply audit quality policy drift")

    snapshot, shards, download_manifest_sha = _validate_download_manifest(config)
    aggregate_module = _load_module(AGGREGATE_SCRIPT, "wp9c_aggregate_taco_dependency")
    taco_module = _load_module(TACO_SHARD_SCRIPT, "wp9c_taco_shard_dependency")
    candidates, solutions_by_id, structural_counts = _taco_candidates(snapshot, shards, taco_module)
    sft_refs, validation_refs, project_refs, humaneval_refs, ready_refs, tokenizer, correction_report = (
        _current_ready_references(config, aggregate_module)
    )

    light = [replace(candidate, tests=()) for candidate in candidates]
    policy = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)
    decisions = classify_refresh_candidates(
        light,
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_refs,
        external_eval_references=[*humaneval_refs, *ready_refs],
        policy=policy,
    )
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    retained = [by_id[item.candidate_id] for item in decisions if item.retained]

    # classify_refresh_candidates already applies deterministic candidate-candidate dedup inside TACO.
    # Keep dedup on the raw source question plus the separate function_signature field. Only after dedup
    # apply the actual production Formal-B prompt projection to the intact >=8-test candidate.
    context_survivors, context_rows, context_summary = _formal_context_filter(
        retained,
        tokenizer=tokenizer,
        cap=2048,
    )
    context_row_by_id = {cast(str, row["candidate_id"]): row for row in context_rows}
    survivor_ids = {candidate.candidate_id for candidate in context_survivors}
    shard_sha_by_path = {cast(str, row["path"]): cast(str, row["sha256"]) for row in shards}
    staged_rows = []
    for candidate in candidates:
        if candidate.candidate_id not in survivor_ids:
            continue
        shard_path, separator, row_index_text = candidate.source_record_id.rpartition(":")
        if not separator or shard_path not in shard_sha_by_path:
            raise ValueError(f"invalid retained TACO source identity: {candidate.source_record_id}")
        row_index = int(row_index_text)
        upstream_source = candidate.category[0].removeprefix("taco_source:")
        staged_rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "dataset_id": source_config["dataset_id"],
                "dataset_revision": source_config["revision"],
                "declared_dataset_license": source_config["declared_license"],
                "provenance_note": source_config["provenance_note"],
                "source_shard_path": shard_path,
                "source_shard_sha256": shard_sha_by_path[shard_path],
                "source_row_index": row_index,
                "upstream_source": upstream_source,
                "dedup_prompt_protocol": "taco_raw_question_plus_separate_contract_v1",
                "prompt_projection_protocol": "canonicalize_refresh_candidate_seed42_then_build_code_prompt_v1",
                "formal_prompt_sha256": context_row_by_id[candidate.candidate_id]["prompt_sha256"],
                "formal_prompt_tokens": context_row_by_id[candidate.candidate_id]["prompt_tokens"],
                "raw_record_hash_protocol": "taco_candidate_provenance_projection_v1",
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
                "quality_gate_required": False,
                "formal_ready": False,
            }
        )

    baseline_under8 = _baseline_under8_candidates(config, aggregate_module, correction_report)
    taco_refs = [
        aggregate_module._candidate_reference(by_id[candidate.candidate_id], prefix="taco-ready")
        for candidate in context_survivors
    ]
    under8_taco_decisions = classify_refresh_candidates(
        [replace(candidate, tests=()) for candidate in baseline_under8],
        sft_references=[],
        validation_references=[],
        project_test_references=[],
        external_eval_references=taco_refs,
        policy=policy,
    )
    under8_by_id = {candidate.candidate_id: candidate for candidate in baseline_under8}
    unexpected_under8_rejections = [
        item
        for item in under8_taco_decisions
        if not item.retained
        and (item.matched_record_id is None or not item.matched_record_id.startswith("taco-ready:"))
    ]
    if unexpected_under8_rejections:
        raise ValueError("TACO-aware under8 dedup changed the frozen baseline for a non-TACO reason")
    under8_after_taco = [under8_by_id[item.candidate_id] for item in under8_taco_decisions if item.retained]
    under8_after_taco_hist = Counter(len(candidate.tests) for candidate in under8_after_taco)
    under8_after_taco_added_slots = sum(8 - len(candidate.tests) for candidate in under8_after_taco)

    baseline_ready = cast(int, cast(Mapping[str, object], config["baseline"])["ready_context_eligible_count"])
    under8_baseline_count = cast(
        int, cast(Mapping[str, object], config["baseline"])["under8_preaugmentation_planning_count"]
    )
    taco_count = len(staged_rows)
    ready_with_taco = baseline_ready + taco_count
    under8_after_taco_count = len(under8_after_taco)
    zero_attrition_with_under8 = ready_with_taco + under8_after_taco_count
    apps_needed_for_exact = max(0, cast(int, targets["external_new_exact"]) - ready_with_taco)
    apps_success_fraction = (
        0.0
        if apps_needed_for_exact == 0
        else apps_needed_for_exact / under8_after_taco_count
        if under8_after_taco_count
        else None
    )
    report = {
        "schema_version": "wp9c-taco-full-supply-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "protocol_amendment": config["protocol_amendment"],
        "formal_blockers": [
            "taco_reference_solution_transformation_not_frozen",
            "project_piston_reference_solution_validation_not_run",
            "taco_mixed_upstream_provenance_requires_preservation_and_review",
            "apps_under8_augmentation_and_final_context_recheck_not_run_if_needed",
        ],
        "config_path": str(config_path),
        "config_sha256": _sha(config_path),
        "download_manifest_sha256": download_manifest_sha,
        "dependency_sha256": {
            "audit_script": _sha(Path(__file__)),
            "aggregate_script": _sha(AGGREGATE_SCRIPT),
            "taco_shard_script": _sha(TACO_SHARD_SCRIPT),
            "aggregate_config": _sha(AGGREGATE_CONFIG),
            "json_strict_module": _sha(JSON_STRICT_MODULE),
        },
        "source_identity": config["source"],
        "structural_counts": dict(sorted(structural_counts.items())),
        "dedup": {
            "input_ge8_direct_signature": len(candidates),
            "retained_after_formal_current_ready_and_intra_taco_dedup": len(retained),
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in decisions).items())
            ),
        },
        "context": context_summary,
        "incremental_taco_context_eligible": taco_count,
        "apps_under8_after_taco_dedup": {
            "baseline_preaugmentation_planning_count": under8_baseline_count,
            "formal_context_eligible_count": None,
            "post_augmentation_context_recheck_required": True,
            "taco_overlap_rejected": under8_baseline_count - under8_after_taco_count,
            "retained_preaugmentation_planning_count": under8_after_taco_count,
            "retained_existing_test_count_histogram": {
                str(key): value for key, value in sorted(under8_after_taco_hist.items())
            },
            "minimum_added_test_slots_to_reach_8": under8_after_taco_added_slots,
            "rejection_reason_counts": dict(
                sorted(Counter(item.rejection_reason or "retained" for item in under8_taco_decisions).items())
            ),
        },
        "supply_projection": {
            "current_ready_context_eligible_before_piston": baseline_ready,
            "ready_plus_taco_context_eligible_before_piston": ready_with_taco,
            "apps_under8_preaugmentation_planning_baseline": under8_baseline_count,
            "apps_under8_preaugmentation_planning_after_taco_dedup": under8_after_taco_count,
            "zero_attrition_planning_ready_plus_taco_plus_under8": zero_attrition_with_under8,
            "apps_under8_planning_successes_needed_for_exact_2275": apps_needed_for_exact,
            "apps_under8_planning_success_fraction_needed": apps_success_fraction,
            "pre_piston_buffer_min_met_under_zero_attrition_planning": zero_attrition_with_under8
            >= cast(int, targets["pre_piston_external_new_buffer_min"]),
            "pre_piston_buffer_target_met_under_zero_attrition_planning": zero_attrition_with_under8
            >= cast(int, targets["pre_piston_external_new_buffer_target"]),
        },
        "baseline_context_correction_report_sha256": cast(Mapping[str, object], config["baseline"])[
            "correction_report_sha256"
        ],
        "historical_aggregate_report_sha256": cast(Mapping[str, object], config["baseline"])[
            "historical_aggregate_report_sha256"
        ],
        "baseline_formal_reference_digest": cast(Mapping[str, object], correction_report["formal_references"])[
            "canonical_sha256"
        ],
        "notes": [
            "No candidate solution or testcase payload is executed and no tests are generated.",
            (
                "Priority is corrected current-ready 1276, then natural TACO >=8 survivors, then APPS under8 "
                "planning rows."
            ),
            (
                "The corrected 1119 APPS-under8 pre-augmentation planning baseline is re-deduplicated against TACO "
                "survivors before supply planning; it is not formal context-eligible supply."
            ),
            (
                "Dedup uses the raw TACO question plus the separate function contract; each dedup survivor then uses "
                "production canonicalize_refresh_candidate(seed=42) plus build_code_prompt before Exact Formal-B "
                "counting."
            ),
            "Every APPS-under8 survivor requires final post-augmentation Exact-B context recheck.",
            "Survivors remain engineering candidates until source-solution transformation and Piston validation pass.",
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        artifacts = {
            "candidates": _write_jsonl(temporary / "candidates.jsonl", staged_rows),
            "context": _write_jsonl(temporary / "context.jsonl", context_rows),
            "dedup_decisions": _write_jsonl(temporary / "dedup_decisions.jsonl", [asdict(item) for item in decisions]),
            "apps_under8_after_taco_decisions": _write_jsonl(
                temporary / "apps_under8_after_taco_decisions.jsonl",
                [asdict(item) for item in under8_taco_decisions],
            ),
        }
        report["artifact_sha256"] = artifacts
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
