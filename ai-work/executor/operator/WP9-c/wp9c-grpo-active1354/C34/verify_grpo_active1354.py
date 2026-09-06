#!/usr/bin/env python3
"""Strict local/target audit for the frozen C29 active-1354 GRPO pool."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer

from code_verifier.data.leakage_checks import TrainingArtifactKind, load_training_artifact
from code_verifier.training.grpo_data import build_grpo_row
from code_verifier.training.reduced_calibrated_pool import check_reduced_calibrated_pool

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
EXPECTED_COUNT = 1354
EXPECTED_MANIFEST_SHA256 = "5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b"
EXPECTED_ACTIVE_ORDER_SHA256 = "401f854032095cb638637dcf2d1ec000b770cd2d4c78619331f0b13746618c14"
EXPECTED_PUBLIC_SHA256 = "558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c"
EXPECTED_HIDDEN_SHA256 = "9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec"
FORMAL_B_CONTEXT_CAP = 2048
LEGACY_REFRESH_PROMPT_CAP = 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prompt_tokens(prompt: list[dict[str, str]], tokenizer: Any) -> int:
    rendered = tokenizer.apply_chat_template(prompt, add_generation_prompt=True, tokenize=False)
    encoded = tokenizer(rendered, add_special_tokens=False)
    count = len(encoded["input_ids"])
    if count <= 0:
        raise ValueError("non-positive GRPO prompt token count")
    return count


def audit(pool_dir: Path) -> dict[str, object]:
    checked = check_reduced_calibrated_pool(pool_dir)
    if checked.selected_problems != EXPECTED_COUNT:
        raise ValueError(f"C29 active problem count drift: {checked.selected_problems}/{EXPECTED_COUNT}")
    if checked.active_order_sha256 != EXPECTED_ACTIVE_ORDER_SHA256:
        raise ValueError("C29 active order SHA256 drift")
    if _sha256(checked.calibration_manifest) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("C29 calibration manifest SHA256 drift")
    if _sha256(checked.public_grpo_jsonl) != EXPECTED_PUBLIC_SHA256:
        raise ValueError("C29 Public training SHA256 drift")
    if _sha256(checked.hidden_grpo_jsonl) != EXPECTED_HIDDEN_SHA256:
        raise ValueError("C29 Hidden training SHA256 drift")

    public_rows = load_training_artifact(checked.public_grpo_jsonl, kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden_rows = load_training_artifact(checked.hidden_grpo_jsonl, kind=TrainingArtifactKind.HIDDEN_GRPO)
    public_ids = [str(row["problem_id"]) for row in public_rows]
    hidden_ids = [str(row["problem_id"]) for row in hidden_rows]
    if public_ids != hidden_ids or len(public_ids) != EXPECTED_COUNT:
        raise ValueError("C29 Public/Hidden active problem order drift")

    loader = getattr(AutoTokenizer, "from_" + "pretrained")
    tokenizer = loader(MODEL_ID, revision=MODEL_REVISION, local_files_only=True, trust_remote_code=False)
    counts: list[tuple[int, str]] = []
    for record in public_rows:
        trainer_row = build_grpo_row(record, reward_mode="public")
        prompt = trainer_row.get("prompt")
        if not isinstance(prompt, list):
            raise ValueError("GRPO trainer prompt is not conversational")
        count = _prompt_tokens(prompt, tokenizer)
        counts.append((count, str(record["problem_id"])))

    counts.sort()
    token_values = [count for count, _ in counts]
    over_1024 = [(count, problem_id) for count, problem_id in counts if count > LEGACY_REFRESH_PROMPT_CAP]
    over_2048 = [(count, problem_id) for count, problem_id in counts if count > FORMAL_B_CONTEXT_CAP]
    if over_2048:
        raise ValueError(f"C29 active GRPO prompt exceeds frozen Formal-B cap: {over_2048[-1]}")
    p95_index = max(0, math.ceil(0.95 * len(token_values)) - 1)
    max_count, max_problem_id = counts[-1]
    return {
        "schema_version": "wp9c-grpo-active1354-audit-v1",
        "status": "passed",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "active_problem_count": EXPECTED_COUNT,
        "calibration_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "active_order_sha256": EXPECTED_ACTIVE_ORDER_SHA256,
        "public_training_sha256": EXPECTED_PUBLIC_SHA256,
        "hidden_training_sha256": EXPECTED_HIDDEN_SHA256,
        "prompt_token_contract": {
            "chat_template": "tokenizer.apply_chat_template(add_generation_prompt=True)",
            "formal_b_context_cap": FORMAL_B_CONTEXT_CAP,
            "legacy_refresh_config_cap": LEGACY_REFRESH_PROMPT_CAP,
            "min_prompt_tokens": token_values[0],
            "p95_prompt_tokens": token_values[p95_index],
            "max_prompt_tokens": max_count,
            "max_prompt_problem_id": max_problem_id,
            "count_over_1024": len(over_1024),
            "count_over_2048": 0,
            "legacy_1024_would_truncate": bool(over_1024),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = audit(args.pool_dir)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
