#!/usr/bin/env python3
"""Audit novel APPS native function-call tasks with 1-7 tests, without executing code."""

from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import cast

from huggingface_hub import snapshot_download

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json, problem_reference_solution_hash, stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.prepare import load_canonical_jsonl
from code_verifier.data.refresh_dedup import RefreshDedupPolicy, classify_refresh_candidates
from code_verifier.data.refresh_sources import (
    Difficulty,
    OverlapReference,
    ReferenceClass,
    RefreshCandidate,
    _function_signature_from_row,
    _taco_function_call_tests,
    load_humanevalplus_references,
    refresh_problem_test_set_fingerprint,
    refresh_test_set_fingerprint,
)
from code_verifier.data.schema import CodeProblem, SchemaError

APPS_FIELDS = {"id", "question", "solutions", "input_output", "difficulty", "url", "starter_code"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _difficulty(value: object) -> Difficulty:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    if normalized in {"introductory", "easy"}:
        return "easy"
    if normalized in {"interview", "medium"}:
        return "medium"
    if normalized in {"competition", "hard"}:
        return "hard"
    return "unknown"


def _annotation_has_linked_node(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    return any(
        isinstance(node, ast.Name) and node.id in {"ListNode", "TreeNode", "Node"} for node in ast.walk(annotation)
    )


def _apps_class_method_contract(
    *,
    starter_code: str,
    solutions: Sequence[str],
    function_name: str,
    arities: set[int],
) -> str | None:
    def contract_from_text(text: str, *, incomplete_starter: bool) -> str | None:
        if not text.strip():
            return None
        candidates = [text + "pass\n", text] if incomplete_starter else [text]
        module: ast.Module | None = None
        for candidate in candidates:
            try:
                module = ast.parse(candidate)
                break
            except (SyntaxError, ValueError, MemoryError, RecursionError):
                continue
        if module is None:
            return None
        classes = [node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "Solution"]
        if len(classes) != 1:
            return None
        methods = [
            node for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name == function_name
        ]
        if len(methods) != 1:
            return None
        method = methods[0]
        arguments = method.args
        positional = [*arguments.posonlyargs, *arguments.args]
        if (
            len(positional) < 2
            or positional[0].arg != "self"
            or arguments.defaults
            or arguments.vararg is not None
            or arguments.kwonlyargs
            or arguments.kwarg is not None
        ):
            return None
        annotations = [argument.annotation for argument in positional[1:]]
        annotations.append(method.returns)
        if any(_annotation_has_linked_node(annotation) for annotation in annotations):
            return None
        parameter_names = [argument.arg for argument in positional[1:]]
        if arities != {len(parameter_names)}:
            return None
        return f"def {function_name}({', '.join(parameter_names)}):"

    starter_contract = contract_from_text(starter_code, incomplete_starter=True)
    if starter_contract is not None:
        return starter_contract
    solution_contracts = {
        contract
        for solution in solutions
        if (contract := contract_from_text(solution, incomplete_starter=False)) is not None
    }
    if not solution_contracts:
        return None
    return min(solution_contracts)


def _source_config(path: Path) -> dict[str, object]:
    raw = load_yaml_mapping(path)
    if raw.get("version") != "wp9c-apps-under8-augmentability-audit-v1":
        raise ValueError("under8 audit config version mismatch")
    source = raw.get("source")
    selection = raw.get("selection")
    augmentation = raw.get("augmentation")
    if not isinstance(source, dict) or not isinstance(selection, dict) or not isinstance(augmentation, dict):
        raise ValueError("under8 audit config structure is invalid")
    if source.get("adapter") != "apps_native_under8_augmentability_v1":
        raise ValueError("under8 APPS adapter identity mismatch")
    if selection.get("minimum_existing_unique_tests") != 1 or selection.get("maximum_existing_unique_tests") != 7:
        raise ValueError("under8 audit must freeze existing test range to 1..7")
    if selection.get("target_unique_tests_after_augmentation") != 8:
        raise ValueError("under8 audit target must remain 8 unique tests")
    if selection.get("minimum_nonempty_source_solutions") != 2:
        raise ValueError("under8 audit requires at least two source solutions")
    if selection.get("token_ngram_size") != 5 or selection.get("near_jaccard_threshold") != 0.90:
        raise ValueError("under8 audit dedup policy differs from frozen WP9-a policy")
    if augmentation.get("execute_source_code") is not False or augmentation.get("generate_tests") is not False:
        raise ValueError("under8 audit is static-only")
    return cast(dict[str, object], source)


def _resolve_source_file(source: Mapping[str, object]) -> tuple[Path, Path]:
    dataset_id = source.get("dataset_id")
    revision = source.get("revision")
    relative_path = source.get("file_path")
    expected_size = source.get("file_size")
    expected_sha = source.get("file_sha256")
    if (
        not isinstance(dataset_id, str)
        or not isinstance(revision, str)
        or not isinstance(relative_path, str)
        or not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or not isinstance(expected_sha, str)
    ):
        raise ValueError("under8 source identity is invalid")
    snapshot = Path(
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=[relative_path],
            local_files_only=True,
        )
    )
    if snapshot.name != revision:
        raise ValueError(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
    path = snapshot / relative_path
    if not path.is_file():
        raise ValueError(f"missing pinned APPS file: {path}")
    if path.stat().st_size != expected_size:
        raise ValueError(f"APPS size mismatch: expected {expected_size}, got {path.stat().st_size}")
    actual_sha = _sha256(path)
    if actual_sha != expected_sha:
        raise ValueError(f"APPS SHA256 mismatch: expected {expected_sha}, got {actual_sha}")
    return snapshot, path


def _apps_under8_candidates(
    path: Path,
) -> tuple[list[RefreshCandidate], dict[str, object], dict[str, int]]:
    counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    test_count_hist: Counter[int] = Counter()
    solution_count_hist: Counter[int] = Counter()
    solution_count_by_id: dict[str, int] = {}
    candidates: list[RefreshCandidate] = []
    seen_source_ids: set[int] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            counts["total_rows"] += 1
            try:
                row = loads_strict(line)
            except StrictJsonError:
                counts["invalid_json_rows"] += 1
                continue
            if not isinstance(row, dict) or set(row) != APPS_FIELDS:
                counts["schema_mismatch_rows"] += 1
                continue
            source_id = row["id"]
            if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id in seen_source_ids:
                counts["invalid_or_duplicate_source_id_rows"] += 1
                continue
            seen_source_ids.add(source_id)
            difficulty_counts[_difficulty(row["difficulty"])] += 1
            question = row["question"]
            if not isinstance(question, str) or not question.strip():
                counts["missing_question_rows"] += 1
                continue
            try:
                input_output = loads_strict(cast(str, row["input_output"]))
            except (StrictJsonError, ValueError, TypeError):
                counts["invalid_input_output_rows"] += 1
                continue
            if not isinstance(input_output, dict) or "fn_name" not in input_output:
                counts["non_function_rows"] += 1
                continue
            counts["function_rows"] += 1
            record_id = f"apps/train/{source_id}"
            try:
                parsed = _taco_function_call_tests(input_output, record_id=record_id)
            except (SchemaError, ValueError):
                counts["invalid_function_rows"] += 1
                continue
            if parsed is None:
                counts["invalid_function_rows"] += 1
                continue
            function_name, tests = parsed
            if len(tests) == 0:
                counts["function_zero_test_rows"] += 1
                continue
            if len(tests) >= 8:
                counts["function_ge8_rows"] += 1
                continue
            counts["function_1_7_rows"] += 1
            try:
                test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
            except ValueError:
                counts["duplicate_existing_test_rows"] += 1
                continue
            counts["unique_1_7_rows"] += 1
            test_count_hist[len(tests)] += 1
            try:
                solutions_value = loads_strict(cast(str, row["solutions"]))
            except (StrictJsonError, ValueError, TypeError):
                counts["invalid_solutions_rows"] += 1
                continue
            if not isinstance(solutions_value, list) or any(not isinstance(item, str) for item in solutions_value):
                counts["invalid_solutions_rows"] += 1
                continue
            solutions = [item for item in solutions_value if item.strip()]
            if len(solutions) < 2:
                counts["fewer_than_two_solutions_rows"] += 1
                continue
            counts["multi_solution_rows"] += 1
            solution_count_hist[len(solutions)] += 1
            starter = row["starter_code"] if isinstance(row["starter_code"], str) else ""
            arities = {len(cast(Sequence[object], test.input)) for test in tests}
            signature = _function_signature_from_row(
                {"problem": f"{question}\n{starter}", "solutions": solutions},
                function_name=function_name,
                arities=arities,
            )
            if signature is None:
                signature = _apps_class_method_contract(
                    starter_code=starter,
                    solutions=solutions,
                    function_name=function_name,
                    arities=arities,
                )
            if signature is None:
                counts["no_signature_rows"] += 1
                continue
            source_url = row["url"]
            if not isinstance(source_url, str) or not source_url:
                counts["invalid_source_url_rows"] += 1
                continue
            counts["augmentable_structural_rows"] += 1
            raw_hash = stable_json_hash(row)
            candidate_id = stable_json_hash(
                {
                    "protocol": "wp9c-apps-under8-augmentability-audit-v1",
                    "source_id": source_id,
                    "raw_record_sha256": raw_hash,
                }
            )
            solution_count_by_id[candidate_id] = len(solutions)
            candidates.append(
                RefreshCandidate(
                    candidate_id=candidate_id,
                    source_name="codeparrot/apps",
                    source_record_id=record_id,
                    prompt=question.strip(),
                    function_name=function_name,
                    function_signature=signature,
                    tests=tests,
                    source_url_hash=hashlib.sha256(source_url.encode("utf-8")).hexdigest(),
                    raw_reference_solution_hash=stable_json_hash(solutions),
                    difficulty=_difficulty(row["difficulty"]),
                    category=("function_call", "apps_native", "under8_augmentation_candidate"),
                    raw_record_sha256=raw_hash,
                    test_fingerprint=test_fingerprint,
                    test_validation_guard=None,
                )
            )
    report: dict[str, object] = {
        "counts": dict(sorted(counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "existing_test_count_histogram": {str(key): value for key, value in sorted(test_count_hist.items())},
        "source_solution_count_histogram": {str(key): value for key, value in sorted(solution_count_hist.items())},
        "candidate_count": len(candidates),
    }
    return candidates, report, solution_count_by_id


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


def _external_eval(refresh_config: Path) -> tuple[str, str]:
    value = load_yaml_mapping(refresh_config).get("external_eval")
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("dataset_id"), str)
        or not isinstance(value.get("revision"), str)
    ):
        raise ValueError("refresh config external_eval identity is invalid")
    return cast(str, value["dataset_id"]), cast(str, value["revision"])


def _verified_baseline(path: Path) -> tuple[dict[str, object], str]:
    digest_path = path.with_name("report.sha256")
    if not path.is_file() or not digest_path.is_file():
        raise ValueError("C4 baseline report/digest is missing")
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    expected = digest_path.read_text(encoding="ascii").strip()
    if actual != expected:
        raise ValueError(f"C4 baseline report digest mismatch: expected {expected}, got {actual}")
    report = loads_strict(payload.decode("utf-8"))
    if not isinstance(report, dict) or report.get("schema_version") != "wp9c-native-function-supply-audit-v2":
        raise ValueError("C4 baseline report schema mismatch")
    if report.get("formal_eligible") is not False:
        raise ValueError("C4 baseline must be audit-only")
    supply = report.get("wp9c_supply_context")
    if not isinstance(supply, dict) or supply.get("existing_plus_this_audit_retained") != 914:
        raise ValueError("C4 baseline qualified supply is not the expected 914")
    return cast(dict[str, object], report), actual


def audit(
    source_config: Path,
    reference_dataset_dir: Path,
    refresh_config: Path,
    baseline_native_report: Path,
    output_dir: Path,
) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    source = _source_config(source_config)
    snapshot, source_path = _resolve_source_file(source)
    candidates, source_report, solution_count_by_id = _apps_under8_candidates(source_path)
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise SystemExit("under8 candidates contain duplicate candidate IDs")
    print(
        canonical_json(
            {
                "stage": "augmentable_candidates_built",
                "source_report": source_report,
                "raw_augmentable_candidate_count": len(candidates),
            }
        ),
        flush=True,
    )

    baseline, baseline_sha = _verified_baseline(baseline_native_report)
    reference_path = reference_dataset_dir / "canonical" / "problems.jsonl"
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
    retained = [by_id[decision.candidate_id] for decision in decisions if decision.retained]
    reason_counts = Counter(decision.rejection_reason or "retained" for decision in decisions)
    class_counts = Counter(decision.overlap_class for decision in decisions)
    retained_test_hist = Counter(len(candidate.tests) for candidate in retained)
    required_added_tests = sum(8 - len(candidate.tests) for candidate in retained)
    print(
        canonical_json(
            {
                "stage": "dedup_completed",
                "retained_external_new_augmentable_count": len(retained),
                "retained_existing_test_count_histogram": {
                    str(key): value for key, value in sorted(retained_test_hist.items())
                },
                "minimum_added_test_slots_to_reach_8": required_added_tests,
                "rejection_reason_counts": dict(sorted(reason_counts.items())),
                "overlap_class_counts": dict(sorted(class_counts.items())),
            }
        ),
        flush=True,
    )

    decision_projection: list[dict[str, object]] = []
    for decision in decisions:
        row = cast(dict[str, object], asdict(decision))
        candidate = by_id[decision.candidate_id]
        row["source_record_id"] = candidate.source_record_id
        row["existing_test_count"] = len(candidate.tests)
        row["source_solution_count"] = solution_count_by_id[decision.candidate_id]
        decision_projection.append(row)
    decision_digest = hashlib.sha256(
        "".join(canonical_json(row) + "\n" for row in decision_projection).encode("utf-8")
    ).hexdigest()
    retained_projection = [
        {
            "candidate_id": candidate.candidate_id,
            "source_record_id": candidate.source_record_id,
            "function_name": candidate.function_name,
            "function_signature": candidate.function_signature,
            "existing_test_count": len(candidate.tests),
            "source_solution_count": solution_count_by_id[candidate.candidate_id],
        }
        for candidate in retained
    ]
    retained_digest = hashlib.sha256(
        "".join(canonical_json(row) + "\n" for row in retained_projection).encode("utf-8")
    ).hexdigest()
    qualified_before = 914
    required_external_new = 2775
    report: dict[str, object] = {
        "schema_version": "wp9c-apps-under8-augmentability-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "formal_blockers": [
            "test_augmentation_protocol_not_frozen",
            "augmented_tests_not_generated",
            "multi_solution_project_piston_consensus_not_run",
            "exact_B_tokenizer_context_gate_not_run",
            "retained_candidates_not_materialized",
        ],
        "source_config_path": str(source_config),
        "source_config_sha256": _sha256(source_config),
        "source_file": {
            "snapshot": str(snapshot),
            "path": str(source_path),
            "size": source_path.stat().st_size,
            "sha256": _sha256(source_path),
        },
        "source_report": source_report,
        "baseline_native_audit": {
            "report_path": str(baseline_native_report),
            "report_sha256": baseline_sha,
            "schema_version": baseline.get("schema_version"),
            "qualified_external_new_before_context_and_piston": qualified_before,
        },
        "reference_canonical_path": str(reference_path),
        "reference_canonical_sha256": _sha256(reference_path),
        "reference_counts": {
            "sft": len(sft_refs),
            "validation": len(validation_refs),
            "project_test": len(test_refs),
            "humanevalplus": len(external_refs),
        },
        "external_eval_snapshot": asdict(external_snapshot),
        "dedup_policy": {"token_ngram_size": 5, "near_jaccard_threshold": 0.90},
        "raw_augmentable_candidate_count": len(candidates),
        "retained_external_new_augmentable_count": len(retained),
        "retained_existing_test_count_histogram": {
            str(key): value for key, value in sorted(retained_test_hist.items())
        },
        "minimum_added_test_slots_to_reach_8": required_added_tests,
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "overlap_class_counts": dict(sorted(class_counts.items())),
        "decision_projection_sha256": decision_digest,
        "retained_projection_sha256": retained_digest,
        "wp9c_supply_context": {
            "required_external_new": required_external_new,
            "qualified_external_new_before_augmentation": qualified_before,
            "current_gap_before_context_and_piston": required_external_new - qualified_before,
            "hypothetical_qualified_if_every_retained_candidate_is_augmented_and_later_passes_all_gates": (
                qualified_before + len(retained)
            ),
            "remaining_gap_under_that_zero_attrition_hypothesis": max(
                0, required_external_new - qualified_before - len(retained)
            ),
        },
        "notes": [
            "This audit executes no source solution or testcase payload and generates no tests.",
            "Candidates preserve native APPS function-call interfaces and have 1-7 unique existing tests.",
            (
                "Every candidate has a recoverable static function signature and at least two non-empty "
                "accepted source solutions."
            ),
            (
                "The >=8-test quality threshold is not relaxed; this audit only measures whether later "
                "augmentation could have enough novel supply."
            ),
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
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
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--reference-dataset-dir", required=True)
    parser.add_argument("--refresh-config", default="configs/data/refresh.yaml")
    parser.add_argument("--baseline-native-report", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = audit(
        Path(args.source_config).resolve(),
        Path(args.reference_dataset_dir).resolve(),
        Path(args.refresh_config).resolve(),
        Path(args.baseline_native_report).resolve(),
        Path(args.output_dir).resolve(),
    )
    print(canonical_json(report))


if __name__ == "__main__":
    main()
