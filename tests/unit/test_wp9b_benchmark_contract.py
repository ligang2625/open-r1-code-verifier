from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

import code_verifier.training.grpo as grpo_module
from code_verifier import throughput
from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.execution import MockExecutor
from code_verifier.throughput import ThroughputError
from code_verifier.training.grpo import GRPOBenchmarkBinding, GRPOTrainingConfig, run_grpo_training
from code_verifier.training.sft import SFTCheckpointIdentity, load_completed_sft_checkpoint
from tests.unit.training.test_grpo import _passing_results, _prepare_fake_grpo_run

_CALIBRATION_ARTIFACTS = {
    "records/calibration.jsonl",
    "manifest/retry_problem_ids.jsonl",
    "manifest/active_selection.jsonl",
    "manifest/problem_order.jsonl",
    "manifest/reserve_problem_ids.jsonl",
    "manifest/hard_problem_ids.jsonl",
    "manifest/easy_problem_ids.jsonl",
    "reports/classification_summary.json",
    "reports/pool_composition.json",
    "training/public_grpo.jsonl",
    "training/hidden_grpo.jsonl",
}


def _probe(
    path: Path,
    *,
    workers: int,
    role: str,
    group_size: int,
    diagnostic_identity: str = "d" * 64,
    reward_mode: str = "public",
    throughput_per_second: float = 1.0,
    group_count: int = 10,
    reward_count: int | None = None,
    zero_variance_groups: int = 4,
    useful_groups_per_gpu_hour: float = 100.0,
    retry_attempts: int = 0,
) -> throughput._GRPOProbe:
    start = datetime(2026, 9, 2, tzinfo=timezone.utc)
    return throughput._GRPOProbe(
        path=path,
        workers=workers,
        reward_mode=reward_mode,
        duration_seconds=10.0,
        throughput_per_second=throughput_per_second,
        scientific_identity_sha256="a" * 64,
        reward_parity_sha256="b" * 64,
        group_parity_sha256="c" * 64,
        paired_definition_sha256=("4" if workers == 8 else "5") * 64,
        run_manifest_sha256="f" * 64,
        retry_exhausted=0,
        recovery_prepare_failures=0,
        peak_cuda_memory_reserved_bytes=1024,
        mean_verifier_runtime_seconds=0.1,
        p95_verifier_runtime_seconds=0.2,
        runtime_utilization=None,
        start_time=start,
        end_time=start,
        reward_count=group_size * group_count if reward_count is None else reward_count,
        group_count=group_count,
        rollout_count=group_size * group_count if reward_count is None else reward_count,
        benchmark_role=role,
        group_size=group_size,
        diagnostic_identity_sha256=diagnostic_identity,
        active_order_sha256="8" * 64,
        problem_order_sha256="9" * 64,
        problem_count=group_count,
        generated_tokens=group_size * group_count * 5,
        tokens_per_second=float(group_size * group_count) / 2.0,
        verifier_request_count=group_size * group_count,
        verifier_runtime_seconds=1.0,
        retry_attempts=retry_attempts,
        oom_count=0,
        infrastructure_error_count=0,
        zero_variance_group_count=zero_variance_groups,
        informative_group_count=group_count - zero_variance_groups,
        gpu_hours=0.1,
        useful_nonzero_variance_groups_per_gpu_hour=useful_groups_per_gpu_hour,
        calibration_manifest_sha256="6" * 64,
        active_public_training_sha256="7" * 64,
        active_hidden_training_sha256="a" * 64,
    )


