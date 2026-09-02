from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

import pytest

from code_verifier.config import ConfigError
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


class _InterruptingGenerator(_FakeGenerator):
    def __init__(self, *, successful_groups: int) -> None:
        super().__init__()
        self._successful_groups = successful_groups

    def generate_group(self, prompt: str, *, seed: int, num_generations: int) -> list[GenerationResult]:
        if len(self.calls) >= self._successful_groups:
            raise RuntimeError("simulated generation interruption")
        return super().generate_group(prompt, seed=seed, num_generations=num_generations)


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


def test_tracked_calibration_config_rejects_protocol_drift(tmp_path: Path) -> None:
    source = Path("configs/grpo/refresh-calibration.yaml").read_text(encoding="utf-8")
    drifted = tmp_path / "drifted.yaml"
    drifted.write_text(source.replace("size: 3000", "size: 2999"), encoding="utf-8")

    with pytest.raises(ConfigError, match="frozen WP9 protocol"):
        load_calibration_config(drifted)


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


def test_generation_resume_accepts_empty_exact_prefix_after_early_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    _write_input_bundle(input_dir, ["p1", "p2"])
    monkeypatch.setattr(calibration, "load_completed_sft_checkpoint", lambda _: _fake_sft_identity(tmp_path))
    run_dir = tmp_path / "run"

    with pytest.raises(RuntimeError, match="simulated generation interruption"):
        run_calibration_generation(
            input_bundle_dir=input_dir,
            sft_run_dir=tmp_path / "sft",
            generator=_InterruptingGenerator(successful_groups=0),
            output_dir=run_dir,
            block_index=0,
        )

    assert (run_dir / "run.json").is_file()
    assert not (run_dir / "samples" / "generations.jsonl").exists()

    resumed = _FakeGenerator()
    summary = run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=tmp_path / "sft",
        generator=resumed,
        output_dir=run_dir,
        block_index=0,
    )

    assert summary.record_count == 16
    assert [call[0] for call in resumed.calls] == ["prompt p1", "prompt p2"]


def test_generation_resume_continues_after_last_complete_k8_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    _write_input_bundle(input_dir, ["p1", "p2"])
    monkeypatch.setattr(calibration, "load_completed_sft_checkpoint", lambda _: _fake_sft_identity(tmp_path))
    run_dir = tmp_path / "run"

    with pytest.raises(RuntimeError, match="simulated generation interruption"):
        run_calibration_generation(
            input_bundle_dir=input_dir,
            sft_run_dir=tmp_path / "sft",
            generator=_InterruptingGenerator(successful_groups=1),
            output_dir=run_dir,
            block_index=0,
        )

    partial = (run_dir / "samples" / "generations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(partial) == 8

    resumed = _FakeGenerator()
    summary = run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=tmp_path / "sft",
        generator=resumed,
        output_dir=run_dir,
        block_index=0,
    )

    assert summary.record_count == 16
    assert [call[0] for call in resumed.calls] == ["prompt p2"]


def test_completed_generation_is_strictly_reused_and_cannot_be_reblessed_after_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    _write_input_bundle(input_dir, ["p1"])
    monkeypatch.setattr(calibration, "load_completed_sft_checkpoint", lambda _: _fake_sft_identity(tmp_path))
    run_dir = tmp_path / "run"
    initial = run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=tmp_path / "sft",
        generator=_FakeGenerator(),
        output_dir=run_dir,
        block_index=0,
    )

    unused = _FakeGenerator()
    reused = run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=tmp_path / "sft",
        generator=unused,
        output_dir=run_dir,
        block_index=0,
    )
    assert reused.records_sha256 == initial.records_sha256
    assert unused.calls == []

    generation_path = run_dir / "samples" / "generations.jsonl"
    rows = generation_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(rows[0])
    tampered["completion"] = "tampered"
    generation_path.write_text(json.dumps(tampered) + "\n" + "\n".join(rows[1:]) + "\n", encoding="utf-8")

    with pytest.raises(CalibrationError, match="hash mismatch"):
        run_calibration_generation(
            input_bundle_dir=input_dir,
            sft_run_dir=tmp_path / "sft",
            generator=_FakeGenerator(),
            output_dir=run_dir,
            block_index=0,
        )


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


def test_retry_and_disposition_rules_cover_hard_easy_and_quality_priority() -> None:
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
    retry_zero = {**base, "sample_indices": list(range(8, 16)), "completion_sha256": ["b"] * 8}
    hard = calibration._merge_score_records(base, retry_zero)
    assert hard["sample_indices"] == list(range(16))
    assert hard["calibration_class"] == CalibrationClass.DUAL_UNINFORMATIVE.value
    assert hard["public_all_test_zero"] is True
    assert hard["hidden_all_test_zero"] is True
    assert calibration._calibration_disposition(hard, retried=True) == "dual_uninformative_after_16"

    saturated_initial = {
        **base,
        "public_test_rewards": [1.0] * 8,
        "hidden_test_rewards": [1.0] * 8,
        "public_total_rewards": [1.1] * 8,
        "hidden_total_rewards": [1.1] * 8,
    }
    saturated_retry = {
        **saturated_initial,
        "sample_indices": list(range(8, 16)),
        "completion_sha256": ["c"] * 8,
    }
    easy = calibration._merge_score_records(saturated_initial, saturated_retry)
    assert easy["public_all_test_correct"] is True
    assert easy["hidden_all_test_correct"] is True
    assert calibration._calibration_disposition(easy, retried=True) == "dual_saturated"

    quality = {**easy, "quality_gate_required": True}
    assert calibration._calibration_disposition(quality, retried=True) == "quality_gate_required"


