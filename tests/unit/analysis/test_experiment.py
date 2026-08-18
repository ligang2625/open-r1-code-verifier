"""Tests for strict A-D analysis manifests and source identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from code_verifier.analysis.experiment import AnalysisConfig, AnalysisError, load_analysis_config, load_analysis_inputs
from code_verifier.evaluation.evaluate import (
    EvaluationRecord,
    evaluation_record_to_mapping,
    resolved_evaluation_config_hash,
)
from code_verifier.training import grpo_evaluation_checkpoint_id, load_completed_grpo_checkpoint


def _record(
    *, run_id: str, checkpoint: str, config_hash: str, problem_id: str, dataset_hash: str = "d" * 64
) -> EvaluationRecord:
    return EvaluationRecord(
        run_id=run_id,
        model_id="example/model",
        checkpoint=checkpoint,
        dataset_hash=dataset_hash,
        config_hash=config_hash,
        problem_id=problem_id,
        prompt_hash=(problem_id[-1] * 64),
        completion="```python\ndef solve(x): return x\n```",
        extracted_code="def solve(x): return x\n",
        parse_success=True,
        target_function_found=True,
        visible_pass_rate=1.0,
        train_hidden_pass_rate=1.0,
        eval_hidden_pass_rate=1.0,
        execution_status="passed",
        visible_execution_status="passed",
        train_hidden_execution_status="passed",
        eval_hidden_execution_status="passed",
        visible_failure_counts={},
        train_hidden_failure_counts={},
        eval_hidden_failure_counts={},
        parse_error_type=None,
        runtime_ms=1.0,
        generation_latency_ms=2.0,
        completion_tokens=3,
        error_category_auto="passed",
    )


def _write_sft_run(path: Path) -> None:
    path.mkdir()
    checkpoint = path / "checkpoints"
    checkpoint.mkdir()
    (path / "run.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "run_id": "sft-b",
                "model_id": "example/model",
                "model_revision": "a" * 40,
                "dataset_hash": "b" * 64,
                "config_hash": "c" * 64,
                "dependency_lock_hash": "e" * 64,
                "seed": 42,
                "gpu_name": "fixture-gpu",
                "gpu_hours": 1.0,
            }
        ),
        encoding="utf-8",
    )
    (checkpoint / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "example/model", "peft_type": "LORA"}), encoding="utf-8"
    )
    (checkpoint / "adapter_model.safetensors").write_bytes(b"fixture")
    for name in ("resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log"):
        (path / name).touch()


def _write_grpo_run(path: Path, parent: Path, *, reward_mode: str) -> None:
    path.mkdir()
    checkpoint = path / "checkpoints"
    checkpoint.mkdir()
    parent_checkpoint = (parent / "checkpoints").resolve()
    metadata = {
        "status": "completed",
        "run_id": f"grpo-{reward_mode}",
        "reward_mode": reward_mode,
        "dataset_hash": "f" * 64,
        "config_hash": ("1" if reward_mode == "public" else "2") * 64,
        "dependency_lock_hash": "e" * 64,
        "seed": 42,
        "parent_sft_run_path": str(parent.resolve()),
        "parent_sft_run_id": "sft-b",
        "parent_sft_checkpoint_path": str(parent_checkpoint),
        "parent_sft_model_id": "example/model",
        "parent_sft_model_revision": "a" * 40,
        "parent_sft_dataset_hash": "b" * 64,
        "parent_sft_config_hash": "c" * 64,
        "parent_sft_dependency_lock_hash": "e" * 64,
        "parent_sft_seed": 42,
        "gpu_name": "fixture-gpu",
        "gpu_hours": 2.0,
    }
    (path / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (checkpoint / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "example/model", "revision": "a" * 40}), encoding="utf-8"
    )
    (checkpoint / "adapter_model.safetensors").write_bytes(b"fixture")
    for name in (
        "resolved_config.yaml",
        "environment.json",
        "metrics.jsonl",
        "rollouts.jsonl",
        "rewards.jsonl",
        "group_metrics.jsonl",
        "stdout.log",
        "stderr.log",
    ):
        (path / name).touch()


def _write_evaluation(
    path: Path,
    *,
    run_id: str,
    checkpoint: str,
    piston_config: Path,
    problem_ids: tuple[str, ...] = ("p1", "p2"),
    dataset_hash: str = "d" * 64,
    seed: int = 42,
) -> None:
    (path / "samples").mkdir(parents=True)
    piston_config_sha256 = hashlib.sha256(piston_config.read_bytes()).hexdigest()
    resolved = {
        "dataset_dir": "/fixture/data",
        "split": "test",
        "piston_config": str(piston_config),
        "model_revision": "a" * 40,
        "checkpoint": checkpoint,
        "device": "cuda",
        "generation": {
            "do_sample": False,
            "temperature": None,
            "top_p": None,
            "max_new_tokens": 512,
            "dtype": "float16",
        },
        "run_id": run_id,
        "model_id": "example/model",
        "seed": seed,
    }
    config_hash = resolved_evaluation_config_hash(resolved, piston_config_sha256=piston_config_sha256)
    records = [
        _record(
            run_id=run_id,
            checkpoint=checkpoint,
            config_hash=config_hash,
            problem_id=item,
            dataset_hash=dataset_hash,
        )
        for item in problem_ids
    ]
    metadata = {
        "status": "completed",
        "run_id": run_id,
        "model_id": "example/model",
        "model_revision": "a" * 40,
        "checkpoint": checkpoint,
        "dataset_hash": dataset_hash,
        "config_hash": config_hash,
        "seed": seed,
        "project_commit": "fixture-project-commit",
        "open_r1_commit": "fixture-open-r1-commit",
        "dependency_lock_hash": "e" * 64,
        "piston_config_sha256": piston_config_sha256,
    }
    (path / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (path / "resolved_config.yaml").write_text(yaml.safe_dump(resolved), encoding="utf-8")
    (path / "samples" / "results.jsonl").write_text(
        "".join(json.dumps(evaluation_record_to_mapping(record)) + "\n" for record in records), encoding="utf-8"
    )


def _fixture(tmp_path: Path) -> AnalysisConfig:
    piston = tmp_path / "piston.yaml"
    piston.write_text("piston:\n  url: http://127.0.0.1:2000\n", encoding="utf-8")
    sft = tmp_path / "sft"
    public = tmp_path / "public"
    hidden = tmp_path / "hidden"
    _write_sft_run(sft)
    _write_grpo_run(public, sft, reward_mode="public")
    _write_grpo_run(hidden, sft, reward_mode="hidden")
    public_id = load_completed_grpo_checkpoint(public)
    hidden_id = load_completed_grpo_checkpoint(hidden)
    checkpoints = {
        "base": "base",
        "sft-eval": str((sft / "checkpoints").resolve()),
        "public-eval": grpo_evaluation_checkpoint_id(public_id),
        "hidden-eval": grpo_evaluation_checkpoint_id(hidden_id),
    }
    eval_dirs: dict[str, Path] = {}
    for run_id, checkpoint in checkpoints.items():
        eval_dirs[run_id] = tmp_path / run_id
        _write_evaluation(eval_dirs[run_id], run_id=run_id, checkpoint=checkpoint, piston_config=piston)
    return AnalysisConfig(
        base_evaluation_run_dir=eval_dirs["base"],
        sft_evaluation_run_dir=eval_dirs["sft-eval"],
        public_evaluation_run_dir=eval_dirs["public-eval"],
        hidden_evaluation_run_dir=eval_dirs["hidden-eval"],
        sft_training_run_dir=sft,
        public_grpo_run_dir=public,
        hidden_grpo_run_dir=hidden,
        bootstrap_seed=7,
        bootstrap_resamples=100,
        confidence_level=0.95,
        gpu_hour_cost_usd=None,
        manual_labels_path=None,
    )


def test_load_analysis_config_requires_exact_schema(tmp_path: Path) -> None:
    manifest = tmp_path / "analysis.yaml"
    manifest.write_text("unknown: true\n", encoding="utf-8")
    with pytest.raises(AnalysisError):
        load_analysis_config(manifest)


def test_load_analysis_inputs_accepts_aligned_completed_a_to_d_fixture(tmp_path: Path) -> None:
    inputs = load_analysis_inputs(_fixture(tmp_path))

    assert set(inputs.evaluation_records) == {"Base", "SFT", "Public-RLVR", "Hidden-RLVR"}
    assert inputs.public_grpo_checkpoint.parent_sft == inputs.sft_checkpoint
    assert inputs.hidden_grpo_checkpoint.parent_sft == inputs.sft_checkpoint


def test_load_analysis_inputs_accepts_finalized_evaluation_with_missing_historical_piston_path(tmp_path: Path) -> None:
    config = _fixture(tmp_path)
    (tmp_path / "piston.yaml").unlink()

    inputs = load_analysis_inputs(config)

    assert len(inputs.evaluation_records["Base"]) == 2


@pytest.mark.parametrize("drift", ["problem", "dataset"])
def test_load_analysis_inputs_rejects_problem_set_or_dataset_drift(tmp_path: Path, drift: str) -> None:
    config = _fixture(tmp_path)
    target = config.hidden_evaluation_run_dir
    piston = tmp_path / "piston.yaml"
    for child in target.rglob("*"):
        if child.is_file():
            child.unlink()
    for child in sorted(target.rglob("*"), reverse=True):
        if child.is_dir():
            child.rmdir()
    target.rmdir()
    _write_evaluation(
        target,
        run_id="hidden-eval",
        checkpoint=grpo_evaluation_checkpoint_id(load_completed_grpo_checkpoint(config.hidden_grpo_run_dir)),
        piston_config=piston,
        problem_ids=("p1",) if drift == "problem" else ("p1", "p2"),
        dataset_hash="9" * 64 if drift == "dataset" else "d" * 64,
    )
    with pytest.raises(AnalysisError):
        load_analysis_inputs(config)


def test_load_analysis_inputs_rejects_decoding_or_seed_drift(tmp_path: Path) -> None:
    config = _fixture(tmp_path)
    metadata_path = config.public_evaluation_run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["seed"] = 9
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(AnalysisError, match="seed"):
        load_analysis_inputs(config)


@pytest.mark.parametrize("tamper", ["resolved_config", "piston_digest"])
def test_load_analysis_inputs_rejects_resolved_evaluation_identity_tampering(tmp_path: Path, tamper: str) -> None:
    config = _fixture(tmp_path)
    if tamper == "resolved_config":
        path = config.public_evaluation_run_dir / "resolved_config.yaml"
        resolved = yaml.safe_load(path.read_text(encoding="utf-8"))
        resolved["generation"]["max_new_tokens"] = 999
        path.write_text(yaml.safe_dump(resolved), encoding="utf-8")
    else:
        metadata_path = config.public_evaluation_run_dir / "run.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["piston_config_sha256"] = "9" * 64
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(AnalysisError, match="resolved evaluation config"):
        load_analysis_inputs(config)


@pytest.mark.parametrize(
    "field,value", [("project_commit", ""), ("open_r1_commit", 7), ("dependency_lock_hash", None)]
)
def test_load_analysis_inputs_rejects_missing_or_malformed_source_provenance(
    tmp_path: Path, field: str, value: object
) -> None:
    config = _fixture(tmp_path)
    metadata_path = config.base_evaluation_run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(AnalysisError, match="provenance"):
        load_analysis_inputs(config)


def test_load_analysis_inputs_rejects_b_checkpoint_mismatch(tmp_path: Path) -> None:
    config = _fixture(tmp_path)
    metadata_path = config.sft_evaluation_run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["checkpoint"] = "/wrong/checkpoint"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(AnalysisError):
        load_analysis_inputs(config)


def test_load_analysis_inputs_rejects_c_d_parent_or_reward_mode_drift(tmp_path: Path) -> None:
    config = _fixture(tmp_path)
    with pytest.raises(AnalysisError):
        load_analysis_inputs(replace(config, public_grpo_run_dir=config.hidden_grpo_run_dir))
