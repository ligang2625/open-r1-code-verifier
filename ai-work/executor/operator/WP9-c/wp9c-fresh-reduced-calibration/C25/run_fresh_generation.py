#!/usr/bin/env python3
"""Run fresh k=8 reduced-pool calibration generation on the operator GPU."""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import torch

from code_verifier.config import load_yaml_mapping
from code_verifier.data.json_strict import loads_strict
from code_verifier.evaluation.generate import SamplingGenerationConfig, TransformersSamplingCompletionGenerator
from code_verifier.training.calibration import (
    _load_input_bundle,
    _sft_identity,
    load_completed_calibration_generation,
    run_calibration_generation,
)
from code_verifier.training.sft import load_completed_sft_checkpoint

ROOT = Path(__file__).resolve().parents[6]
CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/checkpoint.json"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, object]:
    value = loads_strict(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _string(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _verify_file(path: Path, expected: object, *, label: str) -> None:
    if not isinstance(expected, str) or _sha(path) != expected:
        raise ValueError(f"{label} digest mismatch: {path}")


def _validate_config(path: Path) -> Mapping[str, object]:
    root = load_yaml_mapping(path)
    if set(root) != {"version", "protocol_amendment", "input", "sampling"}:
        raise ValueError("C25 config shape drift")
    if root.get("version") != "wp9c-reduced-fresh-calibration-generation-v1":
        raise ValueError("C25 config version drift")
    if root.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("C25 protocol drift")
    input_cfg = _mapping(root.get("input"), context="C25 input config")
    sampling = _mapping(root.get("sampling"), context="C25 sampling config")
    if dict(input_cfg) != {
        "problem_count": 1602,
        "external_new_count": 1602,
        "sft_reuse_count": 0,
        "seed": 42,
    }:
        raise ValueError("C25 input count contract drift")
    if dict(sampling) != {
        "initial_generations": 8,
        "retry_generations": 8,
        "temperature": 0.8,
        "top_p": 0.95,
        "max_new_tokens": 512,
        "max_prompt_tokens": 2048,
    }:
        raise ValueError("C25 sampling contract drift")
    return sampling


def _validate_gpu() -> dict[str, object]:
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("C25 requires exactly one CUDA device after CUDA_VISIBLE_DEVICES selection")
    name = torch.cuda.get_device_name(0)
    properties = torch.cuda.get_device_properties(0)
    total_mib = properties.total_memory // (1024 * 1024)
    if "RTX 4090" not in name or total_mib < 22528:
        raise ValueError(f"C25 requires an RTX 4090 with at least 22528 MiB, got {name} {total_mib} MiB")
    if not torch.cuda.is_bf16_supported():
        raise ValueError("C25 requires CUDA bf16 support")
    return {"name": name, "total_memory_mib": total_mib, "bf16_supported": True}


def run(output_dir: Path, input_dir: Path, sft_dir: Path, problem_batch_size: int) -> None:
    checkpoint = _json(CHECKPOINT)
    if checkpoint.get("status") != "awaiting_operator":
        raise ValueError("C25 checkpoint is not awaiting_operator")
    bindings = _mapping(checkpoint.get("bindings"), context="C25 bindings")
    paths = _mapping(checkpoint.get("paths"), context="C25 paths")

    config_path = ROOT / _string(paths, "config")
    _verify_file(config_path, bindings.get("config_sha256"), label="C25 config")
    _verify_file(
        input_dir / "input_manifest.json",
        bindings.get("input_manifest_sha256"),
        label="C25 input manifest",
    )
    _verify_file(input_dir / "inputs.jsonl", bindings.get("inputs_sha256"), label="C25 input records")
    _verify_file(
        ROOT / _string(paths, "preparation_script"),
        bindings.get("preparation_script_sha256"),
        label="C25 preparation script",
    )
    _verify_file(ROOT / _string(paths, "runner"), bindings.get("runner_sha256"), label="C25 runner")

    sampling = _validate_config(config_path)
    if problem_batch_size != 4:
        raise ValueError("C25 problem_batch_size must remain frozen at 4")
    manifest, input_rows = _load_input_bundle(input_dir)
    if len(input_rows) != 1602 or manifest.get("seed") != 42:
        raise ValueError("C25 input bundle count/seed drift")
    if any(row.overlap_origin != "external_new" or row.quality_gate_required for row in input_rows):
        raise ValueError("C25 input bundle is not external-new-only and quality-safe")

    sft = load_completed_sft_checkpoint(sft_dir)
    expected_sft = _mapping(checkpoint.get("sft_identity"), context="C25 SFT identity")
    actual_sft = _sft_identity(sft)
    if actual_sft != dict(expected_sft):
        raise ValueError("C25 frozen B identity drift")

    if output_dir.exists() and (output_dir / "run.json").is_file():
        run_manifest = _json(output_dir / "run.json")
        if run_manifest.get("status") == "completed":
            completed_manifest, completed_rows = load_completed_calibration_generation(output_dir)
            if completed_manifest.get("input_manifest_sha256") != bindings.get("input_manifest_sha256"):
                raise ValueError("completed C25 output input binding drift")
            if completed_manifest.get("input_records_sha256") != bindings.get("inputs_sha256"):
                raise ValueError("completed C25 output input-record binding drift")
            if completed_manifest.get("sft_checkpoint") != dict(expected_sft):
                raise ValueError("completed C25 output frozen-B identity drift")
            if completed_manifest.get("problem_batch_size") != 4:
                raise ValueError("completed C25 output batch-size drift")
            if len(completed_rows) != 1602 * 8:
                raise ValueError("completed C25 output record count drift")
            print("C25 generation already completed and strictly verified; no model load required")
            return

    gpu = _validate_gpu()
    print(
        f"C25 preflight input=1602 gpu={gpu['name']} memory_mib={gpu['total_memory_mib']} batch={problem_batch_size}"
    )

    generator = TransformersSamplingCompletionGenerator.from_peft_checkpoint(
        base_model_id=sft.model_id,
        base_model_revision=sft.model_revision,
        adapter_dir=sft.checkpoint_dir,
        device="cuda",
        local_files_only=True,
        config=SamplingGenerationConfig(
            temperature=cast(float, sampling["temperature"]),
            top_p=cast(float, sampling["top_p"]),
            max_new_tokens=cast(int, sampling["max_new_tokens"]),
        ),
    )
    summary = run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=sft_dir,
        generator=generator,
        output_dir=output_dir,
        block_index=0,
        retry_manifest=None,
        problem_batch_size=problem_batch_size,
    )
    print(
        "C25 generation complete "
        f"problems={summary.problem_count} records={summary.record_count} records_sha256={summary.records_sha256}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-bundle", type=Path, required=True)
    parser.add_argument("--sft-run", type=Path, required=True)
    parser.add_argument("--problem-batch-size", type=int, default=4, choices=range(1, 9))
    args = parser.parse_args()
    run(args.output.resolve(), args.input_bundle.resolve(), args.sft_run.resolve(), args.problem_batch_size)


if __name__ == "__main__":
    main()
