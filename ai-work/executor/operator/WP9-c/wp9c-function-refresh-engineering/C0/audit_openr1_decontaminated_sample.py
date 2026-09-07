#!/usr/bin/env python3
"""Audit sampled raw Open-R1 decontaminated Python shards for function-call supply."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from huggingface_hub import snapshot_download

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.refresh_sources import _function_signature_from_row, refresh_test_set_fingerprint
from code_verifier.data.schema import TestCase, validate_json_value

EXPECTED_FIELDS = {
    "source",
    "task_type",
    "in_source_id",
    "problem",
    "gold_standard_solution",
    "problem_id",
    "metadata",
    "verification_info",
}
TEST_FIELDS = {"fn_name", "input", "output", "type"}


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
        raise ValueError("audit config must contain source mapping")
    required = {
        "source_name",
        "dataset_id",
        "revision",
        "config_name",
        "split",
        "declared_license",
        "license_status",
        "adapter",
        "shards",
    }
    if set(source) != required:
        raise ValueError("audit source config schema mismatch")
    if source.get("adapter") != "audit_only_v1" or source.get("license_status") != "unresolved_upstream":
        raise ValueError("source must remain audit-only with unresolved upstream license")
    shards = source.get("shards")
    if not isinstance(shards, list) or len(shards) != 2:
        raise ValueError("audit must pin exactly two sample shards")
    return cast(dict[str, object], source)


def _strict_json(text: object) -> object:
    if not isinstance(text, str):
        raise ValueError("test payload must be text")

    def reject_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant {value}")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)


def _safe_literal(text: object) -> object:
    if not isinstance(text, str):
        raise ValueError("test payload must be text")
    return ast.literal_eval(text)


def _expected_value(value: object, *, field: str) -> object:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    return validate_json_value(value, field_path=field)


def _parse_function_tests(
    tests: list[Mapping[str, object]],
    *,
    parser: str,
    record_id: str,
) -> tuple[str, tuple[TestCase, ...]] | None:
    parse = _strict_json if parser == "strict_json" else _safe_literal
    names = {test.get("fn_name") for test in tests}
    if len(names) != 1:
        return None
    function_name = next(iter(names))
    if not isinstance(function_name, str) or not function_name.isidentifier():
        return None
    parsed: list[TestCase] = []
    for index, test in enumerate(tests):
        try:
            input_value = parse(test["input"])
            output_value = parse(test["output"])
            if not isinstance(input_value, list):
                return None
            arguments = validate_json_value(input_value, field_path=f"{record_id}.tests[{index}].input")
            expected = _expected_value(output_value, field=f"{record_id}.tests[{index}].expected")
            parsed.append(TestCase(input=arguments, expected=expected))
        except (SyntaxError, TypeError, ValueError, MemoryError, RecursionError):
            return None
    return function_name, tuple(parsed)


def _audit_shard(path: Path, shard_index: int) -> dict[str, object]:
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(path)
    columns = parquet_file.schema_arrow.names
    if set(columns) != EXPECTED_FIELDS:
        raise SystemExit(f"shard {shard_index}: schema drift: {columns}")

    counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    function_source_counts: Counter[str] = Counter()
    ge8_source_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    test_counts: list[int] = []

    row_number = 0
    for batch in parquet_file.iter_batches(batch_size=128, columns=columns):
        for row in batch.to_pylist():
            current = row_number
            row_number += 1
            counts["total_rows"] += 1
            if not isinstance(row, Mapping) or set(row) != EXPECTED_FIELDS:
                raise SystemExit(f"shard {shard_index} row {current}: row schema drift")
            source_name = row["source"] if isinstance(row["source"], str) else "<invalid>"
            source_counts[source_name] += 1
            verification = row["verification_info"]
            if not isinstance(verification, Mapping) or set(verification) != {"language", "test_cases"}:
                counts["invalid_verification_info"] += 1
                continue
            if verification["language"] != "python":
                counts["non_python_rows"] += 1
                continue
            tests_raw = verification["test_cases"]
            if not isinstance(tests_raw, list) or not tests_raw:
                counts["missing_tests"] += 1
                continue
            if any(not isinstance(item, Mapping) or set(item) != TEST_FIELDS for item in tests_raw):
                counts["invalid_test_schema"] += 1
                continue
            tests = cast(list[Mapping[str, object]], tests_raw)
            types = {test["type"] for test in tests}
            for test in tests:
                type_counts[str(test["type"])] += 1
            if types != {"function_call"}:
                if "function_call" in types:
                    counts["mixed_function_call_rows"] += 1
                else:
                    counts["non_function_call_rows"] += 1
                continue

            counts["pure_function_call_rows"] += 1
            function_source_counts[source_name] += 1
            test_counts.append(len(tests))
            if len(tests) >= 8:
                counts["pure_function_call_ge8_raw"] += 1
                ge8_source_counts[source_name] += 1

            record_id = f"openr1-decontaminated/shard{shard_index}/{current}"
            strict_parsed = _parse_function_tests(tests, parser="strict_json", record_id=record_id)
            literal_parsed = _parse_function_tests(tests, parser="safe_literal", record_id=record_id)
            if strict_parsed is not None:
                counts["strict_json_rows"] += 1
            if literal_parsed is not None:
                counts["safe_literal_rows"] += 1

            chosen = strict_parsed or literal_parsed
            if chosen is None or len(chosen[1]) < 8:
                continue
            counts["parseable_ge8_rows"] += 1
            function_name, parsed_tests = chosen
            try:
                refresh_test_set_fingerprint(parsed_tests, context=record_id)
            except ValueError:
                counts["duplicate_normalized_test_rows"] += 1
                continue
            counts["unique_parseable_ge8_rows"] += 1

            solution = row["gold_standard_solution"]
            problem = row["problem"]
            if (
                not isinstance(solution, str)
                or not solution.strip()
                or not isinstance(problem, str)
                or not problem.strip()
            ):
                counts["unique_ge8_missing_problem_or_solution"] += 1
                continue
            arities = {len(cast(Sequence[object], test.input)) for test in parsed_tests}
            signature = _function_signature_from_row(
                {"problem": problem, "solutions": [solution]},
                function_name=function_name,
                arities=arities,
            )
            if signature is None:
                counts["unique_ge8_no_direct_signature"] += 1
            else:
                counts["direct_signature_ge8_rows"] += 1

    return {
        "shard_index": shard_index,
        "path": str(path),
        "sha256": _sha256(path),
        "counts": dict(sorted(counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "function_source_counts": dict(sorted(function_source_counts.items())),
        "ge8_source_counts": dict(sorted(ge8_source_counts.items())),
        "test_type_counts": dict(sorted(type_counts.items())),
        "function_call_test_count": {
            "count": len(test_counts),
            "min": min(test_counts) if test_counts else None,
            "max": max(test_counts) if test_counts else None,
            "mean": (sum(test_counts) / len(test_counts)) if test_counts else None,
        },
    }


def audit(config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    source = _config(config_path)
    dataset_id = cast(str, source["dataset_id"])
    revision = cast(str, source["revision"])
    shards = cast(list[dict[str, object]], source["shards"])
    paths = [cast(str, shard["parquet_path"]) for shard in shards]
    snapshot = Path(
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=["README.md", *paths],
            local_files_only=True,
        )
    ).resolve()
    if snapshot.name != revision:
        raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")

    shard_reports = []
    for shard in shards:
        shard_index = cast(int, shard["shard_index"])
        path = snapshot / cast(str, shard["parquet_path"])
        expected_size = cast(int, shard["parquet_size"])
        expected_sha = cast(str, shard["parquet_sha256"])
        if not path.is_file() or path.stat().st_size != expected_size or _sha256(path) != expected_sha:
            raise SystemExit(f"shard {shard_index}: pinned size/SHA mismatch")
        shard_reports.append(_audit_shard(path, shard_index))

    aggregate: Counter[str] = Counter()
    aggregate_sources: Counter[str] = Counter()
    for shard_report in shard_reports:
        aggregate.update(cast(dict[str, int], shard_report["counts"]))
        aggregate_sources.update(cast(dict[str, int], shard_report["function_source_counts"]))

    report: dict[str, object] = {
        "schema_version": "wp9c-openr1-decontaminated-sample-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "formal_blockers": [
            "only_two_of_six_shards_audited",
            "dataset_license_not_declared_and_per_source_provenance_not_yet_resolved",
            "cross_source_dedup_not_run",
            "context_gate_not_run",
            "project_piston_reference_solution_validation_not_run",
        ],
        "source_config_path": str(config_path),
        "source_config_sha256": _sha256(config_path),
        "source_identity": source,
        "snapshot_path": str(snapshot),
        "shards": shard_reports,
        "aggregate_counts": dict(sorted(aggregate.items())),
        "aggregate_function_source_counts": dict(sorted(aggregate_sources.items())),
        "notes": [
            "No source testcase or solution code is executed by this audit.",
            "Function-call input must parse to an explicit positional-argument list.",
            "strict JSON is preferred; ast.literal_eval is only an audit fallback and never executes input text.",
            "A single-element output envelope is unwrapped to match the existing DeepCoder function-call adapter.",
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
    print(canonical_json(audit(Path(args.source_config).resolve(), Path(args.output_dir).resolve())))


if __name__ == "__main__":
    main()
