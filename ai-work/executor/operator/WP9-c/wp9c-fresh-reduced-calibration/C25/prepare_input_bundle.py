#!/usr/bin/env python3
"""Prepare the fresh reduced-pool calibration input bundle from closed C24 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from transformers import AutoTokenizer

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.data.schema import problem_from_mapping
from code_verifier.prompting import build_code_prompt
from code_verifier.training.calibration import CALIBRATION_SCHEMA_VERSION, _load_input_bundle

ROOT = Path(__file__).resolve().parents[6]
C24_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-final-reduced-pool/C24/checkpoint.json"
C6_REPORT = Path("/home/dzy/wp9c-function-supply-context-correction-C6-r1/report.json")
SEED = 42
EXPECTED_COUNT = 1602
MAX_PROMPT_TOKENS = 2048
MAX_NEW_TOKENS = 512


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


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _string(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = canonical_json(row) + "\n"
            handle.write(payload)
            digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def _prompt_tokens(prompt: str, tokenizer: Any) -> int:
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )
    encoded = tokenizer(rendered, add_special_tokens=False)
    count = len(encoded["input_ids"])
    if count <= 0:
        raise ValueError("non-positive prompt token count")
    return count


def prepare(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C25 input bundle: {output_dir}")

    c24 = _json(C24_CHECKPOINT)
    if c24.get("status") != "completed_verified":
        raise ValueError("C24 must be completed_verified")
    result = _mapping(c24.get("verified_result"), context="C24 verified_result")
    if result.get("external_new_formal_total") != EXPECTED_COUNT or result.get("sft_reuse_formal_eligible") != 0:
        raise ValueError("C24 reduced-pool count drift")
    artifacts = _mapping(c24.get("verified_artifacts"), context="C24 verified_artifacts")
    problems_path = Path(_string(artifacts, "external_formal_problems"))
    expected_problems_sha = _string(artifacts, "external_formal_problems_sha256")
    if _sha(problems_path) != expected_problems_sha:
        raise ValueError("C24 external formal problems digest drift")

    c6 = _json(C6_REPORT)
    context = _mapping(c6.get("context_filter"), context="C6 context_filter")
    model_id = context.get("tokenizer_model_id")
    revision = context.get("tokenizer_revision")
    if not isinstance(model_id, str) or not model_id or not isinstance(revision, str) or not revision:
        raise ValueError("Formal-B tokenizer identity unavailable")
    if context.get("max_prompt_tokens") != MAX_PROMPT_TOKENS:
        raise ValueError("Formal-B prompt cap drift")
    loader = getattr(AutoTokenizer, "from_" + "pretrained")
    tokenizer = loader(model_id, revision=revision, local_files_only=True)

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    token_counts: list[int] = []
    with problems_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = loads_strict(line)
            problem = problem_from_mapping(value)
            if problem.problem_id in seen:
                raise ValueError(f"duplicate problem_id at line {line_number}")
            seen.add(problem.problem_id)
            total_tests = len(problem.visible_tests) + len(problem.train_hidden_tests) + len(problem.eval_hidden_tests)
            if total_tests < 8:
                raise ValueError(f"formal row has fewer than eight tests: {problem.problem_id}")
            prompt = build_code_prompt(problem)
            count = _prompt_tokens(prompt, tokenizer)
            if count > MAX_PROMPT_TOKENS:
                raise ValueError(f"Formal-B context overflow: {problem.problem_id}={count}")
            token_counts.append(count)
            rows.append(
                {
                    "problem_id": problem.problem_id,
                    "prompt": prompt,
                    "function_name": problem.function_name,
                    "source_name": problem.source,
                    "difficulty": problem.metadata.difficulty,
                    "overlap_origin": "external_new",
                    "quality_gate_required": False,
                }
            )
    if len(rows) != EXPECTED_COUNT:
        raise ValueError(f"C25 input count mismatch: {len(rows)}/{EXPECTED_COUNT}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records_sha = _write_jsonl(temporary / "inputs.jsonl", rows)
        empty_context_sha = _write_jsonl(temporary / "excluded_context.jsonl", [])
        empty_quality_sha = _write_jsonl(temporary / "excluded_quality.jsonl", [])
        manifest: dict[str, object] = {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "seed": SEED,
            "record_count": EXPECTED_COUNT,
            "records_sha256": records_sha,
            "problem_order_sha256": stable_json_hash([row["problem_id"] for row in rows]),
            "evidence_class": "formal_input",
            "source_authority": {
                "protocol": "wp9c-reduced-quota-current-viable-v1",
                "c24_checkpoint_sha256": _sha(C24_CHECKPOINT),
                "c24_external_formal_problems_sha256": expected_problems_sha,
                "all_rows_external_new": True,
                "sft_reuse_count": 0,
            },
            "context_filter": {
                "policy": "chat_template_prompt_cap_v1",
                "tokenizer_model_id": model_id,
                "tokenizer_model_revision": revision,
                "max_prompt_tokens": MAX_PROMPT_TOKENS,
                "max_new_tokens": MAX_NEW_TOKENS,
                "source_record_count": EXPECTED_COUNT,
                "eligible_record_count": EXPECTED_COUNT,
                "excluded_record_count": 0,
                "excluded_records_sha256": empty_context_sha,
            },
            "candidate_filter": {
                "policy": "quality_safe_stratified_tranche_v1",
                "exclude_quality_gate_required": True,
                "maximum_records": None,
                "context_eligible_record_count": EXPECTED_COUNT,
                "quality_eligible_record_count": EXPECTED_COUNT,
                "quality_excluded_record_count": 0,
                "quality_excluded_records_sha256": empty_quality_sha,
                "selected_record_count": EXPECTED_COUNT,
                "tranche_reserve_record_count": 0,
                "tranche_reserve_records_sha256": None,
            },
        }
        _write_json(temporary / "input_manifest.json", manifest)
        loaded_manifest, loaded_rows = _load_input_bundle(temporary)
        if len(loaded_rows) != EXPECTED_COUNT or loaded_manifest.get("records_sha256") != records_sha:
            raise ValueError("strict calibration input readback mismatch")
        report: dict[str, object] = {
            "schema_version": "wp9c-fresh-reduced-calibration-input-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "record_count": EXPECTED_COUNT,
            "overlap_counts": {"external_new": EXPECTED_COUNT, "sft_reuse": 0},
            "all_quality_gate_required_false": True,
            "all_formal_b_context_pass": True,
            "max_prompt_tokens": max(token_counts),
            "formal_b_cap": MAX_PROMPT_TOKENS,
            "input_manifest_sha256": _sha(temporary / "input_manifest.json"),
            "inputs_sha256": records_sha,
            "excluded_context_sha256": empty_context_sha,
            "excluded_quality_sha256": empty_quality_sha,
            "c24_checkpoint_sha256": _sha(C24_CHECKPOINT),
            "c24_external_formal_problems_sha256": expected_problems_sha,
            "preparation_script_sha256": _sha(Path(__file__)),
            "execution_boundaries": {
                "generation_run": False,
                "candidate_code_execution": False,
                "piston_run": False,
                "gpu_run": False,
            },
        }
        _write_json(temporary / "report.json", report)
        report_sha = _sha(temporary / "report.json")
        (temporary / "report.sha256").write_text(report_sha + "\n", encoding="ascii")
        temporary.rename(output_dir)
        print(json.dumps(report, sort_keys=True))
        return report
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output.resolve())


if __name__ == "__main__":
    main()
