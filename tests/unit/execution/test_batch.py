"""Unit tests for bounded batch orchestration and cache policy."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from code_verifier.config import ConfigError
from code_verifier.execution import (
    BatchExecutionError,
    BatchExecutionRequest,
    BatchExecutor,
    BatchExecutorConfig,
    CodeExecutor,
    ExecutionCacheKey,
    ExecutionCacheMode,
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTestLayer,
    ExecutionWorkloadMode,
    batch_execution_config_from_mapping,
    batch_execution_request_from_mapping,
    batch_execution_result_to_mapping,
    build_execution_cache_key,
    load_batch_execution_config,
)
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult


def _piston_mapping() -> dict[str, object]:
    return {
        "base_url": "http://127.0.0.1:2000",
        "language": "python",
        "version": "3.10.0",
        "request_timeout_margin_seconds": 2.0,
        "max_response_bytes": 131072,
        "max_output_bytes": 4096,
        "stop_on_first_failure": False,
    }


def _config_mapping() -> dict[str, object]:
    return {
        "piston": _piston_mapping(),
        "batch": {"max_concurrency": 4, "cache_mode": "disabled", "allow_training_cache": False},
    }


def _request(request_id: str, *, code: str = "fixed", problem_id: str | None = None) -> BatchExecutionRequest:
    return BatchExecutionRequest(
        request_id=request_id,
        problem_id=problem_id or f"problem-{request_id}",
        test_layer=ExecutionTestLayer.VISIBLE,
        code=code,
        function_name="target",
        tests=[{"input": [1], "expected": 2}],
        timeout_seconds=1.0,
        memory_limit_mb=64,
    )


def _result(
    status: ExecutionStatus = ExecutionStatus.PASSED,
    *,
    runtime_ms: float = 1.0,
    stderr: str = "",
) -> ExecutionResult:
    passed = status is ExecutionStatus.PASSED
    return ExecutionResult(
        status=status,
        passed_tests=1 if passed else 0,
        total_tests=1,
        pass_rate=1.0 if passed else 0.0,
        runtime_ms=runtime_ms,
        test_results=[
            ExecutionTestCaseResult(
                status=status,
                passed=passed,
                runtime_ms=runtime_ms,
                stdout="",
                stderr=stderr,
            )
        ],
    )


def _batch_config(
    *,
    max_concurrency: int = 2,
    cache_mode: ExecutionCacheMode = ExecutionCacheMode.DISABLED,
    allow_training_cache: bool = False,
) -> BatchExecutorConfig:
    return BatchExecutorConfig(
        max_concurrency=max_concurrency,
        cache_mode=cache_mode,
        allow_training_cache=allow_training_cache,
    )


def _key(request: BatchExecutionRequest) -> ExecutionCacheKey:
    return build_execution_cache_key(
        code=request.code,
        problem_id=request.problem_id,
        test_layer=request.test_layer,
        tests=request.tests,
        executor_version="executor-v1",
        function_name=request.function_name,
        timeout_seconds=request.timeout_seconds,
        memory_limit_mb=request.memory_limit_mb,
    )


class _MemoryCache:
    def __init__(self, values: dict[ExecutionCacheKey, ExecutionResult] | None = None) -> None:
        self.values = {} if values is None else dict(values)
        self.get_calls: list[ExecutionCacheKey] = []
        self.put_calls: list[tuple[ExecutionCacheKey, ExecutionResult]] = []
        self.close_calls = 0
        self.threads: list[int] = []

    def get(self, key: ExecutionCacheKey) -> ExecutionResult | None:
        self.threads.append(threading.get_ident())
        self.get_calls.append(key)
        return self.values.get(key)

    def put(self, key: ExecutionCacheKey, result: ExecutionResult) -> None:
        self.threads.append(threading.get_ident())
        self.put_calls.append((key, result))
        self.values[key] = result

    def close(self) -> None:
        self.close_calls += 1


class _CallableExecutor:
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


def _factory(callback: Callable[[str], ExecutionResult], calls: list[CodeExecutor]) -> Callable[[], CodeExecutor]:
    def create() -> CodeExecutor:
        executor: CodeExecutor = _CallableExecutor(callback)
        calls.append(executor)
        return executor

    return create


def test_batch_config_accepts_exact_mapping_and_rejects_unknown_fields(tmp_path: Path) -> None:
    config = batch_execution_config_from_mapping(_config_mapping())
    assert config.batch.max_concurrency == 4
    assert config.batch.cache_mode is ExecutionCacheMode.DISABLED

    path = tmp_path / "batch.yaml"
    path.write_text(
        """piston:
  base_url: http://127.0.0.1:2000
  language: python
  version: "3.10.0"
  request_timeout_margin_seconds: 2.0
  max_response_bytes: 131072
  max_output_bytes: 4096
  stop_on_first_failure: false
batch:
  max_concurrency: 4
  cache_mode: disabled
  allow_training_cache: false
