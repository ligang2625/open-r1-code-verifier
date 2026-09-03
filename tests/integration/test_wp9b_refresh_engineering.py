"""Production-shadow engineering acceptance for WP9-b refresh tooling."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

import code_verifier.training.calibration as calibration_module
from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.data.refresh import prepare_refresh_data
from code_verifier.evaluation.generate import GenerationResult
from code_verifier.execution import ExecutionResult, ExecutionStatus
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.throughput import summarize_refresh_benchmarks
from code_verifier.training.calibration import (
    CalibrationConfig,
    CalibrationError,
    build_calibrated_active_pool,
    check_calibrated_active_pool,
    prepare_calibration_input_bundle,
    run_calibration_generation,
    score_calibration_generation,
)
from code_verifier.training.grpo import GRPOTrainingError, load_grpo_refresh_binding, load_grpo_training_config
from code_verifier.training.sft import SFTCheckpointIdentity
from tests.integration.test_wp9a_refresh_data_pipeline import _setup_fixture_environment
from tests.unit.throughput_fixture import write_grpo_probe

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "wp9b"


class _AlternatingGenerator:
    """Emit deterministic parseable k=8 completions without loading a model."""

    def generate_group(self, prompt: str, *, seed: int, num_generations: int) -> list[GenerationResult]:
        assert seed >= 0
        assert num_generations == 8
        signature = prompt.split("Function signature:\n", 1)[1].splitlines()[0]
        return [
            GenerationResult(
                completion=f"```python\n{signature}\n    return None  # SAMPLE_{index}\n```",
                completion_tokens=8 + index,
                latency_ms=float(index + 1),
                hit_max_new_tokens=False,
            )
            for index in range(num_generations)
        ]


class _PatternExecutor:
    """Executor double whose result depends only on the fixture sample marker."""

    def __init__(self, pass_pattern: tuple[bool, ...]) -> None:
        self._pass_pattern = pass_pattern

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        assert function_name
        assert timeout_seconds > 0.0
        assert memory_limit_mb > 0
        match = re.search(r"SAMPLE_([0-7])", code)
        assert match is not None
        passed = self._pass_pattern[int(match.group(1))]
        status = ExecutionStatus.PASSED if passed else ExecutionStatus.WRONG_ANSWER
        test_results = [
            ExecutionTestCaseResult(
                status=status,
                passed=passed,
                runtime_ms=0.1,
                stdout="",
                stderr="",
            )
            for _ in tests
        ]
        passed_tests = len(tests) if passed else 0
        return ExecutionResult(
            status=status,
            passed_tests=passed_tests,
            total_tests=len(tests),
            pass_rate=1.0 if passed else 0.0,
            runtime_ms=0.1 * len(tests),
            test_results=test_results,
        )


def _fake_sft_identity(root: Path) -> SFTCheckpointIdentity:
    return SFTCheckpointIdentity(
        run_dir=root / "sft",
        checkpoint_dir=root / "sft" / "checkpoints",
        run_id="fixture-b",
        model_id="fixture/model",
        model_revision="a" * 40,
        dataset_hash="b" * 64,
        config_hash="c" * 64,
        dependency_lock_hash="d" * 64,
        seed=42,
    )


def _generation_bundle(root: Path, *, name: str, batch_size: int, latency_ms: float) -> Path:
    run = root / name
    samples = run / "samples"
    samples.mkdir(parents=True)
    resolved = {
        "schema_version": 2,
        "run_id": name,
        "model_id": "fixture/model",
        "model_revision": "a" * 40,
        "checkpoint": "fixture-b",
        "seed": 42,
        "split": "test",
        "device": "cuda",
        "generation": {"do_sample": False, "max_new_tokens": 512},
        "dataset_hash": "e" * 64,
        "piston_config_sha256": "9" * 64,
        "batch_size": batch_size,
    }
    contract_sha256 = stable_json_hash(resolved)
    rows = [
        {
            "run_id": name,
            "model_id": "fixture/model",
            "checkpoint": "fixture-b",
            "dataset_hash": "e" * 64,
            "evaluation_contract_sha256": contract_sha256,
            "problem_id": f"eval-{index}",
            "prompt_hash": ("1" if index == 0 else "2") * 64,
            "completion": "same deterministic completion",
            "completion_tokens": 12,
            "generation_latency_ms": latency_ms,
            "hit_max_new_tokens": False,
        }
        for index in range(2)
    ]
    records_path = samples / "generations.jsonl"
    records_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    resolved_path = run / "resolved_config.yaml"
    resolved_path.write_text(yaml.safe_dump(resolved, sort_keys=True), encoding="utf-8")
    (run / "run.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_type": "evaluation_generation_bundle",
                "status": "completed",
                "run_id": name,
                "model_id": "fixture/model",
                "model_revision": "a" * 40,
                "checkpoint": "fixture-b",
                "dataset_hash": "e" * 64,
                "seed": 42,
                "batch_size": batch_size,
                "evaluation_contract_sha256": contract_sha256,
                "ordered_problem_ids_sha256": stable_json_hash([row["problem_id"] for row in rows]),
                "resolved_config_sha256": hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
                "completed_records": len(rows),
                "total_problems": len(rows),
                "records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return run


def test_calibration_input_context_filter_records_exclusions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refresh_config, reference_dir = _setup_fixture_environment(tmp_path, monkeypatch)
    refresh_dir = tmp_path / "refresh-filter"
    refresh_summary = prepare_refresh_data(
        refresh_config,
        seed=42,
        reference_dataset_dir=reference_dir,
        source_cache_dir=tmp_path / "cache-filter",
        output_dir=refresh_dir,
    )
    assert refresh_summary.selected_problems == 7

    calls = 0

    def count_prompt_tokens(_: str) -> int:
        nonlocal calls
        calls += 1
        return 4096 if calls == 2 else 128

    input_dir = tmp_path / "calibration-input-filtered"
    prepare_calibration_input_bundle(
        refresh_dataset_dir=refresh_dir,
        reference_dataset_dir=reference_dir,
        output_dir=input_dir,
        seed=42,
        allow_test_protocol=True,
        prompt_token_counter=count_prompt_tokens,
        max_prompt_tokens=2048,
        max_new_tokens=512,
        tokenizer_model_id="fixture-model",
        tokenizer_model_revision="a" * 40,
        minimum_records=4,
    )

    manifest = json.loads((input_dir / "input_manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 6
    context_filter = manifest["context_filter"]
    assert context_filter["policy"] == "chat_template_prompt_cap_v1"
    assert context_filter["source_record_count"] == 7
    assert context_filter["eligible_record_count"] == 6
    assert context_filter["excluded_record_count"] == 1
    excluded = [json.loads(line) for line in (input_dir / "excluded_context.jsonl").read_text().splitlines()]
    assert len(excluded) == 1
    assert excluded[0]["prompt_tokens"] == 4096
    assert excluded[0]["reason"] == "prompt_token_limit"
    _, records = calibration_module._load_input_bundle(input_dir)
    assert len(records) == 6


def test_wp9b_production_shadow_calibration_active_pool_and_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sampling = json.loads((FIXTURE_DIR / "engineering_sampling.json").read_text(encoding="utf-8"))
    assert sampling["evidence_class"] == "engineering"
    pass_pattern = tuple(bool(value) for value in sampling["pass_pattern"])
    assert len(pass_pattern) == 8 and 0 < sum(pass_pattern) < 8

    refresh_config, reference_dir = _setup_fixture_environment(tmp_path, monkeypatch)
    refresh_dir = tmp_path / "refresh"
    refresh_summary = prepare_refresh_data(
        refresh_config,
        seed=42,
        reference_dataset_dir=reference_dir,
        source_cache_dir=tmp_path / "cache",
        output_dir=refresh_dir,
    )
    assert refresh_summary.selected_problems == 7

    input_dir = tmp_path / "calibration-input"
    prepare_calibration_input_bundle(
        refresh_dataset_dir=refresh_dir,
        reference_dataset_dir=reference_dir,
        output_dir=input_dir,
        seed=42,
        allow_test_protocol=True,
    )
    input_payload = (input_dir / "inputs.jsonl").read_text(encoding="utf-8")
    assert "train_hidden_tests" not in input_payload
    assert "eval_hidden_tests" not in input_payload
    assert "reference_solution" not in input_payload

    monkeypatch.setattr(
        calibration_module,
        "load_completed_sft_checkpoint",
        lambda _: _fake_sft_identity(tmp_path),
    )
    generation_dir = tmp_path / "calibration-generation"
    run_calibration_generation(
        input_bundle_dir=input_dir,
        sft_run_dir=tmp_path / "unused-sft",
        generator=_AlternatingGenerator(),
        output_dir=generation_dir,
        block_index=0,
    )

    score_dir = tmp_path / "calibration-score"
    score_calibration_generation(
        refresh_dataset_dir=refresh_dir,
        reference_dataset_dir=reference_dir,
        input_bundle_dir=input_dir,
        generation_run_dir=generation_dir,
        output_dir=score_dir,
        executor_factory=lambda: _PatternExecutor(pass_pattern),
        workers=8,
        allow_test_protocol=True,
    )
    retry_rows = (score_dir / "manifest" / "retry_problem_ids.jsonl").read_text(encoding="utf-8")
    assert retry_rows == ""

    active_config = CalibrationConfig(
        initial_generations=8,
        retry_generations=8,
        temperature=0.8,
        top_p=0.95,
        max_new_tokens=512,
        max_prompt_tokens=2048,
        active_pool_size=4,
        sft_overlap_fraction=0.0,
        sft_overlap_hard_max=0.15,
        dual_informative_min_fraction=0.70,
        public_only_max_fraction=0.15,
        hidden_only_max_fraction=0.15,
    )
    active_dir = tmp_path / "active-pool"
    built = build_calibrated_active_pool(
        config=active_config,
        refresh_dataset_dir=refresh_dir,
        reference_dataset_dir=reference_dir,
        input_bundle_dir=input_dir,
        initial_scoring_dir=score_dir,
        retry_scoring_dir=None,
        output_dir=active_dir,
        seed=42,
        allow_test_protocol=True,
    )
    checked = check_calibrated_active_pool(
        active_dir,
        refresh_dataset_dir=refresh_dir,
        reference_dataset_dir=reference_dir,
        allow_test_protocol=True,
    )
    assert built == checked
    assert checked.selected_problems == 4
    assert checked.dual_informative == 4
    public_text = checked.public_grpo_jsonl.read_text(encoding="utf-8")
    hidden_text = checked.hidden_grpo_jsonl.read_text(encoding="utf-8")
    assert "train_hidden_tests" not in public_text
    assert "eval_hidden_tests" not in public_text
    assert "eval_hidden_tests" not in hidden_text

    eval_base = _generation_bundle(tmp_path, name="eval-batch1", batch_size=1, latency_ms=4.0)
    eval_batch2 = _generation_bundle(tmp_path, name="eval-batch2", batch_size=2, latency_ms=2.0)
    started = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)
    grpo_base = write_grpo_probe(
        tmp_path,
        name="grpo-workers8",
        reward_mode="public",
        workers=8,
        start=started,
        duration_seconds=8.0,
        calibration_manifest_sha256=hashlib.sha256(checked.calibration_manifest.read_bytes()).hexdigest(),
        active_order_sha256=checked.active_order_sha256,
        active_public_training_sha256=hashlib.sha256(checked.public_grpo_jsonl.read_bytes()).hexdigest(),
        active_hidden_training_sha256=hashlib.sha256(checked.hidden_grpo_jsonl.read_bytes()).hexdigest(),
    )
    grpo_workers16 = write_grpo_probe(
        tmp_path,
        name="grpo-workers16",
        reward_mode="public",
        workers=16,
        start=started,
        duration_seconds=4.0,
        calibration_manifest_sha256=hashlib.sha256(checked.calibration_manifest.read_bytes()).hexdigest(),
        active_order_sha256=checked.active_order_sha256,
        active_public_training_sha256=hashlib.sha256(checked.public_grpo_jsonl.read_bytes()).hexdigest(),
        active_hidden_training_sha256=hashlib.sha256(checked.hidden_grpo_jsonl.read_bytes()).hexdigest(),
    )
    benchmark_manifest = tmp_path / "benchmark.yaml"
    benchmark_manifest.write_text(
        yaml.safe_dump(
            {
                "version": "wp9b-refresh-benchmark-v1",
                "evidence_class": "engineering",
                "eval_generation": {
                    "baseline": str(eval_base),
                    "candidates": [str(eval_batch2)],
                },
                "grpo_verification": {
                    "baseline": str(grpo_base),
                    "candidates": [str(grpo_workers16)],
                },
            }
        ),
        encoding="utf-8",
    )
    benchmark = summarize_refresh_benchmarks(
        benchmark_manifest,
        output_dir=tmp_path / "benchmark-report",
    )
    assert benchmark.evidence_class == "engineering"
    assert benchmark.selected_eval_generation_batch_size == 2
    assert benchmark.selected_grpo_verification_workers == 16

    binding = load_grpo_refresh_binding(
        calibration_manifest_path=checked.calibration_manifest,
        refresh_dataset_dir=refresh_dir,
        reference_dataset_dir=reference_dir,
        benchmark_report_path=benchmark.report_path,
        verification_workers=16,
        allow_engineering=True,
    )
    assert binding.active_order_sha256 == checked.active_order_sha256
    assert binding.verification_workers == 16

    legacy_public = load_grpo_training_config(Path("configs/grpo/public.yaml"))
    legacy_hidden = load_grpo_training_config(Path("configs/grpo/hidden.yaml"))
    refresh_public = load_grpo_training_config(Path("configs/grpo/refresh-public.yaml"))
    refresh_hidden = load_grpo_training_config(Path("configs/grpo/refresh-hidden.yaml"))
    assert legacy_public.num_generations == legacy_hidden.num_generations == 4
    assert refresh_public.num_generations == refresh_hidden.num_generations == 8

    tampered = tmp_path / "tampered-active"
    shutil.copytree(active_dir, tampered)
    with (tampered / "training" / "public_grpo.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(CalibrationError, match="artifact hash mismatch"):
        check_calibrated_active_pool(
            tampered,
            refresh_dataset_dir=refresh_dir,
            reference_dataset_dir=reference_dir,
            allow_test_protocol=True,
        )

    selection_tamper = tmp_path / "selection-tamper"
    shutil.copytree(active_dir, selection_tamper)
    selection_path = selection_tamper / "manifest" / "active_selection.jsonl"
    selection_rows = [json.loads(line) for line in selection_path.read_text(encoding="utf-8").splitlines()]
    selection_rows.reverse()
    for ordinal, row in enumerate(selection_rows):
        row["ordinal"] = ordinal
    order_rows = [{"ordinal": index, "problem_id": row["problem_id"]} for index, row in enumerate(selection_rows)]
    public_path = selection_tamper / "training" / "public_grpo.jsonl"
    hidden_path = selection_tamper / "training" / "hidden_grpo.jsonl"
    public_rows = [json.loads(line) for line in public_path.read_text(encoding="utf-8").splitlines()]
    hidden_rows = [json.loads(line) for line in hidden_path.read_text(encoding="utf-8").splitlines()]
    public_rows.reverse()
    hidden_rows.reverse()
    manifest_path = selection_tamper / "calibration_manifest.json"
    selection_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selection_manifest["active_order_sha256"] = stable_json_hash([row["problem_id"] for row in selection_rows])
    selection_manifest["artifacts"]["manifest/active_selection.jsonl"] = calibration_module._write_jsonl(
        selection_path, selection_rows
    )
    selection_manifest["artifacts"]["manifest/problem_order.jsonl"] = calibration_module._write_jsonl(
        selection_tamper / "manifest" / "problem_order.jsonl", order_rows
    )
    selection_manifest["artifacts"]["training/public_grpo.jsonl"] = calibration_module._write_jsonl(
        public_path, public_rows
    )
    selection_manifest["artifacts"]["training/hidden_grpo.jsonl"] = calibration_module._write_jsonl(
        hidden_path, hidden_rows
    )
    calibration_module._write_json(manifest_path, selection_manifest)
    with pytest.raises(CalibrationError, match="order does not recompute"):
        check_calibrated_active_pool(
            selection_tamper,
            refresh_dataset_dir=refresh_dir,
            reference_dataset_dir=reference_dir,
            allow_test_protocol=True,
        )

    derived_tamper = tmp_path / "derived-tamper"
    shutil.copytree(active_dir, derived_tamper)
    records_path = derived_tamper / "records" / "calibration.jsonl"
    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
    records[0]["public_test_reward_std"] = 123.0
    unhashed = dict(records[0])
    unhashed.pop("calibration_record_sha256")
    records[0]["calibration_record_sha256"] = stable_json_hash(unhashed)
    records_sha = calibration_module._write_jsonl(records_path, records)
    derived_manifest_path = derived_tamper / "calibration_manifest.json"
    derived_manifest = json.loads(derived_manifest_path.read_text(encoding="utf-8"))
    derived_manifest["artifacts"]["records/calibration.jsonl"] = records_sha
    calibration_module._write_json(derived_manifest_path, derived_manifest)
    with pytest.raises(CalibrationError, match="derived reward statistics"):
        check_calibrated_active_pool(
            derived_tamper,
            refresh_dataset_dir=refresh_dir,
            reference_dataset_dir=reference_dir,
            allow_test_protocol=True,
        )

    class_tamper = tmp_path / "class-tamper"
    shutil.copytree(active_dir, class_tamper)
    class_records_path = class_tamper / "records" / "calibration.jsonl"
    class_records = [json.loads(line) for line in class_records_path.read_text(encoding="utf-8").splitlines()]
    class_records[0]["calibration_class"] = "public_only"
    unhashed_class_record = dict(class_records[0])
    unhashed_class_record.pop("calibration_record_sha256")
    class_records[0]["calibration_record_sha256"] = stable_json_hash(unhashed_class_record)
    class_records_sha = calibration_module._write_jsonl(class_records_path, class_records)
    class_manifest_path = class_tamper / "calibration_manifest.json"
    class_manifest = json.loads(class_manifest_path.read_text(encoding="utf-8"))
    class_manifest["artifacts"]["records/calibration.jsonl"] = class_records_sha
    calibration_module._write_json(class_manifest_path, class_manifest)
    with pytest.raises(CalibrationError, match="class does not recompute"):
        check_calibrated_active_pool(
            class_tamper,
            refresh_dataset_dir=refresh_dir,
            reference_dataset_dir=reference_dir,
            allow_test_protocol=True,
        )

    with pytest.raises(GRPOTrainingError, match="calibration artifact failed strict check"):
        load_grpo_refresh_binding(
            calibration_manifest_path=derived_manifest_path,
            refresh_dataset_dir=refresh_dir,
            reference_dataset_dir=reference_dir,
            benchmark_report_path=benchmark.report_path,
            verification_workers=16,
            allow_engineering=True,
        )

    training_tamper = tmp_path / "training-view-tamper"
    shutil.copytree(active_dir, training_tamper)
    public_path = training_tamper / "training" / "public_grpo.jsonl"
    public_rows = [json.loads(line) for line in public_path.read_text(encoding="utf-8").splitlines()]
    public_rows[0]["prompt"] = f"{public_rows[0]['prompt']} [tampered]"
    public_sha = calibration_module._write_jsonl(public_path, public_rows)
    training_manifest_path = training_tamper / "calibration_manifest.json"
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
    training_manifest["artifacts"]["training/public_grpo.jsonl"] = public_sha
    calibration_module._write_json(training_manifest_path, training_manifest)
    with pytest.raises(CalibrationError, match="frozen WP9-a row"):
        check_calibrated_active_pool(
            training_tamper,
            refresh_dataset_dir=refresh_dir,
            reference_dataset_dir=reference_dir,
            allow_test_protocol=True,
        )

    composition_tamper = tmp_path / "composition-tamper"
    shutil.copytree(active_dir, composition_tamper)
    composition_path = composition_tamper / "reports" / "pool_composition.json"
    composition = json.loads(composition_path.read_text(encoding="utf-8"))
    composition["selected_problems"] += 1
    calibration_module._write_json(composition_path, composition)
    composition_manifest_path = composition_tamper / "calibration_manifest.json"
    composition_manifest = json.loads(composition_manifest_path.read_text(encoding="utf-8"))
    composition_manifest["composition"] = composition
    composition_manifest["artifacts"]["reports/pool_composition.json"] = hashlib.sha256(
        composition_path.read_bytes()
    ).hexdigest()
    calibration_module._write_json(composition_manifest_path, composition_manifest)
    with pytest.raises(CalibrationError, match="composition does not recompute"):
        check_calibrated_active_pool(
            composition_tamper,
            refresh_dataset_dir=refresh_dir,
            reference_dataset_dir=reference_dir,
            allow_test_protocol=True,
        )