def test_active_selection_stratifies_unequal_source_difficulty_in_both_overlap_buckets() -> None:
    config = CalibrationConfig(8, 8, 0.8, 0.95, 512, 20, 0.10, 0.15, 0.70, 0.15, 0.15)
    records: list[dict[str, object]] = []
    for prefix, count, source_name, difficulty, overlap_origin in (
        ("sft-a", 3, "source-a", "easy", "sft_reuse"),
        ("sft-b", 2, "source-b", "hard", "sft_reuse"),
        ("ext-c", 15, "source-c", "easy", "external_new"),
        ("ext-d", 7, "source-d", "hard", "external_new"),
    ):
        records.extend(
            {
                "problem_id": f"{prefix}-{index}",
                "source_name": source_name,
                "difficulty": difficulty,
                "overlap_origin": overlap_origin,
                "calibration_class": CalibrationClass.DUAL_INFORMATIVE.value,
            }
            for index in range(count)
        )

    selected, reserve = calibration._select_active_records(records, config=config, seed=42)
    strata = Counter(
        (
            cast(str, record["overlap_origin"]),
            cast(str, record["source_name"]),
            cast(str, record["difficulty"]),
        )
        for record in selected
    )
    assert len(selected) == 20
    assert len(reserve) == 7
    assert strata == Counter(
        {
            ("sft_reuse", "source-a", "easy"): 1,
            ("sft_reuse", "source-b", "hard"): 1,
            ("external_new", "source-c", "easy"): 12,
            ("external_new", "source-d", "hard"): 6,
        }
    )

    selected_again, _ = calibration._select_active_records(records, config=config, seed=42)
    assert [record["problem_id"] for record in selected_again] == [record["problem_id"] for record in selected]


def test_active_selection_allocates_whole_bucket_before_class_preference() -> None:
    config = CalibrationConfig(8, 8, 0.8, 0.95, 512, 18, 0.0, 0.15, 0.70, 0.15, 0.15)
    records: list[dict[str, object]] = [
        {
            "problem_id": f"dual-{index}",
            "source_name": "source-a",
            "difficulty": "hard",
            "overlap_origin": "external_new",
            "calibration_class": CalibrationClass.DUAL_INFORMATIVE.value,
        }
        for index in range(16)
    ]
    records.extend(
        {
            "problem_id": f"public-{index}",
            "source_name": "source-b",
            "difficulty": "easy",
            "overlap_origin": "external_new",
            "calibration_class": CalibrationClass.PUBLIC_ONLY.value,
        }
        for index in range(2)
    )
    records.extend(
        {
            "problem_id": f"hidden-{index}",
            "source_name": "source-b",
            "difficulty": "easy",
            "overlap_origin": "external_new",
            "calibration_class": CalibrationClass.HIDDEN_ONLY.value,
        }
        for index in range(2)
    )

    selected, reserve = calibration._select_active_records(records, config=config, seed=42)
    assert Counter(
        (cast(str, record["source_name"]), cast(str, record["difficulty"])) for record in selected
    ) == Counter({("source-a", "hard"): 14, ("source-b", "easy"): 4})
    assert Counter(cast(str, record["calibration_class"]) for record in selected) == Counter(
        {
            CalibrationClass.DUAL_INFORMATIVE.value: 14,
            CalibrationClass.PUBLIC_ONLY.value: 2,
            CalibrationClass.HIDDEN_ONLY.value: 2,
        }
    )
    assert len(reserve) == 2

    selected_again, reserve_again = calibration._select_active_records(list(reversed(records)), config=config, seed=42)
    assert [record["problem_id"] for record in selected_again] == [record["problem_id"] for record in selected]
    assert sorted(reserve_again, key=lambda record: cast(str, record["problem_id"])) == sorted(
        reserve, key=lambda record: cast(str, record["problem_id"])
    )


def test_active_selection_rejects_correlated_single_arm_cap_with_diagnostics() -> None:
    config = CalibrationConfig(8, 8, 0.8, 0.95, 512, 18, 0.0, 0.15, 0.70, 0.15, 0.15)
    records: list[dict[str, object]] = [
        {
            "problem_id": f"dual-{index}",
            "source_name": "source-a",
            "difficulty": "hard",
            "overlap_origin": "external_new",
            "calibration_class": CalibrationClass.DUAL_INFORMATIVE.value,
        }
        for index in range(16)
    ]
    records.extend(
        {
            "problem_id": f"public-{index}",
            "source_name": "source-b",
            "difficulty": "easy",
            "overlap_origin": "external_new",
            "calibration_class": CalibrationClass.PUBLIC_ONLY.value,
        }
        for index in range(4)
    )

    with pytest.raises(CalibrationError, match="population_diagnostics=") as error:
        calibration._select_active_records(records, config=config, seed=42)

    message = str(error.value)
    for expected in (
        '"overlap_bucket":"external_new"',
        '"calibration_class":"public_only"',
        '"source_name":"source-b"',
    ):
        assert expected in message


def test_active_selection_error_reports_requested_constraints_and_stratified_population() -> None:
    config = CalibrationConfig(8, 8, 0.8, 0.95, 512, 10, 0.10, 0.15, 0.70, 0.15, 0.15)
    records: list[dict[str, object]] = [
        {
            "problem_id": f"p-{index}",
            "source_name": "only-source",
            "difficulty": "hard",
            "overlap_origin": "external_new",
            "calibration_class": CalibrationClass.DUAL_INFORMATIVE.value,
        }
        for index in range(10)
    ]

    with pytest.raises(CalibrationError, match="population_diagnostics=") as error:
        calibration._select_active_records(records, config=config, seed=42)

    message = str(error.value)
    for expected in (
        '"requested_class_constraints"',
        '"overlap_bucket":"external_new"',
        '"source_name":"only-source"',
        '"difficulty":"hard"',
    ):
        assert expected in message
