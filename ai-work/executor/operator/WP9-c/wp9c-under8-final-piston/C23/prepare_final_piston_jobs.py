#!/usr/bin/env python3
"""Prepare C23 final formal Piston jobs for C22 context-pass under8 rows."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict

ROOT = Path(__file__).resolve().parents[6]
C22_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-under8-final-exact-b/C22/checkpoint.json"
C21_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-under8-proposal-consensus/C21/checkpoint.json"
C20_CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-under8-oracle-qualification/C20/checkpoint.json"
C21_JOBS = Path("/home/dzy/wp9c-under8-proposal-consensus-prep-C21-r2/consensus_jobs.jsonl")
PISTON_CONFIG = ROOT / "configs/execution/piston-local.yaml"
TRANSPORT_POLICY = ROOT / "configs/execution/piston-transport-resilience.yaml"
ENTRY = "__wp9c_reference_entry__"


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


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = canonical_json(row) + "\n"
            handle.write(payload)
            digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def prepare(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C23 preparation: {output_dir}")

    c22 = _json(C22_CHECKPOINT)
    if c22.get("status") != "completed_verified" or c22.get("next_gate") != "C23-under8-final-formal-piston":
        raise ValueError("C22 prerequisite drift")
    c22_result = _mapping(c22.get("verified_result"), context="C22 verified result")
    if c22_result.get("context_pass") != 572 or c22_result.get("context_fail") != 0:
        raise ValueError("C22 context result drift")
    c22_artifacts = _mapping(c22.get("verified_artifacts"), context="C22 verified artifacts")
    passers_path = Path(_str(c22_artifacts, "context_passers"))
    if _sha(passers_path) != _str(c22_artifacts, "context_passers_sha256"):
        raise ValueError("C22 context passer digest drift")

    c21 = _json(C21_CHECKPOINT)
    if c21.get("status") != "completed_verified":
        raise ValueError("C21 is not closed")
    c21_bindings = _mapping(c21.get("bindings"), context="C21 bindings")
    if _sha(C21_JOBS) != _str(c21_bindings, "consensus_jobs_sha256"):
        raise ValueError("C21 consensus job digest drift")

    c20 = _json(C20_CHECKPOINT)
    if c20.get("status") != "completed_verified":
        raise ValueError("C20 is not closed")
    c20_bindings = _mapping(c20.get("bindings"), context="C20 bindings")
    if _sha(PISTON_CONFIG) != _str(c20_bindings, "piston_config_sha256"):
        raise ValueError("Piston config drift since C20")
    if _sha(TRANSPORT_POLICY) != _str(c20_bindings, "piston_transport_policy_sha256"):
        raise ValueError("Piston transport policy drift since C20")

    passers = _jsonl(passers_path)
    c21_jobs = {_str(row, "candidate_id"): row for row in _jsonl(C21_JOBS)}
    if len(passers) != 572 or len({_str(row, "candidate_id") for row in passers}) != 572:
        raise ValueError("C23 expected 572 unique C22 passers")

    jobs: list[dict[str, object]] = []
    sources: Counter[str] = Counter()
    for passer in sorted(passers, key=lambda row: _str(row, "candidate_id")):
        candidate_id = _str(passer, "candidate_id")
        c21_job = c21_jobs.get(candidate_id)
        if c21_job is None:
            raise ValueError(f"C23 missing C21 oracle job: {candidate_id}")
        if passer.get("candidate_binding_sha256") != c21_job.get("candidate_binding_sha256"):
            raise ValueError(f"candidate binding drift: {candidate_id}")
        if passer.get("source_name") != c21_job.get("source_name"):
            raise ValueError(f"source identity drift: {candidate_id}")
        tests = passer.get("tests")
        if not isinstance(tests, list) or len(tests) != 8:
            raise ValueError(f"C23 final test payload drift: {candidate_id}")
        test_hashes = [stable_json_hash(value) for value in tests]
        if len(set(test_hashes)) != 8 or stable_json_hash(tests) != passer.get("frozen_tests_sha256"):
            raise ValueError(f"C23 final test digest/uniqueness drift: {candidate_id}")
        oracle_pair = c21_job.get("oracle_pair")
        if not isinstance(oracle_pair, list) or len(oracle_pair) != 2:
            raise ValueError(f"C23 oracle pair drift: {candidate_id}")
        normalized_pair: list[dict[str, str]] = []
        hashes: list[str] = []
        for value in oracle_pair:
            oracle = _mapping(value, context=f"{candidate_id} oracle")
            code = _str(oracle, "code")
            digest = _str(oracle, "transformed_code_sha256")
            if hashlib.sha256(code.encode("utf-8")).hexdigest() != digest:
                raise ValueError(f"C23 oracle code digest drift: {candidate_id}")
            normalized_pair.append({"transformed_code_sha256": digest, "code": code})
            hashes.append(digest)
        if hashes != sorted(set(hashes)):
            raise ValueError(f"C23 oracle order/uniqueness drift: {candidate_id}")
        source_name = _str(passer, "source_name")
        sources[source_name] += 1
        jobs.append(
            {
                "candidate_id": candidate_id,
                "candidate_binding_sha256": passer.get("candidate_binding_sha256"),
                "source_name": source_name,
                "source_record_id": passer.get("source_record_id"),
                "function_name": passer.get("function_name"),
                "execution_function_name": ENTRY,
                "tests": tests,
                "test_count": 8,
                "frozen_tests_sha256": passer.get("frozen_tests_sha256"),
                "formal_b_prompt_sha256": passer.get("prompt_sha256"),
                "formal_b_prompt_tokens": passer.get("prompt_tokens"),
                "oracle_pair": normalized_pair,
                "oracle_pair_size": 2,
                "c22_context_passer_sha256": stable_json_hash(passer),
                "formal_pass_rule": "both_frozen_qualified_oracles_pass_all_final_exact8_tests",
                "backfill_on_failure": False,
            }
        )

    if sources != Counter({"BAAI/TACO": 513, "codeparrot/apps": 58, "deepcoder-taco": 1}):
        raise ValueError(f"C23 source-count drift: {dict(sources)}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        jobs_sha = _write_jsonl(temporary / "final_piston_jobs.jsonl", jobs)
        report: dict[str, object] = {
            "schema_version": "wp9c-under8-final-formal-piston-preparation-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "formal_eligible": False,
            "job_count": len(jobs),
            "source_counts": dict(sorted(sources.items())),
            "test_count_exact": 8,
            "oracle_pair_size_exact": 2,
            "formal_pass_rule": "both_frozen_qualified_oracles_pass_all_final_exact8_tests",
            "backfill_required": False,
            "minimum_pass_count": None,
            "execution_boundaries": {
                "candidate_code_execution": False,
                "piston_run": False,
                "tests_generated": False,
                "calibration_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "input_bindings": {
                "c22_checkpoint_sha256": _sha(C22_CHECKPOINT),
                "c22_context_passers_sha256": _sha(passers_path),
                "c21_checkpoint_sha256": _sha(C21_CHECKPOINT),
                "c21_consensus_jobs_sha256": _sha(C21_JOBS),
                "c20_checkpoint_sha256": _sha(C20_CHECKPOINT),
                "piston_config_sha256": _sha(PISTON_CONFIG),
                "piston_transport_policy_sha256": _sha(TRANSPORT_POLICY),
                "preparation_script_sha256": _sha(Path(__file__)),
            },
            "artifact_sha256": {"final_piston_jobs": jobs_sha},
            "next_gate": "manual_final_formal_piston_both_oracles_exact8",
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
    prepare(args.output.resolve())


if __name__ == "__main__":
    main()
