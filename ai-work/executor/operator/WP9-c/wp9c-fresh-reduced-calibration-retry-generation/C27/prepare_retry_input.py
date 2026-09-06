#!/usr/bin/env python3
"""Freeze the accepted C26 both-zero retry IDs into the minimal C27 handoff bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.training.calibration import _load_input_bundle

EXPECTED_C26_SCORE_MANIFEST_SHA256 = "b7333162acb0e24d7285d8ca9145b220c10636541db09f5fac531de670edd226"
EXPECTED_C26_SCORE_RECORDS_SHA256 = "b9c7ada9d21a2f3140eeb074248a4b306d49d14b8dcdc90b39e9e3692ffff08e"
EXPECTED_RETRY_MANIFEST_SHA256 = "f0c03e55771bc86dd3f9966214ade7d34a9734cff133bdbdd1e6d1d8071c2eb5"
EXPECTED_RETRY_ORDER_SHA256 = "1309b9f7cbbb4e488499a21026a87c3148284becd07a57672131e6f244dea0d3"
EXPECTED_C25_INPUT_MANIFEST_SHA256 = "bdccb68febe85f1da381ba01671fb220246dac9e74cdfacb89e4d1da7e334aff"
EXPECTED_C25_INPUT_RECORDS_SHA256 = "dbb6f18a472e390acbec641daab65db6d3f2cb07d3469f8e46ef2d90bf867d18"
EXPECTED_RETRY_PROBLEM_COUNT = 195


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object at {path}:{line_number}")
        rows.append(value)
    return rows


def prepare(score_dir: Path, input_dir: Path, output_dir: Path) -> None:
    score_manifest_path = score_dir / "score_manifest.json"
    score_records_path = score_dir / "records" / "scoring.jsonl"
    retry_path = score_dir / "manifest" / "retry_problem_ids.jsonl"

    if _sha256(score_manifest_path) != EXPECTED_C26_SCORE_MANIFEST_SHA256:
        raise ValueError("C26 score manifest SHA256 drift")
    if _sha256(score_records_path) != EXPECTED_C26_SCORE_RECORDS_SHA256:
        raise ValueError("C26 score records SHA256 drift")
    if _sha256(retry_path) != EXPECTED_RETRY_MANIFEST_SHA256:
        raise ValueError("C26 retry manifest SHA256 drift")
    if _sha256(input_dir / "input_manifest.json") != EXPECTED_C25_INPUT_MANIFEST_SHA256:
        raise ValueError("C25 input manifest SHA256 drift")
    if _sha256(input_dir / "inputs.jsonl") != EXPECTED_C25_INPUT_RECORDS_SHA256:
        raise ValueError("C25 input records SHA256 drift")

    score_manifest = _load_json(score_manifest_path)
    if (
        score_manifest.get("status") != "completed"
        or score_manifest.get("problem_count") != 1602
        or score_manifest.get("block_index") != 0
        or score_manifest.get("records_sha256") != EXPECTED_C26_SCORE_RECORDS_SHA256
        or score_manifest.get("retry_problem_count") != EXPECTED_RETRY_PROBLEM_COUNT
        or score_manifest.get("retry_problem_ids_sha256") != EXPECTED_RETRY_MANIFEST_SHA256
    ):
        raise ValueError("C26 score manifest contract drift")

    score_rows = _load_jsonl(score_records_path)
    if len(score_rows) != 1602:
        raise ValueError("C26 score record count drift")
    if any(row.get("infrastructure_failure_count") != 0 for row in score_rows):
        raise ValueError("C26 contains an infrastructure-failure score record")

    retry_rows = _load_jsonl(retry_path)
    if any(set(row) != {"problem_id"} or not isinstance(row.get("problem_id"), str) for row in retry_rows):
        raise ValueError("C26 retry manifest schema drift")
    retry_ids = [str(row["problem_id"]) for row in retry_rows]
    derived = sorted(
        str(row["problem_id"])
        for row in score_rows
        if row.get("public_all_test_zero") is True and row.get("hidden_all_test_zero") is True
    )
    if retry_ids != derived:
        raise ValueError("C26 retry IDs are not the exact both-zero set")
    if len(retry_ids) != EXPECTED_RETRY_PROBLEM_COUNT or retry_ids != sorted(retry_ids):
        raise ValueError("C26 retry count/order drift")
    if len(set(retry_ids)) != EXPECTED_RETRY_PROBLEM_COUNT:
        raise ValueError("C26 retry IDs are not unique")
    if stable_json_hash(retry_ids) != EXPECTED_RETRY_ORDER_SHA256:
        raise ValueError("C26 retry problem-order SHA256 drift")

    input_manifest, input_rows = _load_input_bundle(input_dir)
    input_ids = [row.problem_id for row in input_rows]
    if len(input_rows) != 1602 or len(set(input_ids)) != 1602:
        raise ValueError("C25 input population drift")
    if any(problem_id not in set(input_ids) for problem_id in retry_ids):
        raise ValueError("C26 retry set is not a subset of C25 input")
    if input_manifest.get("seed") != 42:
        raise ValueError("C25 input seed drift")

    if output_dir.exists():
        existing_retry = output_dir / "retry_problem_ids.jsonl"
        existing_manifest = output_dir / "retry-input-manifest.json"
        if existing_retry.is_file() and existing_manifest.is_file():
            existing = _load_json(existing_manifest)
            if (
                _sha256(existing_retry) == EXPECTED_RETRY_MANIFEST_SHA256
                and existing.get("retry_problem_ids_sha256") == EXPECTED_RETRY_MANIFEST_SHA256
                and existing.get("retry_problem_order_sha256") == EXPECTED_RETRY_ORDER_SHA256
                and existing.get("retry_problem_count") == EXPECTED_RETRY_PROBLEM_COUNT
            ):
                print(f"C27 retry input already frozen: {output_dir}")
                return
        raise ValueError(f"C27 retry output already exists but is not the accepted bundle: {output_dir}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        retry_bytes = retry_path.read_bytes()
        (temporary / "retry_problem_ids.jsonl").write_bytes(retry_bytes)
        manifest = {
            "version": 1,
            "stage_id": "WP9-c",
            "checkpoint_id": "C27",
            "protocol": "wp9c-reduced-quota-current-viable-v1",
            "source": "C26 exact both-zero retry set",
            "block_index": 1,
            "sample_index_start": 8,
            "sample_index_end": 15,
            "samples_per_problem": 8,
            "retry_problem_count": EXPECTED_RETRY_PROBLEM_COUNT,
            "expected_record_count": EXPECTED_RETRY_PROBLEM_COUNT * 8,
            "retry_problem_ids_sha256": EXPECTED_RETRY_MANIFEST_SHA256,
            "retry_problem_order_sha256": EXPECTED_RETRY_ORDER_SHA256,
            "c26_score_manifest_sha256": EXPECTED_C26_SCORE_MANIFEST_SHA256,
            "c26_score_records_sha256": EXPECTED_C26_SCORE_RECORDS_SHA256,
            "c25_input_manifest_sha256": EXPECTED_C25_INPUT_MANIFEST_SHA256,
            "c25_input_records_sha256": EXPECTED_C25_INPUT_RECORDS_SHA256,
            "retry_problem_ids_size_bytes": len(retry_bytes),
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        (temporary / "retry-input-manifest.json").write_bytes(manifest_bytes)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(
        json.dumps(
            {
                "status": "C27_RETRY_INPUT_READY",
                "output_dir": str(output_dir),
                "retry_problem_count": EXPECTED_RETRY_PROBLEM_COUNT,
                "retry_problem_ids_sha256": EXPECTED_RETRY_MANIFEST_SHA256,
                "retry_problem_order_sha256": EXPECTED_RETRY_ORDER_SHA256,
                "retry_input_manifest_sha256": _sha256(output_dir / "retry-input-manifest.json"),
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score-dir", type=Path, default=Path("/home/dzy/wp9c-fresh-reduced-calibration-score-C26"))
    parser.add_argument("--input-bundle", type=Path, default=Path("/home/dzy/wp9c-fresh-calibration-input-C25"))
    parser.add_argument("--output", type=Path, default=Path("/home/dzy/wp9c-fresh-calibration-retry-input-C27"))
    args = parser.parse_args()
    prepare(args.score_dir.resolve(), args.input_bundle.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
