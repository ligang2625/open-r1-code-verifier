from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

import pytest

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.training.grpo import load_grpo_benchmark_binding
from code_verifier.training.reduced_calibrated_pool import ReducedCalibratedPoolError, check_reduced_calibrated_pool

CLASS_NAMES = ("dual_informative", "public_only", "hidden_only", "dual_uninformative")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(problem_id: str, public: list[float], hidden: list[float]) -> dict[str, object]:
    public_std = statistics.pstdev(public)
    hidden_std = statistics.pstdev(hidden)
    calibration_class = (
        "dual_informative"
        if public_std > 0 and hidden_std > 0
        else "public_only"
        if public_std > 0
        else "hidden_only"
        if hidden_std > 0
        else "dual_uninformative"
    )
    record: dict[str, object] = {
        "problem_id": problem_id,
        "source_name": "unit-source",
        "difficulty": "easy",
        "overlap_origin": "external_new",
        "quality_gate_required": False,
        "sample_indices": list(range(8)),
        "completion_sha256": [hashlib.sha256(f"{problem_id}:{index}".encode()).hexdigest() for index in range(8)],
        "public_test_rewards": public,
        "hidden_test_rewards": hidden,
        "public_total_rewards": public,
        "hidden_total_rewards": hidden,
        "public_test_reward_mean": statistics.fmean(public),
        "public_test_reward_std": public_std,
        "hidden_test_reward_mean": statistics.fmean(hidden),
        "hidden_test_reward_std": hidden_std,
        "public_total_reward_mean": statistics.fmean(public),
        "public_total_reward_std": public_std,
        "hidden_total_reward_mean": statistics.fmean(hidden),
        "hidden_total_reward_std": hidden_std,
        "public_informative": public_std > 0,
        "hidden_informative": hidden_std > 0,
        "calibration_class": calibration_class,
        "public_all_test_correct": all(value == 1.0 for value in public),
        "hidden_all_test_correct": all(value == 1.0 for value in hidden),
        "public_all_test_zero": all(value == 0.0 for value in public),
        "hidden_all_test_zero": all(value == 0.0 for value in hidden),
        "public_full_pass_count": sum(value == 1.0 for value in public),
        "hidden_full_pass_count": sum(value == 1.0 for value in hidden),
        "parse_failure_count": 0,
        "execution_failure_count": 0,
        "timeout_count": 0,
        "infrastructure_failure_count": 0,
        "completion_token_mean": 10.0,
        "completion_token_max": 10,
        "truncation_count": 0,
    }
    record["calibration_record_sha256"] = stable_json_hash(record)
    return record


def _training_row(record: dict[str, object], *, hidden: bool) -> dict[str, object]:
    metadata = {
        "difficulty": "easy",
        "category": [],
        "time_limit_seconds": 1.0,
        "memory_limit_mb": 256,
        "license": "unit-test",
        "source_url_hash": hashlib.sha256(b"unit-source").hexdigest(),
        "calibration_class": record["calibration_class"],
        "calibration_record_sha256": record["calibration_record_sha256"],
        "overlap_origin": "external_new",
    }
    row: dict[str, object] = {
        "problem_id": record["problem_id"],
        "prompt": "Return x.",
        "function_name": "solve",
        "function_signature": "solve(x)",
        "visible_tests": [{"input": [1], "expected": 1}],
        "metadata": metadata,
    }
    if hidden:
        row["train_hidden_tests"] = [{"input": [2], "expected": 2}]
    return row