def _prepare_formal_benchmark_inputs(
    tmp_path: Path,
    public_config: GRPOTrainingConfig,
    hidden_config: GRPOTrainingConfig,
    parent: SFTCheckpointIdentity,
    *,
    group_size: int,
) -> tuple[GRPOTrainingConfig, GRPOTrainingConfig, Path]:
    root = tmp_path / "calibration"
    training = root / "training"
    training.mkdir(parents=True)
    configured: dict[str, GRPOTrainingConfig] = {}
    for reward_mode, source_config in (("public", public_config), ("hidden", hidden_config)):
        record = json.loads(source_config.dataset_path.read_text(encoding="utf-8"))
        metadata = cast(dict[str, object], record["metadata"])
        metadata["calibration_class"] = "dual_informative"
        target = training / f"{reward_mode}_grpo.jsonl"
        target.write_text(json.dumps(record) + "\n", encoding="utf-8")
        configured[reward_mode] = replace(source_config, dataset_path=target, num_generations=group_size)

    for relative in sorted(_CALIBRATION_ARTIFACTS - {"training/public_grpo.jsonl", "training/hidden_grpo.jsonl"}):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    artifacts = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(_CALIBRATION_ARTIFACTS)
    }
    parent_core = {
        "run_id": parent.run_id,
        "model_id": parent.model_id,
        "model_revision": parent.model_revision,
        "dataset_hash": parent.dataset_hash,
        "config_hash": parent.config_hash,
        "dependency_lock_hash": parent.dependency_lock_hash,
        "seed": parent.seed,
    }
    calibration = {
        "schema_version": "wp9b-calibration-v1",
        "status": "completed",
        "evidence_class": "formal_calibration",
        "seed": 42,
        "active_order_sha256": stable_json_hash(["grpo-1"]),
        "sft_checkpoint": {**parent_core, "checkpoint_sha256": throughput._stable_hash(parent_core)},
        "artifacts": artifacts,
    }
    manifest = root / "calibration_manifest.json"
    manifest.write_text(json.dumps(calibration, sort_keys=True), encoding="utf-8")
    return configured["public"], configured["hidden"], manifest


def _complete_strict_benchmark_fixture(run_dir: Path, parent: SFTCheckpointIdentity) -> None:
    checkpoint_dir = run_dir / "checkpoints"
    (checkpoint_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": parent.model_id, "revision": parent.model_revision}),
        encoding="utf-8",
    )
    (checkpoint_dir / "adapter_model.safetensors").write_bytes(b"strict-benchmark-fixture")
    environment_path = run_dir / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment["bf16_supported"] = True
    environment_path.write_text(json.dumps(environment, sort_keys=True), encoding="utf-8")


def test_strict_active_pool_paths_accept_public_and_hidden_arms(tmp_path: Path) -> None:
    training = tmp_path / "training"
    training.mkdir()
    public = training / "public_grpo.jsonl"
    hidden = training / "hidden_grpo.jsonl"
    public.write_text("{}\n", encoding="utf-8")
    hidden.write_text("{}\n", encoding="utf-8")

    assert throughput._strict_active_pool_paths(public, reward_mode="public") == (public, hidden)
    assert throughput._strict_active_pool_paths(hidden, reward_mode="hidden") == (public, hidden)

    wrong = training / "wrong.jsonl"
    wrong.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ThroughputError, match="selected dataset path"):
        throughput._strict_active_pool_paths(wrong, reward_mode="hidden")


def test_strict_k8_worker_sweep_ignores_candidate_worker_in_scientific_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "baseline"
    candidate_16 = tmp_path / "candidate-16"
    candidate_32 = tmp_path / "candidate-32"
    probes = {
        baseline_path: _probe(baseline_path, workers=8, role="k8_candidate", group_size=8),
        candidate_16: _probe(
            candidate_16,
            workers=16,
            role="k8_candidate",
            group_size=8,
            throughput_per_second=3.0,
        ),
        candidate_32: _probe(
            candidate_32,
            workers=32,
            role="k8_candidate",
            group_size=8,
            throughput_per_second=2.0,
        ),
    }
    expected_roles: list[str | None] = []

    def fake_probe(path: Path, **kwargs: object) -> throughput._GRPOProbe:
        assert kwargs["strict_source"] is True
        expected_role = kwargs.get("expected_role")
        expected_roles.append(expected_role if isinstance(expected_role, str) else None)
        return probes[path]

    monkeypatch.setattr(throughput, "_grpo_probe", fake_probe)

    selected, report = throughput._select_grpo_verification(
        {"baseline": str(baseline_path), "candidates": [str(candidate_16), str(candidate_32)]},
        strict_source=True,
    )

    report_any = cast(Any, report)
    assert selected == 16
    assert expected_roles == ["k8_candidate", "k8_candidate", "k8_candidate"]
    assert report_any["candidates"][0]["rejection"] is None


