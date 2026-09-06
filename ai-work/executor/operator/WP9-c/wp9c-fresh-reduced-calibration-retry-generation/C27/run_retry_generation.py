#!/usr/bin/env python3
"""Run the accepted C27 block-1 retry generation on the RTX 4090."""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import torch

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import stable_json_hash
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
CHECKPOINT = (
    ROOT
    / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration-retry-generation/C27/checkpoint.json"
)


def _sha256(path: Path) -> str:
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


def _jsonl_ids(path: Path) -> list[str]:
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        value = loads_strict(line)
        if not isinstance(value, dict) or set(value) != {"problem_id"}:
            raise ValueError("C27 retry manifest row schema drift")
        problem_id = value.get("problem_id")
        if not isinstance(problem_id, str) or not problem_id:
            raise ValueError("C27 retry manifest problem_id drift")
        ids.append(problem_id)
    return ids


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
    if not isinstance(expected, str) or _sha256(path) != expected:
        raise ValueError(f"{label} digest mismatch: {path}")


def _validate_config(path: Path) -> Mapping[str, object]:
    root = load_yaml_mapping(path)
    if set(root) != {"version", "protocol_amendment", "input", "sampling"}:
        raise ValueError("C27 config shape drift")
    if root.get("version") != "wp9c-reduced-fresh-calibration-generation-v1":
        raise ValueError("C27 config version drift")
    if root.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("C27 protocol drift")
    sampling = _mapping(root.get("sampling"), context="C27 sampling config")
    if dict(sampling) != {
        "initial_generations": 8,
        "retry_generations": 8,
        "temperature": 0.8,
        "top_p": 0.95,
        "max_new_tokens": 512,
        "max_prompt_tokens": 2048,
    }:
        raise ValueError("C27 sampling contract drift")
    return sampling


def _validate_gpu() -> dict[str, object]:
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("C27 requires exactly one CUDA device after CUDA_VISIBLE_DEVICES selection")
    name = torch.cuda.get_device_name(0)
    properties = torch.cuda.get_device_properties(0)
    total_mib = properties.total_memory // (1024 * 1024)
    if "RTX 4090" not in name or total_mib < 22528:
        raise ValueError(f"C27 requires an RTX 4090 with at least 22528 MiB, got {name} {total_mib} MiB")
    if not torch.cuda.is_bf16_supported():
        raise ValueError("C27 requires CUDA bf16 support")
    return {"name": name, "total_memory_mib": total_mib, "bf16_supported": True}


