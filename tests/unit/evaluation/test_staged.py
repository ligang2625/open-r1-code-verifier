"""Tests for two-stage generation bundles and off-GPU verification."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

import code_verifier.evaluation.evaluate as evaluation_module
import code_verifier.evaluation.staged as staged_module
from code_verifier.data.schema import CodeProblem, ProblemMetadata
from code_verifier.data.schema import TestCase as CodeTestCase
from code_verifier.environment import collect_environment
from code_verifier.evaluation.evaluate import (
    EvaluationConfig,
    EvaluationError,
    load_evaluation_records,
    run_pass1_evaluation,
)
from code_verifier.evaluation.generate import GenerationConfig, GenerationError, GenerationResult
from code_verifier.evaluation.metrics import aggregate_evaluation_run
from code_verifier.evaluation.staged import (
    load_completed_generation_bundle,
    run_generation_bundle,
    run_verification_from_generation_bundle,
)
from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.base import TestCaseResult as ExecutionTestCaseResult
from code_verifier.runtime_telemetry import RuntimeUtilizationSampler


class _SequenceGenerator:
    def __init__(self, values: list[GenerationResult | BaseException]) -> None:
        self._values = list(values)
        self.calls: list[tuple[str, int]] = []

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        self.calls.append((prompt, seed))
        if not self._values:
            raise AssertionError("unexpected generation call")
        value = self._values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class _BatchGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], list[int]]] = []

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        raise AssertionError("batch generator must use generate_batch")

    def generate_batch(self, prompts: list[str], *, seeds: list[int]) -> list[GenerationResult]:
        self.calls.append((list(prompts), list(seeds)))
        return [
            GenerationResult(
                completion=f"```python\ndef solve(x):\n    return x\n# {index}\n```",
                completion_tokens=8 + index,
                latency_ms=2.0,
            )
            for index, _ in enumerate(prompts)
        ]


class _PassExecutor:
    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        del code, function_name, timeout_seconds, memory_limit_mb
        results = [
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
            test_results=results,
        )


class _ConcurrentPassExecutor(_PassExecutor):
    def __init__(self, tracker: dict[str, Any]) -> None:
        self._tracker = tracker

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        lock = self._tracker["lock"]
        assert isinstance(lock, type(threading.Lock()))
        with lock:
            self._tracker["active"] = int(self._tracker["active"]) + 1
            self._tracker["max_active"] = max(int(self._tracker["max_active"]), int(self._tracker["active"]))
        time.sleep(0.01)
        with lock:
            self._tracker["active"] = int(self._tracker["active"]) - 1
        return super().execute(code, function_name, tests, timeout_seconds, memory_limit_mb)


def _problem(problem_id: str, marker: str) -> CodeProblem:
    return CodeProblem(
        problem_id=problem_id,
        source="unit",
        split="test",
        prompt=f"Return the input for {marker}.",
        function_name="solve",
        function_signature="def solve(x):",
        starter_code=None,
        visible_tests=(CodeTestCase(input=f"visible-{marker}", expected=f"visible-{marker}"),),
        train_hidden_tests=(CodeTestCase(input=f"train-{marker}", expected=f"train-{marker}"),),
        eval_hidden_tests=(CodeTestCase(input=f"eval-{marker}", expected=f"eval-{marker}"),),
        reference_solution=None,
        sft_response=None,
        metadata=ProblemMetadata(
            difficulty="easy",
            category=("unit",),
            time_limit_seconds=1.0,
            memory_limit_mb=128,
            license="test",
            source_url_hash=None,
        ),
    )


def _piston_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    return path


def _config(tmp_path: Path, *, name: str = "machine-a") -> EvaluationConfig:
    root = tmp_path / name
    return EvaluationConfig(
        dataset_dir=root / "prepared",
        split="test",
        piston_config=_piston_config(root / "piston.yaml"),
        model_revision="revision-1",
        checkpoint="checkpoint-1",
        device="cpu",
        generation=GenerationConfig(
            do_sample=False,
            temperature=None,
            top_p=None,
            max_new_tokens=32,
            dtype="float32",
        ),
    )


def _completion(marker: str, *, latency_ms: float = 2.0) -> GenerationResult:
    return GenerationResult(
        completion=f"```python\n# {marker}\ndef solve(x):\n    return x\n```",
        completion_tokens=8,
        latency_ms=latency_ms,
        hit_max_new_tokens=False,
    )


def _patch_problems(monkeypatch: pytest.MonkeyPatch, problems: list[CodeProblem]) -> None:
    monkeypatch.setattr(staged_module, "load_evaluation_problems", lambda config: list(problems))
    monkeypatch.setattr(evaluation_module, "load_evaluation_problems", lambda config: list(problems))


def test_two_stage_records_are_exactly_equivalent_to_single_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem("p1", "ONE"), _problem("p2", "TWO")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    values = [_completion("ONE", latency_ms=3.0), _completion("TWO", latency_ms=4.0)]

    direct = run_pass1_evaluation(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator(list(values)),
        executor=_PassExecutor(),
        run_id="equivalent",
        output_root=tmp_path / "direct",
        seed=42,
    )
    generation = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator(list(values)),
        run_id="equivalent",
        output_root=tmp_path / "staged",
        seed=42,
    )
    verified = run_verification_from_generation_bundle(
        config=config,
        generation_run_dir=generation.run_dir,
        executor_factory=_PassExecutor,
        run_id="equivalent",
        output_root=tmp_path / "staged",
        seed=42,
        workers=2,
    )

    assert load_evaluation_records(direct.results_path) == load_evaluation_records(verified.results_path)
    metadata = json.loads((verified.results_path.parents[1] / "run.json").read_text(encoding="utf-8"))
    assert metadata["generation_bundle_records_sha256"]
    assert metadata["generation_bundle_contract_sha256"]
    assert metadata["verification_workers"] == 2
    host_runtime = metadata["runtime_utilization"]
    assert host_runtime["status"] == "unavailable"
    assert host_runtime["host_cpu_count"] > 0
    assert host_runtime["host_max_rss_mib"] >= 0.0
    assert "gpu_utilization_mean_percent" not in host_runtime


def test_generation_bundle_persists_runtime_utilization_when_sampler_is_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem("p1", "ONE")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    sampler = RuntimeUtilizationSampler(interval_seconds=60.0, sample_fn=lambda: (40.0, 768.0))

    summary = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE")]),
        run_id="utilization",
        output_root=tmp_path / "utilization-output",
        seed=42,
        utilization_sampler=sampler,
    )

    metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    utilization = metadata["runtime_utilization"]
    assert utilization["status"] == "available"
    assert utilization["sample_count"] >= 1
    assert utilization["gpu_utilization_mean_percent"] == 40.0
    assert utilization["gpu_memory_used_max_mib"] == 768.0


def test_generation_resume_uses_only_the_missing_exact_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE"), _problem("p2", "TWO")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"

    with pytest.raises(GenerationError, match="stop"):
        run_generation_bundle(
            config=config,
            model_id="example/model",
            generator=_SequenceGenerator([_completion("ONE"), GenerationError("stop")]),
            run_id="resume",
            output_root=output_root,
            seed=42,
        )
    run_json = output_root / "generation" / "resume" / "run.json"
    interrupted = json.loads(run_json.read_text(encoding="utf-8"))
    assert interrupted["status"] == "failed"
    assert interrupted["completed_records"] == 1

    # Simulate a hard process loss after the durable row but before run metadata catches up.
    interrupted["status"] = "running"
    interrupted["completed_records"] = 0
    interrupted["gpu_hours"] = 0.0
    interrupted["records_sha256"] = None
    interrupted["end_time"] = None
    run_json.write_text(json.dumps(interrupted, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    metrics_path = output_root / "generation" / "resume" / "metrics.jsonl"
    metrics_path.write_text("stale-telemetry\n", encoding="utf-8")

    second = _SequenceGenerator([_completion("TWO")])
    resumed = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=second,
        run_id="resume",
        output_root=output_root,
        seed=42,
    )
    assert resumed.completed_before_run == 1
    assert resumed.generated_this_run == 1
    assert len(second.calls) == 1
    metrics_rows = [json.loads(line) for line in metrics_path.read_text(encoding="utf-8").splitlines()]
    assert [row["completed"] for row in metrics_rows] == [1, 2]

    no_op = _SequenceGenerator([])
    completed = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=no_op,
        run_id="resume",
        output_root=output_root,
        seed=42,
    )
    assert completed.completed_before_run == 2
    assert completed.generated_this_run == 0
    assert no_op.calls == []


def test_generation_batch_v2_persists_partial_batch_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem(f"p{index}", f"M{index}") for index in range(5)]
    _patch_problems(monkeypatch, problems)
    generator = _BatchGenerator()
    config = _config(tmp_path)

    bundle = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=generator,
        run_id="batch-v2",
        output_root=tmp_path / "outputs",
        seed=42,
        batch_size=2,
    )

    assert [len(prompts) for prompts, _ in generator.calls] == [2, 2, 1]
    metadata = json.loads((bundle.run_dir / "run.json").read_text(encoding="utf-8"))
    assert metadata["schema_version"] == 2
    assert metadata["batch_size"] == 2
    metrics = [json.loads(line) for line in (bundle.run_dir / "metrics.jsonl").read_text().splitlines()]
    assert [row["batch_index"] for row in metrics] == [0, 0, 1, 1, 2]
    assert metrics[-1]["batch_start_ordinal"] == 4
    assert metrics[-1]["batch_end_ordinal"] == 5
    assert sum(row["generation_latency_ms"] for row in metrics) == 10.0


def test_completed_loader_accepts_historical_v1_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    bundle = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE")]),
        run_id="historical-v1",
        output_root=tmp_path / "outputs",
        seed=42,
    )
    resolved_path = bundle.run_dir / "resolved_config.yaml"
    resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    resolved["schema_version"] = 1
    resolved.pop("batch_size")
    resolved_path.write_text(yaml.safe_dump(resolved, sort_keys=True, allow_unicode=True), encoding="utf-8")
    encoded_contract = json.dumps(resolved, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    contract_sha = hashlib.sha256(encoded_contract.encode()).hexdigest()
    rows_path = bundle.records_path
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["evaluation_contract_sha256"] = contract_sha
    rows_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    run_path = bundle.run_dir / "run.json"
    metadata = json.loads(run_path.read_text(encoding="utf-8"))
    metadata["schema_version"] = 1
    metadata.pop("batch_size")
    metadata["evaluation_contract_sha256"] = contract_sha
    metadata["resolved_config_sha256"] = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    metadata["records_sha256"] = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    run_path.write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    identity, loaded_rows = load_completed_generation_bundle(bundle.run_dir, config=config, problems=problems, seed=42)
    assert identity.schema_version == 1
    assert identity.batch_size == 1
    assert len(loaded_rows) == 1


def test_completed_bundle_is_portable_across_local_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE")]
    _patch_problems(monkeypatch, problems)
    generation_config = _config(tmp_path, name="generation-machine")
    verification_config = _config(tmp_path, name="verification-machine")
    output_root = tmp_path / "outputs"

    bundle = run_generation_bundle(
        config=generation_config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE")]),
        run_id="portable",
        output_root=output_root,
        seed=42,
    )
    resolved_text = (bundle.run_dir / "resolved_config.yaml").read_text(encoding="utf-8")
    assert str(generation_config.dataset_dir) not in resolved_text
    assert str(generation_config.piston_config) not in resolved_text

    identity, rows = load_completed_generation_bundle(
        bundle.run_dir,
        config=verification_config,
        problems=problems,
        seed=42,
    )
    assert identity.run_id == "portable"
    assert identity.total_problems == 1
    assert len(rows) == 1


def test_completed_bundle_rejects_generation_payload_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem("p1", "ONE")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    bundle = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ORIGINAL")]),
        run_id="tamper",
        output_root=tmp_path / "outputs",
        seed=42,
    )
    generations = bundle.records_path
    generations.write_text(generations.read_text(encoding="utf-8").replace("ORIGINAL", "TAMPERED"), encoding="utf-8")

    with pytest.raises(EvaluationError, match="hash mismatch"):
        load_completed_generation_bundle(bundle.run_dir, config=config, problems=problems, seed=42)


def test_verification_resume_preserves_ordered_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE"), _problem("p2", "TWO")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    bundle = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE"), _completion("TWO")]),
        run_id="verify-resume",
        output_root=output_root,
        seed=42,
    )
    calls = 0

    def flaky_factory() -> _PassExecutor:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("verification stop")
        return _PassExecutor()

    with pytest.raises(RuntimeError, match="verification stop"):
        run_verification_from_generation_bundle(
            config=config,
            generation_run_dir=bundle.run_dir,
            executor_factory=flaky_factory,
            run_id="verify-resume",
            output_root=output_root,
            seed=42,
            workers=1,
        )
    partial_path = output_root / "evaluation" / "verify-resume" / "samples" / "results.jsonl"
    assert [row.problem_id for row in load_evaluation_records(partial_path)] == ["p1"]

    resumed = run_verification_from_generation_bundle(
        config=config,
        generation_run_dir=bundle.run_dir,
        executor_factory=_PassExecutor,
        run_id="verify-resume",
        output_root=output_root,
        seed=42,
        workers=1,
    )
    assert resumed.completed_before_run == 1
    assert resumed.verified_this_run == 1
    assert [row.problem_id for row in load_evaluation_records(resumed.results_path)] == ["p1", "p2"]


def test_verification_workers_are_concurrent_ordered_and_aggregatable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = [_problem(f"p{index}", f"M{index}") for index in range(4)]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    bundle = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion(f"M{index}") for index in range(4)]),
        run_id="concurrent",
        output_root=output_root,
        seed=42,
    )
    tracker: dict[str, Any] = {"lock": threading.Lock(), "active": 0, "max_active": 0}
    verified = run_verification_from_generation_bundle(
        config=config,
        generation_run_dir=bundle.run_dir,
        executor_factory=lambda: _ConcurrentPassExecutor(tracker),
        run_id="concurrent",
        output_root=output_root,
        seed=42,
        workers=4,
    )
    assert int(tracker["max_active"]) >= 2
    rows = load_evaluation_records(verified.results_path)
    assert [row.problem_id for row in rows] == [problem.problem_id for problem in problems]
    aggregate = aggregate_evaluation_run(verified.results_path.parents[1], bootstrap_seed=42, bootstrap_resamples=100)
    assert aggregate.total_problems == 4
    assert aggregate.aggregate.metrics.eval_hidden_pass_at_1 == 1.0


def test_generation_non_sample_artifacts_remain_payload_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "SECRET_MARKER")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    bundle = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("COMPLETION_MARKER")]),
        run_id="payload-boundary",
        output_root=tmp_path / "outputs",
        seed=42,
    )
    non_sample = "\n".join(
        (bundle.run_dir / name).read_text(encoding="utf-8")
        for name in (
            "run.json",
            "resolved_config.yaml",
            "environment.json",
            "metrics.jsonl",
            "stdout.log",
            "stderr.log",
        )
    )
    assert "COMPLETION_MARKER" not in non_sample
    assert "SECRET_MARKER" not in non_sample


def test_verification_rejects_generation_code_identity_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = [_problem("p1", "ONE")]
    _patch_problems(monkeypatch, problems)
    config = _config(tmp_path)
    output_root = tmp_path / "outputs"
    bundle = run_generation_bundle(
        config=config,
        model_id="example/model",
        generator=_SequenceGenerator([_completion("ONE")]),
        run_id="identity-drift",
        output_root=output_root,
        seed=42,
    )
    original_collect = collect_environment

    def drifted_environment() -> dict[str, object]:
        environment = dict(original_collect())
        environment["dependency_lock_hash"] = "different-lock"
        return environment

    monkeypatch.setattr("code_verifier.evaluation.staged.collect_environment", drifted_environment)
    with pytest.raises(EvaluationError, match="verification code identity"):
        run_verification_from_generation_bundle(
            config=config,
            generation_run_dir=bundle.run_dir,
            executor_factory=_PassExecutor,
            run_id="identity-drift",
            output_root=output_root,
            seed=42,
            workers=1,
        )
