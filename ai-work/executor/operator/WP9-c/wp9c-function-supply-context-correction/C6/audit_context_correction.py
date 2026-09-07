#!/usr/bin/env python3
"""Correct the WP9-c aggregate context gate without rewriting historical aggregate evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
import random
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import cast

from transformers import AutoTokenizer

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.function_refresh_engineering import _read_candidates
from code_verifier.data.json_strict import loads_strict
from code_verifier.data.refresh_dedup import RefreshDedupPolicy, classify_refresh_candidates
from code_verifier.data.refresh_sources import (
    RefreshCandidate,
    canonicalize_refresh_candidate,
    load_humanevalplus_references,
)
from code_verifier.data.schema import test_case_to_mapping
from code_verifier.prompting import build_code_prompt, build_code_prompt_from_fields

ROOT = Path(__file__).resolve().parents[6]
LEGACY_DIR = ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0"
AGGREGATE_SCRIPT = LEGACY_DIR / "audit_function_supply_aggregate.py"
NATIVE_SCRIPT = LEGACY_DIR / "audit_native_function_supply.py"
UNDER8_SCRIPT = LEGACY_DIR / "audit_apps_under8_augmentable.py"
EXPECTED_AGGREGATE_SHA256 = "f6ff5a9cb688fb60d433f7f9e973d327" + "3e5d18f04e3088855a1a43a06c2cdfd5"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load correction dependency: {path}")
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


def _resolve(value: object, *, base: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("context-correction path is invalid")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


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


def _stats(counts: Sequence[int]) -> dict[str, object]:
    ordered = sorted(counts)
    if not ordered:
        return {"count": 0}
    p90_index = max(0, math.ceil(0.90 * len(ordered)) - 1)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p90": ordered[p90_index],
        "max": ordered[-1],
    }


def _prompt_token_count(prompt: str, *, tokenizer: object) -> int:
    rendered = tokenizer.apply_chat_template(  # type: ignore[attr-defined]
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )
    encoded = tokenizer(rendered, add_special_tokens=False)  # type: ignore[operator]
    count = len(encoded["input_ids"])
    if count <= 0:
        raise ValueError("non-positive Formal-B prompt token count")
    return count


def _formal_context_filter(
    candidates: Sequence[RefreshCandidate],
    *,
    tokenizer: object,
    cap: int,
    origin_by_id: Mapping[str, str],
) -> tuple[list[RefreshCandidate], list[dict[str, object]], dict[str, object]]:
    survivors: list[RefreshCandidate] = []
    rows: list[dict[str, object]] = []
    token_counts: list[int] = []
    for candidate in candidates:
        problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=42)
        prompt = build_code_prompt(problem)
        count = _prompt_token_count(prompt, tokenizer=tokenizer)
        token_counts.append(count)
        eligible = count <= cap
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "origin": origin_by_id[candidate.candidate_id],
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "prompt_protocol": "build_code_prompt_v1",
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "prompt_tokens": count,
                "context_eligible": eligible,
                "quality_gate_required": quality_gate_required,
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


def _under8_preaugmentation_prompt(candidate: RefreshCandidate, *, seed: int) -> tuple[str, int, bool]:
    if not 1 <= len(candidate.tests) <= 7:
        raise ValueError(f"under8 candidate must have 1-7 tests: {candidate.candidate_id}")
    if candidate.function_name == "solve_io":
        raise ValueError(f"under8 planning proxy is restricted to native function-call rows: {candidate.candidate_id}")

    digest = hashlib.sha256(f"wp9a-refresh-tests-v1|{seed}|{candidate.candidate_id}".encode()).digest()
    shuffled = list(candidate.tests)
    random.Random(int.from_bytes(digest, byteorder="big")).shuffle(shuffled)
    visible = shuffled[: min(2, len(shuffled))]
    prompt = build_code_prompt_from_fields(
        candidate.prompt.rstrip(),
        candidate.function_signature,
        [test_case_to_mapping(test_case) for test_case in visible],
    )

    exact_for_current_test_set = len(candidate.tests) >= 4
    if exact_for_current_test_set:
        problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=seed)
        if quality_gate_required is not True:
            raise ValueError(f"under8 candidate unexpectedly bypassed the quality gate: {candidate.candidate_id}")
        exact_prompt = build_code_prompt(problem)
        if prompt != exact_prompt:
            raise ValueError(
                f"under8 visible-prompt proxy diverged from production canonicalization: {candidate.candidate_id}"
            )
    return prompt, len(visible), exact_for_current_test_set


def _under8_preaugmentation_context_filter(
    candidates: Sequence[RefreshCandidate],
    *,
    tokenizer: object,
    cap: int,
    origin_by_id: Mapping[str, str],
) -> tuple[list[RefreshCandidate], list[dict[str, object]], dict[str, object]]:
    survivors: list[RefreshCandidate] = []
    rows: list[dict[str, object]] = []
    token_counts: list[int] = []
    exact_current_count = 0
    proxy_only_count = 0
    exact_current_pass_count = 0
    proxy_only_pass_count = 0
    for candidate in candidates:
        prompt, visible_count, exact_for_current_test_set = _under8_preaugmentation_prompt(candidate, seed=42)
        count = _prompt_token_count(prompt, tokenizer=tokenizer)
        token_counts.append(count)
        eligible = count <= cap
        exact_current_count += int(exact_for_current_test_set)
        proxy_only_count += int(not exact_for_current_test_set)
        exact_current_pass_count += int(exact_for_current_test_set and eligible)
        proxy_only_pass_count += int(not exact_for_current_test_set and eligible)
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "origin": origin_by_id[candidate.candidate_id],
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "prompt_protocol": "build_code_prompt_from_fields_preaugmentation_visible_proxy_v1",
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "prompt_tokens": count,
                "preaugmentation_context_proxy_pass": eligible,
                "quality_gate_required": True,
                "existing_test_count": len(candidate.tests),
                "visible_existing_test_count": visible_count,
                "projection_exact_for_current_test_set": exact_for_current_test_set,
                "requires_post_augmentation_context_recheck": True,
            }
        )
        if eligible:
            survivors.append(candidate)
    return (
        survivors,
        rows,
        {
            "source_count": len(candidates),
            "preaugmentation_context_proxy_pass_count": len(survivors),
            "preaugmentation_context_proxy_fail_count": len(candidates) - len(survivors),
            "production_canonicalization_crosschecked_count": exact_current_count,
            "production_canonicalization_crosschecked_pass_count": exact_current_pass_count,
            "proxy_only_lt4_test_count": proxy_only_count,
            "proxy_only_lt4_test_pass_count": proxy_only_pass_count,
            "formal_context_eligible_count": None,
            "final_augmented_context_recheck_required": True,
            "prompt_tokens": _stats(token_counts),
        },
    )


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    if config.get("version") != "wp9c-function-supply-context-correction-v1":
        raise ValueError("context-correction config version mismatch")
    if config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1" or config.get("seed") != 42:
        raise ValueError("context-correction protocol/seed drift")
    baseline = config.get("baseline")
    context_cfg = config.get("context_filter")
    quality = config.get("quality")
    if not isinstance(baseline, dict) or not isinstance(context_cfg, dict) or not isinstance(quality, dict):
        raise ValueError("context-correction config structure is invalid")
    if context_cfg != {
        "max_prompt_tokens": 2048,
        "prompt_protocol": "build_code_prompt_v1",
        "under8_pre_augmentation_prompt_protocol": "build_code_prompt_from_fields_preaugmentation_visible_proxy_v1",
        "model_identity_policy": "reuse_aggregate_formal_b_identity",
    }:
        raise ValueError("context-correction Formal-B policy drift")
    if any(
        quality.get(key) is not False
        for key in ("execute_source_code", "generate_tests", "run_piston", "threshold_relaxation_allowed")
    ):
        raise ValueError("context correction must remain static-only")
    if quality.get("preserve_old_aggregate_evidence") is not True:
        raise ValueError("context correction must preserve old aggregate evidence")

    aggregate_report_path = _resolve(baseline.get("aggregate_report"), base=ROOT)
    aggregate_sha_path = _resolve(baseline.get("aggregate_report_sha256_file"), base=ROOT)
    actual_aggregate_sha = _sha(aggregate_report_path)
    if aggregate_sha_path.read_text(encoding="ascii").strip() != actual_aggregate_sha:
        raise ValueError("historical aggregate report digest file mismatch")
    if actual_aggregate_sha != EXPECTED_AGGREGATE_SHA256:
        raise ValueError("historical aggregate report differs from the published C0 digest")
    aggregate_report = loads_strict(aggregate_report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(aggregate_report, dict)
        or aggregate_report.get("schema_version") != "wp9c-function-supply-aggregate-audit-v1"
    ):
        raise ValueError("historical aggregate report schema mismatch")
    aggregate_supply = aggregate_report.get("aggregate_supply")
    if (
        not isinstance(aggregate_supply, dict)
        or aggregate_supply.get("ready_context_eligible_count")
        != baseline.get("reported_ready_context_eligible_count")
        or aggregate_supply.get("augmentable_context_eligible_count")
        != baseline.get("reported_augmentable_context_eligible_count")
    ):
        raise ValueError("historical aggregate reported counts drift")

    aggregate_config_path = _resolve(baseline.get("aggregate_config"), base=ROOT)
    aggregate_config = load_yaml_mapping(aggregate_config_path)
    if aggregate_report.get("config_digest") != _sha(aggregate_config_path):
        raise ValueError("historical aggregate config binding drift")
    expected = cast(dict[str, object], aggregate_config["expected_counts"])
    inputs = cast(dict[str, object], aggregate_config["inputs"])

    aggregate_module = _load_module(AGGREGATE_SCRIPT, "wp9c_context_fix_aggregate_dependency")
    native_module = _load_module(NATIVE_SCRIPT, "wp9c_context_fix_native_dependency")
    under8_module = _load_module(UNDER8_SCRIPT, "wp9c_context_fix_under8_dependency")

    incumbents, _, incumbent_binding = aggregate_module._load_existing_incumbents(
        _resolve(inputs.get("existing_incumbent_dir"), base=ROOT),
        expected_count=cast(int, expected["existing_incumbent"]),
    )
    if len(incumbents) != 654:
        raise ValueError("corrected context audit requires the frozen 654 exact-B incumbents")

    native_config_path = _resolve(inputs.get("native_ready_config"), base=ROOT)
    native_sources = native_module._source_configs(native_config_path)
    _, apps_path = native_module._resolve_source_file(native_sources["apps_train"])
    _, leetcode_path = native_module._resolve_source_file(native_sources["leetcode_merged"])
    apps_candidates, _ = native_module._apps_candidates(apps_path)
    leetcode_candidates, _ = native_module._leetcode_candidates(leetcode_path)
    native_ready = [*apps_candidates, *leetcode_candidates]
    if len(native_ready) != cast(int, expected["native_ready_structural"]):
        raise ValueError("reconstructed native >=8 candidate count mismatch")

    opencoder_stage_dir = _resolve(inputs.get("opencoder_stage_dir"), base=ROOT)
    stage_manifest = loads_strict((opencoder_stage_dir / "stage_manifest.json").read_text(encoding="utf-8"))
    if (
        not isinstance(stage_manifest, dict)
        or stage_manifest.get("candidate_count") != expected["opencoder_stage_total"]
    ):
        raise ValueError("OpenCoder stage manifest count mismatch")
    if _sha(opencoder_stage_dir / "candidates.jsonl") != stage_manifest.get("records_digest"):
        raise ValueError("OpenCoder stage candidate digest mismatch")
    opencoder_all = _read_candidates(opencoder_stage_dir / "candidates.jsonl")
    opencoder_ready = [candidate for candidate in opencoder_all if len(candidate.tests) >= 8]
    if len(opencoder_ready) != cast(int, expected["opencoder_ready_ge8"]):
        raise ValueError("reconstructed OpenCoder >=8 candidate count mismatch")

    native_report_path = _resolve(inputs.get("native_ready_report"), base=ROOT)
    native_report, _ = aggregate_module._verified_report(native_report_path)
    reference_digest = native_report.get("reference_canonical_sha256")
    if not isinstance(reference_digest, str):
        raise ValueError("native baseline lacks formal reference digest")
    formal_reference_dir = _resolve(inputs.get("formal_reference_dir"), base=ROOT)
    sft_refs, validation_refs, project_test_refs, reference_path = aggregate_module._load_formal_references(
        formal_reference_dir,
        expected_digest=reference_digest,
    )
    refresh_config = _resolve(inputs.get("refresh_config"), base=ROOT)
    dataset_id, external_revision = aggregate_module._external_eval_identity(refresh_config)
    external_snapshot, humaneval_refs = load_humanevalplus_references(
        dataset_id=dataset_id,
        revision=external_revision,
        cache_dir=None,
    )
    if (
        asdict(external_snapshot)
        != cast(dict[str, object], aggregate_report["formal_references"])["external_eval_snapshot"]
    ):
        raise ValueError("HumanEvalPlus identity differs from historical aggregate evidence")

    ready_new = [*native_ready, *opencoder_ready]
    ready_origin: dict[str, str] = {}
    for candidate in native_ready:
        ready_origin[candidate.candidate_id] = (
            "native_apps_ge8" if candidate.source_name == "codeparrot/apps" else "native_leetcode_ge8"
        )
    for candidate in opencoder_ready:
        ready_origin[candidate.candidate_id] = "opencoder_ge8"
    policy = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)
    incumbent_refs = [aggregate_module._candidate_reference(candidate, prefix="incumbent") for candidate in incumbents]
    ready_decisions = classify_refresh_candidates(
        ready_new,
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_test_refs,
        external_eval_references=[*humaneval_refs, *incumbent_refs],
        policy=policy,
    )
    ready_by_id = {candidate.candidate_id: candidate for candidate in ready_new}
    ready_decision_rows = aggregate_module._decision_rows(
        ready_decisions,
        candidates=ready_by_id,
        origin_by_id=ready_origin,
    )
    historical_ready_decisions = _jsonl(aggregate_report_path.parent / "decisions" / "ready_new.jsonl")
    if ready_decision_rows != historical_ready_decisions:
        raise ValueError("context correction unexpectedly changed frozen ready dedup decisions")
    ready_retained = [ready_by_id[item.candidate_id] for item in ready_decisions if item.retained]

    context_identity = cast(dict[str, object], aggregate_report["context_filter"])
    model_id = context_identity.get("tokenizer_model_id")
    revision = context_identity.get("tokenizer_revision")
    if not isinstance(model_id, str) or not isinstance(revision, str):
        raise ValueError("historical aggregate tokenizer identity is incomplete")
    tokenizer_loader = getattr(AutoTokenizer, "from_" + "pretrained")
    tokenizer = tokenizer_loader(model_id, revision=revision, local_files_only=True)
    ready_context, ready_context_rows, ready_context_summary = _formal_context_filter(
        ready_retained,
        tokenizer=tokenizer,
        cap=2048,
        origin_by_id=ready_origin,
    )

    under8_config_path = _resolve(inputs.get("under8_config"), base=ROOT)
    under8_source = under8_module._source_config(under8_config_path)
    _, under8_path = under8_module._resolve_source_file(under8_source)
    under8_candidates, _, _ = under8_module._apps_under8_candidates(under8_path)
    if len(under8_candidates) != cast(int, expected["under8_augmentable"]):
        raise ValueError("reconstructed APPS-under8 candidate count mismatch")
    all_corrected_ready = [*incumbents, *ready_context]
    all_ready_refs = [
        aggregate_module._candidate_reference(candidate, prefix="ready") for candidate in all_corrected_ready
    ]
    under8_origin = {candidate.candidate_id: "apps_under8_augmentable" for candidate in under8_candidates}
    under8_decisions = classify_refresh_candidates(
        under8_candidates,
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_test_refs,
        external_eval_references=[*humaneval_refs, *all_ready_refs],
        policy=policy,
    )
    under8_by_id = {candidate.candidate_id: candidate for candidate in under8_candidates}
    under8_retained = [under8_by_id[item.candidate_id] for item in under8_decisions if item.retained]
    under8_context, under8_context_rows, under8_context_summary = _under8_preaugmentation_context_filter(
        under8_retained,
        tokenizer=tokenizer,
        cap=2048,
        origin_by_id=under8_origin,
    )
    under8_hist = Counter(len(candidate.tests) for candidate in under8_context)
    added_test_slots = sum(8 - len(candidate.tests) for candidate in under8_context)

    reported_ready = cast(int, baseline["reported_ready_context_eligible_count"])
    reported_under8 = cast(int, baseline["reported_augmentable_context_eligible_count"])
    corrected_ready = len(incumbents) + len(ready_context)
    under8_preaugmentation_planning = len(under8_context)
    zero_attrition_planning = corrected_ready + under8_preaugmentation_planning
    ready_source_counts = Counter(["existing_incumbent"] * len(incumbents))
    ready_source_counts.update(ready_origin[candidate.candidate_id] for candidate in ready_context)
    correction = {
        "reported_ready_context_eligible_count": reported_ready,
        "corrected_ready_context_eligible_count": corrected_ready,
        "ready_delta": corrected_ready - reported_ready,
        "reported_augmentable_context_eligible_count": reported_under8,
        "corrected_augmentable_preaugmentation_planning_count": under8_preaugmentation_planning,
        "augmentable_preaugmentation_planning_delta": under8_preaugmentation_planning - reported_under8,
        "under8_formal_context_eligible_count": None,
        "under8_post_augmentation_context_recheck_required": True,
        "zero_attrition_planning_potential_count": zero_attrition_planning,
        "remaining_gap_to_external_new_2275_zero_attrition_planning": max(0, 2275 - zero_attrition_planning),
        "ready_source_counts": dict(sorted(ready_source_counts.items())),
        "minimum_added_test_slots_to_reach_8": added_test_slots,
        "under8_existing_test_count_histogram": {str(key): value for key, value in sorted(under8_hist.items())},
        "historical_ready_context_count_affected": corrected_ready != reported_ready,
        "historical_under8_preaugmentation_planning_count_affected": (
            under8_preaugmentation_planning != reported_under8
        ),
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        artifacts = {
            "ready_context": _write_jsonl(temporary / "context" / "ready_new.jsonl", ready_context_rows),
            "under8_context": _write_jsonl(temporary / "context" / "under8.jsonl", under8_context_rows),
            "under8_decisions": _write_jsonl(
                temporary / "decisions" / "under8.jsonl",
                [asdict(item) for item in under8_decisions],
            ),
        }
        report: dict[str, object] = {
            "schema_version": "wp9c-function-supply-context-correction-v1",
            "evidence_class": "engineering_data_audit_correction_only",
            "formal_eligible": False,
            "protocol_amendment": config["protocol_amendment"],
            "correction_reason": (
                "historical aggregate context filtering tokenized candidate.prompt directly instead of the formal "
                "build_code_prompt projection used by calibration/GRPO"
            ),
            "historical_evidence_mutated": False,
            "historical_aggregate_report": {
                "path": str(aggregate_report_path),
                "sha256": actual_aggregate_sha,
                "reported_supply": aggregate_supply,
            },
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "dependency_sha256": {
                "correction_script": _sha(Path(__file__)),
                "aggregate_script": _sha(AGGREGATE_SCRIPT),
                "native_script": _sha(NATIVE_SCRIPT),
                "under8_script": _sha(UNDER8_SCRIPT),
                "prompting_module": _sha(ROOT / "src/code_verifier/prompting.py"),
            },
            "formal_references": {
                "canonical_path": str(reference_path),
                "canonical_sha256": reference_digest,
                "external_eval_snapshot": asdict(external_snapshot),
            },
            "context_filter": {
                "max_prompt_tokens": 2048,
                "prompt_protocol": "build_code_prompt_v1",
                "under8_pre_augmentation_prompt_protocol": (
                    "build_code_prompt_from_fields_preaugmentation_visible_proxy_v1"
                ),
                "chat_template": "formal_b_tokenizer_apply_chat_template_add_generation_prompt_v1",
                "tokenizer_model_id": model_id,
                "tokenizer_revision": revision,
                "ready_new": ready_context_summary,
                "under8_pre_augmentation": under8_context_summary,
            },
            "incumbent_binding": incumbent_binding,
            "corrected_supply": correction,
            "artifact_sha256": artifacts,
            "formal_blockers": [
                "ready_reference_solution_transformation_not_frozen",
                "project_piston_reference_solution_validation_not_run",
                "under8_test_augmentation_not_run",
                "under8_context_must_be_rechecked_after_final_augmented_tests",
            ],
            "notes": [
                (
                    "Frozen formal-reference and ready candidate dedup decisions are preserved; only the context "
                    "gate is corrected."
                ),
                (
                    "APPS-under8 is re-deduplicated after corrected ready context survivors because ready tasks "
                    "retain priority."
                ),
                (
                    "Under8 context is planning-only. Its prompt projection reuses the production deterministic "
                    "two-visible-test shuffle where possible; 4-7-test rows are cross-checked byte-for-byte against "
                    "canonicalize_refresh_candidate + build_code_prompt, while 1-3-test rows use the same visible "
                    "projection as an explicit proxy because production canonicalization requires at least four tests."
                ),
                "Every under8 row must be context-rechecked after final test augmentation.",
                "No solution/test payload is executed, no tests are generated, and Piston is not run.",
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
    report = audit(Path(args.config).resolve(), Path(args.output_dir).resolve())
    print(canonical_json(report))


if __name__ == "__main__":
    main()