def run(
    output_dir: Path,
    input_dir: Path,
    retry_bundle_dir: Path,
    sft_dir: Path,
    problem_batch_size: int,
) -> None:
    checkpoint = _json(CHECKPOINT)
    if checkpoint.get("status") != "awaiting_operator":
        raise ValueError("C27 checkpoint is not awaiting_operator")
    bindings = _mapping(checkpoint.get("bindings"), context="C27 bindings")
    paths = _mapping(checkpoint.get("paths"), context="C27 paths")

    config_path = ROOT / _string(paths, "config")
    retry_manifest = retry_bundle_dir / "retry_problem_ids.jsonl"
    retry_input_manifest = retry_bundle_dir / "retry-input-manifest.json"
    _verify_file(config_path, bindings.get("config_sha256"), label="C27 config")
    _verify_file(
        input_dir / "input_manifest.json",
        bindings.get("c25_input_manifest_sha256"),
        label="C25 input manifest",
    )
    _verify_file(input_dir / "inputs.jsonl", bindings.get("c25_input_records_sha256"), label="C25 input records")
    _verify_file(retry_manifest, bindings.get("retry_problem_ids_sha256"), label="C27 retry problem IDs")
    _verify_file(retry_input_manifest, bindings.get("retry_input_manifest_sha256"), label="C27 retry input manifest")
    _verify_file(ROOT / _string(paths, "runner"), bindings.get("runner_sha256"), label="C27 runner")

    sampling = _validate_config(config_path)
    if problem_batch_size != 4:
        raise ValueError("C27 problem_batch_size must remain frozen at 4")

    input_manifest, input_rows = _load_input_bundle(input_dir)
    if len(input_rows) != 1602 or input_manifest.get("seed") != 42:
        raise ValueError("C27 C25-input count/seed drift")
    by_id = {row.problem_id: row for row in input_rows}
    retry_ids = _jsonl_ids(retry_manifest)
    if (
        len(retry_ids) != 195
        or retry_ids != sorted(retry_ids)
        or len(set(retry_ids)) != 195
        or any(problem_id not in by_id for problem_id in retry_ids)
    ):
        raise ValueError("C27 retry ID population drift")
    if stable_json_hash(retry_ids) != bindings.get("retry_problem_order_sha256"):
        raise ValueError("C27 retry problem order drift")

    frozen_retry = _json(retry_input_manifest)
    expected_retry_fields = {
        "version": 1,
        "stage_id": "WP9-c",
        "checkpoint_id": "C27",
        "protocol": "wp9c-reduced-quota-current-viable-v1",
        "block_index": 1,
        "sample_index_start": 8,
        "sample_index_end": 15,
        "samples_per_problem": 8,
        "retry_problem_count": 195,
        "expected_record_count": 1560,
        "retry_problem_ids_sha256": bindings.get("retry_problem_ids_sha256"),
        "retry_problem_order_sha256": bindings.get("retry_problem_order_sha256"),
        "c26_score_manifest_sha256": bindings.get("c26_score_manifest_sha256"),
        "c26_score_records_sha256": bindings.get("c26_score_records_sha256"),
        "c25_input_manifest_sha256": bindings.get("c25_input_manifest_sha256"),
        "c25_input_records_sha256": bindings.get("c25_input_records_sha256"),
    }
    for key, expected in expected_retry_fields.items():
        if frozen_retry.get(key) != expected:
            raise ValueError(f"C27 retry input manifest drift: {key}")

    sft = load_completed_sft_checkpoint(sft_dir)
    expected_sft = _mapping(checkpoint.get("sft_identity"), context="C27 SFT identity")
    actual_sft = _sft_identity(sft)
    if actual_sft != dict(expected_sft):
        raise ValueError("C27 frozen B identity drift")

    if output_dir.exists() and (output_dir / "run.json").is_file():
        run_manifest = _json(output_dir / "run.json")
        if run_manifest.get("status") == "completed":
            completed_manifest, completed_rows = load_completed_calibration_generation(output_dir)
            if completed_manifest.get("block_index") != 1:
                raise ValueError("completed C27 output block drift")
            if completed_manifest.get("input_manifest_sha256") != bindings.get("c25_input_manifest_sha256"):
                raise ValueError("completed C27 output input binding drift")
            if completed_manifest.get("input_records_sha256") != bindings.get("c25_input_records_sha256"):
                raise ValueError("completed C27 output input-record binding drift")
            if completed_manifest.get("retry_manifest_sha256") != bindings.get("retry_problem_ids_sha256"):
                raise ValueError("completed C27 output retry-manifest binding drift")
            if completed_manifest.get("problem_order_sha256") != bindings.get("retry_problem_order_sha256"):
                raise ValueError("completed C27 output retry-order binding drift")
            if completed_manifest.get("sft_checkpoint") != dict(expected_sft):
                raise ValueError("completed C27 output frozen-B identity drift")
            if completed_manifest.get("problem_batch_size") != 4:
                raise ValueError("completed C27 output batch-size drift")
            if len(completed_rows) != 1560:
                raise ValueError("completed C27 output record count drift")
            print("C27 retry generation already completed and strictly verified; no model load required")
            return

    gpu = _validate_gpu()
    print(f"C27 preflight retry=195 gpu={gpu['name']} memory_mib={gpu['total_memory_mib']} batch={problem_batch_size}")

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
        block_index=1,
        retry_manifest=retry_manifest,
        problem_batch_size=problem_batch_size,
    )
    print(
        "C27 retry generation complete "
        f"problems={summary.problem_count} records={summary.record_count} records_sha256={summary.records_sha256}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-bundle", type=Path, required=True)
    parser.add_argument("--retry-bundle", type=Path, required=True)
    parser.add_argument("--sft-run", type=Path, required=True)
    parser.add_argument("--problem-batch-size", type=int, default=4, choices=range(1, 9))
    args = parser.parse_args()
    run(
        args.output.resolve(),
        args.input_bundle.resolve(),
        args.retry_bundle.resolve(),
        args.sft_run.resolve(),
        args.problem_batch_size,
    )


if __name__ == "__main__":
    main()
