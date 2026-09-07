#!/usr/bin/env python3
"""Run the final post-augmentation Exact-B context audit for C21 exact-8 survivors."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
import re
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from transformers import AutoTokenizer

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.data.refresh_sources import Difficulty, RefreshCandidate, canonicalize_refresh_candidate
from code_verifier.data.schema import TestCase
from code_verifier.prompting import build_code_prompt

ROOT = Path(__file__).resolve().parents[6]
C21_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-under8-proposal-consensus/C21/checkpoint.json"
C6_REPORT = Path("/home/dzy/wp9c-function-supply-context-correction-C6-r1/report.json")
C7_REPORT = Path("/home/dzy/wp9c-taco-under8-supply-audit-C7/report.json")
C7_CANDIDATES = C7_REPORT.parent / "taco_under8_candidates.jsonl"
C8_REPORT = Path("/home/dzy/wp9c-deepcoder-function-supply-audit-C8/report.json")
C8_CANDIDATES = C8_REPORT.parent / "deepcoder_under8_candidates.jsonl"
APPS_REPORT = Path("/home/dzy/wp9c-apps-under8-augmentability-audit-C0/report.json")
APPS_CONFIG = ROOT / "configs/data/wp9c-apps-under8-augmentability-audit.yaml"
APPS_AUDIT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_apps_under8_augmentable.py"
)
APPS_RUNNER = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/16-audit-apps-under8-augmentable.sh"
)
MAX_PROMPT_TOKENS = 2048
SEED = 42


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


def _verify_report_sidecar(path: Path, schema: str) -> dict[str, object]:
    sidecar = path.with_name("report.sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError(f"missing report/sidecar: {path}")
    actual = _sha(path)
    if sidecar.read_text(encoding="ascii").strip() != actual:
        raise ValueError(f"report sidecar mismatch: {path}")
    report = _json(path)
    if report.get("schema_version") != schema:
        raise ValueError(f"report schema mismatch: {path}")
    return report


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _historical_apps_hashes() -> tuple[str, str]:
    text = APPS_RUNNER.read_text(encoding="utf-8")
    config = re.search(r'^SOURCE_CONFIG_SHA256="([0-9a-f]{64})"$', text, flags=re.MULTILINE)
    script = re.search(r'^AUDIT_SCRIPT_SHA256="([0-9a-f]{64})"$', text, flags=re.MULTILINE)
    if config is None or script is None:
        raise ValueError("historical APPS runner no longer exposes frozen config/script digests")
    return config.group(1), script.group(1)


def _tests(value: object, *, candidate_id: str) -> tuple[TestCase, ...]:
    if not isinstance(value, list) or len(value) != 8:
        raise ValueError(f"{candidate_id} final tests must contain exactly eight rows")
    parsed: list[TestCase] = []
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"input", "expected"}:
            raise ValueError(f"{candidate_id} final test schema drift")
        digest = stable_json_hash(row)
        if digest in seen:
            raise ValueError(f"{candidate_id} final tests are not unique")
        seen.add(digest)
        parsed.append(TestCase(input=row["input"], expected=row["expected"]))
    return tuple(parsed)


def _candidate_from_row(row: Mapping[str, object], *, final_tests: tuple[TestCase, ...]) -> RefreshCandidate:
    category = row.get("category")
    if not isinstance(category, list) or any(not isinstance(value, str) for value in category):
        raise ValueError("candidate category drift")
    difficulty = row.get("difficulty")
    if difficulty not in {"easy", "medium", "hard", "unknown"}:
        raise ValueError("candidate difficulty drift")
    return RefreshCandidate(
        candidate_id=_string(row, "candidate_id"),
        source_name=_string(row, "source_name"),
        source_record_id=_string(row, "source_record_id"),
        prompt=_string(row, "prompt"),
        function_name=_string(row, "function_name"),
        function_signature=_string(row, "function_signature"),
        tests=final_tests,
        source_url_hash=cast(str | None, row.get("source_url_hash")),
        raw_reference_solution_hash=cast(str | None, row.get("raw_reference_solution_hash")),
        difficulty=cast(Difficulty, difficulty),
        category=tuple(cast(list[str], category)),
        raw_record_sha256=_string(row, "raw_record_sha256"),
        test_fingerprint=cast(str | None, row.get("test_fingerprint")),
        test_validation_guard=None,
    )


def _prompt_token_count(prompt: str, tokenizer: Any) -> int:
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )
    encoded = tokenizer(rendered, add_special_tokens=False)
    count = len(encoded["input_ids"])
    if count <= 0:
        raise ValueError("non-positive Formal-B prompt token count")
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
        "p90": ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)],
        "max": ordered[-1],
    }


def audit(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C22 output: {output_dir}")

    c21 = _json(C21_CHECKPOINT)
    if c21.get("status") != "completed_verified" or c21.get("next_gate") != "C22-under8-final-exact-b-context":
        raise ValueError("C21 prerequisite is not closed for C22")
    verified = _mapping(c21.get("verified_artifacts"), context="C21 verified artifacts")
    frozen_path = Path(_string(verified, "frozen_exact8"))
    if _sha(frozen_path) != _string(verified, "frozen_exact8_sha256"):
        raise ValueError("C21 frozen exact8 digest drift")
    frozen_rows = _jsonl(frozen_path)
    if len(frozen_rows) != 572:
        raise ValueError("C22 expected exactly 572 C21 survivors")
    frozen_by_id = {_string(row, "candidate_id"): row for row in frozen_rows}
    if len(frozen_by_id) != 572:
        raise ValueError("C21 frozen exact8 IDs are not unique")
    source_counts = Counter(_string(row, "source_name") for row in frozen_rows)
    if source_counts != Counter({"BAAI/TACO": 513, "codeparrot/apps": 58, "deepcoder-taco": 1}):
        raise ValueError(f"C22 source-count drift: {dict(source_counts)}")

    c6 = _verify_report_sidecar(C6_REPORT, "wp9c-function-supply-context-correction-v1")
    context = _mapping(c6.get("context_filter"), context="C6 context filter")
    if (
        context.get("max_prompt_tokens") != MAX_PROMPT_TOKENS
        or context.get("prompt_protocol") != "build_code_prompt_v1"
    ):
        raise ValueError("C6 Formal-B contract drift")
    model_id = context.get("tokenizer_model_id")
    revision = context.get("tokenizer_revision")
    if not isinstance(model_id, str) or not model_id or not isinstance(revision, str) or not revision:
        raise ValueError("C6 tokenizer identity is unavailable")
    identity_sha = stable_json_hash({"model_id": model_id, "revision": revision})
    tokenizer_loader = getattr(AutoTokenizer, "from_" + "pretrained")
    tokenizer = tokenizer_loader(model_id, revision=revision, local_files_only=True)

    c7 = _verify_report_sidecar(C7_REPORT, "wp9c-taco-under8-supply-audit-v1")
    c7_artifacts = _mapping(c7.get("artifact_sha256"), context="C7 artifacts")
    if _sha(C7_CANDIDATES) != _string(c7_artifacts, "taco_under8_candidates"):
        raise ValueError("C7 candidate artifact drift")
    c7_rows = {_string(row, "candidate_id"): row for row in _jsonl(C7_CANDIDATES)}

    c8 = _verify_report_sidecar(C8_REPORT, "wp9c-deepcoder-function-supply-audit-v1")
    c8_artifacts = _mapping(c8.get("artifact_sha256"), context="C8 artifacts")
    if _sha(C8_CANDIDATES) != _string(c8_artifacts, "deepcoder_under8_candidates"):
        raise ValueError("C8 candidate artifact drift")
    c8_rows = {_string(row, "candidate_id"): row for row in _jsonl(C8_CANDIDATES)}

    _verify_report_sidecar(APPS_REPORT, "wp9c-apps-under8-augmentability-audit-v1")
    expected_config_sha, expected_script_sha = _historical_apps_hashes()
    if _sha(APPS_CONFIG) != expected_config_sha or _sha(APPS_AUDIT) != expected_script_sha:
        raise ValueError("historical APPS reconstruction implementation drift")
    apps_module = _load_module(APPS_AUDIT, "wp9c_c22_apps_historical")
    source = apps_module._source_config(APPS_CONFIG)
    _, apps_path = apps_module._resolve_source_file(source)
    apps_candidates, _, _ = apps_module._apps_under8_candidates(apps_path)
    apps_by_id = {candidate.candidate_id: candidate for candidate in apps_candidates}

    context_rows: list[dict[str, object]] = []
    passers: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    token_counts: list[int] = []
    final_split_counts: Counter[tuple[int, int, int]] = Counter()

    for candidate_id in sorted(frozen_by_id):
        frozen = frozen_by_id[candidate_id]
        source_name = _string(frozen, "source_name")
        final_tests = _tests(frozen.get("frozen_tests"), candidate_id=candidate_id)
        if stable_json_hash([{"input": test.input, "expected": test.expected} for test in final_tests]) != frozen.get(
            "frozen_tests_sha256"
        ):
            raise ValueError(f"{candidate_id} final test digest drift")

        if source_name == "BAAI/TACO":
            base_row = c7_rows.get(candidate_id)
            if base_row is None:
                raise ValueError(f"missing C7 TACO source row: {candidate_id}")
            candidate = _candidate_from_row(base_row, final_tests=final_tests)
            original_tests = base_row.get("tests")
        elif source_name == "deepcoder-taco":
            base_row = c8_rows.get(candidate_id)
            if base_row is None:
                raise ValueError(f"missing C8 DeepCoder-TACO source row: {candidate_id}")
            candidate = _candidate_from_row(base_row, final_tests=final_tests)
            original_tests = base_row.get("tests")
        elif source_name == "codeparrot/apps":
            base_candidate = apps_by_id.get(candidate_id)
            if base_candidate is None:
                raise ValueError(f"missing historical APPS source row: {candidate_id}")
            candidate = replace(base_candidate, tests=final_tests)
            original_tests = [{"input": test.input, "expected": test.expected} for test in base_candidate.tests]
        else:
            raise ValueError(f"unexpected C22 source: {source_name}")

        existing_count = frozen.get("existing_test_count")
        if isinstance(existing_count, bool) or not isinstance(existing_count, int):
            raise ValueError(f"{candidate_id} existing count drift")
        if not isinstance(original_tests, list) or len(original_tests) != existing_count:
            raise ValueError(f"{candidate_id} historical existing tests count drift")
        frozen_prefix = [{"input": test.input, "expected": test.expected} for test in final_tests[:existing_count]]
        if canonical_json(original_tests) != canonical_json(frozen_prefix):
            raise ValueError(f"{candidate_id} final tests do not preserve historical existing tests")

        problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=SEED)
        if quality_gate_required is not False:
            raise ValueError(f"{candidate_id} exactly8 candidate unexpectedly still requires quality gate")
        split = (len(problem.visible_tests), len(problem.train_hidden_tests), len(problem.eval_hidden_tests))
        if split != (2, 3, 3):
            raise ValueError(f"{candidate_id} final canonical split drift: {split}")
        final_split_counts[split] += 1
        prompt = build_code_prompt(problem)
        prompt_tokens = _prompt_token_count(prompt, tokenizer)
        token_counts.append(prompt_tokens)
        eligible = prompt_tokens <= MAX_PROMPT_TOKENS
        row = {
            "candidate_id": candidate_id,
            "candidate_binding_sha256": frozen.get("candidate_binding_sha256"),
            "source_name": source_name,
            "frozen_tests_sha256": frozen.get("frozen_tests_sha256"),
            "prompt_protocol": "build_code_prompt_v1",
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt_tokens": prompt_tokens,
            "max_prompt_tokens": MAX_PROMPT_TOKENS,
            "formal_context_eligible": eligible,
            "quality_gate_required": False,
            "visible_test_count": 2,
            "train_hidden_test_count": 3,
            "eval_hidden_test_count": 3,
            "backfill_required": False,
        }
        context_rows.append(row)
        full = {
            **row,
            "source_record_id": candidate.source_record_id,
            "prompt": candidate.prompt,
            "function_name": candidate.function_name,
            "function_signature": candidate.function_signature,
            "tests": [{"input": test.input, "expected": test.expected} for test in final_tests],
            "source_url_hash": candidate.source_url_hash,
            "raw_reference_solution_hash": candidate.raw_reference_solution_hash,
            "difficulty": candidate.difficulty,
            "category": list(candidate.category),
            "raw_record_sha256": candidate.raw_record_sha256,
        }
        (passers if eligible else failures).append(full)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        rows_sha = _write_jsonl(temporary / "context_rows.jsonl", context_rows)
        pass_sha = _write_jsonl(temporary / "context_passers.jsonl", passers)
        fail_sha = _write_jsonl(temporary / "context_failures.jsonl", failures)
        report: dict[str, object] = {
            "schema_version": "wp9c-under8-final-exact-b-context-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "formal_eligible": False,
            "input_exact8_count": len(frozen_rows),
            "context_pass_count": len(passers),
            "context_fail_count": len(failures),
            "source_input_counts": dict(sorted(source_counts.items())),
            "source_pass_counts": dict(sorted(Counter(_string(row, "source_name") for row in passers).items())),
            "source_fail_counts": dict(sorted(Counter(_string(row, "source_name") for row in failures).items())),
            "max_prompt_tokens": MAX_PROMPT_TOKENS,
            "prompt_protocol": "build_code_prompt_v1",
            "chat_template_protocol": "formal_b_tokenizer_apply_chat_template_add_generation_prompt_v1",
            "tokenizer_identity_sha256": identity_sha,
            "prompt_token_stats": _stats(token_counts),
            "final_split_counts": {"2/3/3": final_split_counts[(2, 3, 3)]},
            "backfill_required": False,
            "minimum_pass_count": None,
            "execution_boundaries": {
                "candidate_code_execution": False,
                "piston_run": False,
                "tests_generated": False,
                "frozen_tests_modified": False,
                "calibration_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "input_bindings": {
                "c21_checkpoint_sha256": _sha(C21_CHECKPOINT),
                "c21_frozen_exact8_sha256": _sha(frozen_path),
                "c6_formal_b_report_sha256": _sha(C6_REPORT),
                "c7_report_sha256": _sha(C7_REPORT),
                "c7_candidates_sha256": _sha(C7_CANDIDATES),
                "c8_report_sha256": _sha(C8_REPORT),
                "c8_candidates_sha256": _sha(C8_CANDIDATES),
                "apps_report_sha256": _sha(APPS_REPORT),
                "apps_config_sha256": _sha(APPS_CONFIG),
                "apps_audit_script_sha256": _sha(APPS_AUDIT),
                "refresh_sources_sha256": _sha(ROOT / "src/code_verifier/data/refresh_sources.py"),
                "split_tests_sha256": _sha(ROOT / "src/code_verifier/data/split_tests.py"),
                "prompting_sha256": _sha(ROOT / "src/code_verifier/prompting.py"),
                "audit_script_sha256": _sha(Path(__file__)),
            },
            "artifact_sha256": {
                "context_rows": rows_sha,
                "context_passers": pass_sha,
                "context_failures": fail_sha,
            },
            "next_gate": "final_formal_piston_for_context_passers",
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
