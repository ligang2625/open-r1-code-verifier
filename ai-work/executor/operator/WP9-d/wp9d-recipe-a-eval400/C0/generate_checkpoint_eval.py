#!/usr/bin/env python3
"""Generate one canonical eval400 bundle from a saved Recipe A GRPO checkpoint."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from code_verifier.evaluation.evaluate import load_evaluation_config
from code_verifier.evaluation.generate import TransformersCompletionGenerator
from code_verifier.evaluation.staged import run_generation_bundle
from code_verifier.runtime_telemetry import RuntimeUtilizationSampler
from code_verifier.training import grpo_evaluation_checkpoint_id, load_completed_grpo_checkpoint

FORMAL_TRAINING_COMMIT = "7b5e097b448b6c42fb9faf1f27711a65e00d2075"
MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
ALLOWED_STEPS = {300, 600, 900, 1200}
EXPECTED_TARGET_MODULES = {"q_proj", "k_proj", "v_proj", "o_proj"}


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def select_checkpoint(run_dir: Path, step: int):
    """Return a validated immutable GRPO identity pointing at checkpoint-<step>."""
    if step not in ALLOWED_STEPS:
        raise RuntimeError(f"checkpoint step must be one of {sorted(ALLOWED_STEPS)}")
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.parent_sft.model_id != MODEL_ID or identity.parent_sft.model_revision != MODEL_REVISION:
        raise RuntimeError("Recipe A parent model identity drift")
    if identity.parent_sft.run_id != "B-sft-formal-seed42" or identity.parent_sft.seed != 42:
        raise RuntimeError("Recipe A parent B identity drift")
    checkpoint_dir = identity.checkpoint_dir / f"checkpoint-{step}"
    resolved_root = identity.checkpoint_dir.resolve(strict=True)
    resolved_checkpoint = checkpoint_dir.resolve(strict=True)
    if checkpoint_dir.is_symlink() or resolved_checkpoint.parent != resolved_root:
        raise RuntimeError("selected checkpoint must belong directly to the completed GRPO run")
    required = {
        "adapter_config.json",
        "adapter_model.safetensors",
        "trainer_state.json",
        "code_verifier_log_state.json",
    }
    for name in required:
        path = resolved_checkpoint / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            raise RuntimeError(f"selected checkpoint has invalid required artifact: {name}")
    trainer_state = _load_json(resolved_checkpoint / "trainer_state.json")
    if trainer_state.get("global_step") != step:
        raise RuntimeError("selected checkpoint trainer_state global_step drift")
    log_state = _load_json(resolved_checkpoint / "code_verifier_log_state.json")
    if log_state.get("global_step") != step or log_state.get("code_commit") != FORMAL_TRAINING_COMMIT:
        raise RuntimeError("selected checkpoint log-state provenance drift")
    adapter = _load_json(resolved_checkpoint / "adapter_config.json")
    if adapter.get("base_model_name_or_path") != MODEL_ID:
        raise RuntimeError("selected checkpoint adapter base model drift")
    if adapter.get("r") != 16 or adapter.get("lora_alpha") != 32 or adapter.get("lora_dropout") != 0.05:
        raise RuntimeError("selected checkpoint LoRA hyperparameter drift")
    targets = adapter.get("target_modules")
    if not isinstance(targets, list) or set(targets) != EXPECTED_TARGET_MODULES:
        raise RuntimeError("selected checkpoint LoRA target-module drift")
    return replace(identity, checkpoint_dir=resolved_checkpoint)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--grpo-run-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-step", type=int, choices=sorted(ALLOWED_STEPS), required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()
    if args.seed != 42:
        raise RuntimeError("formal Recipe A eval generation requires seed=42")
    if args.batch_size != 4:
        raise RuntimeError("formal Recipe A eval generation requires batch_size=4")

    identity = select_checkpoint(args.grpo_run_dir, args.checkpoint_step)
    config = load_evaluation_config(args.config)
    config = replace(
        config,
        dataset_dir=args.dataset_dir,
        model_revision=identity.parent_sft.model_revision,
        checkpoint=grpo_evaluation_checkpoint_id(identity),
    )
    generator = TransformersCompletionGenerator.from_grpo_checkpoint(
        base_model_id=identity.parent_sft.model_id,
        base_model_revision=identity.parent_sft.model_revision,
        parent_sft_adapter_dir=identity.parent_sft.checkpoint_dir,
        grpo_adapter_dir=identity.checkpoint_dir,
        device=config.device,
        config=config.generation,
    )
    summary = run_generation_bundle(
        config=config,
        model_id=identity.parent_sft.model_id,
        generator=generator,
        run_id=args.run_name,
        output_root=args.output_dir,
        seed=args.seed,
        batch_size=args.batch_size,
        utilization_sampler=RuntimeUtilizationSampler(),
    )
    print(
        f"generated checkpoint={args.checkpoint_step} problems={summary.total_problems} "
        f"resumed={summary.completed_before_run} generated={summary.generated_this_run}"
    )
    print(f"generation_run={summary.run_dir}")
    print(f"generations={summary.records_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
