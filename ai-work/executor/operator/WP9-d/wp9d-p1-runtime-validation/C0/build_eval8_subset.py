#!/usr/bin/env python3
"""Build once, then strictly verify the first-8-problem WP9-d P1 systems subset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from code_verifier.data.prepare import (
    check_prepared_data,
    export_canonical_jsonl,
    export_hf_dataset,
    export_training_artifacts,
    load_canonical_jsonl,
)

SOURCE_HASHES = {
    "canonical/problems.jsonl": "d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6",
    "hf_dataset/data-00000-of-00001.arrow": "474edfd8731dea9f4938630f4f4903b6a016124c9ee5d4d4eed2a322015c47af",
    "hf_dataset/dataset_info.json": "92bbb50ce5825d6c8ee4a675a9199f0ebae50535909313d1e442ed28d68895f9",
    "hf_dataset/state.json": "ea62279de3ce3df8f6908e3a9dd1901734f12fc6cc0569cda75527e2d7841ca1",
    "training/hidden_grpo.jsonl": "79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7",
    "training/public_grpo.jsonl": "94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223",
    "training/sft.jsonl": "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c",
    "training/sft_validation.jsonl": "7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2",
}
TEST_COUNT = 8
MANIFEST = "wp9d_p1_eval8_manifest.json"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != MANIFEST
    }


def source_selection(source: Path) -> tuple[list[object], list[str]]:
    for rel, expected in SOURCE_HASHES.items():
        path = source / rel
        if not path.is_file() or sha(path) != expected:
            raise SystemExit(f"canonical eval400 source drift: {rel}")
    summary = check_prepared_data(source)
    if summary.hf_dataset_dir is None:
        raise SystemExit("canonical eval400 lacks hf_dataset")
    problems = load_canonical_jsonl(source / "canonical/problems.jsonl")
    test = [problem for problem in problems if problem.split == "test"]
    if len(test) != 400 or len({problem.problem_id for problem in test}) != 400:
        raise SystemExit("canonical eval400 must contain 400 unique test problems")
    selected = test[:TEST_COUNT]
    ids = [problem.problem_id for problem in selected]
    keep = set(ids)
    subset = [problem for problem in problems if problem.split != "test" or problem.problem_id in keep]
    if [problem.problem_id for problem in subset if problem.split == "test"] != ids:
        raise SystemExit("eval8 order differs from canonical eval400 prefix")
    return subset, ids


def expected_manifest(ids: list[str], hashes: dict[str, str]) -> dict[str, object]:
    return {
        "schema_version": "wp9d-p1-eval8-v1",
        "purpose": "systems_validation_only",
        "selection": "first_8_in_canonical_eval400_order",
        "problem_count": TEST_COUNT,
        "problem_ids": ids,
        "ordered_problem_ids_sha256": hashlib.sha256(
            "".join(f"{problem_id}\n" for problem_id in ids).encode()
        ).hexdigest(),
        "source_canonical_problems_sha256": SOURCE_HASHES["canonical/problems.jsonl"],
        "artifact_sha256": hashes,
    }


def source_ids_fast(source: Path) -> list[str]:
    canonical = source / "canonical/problems.jsonl"
    if not canonical.is_file() or sha(canonical) != SOURCE_HASHES["canonical/problems.jsonl"]:
        raise SystemExit("canonical eval400 source drift: canonical/problems.jsonl")
    problems = load_canonical_jsonl(canonical)
    test = [problem for problem in problems if problem.split == "test"]
    if len(test) != 400 or len({problem.problem_id for problem in test}) != 400:
        raise SystemExit("canonical eval400 must contain 400 unique test problems")
    return [problem.problem_id for problem in test[:TEST_COUNT]]


def verify_existing(source: Path, output: Path, *, fast: bool = False) -> dict[str, object]:
    ids = source_ids_fast(source) if fast else source_selection(source)[1]
    if not output.is_dir():
        raise SystemExit("eval8 output is not an existing directory")
    manifest_path = output / MANIFEST
    if not manifest_path.is_file():
        raise SystemExit("eval8 manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SystemExit("eval8 manifest is unreadable") from None
    if not isinstance(manifest, dict):
        raise SystemExit("eval8 manifest must be an object")
    hashes = artifact_hashes(output)
    if manifest != expected_manifest(ids, hashes):
        raise SystemExit("existing eval8 manifest/artifact identity drift")
    if not fast:
        summary = check_prepared_data(output)
        if summary.hf_dataset_dir is None or summary.split_counts.get("test") != TEST_COUNT:
            raise SystemExit("existing eval8 prepared-data readback failed")
    output_problems = load_canonical_jsonl(output / "canonical/problems.jsonl")
    if [problem.problem_id for problem in output_problems if problem.split == "test"] != ids:
        raise SystemExit("existing eval8 test order drift")
    return manifest


def build(source: Path, output: Path) -> dict[str, object]:
    subset, ids = source_selection(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        export_canonical_jsonl(subset, temp / "canonical/problems.jsonl")
        export_hf_dataset(subset, temp / "hf_dataset")
        export_training_artifacts(subset, temp / "training")
        built = check_prepared_data(temp)
        if built.hf_dataset_dir is None or built.split_counts.get("test") != TEST_COUNT:
            raise SystemExit("eval8 prepared-data readback failed")
        manifest = expected_manifest(ids, artifact_hashes(temp))
        (temp / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, output)
        return verify_existing(source, output)
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


def build_or_verify(source: Path, output: Path) -> tuple[dict[str, object], bool]:
    if output.exists():
        return verify_existing(source, output), True
    return build(source, output), False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-existing-only", action="store_true")
    args = parser.parse_args()
    if args.verify_existing_only:
        manifest, reused = verify_existing(args.source, args.output, fast=True), True
    else:
        manifest, reused = build_or_verify(args.source, args.output)
    print(json.dumps({**manifest, "reused_existing": reused}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
