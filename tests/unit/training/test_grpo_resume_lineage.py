"""Regression tests for explicit cross-commit GRPO resume lineage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_verifier.execution import MockExecutor
from code_verifier.training.grpo import GRPOTrainingConfig, GRPOTrainingError, run_grpo_training
from tests.unit.training.test_grpo import (
    _create_fake_resume_checkpoint,
    _passing_results,
    _prepare_fake_grpo_run,
)


def _make_legacy_failed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[GRPOTrainingConfig, GRPOTrainingConfig, Path, Path, Path, str, str]:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
    )
    checkpoint = _create_fake_resume_checkpoint(summary.run_dir)
    metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    current_commit = metadata["git_commit"]
    assert isinstance(current_commit, str)
    preserved_commit = "0" * 40 if current_commit != "0" * 40 else "1" * 40
    metadata["git_commit"] = preserved_commit
    metadata["status"] = "failed"
    metadata["attempts"][-1]["status"] = "failed"
    metadata["attempts"][-1].pop("code_commit", None)
    (summary.run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    return public_config, hidden_config, sft_run_dir, output_root, checkpoint, current_commit, preserved_commit


def test_cross_commit_grpo_resume_requires_explicit_preserved_run_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root, checkpoint, _, preserved_commit = _make_legacy_failed_run(
        tmp_path, monkeypatch
    )
    run_json = output_root / public_config.run_name / "run.json"
    before = run_json.read_bytes()

    with pytest.raises(GRPOTrainingError, match="different project commit"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=42,
            executor=MockExecutor(_passing_results(4)),
            resume_from_checkpoint=checkpoint,
        )
    assert run_json.read_bytes() == before

    wrong_commit = "2" * 40 if preserved_commit != "2" * 40 else "3" * 40
    with pytest.raises(GRPOTrainingError, match="explicit resume_run_git_commit"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=42,
            executor=MockExecutor(_passing_results(4)),
            resume_from_checkpoint=checkpoint,
            resume_run_git_commit=wrong_commit,
        )
    assert run_json.read_bytes() == before


def test_cross_commit_grpo_resume_preserves_origin_and_records_new_attempt_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        public_config,
        hidden_config,
        sft_run_dir,
        output_root,
        checkpoint,
        current_commit,
        preserved_commit,
    ) = _make_legacy_failed_run(tmp_path, monkeypatch)

    resumed = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(4)),
        resume_from_checkpoint=checkpoint,
        resume_run_git_commit=preserved_commit,
    )

    metadata = json.loads((resumed.run_dir / "run.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "completed"
    assert metadata["git_commit"] == preserved_commit
    assert len(metadata["attempts"]) == 2
    assert "code_commit" not in metadata["attempts"][0]
    assert metadata["attempts"][1]["code_commit"] == current_commit
    assert metadata["attempts"][1]["resume_from_checkpoint"] == "checkpoints/checkpoint-1"


def test_resume_run_git_commit_is_rejected_without_resume_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    with pytest.raises(GRPOTrainingError, match="requires resume_from_checkpoint"):
        run_grpo_training(
            public_config,
            hidden_config,
            reward_mode="public",
            public_sft_run_dir=sft_run_dir,
            hidden_sft_run_dir=sft_run_dir,
            output_root=output_root,
            seed=42,
            executor=MockExecutor(_passing_results(4)),
            resume_run_git_commit="0" * 40,
        )
