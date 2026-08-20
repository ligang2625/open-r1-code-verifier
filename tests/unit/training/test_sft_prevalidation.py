"""Tests for durable off-GPU SFT prevalidation evidence."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from code_verifier.execution import ExecutionResult, ExecutionStatus
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training import sft_prevalidation as module
from code_verifier.training.sft_prevalidation import (
    SFTPrevalidationError,
    run_sft_prevalidation,
    validate_sft_prevalidation_manifest,
)


class _Codec:
    chat_template = "fixture-template"

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> list[int]:
        assert tokenize is True
        assert add_generation_prompt is False
        content = "".join(message["content"] for message in messages)
        return list(range(max(1, len(content) // 4)))


class _PassingPiston:
    calls = 0

    def __init__(self, config: object) -> None:
        self.config = config

    @staticmethod
    def validate_runtime() -> str:
        return "3.10.0"

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        del code, function_name, timeout_seconds, memory_limit_mb
        type(self).calls += 1
        delay = float(tests[0]["input"]) * 0.002
        time.sleep(delay)
        rows = [
            ExecutionTestCaseResult(
                status=ExecutionStatus.PASSED,
                passed=True,
                runtime_ms=1.0,
                stdout="",
                stderr="",
            )
            for _ in tests
        ]
        return ExecutionResult(
            status=ExecutionStatus.PASSED,
            passed_tests=len(tests),
            total_tests=len(tests),
            pass_rate=1.0,
            runtime_ms=float(len(tests)),
            test_results=rows,
        )


def _record(problem_id: str, value: int) -> dict[str, object]:
    return {
        "problem_id": problem_id,
        "prompt": f"Return {value}.",
        "function_name": "solve",
        "visible_tests": [{"input": value, "expected": value}],
        "sft_response": "def solve(value):\n    return value",
        "metadata": {
            "difficulty": "easy",
            "category": ["unit"],
            "time_limit_seconds": 1.0,
            "memory_limit_mb": 128,
            "license": "test",
            "source_url_hash": None,
        },
    }


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_piston_config(path: Path) -> None:
    path.write_text(
        "piston:\n"
        "  base_url: http://127.0.0.1:2000\n"
        "  language: python\n"
        '  version: "3.10.0"\n'
        "  request_timeout_margin_seconds: 30.0\n"
        "  max_response_bytes: 131072\n"
        "  max_output_bytes: 4096\n"
        "  stop_on_first_failure: false\n",
        encoding="utf-8",
    )


def _environment() -> dict[str, object]:
    return {
        "project_commit": "1" * 40,
        "open_r1_commit": "2" * 40,
        "python_version": "3.10.0",
        "platform": "fixture-linux",
        "packages": {},
        "cuda_version": None,
        "gpu_name": None,
        "gpu_count": 0,
        "compute_capability": None,
        "bf16_supported": None,
        "dependency_lock_hash": "3" * 64,
    }


def _produce_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path, Path]:
    train_path = tmp_path / "training/sft.jsonl"
    validation_path = tmp_path / "training/sft_validation.jsonl"
    piston_path = tmp_path / "piston.yaml"
    manifest_path = tmp_path / "evidence/manifest.json"
    _write_records(train_path, [_record("train-1", 3), _record("train-2", 1), _record("train-3", 2)])
    _write_records(validation_path, [_record("validation-1", 1)])
    _write_piston_config(piston_path)
    _PassingPiston.calls = 0
    monkeypatch.setattr(module, "PistonExecutor", _PassingPiston)
    monkeypatch.setattr(module, "_load_tokenizer", lambda model_id, revision: _Codec())
    monkeypatch.setattr(module, "collect_environment", _environment)
    progress: list[tuple[str, int, int]] = []

    summary = run_sft_prevalidation(
        dataset_path=train_path,
        validation_dataset_path=validation_path,
        model_id="example/model",
        model_revision="revision-1",
        max_seq_length=128,
        piston_config_path=piston_path,
        output_manifest=manifest_path,
        workers=3,
        progress_every=1,
        progress_callback=lambda split, done, total, elapsed: progress.append((split, done, total)),
    )

    assert summary.total_samples == 4
    assert summary.train_samples == 3
    assert summary.validation_samples == 1
    assert summary.workers == 3
    assert _PassingPiston.calls == 4
    assert progress[-1] == ("validation", 1, 1)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [row["problem_id"] for row in manifest["train"]["records"]] == ["train-1", "train-2", "train-3"]
    expected_fields = {"index", "problem_id", "record_sha256", "token_count", "status"}
    assert all(set(row) == expected_fields for row in manifest["train"]["records"])
    serialized = manifest_path.read_text(encoding="utf-8")
    for forbidden in ("visible_tests", "sft_response", "Return 3.", "def solve"):
        assert forbidden not in serialized
    return manifest_path, train_path, validation_path, piston_path


def test_prevalidation_writes_payload_minimal_ordered_manifest_and_accepts_exact_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, train_path, validation_path, piston_path = _produce_manifest(tmp_path, monkeypatch)

    evidence = validate_sft_prevalidation_manifest(
        manifest_path,
        dataset_path=train_path,
        validation_dataset_path=validation_path,
        model_id="example/model",
        model_revision="revision-1",
        max_seq_length=128,
        piston_config_path=piston_path,
    )

    assert len(evidence.manifest_sha256) == 64
    assert evidence.validator_project_commit == "1" * 40
    assert evidence.train_samples == 3
    assert evidence.validation_samples == 1
    assert evidence.max_token_count > 0


def test_prevalidation_manifest_rejects_data_model_and_piston_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, train_path, validation_path, piston_path = _produce_manifest(tmp_path, monkeypatch)

    with pytest.raises(SFTPrevalidationError, match="model identity"):
        validate_sft_prevalidation_manifest(
            manifest_path,
            dataset_path=train_path,
            validation_dataset_path=validation_path,
            model_id="example/model",
            model_revision="revision-2",
            max_seq_length=128,
            piston_config_path=piston_path,
        )

    original = train_path.read_text(encoding="utf-8")
    train_path.write_text(original.replace("Return 3.", "Return three."), encoding="utf-8")
    with pytest.raises(SFTPrevalidationError, match="dataset hash"):
        validate_sft_prevalidation_manifest(
            manifest_path,
            dataset_path=train_path,
            validation_dataset_path=validation_path,
            model_id="example/model",
            model_revision="revision-1",
            max_seq_length=128,
            piston_config_path=piston_path,
        )
    train_path.write_text(original, encoding="utf-8")

    changed_piston = piston_path.read_text(encoding="utf-8").replace(
        "max_output_bytes: 4096", "max_output_bytes: 4095"
    )
    piston_path.write_text(changed_piston, encoding="utf-8")
    with pytest.raises(SFTPrevalidationError, match="Piston config hash"):
        validate_sft_prevalidation_manifest(
            manifest_path,
            dataset_path=train_path,
            validation_dataset_path=validation_path,
            model_id="example/model",
            model_revision="revision-1",
            max_seq_length=128,
            piston_config_path=piston_path,
        )


def test_prevalidation_manifest_is_immutable_and_fail_closed_on_incomplete_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, train_path, validation_path, piston_path = _produce_manifest(tmp_path, monkeypatch)

    with pytest.raises(SFTPrevalidationError, match="already exists"):
        run_sft_prevalidation(
            dataset_path=train_path,
            validation_dataset_path=validation_path,
            model_id="example/model",
            model_revision="revision-1",
            max_seq_length=128,
            piston_config_path=piston_path,
            output_manifest=manifest_path,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    incomplete = tmp_path / "evidence/incomplete.json"
    incomplete.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SFTPrevalidationError, match="not completed"):
        validate_sft_prevalidation_manifest(
            incomplete,
            dataset_path=train_path,
            validation_dataset_path=validation_path,
            model_id="example/model",
            model_revision="revision-1",
            max_seq_length=128,
            piston_config_path=piston_path,
        )
