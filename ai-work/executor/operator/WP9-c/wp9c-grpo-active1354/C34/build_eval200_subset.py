#!/usr/bin/env python3
"""Build the deterministic C34 200-problem systems-benchmark evaluation subset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from code_verifier.data.leakage_checks import check_dataset
from code_verifier.data.prepare import (
    check_prepared_data,
    export_canonical_jsonl,
    export_hf_dataset,
    export_training_artifacts,
    load_canonical_jsonl,
)
from code_verifier.data.schema import CodeProblem

SOURCE_EVAL400_HASHES = {
    "canonical/problems.jsonl": "d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6",
    "hf_dataset/data-00000-of-00001.arrow": "474edfd8731dea9f4938630f4f4903b6a016124c9ee5d4d4eed2a322015c47af",
    "hf_dataset/dataset_info.json": "92bbb50ce5825d6c8ee4a675a9199f0ebae50535909313d1e442ed28d68895f9",
    "hf_dataset/state.json": "ea62279de3ce3df8f6908e3a9dd1901734f12fc6cc0569cda75527e2d7841ca1",
    "training/hidden_grpo.jsonl": "79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7",
    "training/public_grpo.jsonl": "94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223",
    "training/sft.jsonl": "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c",
    "training/sft_validation.jsonl": "7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2",
}
EXPECTED_SOURCE_TEST_COUNT = 400
EVAL200_TEST_COUNT = 200
MANIFEST_NAME = "eval200_manifest.json"
ORDER_HASH_ALGORITHM = "sha256_utf8_lf_lines_v1"


class Eval200BuildError(RuntimeError):
    """Raised when the frozen source or deterministic subset contract is violated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ordered_ids_sha256(problem_ids: Sequence[str]) -> str:
    payload = "".join(f"{problem_id}\n" for problem_id in problem_ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_source(source: Path) -> list[CodeProblem]:
    if not source.is_absolute() or not source.is_dir():
        raise Eval200BuildError(f"source must be an existing absolute directory: {source}")
    for relative_path, expected_sha in SOURCE_EVAL400_HASHES.items():
        path = source / relative_path
        if not path.is_file():
            raise Eval200BuildError(f"frozen eval400 source artifact is missing: {relative_path}")
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise Eval200BuildError(
                f"frozen eval400 source hash mismatch for {relative_path}: {actual_sha} != {expected_sha}"
            )
    summary = check_prepared_data(source)
    if summary.hf_dataset_dir is None:
        raise Eval200BuildError("frozen eval400 source is missing its HF dataset")
    problems = load_canonical_jsonl(source / "canonical" / "problems.jsonl")
    test_problems = [problem for problem in problems if problem.split == "test"]
    if len(test_problems) != EXPECTED_SOURCE_TEST_COUNT:
        raise Eval200BuildError(
            f"frozen eval400 source must contain exactly {EXPECTED_SOURCE_TEST_COUNT} test problems; "
            f"found {len(test_problems)}"
        )
    test_ids = [problem.problem_id for problem in test_problems]
    if len(test_ids) != len(set(test_ids)):
        raise Eval200BuildError("frozen eval400 test split contains duplicate problem IDs")
    return problems


def _subset_problems(source_problems: Sequence[CodeProblem]) -> tuple[list[CodeProblem], list[str]]:
    source_test = [problem for problem in source_problems if problem.split == "test"]
    selected_test = source_test[:EVAL200_TEST_COUNT]
    selected_ids = [problem.problem_id for problem in selected_test]
    selected_set = set(selected_ids)
    subset = [problem for problem in source_problems if problem.split != "test" or problem.problem_id in selected_set]
    actual_test_ids = [problem.problem_id for problem in subset if problem.split == "test"]
    if actual_test_ids != selected_ids:
        raise Eval200BuildError("eval200 test problem order does not equal the frozen eval400 first 200")
    if len(selected_ids) != EVAL200_TEST_COUNT or len(selected_set) != EVAL200_TEST_COUNT:
        raise Eval200BuildError("eval200 selection must contain exactly 200 unique problem IDs")
    check_dataset(subset)
    return subset, selected_ids


def _artifact_hashes(root: Path) -> dict[str, str]:
    expected_paths = tuple(SOURCE_EVAL400_HASHES)
    hashes: dict[str, str] = {}
    for relative_path in expected_paths:
        path = root / relative_path
        if not path.is_file():
            raise Eval200BuildError(f"eval200 artifact is missing: {relative_path}")
        hashes[relative_path] = _sha256(path)
    actual_hf_files = sorted(
        path.relative_to(root).as_posix() for path in (root / "hf_dataset").iterdir() if path.is_file()
    )
    expected_hf_files = sorted(path for path in expected_paths if path.startswith("hf_dataset/"))
    if actual_hf_files != expected_hf_files:
        raise Eval200BuildError(f"eval200 HF artifact inventory drift: {actual_hf_files} != {expected_hf_files}")
    return hashes


def _split_counts(problems: Sequence[CodeProblem]) -> dict[str, int]:
    return {split: sum(problem.split == split for problem in problems) for split in ("train", "validation", "test")}


def _write_manifest(
    root: Path,
    *,
    source: Path,
    source_problems: Sequence[CodeProblem],
    subset_problems: Sequence[CodeProblem],
    selected_ids: Sequence[str],
    artifact_hashes: dict[str, str],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": "wp9c-c34-eval200-subset-v1",
        "purpose": "systems_benchmark_only",
        "selection": "first_200_in_frozen_order",
        "problem_count": EVAL200_TEST_COUNT,
        "ordered_problem_ids_sha256": _ordered_ids_sha256(selected_ids),
        "ordered_problem_ids_sha256_algorithm": ORDER_HASH_ALGORITHM,
        "source_eval400": {
            "authority": str(source),
            "test_problem_count": EXPECTED_SOURCE_TEST_COUNT,
            "split_counts": _split_counts(source_problems),
            "artifact_sha256": dict(SOURCE_EVAL400_HASHES),
        },
        "eval200": {
            "split_counts": _split_counts(subset_problems),
            "artifact_sha256": artifact_hashes,
        },
        "scientific_evaluation_contract": {
            "heldout_eval400_remains_authoritative": True,
            "systems_benchmark_subset_is_not_final_model_evaluation_suite": True,
        },
    }
    path = root / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def _build_into(source: Path, destination: Path) -> dict[str, Any]:
    source_problems = _verify_source(source)
    subset, selected_ids = _subset_problems(source_problems)
    export_canonical_jsonl(subset, destination / "canonical" / "problems.jsonl")
    export_hf_dataset(subset, destination / "hf_dataset")
    export_training_artifacts(subset, destination / "training")
    summary = check_prepared_data(destination)
    if summary.total_problems != len(subset) or summary.split_counts.get("test") != EVAL200_TEST_COUNT:
        raise Eval200BuildError("prepared eval200 readback count mismatch")
    artifact_hashes = _artifact_hashes(destination)
    return _write_manifest(
        destination,
        source=source,
        source_problems=source_problems,
        subset_problems=subset,
        selected_ids=selected_ids,
        artifact_hashes=artifact_hashes,
    )


def _file_inventory(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): _sha256(path) for path in sorted(root.rglob("*")) if path.is_file()}


