"""WP3-c batch, cache, CLI, and explicit real-Piston integration acceptance."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from code_verifier import cli as cli_module
from code_verifier.cli import main
from code_verifier.execution import (
    BatchExecutionRequest,
    BatchExecutor,
    BatchExecutorConfig,
    CodeExecutor,
    ExecutionCacheMode,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTestLayer,
    ExecutionWorkloadMode,
    PistonExecutor,
    PistonTransportError,
    SQLiteExecutionCache,
    batch_execution_result_to_mapping,
    execution_result_to_mapping,
    load_piston_executor_config,
    piston_executor_version,
)
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult

_RUN_PISTON = os.environ.get("CODE_VERIFIER_RUN_PISTON") == "1"


def _request(
    request_id: str,
    code: str,
    *,
    input_value: object = 1,
    expected: object = 2,
    timeout_seconds: float = 1.0,
) -> BatchExecutionRequest:
    return BatchExecutionRequest(
        request_id=request_id,
        problem_id=f"problem-{request_id}",
        test_layer=ExecutionTestLayer.VISIBLE,
        code=code,
        function_name="target",
        tests=[{"input": input_value, "expected": expected}],
        timeout_seconds=timeout_seconds,
        memory_limit_mb=64,
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


class _CallbackExecutor:
    def __init__(self, callback: Callable[[str], ExecutionResult]) -> None:
        self._callback = callback

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        del function_name, tests, timeout_seconds, memory_limit_mb
        return self._callback(code)


def test_mock_batch_preserves_order_bounds_concurrency_and_reuses_cache(tmp_path: Path) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()
    factory_calls = 0

    def callback(code: str) -> ExecutionResult:
        nonlocal active, peak
        del code
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return _passed_result()

    def factory() -> CodeExecutor:
        nonlocal factory_calls
        factory_calls += 1
        return _CallbackExecutor(callback)

    requests = [_request(str(index), f"fixed-{index}") for index in range(4)]
    cache_path = tmp_path / "cache.sqlite3"
    with SQLiteExecutionCache(cache_path) as cache:
        first = BatchExecutor(
            factory,
            executor_version="executor-v1",
            config=BatchExecutorConfig(2, ExecutionCacheMode.READ_WRITE, False),
            cache=cache,
        ).execute_batch(requests)
        first_factory_calls = factory_calls
        second = BatchExecutor(
            factory,
            executor_version="executor-v1",
            config=BatchExecutorConfig(2, ExecutionCacheMode.READ_ONLY, False),
            cache=cache,
        ).execute_batch(requests)

    assert [item.request_id for item in first.items] == [str(index) for index in range(4)]
    assert peak == 2
    assert first.cache_hits == 0
    assert second.cache_hits == 4
    assert factory_calls == first_factory_calls == 4
    assert [execution_result_to_mapping(item.result) for item in second.items] == [
        execution_result_to_mapping(item.result) for item in first.items
    ]
    encoded = json.dumps(batch_execution_result_to_mapping(second), allow_nan=False)
    assert "fixed-" not in encoded


def test_execute_batch_cli_writes_desensitized_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePistonExecutor:
        def __init__(self, config: object) -> None:
            del config

        def validate_runtime(self) -> str:
            return "3.10.0"

        def execute(
            self,
            code: str,
            function_name: str,
            tests: list[dict[str, Any]],
            timeout_seconds: float,
            memory_limit_mb: int,
        ) -> ExecutionResult:
            del function_name, tests, timeout_seconds, memory_limit_mb
            if "raise RuntimeError" in code:
                status = ExecutionStatus.RUNTIME_ERROR
            elif "return value - 1" in code:
                status = ExecutionStatus.WRONG_ANSWER
            else:
                status = ExecutionStatus.PASSED
            passed = status is ExecutionStatus.PASSED
            return ExecutionResult(
                status=status,
                passed_tests=1 if passed else 0,
                total_tests=1,
                pass_rate=1.0 if passed else 0.0,
                runtime_ms=1.0,
                test_results=[
                    ExecutionTestCaseResult(
                        status=status,
                        passed=passed,
                        runtime_ms=1.0,
                        stdout="",
                        stderr="",
                    )
                ],
            )

    monkeypatch.setattr(cli_module, "PistonExecutor", FakePistonExecutor)
    monkeypatch.setattr(cli_module, "piston_executor_version", lambda config: "executor-v1")
    output = tmp_path / "output"
    assert (
        main(
            [
                "execute-batch",
                "--config",
                "configs/execution/batch-local.yaml",
                "--requests",
                "tests/fixtures/wp3c/batch_requests.jsonl",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    results = output.joinpath("results.jsonl").read_text(encoding="utf-8")
    summary = json.loads(output.joinpath("summary.json").read_text(encoding="utf-8"))
    assert len(results.splitlines()) == 4
    assert summary["status_counts"]["passed"] == 2
    assert summary["status_counts"]["wrong_answer"] == 1
    assert summary["status_counts"]["runtime_error"] == 1
    fixture = Path("tests/fixtures/wp3c/batch_requests.jsonl").read_text(encoding="utf-8")
    for line in fixture.splitlines():
        request = json.loads(line)
        assert request["code"] not in results
        assert json.dumps(request["tests"], sort_keys=True) not in results


def _real_piston_config_path() -> Path:
    value = os.environ.get("CODE_VERIFIER_PISTON_CONFIG")
    if not value:
        pytest.fail("CODE_VERIFIER_PISTON_CONFIG must identify the local Piston YAML")
    return Path(value)


def _real_requests() -> list[BatchExecutionRequest]:
    return [
        _request("correct-1", "def target(value):\n    return value + 1\n"),
        _request("correct-2", "def target(value):\n    return value * 2\n", input_value=3, expected=6),
        _request("correct-3", "def target(value):\n    return [value]\n", input_value="x", expected=["x"]),
        _request("wrong", "def target(value):\n    return value - 1\n"),
        _request("runtime", "def target(value):\n    raise RuntimeError('fixed')\n", expected=1),
        _request("timeout", "def target(value):\n    while True:\n        pass\n", expected=None, timeout_seconds=0.5),
    ]


def _assert_real_service_healthy(config_path: Path) -> None:
    config = load_piston_executor_config(config_path)
    executor = PistonExecutor(config)
    assert executor.validate_runtime() == config.version
    result = executor.execute(
        "def target(value):\n    return value + 1\n",
        "target",
        [{"input": 1, "expected": 2}],
        1.0,
        64,
    )
    assert result.status is ExecutionStatus.PASSED


@pytest.mark.piston
@pytest.mark.skipif(not _RUN_PISTON, reason="real Piston tests require CODE_VERIFIER_RUN_PISTON=1")
def test_real_piston_batch_runs_concurrently_and_reuses_valid_cache(tmp_path: Path) -> None:
    config_path = _real_piston_config_path()
    config = load_piston_executor_config(config_path)
    assert PistonExecutor(config).validate_runtime() == config.version
    version = piston_executor_version(config)
    requests = _real_requests()
    cache_path = tmp_path / "cache.sqlite3"
    with SQLiteExecutionCache(cache_path) as cache:
        first = BatchExecutor(
            lambda: PistonExecutor(config),
            executor_version=version,
            config=BatchExecutorConfig(3, ExecutionCacheMode.READ_WRITE, False),
            cache=cache,
        ).execute_batch(requests, workload_mode=ExecutionWorkloadMode.EVALUATION)
        second = BatchExecutor(
            lambda: PistonExecutor(config),
            executor_version=version,
            config=BatchExecutorConfig(3, ExecutionCacheMode.READ_ONLY, False),
            cache=cache,
        ).execute_batch(requests, workload_mode=ExecutionWorkloadMode.EVALUATION)

    assert [item.request_id for item in first.items] == [request.request_id for request in requests]
    assert [item.result.status for item in first.items] == [
        ExecutionStatus.PASSED,
        ExecutionStatus.PASSED,
        ExecutionStatus.PASSED,
        ExecutionStatus.WRONG_ANSWER,
        ExecutionStatus.RUNTIME_ERROR,
        ExecutionStatus.TIMEOUT,
    ]
    assert first.cache_hits == 0
    assert second.cache_hits == len(requests)
    assert [execution_result_to_mapping(item.result) for item in second.items] == [
        execution_result_to_mapping(item.result) for item in first.items
    ]
    _assert_real_service_healthy(config_path)


class _FailingTransport:
    def list_runtimes(self, *, timeout_seconds: float, max_response_bytes: int) -> object:
        del timeout_seconds, max_response_bytes
        raise PistonTransportError("fixed transport failure")

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        del payload, timeout_seconds, max_response_bytes
        raise PistonTransportError("fixed transport failure")


@pytest.mark.piston
@pytest.mark.skipif(not _RUN_PISTON, reason="real Piston tests require CODE_VERIFIER_RUN_PISTON=1")
def test_real_piston_batch_sandbox_error_is_not_cached_and_service_recovers(tmp_path: Path) -> None:
    config_path = _real_piston_config_path()
    config = load_piston_executor_config(config_path)
    assert PistonExecutor(config).validate_runtime() == config.version
    version = piston_executor_version(config)
    request = _request("recover", "def target(value):\n    return value + 1\n")
    cache_path = tmp_path / "cache.sqlite3"
    with SQLiteExecutionCache(cache_path) as cache:
        failed = BatchExecutor(
            lambda: PistonExecutor(config, transport=_FailingTransport()),
            executor_version=version,
            config=BatchExecutorConfig(1, ExecutionCacheMode.READ_WRITE, False),
            cache=cache,
        ).execute_batch([request])
        recovered = BatchExecutor(
            lambda: PistonExecutor(config),
            executor_version=version,
            config=BatchExecutorConfig(1, ExecutionCacheMode.READ_WRITE, False),
            cache=cache,
        ).execute_batch([request])
        cached = BatchExecutor(
            lambda: PistonExecutor(config, transport=_FailingTransport()),
            executor_version=version,
            config=BatchExecutorConfig(1, ExecutionCacheMode.READ_ONLY, False),
            cache=cache,
        ).execute_batch([request])

    assert failed.items[0].result.status is ExecutionStatus.SANDBOX_ERROR
    assert failed.cache_hits == 0
    assert recovered.items[0].result.status is ExecutionStatus.PASSED
    assert recovered.cache_hits == 0
    assert cached.items[0].result.status is ExecutionStatus.PASSED
    assert cached.cache_hits == 1
    _assert_real_service_healthy(config_path)
