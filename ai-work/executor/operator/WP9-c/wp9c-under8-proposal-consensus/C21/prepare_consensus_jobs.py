#!/usr/bin/env python3
"""Prepare frozen C21 two-oracle deterministic proposal-consensus jobs."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CONFIG = ROOT / "configs/data/wp9c-under8-proposal-consensus.yaml"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _json(path: Path) -> dict[str, object]:
    value = loads_strict(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            value = loads_strict(raw.decode("utf-8"))
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


def _verify(path: Path, expected: object, *, context: str) -> None:
    if not isinstance(expected, str) or _sha(path) != expected:
        raise ValueError(f"{context} digest mismatch: {path}")


def _validate_config(config: Mapping[str, object]) -> None:
    if config.get("version") != "wp9c-under8-deterministic-proposal-consensus-v1":
        raise ValueError("C21 config version drift")
    if config.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("C21 protocol drift")
    decision = _mapping(config.get("user_decision"), context="C21 user decision")
    if (
        decision.get("keep_only_remaining_gate_passers") is not True
        or decision.get("backfill_failed_candidates") is not False
        or decision.get("source_expansion_allowed") is not False
        or decision.get("minimum_under8_pass_count") is not None
        or decision.get("threshold_relaxation_allowed") is not False
    ):
        raise ValueError("C21 user decision drift")
    protocol = _mapping(config.get("consensus_protocol"), context="C21 consensus protocol")
    if (
        protocol.get("proposal_order") != "c13_input_proposals_in_frozen_rank_order"
        or protocol.get("oracle_order") != "c20_qualified_solution_sha256_order"
        or protocol.get("oracle_pair_size") != 2
        or protocol.get("output_protocol") != "wp9c-piston-json-output-probe-v1"
        or protocol.get("correctness_retry_allowed") is not False
        or protocol.get("transport_safe_retry_only") is not True
    ):
        raise ValueError("C21 consensus protocol drift")
    isolation = _mapping(config.get("isolation"), context="C21 isolation")
    if (
        isolation.get("execute_only_qualified_oracle_pair") is not True
        or isolation.get("use_only_c13_frozen_proposals") is not True
    ):
        raise ValueError("C21 isolation affirmative fields drift")
    for key, value in isolation.items():
        if key not in {"execute_only_qualified_oracle_pair", "use_only_c13_frozen_proposals"} and value is not False:
            raise ValueError(f"C21 isolation drift: {key}")


def prepare(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C21 preparation: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    bindings = _mapping(config.get("bindings"), context="C21 bindings")
    expected = _mapping(config.get("expected"), context="C21 expected")
    protocol = _mapping(config.get("consensus_protocol"), context="C21 consensus protocol")

    c20_checkpoint = ROOT / _str(bindings, "c20_checkpoint")
    _verify(c20_checkpoint, bindings.get("c20_checkpoint_sha256"), context="C20 checkpoint")
    c20 = _json(c20_checkpoint)
    c20_result = _mapping(c20.get("verified_result"), context="C20 verified result")
    if (
        c20.get("status") != "completed_verified"
        or c20.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1"
        or c20_result.get("under8_oracle_pair_survivors") != 615
        or c20_result.get("infrastructure_blocked") != 0
    ):
        raise ValueError("C20 prerequisite drift")

    for key in ("c20_qualified", "c20_qualification_jobs", "c13_jobs"):
        path = Path(_str(bindings, key))
        _verify(path, bindings.get(f"{key}_sha256"), context=key)
    for key in ("piston_config", "piston_transport_policy", "harness_source", "piston_source"):
        path = ROOT / _str(bindings, key)
        _verify(path, bindings.get(f"{key}_sha256"), context=key)

    qualified_rows = _jsonl(Path(_str(bindings, "c20_qualified")))
    c20_jobs = {_str(row, "candidate_id"): row for row in _jsonl(Path(_str(bindings, "c20_qualification_jobs")))}
    c13_jobs = {_str(row, "candidate_id"): row for row in _jsonl(Path(_str(bindings, "c13_jobs")))}
    count = _int(expected, "consensus_jobs")
    if len(qualified_rows) != count or count != 615:
        raise ValueError("C21 qualified input count drift")
    qualified = {_str(row, "candidate_id"): row for row in qualified_rows}
    if len(qualified) != count:
        raise ValueError("C21 qualified IDs are not unique")

    expected_sources = _mapping(expected.get("source_counts"), context="C21 source counts")
    actual_sources = Counter(_str(row, "source_name") for row in qualified_rows)
    if dict(sorted(actual_sources.items())) != {key: _int(expected_sources, key) for key in sorted(expected_sources)}:
        raise ValueError(f"C21 source count drift: {dict(actual_sources)}")

    jobs: list[dict[str, object]] = []
    existing_hist: Counter[int] = Counter()
    slots_hist: Counter[int] = Counter()
    proposal_hist: Counter[int] = Counter()
    for candidate_id in sorted(qualified):
        qrow = qualified[candidate_id]
        c20_job = c20_jobs.get(candidate_id)
        c13_job = c13_jobs.get(candidate_id)
        if c20_job is None or c13_job is None:
            raise ValueError(f"C21 join missing candidate: {candidate_id}")
        if qrow.get("classification") != "oracle_pair_qualified":
            raise ValueError(f"C21 non-qualified row admitted: {candidate_id}")
        if qrow.get("candidate_binding_sha256") != c20_job.get("candidate_binding_sha256") or qrow.get(
            "candidate_binding_sha256"
        ) != c13_job.get("candidate_binding_sha256"):
            raise ValueError(f"candidate binding drift: {candidate_id}")
        if qrow.get("c13_job_sha256") != c20_job.get("c13_job_sha256") or qrow.get(
            "c13_job_sha256"
        ) != stable_json_hash(c13_job):
            raise ValueError(f"C13 job binding drift: {candidate_id}")
        pair = qrow.get("qualified_solution_sha256")
        if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(value, str) for value in pair):
            raise ValueError(f"qualified pair schema drift: {candidate_id}")
        pair_str = cast(list[str], pair)
        if pair_str != sorted(pair_str) or len(set(pair_str)) != 2:
            raise ValueError(f"qualified pair order/uniqueness drift: {candidate_id}")
        solutions_value = c20_job.get("transformed_source_solutions")
        if not isinstance(solutions_value, list):
            raise ValueError(f"C20 solution payload drift: {candidate_id}")
        by_sha: dict[str, Mapping[str, object]] = {}
        for value in solutions_value:
            solution = _mapping(value, context=f"{candidate_id} solution")
            by_sha[_str(solution, "transformed_code_sha256")] = solution
        if any(solution_sha not in by_sha for solution_sha in pair_str):
            raise ValueError(f"qualified pair code missing: {candidate_id}")
        oracle_pair = [
            {
                "transformed_code_sha256": solution_sha,
                "code": _str(by_sha[solution_sha], "code"),
            }
            for solution_sha in pair_str
        ]
        for oracle in oracle_pair:
            if (
                hashlib.sha256(oracle["code"].encode("utf-8")).hexdigest()
                != oracle["transformed_code_sha256"]
            ):
                raise ValueError(f"oracle code digest drift: {candidate_id}")

        existing_tests = c13_job.get("existing_tests")
        proposals = c13_job.get("input_proposals")
        existing_count = _int(c13_job, "existing_test_count")
        slots = _int(c13_job, "additional_tests_required")
        proposal_count = _int(c13_job, "proposal_count")
        if not isinstance(existing_tests, list) or len(existing_tests) != existing_count:
            raise ValueError(f"existing tests drift: {candidate_id}")
        if not isinstance(proposals, list) or len(proposals) != proposal_count:
            raise ValueError(f"proposal payload drift: {candidate_id}")
        if (
            not _int(expected, "existing_test_count_min")
            <= existing_count
            <= _int(expected, "existing_test_count_max")
        ):
            raise ValueError(f"existing count outside under8 range: {candidate_id}")
        if existing_count + slots != _int(expected, "target_unique_tests_exact") or proposal_count < slots:
            raise ValueError(f"slot/proposal count drift: {candidate_id}")
        if stable_json_hash(proposals) != qrow.get("input_proposals_sha256"):
            raise ValueError(f"proposal digest drift: {candidate_id}")
        ranks: list[str] = []
        ids: set[str] = set()
        for value in proposals:
            proposal = _mapping(value, context=f"{candidate_id} proposal")
            if set(proposal) != {"proposal_id", "proposal_rank_sha256", "input"}:
                raise ValueError(f"proposal schema drift: {candidate_id}")
            proposal_id = _str(proposal, "proposal_id")
            rank = _str(proposal, "proposal_rank_sha256")
            if proposal_id in ids:
                raise ValueError(f"duplicate proposal ID: {candidate_id}")
            ids.add(proposal_id)
            ranks.append(rank)
        if ranks != sorted(ranks):
            raise ValueError(f"proposal rank order drift: {candidate_id}")

        jobs.append(
            {
                "candidate_id": candidate_id,
                "candidate_binding_sha256": qrow.get("candidate_binding_sha256"),
                "source_name": _str(qrow, "source_name"),
                "function_name": _str(c13_job, "function_name"),
                "execution_function_name": "__wp9c_reference_entry__",
                "existing_tests": existing_tests,
                "existing_test_count": existing_count,
                "additional_tests_required": slots,
                "input_proposals": proposals,
                "proposal_count": proposal_count,
                "oracle_pair": oracle_pair,
                "c13_job_sha256": qrow.get("c13_job_sha256"),
                "c20_qualified_row_sha256": stable_json_hash(qrow),
                "consensus_protocol": dict(protocol),
                "backfill_on_failure": False,
            }
        )
        existing_hist[existing_count] += 1
        slots_hist[slots] += 1
        proposal_hist[proposal_count] += 1

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        jobs_sha = _write_jsonl(temporary / "consensus_jobs.jsonl", jobs)
        report: dict[str, object] = {
            "schema_version": "wp9c-under8-proposal-consensus-preparation-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "formal_eligible": False,
            "consensus_job_count": len(jobs),
            "source_counts": dict(sorted(actual_sources.items())),
            "existing_test_count_histogram": {str(k): v for k, v in sorted(existing_hist.items())},
            "additional_test_slots_histogram": {str(k): v for k, v in sorted(slots_hist.items())},
            "proposal_count_histogram": {str(k): v for k, v in sorted(proposal_hist.items())},
            "consensus_protocol": dict(protocol),
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "preparation_script_sha256": _sha(Path(__file__)),
            "artifact_sha256": {"consensus_jobs": jobs_sha},
            "execution_boundaries": {
                "oracle_execution_run": False,
                "proposal_execution_run": False,
                "piston_run": False,
                "augmented_tests_frozen": False,
                "final_exact_b_run": False,
                "final_formal_piston_run": False,
                "calibration_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "next_gate": "manual_two_oracle_piston_proposal_consensus_and_exactly8_freeze",
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii")
        temporary.rename(output_dir)
        print(payload, end="")
        return report
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.config.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
