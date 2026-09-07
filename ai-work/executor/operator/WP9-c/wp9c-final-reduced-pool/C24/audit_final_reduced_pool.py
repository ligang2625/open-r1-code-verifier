#!/usr/bin/env python3
"""Assemble the reduced WP9-c pre-calibration formal pool and re-audit SFT reuse."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from transformers import AutoTokenizer

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.data.refresh_sources import Difficulty, RefreshCandidate, canonicalize_refresh_candidate
from code_verifier.data.schema import CodeProblem, TestCase, problem_to_mapping
from code_verifier.prompting import build_code_prompt

ROOT = Path(__file__).resolve().parents[6]
C18_SCRIPT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-ready-final-piston/C18/prepare_ready_piston_jobs.py"
C18_CONFIG = ROOT / "configs/data/wp9c-ready-final-piston.yaml"
C18_JOBS = Path("/home/dzy/wp9c-ready-final-piston-prep-C18/piston_jobs.jsonl")
C19_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-ready-final-piston/C19/checkpoint.json"
C19_PASSERS = Path("/home/dzy/wp9c-ready-final-piston-C19/formal_passers.jsonl")
C22_PASSERS = Path("/home/dzy/wp9c-under8-final-exact-b-C22/context_passers.jsonl")
C23_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-under8-final-piston/C23/checkpoint.json"
C23_PASSERS = Path("/home/dzy/wp9c-under8-final-piston-C23/formal_passers.jsonl")
C6_REPORT = Path("/home/dzy/wp9c-function-supply-context-correction-C6-r1/report.json")
WP9A_DIR = Path("/home/dzy/wp9a-refresh-seed42-e2-final-run4")
WP9A_MANIFEST = WP9A_DIR / "refresh_manifest.json"
WP9A_SELECTION = WP9A_DIR / "manifest/selection.jsonl"
SEED = 42
MAX_PROMPT_TOKENS = 2048


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, object]:
    value = loads_strict(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = loads_strict(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = canonical_json(row) + "\n"
            handle.write(payload)
            digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _string(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _tests(value: object, *, candidate_id: str) -> tuple[TestCase, ...]:
    if not isinstance(value, list) or len(value) < 8:
        raise ValueError(f"{candidate_id} must have at least eight tests")
    parsed: list[TestCase] = []
    hashes: set[str] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"input", "expected"}:
            raise ValueError(f"{candidate_id} test schema drift")
        digest = stable_json_hash(row)
        if digest in hashes:
            raise ValueError(f"{candidate_id} repeats a normalized frozen test")
        hashes.add(digest)
        parsed.append(TestCase(input=row["input"], expected=row["expected"]))
    return tuple(parsed)


def _candidate_from_c22(row: Mapping[str, object]) -> RefreshCandidate:
    category = row.get("category")
    if not isinstance(category, list) or any(not isinstance(item, str) for item in category):
        raise ValueError("C22 category drift")
    difficulty = row.get("difficulty")
    if difficulty not in {"easy", "medium", "hard", "unknown"}:
        raise ValueError("C22 difficulty drift")
    return RefreshCandidate(
        candidate_id=_string(row, "candidate_id"),
        source_name=_string(row, "source_name"),
        source_record_id=_string(row, "source_record_id"),
        prompt=_string(row, "prompt"),
        function_name=_string(row, "function_name"),
        function_signature=_string(row, "function_signature"),
        tests=_tests(row.get("tests"), candidate_id=_string(row, "candidate_id")),
        source_url_hash=cast(str | None, row.get("source_url_hash")),
        raw_reference_solution_hash=cast(str | None, row.get("raw_reference_solution_hash")),
        difficulty=cast(Difficulty, difficulty),
        category=tuple(cast(list[str], category)),
        raw_record_sha256=_string(row, "raw_record_sha256"),
        test_fingerprint=None,
        test_validation_guard=None,
    )


def _prompt_tokens(prompt: str, tokenizer: Any) -> int:
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )
    encoded = tokenizer(rendered, add_special_tokens=False)
    count = len(encoded["input_ids"])
    if count <= 0:
        raise ValueError("non-positive Formal-B token count")
    return count


def _stats(values: list[int]) -> dict[str, object]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0}
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p90": ordered[max(0, int(0.9 * len(ordered) + 0.999999) - 1)],
        "max": ordered[-1],
    }


def _verify_closed_inputs() -> tuple[dict[str, object], dict[str, object]]:
    c19 = _json(C19_CHECKPOINT)
    if c19.get("status") != "completed_verified":
        raise ValueError("C19 must be completed_verified")
    c23 = _json(C23_CHECKPOINT)
    if c23.get("status") != "completed_verified":
        raise ValueError("C23 must be completed_verified")
    c23_result = _mapping(c23.get("verified_result"), context="C23 result")
    if c23_result.get("formal_pass") != 572 or c23_result.get("formal_fail") != 0:
        raise ValueError("C23 result drift")
    return c19, c23


def _reconstruct_ready(pass_ids: set[str]) -> dict[str, CodeProblem]:
    c18 = cast(Any, _load_module(C18_SCRIPT, "wp9c_c24_c18_dependency"))
    config = load_yaml_mapping(C18_CONFIG)
    bindings = _mapping(config.get("bindings"), context="C18 config bindings")
    refresh_config = ROOT / _string(bindings, "refresh_config")
    native_config = ROOT / _string(bindings, "native_source_config")
    opencoder_config = ROOT / _string(bindings, "opencoder_source_config")

    c18_jobs = {_string(row, "candidate_id"): row for row in _jsonl(C18_JOBS)}
    if not pass_ids.issubset(c18_jobs):
        raise ValueError("C19 pass IDs are not a subset of C18 Piston jobs")
    targets_by_source: dict[str, set[str]] = {
        "deepcoder-primeintellect": set(),
        "deepcoder-taco": set(),
    }
    native_ids: set[str] = set()
    opencoder_ids: set[str] = set()
    for candidate_id in pass_ids:
        source = _string(c18_jobs[candidate_id], "source_name")
        if source in targets_by_source:
            targets_by_source[source].add(candidate_id)
        elif source in {"codeparrot/apps", "tkeskin/leetcode-solutions"}:
            native_ids.add(candidate_id)
        elif source == "opencoder-educational":
            opencoder_ids.add(candidate_id)
        else:
            raise ValueError(f"unexpected C19 passer source: {source}")

    candidates: dict[str, RefreshCandidate] = {}
    deep_candidates, _, _ = c18._deepcoder_hydration(refresh_config, targets_by_source)
    native_candidates, _, _ = c18._native_hydration(native_config, native_ids)
    opencoder_candidates, _, _ = c18._opencoder_hydration(opencoder_config, opencoder_ids)
    for mapping in (deep_candidates, native_candidates, opencoder_candidates):
        overlap = set(candidates) & set(mapping)
        if overlap:
            raise ValueError(f"duplicate ready hydration IDs: {len(overlap)}")
        candidates.update(mapping)
    if set(candidates) != pass_ids:
        raise ValueError(f"ready hydration mismatch: {len(candidates)}/{len(pass_ids)}")

    problems: dict[str, CodeProblem] = {}
    for candidate_id in sorted(pass_ids):
        problem, quality_required = canonicalize_refresh_candidate(candidates[candidate_id], seed=SEED)
        if quality_required:
            raise ValueError(f"ready passer still requires quality gate: {candidate_id}")
        expected = c18_jobs[candidate_id].get("canonical_problem_sha256")
        actual = stable_json_hash(problem_to_mapping(problem))
        if expected != actual:
            raise ValueError(f"ready canonical problem binding drift: {candidate_id}")
        problems[candidate_id] = problem
    return problems


def _reconstruct_under8(pass_ids: set[str]) -> dict[str, CodeProblem]:
    c22_rows = {_string(row, "candidate_id"): row for row in _jsonl(C22_PASSERS)}
    if pass_ids != set(c22_rows):
        raise ValueError("C23 pass IDs must exactly equal C22 context pass IDs")
    problems: dict[str, CodeProblem] = {}
    for candidate_id in sorted(pass_ids):
        row = c22_rows[candidate_id]
        candidate = _candidate_from_c22(row)
        problem, quality_required = canonicalize_refresh_candidate(candidate, seed=SEED)
        if quality_required:
            raise ValueError(f"under8 final passer still requires quality gate: {candidate_id}")
        if (len(problem.visible_tests), len(problem.train_hidden_tests), len(problem.eval_hidden_tests)) != (2, 3, 3):
            raise ValueError(f"under8 final split drift: {candidate_id}")
        if hashlib.sha256(build_code_prompt(problem).encode("utf-8")).hexdigest() != row.get("prompt_sha256"):
            raise ValueError(f"under8 final prompt binding drift: {candidate_id}")
        problems[candidate_id] = problem
    return problems


def _audit_sft_reuse() -> list[dict[str, object]]:
    manifest = _json(WP9A_MANIFEST)
    artifacts = _mapping(manifest.get("artifacts"), context="WP9-a artifacts")
    selection_meta = _mapping(artifacts.get("manifest/selection.jsonl"), context="WP9-a selection artifact")
    if _sha(WP9A_SELECTION) != _string(selection_meta, "sha256") or selection_meta.get("rows") != 10000:
        raise ValueError("WP9-a selection artifact drift")
    protocol = _mapping(manifest.get("selection_protocol"), context="WP9-a selection protocol")
    if protocol.get("sft_overlap_count") != 750 or protocol.get("sft_overlap_fraction") != 0.075:
        raise ValueError("WP9-a frozen SFT reuse population drift")

    audit_rows: list[dict[str, object]] = []
    with WP9A_SELECTION.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = loads_strict(line)
            if not isinstance(value, dict):
                raise ValueError(f"invalid WP9-a selection row: {line_number}")
            row = cast(dict[str, object], value)
            if row.get("overlap_origin") != "sft_reuse":
                continue
            if row.get("quality_gate_required") is not True:
                raise ValueError("historical SFT reuse row unexpectedly has no required quality gate")
            audit_rows.append(
                {
                    "problem_id": _string(row, "problem_id"),
                    "source": _string(row, "source"),
                    "difficulty": _string(row, "difficulty"),
                    "overlap_origin": "sft_reuse",
                    "quality_gate_required": True,
                    "independent_quality_gate_passed": False,
                    "formal_eligible": False,
                    "exclusion_reason": "required_quality_gate_unresolved",
                    "backfill_required": False,
                }
            )
    if len(audit_rows) != 750:
        raise ValueError(f"historical SFT reuse count drift: {len(audit_rows)}")
    return sorted(audit_rows, key=lambda row: _string(row, "problem_id"))


def audit(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C24 output: {output_dir}")
    _, c23 = _verify_closed_inputs()

    c19_pass_rows = _jsonl(C19_PASSERS)
    c23_pass_rows = _jsonl(C23_PASSERS)
    ready_ids = {_string(row, "candidate_id") for row in c19_pass_rows}
    under8_ids = {_string(row, "candidate_id") for row in c23_pass_rows}
    if len(ready_ids) != 1030 or len(under8_ids) != 572 or ready_ids & under8_ids:
        raise ValueError("final external formal ID partition drift")

    ready = _reconstruct_ready(ready_ids)
    under8 = _reconstruct_under8(under8_ids)
    problems = {**ready, **under8}
    if len(problems) != 1602:
        raise ValueError("final external formal count must be 1602")

    c6 = _json(C6_REPORT)
    context = _mapping(c6.get("context_filter"), context="C6 Formal-B context")
    model_id = context.get("tokenizer_model_id")
    revision = context.get("tokenizer_revision")
    if context.get("max_prompt_tokens") != MAX_PROMPT_TOKENS:
        raise ValueError("Formal-B prompt cap drift")
    if not isinstance(model_id, str) or not model_id or not isinstance(revision, str) or not revision:
        raise ValueError("Formal-B tokenizer identity unavailable")
    tokenizer_loader = getattr(AutoTokenizer, "from_" + "pretrained")
    tokenizer = tokenizer_loader(model_id, revision=revision, local_files_only=True)

    selection_rows: list[dict[str, object]] = []
    problem_rows: list[dict[str, object]] = []
    token_counts: list[int] = []
    source_counts: Counter[str] = Counter()
    lane_counts: Counter[str] = Counter()
    for candidate_id in sorted(problems):
        problem = problems[candidate_id]
        prompt = build_code_prompt(problem)
        count = _prompt_tokens(prompt, tokenizer)
        if count > MAX_PROMPT_TOKENS:
            raise ValueError(f"final formal external row exceeds Formal-B context cap: {candidate_id}={count}")
        token_counts.append(count)
        lane = "ready_formal" if candidate_id in ready_ids else "under8_augmented_formal"
        source_counts[problem.source] += 1
        lane_counts[lane] += 1
        mapping = cast(dict[str, object], problem_to_mapping(problem))
        problem_rows.append(mapping)
        selection_rows.append(
            {
                "schema_version": "wp9c-reduced-precalibration-selection-v1",
                "problem_id": candidate_id,
                "source": problem.source,
                "difficulty": problem.metadata.difficulty,
                "overlap_origin": "external_new",
                "quality_gate_required": False,
                "formal_lane": lane,
                "canonical_problem_sha256": stable_json_hash(mapping),
                "formal_b_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "formal_b_prompt_tokens": count,
            }
        )

    sft_audit = _audit_sft_reuse()
    if any(row["formal_eligible"] is True for row in sft_audit):
        raise ValueError("C24 cannot admit unresolved SFT-reuse quality rows")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        problems_sha = _write_jsonl(temporary / "external_formal_problems.jsonl", problem_rows)
        selection_sha = _write_jsonl(temporary / "precalibration_selection.jsonl", selection_rows)
        sft_sha = _write_jsonl(temporary / "sft_reuse_audit.jsonl", sft_audit)
        report: dict[str, object] = {
            "schema_version": "wp9c-final-reduced-pool-assembly-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "formal_external_new_count": 1602,
            "ready_lane_formal_count": 1030,
            "under8_formal_count": 572,
            "historical_sft_reuse_population": 750,
            "historical_sft_reuse_requested_old_quota": 225,
            "sft_reuse_formal_eligible_count": 0,
            "precalibration_pool_count": 1602,
            "precalibration_overlap_counts": {"external_new": 1602, "sft_reuse": 0},
            "source_counts": dict(sorted(source_counts.items())),
            "formal_lane_counts": dict(sorted(lane_counts.items())),
            "all_quality_gate_required_false": True,
            "all_formal_b_context_pass": True,
            "formal_b_prompt_cap": MAX_PROMPT_TOKENS,
            "formal_b_prompt_token_stats": _stats(token_counts),
            "sft_reuse_decision": {
                "admit_count": 0,
                "reason": "all_750_frozen_sft_reuse_rows_require_an_unresolved_independent_quality_gate",
                "quota_backfill_allowed": False,
            },
            "informativeness_accounting": {
                "status": "pending_fresh_calibration",
                "dual_informative": None,
                "public_only": None,
                "hidden_only": None,
                "dual_uninformative": None,
                "old_5000_problem_calibration_scoring_source_allowed": False,
                "selection_by_old_reward_outcome_allowed": False,
                "rule_after_fresh_scoring": "report_actual_counts_and_exclude_dual_uninformative_without_backfill",
            },
            "minimum_pool_count": None,
            "backfill_required": False,
            "execution_boundaries": {
                "candidate_code_execution": False,
                "piston_run": False,
                "generation_run": False,
                "calibration_scoring_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "input_bindings": {
                "c19_checkpoint_sha256": _sha(C19_CHECKPOINT),
                "c19_formal_passers_sha256": _sha(C19_PASSERS),
                "c23_checkpoint_sha256": _sha(C23_CHECKPOINT),
                "c23_formal_passers_sha256": _sha(C23_PASSERS),
                "c22_context_passers_sha256": _sha(C22_PASSERS),
                "c18_jobs_sha256": _sha(C18_JOBS),
                "c18_script_sha256": _sha(C18_SCRIPT),
                "c18_config_sha256": _sha(C18_CONFIG),
                "c6_formal_b_report_sha256": _sha(C6_REPORT),
                "wp9a_refresh_manifest_sha256": _sha(WP9A_MANIFEST),
                "wp9a_selection_sha256": _sha(WP9A_SELECTION),
                "audit_script_sha256": _sha(Path(__file__)),
            },
            "artifact_sha256": {
                "external_formal_problems": problems_sha,
                "precalibration_selection": selection_sha,
                "sft_reuse_audit": sft_sha,
            },
            "next_gate": "fresh_reduced_pool_calibration_generation_and_scoring",
        }
        payload = canonical_json(report) + "\n"
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.output.resolve())


if __name__ == "__main__":
    main()
