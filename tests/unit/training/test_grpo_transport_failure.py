"""GRPO fail-closed regression for unrecovered Piston infrastructure failures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_verifier.execution import ExecutionResult, ExecutionStatus, MockExecutor
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult
from code_verifier.training.grpo import GRPOTrainingError, build_grpo_reward_callback


def _sandbox_result() -> ExecutionResult:
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
                stderr="piston transport failed",
            )
        ],
    )


def test_unrecovered_transport_infrastructure_failure_aborts_reward_callback_before_update(tmp_path: Path) -> None:
    executor = MockExecutor([_sandbox_result()])
    callback = build_grpo_reward_callback(
        reward_mode="public",
        executor=executor,
        rollout_log_path=tmp_path / "rollouts.jsonl",
        reward_log_path=tmp_path / "rewards.jsonl",
        group_metrics_log_path=tmp_path / "groups.jsonl",
        num_generations=1,
        max_completion_length=16,
    )
    metadata = {
        "difficulty": "easy",
        "category": ["unit"],
        "time_limit_seconds": 1.0,
        "memory_limit_mb": 128,
        "license": "test",
        "source_url_hash": None,
    }
    with pytest.raises(GRPOTrainingError, match="aborting before optimizer update"):
        callback(
            prompts=[[{"role": "user", "content": "prompt"}]],
            completions=["```python\ndef solve(value): return value\n```"],
            completion_ids=[[1]],
            problem_id=["problem-1"],
            function_name=["solve"],
            metadata=[metadata],
            visible_tests=[[json.dumps({"input": 1, "expected": 1})]],
        )
    assert len(executor.calls) == 1
    reward_rows = [json.loads(line) for line in (tmp_path / "rewards.jsonl").read_text(encoding="utf-8").splitlines()]
    assert reward_rows[0]["infrastructure_failure"] is True
    assert reward_rows[0]["total_reward"] == 0.0
