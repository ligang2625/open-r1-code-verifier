#!/usr/bin/env python3
"""Audit-only inventory for the pinned Open-R1 tested/shuffled coding dataset.

This script intentionally does not materialize refresh candidates. It measures whether
function-call rows can be mapped to the project's canonical positional-argument schema
without executing source testcase text or guessing source-specific syntax.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import keyword
import math
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from huggingface_hub import snapshot_download

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.schema import SchemaError, validate_json_value

EXPECTED_FIELDS = {
    "source",
    "task_type",
    "in_source_id",
    "problem",
    "gold_standard_solution",
    "problem_id",
    "metadata",
    "verification_info",
    "test_reward",
}
TEST_FIELDS = {"fn_name", "input", "output", "type"}
SOURCE_KEY = "openr1_tested_shuffled"


@dataclass(frozen=True)
class SignatureShape:
    location: str
    required_positional: int
    maximum_positional: int

    def supports(self, arity: int) -> bool:
        return self.required_positional <= arity <= self.maximum_positional


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_json(text: object) -> object:
    if not isinstance(text, str):
        raise ValueError("value is not text")

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


def _canonicalizable(value: object) -> bool:
    try:
        validate_json_value(value, field_path="audit")
    except SchemaError:
        return False
    return True


def _parse_literal(text: object) -> object:
    if not isinstance(text, str):
        raise ValueError("value is not text")
    value = ast.literal_eval(text)
    if not _canonicalizable(value):
        raise ValueError("literal is not canonical JSON-compatible")
    return value


def _strip_single_code_fence(text: str) -> str:
    match = re.fullmatch(r"\s*```(?:python)?\s*\n(?P<body>.*)\n```\s*", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group("body") if match is not None else text


def _shape_from_function(node: ast.FunctionDef, *, location: str, drop_receiver: bool) -> SignatureShape | None:
    arguments = node.args
    if arguments.vararg is not None or arguments.kwonlyargs or arguments.kwarg is not None:
        return None
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = list(arguments.defaults)
    if drop_receiver:
        if not positional or positional[0].arg not in {"self", "cls"}:
            return None
        positional = positional[1:]
        if len(defaults) > len(positional):
            return None
    required = len(positional) - len(defaults)
    if required < 0:
        return None
    return SignatureShape(location=location, required_positional=required, maximum_positional=len(positional))


def _signature_shapes(solution: object, function_name: str) -> tuple[str, list[SignatureShape]]:
    if not isinstance(solution, str) or not solution.strip():
        return "missing_solution", []
    try:
        module = ast.parse(_strip_single_code_fence(solution))
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return "solution_syntax_error", []

    shapes: list[SignatureShape] = []
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            shape = _shape_from_function(node, location="top_level", drop_receiver=False)
            if shape is not None:
                shapes.append(shape)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == function_name:
                    receiver = bool(child.args.args or child.args.posonlyargs) and (
                        [*child.args.posonlyargs, *child.args.args][0].arg in {"self", "cls"}
                    )
                    shape = _shape_from_function(
                        child,
                        location=f"class:{node.name}",
                        drop_receiver=receiver,
                    )
                    if shape is not None:
                        shapes.append(shape)
    if not shapes:
        return "no_supported_signature", []
    if len(shapes) != 1:
        return "multiple_supported_signatures", shapes
    return "unique_supported_signature", shapes


def _argument_interpretations(value: object, shape: SignatureShape) -> list[list[object]]:
    interpretations: list[list[object]] = []
    if shape.supports(1):
        interpretations.append([value])
    if isinstance(value, list) and shape.supports(len(value)):
        interpretations.append(list(value))

    unique: dict[str, list[object]] = {}
    for arguments in interpretations:
        if all(_canonicalizable(argument) for argument in arguments):
            unique[canonical_json(arguments)] = arguments
    return list(unique.values())


def _mapped_tests(
    tests: list[Mapping[str, object]],
    shape: SignatureShape,
    *,
    parser: str,
) -> list[dict[str, object]] | None:
    parse = _strict_json if parser == "strict_json" else _parse_literal
    mapped: list[dict[str, object]] = []
    fingerprints: set[str] = set()
    for test in tests:
        try:
            input_value = parse(test["input"])
            expected = parse(test["output"])
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return None
        if not _canonicalizable(expected):
            return None
        interpretations = _argument_interpretations(input_value, shape)
        if len(interpretations) != 1:
            return None
        row = {"input": interpretations[0], "expected": expected}
        fingerprint = canonical_json(row)
        if fingerprint in fingerprints:
            return None
        fingerprints.add(fingerprint)
        mapped.append(row)
    return mapped


def _stats(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "p90": None, "max": None, "mean": None}
    ordered = sorted(values)
    median = (
        ordered[len(ordered) // 2]
        if len(ordered) % 2
        else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2
    )
    p90_index = max(0, math.ceil(0.90 * len(ordered)) - 1)
    return {
        "count": len(values),
        "min": ordered[0],
        "median": median,
        "p90": ordered[p90_index],
        "max": ordered[-1],
        "mean": sum(values) / len(values),
    }


def _source_config(path: Path) -> dict[str, object]:
    raw = load_yaml_mapping(path)
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("source config must contain a sources object")
    value = sources.get(SOURCE_KEY)
    if not isinstance(value, dict):
        raise ValueError(f"source config is missing {SOURCE_KEY}")
    required = {
        "source_name",
        "dataset_id",
        "revision",
        "config_name",
        "split",
        "declared_license",
        "license_status",
        "parquet_path",
        "parquet_size",
        "parquet_sha256",
        "adapter",
        "upstream_reward_evidence",
    }
    if set(value) != required:
        raise ValueError("Open-R1 audit source config schema mismatch")
    if value["adapter"] != "audit_only_v1" or value["license_status"] != "unresolved_upstream":
        raise ValueError("Open-R1 audit source must remain audit-only with unresolved license status")
    return cast(dict[str, object], value)


def audit(source_config_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SystemExit(f"output already exists: {output_dir}")
    source = _source_config(source_config_path)
    dataset_id = cast(str, source["dataset_id"])
    revision = cast(str, source["revision"])
    relative_path = cast(str, source["parquet_path"])
    expected_sha = cast(str, source["parquet_sha256"])
    expected_size = cast(int, source["parquet_size"])

    snapshot = Path(
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=["README.md", relative_path],
            local_files_only=True,
        )
    ).resolve()
    if snapshot.name != revision:
        raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
    parquet_path = snapshot / relative_path
    if not parquet_path.is_file():
        raise SystemExit(f"missing pinned parquet: {parquet_path}")
    if parquet_path.stat().st_size != expected_size or _sha256(parquet_path) != expected_sha:
        raise SystemExit("pinned Open-R1 parquet size/SHA256 mismatch")

    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(parquet_path)
    column_names = parquet_file.schema_arrow.names
    if set(column_names) != EXPECTED_FIELDS:
        raise SystemExit(f"schema drift: expected {sorted(EXPECTED_FIELDS)}, got {column_names}")

    counts: Counter[str] = Counter()
    source_total: Counter[str] = Counter()
    source_function: Counter[str] = Counter()
    source_json_ge8: Counter[str] = Counter()
    source_literal_ge8: Counter[str] = Counter()
    signature_status: Counter[str] = Counter()
    signature_locations: Counter[str] = Counter()
    test_counts: list[int] = []
    prompt_lengths: list[int] = []

    for batch in parquet_file.iter_batches(batch_size=128, columns=column_names):
        for raw_row in batch.to_pylist():
            counts["total_rows"] += 1
            if not isinstance(raw_row, Mapping) or set(raw_row) != EXPECTED_FIELDS:
                raise SystemExit(f"row {counts['total_rows'] - 1}: schema drift")
            row = cast(Mapping[str, object], raw_row)
            source_name = row["source"] if isinstance(row["source"], str) else "<invalid>"
            source_total[source_name] += 1
            problem = row["problem"]
            if isinstance(problem, str):
                prompt_lengths.append(len(problem))
            if row["test_reward"] == 1.0:
                counts["test_reward_eq_1"] += 1

            verification = row["verification_info"]
            if not isinstance(verification, Mapping) or set(verification) != {"language", "test_cases"}:
                counts["invalid_verification_info"] += 1
                continue
            if verification["language"] != "python":
                counts["non_python"] += 1
                continue
            tests_raw = verification["test_cases"]
            if not isinstance(tests_raw, list) or not tests_raw:
                counts["missing_tests"] += 1
                continue
            if any(not isinstance(test, Mapping) or set(test) != TEST_FIELDS for test in tests_raw):
                counts["invalid_test_schema"] += 1
                continue
            tests = cast(list[Mapping[str, object]], tests_raw)
            types = {test["type"] for test in tests}
            if types != {"function_call"}:
                if "function_call" in types:
                    counts["mixed_test_type_rows"] += 1
                else:
                    counts["non_function_call_rows"] += 1
                continue

            counts["pure_function_call_rows"] += 1
            source_function[source_name] += 1
            test_counts.append(len(tests))
            if len(tests) >= 8:
                counts["pure_function_call_ge8_raw"] += 1

            names = {test["fn_name"] for test in tests}
            if len(names) != 1:
                counts["inconsistent_fn_name_rows"] += 1
                continue
            function_name = next(iter(names))
            if (
                not isinstance(function_name, str)
                or not function_name.isidentifier()
                or keyword.iskeyword(function_name)
            ):
                counts["invalid_fn_name_rows"] += 1
                continue
            counts["valid_fn_name_rows"] += 1

            raw_fingerprints = {
                canonical_json(
                    {
                        "fn_name": test["fn_name"],
                        "input": test["input"],
                        "output": test["output"],
                        "type": test["type"],
                    }
                )
                for test in tests
            }
            if len(raw_fingerprints) >= 8:
                counts["raw_unique_ge8_rows"] += 1

            status, shapes = _signature_shapes(row["gold_standard_solution"], function_name)
            signature_status[status] += 1
            if status != "unique_supported_signature":
                continue
            shape = shapes[0]
            signature_locations[shape.location] += 1
            counts["unique_supported_signature_rows"] += 1

            strict_mapped = _mapped_tests(tests, shape, parser="strict_json")
            if strict_mapped is not None:
                counts["strict_json_unambiguous_rows"] += 1
                if len(strict_mapped) >= 8:
                    counts["strict_json_unambiguous_ge8_rows"] += 1
                    source_json_ge8[source_name] += 1

            literal_mapped = _mapped_tests(tests, shape, parser="literal")
            if literal_mapped is not None:
                counts["safe_literal_unambiguous_rows"] += 1
                if len(literal_mapped) >= 8:
                    counts["safe_literal_unambiguous_ge8_rows"] += 1
                    source_literal_ge8[source_name] += 1

    report: dict[str, object] = {
        "schema_version": "wp9c-openr1-tested-audit-v1",
        "evidence_class": "engineering_data_audit_only",
        "formal_eligible": False,
        "formal_blockers": [
            "dataset_license_not_declared_and_upstream_provenance_not_yet_resolved",
            "no_project_piston_reference_solution_validation",
            "function_call_input_semantics_not_yet_frozen_for_non_unambiguous_rows",
        ],
        "source_config_path": str(source_config_path),
        "source_config_sha256": _sha256(source_config_path),
        "source_identity": source,
        "snapshot_path": str(snapshot),
        "parquet_path": str(parquet_path),
        "parquet_sha256": expected_sha,
        "counts": dict(sorted(counts.items())),
        "source_total_counts": dict(sorted(source_total.items())),
        "source_function_call_counts": dict(sorted(source_function.items())),
        "source_strict_json_unambiguous_ge8_counts": dict(sorted(source_json_ge8.items())),
        "source_safe_literal_unambiguous_ge8_counts": dict(sorted(source_literal_ge8.items())),
        "signature_status_counts": dict(sorted(signature_status.items())),
        "signature_location_counts": dict(sorted(signature_locations.items())),
        "function_call_test_count_stats": _stats(test_counts),
        "prompt_character_count_stats": _stats(prompt_lengths),
        "notes": [
            "No testcase text was executed by this audit.",
            "strict_json requires RFC-style JSON with duplicate keys and NaN/Infinity rejected.",
            "safe_literal uses ast.literal_eval only, then requires project-canonical JSON-compatible values.",
            (
                "An input is counted as unambiguous only when exactly one of single-argument "
                "or list-as-positional-envelope semantics matches the frozen signature arity."
            ),
            (
                "Upstream test_reward==1 is recorded only as informational evidence and is not "
                "a substitute for project Piston validation."
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
