"""Regression tests for explicit cross-commit GRPO resume lineage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_verifier.execution import MockExecutor
from code_verifier.training.grpo import (
    GRPO_RESUME_CODE_MIGRATION_OPERATIONAL_REWARD_RESILIENCE,
    GRPOTrainingConfig,
    GRPOTrainingError,
    run_grpo_training,
)
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
    checkpoint_state_path = checkpoint / "code_verifier_log_state.json"
    checkpoint_state = json.loads(checkpoint_state_path.read_text(encoding="utf-8"))
    checkpoint_state["version"] = 1
    checkpoint_state.pop("code_commit")
    checkpoint_state_path.write_text(json.dumps(checkpoint_state), encoding="utf-8")
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

    with pytest.raises(GRPOTrainingError, match="requires explicit operational_reward_resilience_v1"):
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
            resume_run_git_commit=preserved_commit,
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
        resume_code_migration=GRPO_RESUME_CODE_MIGRATION_OPERATIONAL_REWARD_RESILIENCE,
    )

    metadata = json.loads((resumed.run_dir / "run.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "completed"
    assert metadata["git_commit"] == preserved_commit
    assert len(metadata["attempts"]) == 2
    assert "code_commit" not in metadata["attempts"][0]
    assert metadata["attempts"][1]["code_commit"] == current_commit
    assert metadata["attempts"][1]["resume_from_checkpoint"] == "checkpoints/checkpoint-1"
    migration = metadata["attempts"][1]["code_migration"]
    assert migration["compatibility_class"] == GRPO_RESUME_CODE_MIGRATION_OPERATIONAL_REWARD_RESILIENCE
    assert migration["from_commit"] == preserved_commit
    assert migration["to_commit"] == current_commit
    assert migration["resume_from_checkpoint"] == "checkpoints/checkpoint-1"
    assert migration["scientific_change"] is False
    assert migration["reward_infrastructure_retry_policy_version"] == "grpo-reward-infra-retry-v1"
    retry = metadata["attempts"][1]["reward_infrastructure_retry"]
    assert retry["max_retries_per_reward_item"] == 3
    assert retry["retry_attempts"] == 0


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


def test_grpo_v2_checkpoint_records_actual_training_code_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    state = json.loads((checkpoint / "code_verifier_log_state.json").read_text(encoding="utf-8"))
    metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))

    assert state["version"] == 2
    assert state["code_commit"] == metadata["git_commit"]


def test_same_code_v2_checkpoint_resume_does_not_record_false_migration(
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
    state_path = checkpoint / "code_verifier_log_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["version"] = 2
    state["code_commit"] = current_commit
    state_path.write_text(json.dumps(state), encoding="utf-8")

    summary = run_grpo_training(
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
        resume_code_migration=GRPO_RESUME_CODE_MIGRATION_OPERATIONAL_REWARD_RESILIENCE,
    )

    metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    assert metadata["git_commit"] == preserved_commit
    assert metadata["attempts"][-1]["code_commit"] == current_commit
    assert "code_migration" not in metadata["attempts"][-1]


def test_v2_checkpoint_migration_uses_checkpoint_commit_and_requires_permission(
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
    checkpoint_commit = "a" * 40 if current_commit != "a" * 40 else "b" * 40
    state_path = checkpoint / "code_verifier_log_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["version"] = 2
    state["code_commit"] = checkpoint_commit
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="checkpoint resume requires explicit"):
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
            resume_run_git_commit=preserved_commit,
        )

    summary = run_grpo_training(
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
        resume_code_migration=GRPO_RESUME_CODE_MIGRATION_OPERATIONAL_REWARD_RESILIENCE,
    )
    attempt = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))["attempts"][-1]
    assert attempt["code_migration"]["from_commit"] == checkpoint_commit
    assert attempt["code_migration"]["to_commit"] == current_commit


def test_resume_rejects_malformed_v2_checkpoint_code_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root, checkpoint, _, preserved_commit = _make_legacy_failed_run(
        tmp_path, monkeypatch
    )
    state_path = checkpoint / "code_verifier_log_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["version"] = 2
    state["code_commit"] = "unknown"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(GRPOTrainingError, match="log-state identity is invalid"):
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
            resume_run_git_commit=preserved_commit,
            resume_code_migration=GRPO_RESUME_CODE_MIGRATION_OPERATIONAL_REWARD_RESILIENCE,
        )


def test_resume_code_migration_is_rejected_for_fresh_run(
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
            resume_code_migration=GRPO_RESUME_CODE_MIGRATION_OPERATIONAL_REWARD_RESILIENCE,
        )
