#!/usr/bin/env python3
"""Generate frozen eval400 completions for the C32 SFT-continuation policy.

The trained C32 adapter is a delta on top of frozen parent B after B was safely
merged into the base model.  Therefore inference must reconstruct
A -> safe-merge B -> attach C32, rather than Base -> attach C32 directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from code_verifier.evaluation import TransformersCompletionGenerator, run_generation_bundle
from code_verifier.evaluation.evaluate import EvaluationConfig, load_evaluation_config
from code_verifier.runtime_telemetry import RuntimeUtilizationSampler
from code_verifier.training.sft import SFTCheckpointIdentity, load_completed_sft_checkpoint

EXPECTED_MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
EXPECTED_MODEL_REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
EXPECTED_PARENT_RUN_ID = "B-sft-formal-seed42"
EXPECTED_PARENT_DATASET_HASH = "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c"
EXPECTED_PARENT_CONFIG_HASH = "250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244"
EXPECTED_CHILD_RUN_ID = "wp9c-sft-only-active1354-seed42"
EXPECTED_CHILD_DATASET_HASH = "de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582"
EXPECTED_CHILD_CONFIG_HASH = "5d6a9579abf9cbb875ca5ee2137eb01a31c345de58d61f3b22cf260fc129633b"
EXPECTED_CHILD_TRAIN_COMMIT = "d59943855e2aab6b786cd5ec5796530a8f486206"
EXPECTED_DATASET_HASH = "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
EXPECTED_ORDER_SHA = "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
EXPECTED_PISTON_SHA = "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
RUN_NAME = "wp9c-sft-only-active1354-eval400-b4-seed42"
BATCH_SIZE = 4
SEED = 42


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parent_mapping(identity: SFTCheckpointIdentity) -> dict[str, object]:
    return {
        "run_id": identity.run_id,
        "model_id": identity.model_id,
        "model_revision": identity.model_revision,
        "dataset_hash": identity.dataset_hash,
        "config_hash": identity.config_hash,
        "dependency_lock_hash": identity.dependency_lock_hash,
        "seed": identity.seed,
    }


def _validate_adapter_identity(identity: SFTCheckpointIdentity, *, role: str) -> None:
    config = json.loads((identity.checkpoint_dir / "adapter_config.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("base_model_name_or_path") != EXPECTED_MODEL_ID:
        raise SystemExit(f"{role} adapter base model identity drift")
    revision = config.get("revision")
    if revision is not None and revision != EXPECTED_MODEL_REVISION:
        raise SystemExit(f"{role} adapter base revision drift")


def _load_lineage(parent_run: Path, child_run: Path) -> tuple[SFTCheckpointIdentity, SFTCheckpointIdentity]:
    parent = load_completed_sft_checkpoint(parent_run)
    child = load_completed_sft_checkpoint(child_run)
    if (
        parent.run_id != EXPECTED_PARENT_RUN_ID
        or parent.model_id != EXPECTED_MODEL_ID
        or parent.model_revision != EXPECTED_MODEL_REVISION
        or parent.dataset_hash != EXPECTED_PARENT_DATASET_HASH
        or parent.config_hash != EXPECTED_PARENT_CONFIG_HASH
        or parent.seed != SEED
    ):
        raise SystemExit("frozen parent B identity drift")
    if (
        child.run_id != EXPECTED_CHILD_RUN_ID
        or child.model_id != EXPECTED_MODEL_ID
        or child.model_revision != EXPECTED_MODEL_REVISION
        or child.dataset_hash != EXPECTED_CHILD_DATASET_HASH
        or child.config_hash != EXPECTED_CHILD_CONFIG_HASH
        or child.seed != SEED
    ):
        raise SystemExit("completed C32 SFT identity drift")
    child_run_json = json.loads((child.run_dir / "run.json").read_text(encoding="utf-8"))
    if child_run_json.get("git_commit") != EXPECTED_CHILD_TRAIN_COMMIT:
        raise SystemExit("completed C32 SFT training commit drift")
    if child_run_json.get("parent_sft") != _parent_mapping(parent):
        raise SystemExit("completed C32 SFT parent B lineage drift")
    _validate_adapter_identity(parent, role="parent B")
    _validate_adapter_identity(child, role="C32 SFT")
    return parent, child


def _continuation_checkpoint_id(parent: SFTCheckpointIdentity, child: SFTCheckpointIdentity) -> str:
    payload = {
        "kind": "sft_continuation_v1",
        "model_id": child.model_id,
        "model_revision": child.model_revision,
        "parent": {
            "run_id": parent.run_id,
            "dataset_hash": parent.dataset_hash,
            "config_hash": parent.config_hash,
            "dependency_lock_hash": parent.dependency_lock_hash,
            "seed": parent.seed,
            "adapter_config_sha256": _sha256(parent.checkpoint_dir / "adapter_config.json"),
            "adapter_model_sha256": _sha256(parent.checkpoint_dir / "adapter_model.safetensors"),
        },
        "child": {
            "run_id": child.run_id,
            "dataset_hash": child.dataset_hash,
            "config_hash": child.config_hash,
            "dependency_lock_hash": child.dependency_lock_hash,
            "seed": child.seed,
            "adapter_config_sha256": _sha256(child.checkpoint_dir / "adapter_config.json"),
            "adapter_model_sha256": _sha256(child.checkpoint_dir / "adapter_model.safetensors"),
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sft-continuation:{child.run_id}#identity={digest}"


def _resolved_config(config_path: Path, dataset_dir: Path, checkpoint: str) -> EvaluationConfig:
    config = load_evaluation_config(config_path)
    return replace(
        config,
        dataset_dir=dataset_dir,
        model_revision=EXPECTED_MODEL_REVISION,
        checkpoint=checkpoint,
    )


def _build_generator(config: EvaluationConfig, parent: SFTCheckpointIdentity, child: SFTCheckpointIdentity) -> Any:
    # The existing GRPO reconstruction primitive is exactly the required PEFT
    # composition: load A, attach+safe-merge parent B, attach a second read-only
    # adapter.  Here the second adapter is supervised C32, not a GRPO adapter.
    return TransformersCompletionGenerator.from_grpo_checkpoint(
        base_model_id=EXPECTED_MODEL_ID,
        base_model_revision=EXPECTED_MODEL_REVISION,
        parent_sft_adapter_dir=parent.checkpoint_dir,
        grpo_adapter_dir=child.checkpoint_dir,
        device=config.device,
        config=config.generation,
        local_files_only=True,
    )


def _postcheck(run_dir: Path, checkpoint: str, expected_project_commit: str) -> dict[str, object]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    expected: dict[str, object] = {
        "status": "completed",
        "run_id": RUN_NAME,
        "completed_records": 400,
        "total_problems": 400,
        "batch_size": BATCH_SIZE,
        "seed": SEED,
        "dataset_hash": EXPECTED_DATASET_HASH,
        "ordered_problem_ids_sha256": EXPECTED_ORDER_SHA,
        "piston_config_sha256": EXPECTED_PISTON_SHA,
        "project_commit": expected_project_commit,
        "model_id": EXPECTED_MODEL_ID,
        "model_revision": EXPECTED_MODEL_REVISION,
        "checkpoint": checkpoint,
    }
    for key, value in expected.items():
        if run.get(key) != value:
            raise SystemExit(f"generation postcheck failed: {key}: {run.get(key)!r} != {value!r}")
    records_sha = run.get("records_sha256")
    if not isinstance(records_sha, str) or re.fullmatch(r"[0-9a-f]{64}", records_sha) is None:
        raise SystemExit("generation records_sha256 is invalid")
    samples = run_dir / "samples" / "generations.jsonl"
    rows = sum(1 for line in samples.read_text(encoding="utf-8").splitlines() if line.strip())
    if rows != 400:
        raise SystemExit(f"generation row count {rows} != 400")
    return {
        "status": "C36_SFT_CONTINUATION_GENERATION_OK",
        "run_dir": str(run_dir),
        "records_sha256": records_sha,
        "checkpoint": checkpoint,
        "gpu_hours": run.get("gpu_hours"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--parent-sft-run-dir", type=Path, required=True)
    parser.add_argument("--child-sft-run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--project-commit", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--postcheck-only", action="store_true")
    args = parser.parse_args()

    parent, child = _load_lineage(args.parent_sft_run_dir, args.child_sft_run_dir)
    checkpoint = _continuation_checkpoint_id(parent, child)
    config = _resolved_config(args.config, args.dataset_dir, checkpoint)
    run_dir = args.output_root / "generation" / RUN_NAME

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "C36_PREFLIGHT_OK",
                    "parent_run_id": parent.run_id,
                    "child_run_id": child.run_id,
                    "checkpoint": checkpoint,
                    "dataset_dir": str(config.dataset_dir),
                    "batch_size": BATCH_SIZE,
                    "seed": SEED,
                },
                sort_keys=True,
            )
        )
        return 0

    if args.postcheck_only:
        print(json.dumps(_postcheck(run_dir, checkpoint, args.project_commit), sort_keys=True))
        return 0

    if (run_dir / "run.json").is_file():
        try:
            result = _postcheck(run_dir, checkpoint, args.project_commit)
        except (OSError, ValueError, SystemExit):
            pass
        else:
            result["reused"] = True
            print(json.dumps(result, sort_keys=True))
            return 0

    generator = _build_generator(config, parent, child)
    summary = run_generation_bundle(
        config=config,
        model_id=EXPECTED_MODEL_ID,
        generator=generator,
        run_id=RUN_NAME,
        output_root=args.output_root,
        seed=SEED,
        batch_size=BATCH_SIZE,
        utilization_sampler=RuntimeUtilizationSampler(),
    )
    result = _postcheck(summary.run_dir, checkpoint, args.project_commit)
    result["completed_before_run"] = summary.completed_before_run
    result["generated_this_run"] = summary.generated_this_run
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
