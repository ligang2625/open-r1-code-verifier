"""Tests for training curves, cost rows, human labels, and report artifacts."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from code_verifier.analysis.compare import FailureCandidate
from code_verifier.analysis.experiment import AnalysisError
from code_verifier.analysis.report import build_cost_row, load_manual_labels, load_training_curve_rows


def _write_run(path: Path, *, run_id: str, metrics: list[dict[str, object]], gpu_hours: float = 2.0) -> None:
    path.mkdir()
    (path / "run.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "run_id": run_id,
                "gpu_name": "fixture-gpu",
                "gpu_hours": gpu_hours,
            }
        ),
        encoding="utf-8",
    )
    (path / "metrics.jsonl").write_text(
        "".join(json.dumps(row, allow_nan=False) + "\n" for row in metrics), encoding="utf-8"
    )


def _reward_row(runtime_ms: float) -> dict[str, object]:
    return {
        "item_index": 0,
        "group_index": 0,
        "group_item_index": 0,
        "problem_id": "p1",
        "mode": "public",
        "test_reward": 1.0,
        "executable_reward": 0.1,
        "timeout_penalty": 0.0,
        "invalid_format_penalty": 0.0,
        "total_reward": 1.1,
        "executor_runtime_ms": runtime_ms,
        "status": "passed",
        "parsed": True,
        "executed": True,
        "infrastructure_failure": False,
        "passed_tests": 1,
        "total_tests": 1,
        "parse_error_type": None,
        "failure_counts": {},
    }


def _rollout_row(token_count: int) -> dict[str, object]:
    return {
        "item_index": 0,
        "group_index": 0,
        "group_item_index": 0,
        "problem_id": "p1",
        "reward_mode": "public",
        "completion": "PRIVATE_ROLLOUT",
        "completion_token_count": token_count,
        "truncated": False,
        "total_reward": 1.1,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _candidate(index: int) -> FailureCandidate:
    return FailureCandidate(
        method="Public-RLVR",
        run_id="public-run",
        problem_id=f"p{index}",
        candidate_reasons=("visible_pass_eval_fail",),
        auto_error_category="visible_only_success",
        visible_pass_rate=1.0,
        train_hidden_pass_rate=0.0,
        eval_hidden_pass_rate=0.0,
        execution_status="wrong_answer",
    )


def test_load_training_curve_rows_emits_long_form_finite_scalars(tmp_path: Path) -> None:
    run = tmp_path / "sft"
    _write_run(
        run,
        run_id="sft-run",
        metrics=[
            {"record_type": "trainer", "step": 1, "epoch": 0.5, "loss": 0.25, "ignored": "bad"},
            {"record_type": "summary", "train_loss": 0.2},
        ],
    )
    with pytest.raises(AnalysisError, match="numeric"):
        load_training_curve_rows(run, method="SFT")
    _write_jsonl(
        run / "metrics.jsonl",
        [{"record_type": "trainer", "step": 1, "epoch": 0.5, "loss": 0.25}],
    )

    rows = load_training_curve_rows(run, method="SFT")

    assert [asdict(row) for row in rows] == [
        {
            "method": "SFT",
            "run_id": "sft-run",
            "record_index": 1,
            "step": 1.0,
            "epoch": 0.5,
            "metric": "loss",
            "value": 0.25,
        }
    ]


def test_load_training_curve_rows_rejects_completed_run_without_curve_data(tmp_path: Path) -> None:
    run = tmp_path / "sft"
    _write_run(run, run_id="sft-run", metrics=[{"record_type": "summary", "train_loss": 0.2}])

    with pytest.raises(AnalysisError, match="no trainer curve"):
        load_training_curve_rows(run, method="SFT")


def test_build_grpo_cost_row_counts_rollouts_tokens_and_executor_hours(tmp_path: Path) -> None:
    run = tmp_path / "public"
    _write_run(run, run_id="public-run", metrics=[])
    _write_jsonl(run / "rollouts.jsonl", [_rollout_row(5), _rollout_row(7)])
    _write_jsonl(run / "rewards.jsonl", [_reward_row(1000.0), _reward_row(2000.0)])

    row = build_cost_row(run, method="Public-RLVR", gpu_hour_cost_usd=None)

    assert row.rollouts == 2
    assert row.generated_tokens == 12
    assert row.executor_hours == pytest.approx(3000.0 / 3_600_000.0)


def test_build_sft_cost_row_uses_gpu_hours_and_marks_rollout_fields_na(tmp_path: Path) -> None:
    run = tmp_path / "sft"
    _write_run(run, run_id="sft-run", metrics=[])

    row = build_cost_row(run, method="SFT", gpu_hour_cost_usd=None)

    assert row.gpu_hours == 2.0
    assert row.rollouts is None
    assert row.generated_tokens is None
    assert row.executor_hours is None


def test_cost_estimate_requires_explicit_hourly_rate(tmp_path: Path) -> None:
    run = tmp_path / "sft"
    _write_run(run, run_id="sft-run", metrics=[])

    assert build_cost_row(run, method="SFT", gpu_hour_cost_usd=None).estimated_cost_usd is None
    assert build_cost_row(run, method="SFT", gpu_hour_cost_usd=3.0).estimated_cost_usd == 6.0


def _write_labels(path: Path, candidates: list[FailureCandidate]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "method",
                "run_id",
                "problem_id",
                "candidate_reasons",
                "auto_error_category",
                "manual_category",
                "notes",
                "source_results_path",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "method": candidate.method,
                    "run_id": candidate.run_id,
                    "problem_id": candidate.problem_id,
                    "candidate_reasons": "|".join(candidate.candidate_reasons),
                    "auto_error_category": candidate.auto_error_category,
                    "manual_category": "missed_edge_case",
                    "notes": "fixture",
                    "source_results_path": "/fixture/results.jsonl",
                }
            )


def test_load_manual_labels_requires_unique_known_candidates(tmp_path: Path) -> None:
    candidate = _candidate(1)
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [candidate, candidate])

    with pytest.raises(AnalysisError, match="uniquely"):
        load_manual_labels(labels, candidates=[candidate])


def test_manual_label_fixture_can_validate_twenty_case_contract_without_becoming_research_evidence(
    tmp_path: Path,
) -> None:
    candidates = [_candidate(index) for index in range(20)]
    labels = tmp_path / "labels.csv"
    _write_labels(labels, candidates)

    loaded = load_manual_labels(labels, candidates=candidates)

    assert len(loaded) == 20
    assert all(row["notes"] == "fixture" for row in loaded)