def _build_pool(root: Path) -> Path:
    active = _record("p-active", [0.0, 1.0] * 4, [1.0, 0.0] * 4)
    excluded = _record("p-saturated", [1.0] * 8, [1.0] * 8)
    records = [active, excluded]
    active_ids = ["p-active"]

    _write_jsonl(root / "records/calibration.jsonl", records)
    _write_jsonl(root / "manifest/retry_problem_ids.jsonl", [])
    _write_jsonl(
        root / "manifest/active_selection.jsonl",
        [
            {
                "ordinal": 0,
                "problem_id": "p-active",
                "calibration_class": "dual_informative",
                "calibration_record_sha256": active["calibration_record_sha256"],
                "overlap_origin": "external_new",
            }
        ],
    )
    _write_jsonl(root / "manifest/problem_order.jsonl", [{"ordinal": 0, "problem_id": "p-active"}])
    _write_jsonl(
        root / "manifest/excluded_dual_uninformative.jsonl",
        [
            {
                "problem_id": "p-saturated",
                "reason": "dual_saturated",
                "retried": False,
                "calibration_class": "dual_uninformative",
                "calibration_record_sha256": excluded["calibration_record_sha256"],
            }
        ],
    )
    _write_jsonl(root / "training/public_grpo.jsonl", [_training_row(active, hidden=False)])
    _write_jsonl(root / "training/hidden_grpo.jsonl", [_training_row(active, hidden=True)])

    class_counts = {name: 0 for name in CLASS_NAMES}
    class_counts["dual_informative"] = 1
    class_counts["dual_uninformative"] = 1
    active_class_counts = {name: 0 for name in CLASS_NAMES}
    active_class_counts["dual_informative"] = 1
    dispositions = {"dual_saturated": 1, "eligible": 1}
    composition = {
        "precalibration_problem_count": 2,
        "retry_problem_count": 0,
        "active_problem_count": 1,
        "excluded_dual_uninformative_count": 1,
        "class_counts": class_counts,
        "active_class_counts": active_class_counts,
        "disposition_counts": dispositions,
        "backfill_performed": False,
        "minimum_pool_count": None,
    }
    _write_json(root / "reports/classification_summary.json", class_counts)
    _write_json(root / "reports/disposition_summary.json", dispositions)
    _write_json(root / "reports/pool_composition.json", composition)

    artifact_paths = [
        "manifest/active_selection.jsonl",
        "manifest/excluded_dual_uninformative.jsonl",
        "manifest/problem_order.jsonl",
        "manifest/retry_problem_ids.jsonl",
        "records/calibration.jsonl",
        "reports/classification_summary.json",
        "reports/disposition_summary.json",
        "reports/pool_composition.json",
        "training/hidden_grpo.jsonl",
        "training/public_grpo.jsonl",
    ]
    artifacts = {relative: _sha(root / relative) for relative in artifact_paths}
    manifest = {
        "schema_version": "wp9c-reduced-calibration-v1",
        "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
        "status": "completed",
        "evidence_class": "formal_calibration",
        "seed": 42,
        "post_calibration_rule": "report actual class counts; exclude dual_uninformative without backfill",
        "source_expansion_allowed": False,
        "backfill_performed": False,
        "minimum_pool_count": None,
        "precalibration_problem_count": 2,
        "calibrated_problem_count": 2,
        "retry_problem_count": 0,
        "active_problem_count": 1,
        "excluded_dual_uninformative_count": 1,
        "calibrated_problem_order_sha256": stable_json_hash(["p-active", "p-saturated"]),
        "active_order_sha256": stable_json_hash(active_ids),
        "class_counts": class_counts,
        "active_class_counts": active_class_counts,
        "disposition_counts": dispositions,
        "sft_checkpoint": {"run_id": "B-test"},
        "public_definition_sha256": hashlib.sha256(b"public").hexdigest(),
        "hidden_definition_sha256": hashlib.sha256(b"hidden").hexdigest(),
        "bindings": {"authority": hashlib.sha256(b"authority").hexdigest()},
        "artifacts": artifacts,
    }
    _write_json(root / "calibration_manifest.json", manifest)
    return root


def test_reduced_calibrated_pool_accepts_exact_no_backfill_artifact(tmp_path: Path) -> None:
    pool = _build_pool(tmp_path / "pool")
    summary = check_reduced_calibrated_pool(pool)

    assert summary.selected_problems == 1
    assert summary.dual_informative == 1
    assert summary.public_only == 0
    assert summary.hidden_only == 0
    assert summary.sft_overlap_count == 0
    assert summary.active_order_sha256 == stable_json_hash(["p-active"])

    binding = load_grpo_benchmark_binding(
        calibration_manifest_path=pool / "calibration_manifest.json",
        refresh_dataset_dir=tmp_path / "unused-refresh",
        reference_dataset_dir=tmp_path / "unused-reference",
        verification_workers=8,
        role="k8_candidate",
    )
    assert binding.active_order_sha256 == summary.active_order_sha256
    assert binding.public_training_sha256 == _sha(pool / "training/public_grpo.jsonl")
    assert binding.hidden_training_sha256 == _sha(pool / "training/hidden_grpo.jsonl")


def test_reduced_calibrated_pool_rejects_training_tamper(tmp_path: Path) -> None:
    pool = _build_pool(tmp_path / "pool")
    with (pool / "training/public_grpo.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("\n")

    with pytest.raises(ReducedCalibratedPoolError, match="artifact hash mismatch"):
        check_reduced_calibrated_pool(pool)


def test_reduced_calibrated_pool_rejects_backfill_flag(tmp_path: Path) -> None:
    pool = _build_pool(tmp_path / "pool")
    manifest_path = pool / "calibration_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["backfill_performed"] = True
    _write_json(manifest_path, manifest)

    with pytest.raises(ReducedCalibratedPoolError, match="identity/protocol"):
        check_reduced_calibrated_pool(pool)
