#!/usr/bin/env python3
"""Run checkpoint-bound fresh Public/Hidden scoring for the accepted C25 block."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config
from code_verifier.execution.piston_resilience import load_piston_transport_policy
from code_verifier.training.reduced_calibration import (
    check_reduced_pool_calibration_scoring,
    score_reduced_pool_calibration_generation,
)

ROOT = Path(__file__).resolve().parents[6]
CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration-scoring/C26/checkpoint.json"

EXPECTED = {
    "c24_checkpoint_sha256": "48ac639cc3fba0c540437bfbba0b65403575f424c06eefd6b8c51d00771313f1",
    "c25_checkpoint_sha256": "0ba51b0b502357482d6eba137d900b6686a19bab3470255992502a9ebb750916",
    "c24_formal_problems_sha256": "d94c5216ef28272fb1e0ee0ec50667c423711d8587227a4feee84687c7509a6f",
    "c25_input_manifest_sha256": "bdccb68febe85f1da381ba01671fb220246dac9e74cdfacb89e4d1da7e334aff",
    "c25_inputs_sha256": "dbb6f18a472e390acbec641daab65db6d3f2cb07d3469f8e46ef2d90bf867d18",
    "c25_generation_run_sha256": "e2ead0f322864be3f262ee3384b6ebbd48af2941f427ad444852373626e42d05",
    "c25_generation_records_sha256": "8802287fc1c4076397093f25ca7180edf222c31a90b7d2395a3e4aedde62365a",
    "c25_generation_progress_sha256": "01f3ea0705adc072d5ed2fe082c16aa9f6adf38a4547ba28c9fd371d167d5fdf",
    "c25_operator_evidence_sha256": "c15acec284333c03da02d4632a8ae56f4b91f986e46f2f86fa8c0c1b7c6c8bec",
    "c25_postcheck_sha256": "8c3586aec8d9f9356f4ff2e39ee2c5427b975e9dd834d6b15807e253f5d19eda",
    "problem_order_sha256": "2b7d6a79ee11a4f21898d27e4cc352f0e5fe1f86104a55e7b4c8ebaac602443e",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "piston_transport_policy_sha256": "16ae94c26c0c8dfdc47998f2f9b52af2ff9b40022221f41a963836cd992fc62c",
    "handoff_commit": "322db1e1649d8c87b51352f57c0884b0b9a24bfc",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _require_sha(path: Path, expected: str, *, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} SHA256 mismatch: {actual} != {expected}")


def _preflight(args: argparse.Namespace) -> dict[str, object]:
    checkpoint = _load_json(CHECKPOINT)
    if checkpoint.get("status") != "awaiting_control_plane_scoring":
        raise ValueError("C26 checkpoint status drift")
    if checkpoint.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("C26 protocol drift")
    bindings = checkpoint.get("bindings")
    if not isinstance(bindings, dict) or bindings != EXPECTED:
        raise ValueError("C26 checkpoint binding drift")
    implementation = checkpoint.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("C26 implementation binding drift")
    implementation_files = {
        "scorer": "scorer_sha256",
        "scoring_checkpoint_module": "scoring_checkpoint_module_sha256",
        "runner": "runner_sha256",
        "shell_runner": "shell_runner_sha256",
    }
    for path_key, sha_key in implementation_files.items():
        relative_path = implementation.get(path_key)
        expected_sha = implementation.get(sha_key)
        if not isinstance(relative_path, str) or not isinstance(expected_sha, str):
            raise ValueError("C26 implementation binding fields are invalid")
        _require_sha(ROOT / relative_path, expected_sha, label=f"C26 implementation {path_key}")

    c24_checkpoint = Path(args.c24_checkpoint)
    c25_checkpoint = Path(args.c25_checkpoint)
    formal_problems = Path(args.formal_problems)
    input_dir = Path(args.input_bundle_dir)
    generation_dir = Path(args.generation_run_dir)
    evidence_dir = Path(args.operator_evidence_dir)
    piston_config = Path(args.piston_config)
    piston_transport_policy = Path(args.piston_transport_policy)

    _require_sha(c24_checkpoint, EXPECTED["c24_checkpoint_sha256"], label="C24 checkpoint")
    _require_sha(c25_checkpoint, EXPECTED["c25_checkpoint_sha256"], label="C25 checkpoint")
    _require_sha(formal_problems, EXPECTED["c24_formal_problems_sha256"], label="C24 formal problems")
    _require_sha(input_dir / "input_manifest.json", EXPECTED["c25_input_manifest_sha256"], label="C25 input manifest")
    _require_sha(input_dir / "inputs.jsonl", EXPECTED["c25_inputs_sha256"], label="C25 input records")
    _require_sha(generation_dir / "run.json", EXPECTED["c25_generation_run_sha256"], label="C25 generation run")
    _require_sha(
        generation_dir / "samples" / "generations.jsonl",
        EXPECTED["c25_generation_records_sha256"],
        label="C25 generation records",
    )
    _require_sha(
        generation_dir / "samples" / "progress.json",
        EXPECTED["c25_generation_progress_sha256"],
        label="C25 generation progress",
    )
    _require_sha(
        evidence_dir / "operator-evidence.json",
        EXPECTED["c25_operator_evidence_sha256"],
        label="C25 operator evidence",
    )
    _require_sha(
        evidence_dir / "postcheck-summary.json",
        EXPECTED["c25_postcheck_sha256"],
        label="C25 postcheck",
    )
    _require_sha(piston_config, EXPECTED["piston_config_sha256"], label="canonical Piston config")
    _require_sha(
        piston_transport_policy,
        EXPECTED["piston_transport_policy_sha256"],
        label="canonical Piston transport policy",
    )

    status = (evidence_dir / "status").read_text(encoding="utf-8")
    if status != "0\n":
        raise ValueError("C25 operator status is not exact zero")
    evidence = _load_json(evidence_dir / "operator-evidence.json")
    postcheck = _load_json(evidence_dir / "postcheck-summary.json")
    if (
        evidence.get("operator_checkpoint_commit") != EXPECTED["handoff_commit"]
        or evidence.get("gate_status") != "passed"
        or evidence.get("command_rc") != 0
        or evidence.get("postcheck_rc") != 0
        or evidence.get("postcheck") != postcheck
    ):
        raise ValueError("C25 operator evidence strict readback failed")
    generation = _load_json(generation_dir / "run.json")
    progress = _load_json(generation_dir / "samples" / "progress.json")
    records_path = generation_dir / "samples" / "generations.jsonl"
    if (
        generation.get("status") != "completed"
        or generation.get("block_index") != 0
        or generation.get("record_count") != 12816
        or generation.get("records_sha256") != EXPECTED["c25_generation_records_sha256"]
        or generation.get("problem_order_sha256") != EXPECTED["problem_order_sha256"]
        or generation.get("samples_per_problem") != 8
        or generation.get("problem_batch_size") != 4
        or progress.get("record_count") != 12816
        or progress.get("byte_count") != records_path.stat().st_size
    ):
        raise ValueError("C25 generation strict receive readback failed")
    if (
        postcheck.get("status") != "passed"
        or postcheck.get("generation_records_sha256") != EXPECTED["c25_generation_records_sha256"]
    ):
        raise ValueError("C25 postcheck receive readback failed")

    return {
        "generation_records_sha256": EXPECTED["c25_generation_records_sha256"],
        "generation_run_sha256": EXPECTED["c25_generation_run_sha256"],
        "problem_order_sha256": EXPECTED["problem_order_sha256"],
        "piston_config_sha256": EXPECTED["piston_config_sha256"],
        "piston_transport_policy_sha256": EXPECTED["piston_transport_policy_sha256"],
        "operator_evidence_sha256": EXPECTED["c25_operator_evidence_sha256"],
        "postcheck_sha256": EXPECTED["c25_postcheck_sha256"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--c24-checkpoint",
        default=str(ROOT / "ai-work/executor/operator/WP9-c/wp9c-final-reduced-pool/C24/checkpoint.json"),
    )
    parser.add_argument(
        "--c25-checkpoint",
        default=str(ROOT / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/checkpoint.json"),
    )
    parser.add_argument(
        "--formal-problems", default="/home/dzy/wp9c-final-reduced-pool-C24/external_formal_problems.jsonl"
    )
    parser.add_argument("--input-bundle-dir", default="/home/dzy/wp9c-fresh-calibration-input-C25")
    parser.add_argument("--generation-run-dir", default="/home/dzy/wp9c-fresh-calibration-generation-C25")
    parser.add_argument(
        "--operator-evidence-dir",
        default="/home/dzy/wp9c-operator-evidence/WP9-c/wp9c-fresh-reduced-calibration-generation/C25",
    )
    parser.add_argument("--piston-config", default=str(ROOT / "configs/execution/piston-local.yaml"))
    parser.add_argument(
        "--piston-transport-policy",
        default=str(ROOT / "configs/execution/piston-transport-resilience.yaml"),
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--output-dir", default="/home/dzy/wp9c-fresh-reduced-calibration-score-C26")
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    preflight = _preflight(args)
    print(json.dumps({"status": "C26_PREFLIGHT_OK", **preflight}, sort_keys=True))
    if args.preflight_only:
        return 0

    piston_path = Path(args.piston_config)
    piston_transport_policy_path = Path(args.piston_transport_policy)
    piston_config = load_piston_executor_config(piston_path)
    piston_transport_policy = load_piston_transport_policy(piston_transport_policy_path)
    output = score_reduced_pool_calibration_generation(
        c24_checkpoint_path=Path(args.c24_checkpoint),
        c25_checkpoint_path=Path(args.c25_checkpoint),
        formal_problems_path=Path(args.formal_problems),
        input_bundle_dir=Path(args.input_bundle_dir),
        generation_run_dir=Path(args.generation_run_dir),
        piston_config_path=piston_path,
        output_dir=Path(args.output_dir),
        executor_factory=lambda: PistonExecutor(
            piston_config,
            transport_policy=piston_transport_policy,
        ),
        workers=args.workers,
    )
    manifest = check_reduced_pool_calibration_scoring(output)
    if (
        manifest.get("problem_count") != 1602
        or manifest.get("block_index") != 0
        or manifest.get("generation_records_sha256") != EXPECTED["c25_generation_records_sha256"]
        or manifest.get("problem_order_sha256") != EXPECTED["problem_order_sha256"]
        or manifest.get("piston_config_sha256") != EXPECTED["piston_config_sha256"]
    ):
        raise ValueError("C26 completed scoring strict postcheck failed")
    print(
        json.dumps(
            {
                "status": "C26_SCORING_COMPLETED",
                "output_dir": str(output),
                "problem_count": manifest["problem_count"],
                "records_sha256": manifest["records_sha256"],
                "retry_problem_count": manifest["retry_problem_count"],
                "retry_problem_ids_sha256": manifest["retry_problem_ids_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
