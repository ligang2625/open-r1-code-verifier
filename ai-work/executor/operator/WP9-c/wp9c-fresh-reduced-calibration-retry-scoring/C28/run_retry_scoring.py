#!/usr/bin/env python3
"""Fresh Public/Hidden scoring for the accepted C27 block-1 retry generation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config
from code_verifier.execution.piston_resilience import load_piston_transport_policy
from code_verifier.training.calibration import calibration_problem_seed, load_completed_calibration_generation
from code_verifier.training.reduced_calibration import (
    check_reduced_pool_calibration_scoring,
    score_reduced_pool_calibration_generation,
)

ROOT = Path(__file__).resolve().parents[6]
CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration-retry-scoring/C28/checkpoint.json"

EXPECTED = {
    "c24_checkpoint_sha256": "48ac639cc3fba0c540437bfbba0b65403575f424c06eefd6b8c51d00771313f1",
    "c25_checkpoint_sha256": "0ba51b0b502357482d6eba137d900b6686a19bab3470255992502a9ebb750916",
    "c24_formal_problems_sha256": "d94c5216ef28272fb1e0ee0ec50667c423711d8587227a4feee84687c7509a6f",
    "c25_input_manifest_sha256": "bdccb68febe85f1da381ba01671fb220246dac9e74cdfacb89e4d1da7e334aff",
    "c25_inputs_sha256": "dbb6f18a472e390acbec641daab65db6d3f2cb07d3469f8e46ef2d90bf867d18",
    "c26_score_manifest_sha256": "b7333162acb0e24d7285d8ca9145b220c10636541db09f5fac531de670edd226",
    "c26_score_records_sha256": "b9c7ada9d21a2f3140eeb074248a4b306d49d14b8dcdc90b39e9e3692ffff08e",
    "c26_retry_problem_ids_sha256": "f0c03e55771bc86dd3f9966214ade7d34a9734cff133bdbdd1e6d1d8071c2eb5",
    "retry_problem_order_sha256": "1309b9f7cbbb4e488499a21026a87c3148284becd07a57672131e6f244dea0d3",
    "c27_checkpoint_sha256": "1968fd16214782a290f69e8af66fa79abcf2dc257707323e8376771f39457f61",
    "c27_retry_input_manifest_sha256": "e9d896de8ad51e54fcbaaf0d04edf691a742e6168ed63908795305d5df22ab33",
    "c27_generation_run_sha256": "824e92881d63d9d44f2c230f169d649077d21c957f7e02bcf1fdfa61362434d6",
    "c27_generation_records_sha256": "4f3a83f49821cb20952228f976577eab64664e076dc0c94483757e9c144e697d",
    "c27_generation_progress_sha256": "2fecfa4c03f8fa01d27a9cb6c5bddb20027d32042f64542ba7842fe4129352a6",
    "c27_operator_evidence_sha256": "d5d69073c56805777c7af389a3b2f34e23596364b71a9598227249e20dcca2b1",
    "c27_postcheck_sha256": "44724ddd671efcad3c885ec63037ca7961a719fe0151739e204129ebce5bc1b4",
    "c27_status_sha256": "9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa",
    "c27_terminal_log_sha256": "ab38e7970d7ece234522196e97f2f858d6dca4ebb2d6fd66fb3a5620e6a980ab",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "piston_transport_policy_sha256": "16ae94c26c0c8dfdc47998f2f9b52af2ff9b40022221f41a963836cd992fc62c",
    "handoff_commit": "4343f864aa0984b5cfe7e98bafa247461980d3e3",
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


def _load_retry_ids(path: Path) -> list[str]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if any(not isinstance(row, dict) or set(row) != {"problem_id"} for row in rows):
        raise ValueError("retry manifest schema drift")
    ids = [row["problem_id"] for row in rows]
    if any(not isinstance(problem_id, str) or not problem_id for problem_id in ids):
        raise ValueError("retry manifest problem_id drift")
    return cast(list[str], ids)


def _require_sha(path: Path, expected: str, *, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} SHA256 mismatch: {actual} != {expected}")


def _preflight(args: argparse.Namespace) -> dict[str, object]:
    checkpoint = _load_json(CHECKPOINT)
    if checkpoint.get("status") != "awaiting_control_plane_retry_scoring":
        raise ValueError("C28 checkpoint status drift")
    if checkpoint.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1":
        raise ValueError("C28 protocol drift")
    if checkpoint.get("bindings") != EXPECTED:
        raise ValueError("C28 checkpoint binding drift")

    implementation = checkpoint.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("C28 implementation binding drift")
    for path_key, sha_key in (
        ("scorer", "scorer_sha256"),
        ("scoring_checkpoint_module", "scoring_checkpoint_module_sha256"),
        ("runner", "runner_sha256"),
        ("shell_runner", "shell_runner_sha256"),
    ):
        relative = implementation.get(path_key)
        expected_sha = implementation.get(sha_key)
        if not isinstance(relative, str) or not isinstance(expected_sha, str):
            raise ValueError("C28 implementation binding fields are invalid")
        _require_sha(ROOT / relative, expected_sha, label=f"C28 implementation {path_key}")

    c24_checkpoint = Path(args.c24_checkpoint)
    c25_checkpoint = Path(args.c25_checkpoint)
    c27_checkpoint = Path(args.c27_checkpoint)
    formal_problems = Path(args.formal_problems)
    input_dir = Path(args.input_bundle_dir)
    initial_score_dir = Path(args.initial_score_dir)
    retry_bundle = Path(args.retry_bundle_dir)
    generation_dir = Path(args.generation_run_dir)
    evidence_dir = Path(args.operator_evidence_dir)
    piston_config = Path(args.piston_config)
    piston_transport_policy = Path(args.piston_transport_policy)

    _require_sha(c24_checkpoint, EXPECTED["c24_checkpoint_sha256"], label="C24 checkpoint")
    _require_sha(c25_checkpoint, EXPECTED["c25_checkpoint_sha256"], label="C25 checkpoint")
    _require_sha(c27_checkpoint, EXPECTED["c27_checkpoint_sha256"], label="C27 checkpoint")
    _require_sha(formal_problems, EXPECTED["c24_formal_problems_sha256"], label="C24 formal problems")
    _require_sha(input_dir / "input_manifest.json", EXPECTED["c25_input_manifest_sha256"], label="C25 input manifest")
    _require_sha(input_dir / "inputs.jsonl", EXPECTED["c25_inputs_sha256"], label="C25 input records")
    _require_sha(
        initial_score_dir / "score_manifest.json", EXPECTED["c26_score_manifest_sha256"], label="C26 score manifest"
    )
    _require_sha(
        initial_score_dir / "records/scoring.jsonl", EXPECTED["c26_score_records_sha256"], label="C26 score records"
    )
    c26_retry = initial_score_dir / "manifest/retry_problem_ids.jsonl"
    _require_sha(c26_retry, EXPECTED["c26_retry_problem_ids_sha256"], label="C26 retry manifest")
    _require_sha(
        retry_bundle / "retry_problem_ids.jsonl", EXPECTED["c26_retry_problem_ids_sha256"], label="C27 retry IDs"
    )
    _require_sha(
        retry_bundle / "retry-input-manifest.json",
        EXPECTED["c27_retry_input_manifest_sha256"],
        label="C27 retry input manifest",
    )
    _require_sha(generation_dir / "run.json", EXPECTED["c27_generation_run_sha256"], label="C27 generation run")
    _require_sha(
        generation_dir / "samples/generations.jsonl",
        EXPECTED["c27_generation_records_sha256"],
        label="C27 generation records",
    )
    _require_sha(
        generation_dir / "samples/progress.json",
        EXPECTED["c27_generation_progress_sha256"],
        label="C27 generation progress",
    )
    _require_sha(
        evidence_dir / "operator-evidence.json",
        EXPECTED["c27_operator_evidence_sha256"],
        label="C27 operator evidence",
    )
    _require_sha(evidence_dir / "postcheck-summary.json", EXPECTED["c27_postcheck_sha256"], label="C27 postcheck")
    _require_sha(evidence_dir / "status", EXPECTED["c27_status_sha256"], label="C27 status")
    _require_sha(evidence_dir / "terminal.log", EXPECTED["c27_terminal_log_sha256"], label="C27 terminal log")
    _require_sha(piston_config, EXPECTED["piston_config_sha256"], label="canonical Piston config")
    _require_sha(
        piston_transport_policy, EXPECTED["piston_transport_policy_sha256"], label="canonical Piston transport policy"
    )

    initial_manifest = _load_json(initial_score_dir / "score_manifest.json")
    if (
        initial_manifest.get("status") != "completed"
        or initial_manifest.get("block_index") != 0
        or initial_manifest.get("problem_count") != 1602
        or initial_manifest.get("retry_problem_count") != 195
        or initial_manifest.get("retry_problem_ids_sha256") != EXPECTED["c26_retry_problem_ids_sha256"]
    ):
        raise ValueError("C26 accepted initial scoring contract drift")

    retry_ids = _load_retry_ids(c26_retry)
    copied_retry_ids = _load_retry_ids(retry_bundle / "retry_problem_ids.jsonl")
    if retry_ids != copied_retry_ids:
        raise ValueError("C27 retry manifest is not byte/semantic identical to C26")
    if len(retry_ids) != 195 or retry_ids != sorted(retry_ids) or len(set(retry_ids)) != 195:
        raise ValueError("C28 retry ID count/order/uniqueness drift")
    if stable_json_hash(retry_ids) != EXPECTED["retry_problem_order_sha256"]:
        raise ValueError("C28 retry problem order drift")

    run, generations = load_completed_calibration_generation(generation_dir)
    if (
        run.get("block_index") != 1
        or run.get("record_count") != 1560
        or run.get("records_sha256") != EXPECTED["c27_generation_records_sha256"]
        or run.get("problem_order_sha256") != EXPECTED["retry_problem_order_sha256"]
        or run.get("retry_manifest_sha256") != EXPECTED["c26_retry_problem_ids_sha256"]
        or run.get("input_manifest_sha256") != EXPECTED["c25_input_manifest_sha256"]
        or run.get("input_records_sha256") != EXPECTED["c25_inputs_sha256"]
    ):
        raise ValueError("C27 completed generation binding drift")
    expected = [
        (problem_id, sample_index, calibration_problem_seed(42, problem_id, 1))
        for problem_id in retry_ids
        for sample_index in range(8, 16)
    ]
    actual = [(row.get("problem_id"), row.get("sample_index"), row.get("sample_seed")) for row in generations]
    if actual != expected:
        raise ValueError("C27 generation is not the exact accepted block-1 retry sequence")

    evidence = _load_json(evidence_dir / "operator-evidence.json")
    postcheck = _load_json(evidence_dir / "postcheck-summary.json")
    if (
        (evidence_dir / "status").read_text(encoding="utf-8") != "0\n"
        or evidence.get("operator_checkpoint_commit") != EXPECTED["handoff_commit"]
        or evidence.get("gate_status") != "passed"
        or evidence.get("command_rc") != 0
        or evidence.get("postcheck_rc") != 0
        or evidence.get("postcheck") != postcheck
        or postcheck.get("status") != "passed"
        or postcheck.get("problem_count") != 195
        or postcheck.get("record_count") != 1560
        or postcheck.get("generation_records_sha256") != EXPECTED["c27_generation_records_sha256"]
    ):
        raise ValueError("C27 operator evidence strict readback failed")

    return {
        "generation_records_sha256": EXPECTED["c27_generation_records_sha256"],
        "generation_run_sha256": EXPECTED["c27_generation_run_sha256"],
        "retry_problem_count": 195,
        "retry_problem_ids_sha256": EXPECTED["c26_retry_problem_ids_sha256"],
        "retry_problem_order_sha256": EXPECTED["retry_problem_order_sha256"],
        "piston_config_sha256": EXPECTED["piston_config_sha256"],
        "piston_transport_policy_sha256": EXPECTED["piston_transport_policy_sha256"],
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
        "--c27-checkpoint",
        default=str(
            ROOT
            / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration-retry-generation/C27/checkpoint.json"
        ),
    )
    parser.add_argument(
        "--formal-problems", default="/home/dzy/wp9c-final-reduced-pool-C24/external_formal_problems.jsonl"
    )
    parser.add_argument("--input-bundle-dir", default="/home/dzy/wp9c-fresh-calibration-input-C25")
    parser.add_argument("--initial-score-dir", default="/home/dzy/wp9c-fresh-reduced-calibration-score-C26")
    parser.add_argument("--retry-bundle-dir", default="/home/dzy/wp9c-fresh-calibration-retry-input-C27")
    parser.add_argument("--generation-run-dir", default="/home/dzy/wp9c-fresh-calibration-retry-generation-C27")
    parser.add_argument(
        "--operator-evidence-dir",
        default="/home/dzy/wp9c-operator-evidence/WP9-c/wp9c-fresh-reduced-calibration-retry-generation/C27",
    )
    parser.add_argument("--piston-config", default=str(ROOT / "configs/execution/piston-local.yaml"))
    parser.add_argument(
        "--piston-transport-policy", default=str(ROOT / "configs/execution/piston-transport-resilience.yaml")
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--output-dir", default="/home/dzy/wp9c-fresh-reduced-calibration-retry-score-C28")
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    preflight = _preflight(args)
    print(json.dumps({"status": "C28_PREFLIGHT_OK", **preflight}, sort_keys=True))
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
        executor_factory=lambda: PistonExecutor(piston_config, transport_policy=piston_transport_policy),
        workers=args.workers,
    )
    manifest = check_reduced_pool_calibration_scoring(output)
    if (
        manifest.get("problem_count") != 195
        or manifest.get("block_index") != 1
        or manifest.get("generation_records_sha256") != EXPECTED["c27_generation_records_sha256"]
        or manifest.get("problem_order_sha256") != EXPECTED["retry_problem_order_sha256"]
        or manifest.get("piston_config_sha256") != EXPECTED["piston_config_sha256"]
        or manifest.get("retry_problem_count") != 0
    ):
        raise ValueError("C28 completed retry scoring strict postcheck failed")
    print(
        json.dumps(
            {
                "status": "C28_RETRY_SCORING_COMPLETED",
                "output_dir": str(output),
                "problem_count": manifest["problem_count"],
                "records_sha256": manifest["records_sha256"],
                "retry_problem_count": manifest["retry_problem_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
