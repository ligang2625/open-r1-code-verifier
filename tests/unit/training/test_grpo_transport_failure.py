"""GRPO bounded retry and fail-closed regressions for Piston infrastructure failures."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from code_verifier.execution import ExecutionInfrastructureFailureKind, ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training import grpo as grpo_module
from code_verifier.training.grpo import GRPOTrainingError, build_grpo_reward_callback, run_grpo_training
from tests.unit.training.test_grpo import _passing_results, _prepare_fake_grpo_run


def _sandbox_result(
    *,
    stderr: str = "piston transport failed",
    kind: ExecutionInfrastructureFailureKind | None = ExecutionInfrastructureFailureKind.PISTON_TRANSPORT,
) -> ExecutionResult:
    return ExecutionResult(
        status=ExecutionStatus.SANDBOX_ERROR,
        passed_tests=0,
        total_tests=1,
        pass_rate=0.0,
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(
                status=ExecutionStatus.SANDBOX_ERROR,
                passed=False,
                runtime_ms=1.0,
                stdout="",
                stderr=stderr,
                infrastructure_failure_kind=kind,
            )
        ],
    )


def _passed_result() -> ExecutionResult:
    return ExecutionResult(
        status=ExecutionStatus.PASSED,
        passed_tests=1,
        total_tests=1,
        pass_rate=1.0,
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(
                status=ExecutionStatus.PASSED,
                passed=True,
                runtime_ms=1.0,
                stdout="",
                stderr="",
            )
        ],
    )


class _RetryingMockExecutor(MockExecutor):
    def __init__(self, results: list[ExecutionResult]) -> None:
        super().__init__(results)
        self.prepare_calls = 0

    def prepare_infrastructure_retry(self) -> str:
        self.prepare_calls += 1
        return "3.10.0"


class _FailingPrepareExecutor(_RetryingMockExecutor):
    def prepare_infrastructure_retry(self) -> str:
        self.prepare_calls += 1
        raise RuntimeError("runtime health unavailable")


def _callback(
    tmp_path: Path,
    executor: MockExecutor,
    *,
    telemetry: grpo_module._RewardInfrastructureRetryTelemetry | None = None,
) -> Callable[..., list[float]]:
    return build_grpo_reward_callback(
        reward_mode="public",
        executor=executor,
        rollout_log_path=tmp_path / "rollouts.jsonl",
        reward_log_path=tmp_path / "rewards.jsonl",
        group_metrics_log_path=tmp_path / "groups.jsonl",
        num_generations=1,
        max_completion_length=16,
        operational_log_path=tmp_path / "stdout.log",
        retry_sleep=lambda _seconds: None,
        retry_telemetry=telemetry,
    )


def _invoke(callback: Callable[..., list[float]]) -> list[float]:
    metadata = {
        "difficulty": "easy",
        "category": ["unit"],
        "time_limit_seconds": 1.0,
        "memory_limit_mb": 128,
        "license": "test",
        "source_url_hash": None,
    }
    completion = chr(96) * 3 + "python\ndef solve(value): return value\n" + chr(96) * 3
    return callback(
        prompts=[[{"role": "user", "content": "prompt"}]],
        completions=[completion],
        completion_ids=[[1]],
        problem_id=["problem-1"],
        function_name=["solve"],
        metadata=[metadata],
        visible_tests=[[json.dumps({"input": 1, "expected": 1})]],
    )


def test_transport_infrastructure_failure_is_retried_in_process_with_same_request(tmp_path: Path) -> None:
    executor = _RetryingMockExecutor([_sandbox_result(), _passed_result()])
    telemetry = grpo_module._RewardInfrastructureRetryTelemetry()
    callback = _callback(tmp_path, executor, telemetry=telemetry)

    assert _invoke(callback) == [1.1]
    assert len(executor.calls) == 2
    assert executor.calls[0] == executor.calls[1]
    assert executor.prepare_calls == 1
    reward_rows = [json.loads(line) for line in (tmp_path / "rewards.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(reward_rows) == 1
    assert reward_rows[0]["infrastructure_failure"] is False
    assert reward_rows[0]["total_reward"] == 1.1
    retry_rows = [json.loads(line) for line in (tmp_path / "stdout.log").read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in retry_rows] == [
        "grpo_reward_infrastructure_retry_scheduled",
        "grpo_reward_infrastructure_retry_succeeded",
    ]
    assert all(row["failure_kind"] == "piston_transport" for row in retry_rows)
    assert all("completion" not in row and "tests" not in row for row in retry_rows)
    assert telemetry.to_mapping() == {
        "policy_version": "grpo-reward-infra-retry-v2",
        "max_retries_per_reward_item": 3,
        "backoff_seconds": [1.0, 2.0, 4.0],
        "retry_attempts": 1,
        "retry_successes": 1,
        "retry_exhausted": 0,
        "recovery_prepare_failures": 0,
    }


def test_piston_internal_infrastructure_failure_is_retried_in_process(tmp_path: Path) -> None:
    executor = _RetryingMockExecutor(
        [
            _sandbox_result(
                stderr="piston internal execution failed",
                kind=ExecutionInfrastructureFailureKind.PISTON_INTERNAL,
            ),
            _passed_result(),
        ]
    )
    telemetry = grpo_module._RewardInfrastructureRetryTelemetry()
    callback = _callback(tmp_path, executor, telemetry=telemetry)

    assert _invoke(callback) == [1.1]
    assert len(executor.calls) == 2
    assert executor.calls[0] == executor.calls[1]
    assert executor.prepare_calls == 1
    retry_rows = [json.loads(line) for line in (tmp_path / "stdout.log").read_text(encoding="utf-8").splitlines()]
    assert [row["failure_kind"] for row in retry_rows] == [
        "piston_internal",
        "piston_internal",
    ]
    assert telemetry.retry_attempts == 1
    assert telemetry.retry_successes == 1


@pytest.mark.parametrize(
    "kind",
    [
        ExecutionInfrastructureFailureKind.PISTON_RESPONSE_PROTOCOL,
        ExecutionInfrastructureFailureKind.HARNESS_PROTOCOL,
    ],
)
def test_protocol_infrastructure_failure_is_retried_in_process(
    tmp_path: Path,
    kind: ExecutionInfrastructureFailureKind,
) -> None:
    executor = _RetryingMockExecutor(
        [_sandbox_result(stderr="sanitized protocol failure", kind=kind), _passed_result()]
    )
    callback = _callback(tmp_path, executor)

    assert _invoke(callback) == [1.1]
    assert executor.calls[0] == executor.calls[1]
    assert executor.prepare_calls == 1
    retry_rows = [json.loads(line) for line in (tmp_path / "stdout.log").read_text(encoding="utf-8").splitlines()]
    assert all(row["failure_kind"] == kind.value for row in retry_rows)


def test_retry_success_does_not_trip_circuit_breaker_for_later_completion(tmp_path: Path) -> None:
    executor = _RetryingMockExecutor(
        [
            _sandbox_result(
                stderr="invalid harness report",
                kind=ExecutionInfrastructureFailureKind.HARNESS_PROTOCOL,
            ),
            _passed_result(),
            _passed_result(),
        ]
    )
    callback = build_grpo_reward_callback(
        reward_mode="public",
        executor=executor,
        rollout_log_path=tmp_path / "rollouts.jsonl",
        reward_log_path=tmp_path / "rewards.jsonl",
        group_metrics_log_path=tmp_path / "groups.jsonl",
        num_generations=2,
        max_completion_length=16,
        operational_log_path=tmp_path / "stdout.log",
        retry_sleep=lambda _seconds: None,
    )
    metadata = {
        "difficulty": "easy",
        "category": ["unit"],
        "time_limit_seconds": 1.0,
        "memory_limit_mb": 128,
        "license": "test",
        "source_url_hash": None,
    }
    completion = chr(96) * 3 + "python\ndef solve(value): return value\n" + chr(96) * 3

    rewards = callback(
        prompts=[[{"role": "user", "content": "prompt"}]] * 2,
        completions=[completion, completion],
        completion_ids=[[1], [1]],
        problem_id=["problem-1", "problem-1"],
        function_name=["solve", "solve"],
        metadata=[metadata, metadata],
        visible_tests=[
            [json.dumps({"input": 1, "expected": 1})],
            [json.dumps({"input": 2, "expected": 2})],
        ],
    )

    assert rewards == [1.1, 1.1]
    assert len(executor.calls) == 3
    assert executor.calls[0] == executor.calls[1]
    assert executor.calls[2].tests == [{"input": 2, "expected": 2}]
    reward_rows = [json.loads(line) for line in (tmp_path / "rewards.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(reward_rows) == 2
    assert all(row["infrastructure_failure"] is False for row in reward_rows)
    assert all(row["infrastructure_failure_kind"] is None for row in reward_rows)
    retry_rows = [json.loads(line) for line in (tmp_path / "stdout.log").read_text(encoding="utf-8").splitlines()]
    assert [row["failure_kind"] for row in retry_rows] == ["harness_protocol", "harness_protocol"]


def test_unrecovered_transport_infrastructure_failure_aborts_before_update_after_bounded_retries(
    tmp_path: Path,
) -> None:
    executor = _RetryingMockExecutor([_sandbox_result() for _ in range(4)])
    telemetry = grpo_module._RewardInfrastructureRetryTelemetry()
    callback = _callback(tmp_path, executor, telemetry=telemetry)

    with pytest.raises(GRPOTrainingError, match="aborting before optimizer update"):
        _invoke(callback)
    assert len(executor.calls) == 4
    assert executor.prepare_calls == 3
    reward_rows = [json.loads(line) for line in (tmp_path / "rewards.jsonl").read_text(encoding="utf-8").splitlines()]
    assert reward_rows[0]["infrastructure_failure"] is True
    assert reward_rows[0]["total_reward"] == 0.0
    retry_rows = [json.loads(line) for line in (tmp_path / "stdout.log").read_text(encoding="utf-8").splitlines()]
    assert retry_rows[-1]["event"] == "grpo_reward_infrastructure_retry_exhausted"
    assert retry_rows[-1]["retries"] == 3
    assert telemetry.retry_attempts == 3
    assert telemetry.retry_successes == 0
    assert telemetry.retry_exhausted == 1


def test_unclassified_sandbox_failure_is_not_retried(tmp_path: Path) -> None:
    executor = _RetryingMockExecutor([_sandbox_result(stderr="unclassified sandbox failure", kind=None)])
    callback = _callback(tmp_path, executor)

    with pytest.raises(GRPOTrainingError, match="aborting before optimizer update"):
        _invoke(callback)
    assert len(executor.calls) == 1
    assert executor.prepare_calls == 0
    assert not (tmp_path / "stdout.log").exists()


def test_runtime_health_prepare_failure_is_bounded_and_fails_closed(tmp_path: Path) -> None:
    executor = _FailingPrepareExecutor([_sandbox_result()])
    telemetry = grpo_module._RewardInfrastructureRetryTelemetry()
    callback = _callback(tmp_path, executor, telemetry=telemetry)

    with pytest.raises(GRPOTrainingError, match="aborting before optimizer update"):
        _invoke(callback)

    assert len(executor.calls) == 1
    assert executor.prepare_calls == 3
    assert telemetry.retry_attempts == 3
    assert telemetry.retry_successes == 0
    assert telemetry.retry_exhausted == 1
    assert telemetry.recovery_prepare_failures == 3
    retry_rows = [json.loads(line) for line in (tmp_path / "stdout.log").read_text(encoding="utf-8").splitlines()]
    assert sum(row["event"] == "grpo_reward_infrastructure_retry_prepare_failed" for row in retry_rows) == 3
    assert retry_rows[-1]["event"] == "grpo_reward_infrastructure_retry_exhausted"


def test_completed_training_attempt_durably_records_retry_counters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_config, hidden_config, sft_run_dir, output_root = _prepare_fake_grpo_run(tmp_path, monkeypatch)
    executor = _RetryingMockExecutor([_sandbox_result(), *_passing_results(4)])

    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode="public",
        public_sft_run_dir=sft_run_dir,
        hidden_sft_run_dir=sft_run_dir,
        output_root=output_root,
        seed=42,
        executor=executor,
    )

    metadata = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    retry = metadata["attempts"][-1]["reward_infrastructure_retry"]
    assert retry["retry_attempts"] == 1
    assert retry["retry_successes"] == 1
    assert retry["retry_exhausted"] == 0
    assert retry["recovery_prepare_failures"] == 0


def test_retry_v2_accepts_v1_attempt_and_migration_history() -> None:
    commit = "a" * 40
    resume_source = "checkpoints/checkpoint-125"
    attempts = [
        {
            "attempt": 1,
            "status": "failed",
            "code_commit": commit,
            "resume_from_checkpoint": resume_source,
            "code_migration": {
                "compatibility_class": "operational_reward_resilience_v1",
                "from_commit": "b" * 40,
                "to_commit": commit,
                "resume_from_checkpoint": resume_source,
                "scientific_change": False,
                "reason": "legacy operational reward resilience repair",
                "reward_infrastructure_retry_policy_version": "grpo-reward-infra-retry-v1",
            },
            "reward_infrastructure_retry": {
                "policy_version": "grpo-reward-infra-retry-v1",
                "max_retries_per_reward_item": 3,
                "backoff_seconds": [1.0, 2.0, 4.0],
                "retry_attempts": 0,
                "retry_successes": 0,
                "retry_exhausted": 0,
                "recovery_prepare_failures": 0,
            },
            "gpu_hours": 1.25,
            "end_time": "2026-08-29T00:00:00+00:00",
        }
    ]

    assert grpo_module._attempt_gpu_hours_total(attempts) == pytest.approx(1.25)


def test_retry_metadata_accepts_mixed_v1_v2_attempt_history_and_new_attempt_writes_v2() -> None:
    legacy = {
        "attempt": 1,
        "status": "failed",
        "code_commit": "a" * 40,
        "resume_from_checkpoint": None,
        "reward_infrastructure_retry": {
            "policy_version": "grpo-reward-infra-retry-v1",
            "max_retries_per_reward_item": 3,
            "backoff_seconds": [1.0, 2.0, 4.0],
            "retry_attempts": 0,
            "retry_successes": 0,
            "retry_exhausted": 0,
            "recovery_prepare_failures": 0,
        },
        "gpu_hours": 0.5,
        "end_time": "2026-08-29T00:00:00+00:00",
    }
    run_metadata: dict[str, object] = {"attempts": [legacy]}

    grpo_module._begin_attempt(
        run_metadata,
        resume_source="checkpoints/checkpoint-125",
        code_commit="b" * 40,
    )

    attempts = run_metadata["attempts"]
    assert isinstance(attempts, list)
    assert attempts[1]["reward_infrastructure_retry"]["policy_version"] == "grpo-reward-infra-retry-v2"
    grpo_module._finish_attempt(run_metadata, status="completed", attempt_gpu_hours=0.25)
    assert grpo_module._attempt_gpu_hours_total(attempts) == pytest.approx(0.75)


def test_retry_metadata_rejects_unknown_policy_version() -> None:
    attempts = [
        {
            "attempt": 1,
            "status": "failed",
            "code_commit": "a" * 40,
            "resume_from_checkpoint": None,
            "reward_infrastructure_retry": {
                "policy_version": "grpo-reward-infra-retry-v999",
                "max_retries_per_reward_item": 3,
                "backoff_seconds": [1.0, 2.0, 4.0],
                "retry_attempts": 0,
                "retry_successes": 0,
                "retry_exhausted": 0,
                "recovery_prepare_failures": 0,
            },
            "gpu_hours": 0.0,
            "end_time": "2026-08-29T00:00:00+00:00",
        }
    ]

    with pytest.raises(GRPOTrainingError, match="policy version is invalid"):
        grpo_module._attempt_gpu_hours_total(attempts)
