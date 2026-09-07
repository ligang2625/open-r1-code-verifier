#!/usr/bin/env python3
"""Audit native APPS/LeetCode function-level supply without executing source code."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import keyword
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
from code_verifier.data.schema import CodeProblem, SchemaError, TestCase, validate_json_value

APPS_FIELDS = {
    "id",
    "question",
    "solutions",
    "input_output",
    "difficulty",
    "url",
    "starter_code",
}
LEETCODE_FIELDS = {
    "parallel_id",
    "title",
    "cpp",
    "java",
    "python",
    "sql",
    "typescript",
    "difficulty",
    "input_output",
    "problem_description",
    "entry_point",
    "prompt",
    "query",
    "response",
    "tags",
    "estimated_date",
    "task_id",
    "test",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_arrow_row_hash(row: Mapping[str, object]) -> str:
    """Hash a PyArrow row after tagging non-JSON scalar types deterministically."""
    normalized: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, dt.datetime):
            normalized[key] = {
                "__arrow_type__": "timestamp_ms",
                "value": value.isoformat(timespec="milliseconds"),
            }
        else:
            normalized[key] = value
    return stable_json_hash(normalized)


def _source_configs(path: Path) -> dict[str, dict[str, object]]:
    raw = load_yaml_mapping(path)
    sources = raw.get("sources")
    if not isinstance(sources, dict) or set(sources) != {"apps_train", "leetcode_merged"}:
        raise ValueError("native function supply config must define apps_train and leetcode_merged")
    result: dict[str, dict[str, object]] = {}
    for key, value in sources.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError("native function supply source config is invalid")
        result[key] = cast(dict[str, object], value)
    return result


def _resolve_source_file(source: Mapping[str, object]) -> tuple[Path, Path]:
    dataset_id = source.get("dataset_id")
    revision = source.get("revision")
    relative_path = source.get("parquet_or_json_path")
    expected_sha = source.get("file_sha256")
    if not all(isinstance(value, str) and value for value in (dataset_id, revision, relative_path, expected_sha)):
        raise ValueError("source identity is incomplete")
    snapshot = Path(
        snapshot_download(
            repo_id=cast(str, dataset_id),
            repo_type="dataset",
            revision=cast(str, revision),
            allow_patterns=["README.md", cast(str, relative_path)],
            local_files_only=True,
        )
    ).resolve()
    if snapshot.name != revision:
        raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
    path = snapshot / cast(str, relative_path)
    if not path.is_file():
        raise SystemExit(f"missing pinned source file: {path}")
    expected_size = source.get("file_size")
    if expected_size is not None and (not isinstance(expected_size, int) or path.stat().st_size != expected_size):
        raise SystemExit(f"pinned source size mismatch: {path}")
    if _sha256(path) != expected_sha:
        raise SystemExit(f"pinned source SHA256 mismatch: {path}")
    return snapshot, path


def _json_value(value: object) -> object:
    if isinstance(value, str):
        return loads_strict(value)
    return value


def _difficulty(value: object) -> Difficulty:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().casefold().replace("_", " ")
    if normalized in {"easy", "introductory"}:
        return "easy"
    if normalized in {"medium", "interview", "medium hard"}:
        return "medium"
    if normalized in {"hard", "competition", "very hard"}:
        return "hard"
    return "unknown"


def _apps_candidates(path: Path) -> tuple[list[RefreshCandidate], dict[str, object]]:
    counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    candidates: list[RefreshCandidate] = []
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
            difficulty_counts[_difficulty(row["difficulty"])] += 1
            question = row["question"]
            if not isinstance(question, str) or not question.strip():
                counts["missing_question_rows"] += 1
                continue
            try:
                input_output = _json_value(row["input_output"])
            except (StrictJsonError, ValueError):
                counts["invalid_input_output_rows"] += 1
                continue
            if not isinstance(input_output, dict) or "fn_name" not in input_output:
                counts["non_function_rows"] += 1
                continue
            counts["function_rows"] += 1
            source_id = row["id"]
            if not isinstance(source_id, int) or isinstance(source_id, bool):
                counts["invalid_source_id_rows"] += 1
                continue
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
            if len(tests) < 8:
                counts["function_lt8_rows"] += 1
                continue
            counts["function_ge8_rows"] += 1
            try:
                test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
            except ValueError:
                counts["duplicate_test_rows"] += 1
                continue
            counts["unique_ge8_rows"] += 1
            try:
                solutions_value = _json_value(row["solutions"])
            except (StrictJsonError, ValueError):
                counts["invalid_solutions_rows"] += 1
                continue
            if not isinstance(solutions_value, list) or any(not isinstance(item, str) for item in solutions_value):
                counts["invalid_solutions_rows"] += 1
                continue
            solutions = [item for item in solutions_value if item.strip()]
            if not solutions:
                counts["missing_solution_rows"] += 1
                continue
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
                counts["class_solution_signature_rows"] += 1
            else:
                counts["direct_signature_rows"] += 1
            counts["signature_safe_rows"] += 1
            source_url = row["url"]
            if not isinstance(source_url, str) or not source_url:
                counts["invalid_source_url_rows"] += 1
                continue
            raw_hash = stable_json_hash(row)
            source_url_hash = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
            candidates.append(
                RefreshCandidate(
                    candidate_id=stable_json_hash(
                        {
                            "protocol": "wp9c-native-apps-audit-v2",
                            "source_id": source_id,
                            "raw_record_sha256": raw_hash,
                        }
                    ),
                    source_name="codeparrot/apps",
                    source_record_id=record_id,
                    prompt=question.strip(),
                    function_name=function_name,
                    function_signature=signature,
                    tests=tests,
                    source_url_hash=source_url_hash,
                    raw_reference_solution_hash=stable_json_hash(solutions),
                    difficulty=_difficulty(row["difficulty"]),
                    category=("function_call", "apps_native"),
                    raw_record_sha256=raw_hash,
                    test_fingerprint=test_fingerprint,
                    test_validation_guard=None,
                )
            )
    return candidates, {
        "counts": dict(sorted(counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "candidate_count": len(candidates),
    }


def _apps_class_method_contract(
    *,
    starter_code: str,
    solutions: Sequence[str],
    function_name: str,
    arities: set[int],
) -> str | None:
    """Recover a conservative top-level contract from APPS class Solution methods."""

    def contract_from_text(text: str, *, incomplete_starter: bool) -> str | None:
        if not text.strip():
            return None
        candidates = [text + "pass\n", text] if incomplete_starter else [text]
        parsed: ast.Module | None = None
        for candidate in candidates:
            try:
                parsed = ast.parse(candidate)
                break
            except (SyntaxError, ValueError, MemoryError, RecursionError):
                continue
        if parsed is None:
            return None
        classes = [node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == "Solution"]
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


def _literal_value(node: ast.AST, *, field: str) -> object:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, MemoryError, RecursionError) as error:
        raise ValueError(f"{field} is not a safe literal") from error
    return validate_json_value(value, field_path=field)


def _parse_expected_text(text: object, *, field: str) -> object:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{field} must be non-empty text")
    try:
        node = ast.parse(text.strip(), mode="eval").body
        return _literal_value(node, field=field)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        try:
            value = loads_strict(text)
        except StrictJsonError as error:
            raise ValueError(f"{field} is neither a Python literal nor strict JSON") from error
        return validate_json_value(value, field_path=field)


def _annotation_has_linked_node(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    return any(
        isinstance(node, ast.Name) and node.id in {"ListNode", "TreeNode", "Node"} for node in ast.walk(annotation)
    )


def _leetcode_method_contract(code: object, entry_point: object) -> tuple[str, list[str]] | None:
    if not isinstance(code, str) or not code.strip() or not isinstance(entry_point, str):
        return None
    prefix = "Solution()."
    if not entry_point.startswith(prefix):
        return None
    function_name = entry_point[len(prefix) :]
    if not function_name.isidentifier() or keyword.iskeyword(function_name):
        return None
    try:
        module = ast.parse(code)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    matches: list[ast.FunctionDef] = []
    for node in module.body:
        if not isinstance(node, ast.ClassDef) or node.name != "Solution":
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name == function_name:
                matches.append(child)
    if len(matches) != 1:
        return None
    method = matches[0]
    arguments = method.args
    positional = [*arguments.posonlyargs, *arguments.args]
    if (
        not positional
        or positional[0].arg not in {"self", "cls"}
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
    if not parameter_names or len(arguments.defaults) > len(parameter_names):
        return None
    return f"def {function_name}({', '.join(parameter_names)}):", parameter_names


def _leetcode_tests(
    value: object,
    *,
    parameter_names: list[str],
    record_id: str,
) -> tuple[TestCase, ...] | None:
    if not isinstance(value, list) or len(value) < 8:
        return None
    tests: list[TestCase] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"input", "output"}:
            return None
        input_text = item["input"]
        if not isinstance(input_text, str) or not input_text.strip():
            return None
        try:
            expression = ast.parse(f"__probe__({input_text})", mode="eval").body
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            return None
        if (
            not isinstance(expression, ast.Call)
            or not isinstance(expression.func, ast.Name)
            or expression.func.id != "__probe__"
            or expression.args
            or any(keyword_item.arg is None for keyword_item in expression.keywords)
        ):
            return None
        keyword_map = {keyword_item.arg: keyword_item.value for keyword_item in expression.keywords}
        if len(keyword_map) != len(expression.keywords) or set(keyword_map) != set(parameter_names):
            return None
        try:
            arguments = tuple(
                _literal_value(keyword_map[name], field=f"{record_id}.tests[{index}].{name}")
                for name in parameter_names
            )
            expected = _parse_expected_text(item["output"], field=f"{record_id}.tests[{index}].expected")
        except (SchemaError, ValueError):
            return None
        tests.append(TestCase(input=arguments, expected=expected))
    return tuple(tests)


def _leetcode_candidates(path: Path) -> tuple[list[RefreshCandidate], dict[str, object]]:
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(path)
    columns = parquet_file.schema_arrow.names
    if set(columns) != LEETCODE_FIELDS:
        raise SystemExit(f"LeetCode merged schema drift: {columns}")
    counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    candidates: list[RefreshCandidate] = []
    for batch in parquet_file.iter_batches(batch_size=128, columns=columns):
        for row in batch.to_pylist():
            row_index = counts["total_rows"]
            counts["total_rows"] += 1
            if not isinstance(row, Mapping) or set(row) != LEETCODE_FIELDS:
                counts["schema_mismatch_rows"] += 1
                continue
            difficulty_counts[_difficulty(row["difficulty"])] += 1
            problem = row["problem_description"]
            input_output = row["input_output"]
            if not isinstance(problem, str) or not problem.strip() or not isinstance(input_output, list):
                counts["missing_metadata_or_tests_rows"] += 1
                continue
            counts["rows_with_metadata_tests"] += 1
            if len(input_output) < 8:
                counts["lt8_rows"] += 1
                continue
            counts["ge8_raw_rows"] += 1
            contract = _leetcode_method_contract(row["python"], row["entry_point"])
            if contract is None:
                counts["unsupported_reference_contract_rows"] += 1
                continue
            signature, parameter_names = contract
            function_name = signature.split("(", 1)[0].removeprefix("def ")
            record_id = f"leetcode-solutions/train/{row_index}"
            tests = _leetcode_tests(input_output, parameter_names=parameter_names, record_id=record_id)
            if tests is None:
                counts["unsafe_or_unsupported_test_rows"] += 1
                continue
            try:
                test_fingerprint = refresh_test_set_fingerprint(tests, context=record_id)
            except ValueError:
                counts["duplicate_test_rows"] += 1
                continue
            counts["signature_safe_unique_ge8_rows"] += 1
            raw_hash = _stable_arrow_row_hash(row)
            python_solution = cast(str, row["python"])
            tags = row["tags"] if isinstance(row["tags"], list) else []
            safe_tags = tuple(item for item in tags if isinstance(item, str) and item.strip())
            candidates.append(
                RefreshCandidate(
                    candidate_id=stable_json_hash(
                        {
                            "protocol": "wp9c-native-leetcode-audit-v1",
                            "parallel_id": row["parallel_id"],
                            "raw_record_sha256": raw_hash,
                        }
                    ),
                    source_name="tkeskin/leetcode-solutions",
                    source_record_id=record_id,
                    prompt=problem.strip(),
                    function_name=function_name,
                    function_signature=signature,
                    tests=tests,
                    source_url_hash=None,
                    raw_reference_solution_hash=stable_json_hash([python_solution]),
                    difficulty=_difficulty(row["difficulty"]),
                    category=("function_call", "leetcode", *safe_tags),
                    raw_record_sha256=raw_hash,
                    test_fingerprint=test_fingerprint,
                    test_validation_guard=None,
                )
            )
    return candidates, {
        "counts": dict(sorted(counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "candidate_count": len(candidates),
    }


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


def audit(
    source_config: Path,
    reference_dataset_dir: Path,
    refresh_config: Path,
    output_dir: Path,
) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    source_configs = _source_configs(source_config)
    source_files: dict[str, dict[str, object]] = {}
    source_reports: dict[str, dict[str, object]] = {}

    apps_snapshot, apps_path = _resolve_source_file(source_configs["apps_train"])
    apps_candidates, apps_report = _apps_candidates(apps_path)
    source_reports["apps_train"] = apps_report
    source_files["apps_train"] = {
        "snapshot": str(apps_snapshot),
        "path": str(apps_path),
        "size": apps_path.stat().st_size,
        "sha256": _sha256(apps_path),
    }

    leetcode_snapshot, leetcode_path = _resolve_source_file(source_configs["leetcode_merged"])
    leetcode_candidates, leetcode_report = _leetcode_candidates(leetcode_path)
    source_reports["leetcode_merged"] = leetcode_report
    source_files["leetcode_merged"] = {
        "snapshot": str(leetcode_snapshot),
        "path": str(leetcode_path),
        "size": leetcode_path.stat().st_size,
        "sha256": _sha256(leetcode_path),
    }

    candidates = [*apps_candidates, *leetcode_candidates]
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise SystemExit("native supply audit candidates contain duplicate candidate IDs")
    print(
        canonical_json(
            {
                "stage": "source_candidates_built",
                "apps": apps_report,
                "leetcode": leetcode_report,
                "raw_structural_candidate_count": len(candidates),
            }
        ),
        flush=True,
    )

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
    retained_sources = Counter(candidate.source_name for candidate in retained)
    print(
        canonical_json(
            {
                "stage": "dedup_completed",
                "retained_external_new_count": len(retained),
                "retained_source_counts": dict(sorted(retained_sources.items())),
                "rejection_reason_counts": dict(sorted(reason_counts.items())),
                "overlap_class_counts": dict(sorted(class_counts.items())),
            }
        ),
        flush=True,
    )

    decision_projection: list[dict[str, object]] = []
    for decision in decisions:
        row = cast(dict[str, object], asdict(decision))
        row["source_name"] = by_id[decision.candidate_id].source_name
        row["source_record_id"] = by_id[decision.candidate_id].source_record_id
        decision_projection.append(row)
    decision_digest = hashlib.sha256(
        "".join(canonical_json(row) + "\n" for row in decision_projection).encode("utf-8")
    ).hexdigest()
    retained_projection = [
        {
            "candidate_id": candidate.candidate_id,
            "source_name": candidate.source_name,
            "source_record_id": candidate.source_record_id,
            "test_count": len(candidate.tests),
            "function_name": candidate.function_name,
            "function_signature": candidate.function_signature,
        }
        for candidate in retained
    ]
    retained_digest = hashlib.sha256(
        "".join(canonical_json(row) + "\n" for row in retained_projection).encode("utf-8")
    ).hexdigest()

    report: dict[str, object] = {
        "schema_version": "wp9c-native-function-supply-audit-v2",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "formal_blockers": [
            "exact_B_tokenizer_context_gate_not_run",
            "project_piston_reference_solution_validation_not_run",
            "retained_candidates_not_materialized",
            "source_specific_reference_solution_transformation_not_frozen",
        ],
        "source_config_path": str(source_config),
        "source_config_sha256": _sha256(source_config),
        "source_files": source_files,
        "source_reports": source_reports,
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
        "raw_structural_candidate_count": len(candidates),
        "retained_external_new_count": len(retained),
        "retained_source_counts": dict(sorted(retained_sources.items())),
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "overlap_class_counts": dict(sorted(class_counts.items())),
        "decision_projection_sha256": decision_digest,
        "retained_projection_sha256": retained_digest,
        "wp9c_supply_context": {
            "required_external_new": 2775,
            "existing_structural_external_new": 654,
            "additional_needed_before_this_audit": 2121,
            "existing_plus_this_audit_retained": 654 + len(retained),
            "remaining_gap_before_context_and_piston": max(0, 2775 - 654 - len(retained)),
        },
        "notes": [
            "No source solution or testcase payload is executed by this audit.",
            (
                "APPS admits only native fn_name function-call rows with at least eight unique tests "
                "and a recoverable direct signature."
            ),
            (
                "LeetCode admits only literal/JSON arguments and expected values matching one class "
                "Solution method; ListNode/TreeNode/Node annotation contracts fail closed."
            ),
            (
                "Dedup is run jointly across both sources and against frozen SFT, validation, "
                "project test, and HumanEvalPlus references."
            ),
        ],
    }

    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(
            hashlib.sha256(payload.encode()).hexdigest() + "\n",
            encoding="ascii",
        )
        output_dir.parent.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = audit(
        Path(args.source_config).resolve(),
        Path(args.reference_dataset_dir).resolve(),
        Path(args.refresh_config).resolve(),
        Path(args.output_dir).resolve(),
    )
    print(canonical_json(report))


if __name__ == "__main__":
    main()