""",
        encoding="utf-8",
    )
    assert load_batch_execution_config(path) == config

    invalid = _config_mapping()
    invalid["extra"] = 1
    with pytest.raises(ConfigError):
        batch_execution_config_from_mapping(invalid)
    for value in (True, 0, 65, 1.5):
        invalid = _config_mapping()
        batch = dict(cast(dict[str, object], invalid["batch"]))
        batch["max_concurrency"] = value
        invalid["batch"] = batch
        with pytest.raises(ConfigError):
            batch_execution_config_from_mapping(invalid)


def test_batch_request_mapping_requires_exact_fields_and_valid_test_layer() -> None:
    mapping: dict[str, object] = {
        "request_id": "request-1",
        "problem_id": "problem-1",
        "test_layer": "visible",
        "code": "def target(value):\n    return value + 1\n",
        "function_name": "target",
        "tests": [{"input": [1], "expected": 2}],
        "timeout_seconds": 1,
        "memory_limit_mb": 64,
    }
    request = batch_execution_request_from_mapping(mapping)
    assert request.timeout_seconds == 1.0
    assert request.test_layer is ExecutionTestLayer.VISIBLE

    for invalid in ({**mapping, "extra": 1}, {**mapping, "test_layer": "private"}, {**mapping, "request_id": ""}):
        with pytest.raises(ExecutionContractError):
            batch_execution_request_from_mapping(invalid)


@pytest.mark.parametrize("cache_mode", list(ExecutionCacheMode))
@pytest.mark.parametrize("field", ["code", "request_id", "problem_id", "tests"])
def test_batch_rejects_non_utf8_requests_before_cache_or_factory_side_effects(
    cache_mode: ExecutionCacheMode,
    field: str,
) -> None:
    request = _request("1")
    if field == "tests":
        request = replace(request, tests=[{"input": "\ud800", "expected": 1}])
    elif field == "code":
        request = replace(request, code="\ud800")
    elif field == "request_id":
        request = replace(request, request_id="\ud800")
    else:
        request = replace(request, problem_id="\ud800")
    cache = None if cache_mode is ExecutionCacheMode.DISABLED else _MemoryCache()
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=cache_mode),
        cache=cache,
    )
    with pytest.raises(ExecutionContractError, match="invalid UTF-8 text"):
        executor.execute_batch([request])
    assert factory_calls == []
    if cache is not None:
        assert cache.get_calls == []
        assert cache.put_calls == []


def test_batch_prevalidates_all_requests_before_factory_is_called() -> None:
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(),
    )
    invalid = replace(_request("bad"), code="")
    with pytest.raises(ExecutionContractError):
        executor.execute_batch([_request("good"), invalid])
    assert factory_calls == []


def test_batch_rejects_duplicate_request_ids_without_side_effects() -> None:
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(),
    )
    with pytest.raises(ExecutionContractError, match="unique"):
        executor.execute_batch([_request("same"), _request("same", problem_id="other")])
    assert factory_calls == []


def test_batch_preserves_input_order_when_futures_finish_out_of_order() -> None:
    factory_calls: list[CodeExecutor] = []

    def callback(code: str) -> ExecutionResult:
        time.sleep(0.08 if code == "slow" else 0.01)
        return _result()

    executor = BatchExecutor(
        _factory(callback, factory_calls),
        executor_version="executor-v1",
        config=_batch_config(max_concurrency=2),
    )
    result = executor.execute_batch([_request("first", code="slow"), _request("second", code="fast")])
    assert [item.request_id for item in result.items] == ["first", "second"]


def test_batch_never_exceeds_configured_concurrency() -> None:
    lock = threading.Lock()
    barrier = threading.Barrier(3)
    active = 0
    peak = 0
    factory_calls: list[CodeExecutor] = []

    def callback(code: str) -> ExecutionResult:
        nonlocal active, peak
        del code
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=3)
        with lock:
            active -= 1
        return _result()

    executor = BatchExecutor(
        _factory(callback, factory_calls),
        executor_version="executor-v1",
        config=_batch_config(max_concurrency=3),
    )
    executor.execute_batch([_request("1"), _request("2"), _request("3")])
    assert peak == 3
    assert peak <= 3


def test_batch_max_concurrency_one_is_sequential() -> None:
    lock = threading.Lock()
    active = 0
    peak = 0
    factory_calls: list[CodeExecutor] = []

    def callback(code: str) -> ExecutionResult:
        nonlocal active, peak
        del code
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return _result()

    executor = BatchExecutor(
        _factory(callback, factory_calls),
        executor_version="executor-v1",
        config=_batch_config(max_concurrency=1),
    )
    executor.execute_batch([_request("1"), _request("2"), _request("3")])
    assert peak == 1


def test_batch_creates_independent_executor_per_cache_miss() -> None:
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(max_concurrency=2),
    )
    executor.execute_batch([_request("1"), _request("2"), _request("3")])
    assert len(factory_calls) == 3
    assert len({id(item) for item in factory_calls}) == 3


def test_batch_converts_worker_exception_to_sanitized_sandbox_result() -> None:
    sentinel = "PRIVATE_WORKER_EXCEPTION_SENTINEL"
    factory_calls: list[CodeExecutor] = []

    def callback(code: str) -> ExecutionResult:
        del code
        raise RuntimeError(sentinel)

    executor = BatchExecutor(
        _factory(callback, factory_calls),
        executor_version="executor-v1",
        config=_batch_config(),
    )
    result = executor.execute_batch([_request("1")])
    assert result.items[0].result.status is ExecutionStatus.SANDBOX_ERROR
    assert result.items[0].result.test_results[0].stderr == "batch executor failed"
    assert sentinel not in json.dumps(batch_execution_result_to_mapping(result))


def test_batch_disabled_cache_never_reads_or_writes() -> None:
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.DISABLED),
    )
    result = executor.execute_batch([_request("1")])
    assert result.cache_hits == 0
    assert len(factory_calls) == 1
    with pytest.raises(BatchExecutionError, match="must not receive"):
        BatchExecutor(
            _factory(lambda code: _result(), []),
            executor_version="executor-v1",
            config=_batch_config(cache_mode=ExecutionCacheMode.DISABLED),
            cache=_MemoryCache(),
        )


def test_batch_read_only_uses_hits_and_does_not_write_misses() -> None:
    hit_request = _request("hit")
    miss_request = _request("miss")
    cache = _MemoryCache({_key(hit_request): _result()})
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.READ_ONLY),
        cache=cache,
    )
    result = executor.execute_batch([hit_request, miss_request])
    assert [item.cache_hit for item in result.items] == [True, False]
    assert result.cache_hits == 1
    assert len(factory_calls) == 1
    assert cache.put_calls == []


def test_batch_read_write_uses_hits_and_writes_non_sandbox_misses() -> None:
    hit_request = _request("hit")
    miss_request = _request("miss")
    cache = _MemoryCache({_key(hit_request): _result()})
    factory_calls: list[CodeExecutor] = []
    main_thread = threading.get_ident()
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.READ_WRITE),
        cache=cache,
    )
    result = executor.execute_batch([hit_request, miss_request])
    assert [item.cache_hit for item in result.items] == [True, False]
    assert len(cache.put_calls) == 1
    assert set(cache.threads) == {main_thread}


def test_batch_does_not_cache_sandbox_error() -> None:
    cache = _MemoryCache()
    factory_calls: list[CodeExecutor] = []

    def callback(code: str) -> ExecutionResult:
        del code
        raise RuntimeError("fixed")

    executor = BatchExecutor(
        _factory(callback, factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.READ_WRITE),
        cache=cache,
    )
    result = executor.execute_batch([_request("1")])
    assert result.items[0].result.status is ExecutionStatus.SANDBOX_ERROR
    assert cache.put_calls == []


def test_batch_rejects_sandbox_error_returned_by_custom_cache_without_running_factory() -> None:
    request = _request("1")
    cache = _MemoryCache({_key(request): _result(ExecutionStatus.SANDBOX_ERROR)})
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.READ_ONLY),
        cache=cache,
    )
    with pytest.raises(BatchExecutionError, match="returned a sandbox error"):
        executor.execute_batch([request])
    assert factory_calls == []


def test_batch_training_cache_requires_explicit_opt_in() -> None:
    request = _request("1")
    cache = _MemoryCache()
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.READ_ONLY, allow_training_cache=False),
        cache=cache,
    )
    with pytest.raises(BatchExecutionError, match="explicit opt-in"):
        executor.execute_batch([request], workload_mode=ExecutionWorkloadMode.TRAINING)
    assert cache.get_calls == []
    assert factory_calls == []

    opted_in = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.READ_ONLY, allow_training_cache=True),
        cache=cache,
    )
    assert opted_in.execute_batch([request], workload_mode=ExecutionWorkloadMode.TRAINING).total_requests == 1


def test_batch_result_mapping_is_json_serializable_and_omits_request_payload() -> None:
    code_sentinel = "PRIVATE_CODE_SENTINEL"
    input_sentinel = "PRIVATE_INPUT_SENTINEL"
    expected_sentinel = "PRIVATE_EXPECTED_SENTINEL"
    request = replace(
        _request("1", code=code_sentinel),
        tests=[{"input": input_sentinel, "expected": expected_sentinel}],
    )
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(),
    )
    mapping = batch_execution_result_to_mapping(executor.execute_batch([request]))
    encoded = json.dumps(mapping, allow_nan=False)
    assert code_sentinel not in encoded
    assert input_sentinel not in encoded
    assert expected_sentinel not in encoded
    assert json.loads(encoded) == mapping


def test_batch_result_runtime_is_wall_clock_and_cache_hit_count_is_exact() -> None:
    hit_request = _request("hit")
    miss_request = _request("miss")
    cache = _MemoryCache({_key(hit_request): _result(runtime_ms=5000.0)})
    factory_calls: list[CodeExecutor] = []
    executor = BatchExecutor(
        _factory(lambda code: _result(runtime_ms=5000.0), factory_calls),
        executor_version="executor-v1",
        config=_batch_config(cache_mode=ExecutionCacheMode.READ_ONLY),
        cache=cache,
    )
    result = executor.execute_batch([hit_request, miss_request])
    assert result.cache_hits == 1
    assert result.runtime_ms < sum(item.result.runtime_ms for item in result.items)
