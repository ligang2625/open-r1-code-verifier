#!/usr/bin/env python3
"""Aggregate WP9-c function-level supply without executing candidate code."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
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
from code_verifier.data.deduplicate import canonical_json, problem_reference_solution_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.data.prepare import load_canonical_jsonl
from code_verifier.data.refresh_dedup import RefreshDedupDecision, RefreshDedupPolicy, classify_refresh_candidates
from code_verifier.data.refresh_sources import (
    OverlapReference,
    ReferenceClass,
    RefreshCandidate,
    load_humanevalplus_references,
    refresh_problem_test_set_fingerprint,
)
from code_verifier.data.schema import CodeProblem, problem_from_mapping

ROOT = Path(__file__).resolve().parents[6]
NATIVE_AUDIT_SCRIPT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_native_function_supply.py"
)
UNDER8_AUDIT_SCRIPT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_apps_under8_augmentable.py"
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_report(path: Path) -> tuple[dict[str, object], str]:
    digest_path = path.with_name("report.sha256")
    if not path.is_file() or not digest_path.is_file():
        raise ValueError(f"report/digest missing: {path}")
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    expected = digest_path.read_text(encoding="ascii").strip()
    if actual != expected:
        raise ValueError(f"report digest mismatch for {path}: expected {expected}, got {actual}")
    value = loads_strict(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"report is not an object: {path}")
    return cast(dict[str, object], value), actual


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load audit dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_path(value: object, *, base: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("aggregate audit config path is invalid")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _reference(problem: CodeProblem, reference_class: ReferenceClass) -> OverlapReference:
    return OverlapReference(
        reference_id=f"{reference_class}:{problem.problem_id}",
        reference_class=reference_class,
        prompt=problem.prompt,
        function_signature=problem.function_signature,
        source_url_hash=problem.metadata.source_url_hash,
        reference_solution_hash=problem_reference_solution_hash(problem),
        test_fingerprint=refresh_problem_test_set_fingerprint(problem),
    )


def _candidate_reference(candidate: RefreshCandidate, *, prefix: str) -> OverlapReference:
    return OverlapReference(
        reference_id=f"{prefix}:{candidate.candidate_id}",
        reference_class="external_eval",
        prompt=candidate.prompt,
        function_signature=candidate.function_signature,
        source_url_hash=candidate.source_url_hash,
        reference_solution_hash=candidate.raw_reference_solution_hash,
        test_fingerprint=candidate.test_fingerprint,
    )


def _light(candidate: RefreshCandidate) -> RefreshCandidate:
    if candidate.test_fingerprint is None:
        raise ValueError(f"candidate lacks frozen test fingerprint: {candidate.candidate_id}")
    return replace(candidate, tests=())


def _load_existing_incumbents(
    incumbent_dir: Path,
    *,
    expected_count: int,
) -> tuple[list[RefreshCandidate], dict[str, object], dict[str, object]]:
    summary_path = incumbent_dir / "reports" / "summary.json"
    canonical_path = incumbent_dir / "canonical" / "problems.jsonl"
    summary = loads_strict(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or summary.get("schema_version") != "wp9c-function-context-bundle-v1":
        raise ValueError("existing incumbent summary schema mismatch")
    if summary.get("record_count") != expected_count:
        raise ValueError("existing incumbent summary count mismatch")
    records_digest = summary.get("records_digest")
    if not isinstance(records_digest, str) or _sha(canonical_path) != records_digest:
        raise ValueError("existing incumbent canonical digest mismatch")
    constraints = summary.get("constraints")
    if not isinstance(constraints, dict) or constraints.get("max_prompt_tokens") != 2048:
        raise ValueError("existing incumbent context policy mismatch")

    candidates: list[RefreshCandidate] = []
    count = 0
    test_count_min: int | None = None
    with canonical_path.open("rb") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            count += 1
            row = loads_strict(raw_line.decode("utf-8"))
            problem = problem_from_mapping(row)
            test_count = len(problem.visible_tests) + len(problem.train_hidden_tests) + len(problem.eval_hidden_tests)
            test_count_min = test_count if test_count_min is None else min(test_count_min, test_count)
            if test_count < 8:
                raise ValueError(f"existing incumbent is not >=8-test quality-safe: {problem.problem_id}")
            candidates.append(
                RefreshCandidate(
                    candidate_id=problem.problem_id,
                    source_name=problem.source,
                    source_record_id=f"existing654/{problem.problem_id}",
                    prompt=problem.prompt,
                    function_name=problem.function_name,
                    function_signature=problem.function_signature,
                    tests=(),
                    source_url_hash=problem.metadata.source_url_hash,
                    raw_reference_solution_hash=problem_reference_solution_hash(problem),
                    difficulty=problem.metadata.difficulty,
                    category=problem.metadata.category,
                    raw_record_sha256=hashlib.sha256(raw_line).hexdigest(),
                    test_fingerprint=refresh_problem_test_set_fingerprint(problem),
                    test_validation_guard=None,
                )
            )
    if count != expected_count or len(candidates) != expected_count:
        raise ValueError("existing incumbent canonical count mismatch")
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("existing incumbent IDs are not unique")
    return (
        candidates,
        cast(dict[str, object], summary),
        {
            "canonical_path": str(canonical_path),
            "canonical_digest": records_digest,
            "summary_path": str(summary_path),
            "summary_digest": _sha(summary_path),
            "test_count_min": test_count_min,
        },
    )


def _load_opencoder_ready(
    stage_dir: Path,
    *,
    expected_total: int,
    expected_ge8: int,
) -> tuple[list[RefreshCandidate], dict[str, object]]:
    manifest_path = stage_dir / "stage_manifest.json"
    candidates_path = stage_dir / "candidates.jsonl"
    manifest = loads_strict(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "wp9c-function-refresh-stage-v1":
        raise ValueError("OpenCoder stage manifest schema mismatch")
    if manifest.get("candidate_count") != expected_total or manifest.get("quality_safe_ge8_count") != expected_ge8:
        raise ValueError("OpenCoder stage count mismatch")
    records_digest = manifest.get("records_digest")
    if not isinstance(records_digest, str) or _sha(candidates_path) != records_digest:
        raise ValueError("OpenCoder candidate digest mismatch")
    source_config_path = manifest.get("source_config_path")
    source_config_digest = manifest.get("source_config_digest")
    if not isinstance(source_config_path, str) or not isinstance(source_config_digest, str):
        raise ValueError("OpenCoder stage source-config binding is missing")
    if _sha(Path(source_config_path)) != source_config_digest:
        raise ValueError("OpenCoder source config digest drift")

    ready: list[RefreshCandidate] = []
    total = 0
    with candidates_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            total += 1
            row = loads_strict(line)
            if not isinstance(row, dict):
                raise ValueError("OpenCoder staged candidate is not an object")
            tests = row.get("tests")
            category = row.get("category")
            if (
                not isinstance(tests, list)
                or not isinstance(category, list)
                or any(not isinstance(item, str) for item in category)
            ):
                raise ValueError("OpenCoder staged candidate schema mismatch")
            if len(tests) < 8:
                continue
            test_fingerprint = row.get("test_fingerprint")
            if not isinstance(test_fingerprint, str):
                raise ValueError("OpenCoder >=8 candidate lacks test fingerprint")
            ready.append(
                RefreshCandidate(
                    candidate_id=cast(str, row["candidate_id"]),
                    source_name=cast(str, row["source_name"]),
                    source_record_id=cast(str, row["source_record_id"]),
                    prompt=cast(str, row["prompt"]),
                    function_name=cast(str, row["function_name"]),
                    function_signature=cast(str, row["function_signature"]),
                    tests=(),
                    source_url_hash=cast(str | None, row.get("source_url_hash")),
                    raw_reference_solution_hash=cast(str | None, row.get("raw_reference_solution_hash")),
                    difficulty=cast(str, row["difficulty"]),
                    category=tuple(cast(list[str], category)),
                    raw_record_sha256=cast(str, row["raw_record_sha256"]),
                    test_fingerprint=test_fingerprint,
                    test_validation_guard=None,
                )
            )
    if total != expected_total or len(ready) != expected_ge8:
        raise ValueError("OpenCoder staged file count mismatch")
    return ready, {
        "stage_dir": str(stage_dir),
        "stage_manifest_digest": _sha(manifest_path),
        "candidates_digest": records_digest,
        "source_config_path": source_config_path,
        "source_config_digest": source_config_digest,
        "total_candidate_count": total,
        "quality_safe_ge8_count": len(ready),
    }


def _context_stats(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    counts = sorted(cast(int, row["prompt_tokens"]) for row in rows)
    if not counts:
        return {"count": 0}
    p90_index = max(0, math.ceil(0.90 * len(counts)) - 1)
    return {
        "count": len(counts),
        "min": counts[0],
        "mean": statistics.fmean(counts),
        "median": statistics.median(counts),
        "p90": counts[p90_index],
        "max": counts[-1],
    }


def _context_filter(
    candidates: Sequence[RefreshCandidate],
    *,
    tokenizer: object,
    cap: int,
    origin_by_id: Mapping[str, str],
) -> tuple[list[RefreshCandidate], list[dict[str, object]], dict[str, object]]:
    survivors: list[RefreshCandidate] = []
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        rendered = tokenizer.apply_chat_template(  # type: ignore[attr-defined]
            [{"role": "user", "content": candidate.prompt}],
            add_generation_prompt=True,
            tokenize=False,
        )
        encoded = tokenizer(rendered, add_special_tokens=False)  # type: ignore[operator]
        count = len(encoded["input_ids"])
        if count <= 0:
            raise ValueError(f"non-positive prompt token count: {candidate.candidate_id}")
        eligible = count <= cap
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "origin": origin_by_id[candidate.candidate_id],
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "prompt_tokens": count,
                "context_eligible": eligible,
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
            "prompt_tokens": _context_stats(rows),
        },
    )


def _decision_rows(
    decisions: Sequence[RefreshDedupDecision],
    *,
    candidates: Mapping[str, RefreshCandidate],
    origin_by_id: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        candidate = candidates[decision.candidate_id]
        row = cast(dict[str, object], asdict(decision))
        row["origin"] = origin_by_id[decision.candidate_id]
        row["source_name"] = candidate.source_name
        row["source_record_id"] = candidate.source_record_id
        rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    payload = "".join(canonical_json(row) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_formal_references(
    reference_dir: Path,
    *,
    expected_digest: str,
) -> tuple[list[OverlapReference], list[OverlapReference], list[OverlapReference], Path]:
    path = reference_dir / "canonical" / "problems.jsonl"
    if _sha(path) != expected_digest:
        raise ValueError("formal reference canonical digest drift")
    problems = load_canonical_jsonl(path)
    sft_refs = [_reference(problem, "sft") for problem in problems if problem.split == "train"]
    validation_refs = [_reference(problem, "validation") for problem in problems if problem.split == "validation"]
    test_refs = [_reference(problem, "project_test") for problem in problems if problem.split == "test"]
    if (len(sft_refs), len(validation_refs), len(test_refs)) != (2500, 300, 400):
        raise ValueError("formal reference split counts drifted")
    return sft_refs, validation_refs, test_refs, path


def _external_eval_identity(refresh_config: Path) -> tuple[str, str]:
    raw = load_yaml_mapping(refresh_config).get("external_eval")
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("dataset_id"), str)
        or not isinstance(raw.get("revision"), str)
    ):
        raise ValueError("refresh external-eval identity is invalid")
    return cast(str, raw["dataset_id"]), cast(str, raw["revision"])


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    if config.get("version") != "wp9c-function-supply-aggregate-audit-v1":
        raise ValueError("aggregate audit config version mismatch")
    if config.get("required_external_new") != 2775:
        raise ValueError("aggregate audit must freeze external-new requirement at 2775")
    expected = config.get("expected_counts")
    inputs = config.get("inputs")
    dedup = config.get("dedup")
    context_cfg = config.get("context_filter")
    quality = config.get("quality")
    priority = config.get("priority")
    if not all(isinstance(value, dict) for value in (expected, inputs, dedup, context_cfg, quality)):
        raise ValueError("aggregate audit config structure is invalid")
    if priority != ["existing_incumbent", "ready_ge8", "under8_augmentable"]:
        raise ValueError("aggregate candidate priority order drifted")
    expected = cast(dict[str, object], expected)
    inputs = cast(dict[str, object], inputs)
    dedup = cast(dict[str, object], dedup)
    context_cfg = cast(dict[str, object], context_cfg)
    quality = cast(dict[str, object], quality)
    for name in (
        "existing_incumbent",
        "native_ready_structural",
        "opencoder_stage_total",
        "opencoder_ready_ge8",
        "under8_augmentable",
    ):
        value = expected.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"aggregate expected count is invalid: {name}")
    if dedup.get("token_ngram_size") != 5 or dedup.get("near_jaccard_threshold") != 0.90:
        raise ValueError("aggregate dedup policy differs from frozen WP9-a policy")
    if (
        context_cfg.get("policy") != "reuse_existing_incumbent_exact_B_identity"
        or context_cfg.get("max_prompt_tokens") != 2048
    ):
        raise ValueError("aggregate exact-B context policy drifted")
    if any(quality.get(key) is not False for key in ("execute_source_code", "generate_tests", "run_piston")):
        raise ValueError("aggregate audit must remain static-only")
    if quality.get("threshold_relaxation_allowed") is not False:
        raise ValueError("aggregate audit cannot relax quality thresholds")

    incumbent_dir = _resolve_path(inputs.get("existing_incumbent_dir"), base=ROOT)
    incumbents, incumbent_summary, incumbent_binding = _load_existing_incumbents(
        incumbent_dir,
        expected_count=cast(int, expected["existing_incumbent"]),
    )
    primary_context_path = _resolve_path(inputs.get("incumbent_primary_context_report"), base=ROOT)
    lcb_context_path = _resolve_path(inputs.get("incumbent_lcb_context_report"), base=ROOT)
    primary_context = loads_strict(primary_context_path.read_text(encoding="utf-8"))
    lcb_context = loads_strict(lcb_context_path.read_text(encoding="utf-8"))
    if (
        not isinstance(primary_context, dict)
        or primary_context.get("schema_version") != "wp9c-function-refresh-context-v1"
    ):
        raise ValueError("primary incumbent context report schema mismatch")
    if (
        not isinstance(lcb_context, dict)
        or lcb_context.get("schema_version") != "wp9c-function-refresh-lcb-context-v1"
    ):
        raise ValueError("LCB incumbent context report schema mismatch")
    if primary_context.get("context_eligible_count") != 554 or primary_context.get("max_prompt_tokens") != 2048:
        raise ValueError("primary incumbent context report count/policy mismatch")
    if lcb_context.get("context_eligible_count") != 100 or lcb_context.get("max_prompt_tokens") != 2048:
        raise ValueError("LCB incumbent context report count/policy mismatch")
    tokenizer_identity = primary_context.get("tokenizer")
    if not isinstance(tokenizer_identity, dict) or lcb_context.get("tokenizer") != tokenizer_identity:
        raise ValueError("incumbent exact-B tokenizer identities disagree")
    source_inputs = incumbent_summary.get("source_inputs")
    if not isinstance(source_inputs, list) or len(source_inputs) != 2:
        raise ValueError("incumbent bundle source-input bindings are invalid")
    source_input_counts: set[int] = set()
    for binding in source_inputs:
        if not isinstance(binding, dict):
            raise ValueError("incumbent source-input binding is invalid")
        source_path = binding.get("path")
        source_digest = binding.get("digest")
        source_count = binding.get("count")
        if not isinstance(source_path, str) or not isinstance(source_digest, str) or not isinstance(source_count, int):
            raise ValueError("incumbent source-input identity is invalid")
        if _sha(Path(source_path)) != source_digest:
            raise ValueError("incumbent source-input digest drift")
        source_input_counts.add(source_count)
    if source_input_counts != {100, 554}:
        raise ValueError("incumbent source-input counts drifted")
    if primary_context.get("quality_safe_context_digest") not in {
        binding.get("digest") for binding in source_inputs if isinstance(binding, dict)
    }:
        raise ValueError("primary exact-B context artifact is not bound into the incumbent bundle")
    lcb_source_bindings = [
        binding for binding in source_inputs if isinstance(binding, dict) and binding.get("count") == 100
    ]
    if len(lcb_source_bindings) != 1:
        raise ValueError("incumbent bundle must contain exactly one 100-row LCB source binding")
    lcb_source_path = Path(cast(str, lcb_source_bindings[0]["path"]))
    lcb_canonical_summary_path = lcb_source_path.parent.parent / "reports" / "summary.json"
    configured_lcb_canonical_summary_path = _resolve_path(inputs.get("incumbent_lcb_canonical_report"), base=ROOT)
    if configured_lcb_canonical_summary_path != lcb_canonical_summary_path.resolve():
        raise ValueError("configured LCB canonical summary path differs from the incumbent source binding")
    lcb_canonical_summary = loads_strict(lcb_canonical_summary_path.read_text(encoding="utf-8"))
    if (
        not isinstance(lcb_canonical_summary, dict)
        or lcb_canonical_summary.get("schema_version") != "wp9c-function-refresh-lcb-canonical-v1"
        or lcb_canonical_summary.get("records_digest") != lcb_source_bindings[0].get("digest")
        or lcb_canonical_summary.get("context_ids_digest") != lcb_context.get("context_eligible_ids_digest")
        or lcb_canonical_summary.get("source_candidates_digest") != lcb_context.get("source_digest")
    ):
        raise ValueError("LCB exact-B context evidence is not bound into the incumbent bundle")
    incumbent_binding["primary_context_report_path"] = str(primary_context_path)
    incumbent_binding["primary_context_report_digest"] = _sha(primary_context_path)
    incumbent_binding["lcb_context_report_path"] = str(lcb_context_path)
    incumbent_binding["lcb_context_report_digest"] = _sha(lcb_context_path)
    incumbent_binding["lcb_canonical_summary_path"] = str(lcb_canonical_summary_path)
    incumbent_binding["lcb_canonical_summary_digest"] = _sha(lcb_canonical_summary_path)
    model_id = tokenizer_identity.get("model_id")
    revision = tokenizer_identity.get("revision")
    if not isinstance(model_id, str) or not isinstance(revision, str):
        raise ValueError("incumbent tokenizer identity is incomplete")
    formal_b_config_path = ROOT / "configs/sft/main.yaml"
    formal_b_config = load_yaml_mapping(formal_b_config_path)
    if formal_b_config.get("model_id") != model_id or formal_b_config.get("model_revision") != revision:
        raise ValueError("incumbent exact-B tokenizer identity differs from Formal-B SFT config")
    incumbent_binding["formal_b_sft_config_path"] = str(formal_b_config_path)
    incumbent_binding["formal_b_sft_config_digest"] = _sha(formal_b_config_path)
    tokenizer_loader = getattr(AutoTokenizer, "from_" + "pretrained")
    tokenizer = tokenizer_loader(model_id, revision=revision, local_files_only=True)

    incumbent_origins = {candidate.candidate_id: "existing_incumbent" for candidate in incumbents}
    incumbent_context, incumbent_context_rows, incumbent_context_summary = _context_filter(
        incumbents,
        tokenizer=tokenizer,
        cap=2048,
        origin_by_id=incumbent_origins,
    )
    if len(incumbent_context) != len(incumbents):
        raise ValueError("existing incumbent exact-B context recheck lost records")

    native_report_path = _resolve_path(inputs.get("native_ready_report"), base=ROOT)
    native_report, native_report_digest = _verified_report(native_report_path)
    if native_report.get("schema_version") != "wp9c-native-function-supply-audit-v2":
        raise ValueError("native C4 report schema mismatch")
    if native_report.get("formal_eligible") is not False:
        raise ValueError("native C4 report must remain audit-only")
    reference_digest = native_report.get("reference_canonical_sha256")
    if not isinstance(reference_digest, str):
        raise ValueError("native C4 report lacks formal reference digest")
    native_config_path = _resolve_path(inputs.get("native_ready_config"), base=ROOT)
    if native_report.get("source_config_sha256") != _sha(native_config_path):
        raise ValueError("native C4 source-config binding drift")
    native_module = _load_module(NATIVE_AUDIT_SCRIPT, "wp9c_native_aggregate_dependency")
    native_sources = native_module._source_configs(native_config_path)
    _, apps_path = native_module._resolve_source_file(native_sources["apps_train"])
    _, leetcode_path = native_module._resolve_source_file(native_sources["leetcode_merged"])
    apps_candidates, _ = native_module._apps_candidates(apps_path)
    leetcode_candidates, _ = native_module._leetcode_candidates(leetcode_path)
    native_ready = [_light(candidate) for candidate in [*apps_candidates, *leetcode_candidates]]
    if len(native_ready) != cast(int, expected["native_ready_structural"]):
        raise ValueError("reconstructed native ready count mismatch")

    opencoder_stage_dir = _resolve_path(inputs.get("opencoder_stage_dir"), base=ROOT)
    opencoder_ready, opencoder_binding = _load_opencoder_ready(
        opencoder_stage_dir,
        expected_total=cast(int, expected["opencoder_stage_total"]),
        expected_ge8=cast(int, expected["opencoder_ready_ge8"]),
    )

    formal_reference_dir = _resolve_path(inputs.get("formal_reference_dir"), base=ROOT)
    sft_refs, validation_refs, project_test_refs, reference_path = _load_formal_references(
        formal_reference_dir,
        expected_digest=reference_digest,
    )
    refresh_config = _resolve_path(inputs.get("refresh_config"), base=ROOT)
    dataset_id, external_revision = _external_eval_identity(refresh_config)
    external_snapshot, humaneval_refs = load_humanevalplus_references(
        dataset_id=dataset_id,
        revision=external_revision,
        cache_dir=None,
    )
    c4_external = native_report.get("external_eval_snapshot")
    if not isinstance(c4_external, dict) or asdict(external_snapshot) != c4_external:
        raise ValueError("HumanEvalPlus snapshot differs from verified C4 baseline")

    ready_new = [*native_ready, *opencoder_ready]
    if len({candidate.candidate_id for candidate in ready_new}) != len(ready_new):
        raise ValueError("ready-new candidate IDs are not unique")
    incumbent_ids = {candidate.candidate_id for candidate in incumbent_context}
    if {candidate.candidate_id for candidate in ready_new} & incumbent_ids:
        raise ValueError("ready-new IDs collide with incumbent IDs")
    ready_origin: dict[str, str] = {}
    for candidate in native_ready:
        ready_origin[candidate.candidate_id] = (
            "native_apps_ge8" if candidate.source_name == "codeparrot/apps" else "native_leetcode_ge8"
        )
    for candidate in opencoder_ready:
        ready_origin[candidate.candidate_id] = "opencoder_ge8"

    policy = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)
    incumbent_refs = [_candidate_reference(candidate, prefix="incumbent") for candidate in incumbent_context]
    ready_decisions = classify_refresh_candidates(
        ready_new,
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=project_test_refs,
        external_eval_references=[*humaneval_refs, *incumbent_refs],
        policy=policy,
    )
    ready_by_id = {candidate.candidate_id: candidate for candidate in ready_new}
    ready_retained = [ready_by_id[item.candidate_id] for item in ready_decisions if item.retained]
    ready_context, ready_context_rows, ready_context_summary = _context_filter(
        ready_retained,
        tokenizer=tokenizer,
        cap=2048,
        origin_by_id=ready_origin,
    )
    ready_reason_counts = Counter(item.rejection_reason or "retained" for item in ready_decisions)
    ready_incumbent_overlap = sum(
        item.matched_record_id is not None and item.matched_record_id.startswith("incumbent:")
        for item in ready_decisions
        if not item.retained
    )
    print(
        canonical_json(
            {
                "stage": "ready_ge8_completed",
                "incumbent_count": len(incumbent_context),
                "ready_new_raw_count": len(ready_new),
                "ready_new_retained_before_context": len(ready_retained),
                "ready_new_context_eligible": len(ready_context),
                "ready_new_incumbent_overlap_count": ready_incumbent_overlap,
                "rejection_reason_counts": dict(sorted(ready_reason_counts.items())),
                "context": ready_context_summary,
            }
        ),
        flush=True,
    )

    under8_report_path = _resolve_path(inputs.get("under8_report"), base=ROOT)
    under8_report, under8_report_digest = _verified_report(under8_report_path)
    if under8_report.get("schema_version") != "wp9c-apps-under8-augmentability-audit-v1":
        raise ValueError("under8 baseline report schema mismatch")
    if under8_report.get("formal_eligible") is not False:
        raise ValueError("under8 baseline report must remain audit-only")
    if under8_report.get("reference_canonical_sha256") != reference_digest:
        raise ValueError("under8 baseline formal-reference binding differs from native C4")
    if under8_report.get("external_eval_snapshot") != c4_external:
        raise ValueError("under8 baseline HumanEvalPlus binding differs from native C4")
    under8_config_path = _resolve_path(inputs.get("under8_config"), base=ROOT)
    if under8_report.get("source_config_sha256") != _sha(under8_config_path):
        raise ValueError("under8 baseline source-config binding drift")
    under8_module = _load_module(UNDER8_AUDIT_SCRIPT, "wp9c_under8_aggregate_dependency")
    under8_source = under8_module._source_config(under8_config_path)
    _, under8_path = under8_module._resolve_source_file(under8_source)
    under8_candidates_full, _, _ = under8_module._apps_under8_candidates(under8_path)
    under8_candidates = [_light(candidate) for candidate in under8_candidates_full]
    if len(under8_candidates) != cast(int, expected["under8_augmentable"]):
        raise ValueError("reconstructed under8 count mismatch")

    all_ready = [*incumbent_context, *ready_context]
    all_ready_refs = [_candidate_reference(candidate, prefix="ready") for candidate in all_ready]
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
    under8_context, under8_context_rows, under8_context_summary = _context_filter(
        under8_retained,
        tokenizer=tokenizer,
        cap=2048,
        origin_by_id=under8_origin,
    )
    under8_reason_counts = Counter(item.rejection_reason or "retained" for item in under8_decisions)
    under8_ready_overlap = sum(
        item.matched_record_id is not None and item.matched_record_id.startswith("ready:")
        for item in under8_decisions
        if not item.retained
    )
    under8_context_ids = {candidate.candidate_id for candidate in under8_context}
    added_test_slots = sum(
        8 - len(candidate.tests)
        for candidate in under8_candidates_full
        if candidate.candidate_id in under8_context_ids
    )
    under8_test_hist = Counter(
        len(candidate.tests) for candidate in under8_candidates_full if candidate.candidate_id in under8_context_ids
    )
    print(
        canonical_json(
            {
                "stage": "under8_completed",
                "under8_raw_count": len(under8_candidates),
                "under8_retained_before_context": len(under8_retained),
                "under8_context_eligible": len(under8_context),
                "under8_ready_overlap_count": under8_ready_overlap,
                "minimum_added_test_slots_to_reach_8": added_test_slots,
                "retained_existing_test_count_histogram": {
                    str(key): value for key, value in sorted(under8_test_hist.items())
                },
                "rejection_reason_counts": dict(sorted(under8_reason_counts.items())),
                "context": under8_context_summary,
            }
        ),
        flush=True,
    )

    ready_total = len(all_ready)
    augmentable_total = len(under8_context)
    zero_attrition_total = ready_total + augmentable_total
    required_external_new = 2775
    gap = max(0, required_external_new - zero_attrition_total)
    ready_source_counts = Counter(["existing_incumbent"] * len(incumbent_context))
    ready_source_counts.update(ready_origin[candidate.candidate_id] for candidate in ready_context)
    aggregate_summary = {
        "ready_context_eligible_count": ready_total,
        "augmentable_context_eligible_count": augmentable_total,
        "zero_attrition_potential_count": zero_attrition_total,
        "remaining_gap_zero_attrition": gap,
        "ready_source_counts": dict(sorted(ready_source_counts.items())),
        "minimum_added_test_slots_to_reach_8": added_test_slots,
    }
    print(canonical_json({"stage": "aggregate_completed", **aggregate_summary}), flush=True)

    ready_decision_rows = _decision_rows(ready_decisions, candidates=ready_by_id, origin_by_id=ready_origin)
    under8_decision_rows = _decision_rows(under8_decisions, candidates=under8_by_id, origin_by_id=under8_origin)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        artifacts = {
            "ready_decisions": _write_jsonl(temporary / "decisions" / "ready_new.jsonl", ready_decision_rows),
            "under8_decisions": _write_jsonl(temporary / "decisions" / "under8.jsonl", under8_decision_rows),
            "incumbent_context": _write_jsonl(temporary / "context" / "incumbent.jsonl", incumbent_context_rows),
            "ready_context": _write_jsonl(temporary / "context" / "ready_new.jsonl", ready_context_rows),
            "under8_context": _write_jsonl(temporary / "context" / "under8.jsonl", under8_context_rows),
        }
        report: dict[str, object] = {
            "schema_version": "wp9c-function-supply-aggregate-audit-v1",
            "evidence_class": "engineering_data_audit_only",
            "formal_eligible": False,
            "formal_blockers": [
                "ready_source_specific_reference_solution_transformation_not_frozen",
                "project_piston_reference_solution_validation_not_run",
                "under8_test_augmentation_protocol_not_frozen",
                "under8_augmented_tests_not_generated",
                "under8_multi_solution_consensus_not_run",
                "ready_candidates_not_materialized_as_formal_pool",
            ],
            "config_path": str(config_path),
            "config_digest": _sha(config_path),
            "dependency_script_digests": {
                "aggregate_audit": _sha(Path(__file__)),
                "native_audit": _sha(NATIVE_AUDIT_SCRIPT),
                "under8_audit": _sha(UNDER8_AUDIT_SCRIPT),
            },
            "existing_incumbent": {
                **incumbent_binding,
                "summary_records_digest": incumbent_summary.get("records_digest"),
                "primary_context_report": {
                    "path": str(primary_context_path),
                    "digest": _sha(primary_context_path),
                },
                "lcb_context_report": {
                    "path": str(lcb_context_path),
                    "digest": _sha(lcb_context_path),
                },
                "context_recheck": incumbent_context_summary,
            },
            "native_baseline_report": {
                "path": str(native_report_path),
                "digest": native_report_digest,
                "raw_structural_candidate_count": native_report.get("raw_structural_candidate_count"),
            },
            "opencoder_stage": opencoder_binding,
            "under8_baseline_report": {
                "path": str(under8_report_path),
                "digest": under8_report_digest,
                "raw_augmentable_candidate_count": under8_report.get("raw_augmentable_candidate_count"),
            },
            "formal_references": {
                "canonical_path": str(reference_path),
                "canonical_digest": reference_digest,
                "counts": {
                    "sft": len(sft_refs),
                    "validation": len(validation_refs),
                    "project_test": len(project_test_refs),
                    "humanevalplus": len(humaneval_refs),
                },
                "external_eval_snapshot": asdict(external_snapshot),
            },
            "context_filter": {
                "policy": "chat_template_prompt_cap_v1",
                "max_prompt_tokens": 2048,
                "tokenizer_model_id": model_id,
                "tokenizer_revision": revision,
            },
            "ready_new": {
                "raw_count": len(ready_new),
                "retained_before_context": len(ready_retained),
                "context_eligible_count": len(ready_context),
                "incumbent_overlap_count": ready_incumbent_overlap,
                "rejection_reason_counts": dict(sorted(ready_reason_counts.items())),
                "context": ready_context_summary,
            },
            "under8_augmentable": {
                "raw_count": len(under8_candidates),
                "retained_before_context": len(under8_retained),
                "context_eligible_count": len(under8_context),
                "ready_overlap_count": under8_ready_overlap,
                "rejection_reason_counts": dict(sorted(under8_reason_counts.items())),
                "context": under8_context_summary,
                "retained_existing_test_count_histogram": {
                    str(key): value for key, value in sorted(under8_test_hist.items())
                },
                "minimum_added_test_slots_to_reach_8": added_test_slots,
            },
            "aggregate_supply": aggregate_summary,
            "artifact_digests": artifacts,
            "notes": [
                "No candidate solution/test payload is executed and no tests are generated.",
                "Existing >=8-test context-qualified incumbents are preserved before considering new ready supply.",
                (
                    "New >=8-test native/OpenCoder candidates are deduplicated against formal references and "
                    "incumbents before exact-B context filtering."
                ),
                (
                    "Under8 APPS candidates are considered only after ready context survivors, so augmentable "
                    "tasks never displace already-ready tasks."
                ),
                (
                    "The zero-attrition potential assumes every surviving under8 candidate is later augmented "
                    "to >=8 unique tests and passes all future Piston gates."
                ),
            ],
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(
            hashlib.sha256(payload.encode("utf-8")).hexdigest() + "\n",
            encoding="ascii",
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
    print(canonical_json(report))


if __name__ == "__main__":
    main()