def test_k4_k8_diagnostic_reports_raw_work_without_selecting_k4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    k4 = _probe(
        tmp_path / "k4",
        workers=16,
        role="k4_diagnostic",
        group_size=4,
        group_count=10,
        reward_count=40,
        zero_variance_groups=4,
        useful_groups_per_gpu_hour=100.0,
    )
    k8 = _probe(
        tmp_path / "k8",
        workers=16,
        role="k8_candidate",
        group_size=8,
        group_count=10,
        reward_count=80,
        zero_variance_groups=2,
        useful_groups_per_gpu_hour=90.0,
    )

    def fake_probe(path: Path, **kwargs: object) -> throughput._GRPOProbe:
        del path
        role = kwargs.get("expected_role")
        return k4 if role == "k4_diagnostic" else k8

    monkeypatch.setattr(throughput, "_grpo_probe", fake_probe)
    report = throughput._grpo_group_size_diagnostic(
        {"k4": str(k4.path), "k8": str(k8.path)},
        require_formal_telemetry=True,
        strict_source=True,
    )

    report_any = cast(Any, report)
    assert report_any["primary_protocol"] == "k8"
    assert report_any["reconsider_k8"] is False
    assert report_any["k4"]["sample_count"] == 40
    assert report_any["k8"]["sample_count"] == 80
    assert report_any["k4"]["generated_tokens"] == k4.generated_tokens
    assert report_any["k8"]["tokens_per_second"] == k8.tokens_per_second


@pytest.mark.parametrize(
    ("confound", "match"),
    [
        ("reward", "reward arm"),
        ("workers", "verification runtime"),
        ("identity", "scientific identity"),
        ("active_order", "active-pool order"),
        ("problem_order", "problem/order workset"),
    ],
)
def test_k4_k8_diagnostic_rejects_identity_confounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    confound: str,
    match: str,
) -> None:
    k4 = _probe(tmp_path / "k4", workers=16, role="k4_diagnostic", group_size=4)
    k8 = _probe(tmp_path / "k8", workers=16, role="k8_candidate", group_size=8)
    if confound == "reward":
        k8 = replace(k8, reward_mode="hidden")
    elif confound == "workers":
        k8 = replace(k8, workers=32)
    elif confound == "identity":
        k8 = replace(k8, diagnostic_identity_sha256="e" * 64)
    elif confound == "active_order":
        k8 = replace(k8, active_order_sha256="e" * 64)
    else:
        k8 = replace(k8, problem_order_sha256="e" * 64)

    def fake_probe(path: Path, **kwargs: object) -> throughput._GRPOProbe:
        del path
        return k4 if kwargs.get("expected_role") == "k4_diagnostic" else k8

    monkeypatch.setattr(throughput, "_grpo_probe", fake_probe)
    with pytest.raises(ThroughputError, match=match):
        throughput._grpo_group_size_diagnostic(
            {"k4": str(k4.path), "k8": str(k8.path)},
            require_formal_telemetry=True,
            strict_source=True,
        )


