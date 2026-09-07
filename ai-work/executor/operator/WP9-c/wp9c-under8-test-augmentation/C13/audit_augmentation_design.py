#!/usr/bin/env python3
"""Freeze static WP9-c under8 augmentation jobs without executing source code."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from augmentation_protocol import PROPOSAL_PROTOCOL, generate_input_proposals, transform_source_solution
from huggingface_hub import snapshot_download

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.refresh_sources import _taco_function_call_tests
from code_verifier.data.schema import SchemaError, test_case_to_mapping

ROOT = Path(__file__).resolve().parents[6]
APPS_FIELDS = {"id", "question", "solutions", "input_output", "difficulty", "url", "starter_code"}


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
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            value = loads_strict(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
    return _sha(path)


def _require_str(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string field {key}")
    return value


def _verified_report(path: Path, expected_sha: object, schema: str) -> dict[str, object]:
    if not isinstance(expected_sha, str) or _sha(path) != expected_sha:
        raise ValueError(f"report digest mismatch: {path}")
    report = _json(path)
    if report.get("schema_version") != schema:
        raise ValueError(f"report schema mismatch: {path}")
    return report


def _verified_artifact(report: Mapping[str, object], report_path: Path, key: str, name: str) -> Path:
    digests = report.get("artifact_sha256")
    if not isinstance(digests, dict) or not isinstance(digests.get(key), str):
        raise ValueError(f"missing artifact digest: {key}")
    path = report_path.parent / name
    if _sha(path) != digests[key]:
        raise ValueError(f"artifact digest mismatch: {path}")
    return path


def _load_apps_payloads(
    *,
    source: Mapping[str, object],
    target_ids: set[str],
) -> dict[str, dict[str, object]]:
    if source.get("local_files_only") is not True:
        raise ValueError("APPS augmentation hydration must remain local-files-only")
    dataset_id = _require_str(source, "dataset_id")
    revision = _require_str(source, "revision")
    relative = _require_str(source, "file_path")
    snapshot = Path(
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=[relative],
            local_files_only=True,
        )
    )
    path = snapshot / relative
    if not path.is_file():
        raise ValueError("pinned local APPS source is unavailable")
    if path.stat().st_size != source.get("file_size") or _sha(path) != source.get("file_sha256"):
        raise ValueError("pinned APPS source identity drift")

    payloads: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = loads_strict(line)
            except StrictJsonError:
                continue
            if not isinstance(row, dict) or set(row) != APPS_FIELDS:
                continue
            source_id = row.get("id")
            if not isinstance(source_id, int) or isinstance(source_id, bool):
                continue
            raw_hash = stable_json_hash(row)
            candidate_id = stable_json_hash(
                {
                    "protocol": "wp9c-apps-under8-augmentability-audit-v1",
                    "source_id": source_id,
                    "raw_record_sha256": raw_hash,
                }
            )
            if candidate_id not in target_ids:
                continue
            try:
                input_output = loads_strict(cast(str, row["input_output"]))
                solutions_value = loads_strict(cast(str, row["solutions"]))
            except (StrictJsonError, ValueError, TypeError):
                raise ValueError(f"frozen APPS target payload is no longer parseable: {candidate_id}") from None
            if not isinstance(input_output, dict):
                raise ValueError(f"frozen APPS target input/output schema drift: {candidate_id}")
            try:
                parsed = _taco_function_call_tests(input_output, record_id=f"apps/train/{source_id}")
            except (SchemaError, ValueError):
                raise ValueError(f"frozen APPS target tests no longer parse: {candidate_id}") from None
            if parsed is None:
                raise ValueError(f"frozen APPS target lost function-call tests: {candidate_id}")
            function_name, tests = parsed
            if not isinstance(solutions_value, list) or any(not isinstance(item, str) for item in solutions_value):
                raise ValueError(f"frozen APPS target solutions schema drift: {candidate_id}")
            solutions = [item for item in solutions_value if item.strip()]
            payloads[candidate_id] = {
                "candidate_id": candidate_id,
                "source_name": "codeparrot/apps",
                "source_record_id": f"apps/train/{source_id}",
                "function_name": function_name,
                "tests": [test_case_to_mapping(test) for test in tests],
                "accepted_source_solutions": solutions,
                "accepted_source_solution_count": len(solutions),
                "raw_record_sha256": raw_hash,
            }
    if set(payloads) != target_ids:
        missing = sorted(target_ids - set(payloads))
        raise ValueError(f"failed to hydrate all frozen APPS targets: missing={len(missing)}")
    return payloads


def _validate_config(config: Mapping[str, object]) -> None:
    if config.get("version") != "wp9c-under8-test-augmentation-v1":
        raise ValueError("augmentation config version mismatch")
    if config.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1":
        raise ValueError("active-pool protocol mismatch")
    augmentation = config.get("augmentation")
    isolation = config.get("isolation")
    piston = config.get("piston")
    if not isinstance(augmentation, dict) or not isinstance(isolation, dict) or not isinstance(piston, dict):
        raise ValueError("augmentation config structure is invalid")
    if augmentation.get("target_unique_tests_exact") != 8:
        raise ValueError("under8 augmentation target must remain exactly 8 unique tests")
    if augmentation.get("minimum_piston_qualified_source_solutions") != 2:
        raise ValueError("multiple-solution consensus minimum must remain 2")
    if augmentation.get("proposal_protocol") != PROPOSAL_PROTOCOL:
        raise ValueError("proposal protocol drift")
    forbidden_true = (
        "source_expansion_allowed",
        "new_candidate_ids_allowed",
        "old_public_hidden_reward_outcomes_allowed",
        "synthetic_proposal_is_formal_evidence",
        "threshold_relaxation_allowed",
        "generation_failure_counts_as_pass",
        "unresolved_deepcoder_primeintellect_formal_admission_allowed",
        "c11_download_allowed",
        "grpo_allowed",
        "gpu_allowed",
    )
    if any(isolation.get(key) is not False for key in forbidden_true):
        raise ValueError("augmentation isolation policy drift")
    if isolation.get("unresolved_deepcoder_primeintellect_engineering_augmentation_allowed") is not True:
        raise ValueError("fixed-universe engineering augmentation policy drift")
    if piston.get("reference_solution_consensus_required") is not True:
        raise ValueError("reference-solution consensus must remain required")
    if piston.get("retry_to_success_allowed") is not False:
        raise ValueError("retry-to-success must remain forbidden")
    if piston.get("infrastructure_failure_is_correctness_failure") is not False:
        raise ValueError("infrastructure failures must remain distinct from correctness")


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    fixed = cast(Mapping[str, object], config["fixed_universe"])
    published = cast(Mapping[str, object], config["published_evidence"])
    augmentation = cast(Mapping[str, object], config["augmentation"])
    apps_source = cast(Mapping[str, object], config["apps_source"])
    piston = cast(Mapping[str, object], config["piston"])

    c12_report_path = Path(_require_str(fixed, "c12_report"))
    c12_manifest_path = Path(_require_str(fixed, "c12_manifest"))
    c12 = _verified_report(
        c12_report_path,
        fixed.get("c12_report_sha256"),
        "wp9c-fixed-2505-candidate-freeze-v1",
    )
    if _sha(c12_manifest_path) != fixed.get("c12_manifest_sha256") or c12.get("manifest_sha256") != fixed.get(
        "c12_manifest_sha256"
    ):
        raise ValueError("C12 manifest binding drift")
    manifest_rows = _jsonl(c12_manifest_path)
    under8_rows = [row for row in manifest_rows if row.get("supply_class") == "under8"]
    if len(under8_rows) != fixed.get("under8_exact"):
        raise ValueError("fixed under8 count drift")
    target_by_id = {_require_str(row, "candidate_id"): row for row in under8_rows}
    if len(target_by_id) != len(under8_rows):
        raise ValueError("fixed under8 IDs are not unique")
    expected_sources = fixed.get("source_counts")
    actual_sources = Counter(_require_str(row, "source_name") for row in under8_rows)
    if not isinstance(expected_sources, dict) or dict(sorted(actual_sources.items())) != dict(
        sorted(expected_sources.items())
    ):
        raise ValueError("fixed under8 source counts drift")

    c11_path = ROOT / _require_str(published, "c11_checkpoint")
    c11 = _json(c11_path)
    if c11.get("status") != published.get("c11_required_status"):
        raise ValueError("C11 must remain paused")
    pause = c11.get("pause_directive")
    if not isinstance(pause, dict) or pause.get("download_authorized") is not False:
        raise ValueError("C11 download pause drift")

    piston_path = ROOT / _require_str(piston, "config")
    if _sha(piston_path) != piston.get("config_sha256"):
        raise ValueError("Piston config digest drift")

    c7_path = Path(_require_str(published, "c7_report"))
    c8_path = Path(_require_str(published, "c8_report"))
    c7 = _verified_report(c7_path, published.get("c7_report_sha256"), "wp9c-taco-under8-supply-audit-v1")
    c8 = _verified_report(c8_path, published.get("c8_report_sha256"), "wp9c-deepcoder-function-supply-audit-v1")
    c7_candidates_path = _verified_artifact(c7, c7_path, "taco_under8_candidates", "taco_under8_candidates.jsonl")
    c8_candidates_path = _verified_artifact(
        c8, c8_path, "deepcoder_under8_candidates", "deepcoder_under8_candidates.jsonl"
    )

    payload_by_id: dict[str, dict[str, object]] = {}
    for row in _jsonl(c7_candidates_path):
        candidate_id = _require_str(row, "candidate_id")
        if candidate_id in target_by_id:
            payload_by_id[candidate_id] = row
    for row in _jsonl(c8_candidates_path):
        candidate_id = _require_str(row, "candidate_id")
        if candidate_id in target_by_id:
            if candidate_id in payload_by_id:
                raise ValueError(f"duplicate frozen payload identity: {candidate_id}")
            payload_by_id[candidate_id] = row

    apps_ids = {
        candidate_id for candidate_id, row in target_by_id.items() if row.get("source_name") == "codeparrot/apps"
    }
    apps_payloads = _load_apps_payloads(source=apps_source, target_ids=apps_ids)
    for candidate_id, row in apps_payloads.items():
        if candidate_id in payload_by_id:
            raise ValueError(f"duplicate APPS payload identity: {candidate_id}")
        payload_by_id[candidate_id] = row
    if set(payload_by_id) != set(target_by_id):
        raise ValueError("hydrated augmentation payload IDs do not equal frozen C12 under8 IDs")

    maximum = cast(int, augmentation["maximum_input_proposals_per_candidate"])
    minimum_transforms = cast(int, augmentation["minimum_transformable_source_solutions_for_job"])
    jobs: list[dict[str, object]] = []
    solution_reason_counts: Counter[str] = Counter()
    transformable_hist: Counter[int] = Counter()
    proposal_hist: Counter[int] = Counter()
    slots_hist: Counter[int] = Counter()
    static_blockers: Counter[str] = Counter()
    source_jobs: Counter[str] = Counter()
    source_accepted_lt2: Counter[str] = Counter()
    source_transformable_lt2: Counter[str] = Counter()
    source_insufficient_proposals: Counter[str] = Counter()
    source_accepted_hist: dict[str, Counter[int]] = {}
    source_transformable_hist: dict[str, Counter[int]] = {}

    for candidate_id in sorted(target_by_id):
        target = target_by_id[candidate_id]
        payload = payload_by_id[candidate_id]
        source_name = _require_str(target, "source_name")
        source_jobs[source_name] += 1
        if payload.get("source_name") != source_name:
            raise ValueError(f"source identity drift for {candidate_id}")
        function_name = _require_str(payload, "function_name")
        tests_value = payload.get("tests")
        solutions_value = payload.get("accepted_source_solutions")
        if not isinstance(tests_value, list) or not isinstance(solutions_value, list):
            raise ValueError(f"augmentation payload schema drift: {candidate_id}")
        if any(not isinstance(item, dict) or set(item) != {"input", "expected"} for item in tests_value):
            raise ValueError(f"test schema drift: {candidate_id}")
        if any(not isinstance(item, str) or not item.strip() for item in solutions_value):
            raise ValueError(f"source solution schema drift: {candidate_id}")
        accepted_count = len(solutions_value)
        source_accepted_hist.setdefault(source_name, Counter())[accepted_count] += 1
        if accepted_count < minimum_transforms:
            source_accepted_lt2[source_name] += 1
        existing_count = len(tests_value)
        if (
            not cast(int, augmentation["minimum_existing_unique_tests"])
            <= existing_count
            <= cast(int, augmentation["maximum_existing_unique_tests"])
        ):
            raise ValueError(f"under8 existing test count drift: {candidate_id}")
        test_hashes = [stable_json_hash(item) for item in tests_value]
        if len(set(test_hashes)) != len(test_hashes):
            raise ValueError(f"existing tests are not unique: {candidate_id}")

        transformed_by_sha: dict[str, dict[str, object]] = {}
        transform_diagnostics: list[dict[str, object]] = []
        for solution in cast(list[str], solutions_value):
            result = transform_source_solution(solution, function_name=function_name)
            solution_reason_counts[result.reason] += 1
            diagnostic = asdict(result)
            if result.success:
                assert result.transformed_code_sha256 is not None
                transformed_by_sha.setdefault(result.transformed_code_sha256, diagnostic)
            else:
                diagnostic.pop("transformed_code", None)
            transform_diagnostics.append(diagnostic)
        transformed = [transformed_by_sha[key] for key in sorted(transformed_by_sha)]
        transformable_count = len(transformed)
        transformable_hist[transformable_count] += 1
        source_transformable_hist.setdefault(source_name, Counter())[transformable_count] += 1
        if transformable_count < minimum_transforms:
            source_transformable_lt2[source_name] += 1

        proposals = generate_input_proposals(
            candidate_id=candidate_id,
            existing_inputs=[cast(dict[str, Any], item)["input"] for item in tests_value],
            maximum=maximum,
        )
        proposal_hist[len(proposals)] += 1
        slots_needed = cast(int, augmentation["target_unique_tests_exact"]) - existing_count
        slots_hist[slots_needed] += 1
        blockers: list[str] = []
        if transformable_count < minimum_transforms:
            blockers.append("fewer_than_two_transformable_source_solutions")
        if len(proposals) < slots_needed:
            blockers.append("insufficient_deterministic_input_proposals")
            source_insufficient_proposals[source_name] += 1
        for blocker in blockers:
            static_blockers[blocker] += 1

        jobs.append(
            {
                "candidate_id": candidate_id,
                "candidate_binding_sha256": target.get("candidate_binding_sha256"),
                "source_name": source_name,
                "source_record_id": target.get("source_record_id"),
                "function_name": function_name,
                "existing_tests": tests_value,
                "existing_test_count": existing_count,
                "additional_tests_required": slots_needed,
                "accepted_source_solution_count": len(solutions_value),
                "transformable_source_solution_count": transformable_count,
                "transformed_source_solutions": transformed,
                "solution_transform_diagnostics": transform_diagnostics,
                "input_proposals": proposals,
                "proposal_count": len(proposals),
                "proposal_protocol": PROPOSAL_PROTOCOL,
                "static_augmentation_ready": not blockers,
                "static_blockers": blockers,
                "formal_admission_provenance_blocked": source_name == "deepcoder-primeintellect",
                "under8_formal_context_eligible": None,
                "quality_gate_passed": False,
            }
        )

    static_ready = sum(row["static_augmentation_ready"] is True for row in jobs)
    provenance_blocked = sum(row["formal_admission_provenance_blocked"] is True for row in jobs)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        jobs_sha = _write_jsonl(temporary / "augmentation_jobs.jsonl", jobs)
        report: dict[str, object] = {
            "schema_version": "wp9c-under8-augmentation-design-v1",
            "evidence_class": "engineering_static_augmentation_design",
            "formal_eligible": False,
            "active_pool_protocol": "wp9c-active-pool-2500-amendment-v1",
            "fixed_candidate_universe_count": c12.get("candidate_count"),
            "under8_job_count": len(jobs),
            "under8_source_counts": dict(sorted(actual_sources.items())),
            "source_job_counts": dict(sorted(source_jobs.items())),
            "source_jobs_with_fewer_than_two_accepted_solutions": dict(sorted(source_accepted_lt2.items())),
            "source_jobs_with_fewer_than_two_transformable_solutions": dict(sorted(source_transformable_lt2.items())),
            "source_jobs_with_insufficient_input_proposals": dict(sorted(source_insufficient_proposals.items())),
            "source_accepted_solution_count_histograms": {
                source: {str(key): value for key, value in sorted(hist.items())}
                for source, hist in sorted(source_accepted_hist.items())
            },
            "source_transformable_solution_count_histograms": {
                source: {str(key): value for key, value in sorted(hist.items())}
                for source, hist in sorted(source_transformable_hist.items())
            },
            "static_augmentation_ready_count": static_ready,
            "static_blocker_counts": dict(sorted(static_blockers.items())),
            "transformable_source_solution_count_histogram": {
                str(key): value for key, value in sorted(transformable_hist.items())
            },
            "solution_transform_reason_counts": dict(sorted(solution_reason_counts.items())),
            "input_proposal_count_histogram": {str(key): value for key, value in sorted(proposal_hist.items())},
            "additional_test_slots_histogram": {str(key): value for key, value in sorted(slots_hist.items())},
            "deepcoder_primeintellect_formal_admission_provenance_blocked": provenance_blocked,
            "under8_formal_context_eligible_count": None,
            "quality_gate_passed_count": 0,
            "generation_or_solution_execution_run": False,
            "piston_run": False,
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "audit_script_sha256": _sha(Path(__file__)),
            "augmentation_protocol_sha256": _sha(Path(__file__).with_name("augmentation_protocol.py")),
            "piston_config_sha256": _sha(piston_path),
            "jobs_sha256": jobs_sha,
            "bindings": {
                "c12_report_sha256": fixed["c12_report_sha256"],
                "c12_manifest_sha256": fixed["c12_manifest_sha256"],
                "c7_report_sha256": published["c7_report_sha256"],
                "c8_report_sha256": published["c8_report_sha256"],
                "c11_checkpoint_sha256": _sha(c11_path),
                "apps_source_sha256": apps_source["file_sha256"],
            },
            "next_gate": "C14-manual-reference-solution-consensus-augmentation",
            "formal_blockers": [
                "reference_solution_piston_qualification_not_run",
                "input_proposal_expected_outputs_not_consensus_validated",
                "augmented_tests_not_frozen",
                "final_exact_b_context_not_run",
                "final_formal_function_level_piston_not_run",
                "deepcoder_primeintellect_provenance_unresolved_for_541_rows",
            ],
            "notes": [
                "C13 hydrates only the frozen C12 under8 IDs and cannot add candidate supply.",
                "Input proposals are deterministic synthetic inputs only and are never formal evidence by themselves.",
                (
                    "C14 must Piston-qualify at least two accepted source solutions before any proposal can "
                    "become a test."
                ),
                (
                    "C14 must derive expected outputs only from strict multi-solution consensus and freeze "
                    "exactly 8 unique tests."
                ),
                (
                    "The 541 DeepCoder-PrimeIntellect jobs may receive engineering augmentation but remain "
                    "blocked from formal admission until provenance closes."
                ),
            ],
        }
        report_payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(report_payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(
            hashlib.sha256(report_payload.encode()).hexdigest() + "\n", encoding="ascii"
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
    print(canonical_json(audit(Path(args.config).resolve(), Path(args.output_dir).resolve())))


if __name__ == "__main__":
    main()
