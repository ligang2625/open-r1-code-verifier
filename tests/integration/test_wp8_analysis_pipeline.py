"""WP8 deterministic synthetic analysis integration evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from code_verifier.analysis import AnalysisError, analyze_experiment
from tests.unit.analysis.test_report import _analysis_fixture


def _comparison_row(path: Path, left: str, right: str) -> dict[str, str]:
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    return next(row for row in rows if row["left_method"] == left and row["right_method"] == right)


def test_wp8_analysis_pipeline_generates_traceable_fixture_report(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)

    summary = analyze_experiment(
        config,
        output_dir=tmp_path / "analysis",
        evidence_class="engineering_fixture_synthetic",
    )
    report = json.loads(summary.report_data_path.read_text(encoding="utf-8"))
    main_rows = list(csv.DictReader(summary.main_results_path.open(encoding="utf-8", newline="")))

    assert summary.total_problems == 2
    assert [row["method"] for row in main_rows] == ["Base", "SFT", "Public-RLVR", "Hidden-RLVR"]
    assert report["bootstrap"]["unit"] == "problem"
    assert report["reward_hacking_candidate_status"] == "automated_proxy_not_human_conclusion"
    assert all(Path(source["results_path"]).is_file() for source in report["sources"].values())
    assert all(len(source["results_sha256"]) == 64 for source in report["sources"].values())


def test_wp8_analysis_pipeline_pairs_c_d_by_problem_id(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)
    first = analyze_experiment(config, output_dir=tmp_path / "analysis-first")
    expected = _comparison_row(first.paired_comparisons_path, "Hidden-RLVR", "Public-RLVR")
    hidden_results = config.hidden_evaluation_run_dir / "samples" / "results.jsonl"
    lines = hidden_results.read_text(encoding="utf-8").splitlines()
    hidden_results.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")

    second = analyze_experiment(config, output_dir=tmp_path / "analysis-second")

    assert _comparison_row(second.paired_comparisons_path, "Hidden-RLVR", "Public-RLVR") == expected


@pytest.mark.parametrize("drift", ["problem", "dataset", "checkpoint"])
def test_wp8_analysis_pipeline_rejects_identity_drift(tmp_path: Path, drift: str) -> None:
    config = _analysis_fixture(tmp_path)
    run_dir = config.hidden_evaluation_run_dir
    metadata_path = run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    results_path = run_dir / "samples" / "results.jsonl"
    if drift == "problem":
        rows = results_path.read_text(encoding="utf-8").splitlines()
        results_path.write_text(rows[0] + "\n", encoding="utf-8")
    elif drift == "dataset":
        metadata["dataset_hash"] = "9" * 64
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    else:
        metadata["checkpoint"] = "/copied/checkpoint"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(AnalysisError):
        analyze_experiment(config, output_dir=tmp_path / "analysis")
    assert not (tmp_path / "analysis").exists()
    assert not list(tmp_path.glob(".analysis.*"))


def test_wp8_fixture_outputs_never_claim_real_training_or_manual_evidence(tmp_path: Path) -> None:
    config = _analysis_fixture(tmp_path)

    summary = analyze_experiment(
        config,
        output_dir=tmp_path / "analysis",
        evidence_class="engineering_fixture_synthetic",
    )
    report = json.loads(summary.report_data_path.read_text(encoding="utf-8"))
    derived = "\n".join(path.read_text(encoding="utf-8") for path in summary.output_dir.iterdir())

    assert report["manual_analysis_status"] == "pending"
    assert report["manual_label_count"] == 0
    assert report["evidence_class"] == "engineering_fixture_synthetic"
    assert "formal_validation" not in derived
    assert "real_training_completed" not in derived
    assert "PRIVATE_COMPLETION" not in derived
    assert "PRIVATE_CODE" not in derived