def test_k4_k8_diagnostic_warns_but_keeps_k8_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    k4 = _probe(
        tmp_path / "k4",
        workers=16,
        role="k4_diagnostic",
        group_size=4,
        group_count=100,
        zero_variance_groups=20,
        useful_groups_per_gpu_hour=100.0,
    )
    k8 = _probe(
        tmp_path / "k8",
        workers=16,
        role="k8_candidate",
        group_size=8,
        group_count=100,
        zero_variance_groups=17,
        useful_groups_per_gpu_hour=80.0,
        retry_attempts=1,
    )

    def fake_probe(path: Path, **kwargs: object) -> throughput._GRPOProbe:
        del path
        return k4 if kwargs.get("expected_role") == "k4_diagnostic" else k8

    monkeypatch.setattr(throughput, "_grpo_probe", fake_probe)
    report = throughput._grpo_group_size_diagnostic(
        {"k4": str(k4.path), "k8": str(k8.path)},
        require_formal_telemetry=True,
        strict_source=True,
    )

    report_any = cast(Any, report)
    assert report_any["primary_protocol"] == "k8"
    assert report_any["reconsider_k8"] is True
    assert set(report_any["warning_reasons"]) == {
        "k4_already_informative_k8_small_variance_gain",
        "k8_useful_groups_per_gpu_hour_regression",
        "k8_infrastructure_instability_observed",
    }


@pytest.mark.parametrize(
    ("reward_mode", "role", "group_size"),
    [
        ("public", "k8_candidate", 8),
        ("hidden", "k8_candidate", 8),
        ("public", "k4_diagnostic", 4),
    ],
)
def test_actual_benchmark_training_is_a_positive_strict_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reward_mode: str,
    role: str,
    group_size: int,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    parent = load_completed_sft_checkpoint(sft_run_dir)
    public_config, hidden_config, calibration_manifest = _prepare_formal_benchmark_inputs(
        tmp_path,
        public_config,
        hidden_config,
        parent,
        group_size=group_size,
    )
    binding = GRPOBenchmarkBinding(
        calibration_manifest_path=calibration_manifest,
        calibration_manifest_sha256=hashlib.sha256(calibration_manifest.read_bytes()).hexdigest(),
        active_order_sha256=stable_json_hash(["grpo-1"]),
        public_training_sha256=grpo_module._file_hash(public_config.dataset_path, description="fixture Public"),
        hidden_training_sha256=grpo_module._file_hash(hidden_config.dataset_path, description="fixture Hidden"),
        verification_workers=8,
        role=role,
    )

    utilization = {
        "version": "wp9b-runtime-utilization-v1",
        "status": "available",
        "sample_interval_seconds": 1.0,
        "sample_count": 1,
        "sample_error_count": 0,
        "last_error_type": None,
        "host_cpu_count": 8,
        "host_max_rss_mib": 256.0,
        "gpu_utilization_mean_percent": 50.0,
        "gpu_utilization_p95_percent": 50.0,
        "gpu_memory_used_mean_mib": 8000.0,
        "gpu_memory_used_p95_mib": 8000.0,
        "gpu_memory_used_max_mib": 8000.0,
    }

    class FakeSampler:
        def start(self) -> None:
            return None

        def stop(self) -> dict[str, object]:
            return dict(utilization)

    monkeypatch.setattr(grpo_module, "RuntimeUtilizationSampler", FakeSampler)
    monkeypatch.setattr(grpo_module, "_install_grpo_runtime_telemetry", lambda *args, **kwargs: None)

    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode=reward_mode,
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=MockExecutor(_passing_results(group_size)),
        executor_factory=lambda: MockExecutor(_passing_results(group_size)),
        verification_workers=8,
        benchmark_binding=binding,
    )
    _complete_strict_benchmark_fixture(summary.run_dir, parent)

    run_metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["paired_definition_version"] == 4
    assert run_metadata["benchmark_source_version"] == 1
    assert run_metadata["benchmark_role"] == role
    assert run_metadata["verification_workers"] == 8
    assert "benchmark_report_sha256" not in run_metadata
    assert "refresh_binding_version" not in run_metadata

    probe = throughput._grpo_probe(
        summary.run_dir,
        require_formal_telemetry=True,
        strict_source=True,
        expected_role=role,
    )
    assert probe.benchmark_role == role
    assert probe.group_size == group_size
    assert probe.reward_mode == reward_mode
    assert probe.reward_count == group_size
    assert probe.group_count == 1
    assert probe.generated_tokens == 2 * group_size
