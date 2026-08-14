"""Tests for training curves, cost rows, human labels, and report artifacts."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

import code_verifier.analysis.report as report_module
from code_verifier.analysis.compare import FailureCandidate
from code_verifier.analysis.experiment import AnalysisConfig, AnalysisError
from code_verifier.analysis.report import (
    analyze_experiment,
    build_cost_row,
    load_manual_labels,
    load_training_curve_rows,
)
from code_verifier.evaluation.evaluate import evaluation_record_to_mapping, load_evaluation_records
from tests.unit.analysis.test_experiment import _fixture


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


def _write_analysis_logs(config: AnalysisConfig) -> None:
    for run_dir, loss in (
        (config.sft_training_run_dir, 0.3),
        (config.public_grpo_run_dir, 0.2),
        (config.hidden_grpo_run_dir, 0.1),
    ):
        _write_jsonl(
            run_dir / "metrics.jsonl",
            [
                {"record_type": "trainer", "step": 1, "loss": loss},
                {"record_type": "summary", "train_loss": loss},
            ],
        )
    for run_dir in (config.public_grpo_run_dir, config.hidden_grpo_run_dir):
        _write_jsonl(run_dir / "rollouts.jsonl", [_rollout_row(5)])
        _write_jsonl(run_dir / "rewards.jsonl", [_reward_row(1000.0)])


def _analysis_fixture(tmp_path: Path) -> AnalysisConfig:
    config = _fixture(tmp_path)
    _write_analysis_logs(config)
    public_results = config.public_evaluation_run_dir / "samples" / "results.jsonl"
    records = load_evaluation_records(public_results)
    records[0] = replace(
        records[0],
        eval_hidden_pass_rate=0.0,
        execution_status="wrong_answer",
        eval_hidden_execution_status="wrong_answer",
        eval_hidden_failure_counts={"wrong_answer": 1},
        error_category_auto="visible_only_success",
    )
    public_results.write_text(
        "".join(json.dumps(evaluation_record_to_mapping(record)) + "\n" for record in records), encoding="utf-8"
    )
    return config


def test_analyze_experiment_writes_exact_artifact_layout_atomically(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)
    output = tmp_path / "analysis"

    summary = analyze_experiment(config, output_dir=output)

    assert summary.total_problems == 2
    assert summary.candidate_count == 1
    assert {path.name for path in output.iterdir()} == report_module._ANALYSIS_LAYOUT


def test_main_results_uses_distinct_public_and_train_verifier_gap_semantics(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)
    output = tmp_path / "analysis"

    analyze_experiment(config, output_dir=output)
    rows = {row["method"]: row for row in csv.DictReader((output / "main_results.csv").open())}

    assert rows["Base"]["train_verifier_gap"] == ""
    assert rows["SFT"]["train_verifier_gap"] == ""
    assert rows["Public-RLVR"]["train_verifier_gap"] == "0.5"
    assert rows["Hidden-RLVR"]["train_verifier_gap"] == "0.0"
    assert rows["Public-RLVR"]["public_eval_gap"] == "0.5"


def test_report_data_traces_every_method_to_source_results_hash(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)
    output = tmp_path / "analysis"

    analyze_experiment(config, output_dir=output)
    report = json.loads((output / "report_data.json").read_text())

    assert set(report["sources"]) == {"Base", "SFT", "Public-RLVR", "Hidden-RLVR"}
    assert all(len(source["results_sha256"]) == 64 for source in report["sources"].values())


def test_report_outputs_do_not_copy_completion_code_or_tests(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)
    output = tmp_path / "analysis"

    analyze_experiment(config, output_dir=output)
    derived = "\n".join(path.read_text() for path in output.iterdir())

    assert "PRIVATE_COMPLETION" not in derived
    assert "PRIVATE_CODE" not in derived
    assert "```python" not in derived


def test_manual_error_counts_remain_pending_without_human_labels(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)
    output = tmp_path / "analysis"

    analyze_experiment(config, output_dir=output)
    report = json.loads((output / "report_data.json").read_text())

    assert report["manual_analysis_status"] == "pending"
    assert (output / "manual_error_counts.csv").read_text() == "method,manual_category,count\n"


def test_existing_output_directory_fails_closed_without_partial_overwrite(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)
    output = tmp_path / "analysis"
    output.mkdir()
    marker = output / "marker"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(AnalysisError, match="must not already exist"):
        analyze_experiment(config, output_dir=output)

    assert marker.read_text() == "keep"
