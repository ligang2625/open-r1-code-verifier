from __future__ import annotations

from pathlib import Path

import pytest

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.training import reduced_calibration
from code_verifier.training.reduced_calibration import ReducedCalibrationScoringError


def _generation_row(problem_id: str, sample_index: int, *, block_index: int = 0) -> dict[str, object]:
    return {
        "problem_id": problem_id,
        "block_index": block_index,
        "sample_index": sample_index,
        "sample_seed": 123,
        "completion": f"completion-{problem_id}-{sample_index}",
        "completion_tokens": 1,
        "generation_latency_ms": 1.0,
        "hit_max_new_tokens": False,
    }


def _write_completed_score_artifact(root: Path, *, retry_ids: list[str]) -> None:
    records = [
        {
            "problem_id": "b",
            "infrastructure_failure_count": 0,
            "public_all_test_zero": True,
            "hidden_all_test_zero": True,
        },
        {
            "problem_id": "a",
            "infrastructure_failure_count": 0,
            "public_all_test_zero": True,
            "hidden_all_test_zero": True,
        },
    ]
    records_sha = reduced_calibration._write_jsonl(root / "records" / "scoring.jsonl", records)
    retry_sha = reduced_calibration._write_jsonl(
        root / "manifest" / "retry_problem_ids.jsonl",
        [{"problem_id": problem_id} for problem_id in retry_ids],
    )
    reduced_calibration._write_json(
        root / "score_manifest.json",
        {
            "version": 1,
            "schema_version": reduced_calibration.REDUCED_CALIBRATION_SCORING_SCHEMA_VERSION,
            "protocol": reduced_calibration.REDUCED_POOL_PROTOCOL,
            "scoring_semantics": "same_completion_bytes_public_then_hidden_v1",
            "block_index": 0,
            "workers": 8,
            "problem_count": 2,
            "problem_order_sha256": stable_json_hash(["b", "a"]),
            "piston_config_sha256": "1" * 64,
            "c24_checkpoint_sha256": "2" * 64,
            "c25_checkpoint_sha256": "3" * 64,
            "formal_problems_sha256": "4" * 64,
            "public_definition_sha256": "5" * 64,
            "hidden_definition_sha256": "6" * 64,
            "input_manifest_sha256": "7" * 64,
            "input_records_sha256": "8" * 64,
            "generation_run_manifest_sha256": "9" * 64,
            "generation_records_sha256": "a" * 64,
            "sft_checkpoint": {"checkpoint_sha256": "b" * 64},
            "status": "completed",
            "records_sha256": records_sha,
            "retry_problem_count": len(retry_ids),
            "retry_problem_ids_sha256": retry_sha,
        },
    )


def test_group_generation_rows_requires_exact_eight_sample_block() -> None:
    rows = [
        *[_generation_row("p0", index) for index in range(8)],
        *[_generation_row("p1", index) for index in range(8)],
    ]

    problem_ids, grouped = reduced_calibration._group_generation_rows(rows, block_index=0)

    assert problem_ids == ["p0", "p1"]
    assert [row["sample_index"] for row in grouped["p0"]] == list(range(8))
    assert [row["sample_index"] for row in grouped["p1"]] == list(range(8))


def test_group_generation_rows_rejects_sample_index_drift() -> None:
    rows = [_generation_row("p0", index) for index in range(8)]
    rows[-1]["sample_index"] = 8

    with pytest.raises(ReducedCalibrationScoringError, match="sample indices are not the exact block"):
        reduced_calibration._group_generation_rows(rows, block_index=0)


def test_check_reduced_pool_scoring_accepts_exact_sorted_both_zero_retry_set(tmp_path: Path) -> None:
    output_dir = tmp_path / "score"
    _write_completed_score_artifact(output_dir, retry_ids=["a", "b"])

    manifest = reduced_calibration.check_reduced_pool_calibration_scoring(output_dir)

    assert manifest["problem_count"] == 2
    assert manifest["retry_problem_count"] == 2


def test_check_reduced_pool_scoring_rejects_semantically_wrong_retry_order_even_with_matching_hash(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "score"
    _write_completed_score_artifact(output_dir, retry_ids=["b", "a"])

    with pytest.raises(ReducedCalibrationScoringError, match="exact sorted both-zero set"):
        reduced_calibration.check_reduced_pool_calibration_scoring(output_dir)
