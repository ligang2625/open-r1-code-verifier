from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.evaluation.generate import GenerationResult
from code_verifier.training import calibration
from code_verifier.training.calibration import (
    CALIBRATION_TEST_SCHEMA_VERSION,
    CalibrationClass,
    CalibrationConfig,
    CalibrationError,
    calibration_problem_seed,
    load_calibration_config,
    load_completed_calibration_generation,
    run_calibration_generation,
)
from code_verifier.training.sft import SFTCheckpointIdentity


class _FakeGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def generate_group(self, prompt: str, *, seed: int, num_generations: int) -> list[GenerationResult]:
        self.calls.append((prompt, seed, num_generations))
        return [
            GenerationResult(
                completion=f"completion-{seed}-{index}",
                completion_tokens=index + 1,
                latency_ms=float(index),
                hit_max_new_tokens=index == 7,
            )
            for index in range(num_generations)
        ]


def _write_input_bundle(root: Path, problem_ids: list[str]) -> None:
    rows = [
        {
            "problem_id": problem_id,
            "prompt": f"prompt {problem_id}",
            "function_name": "solve",
            "source_name": "fixture",
            "difficulty": "easy",
            "overlap_origin": "external_new",
            "quality_gate_required": False,
        }
        for problem_id in problem_ids
    ]
    records_sha = calibration._write_jsonl(root / "inputs.jsonl", rows)
    calibration._write_json(
        root / "input_manifest.json",
        {
            "schema_version": CALIBRATION_TEST_SCHEMA_VERSION,
            "seed": 42,
            "record_count": len(rows),
            "records_sha256": records_sha,
            "problem_order_sha256": stable_json_hash(problem_ids),
        },
    )


def _fake_sft_identity(root: Path) -> SFTCheckpointIdentity:
    return SFTCheckpointIdentity(
        run_dir=root,
        checkpoint_dir=root / "adapter",
        run_id="fixture-b",
        model_id="model",
        model_revision="a" * 40,
        dataset_hash="b" * 64,
        config_hash="c" * 64,
        dependency_lock_hash="d" * 64,
        seed=42,
    )


def test_tracked_calibration_config_is_frozen() -> None:
    config = load_calibration_config(Path("configs/grpo/refresh-calibration.yaml"))
    assert config == CalibrationConfig(8, 8, 0.8, 0.95, 512, 3000, 0.075, 0.15, 0.70, 0.15, 0.15)


@pytest.mark.parametrize(
    ("public_std", "hidden_std", "expected"),
    [
        (1.0, 1.0, CalibrationClass.DUAL_INFORMATIVE),
        (1.0, 0.0, CalibrationClass.PUBLIC_ONLY),
        (0.0, 1.0, CalibrationClass.HIDDEN_ONLY),
        (0.0, 0.0, CalibrationClass.DUAL_UNINFORMATIVE),
    ],
)
def test_calibration_class_uses_test_reward_variance(
    public_std: float, hidden_std: float, expected: CalibrationClass
) -> None:
    assert calibration._classification(public_std, hidden_std) is expected


def test_problem_seed_is_stable_and_block_scoped() -> None:
    assert calibration_problem_seed(42, "p1", 0) == calibration_problem_seed(42, "p1", 0)
    assert calibration_problem_seed(42, "p1", 0) != calibration_problem_seed(42, "p1", 1)
    assert calibration_problem_seed(42, "p1", 0) != calibration_problem_seed(42, "p2", 0)


def test_generation_bundle_is_k8_ordered_and_hash_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_dir = tmp_path / "input"
    _write_input_bundle(input_dir, ["p1", "p2"])
    monkeypatch.setattr(calibration, "load_completed_sft_checkpoint", lambda _: _fake_sft_identity(tmp_path))
    generator = _FakeGenerator()
    run_dir = tmp_path / "run"

    summary = run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=tmp_path / "sft",
        generator=generator,
        output_dir=run_dir,
        block_index=0,
    )
    manifest, records = load_completed_calibration_generation(run_dir)

    assert summary.record_count == 16
    assert manifest["samples_per_problem"] == 8
    assert [row["sample_index"] for row in records] == list(range(8)) * 2
    assert len(generator.calls) == 2
    assert all(call[2] == 8 for call in generator.calls)

    generation_path = run_dir / "samples" / "generations.jsonl"
    tampered = json.loads(generation_path.read_text().splitlines()[0])
    tampered["completion"] = "tampered"
    generation_path.write_text(
        json.dumps(tampered) + "\n" + "\n".join(generation_path.read_text().splitlines()[1:]) + "\n"
    )
    with pytest.raises(CalibrationError, match="hash mismatch"):
        load_completed_calibration_generation(run_dir)


def test_retry_generation_requires_exact_sorted_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_dir = tmp_path / "input"
    _write_input_bundle(input_dir, ["p1", "p2"])
    monkeypatch.setattr(calibration, "load_completed_sft_checkpoint", lambda _: _fake_sft_identity(tmp_path))
    retry = tmp_path / "retry.jsonl"
    retry.write_text('{"problem_id":"p2"}\n', encoding="utf-8")

    summary = run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=tmp_path / "sft",
        generator=_FakeGenerator(),
        output_dir=tmp_path / "retry-run",
        block_index=1,
        retry_manifest=retry,
    )
    _, rows = load_completed_calibration_generation(summary.run_dir)
    assert {cast(str, row["problem_id"]) for row in rows} == {"p2"}
    assert [row["sample_index"] for row in rows] == list(range(8, 16))

    retry.write_text('{"problem_id":"p2"}\n{"problem_id":"p1"}\n', encoding="utf-8")
    with pytest.raises(CalibrationError, match="unique and sorted"):
        run_calibration_generation(
            input_bundle_dir=input_dir,
            sft_run_dir=tmp_path / "sft",
            generator=_FakeGenerator(),
            output_dir=tmp_path / "bad-retry-run",
            block_index=1,
            retry_manifest=retry,
        )


def test_merge_retry_recomputes_test_informativeness() -> None:
    base: dict[str, object] = {
        "problem_id": "p1",
        "public_test_rewards": [0.0] * 8,
        "hidden_test_rewards": [0.0] * 8,
        "public_total_rewards": [0.1] * 8,
        "hidden_total_rewards": [0.1] * 8,
        "sample_indices": list(range(8)),
        "completion_sha256": ["a"] * 8,
        "parse_failure_count": 0,
        "execution_failure_count": 0,
        "timeout_count": 0,
        "infrastructure_failure_count": 0,
        "truncation_count": 0,
        "completion_token_max": 10,
        "completion_token_mean": 10.0,
    }
    retry = {
        **base,
        "public_test_rewards": [0.0, 1.0] * 4,
        "hidden_test_rewards": [0.0] * 8,
        "sample_indices": list(range(8, 16)),
    }
    merged = calibration._merge_score_records(base, retry)
    assert merged["calibration_class"] == CalibrationClass.PUBLIC_ONLY.value
    assert merged["public_informative"] is True
    assert merged["hidden_informative"] is False
