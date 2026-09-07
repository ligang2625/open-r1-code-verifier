#!/usr/bin/env python3
"""Audit one pinned BAAI/TACO train parquet shard for function-call supply."""

from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from huggingface_hub import snapshot_download

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.refresh_sources import (
    _function_signature_from_row,
    _taco_function_call_tests,
    refresh_test_set_fingerprint,
)

EXPECTED_FIELDS = {
    "question",
    "solutions",
    "starter_code",
    "input_output",
    "difficulty",
    "raw_tags",
    "name",
    "source",
    "tags",
    "skill_types",
    "url",
    "Expected Auxiliary Space",
    "time_limit",
    "date",
    "picture_num",
    "memory_limit",
    "Expected Time Complexity",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _config(path: Path) -> dict[str, object]:
    raw = load_yaml_mapping(path)
    source = raw.get("source")
    if not isinstance(source, dict):
        raise ValueError("TACO audit config must contain source mapping")
    required = {
        "source_name",
        "dataset_id",
        "revision",
        "config_name",
        "split",
        "declared_license",
        "provenance_note",
        "shard_path",
        "shard_size",
        "shard_sha256",
        "adapter",
    }
    if set(source) != required or source.get("adapter") != "taco_function_call_audit_v1":
        raise ValueError("TACO audit source config mismatch")
    return cast(dict[str, object], source)


def _solutions(value: object) -> list[str] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = loads_strict(value)
    except StrictJsonError:
        return None
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        return None
    result = [item for item in parsed if item.strip()]
    return result or None


def _class_method_supports_arities(text: str, function_name: str, arities: set[int]) -> bool:
    try:
        module = ast.parse(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return False
    matches = []
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if not isinstance(child, ast.FunctionDef) or child.name != function_name:
                continue
            arguments = child.args
            positional = [*arguments.posonlyargs, *arguments.args]
            if (
                not positional
                or positional[0].arg not in {"self", "cls"}
                or arguments.vararg is not None
                or arguments.kwonlyargs
                or arguments.kwarg is not None
            ):
                continue
            positional = positional[1:]
            defaults = list(arguments.defaults)
            if len(defaults) > len(positional):
                continue
            required = len(positional) - len(defaults)
            maximum = len(positional)
            if all(required <= arity <= maximum for arity in arities):
                matches.append(child)
    return len(matches) == 1


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    source = _config(config_path)
    dataset_id = cast(str, source["dataset_id"])
    revision = cast(str, source["revision"])
    shard_path = cast(str, source["shard_path"])
    expected_size = cast(int, source["shard_size"])
    expected_sha = cast(str, source["shard_sha256"])

    snapshot = Path(
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=["README.md", shard_path],
            local_files_only=True,
        )
    ).resolve()
    if snapshot.name != revision:
        raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
    parquet_path = snapshot / shard_path
    if not parquet_path.is_file():
        raise SystemExit(f"missing pinned TACO shard: {parquet_path}")
    if parquet_path.stat().st_size != expected_size or _sha256(parquet_path) != expected_sha:
        raise SystemExit("pinned TACO shard size/SHA256 mismatch")

    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(parquet_path)
    columns = parquet_file.schema_arrow.names
    if set(columns) != EXPECTED_FIELDS:
        raise SystemExit(f"TACO schema drift: expected {sorted(EXPECTED_FIELDS)}, got {columns}")

    counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    function_source_counts: Counter[str] = Counter()
    ge8_source_counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    ge8_difficulty_counts: Counter[str] = Counter()
    test_counts: list[int] = []

    for batch in parquet_file.iter_batches(batch_size=128, columns=columns):
        for row_index, row in enumerate(batch.to_pylist(), start=counts["total_rows"]):
            counts["total_rows"] += 1
            if not isinstance(row, Mapping) or set(row) != EXPECTED_FIELDS:
                raise SystemExit(f"row {row_index}: TACO row schema drift")
            source_name = row["source"] if isinstance(row["source"], str) else "<invalid>"
            difficulty = row["difficulty"] if isinstance(row["difficulty"], str) else "<invalid>"
            source_counts[source_name] += 1
            difficulty_counts[difficulty] += 1
            question = row["question"]
            if not isinstance(question, str) or not question.strip():
                counts["invalid_question_rows"] += 1
                continue
            if not isinstance(row["input_output"], str):
                counts["missing_input_output_rows"] += 1
                continue
            try:
                input_output = loads_strict(cast(str, row["input_output"]))
            except StrictJsonError:
                counts["invalid_input_output_json_rows"] += 1
                continue
            if not isinstance(input_output, dict) or "fn_name" not in input_output:
                counts["stdio_or_non_function_rows"] += 1
                continue
            counts["function_call_rows"] += 1
            function_source_counts[source_name] += 1
            record_id = f"taco-shard0/{row_index}"
            try:
                parsed = _taco_function_call_tests(input_output, record_id=record_id)
            except ValueError:
                counts["invalid_function_call_test_rows"] += 1
                continue
            if parsed is None:
                counts["invalid_function_call_test_rows"] += 1
                continue
            function_name, tests = parsed
            test_counts.append(len(tests))
            if len(tests) < 8:
                counts["function_call_lt8_rows"] += 1
                continue
            counts["function_call_ge8_rows"] += 1
            ge8_source_counts[source_name] += 1
            ge8_difficulty_counts[difficulty] += 1
            try:
                refresh_test_set_fingerprint(tests, context=record_id)
            except ValueError:
                counts["duplicate_normalized_test_rows"] += 1
                continue
            counts["unique_ge8_rows"] += 1

            solutions = _solutions(row["solutions"])
            if solutions is None:
                counts["unique_ge8_without_solution_rows"] += 1
                continue
            counts["unique_ge8_with_solution_rows"] += 1
            arities = {len(cast(Sequence[object], test.input)) for test in tests}
            starter = row["starter_code"] if isinstance(row["starter_code"], str) else ""
            direct_signature = _function_signature_from_row(
                {"problem": f"{question}\n{starter}", "solutions": solutions},
                function_name=function_name,
                arities=arities,
            )
            if direct_signature is not None:
                counts["direct_signature_ge8_rows"] += 1
                continue

            class_method = any(
                _class_method_supports_arities(text, function_name, arities)
                for text in ([starter] if starter.strip() else []) + solutions
            )
            if class_method:
                counts["class_method_only_signature_ge8_rows"] += 1
            else:
                counts["no_recoverable_signature_ge8_rows"] += 1

    report: dict[str, object] = {
        "schema_version": "wp9c-taco-shard-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "formal_blockers": [
            "only_one_of_nine_train_shards_audited",
            "cross_source_dedup_not_run",
            "context_gate_not_run",
            "project_piston_reference_solution_validation_not_run",
            "mixed_upstream_provenance_requires_preservation_and_review",
        ],
        "source_config_path": str(config_path),
        "source_config_sha256": _sha256(config_path),
        "source_identity": source,
        "snapshot_path": str(snapshot),
        "parquet_path": str(parquet_path),
        "parquet_sha256": expected_sha,
        "counts": dict(sorted(counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "function_source_counts": dict(sorted(function_source_counts.items())),
        "ge8_source_counts": dict(sorted(ge8_source_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "ge8_difficulty_counts": dict(sorted(ge8_difficulty_counts.items())),
        "function_call_test_count": {
            "count": len(test_counts),
            "min": min(test_counts) if test_counts else None,
            "max": max(test_counts) if test_counts else None,
            "mean": (sum(test_counts) / len(test_counts)) if test_counts else None,
        },
        "notes": [
            "No candidate solution or testcase payload was executed by this audit.",
            (
                "Function-call tests use the same strict TACO parser already used by WP9-c "
                "DeepCoder function-call engineering."
            ),
            "direct_signature_ge8_rows is the conservative immediately-compatible contract count.",
            (
                "class_method_only_signature_ge8_rows is reported separately and is not admitted "
                "without an explicit adapter decision."
            ),
        ],
    }

    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        payload = canonical_json(report) + "\n"
        (temporary / "report.json").write_text(payload, encoding="utf-8")
        (temporary / "report.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = audit(Path(args.source_config).resolve(), Path(args.output_dir).resolve())
    print(canonical_json(report))


if __name__ == "__main__":
    main()
