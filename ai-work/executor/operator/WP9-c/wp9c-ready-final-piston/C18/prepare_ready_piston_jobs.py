#!/usr/bin/env python3
"""Prepare frozen ready-lane reference-solution Piston jobs without executing code."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from huggingface_hub import snapshot_download

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.data.prepare import load_canonical_jsonl
from code_verifier.data.refresh_sources import (
    RefreshCandidate,
    RefreshSourceSpec,
    _deepcoder_raw_record_hash,
    _function_candidate_from_row,
    _iter_parquet_rows,
    _opencoder_candidate_from_row,
    _validate_license,
    canonicalize_refresh_candidate,
)
from code_verifier.data.schema import CodeProblem, problem_to_mapping, test_case_to_mapping
from code_verifier.prompting import build_code_prompt

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CONFIG = ROOT / "configs/data/wp9c-ready-final-piston.yaml"
NATIVE_AUDIT = (
    ROOT / "ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_native_function_supply.py"
)
C13_DIR = ROOT / "ai-work/executor/operator/WP9-c/wp9c-under8-test-augmentation/C13"
sys.path.insert(0, str(C13_DIR))
from augmentation_protocol import REFERENCE_ENTRY, SolutionTransform, transform_source_solution  # noqa: E402


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _require_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_int(row: Mapping[str, object], key: str) -> int:
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
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            value = loads_strict(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
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


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _local_snapshot(dataset_id: str, revision: str) -> Path:
    snapshot = Path(
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            revision=revision,
            local_files_only=True,
        )
    ).resolve()
    if snapshot.name != revision:
        raise ValueError(f"snapshot identity mismatch for {dataset_id}: {snapshot.name}")
    return snapshot


def _deepcoder_specs(path: Path) -> dict[str, RefreshSourceSpec]:
    sources = load_yaml_mapping(path).get("sources")
    if not isinstance(sources, list):
        raise ValueError("refresh sources must be a list")
    result: dict[str, RefreshSourceSpec] = {}
    for value in sources:
        if not isinstance(value, dict):
            continue
        source_name = value.get("source_name")
        config_name = value.get("config_name")
        if source_name not in {"deepcoder-primeintellect", "deepcoder-taco"}:
            continue
        if config_name not in {"primeintellect", "taco"}:
            raise ValueError("DeepCoder config-name drift")
        result[cast(str, source_name)] = RefreshSourceSpec(
            source_name=cast(str, source_name),
            dataset_id=cast(str, value["dataset_id"]),
            revision=cast(str, value["revision"]),
            config_name=cast(str, config_name),
            split=cast(str, value["split"]),
            declared_license=cast(str, value["declared_license"]),
            adapter=cast(Any, value["adapter"]),
        )
    if set(result) != {"deepcoder-primeintellect", "deepcoder-taco"}:
        raise ValueError("frozen DeepCoder source identities are incomplete")
    return result


def _tests(problem: CodeProblem) -> list[dict[str, Any]]:
    values = [*problem.visible_tests, *problem.train_hidden_tests, *problem.eval_hidden_tests]
    return [cast(dict[str, Any], test_case_to_mapping(value)) for value in values]


def _verify_problem(row: Mapping[str, object], problem: CodeProblem) -> None:
    if problem.problem_id != _require_str(row, "candidate_id"):
        raise ValueError("candidate/problem ID mismatch")
    if problem.source != _require_str(row, "source_name"):
        raise ValueError(f"candidate/problem source mismatch: {problem.problem_id}")
    if len(_tests(problem)) < 8:
        raise ValueError(f"ready problem has fewer than eight tests: {problem.problem_id}")
    prompt_sha = row.get("prompt_sha256")
    if prompt_sha is not None and prompt_sha != _sha_text(build_code_prompt(problem)):
        raise ValueError(f"ready prompt binding drift: {problem.problem_id}")


def _deepcoder_hydration(
    refresh_config: Path,
    target_by_source: Mapping[str, set[str]],
) -> tuple[dict[str, RefreshCandidate], dict[str, list[str]], dict[str, object]]:
    candidates: dict[str, RefreshCandidate] = {}
    solutions: dict[str, list[str]] = {}
    identities: dict[str, object] = {}
    for source_name, spec in _deepcoder_specs(refresh_config).items():
        targets = target_by_source[source_name]
        snapshot = _local_snapshot(spec.dataset_id, spec.revision)
        _validate_license(snapshot, spec.declared_license)
        if spec.config_name is None:
            raise ValueError("DeepCoder config name cannot be null")
        matched = 0
        for row_index, raw_row in enumerate(_iter_parquet_rows(snapshot, spec.config_name, spec.split)):
            raw_hash = _deepcoder_raw_record_hash(raw_row)
            candidate = _function_candidate_from_row(spec, raw_row, row_index=row_index, raw_hash=raw_hash)
            if candidate is None or candidate.candidate_id not in targets:
                continue
            raw_solutions = raw_row.get("solutions")
            if not isinstance(raw_solutions, list) or any(not isinstance(item, str) for item in raw_solutions):
                raise ValueError(f"DeepCoder solutions schema drift: {candidate.candidate_id}")
            candidates[candidate.candidate_id] = candidate
            solutions[candidate.candidate_id] = [item for item in cast(list[str], raw_solutions) if item.strip()]
            matched += 1
        if matched != len(targets):
            raise ValueError(f"DeepCoder hydration shortfall for {source_name}: {matched}/{len(targets)}")
        identities[source_name] = {
            "dataset_id": spec.dataset_id,
            "revision": spec.revision,
            "config_name": spec.config_name,
            "declared_license": spec.declared_license,
        }
    return candidates, solutions, identities


def _native_hydration(
    native_config: Path,
    target_ids: set[str],
) -> tuple[dict[str, RefreshCandidate], dict[str, list[str]], dict[str, object]]:
    native = cast(Any, _load_module(NATIVE_AUDIT, "wp9c_ready_piston_native_dependency"))
    source_configs = cast(dict[str, dict[str, object]], native._source_configs(native_config))
    _, apps_path = cast(tuple[Path, Path], native._resolve_source_file(source_configs["apps_train"]))
    _, leetcode_path = cast(tuple[Path, Path], native._resolve_source_file(source_configs["leetcode_merged"]))
    apps_candidates = cast(tuple[list[RefreshCandidate], dict[str, object]], native._apps_candidates(apps_path))[0]
    leetcode_candidates = cast(
        tuple[list[RefreshCandidate], dict[str, object]], native._leetcode_candidates(leetcode_path)
    )[0]
    candidates = {
        candidate.candidate_id: candidate
        for candidate in [*apps_candidates, *leetcode_candidates]
        if candidate.candidate_id in target_ids
    }
    if set(candidates) != target_ids:
        raise ValueError(f"native hydration candidate shortfall: {len(candidates)}/{len(target_ids)}")

    apps_ids = {
        int(candidate.source_record_id.rsplit("/", 1)[-1]): candidate_id
        for candidate_id, candidate in candidates.items()
        if candidate.source_name == "codeparrot/apps"
    }
    leetcode_ids = {
        int(candidate.source_record_id.rsplit("/", 1)[-1]): candidate_id
        for candidate_id, candidate in candidates.items()
        if candidate.source_name == "tkeskin/leetcode-solutions"
    }
    solutions: dict[str, list[str]] = {}
    with apps_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = loads_strict(line)
            if not isinstance(value, dict):
                continue
            source_id = value.get("id")
            if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id not in apps_ids:
                continue
            candidate_id = apps_ids[source_id]
            candidate = candidates[candidate_id]
            if stable_json_hash(value) != candidate.raw_record_sha256:
                raise ValueError(f"APPS raw-record digest drift: {candidate_id}")
            raw_solutions = value.get("solutions")
            if isinstance(raw_solutions, str):
                raw_solutions = loads_strict(raw_solutions)
            if not isinstance(raw_solutions, list) or any(not isinstance(item, str) for item in raw_solutions):
                raise ValueError(f"APPS solutions schema drift: {candidate_id}")
            solutions[candidate_id] = [item for item in cast(list[str], raw_solutions) if item.strip()]

    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    parquet = pq.ParquetFile(leetcode_path)
    index = 0
    for batch in parquet.iter_batches(batch_size=128, columns=parquet.schema_arrow.names):
        for raw_row in batch.to_pylist():
            if index in leetcode_ids:
                if not isinstance(raw_row, Mapping):
                    raise ValueError("LeetCode raw row is not a mapping")
                candidate_id = leetcode_ids[index]
                candidate = candidates[candidate_id]
                raw_hash = cast(str, native._stable_arrow_row_hash(raw_row))
                if raw_hash != candidate.raw_record_sha256:
                    raise ValueError(f"LeetCode raw-record digest drift: {candidate_id}")
                code = raw_row.get("python")
                if not isinstance(code, str) or not code.strip():
                    raise ValueError(f"LeetCode reference solution missing: {candidate_id}")
                solutions[candidate_id] = [code]
            index += 1
    if set(solutions) != target_ids:
        raise ValueError(f"native solution hydration shortfall: {len(solutions)}/{len(target_ids)}")
    return (
        candidates,
        solutions,
        {
            "apps_file_sha256": _sha(apps_path),
            "leetcode_file_sha256": _sha(leetcode_path),
        },
    )


def _opencoder_hydration(
    source_config: Path,
    target_ids: set[str],
) -> tuple[dict[str, RefreshCandidate], dict[str, list[str]], dict[str, object]]:
    sources = _mapping(load_yaml_mapping(source_config).get("sources"), context="OpenCoder sources")
    source = _mapping(sources.get("opencoder_educational"), context="OpenCoder source")
    dataset_id = _require_str(source, "dataset_id")
    revision = _require_str(source, "revision")
    declared_license = _require_str(source, "declared_license")
    expected_sha = _require_str(source, "parquet_sha256")
    snapshot = _local_snapshot(dataset_id, revision)
    _validate_license(snapshot, declared_license)
    path = snapshot / _require_str(source, "parquet_path")
    if _sha(path) != expected_sha:
        raise ValueError("OpenCoder parquet digest drift")

    import pyarrow.parquet as pq

    candidates: dict[str, RefreshCandidate] = {}
    solutions: dict[str, list[str]] = {}
    parquet = pq.ParquetFile(path)
    row_index = 0
    for batch in parquet.iter_batches(batch_size=128, columns=parquet.schema_arrow.names):
        for raw_row in batch.to_pylist():
            if not isinstance(raw_row, Mapping):
                raise ValueError("OpenCoder raw row is not a mapping")
            candidate = _opencoder_candidate_from_row(
                raw_row,
                row_index=row_index,
                dataset_id=dataset_id,
                revision=revision,
            )
            row_index += 1
            if candidate is None or candidate.candidate_id not in target_ids:
                continue
            code = raw_row.get("code")
            if not isinstance(code, str) or not code.strip():
                raise ValueError(f"OpenCoder reference solution missing: {candidate.candidate_id}")
            candidates[candidate.candidate_id] = candidate
            solutions[candidate.candidate_id] = [code]
    if set(candidates) != target_ids or set(solutions) != target_ids:
        raise ValueError(f"OpenCoder hydration shortfall: {len(candidates)}/{len(target_ids)}")
    return (
        candidates,
        solutions,
        {
            "dataset_id": dataset_id,
            "revision": revision,
            "parquet_sha256": expected_sha,
        },
    )


def _transform_all(
    raw_solutions: Sequence[str],
    *,
    function_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    transformed: dict[str, dict[str, object]] = {}
    diagnostics: list[dict[str, object]] = []
    for raw_solution in raw_solutions:
        result: SolutionTransform = transform_source_solution(raw_solution, function_name=function_name)
        value = cast(dict[str, object], asdict(result))
        diagnostics.append({key: item for key, item in value.items() if key != "transformed_code"})
        if not result.success:
            continue
        if result.transformed_code_sha256 is None or result.transformed_code is None:
            raise ValueError("successful transform is missing code or digest")
        transformed.setdefault(
            result.transformed_code_sha256,
            {
                "transformed_code_sha256": result.transformed_code_sha256,
                "source_code_sha256": result.source_code_sha256,
                "raw_solution_sha256": result.raw_solution_sha256,
                "target_kind": result.target_kind,
                "target_owner": result.target_owner,
                "extraction_mode": result.extraction_mode,
                "code": result.transformed_code,
            },
        )
    return [transformed[key] for key in sorted(transformed)], diagnostics


def _validate_config(config: Mapping[str, object]) -> None:
    if config.get("version") != "wp9c-ready-final-piston-v1":
        raise ValueError("C18 config version drift")
    if config.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("C18 protocol drift")
    decision = _mapping(config.get("user_decision"), context="C18 user decision")
    if (
        decision.get("keep_only_remaining_gate_passers") is not True
        or decision.get("backfill_failed_candidates") is not False
        or decision.get("source_expansion_allowed") is not False
        or decision.get("minimum_ready_piston_pass_count") is not None
        or decision.get("threshold_relaxation_allowed") is not False
    ):
        raise ValueError("C18 user decision drift")
    isolation = _mapping(config.get("isolation"), context="C18 isolation")
    if isolation.get("local_source_snapshots_only") is not True:
        raise ValueError("C18 must be local-snapshot-only")
    for key, value in isolation.items():
        if key != "local_source_snapshots_only" and value is not False:
            raise ValueError(f"C18 isolation drift: {key}")


def prepare(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C18 output: {output_dir}")
    config = load_yaml_mapping(config_path)
    _validate_config(config)
    bindings = _mapping(config.get("bindings"), context="C18 bindings")
    expected = _mapping(config.get("expected"), context="C18 expected")
    protocol = _mapping(config.get("reference_solution_protocol"), context="C18 reference protocol")

    for key in (
        "refresh_config",
        "native_source_config",
        "opencoder_source_config",
        "aggregate_config",
        "solution_transform",
        "piston_config",
        "piston_transport_policy",
    ):
        _verify(ROOT / _require_str(bindings, key), bindings.get(f"{key}_sha256"), context=key)
    c17_checkpoint_path = ROOT / _require_str(bindings, "c17_checkpoint")
    _verify(c17_checkpoint_path, bindings.get("c17_checkpoint_sha256"), context="C17 checkpoint")
    c17_checkpoint = _json(c17_checkpoint_path)
    if (
        c17_checkpoint.get("status") != "completed"
        or c17_checkpoint.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1"
    ):
        raise ValueError("C17 prerequisite drift")
    c17_report_path = Path(_require_str(bindings, "c17_report"))
    _verify(c17_report_path, bindings.get("c17_report_sha256"), context="C17 report")
    viable_path = Path(_require_str(bindings, "c17_viable_candidates"))
    _verify(viable_path, bindings.get("c17_viable_candidates_sha256"), context="C17 viable manifest")

    ready_rows = [row for row in _jsonl(viable_path) if row.get("reduced_pool_lane") == "ready_for_final_piston"]
    if len(ready_rows) != _require_int(expected, "ready_lane") or len(ready_rows) != 1276:
        raise ValueError("C17 ready-lane count drift")
    ready = {_require_str(row, "candidate_id"): row for row in ready_rows}
    if len(ready) != 1276:
        raise ValueError("C17 ready IDs are not unique")
    source_counts = Counter(_require_str(row, "source_name") for row in ready_rows)
    expected_source_values = _mapping(expected.get("ready_source_counts"), context="expected source counts")
    expected_source_counts = {key: _require_int(expected_source_values, key) for key in expected_source_values}
    if dict(sorted(source_counts.items())) != dict(sorted(expected_source_counts.items())):
        raise ValueError(f"C17 ready source-count drift: {dict(source_counts)}")

    incumbent_rows = [row for row in ready_rows if row.get("origin") == "existing_incumbent"]
    if len(incumbent_rows) != _require_int(expected, "incumbent_ready"):
        raise ValueError("C17 incumbent-ready count drift")
    if len(ready_rows) - len(incumbent_rows) != _require_int(expected, "newly_reconstructed_ready"):
        raise ValueError("C17 reconstructed-ready count drift")

    incumbent_path = Path(_require_str(bindings, "incumbent_canonical"))
    _verify(incumbent_path, bindings.get("incumbent_canonical_sha256"), context="incumbent canonical")
    summary = _json(Path(_require_str(bindings, "incumbent_summary")))
    if summary.get("record_count") != 654 or summary.get("records_digest") != bindings.get(
        "incumbent_canonical_sha256"
    ):
        raise ValueError("incumbent summary drift")
    incumbent_problems = {problem.problem_id: problem for problem in load_canonical_jsonl(incumbent_path)}
    incumbent_ids = {_require_str(row, "candidate_id") for row in incumbent_rows}
    if set(incumbent_problems) != incumbent_ids:
        raise ValueError("incumbent canonical IDs differ from C17")
    if any(problem.reference_solution for problem in incumbent_problems.values()):
        raise ValueError("incumbent reference_solution unexpectedly populated")

    deep_targets = {
        source: {candidate_id for candidate_id, row in ready.items() if row.get("source_name") == source}
        for source in ("deepcoder-primeintellect", "deepcoder-taco")
    }
    deep_candidates, deep_solutions, deep_identity = _deepcoder_hydration(
        ROOT / _require_str(bindings, "refresh_config"), deep_targets
    )
    native_ids = {
        candidate_id
        for candidate_id, row in ready.items()
        if row.get("source_name") in {"codeparrot/apps", "tkeskin/leetcode-solutions"}
    }
    native_candidates, native_solutions, native_identity = _native_hydration(
        ROOT / _require_str(bindings, "native_source_config"), native_ids
    )
    opencoder_ids = {
        candidate_id for candidate_id, row in ready.items() if row.get("source_name") == "opencoder-educational"
    }
    opencoder_candidates, opencoder_solutions, opencoder_identity = _opencoder_hydration(
        ROOT / _require_str(bindings, "opencoder_source_config"), opencoder_ids
    )
    candidates = {**deep_candidates, **native_candidates, **opencoder_candidates}
    raw_solutions = {**deep_solutions, **native_solutions, **opencoder_solutions}
    non_lcb_ids = {
        candidate_id for candidate_id, row in ready.items() if row.get("source_name") != "deepcoder-lcbv5-train"
    }
    if set(candidates) != non_lcb_ids or set(raw_solutions) != non_lcb_ids:
        raise ValueError("non-lcb ready hydration partition drift")

    jobs: list[dict[str, object]] = []
    dropped: list[dict[str, object]] = []
    job_sources: Counter[str] = Counter()
    dropped_sources: Counter[str] = Counter()
    dropped_reasons: Counter[str] = Counter()
    transform_reasons: Counter[str] = Counter()
    raw_solution_hist: Counter[int] = Counter()
    transformed_hist: Counter[int] = Counter()

    for candidate_id in sorted(ready):
        row = ready[candidate_id]
        source_name = _require_str(row, "source_name")
        if source_name == "deepcoder-lcbv5-train":
            problem = incumbent_problems[candidate_id]
            _verify_problem(row, problem)
            reasons = ["source_has_no_reference_solution_field", "formal_reference_solution_piston_cannot_be_run"]
            dropped.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_binding_sha256": row.get("candidate_binding_sha256"),
                    "source_name": source_name,
                    "drop_reasons": reasons,
                    "backfill_required": False,
                }
            )
            dropped_sources[source_name] += 1
            dropped_reasons.update(reasons)
            continue

        candidate = candidates[candidate_id]
        canonical, quality_required = canonicalize_refresh_candidate(candidate, seed=42)
        if quality_required:
            raise ValueError(f"ready candidate unexpectedly requires quality gate: {candidate_id}")
        if row.get("origin") == "existing_incumbent":
            incumbent = incumbent_problems[candidate_id]
            if canonical_json(problem_to_mapping(canonical)) != canonical_json(problem_to_mapping(incumbent)):
                raise ValueError(f"incumbent canonical reconstruction drift: {candidate_id}")
            problem = incumbent
        else:
            problem = canonical
        _verify_problem(row, problem)
        if row.get("raw_record_sha256") is not None and candidate.raw_record_sha256 != row.get("raw_record_sha256"):
            raise ValueError(f"raw-record binding drift: {candidate_id}")

        accepted = raw_solutions[candidate_id]
        raw_solution_hist[len(accepted)] += 1
        transformed, diagnostics = _transform_all(accepted, function_name=problem.function_name)
        transform_reasons.update(str(value.get("reason")) for value in diagnostics)
        transformed_hist[len(transformed)] += 1
        if not transformed:
            reason = "no_transformable_accepted_source_solution"
            dropped.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_binding_sha256": row.get("candidate_binding_sha256"),
                    "source_name": source_name,
                    "source_record_id": candidate.source_record_id,
                    "drop_reasons": [reason],
                    "solution_transform_diagnostics": diagnostics,
                    "backfill_required": False,
                }
            )
            dropped_sources[source_name] += 1
            dropped_reasons[reason] += 1
            continue

        tests = _tests(problem)
        jobs.append(
            {
                "candidate_id": candidate_id,
                "candidate_binding_sha256": row.get("candidate_binding_sha256"),
                "source_name": source_name,
                "source_record_id": candidate.source_record_id,
                "canonical_problem_sha256": stable_json_hash(problem_to_mapping(problem)),
                "original_function_name": problem.function_name,
                "execution_function_name": REFERENCE_ENTRY,
                "test_count": len(tests),
                "tests": tests,
                "timeout_seconds": problem.metadata.time_limit_seconds,
                "memory_limit_mb": problem.metadata.memory_limit_mb,
                "accepted_source_solution_count": len(accepted),
                "transformed_source_solution_count": len(transformed),
                "transformed_source_solutions": transformed,
                "solution_transform_diagnostics": diagnostics,
                "candidate_pass_rule": protocol.get("candidate_pass_rule"),
                "infrastructure_block_rule": protocol.get("infrastructure_block_rule"),
                "backfill_on_failure": False,
            }
        )
        job_sources[source_name] += 1

    if dropped_sources["deepcoder-lcbv5-train"] != _require_int(expected, "lcbv5_without_source_reference_solution"):
        raise ValueError("lcbv5 pre-Piston drop count drift")
    if len(jobs) > _require_int(expected, "maximum_pre_piston_jobs_before_transform_failures"):
        raise ValueError("C18 Piston-job count exceeds frozen maximum")
    if len(jobs) + len(dropped) != 1276:
        raise ValueError("C18 jobs+drops do not partition the ready lane")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        jobs_sha = _write_jsonl(temporary / "piston_jobs.jsonl", jobs)
        dropped_sha = _write_jsonl(temporary / "dropped_pre_piston.jsonl", dropped)
        report: dict[str, object] = {
            "schema_version": "wp9c-ready-final-piston-preparation-v1",
            "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
            "evidence_class": "engineering_formal_piston_preparation",
            "formal_eligible": False,
            "ready_input_count": 1276,
            "piston_job_count": len(jobs),
            "pre_piston_dropped_count": len(dropped),
            "job_source_counts": dict(sorted(job_sources.items())),
            "dropped_source_counts": dict(sorted(dropped_sources.items())),
            "dropped_reason_counts": dict(sorted(dropped_reasons.items())),
            "raw_solution_count_histogram": {str(key): value for key, value in sorted(raw_solution_hist.items())},
            "transformed_solution_count_histogram": {
                str(key): value for key, value in sorted(transformed_hist.items())
            },
            "transform_reason_counts": dict(sorted(transform_reasons.items())),
            "reference_solution_protocol": dict(protocol),
            "source_bindings": {
                "deepcoder": deep_identity,
                "native": native_identity,
                "opencoder": opencoder_identity,
                "incumbent_canonical_sha256": bindings["incumbent_canonical_sha256"],
            },
            "execution_boundaries": {
                "source_solution_execution_run": False,
                "piston_run": False,
                "test_generation_run": False,
                "calibration_run": False,
                "grpo_run": False,
                "gpu_run": False,
            },
            "config_path": str(config_path),
            "config_sha256": _sha(config_path),
            "audit_script_sha256": _sha(Path(__file__)),
            "piston_config_sha256": bindings["piston_config_sha256"],
            "piston_transport_policy_sha256": bindings["piston_transport_policy_sha256"],
            "artifact_sha256": {"piston_jobs": jobs_sha, "dropped_pre_piston": dropped_sha},
            "next_gate": "manual_final_formal_piston_for_prepared_ready_jobs",
            "notes": [
                "C18 preparation executes no candidate/source solution and does not call Piston.",
                "lcbv5 rows without a source reference solution are dropped without replacement.",
                "Rows with zero transformable accepted source solutions are dropped without replacement.",
                "Infrastructure failures remain distinct from correctness failures in the manual Piston gate.",
            ],
        }
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(
            hashlib.sha256(payload.encode("utf-8")).hexdigest() + "\n",
            encoding="ascii",
        )
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