def build_eval200_subset(source: Path, output: Path) -> tuple[dict[str, Any], bool]:
    """Build or byte-verify the deterministic eval200 prepared dataset."""
    if not output.is_absolute():
        raise Eval200BuildError(f"output must be absolute: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        manifest = _build_into(source, temporary)
        if output.exists():
            if not output.is_dir():
                raise Eval200BuildError(f"existing output is not a directory: {output}")
            if _file_inventory(output) != _file_inventory(temporary):
                raise Eval200BuildError("existing eval200 output differs from a fresh deterministic rebuild")
            shutil.rmtree(temporary)
            existing_manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
            if existing_manifest != manifest:
                raise Eval200BuildError("existing eval200 manifest differs from a fresh deterministic rebuild")
            return manifest, True
        os.replace(temporary, output)
        return manifest, False
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="absolute frozen eval400 prepared dataset")
    parser.add_argument("--output", type=Path, required=True, help="absolute eval200 prepared dataset output")
    args = parser.parse_args()
    manifest, reused = build_eval200_subset(args.source, args.output)
    result = {
        "status": "completed",
        "output": str(args.output),
        "reused_existing": reused,
        "problem_count": manifest["problem_count"],
        "ordered_problem_ids_sha256": manifest["ordered_problem_ids_sha256"],
        "artifact_sha256": manifest["eval200"]["artifact_sha256"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
