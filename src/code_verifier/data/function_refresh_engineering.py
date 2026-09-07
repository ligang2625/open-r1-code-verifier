"""Engineering-only function refresh preparation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, problem_reference_solution_hash
from code_verifier.data.prepare import load_canonical_jsonl
from code_verifier.data.refresh_dedup import RefreshDedupPolicy, classify_refresh_candidates
from code_verifier.data.refresh_sources import (
    Difficulty,
    OverlapReference,
    ReferenceClass,
    RefreshCandidate,
    RefreshSourceSpec,
    canonicalize_refresh_candidate,
    load_humanevalplus_references,
    load_lcbv5_function_call_source,
    load_opencoder_educational_source,
    load_refresh_function_call_source,
    refresh_problem_test_set_fingerprint,
)
from code_verifier.data.schema import CodeProblem, TestCase, problem_to_mapping, test_case_to_mapping

SEED = 42
MAX_PROMPT_TOKENS = 2048


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> str:
    payload = canonical_json(value) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> str:
    payload = "".join(canonical_json(row) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def _source_spec(path: Path, config_name: str) -> RefreshSourceSpec:
    raw = load_yaml_mapping(path)
    sources = raw.get("sources")
    if not isinstance(sources, list):
        raise ValueError("refresh config sources must be a list")
    lookup_name = "primeintellect" if config_name == "lcbv5" else config_name
    matches = [row for row in sources if isinstance(row, dict) and row.get("config_name") == lookup_name]
    if len(matches) != 1:
        raise ValueError(f"refresh config must contain exactly one {lookup_name} source")
    row = matches[0]
    return RefreshSourceSpec(
        source_name="deepcoder-lcbv5-train" if config_name == "lcbv5" else cast(str, row["source_name"]),
        dataset_id=cast(str, row["dataset_id"]),
        revision=cast(str, row["revision"]),
        config_name=config_name,
        split="train",
        declared_license=cast(str, row["declared_license"]),
        adapter=cast(Any, row["adapter"]),
    )


def _external_eval(path: Path) -> tuple[str, str]:
    value = load_yaml_mapping(path).get("external_eval")
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("dataset_id"), str)
        or not isinstance(value.get("revision"), str)
    ):
        raise ValueError("refresh config external_eval identity is invalid")
    return cast(str, value["dataset_id"]), cast(str, value["revision"])


def _opencoder_source_config(path: Path) -> dict[str, str]:
    raw = load_yaml_mapping(path)
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("function refresh source config must contain a sources object")
    value = sources.get("opencoder_educational")
    if not isinstance(value, dict):
        raise ValueError("function refresh source config is missing opencoder_educational")
    required = {
        "source_name",
        "dataset_id",
        "revision",
        "config_name",
        "split",
        "declared_license",
        "parquet_path",
        "parquet_sha256",
        "adapter",
    }
    if set(value) != required or any(not isinstance(value[field], str) for field in required):
        raise ValueError("opencoder_educational source identity is invalid")
    if value["config_name"] != "educational_instruct" or value["split"] != "train":
        raise ValueError("opencoder_educational must use educational_instruct/train")
    if value["adapter"] != "opencoder_assert_literal_v1":
        raise ValueError("unexpected opencoder_educational adapter")
    return {field: cast(str, value[field]) for field in required}


def _candidate_mapping(candidate: RefreshCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "source_name": candidate.source_name,
        "source_record_id": candidate.source_record_id,
        "prompt": candidate.prompt,
        "function_name": candidate.function_name,
        "function_signature": candidate.function_signature,
        "tests": [test_case_to_mapping(test) for test in candidate.tests],
        "source_url_hash": candidate.source_url_hash,
        "raw_reference_solution_hash": candidate.raw_reference_solution_hash,
        "difficulty": candidate.difficulty,
        "category": list(candidate.category),
        "raw_record_sha256": candidate.raw_record_sha256,
        "test_fingerprint": candidate.test_fingerprint,
        "test_validation_guard": candidate.test_validation_guard,
    }


def _candidate_from_mapping(row: dict[str, object]) -> RefreshCandidate:
    tests = row.get("tests")
    category = row.get("category")
    if (
        not isinstance(tests, list)
        or not isinstance(category, list)
        or any(not isinstance(item, str) for item in category)
    ):
        raise ValueError("staged candidate tests/category are invalid")
    parsed_tests: list[TestCase] = []
    for test in tests:
        if not isinstance(test, dict) or set(test) != {"input", "expected"}:
            raise ValueError("staged candidate test schema mismatch")
        parsed_tests.append(TestCase(input=test["input"], expected=test["expected"]))
    return RefreshCandidate(
        candidate_id=cast(str, row["candidate_id"]),
        source_name=cast(str, row["source_name"]),
        source_record_id=cast(str, row["source_record_id"]),
        prompt=cast(str, row["prompt"]),
        function_name=cast(str, row["function_name"]),
        function_signature=cast(str, row["function_signature"]),
        tests=tuple(parsed_tests),
        source_url_hash=cast(str | None, row.get("source_url_hash")),
        raw_reference_solution_hash=cast(str | None, row.get("raw_reference_solution_hash")),
        difficulty=cast(Difficulty, row["difficulty"]),
        category=tuple(cast(list[str], category)),
        raw_record_sha256=cast(str, row["raw_record_sha256"]),
        test_fingerprint=cast(str | None, row.get("test_fingerprint")),
        test_validation_guard=cast(str | None, row.get("test_validation_guard")),
    )


def _read_candidates(path: Path) -> list[RefreshCandidate]:
    result: list[RefreshCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("staged candidate row must be an object")
            result.append(_candidate_from_mapping(value))
    return result


def _candidate_header_from_line(line: str) -> RefreshCandidate:
    prefix, separator, _ = line.rstrip("\n").rpartition(',"tests":')
    if not separator:
        raise ValueError("staged candidate row is missing final tests field")
    value = json.loads(prefix + "}")
    if not isinstance(value, dict):
        raise ValueError("staged candidate header must be an object")
    required = {
        "candidate_id",
        "source_name",
        "source_record_id",
        "prompt",
        "function_name",
        "function_signature",
        "source_url_hash",
        "raw_reference_solution_hash",
        "difficulty",
        "category",
        "raw_record_sha256",
        "test_fingerprint",
        "test_validation_guard",
    }
    if set(value) != required or not isinstance(value.get("category"), list):
        raise ValueError("staged candidate header schema mismatch")
    return RefreshCandidate(
        candidate_id=cast(str, value["candidate_id"]),
        source_name=cast(str, value["source_name"]),
        source_record_id=cast(str, value["source_record_id"]),
        prompt=cast(str, value["prompt"]),
        function_name=cast(str, value["function_name"]),
        function_signature=cast(str, value["function_signature"]),
        tests=(),
        source_url_hash=cast(str | None, value["source_url_hash"]),
        raw_reference_solution_hash=cast(str | None, value["raw_reference_solution_hash"]),
        difficulty=cast(Difficulty, value["difficulty"]),
        category=tuple(cast(list[str], value["category"])),
        raw_record_sha256=cast(str, value["raw_record_sha256"]),
        test_fingerprint=cast(str | None, value["test_fingerprint"]),
        test_validation_guard=cast(str | None, value["test_validation_guard"]),
    )


def _read_candidate_headers(path: Path) -> list[RefreshCandidate]:
    result: list[RefreshCandidate] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                result.append(_candidate_header_from_line(line))
    return result


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


def _stage_source(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    refresh_config = Path(args.refresh_config).resolve()
    spec = _source_spec(refresh_config, args.config_name)
    if args.config_name == "lcbv5":
        snapshot, candidates = load_lcbv5_function_call_source(
            spec,
            cache_dir=None,
            shard_index=args.lcb_shard_index,
        )
    else:
        snapshot, candidates = load_refresh_function_call_source(spec, cache_dir=None)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records_sha = _write_jsonl(
            temporary / "candidates.jsonl",
            [_candidate_mapping(candidate) for candidate in candidates],
        )
        manifest = {
            "schema_version": "wp9c-function-refresh-stage-v1",
            "evidence_class": "engineering_data",
            "source": asdict(snapshot),
            "source_shard_index": args.lcb_shard_index if args.config_name == "lcbv5" else None,
            "candidate_count": len(candidates),
            "records_digest": records_sha,
            "quality_safe_ge8_count": sum(len(candidate.tests) >= 8 for candidate in candidates),
            "quality_gate_lt8_count": sum(len(candidate.tests) < 8 for candidate in candidates),
        }
        _write_json(temporary / "stage_manifest.json", manifest)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(canonical_json(manifest))


def _stage_opencoder(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    source_config = Path(args.source_config).resolve()
    source = _opencoder_source_config(source_config)
    snapshot, candidates = load_opencoder_educational_source(
        dataset_id=source["dataset_id"],
        revision=source["revision"],
        declared_license=source["declared_license"],
        cache_dir=None,
        expected_parquet_sha256=source["parquet_sha256"],
    )
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records_sha = _write_jsonl(
            temporary / "candidates.jsonl",
            [_candidate_mapping(candidate) for candidate in candidates],
        )
        manifest = {
            "schema_version": "wp9c-function-refresh-stage-v1",
            "evidence_class": "engineering_data",
            "source_config_path": str(source_config),
            "source_config_digest": _sha(source_config),
            "source": asdict(snapshot),
            "candidate_count": len(candidates),
            "records_digest": records_sha,
            "quality_safe_ge8_count": sum(len(candidate.tests) >= 8 for candidate in candidates),
            "quality_gate_lt8_count": sum(len(candidate.tests) < 8 for candidate in candidates),
        }
        _write_json(temporary / "stage_manifest.json", manifest)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(canonical_json(manifest))


def _finalize(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    refresh_config = Path(args.refresh_config).resolve()
    candidates: list[RefreshCandidate] = []
    stage_bindings: list[dict[str, object]] = []
    for stage_text in args.stage_dir:
        stage_dir = Path(stage_text).resolve()
        manifest_path = stage_dir / "stage_manifest.json"
        candidate_path = stage_dir / "candidates.jsonl"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("records_digest") != _sha(candidate_path):
            raise SystemExit(f"staged candidate digest mismatch: {stage_dir}")
        loaded = _read_candidates(candidate_path)
        if manifest.get("candidate_count") != len(loaded):
            raise SystemExit(f"staged candidate count mismatch: {stage_dir}")
        candidates.extend(loaded)
        stage_bindings.append(
            {
                "stage_dir": str(stage_dir),
                "manifest_digest": _sha(manifest_path),
                "records_digest": _sha(candidate_path),
                "candidate_count": len(loaded),
            }
        )
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise SystemExit("staged function candidates contain duplicate candidate IDs")

    reference_path = Path(args.reference_dataset_dir).resolve() / "canonical" / "problems.jsonl"
    reference_problems = load_canonical_jsonl(reference_path)
    sft_refs = [_reference(problem, "sft") for problem in reference_problems if problem.split == "train"]
    validation_refs = [
        _reference(problem, "validation") for problem in reference_problems if problem.split == "validation"
    ]
    test_refs = [_reference(problem, "project_test") for problem in reference_problems if problem.split == "test"]
    external_dataset_id, external_revision = _external_eval(refresh_config)
    external_snapshot, external_refs = load_humanevalplus_references(
        dataset_id=external_dataset_id,
        revision=external_revision,
        cache_dir=None,
    )
    policy = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)
    decisions = classify_refresh_candidates(
        candidates,
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=test_refs,
        external_eval_references=external_refs,
        policy=policy,
    )
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    retained = [by_id[decision.candidate_id] for decision in decisions if decision.retained]

    retained_rows: list[Mapping[str, object]] = []
    quality_rows: list[Mapping[str, object]] = []
    provenance_rows: list[dict[str, object]] = []
    for candidate in retained:
        problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=SEED)
        mapping = problem_to_mapping(problem)
        retained_rows.append(mapping)
        provenance_rows.append(
            {
                "problem_id": problem.problem_id,
                "source_name": candidate.source_name,
                "source_record_id": candidate.source_record_id,
                "raw_record_digest": candidate.raw_record_sha256,
                "test_fingerprint": candidate.test_fingerprint,
                "function_name": candidate.function_name,
                "function_signature": candidate.function_signature,
                "test_count": len(candidate.tests),
                "quality_gate_required": quality_gate_required,
            }
        )
        if not quality_gate_required:
            quality_rows.append(mapping)

    reason_counts = Counter(decision.rejection_reason or "retained" for decision in decisions)
    class_counts = Counter(decision.overlap_class for decision in decisions)
    retained_sources = Counter(candidate.source_name for candidate in retained)
    quality_ids = {cast(str, row["problem_id"]) for row in quality_rows}
    quality_sources = Counter(by_id[problem_id].source_name for problem_id in quality_ids)
    decision_rows: list[dict[str, object]] = []
    for decision in decisions:
        row = asdict(decision)
        row["source_name"] = by_id[decision.candidate_id].source_name
        row["source_record_id"] = by_id[decision.candidate_id].source_record_id
        decision_rows.append(row)

    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        retained_digest = _write_jsonl(temporary / "canonical" / "retained_external_new.jsonl", retained_rows)
        quality_digest = _write_jsonl(temporary / "canonical" / "quality_safe_ge8.jsonl", quality_rows)
        provenance_digest = _write_jsonl(temporary / "manifest" / "candidate_provenance.jsonl", provenance_rows)
        decisions_digest = _write_jsonl(temporary / "manifest" / "dedup_decisions.jsonl", decision_rows)
        summary = {
            "schema_version": "wp9c-function-refresh-engineering-v1",
            "evidence_class": "engineering_data",
            "seed": SEED,
            "source_stage_bindings": stage_bindings,
            "reference_canonical_path": str(reference_path),
            "reference_canonical_digest": _sha(reference_path),
            "reference_counts": {
                "sft": len(sft_refs),
                "validation": len(validation_refs),
                "project_test": len(test_refs),
                "external_eval": len(external_refs),
            },
            "external_eval_snapshot": asdict(external_snapshot),
            "dedup_policy": {"token_ngram_size": 5, "near_jaccard_threshold": 0.90},
            "raw_function_candidate_count": len(candidates),
            "dedup_retained_external_new_count": len(retained),
            "quality_safe_ge8_count": len(quality_rows),
            "rejection_reason_counts": dict(sorted(reason_counts.items())),
            "overlap_class_counts": dict(sorted(class_counts.items())),
            "retained_source_counts": dict(sorted(retained_sources.items())),
            "quality_safe_source_counts": dict(sorted(quality_sources.items())),
            "artifact_digests": {
                "retained_external_new": retained_digest,
                "quality_safe_ge8": quality_digest,
                "candidate_provenance": provenance_digest,
                "dedup_decisions": decisions_digest,
            },
        }
        _write_json(temporary / "reports" / "summary.json", summary)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(canonical_json(summary))


def _light_finalize(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    refresh_config = Path(args.refresh_config).resolve()
    candidates: list[RefreshCandidate] = []
    candidate_paths: list[Path] = []
    stage_bindings: list[dict[str, object]] = []
    for stage_text in args.stage_dir:
        stage_dir = Path(stage_text).resolve()
        manifest_path = stage_dir / "stage_manifest.json"
        candidate_path = stage_dir / "candidates.jsonl"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("records_digest") != _sha(candidate_path):
            raise SystemExit(f"staged candidate digest mismatch: {stage_dir}")
        loaded = _read_candidate_headers(candidate_path)
        if manifest.get("candidate_count") != len(loaded):
            raise SystemExit(f"staged candidate count mismatch: {stage_dir}")
        candidates.extend(loaded)
        candidate_paths.append(candidate_path)
        stage_bindings.append(
            {
                "stage_dir": str(stage_dir),
                "manifest_digest": _sha(manifest_path),
                "records_digest": _sha(candidate_path),
                "candidate_count": len(loaded),
            }
        )
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise SystemExit("staged function candidates contain duplicate candidate IDs")

    reference_path = Path(args.reference_dataset_dir).resolve() / "canonical" / "problems.jsonl"
    reference_problems = load_canonical_jsonl(reference_path)
    sft_refs = [_reference(problem, "sft") for problem in reference_problems if problem.split == "train"]
    validation_refs = [
        _reference(problem, "validation") for problem in reference_problems if problem.split == "validation"
    ]
    test_refs = [_reference(problem, "project_test") for problem in reference_problems if problem.split == "test"]
    external_dataset_id, external_revision = _external_eval(refresh_config)
    external_snapshot, external_refs = load_humanevalplus_references(
        dataset_id=external_dataset_id,
        revision=external_revision,
        cache_dir=None,
    )
    decisions = classify_refresh_candidates(
        candidates,
        sft_references=sft_refs,
        validation_references=validation_refs,
        project_test_references=test_refs,
        external_eval_references=external_refs,
        policy=RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90),
    )
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    retained_ids = {decision.candidate_id for decision in decisions if decision.retained}
    decision_rows: list[dict[str, object]] = []
    for decision in decisions:
        row = asdict(decision)
        row["source_name"] = by_id[decision.candidate_id].source_name
        row["source_record_id"] = by_id[decision.candidate_id].source_record_id
        decision_rows.append(row)
    retained_id_rows = [
        {
            "candidate_id": decision.candidate_id,
            "source_name": by_id[decision.candidate_id].source_name,
            "source_record_id": by_id[decision.candidate_id].source_record_id,
        }
        for decision in decisions
        if decision.retained
    ]

    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        decisions_digest = _write_jsonl(temporary / "manifest" / "dedup_decisions.jsonl", decision_rows)
        retained_ids_digest = _write_jsonl(temporary / "manifest" / "retained_ids.jsonl", retained_id_rows)
        retained_path = temporary / "candidates" / "retained_candidates.jsonl"
        retained_path.parent.mkdir(parents=True, exist_ok=True)
        retained_digest = hashlib.sha256()
        retained_count = 0
        with retained_path.open("w", encoding="utf-8", newline="") as output:
            for candidate_path in candidate_paths:
                with candidate_path.open("r", encoding="utf-8", newline="") as source:
                    for line in source:
                        if not line.strip():
                            continue
                        candidate_id = _candidate_header_from_line(line).candidate_id
                        if candidate_id not in retained_ids:
                            continue
                        output.write(line)
                        retained_digest.update(line.encode("utf-8"))
                        retained_count += 1
        if retained_count != len(retained_ids):
            raise ValueError("retained candidate copy count mismatch")
        reason_counts = Counter(decision.rejection_reason or "retained" for decision in decisions)
        class_counts = Counter(decision.overlap_class for decision in decisions)
        retained_sources = Counter(by_id[candidate_id].source_name for candidate_id in retained_ids)
        summary = {
            "schema_version": "wp9c-function-refresh-light-dedup-v1",
            "evidence_class": "engineering_data",
            "source_stage_bindings": stage_bindings,
            "reference_canonical_path": str(reference_path),
            "reference_canonical_digest": _sha(reference_path),
            "reference_counts": {
                "sft": len(sft_refs),
                "validation": len(validation_refs),
                "project_test": len(test_refs),
                "external_eval": len(external_refs),
            },
            "external_eval_snapshot": asdict(external_snapshot),
            "dedup_policy": {"token_ngram_size": 5, "near_jaccard_threshold": 0.90},
            "raw_candidate_count": len(candidates),
            "retained_external_new_count": len(retained_ids),
            "rejection_reason_counts": dict(sorted(reason_counts.items())),
            "overlap_class_counts": dict(sorted(class_counts.items())),
            "retained_source_counts": dict(sorted(retained_sources.items())),
            "artifact_digests": {
                "dedup_decisions": decisions_digest,
                "retained_ids": retained_ids_digest,
                "retained_candidates": retained_digest.hexdigest(),
            },
        }
        _write_json(temporary / "reports" / "summary.json", summary)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(canonical_json(summary))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage = subparsers.add_parser("stage-source")
    stage.add_argument("--config-name", choices=("primeintellect", "taco", "lcbv5"), required=True)
    stage.add_argument("--refresh-config", default="configs/data/refresh.yaml")
    stage.add_argument("--lcb-shard-index", type=int)
    stage.add_argument("--output-dir", required=True)
    stage.set_defaults(func=_stage_source)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--stage-dir", action="append", required=True)
    finalize.add_argument("--reference-dataset-dir", required=True)
    finalize.add_argument("--refresh-config", default="configs/data/refresh.yaml")
    finalize.add_argument("--output-dir", required=True)
    finalize.set_defaults(func=_finalize)
    opencoder = subparsers.add_parser("stage-opencoder")
    opencoder.add_argument(
        "--source-config",
        default="configs/data/wp9c-function-refresh-sources.yaml",
    )
    opencoder.add_argument("--output-dir", required=True)
    opencoder.set_defaults(func=_stage_opencoder)
    light = subparsers.add_parser("light-finalize")
    light.add_argument("--stage-dir", action="append", required=True)
    light.add_argument("--reference-dataset-dir", required=True)
    light.add_argument("--refresh-config", default="configs/data/refresh.yaml")
    light.add_argument("--output-dir", required=True)
    light.set_defaults(func=_light_finalize)
    return parser


def main() -> None:
    args = _parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
