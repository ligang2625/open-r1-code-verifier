"""Bounded batch orchestration over independent single-request executors."""

from __future__ import annotations

import copy
import math
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.execution.base import (
    CodeExecutor,
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    TestCaseResult,
    execution_result_to_mapping,
    validate_execution_request,
    validate_execution_result,
)
from code_verifier.execution.cache import (
    ExecutionCache,
    ExecutionCacheKey,
    ExecutionTestLayer,
    build_execution_cache_key,
)
from code_verifier.execution.piston import PistonExecutorConfig, piston_executor_config_from_mapping

_BATCH_CONFIG_FIELDS = frozenset({"max_concurrency", "cache_mode", "allow_training_cache"})
_BATCH_REQUEST_FIELDS = frozenset(
    {
        "request_id",
        "problem_id",
        "test_layer",
        "code",
        "function_name",
        "tests",
        "timeout_seconds",
        "memory_limit_mb",
    }
)
_EXECUTOR_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


class BatchExecutionError(RuntimeError):
    """Raised when batch orchestration cannot proceed without misattributing a failure."""


class ExecutionCacheMode(str, Enum):
    """Read/write policy for optional execution caching."""

    DISABLED = "disabled"
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class ExecutionWorkloadMode(str, Enum):
    """Experiment mode controlling cache safety defaults."""

    EVALUATION = "evaluation"
    TRAINING = "training"


@dataclass(frozen=True)
class BatchExecutorConfig:
    """Validated concurrency and cache policy for one batch executor."""

    max_concurrency: int
    cache_mode: ExecutionCacheMode
    allow_training_cache: bool


@dataclass(frozen=True)
class BatchExecutionConfig:
    """Combined strict Piston and batch configuration."""

    piston: PistonExecutorConfig
    batch: BatchExecutorConfig


@dataclass(frozen=True)
class BatchExecutionRequest:
    """One independently executable problem/test-layer request."""

    request_id: str
    problem_id: str
    test_layer: ExecutionTestLayer
    code: str
    function_name: str
    tests: list[dict[str, Any]]
    timeout_seconds: float
    memory_limit_mb: int


@dataclass(frozen=True)
class BatchExecutionItemResult:
    """One ordered batch item and its cache provenance."""

    request_id: str
    problem_id: str
    test_layer: ExecutionTestLayer
    cache_hit: bool
    result: ExecutionResult


@dataclass(frozen=True)
class BatchExecutionResult:
    """Validated batch summary with items in original request order."""

    executor_version: str
    max_concurrency: int
    cache_mode: ExecutionCacheMode
    workload_mode: ExecutionWorkloadMode
    total_requests: int
    cache_hits: int
    runtime_ms: float
    items: list[BatchExecutionItemResult]


def _require_nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionContractError(f"{field_name} must be a non-empty string")
    return value


def _parse_test_layer(value: object) -> ExecutionTestLayer:
    if not isinstance(value, str):
        raise ExecutionContractError("test_layer must be a supported string")
    try:
        return ExecutionTestLayer(value)
    except ValueError:
        raise ExecutionContractError("test_layer must be a supported string") from None


def batch_execution_request_from_mapping(value: object) -> BatchExecutionRequest:
    """Parse one exact JSON request mapping and validate its single-execution contract."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ExecutionContractError("batch request must be an object")
    mapping = cast(dict[str, object], value)
    if set(mapping) != _BATCH_REQUEST_FIELDS:
        raise ExecutionContractError("batch request fields do not match the required schema")
    request_id = _require_nonempty_string(mapping["request_id"], field_name="request_id")
    problem_id = _require_nonempty_string(mapping["problem_id"], field_name="problem_id")
    test_layer = _parse_test_layer(mapping["test_layer"])
    code = mapping["code"]
    function_name = mapping["function_name"]
    tests = mapping["tests"]
    timeout_seconds = mapping["timeout_seconds"]
    memory_limit_mb = mapping["memory_limit_mb"]
    validate_execution_request(
        cast(str, code),
        cast(str, function_name),
        cast(list[dict[str, Any]], tests),
        cast(float, timeout_seconds),
        cast(int, memory_limit_mb),
    )
    return BatchExecutionRequest(
        request_id=request_id,
        problem_id=problem_id,
        test_layer=test_layer,
        code=cast(str, code),
        function_name=cast(str, function_name),
        tests=copy.deepcopy(cast(list[dict[str, Any]], tests)),
        timeout_seconds=float(cast(int | float, timeout_seconds)),
        memory_limit_mb=cast(int, memory_limit_mb),
    )


def _copy_execution_result(result: ExecutionResult) -> ExecutionResult:
    validate_execution_result(result)
    return ExecutionResult(
        status=result.status,
        passed_tests=result.passed_tests,
        total_tests=result.total_tests,
        pass_rate=result.pass_rate,
        runtime_ms=result.runtime_ms,
        test_results=list(result.test_results),
    )


def _validate_batch_request(request: object) -> BatchExecutionRequest:
    if not isinstance(request, BatchExecutionRequest):
        raise ExecutionContractError("batch requests must contain BatchExecutionRequest values")
    request_id = _require_nonempty_string(request.request_id, field_name="request_id")
    problem_id = _require_nonempty_string(request.problem_id, field_name="problem_id")
    if not isinstance(request.test_layer, ExecutionTestLayer):
        raise ExecutionContractError("test_layer must be an ExecutionTestLayer")
    validate_execution_request(
        request.code,
        request.function_name,
        request.tests,
        request.timeout_seconds,
        request.memory_limit_mb,
    )
    return BatchExecutionRequest(
        request_id=request_id,
        problem_id=problem_id,
        test_layer=request.test_layer,
        code=request.code,
        function_name=request.function_name,
        tests=copy.deepcopy(request.tests),
        timeout_seconds=float(request.timeout_seconds),
        memory_limit_mb=request.memory_limit_mb,
    )


def batch_execution_item_to_mapping(item: BatchExecutionItemResult) -> dict[str, object]:
    """Serialize one non-sensitive item result without code or tests."""
    if not isinstance(item, BatchExecutionItemResult):
        raise ExecutionContractError("batch item must be a BatchExecutionItemResult")
    _require_nonempty_string(item.request_id, field_name="request_id")
    _require_nonempty_string(item.problem_id, field_name="problem_id")
    if not isinstance(item.test_layer, ExecutionTestLayer) or not isinstance(item.cache_hit, bool):
        raise ExecutionContractError("batch item fields are invalid")
    return {
        "request_id": item.request_id,
        "problem_id": item.problem_id,
        "test_layer": item.test_layer.value,
        "cache_hit": item.cache_hit,
        "result": execution_result_to_mapping(item.result),
    }


def batch_execution_result_to_mapping(result: BatchExecutionResult) -> dict[str, object]:
    """Serialize one batch summary and all item results as JSON-safe mappings."""
    if not isinstance(result, BatchExecutionResult):
        raise ExecutionContractError("batch result must be a BatchExecutionResult")
    _validate_executor_version(result.executor_version)
    _validate_batch_executor_config(
        BatchExecutorConfig(
            max_concurrency=result.max_concurrency,
            cache_mode=result.cache_mode,
            allow_training_cache=False,
        )
    )
    if not isinstance(result.workload_mode, ExecutionWorkloadMode):
        raise ExecutionContractError("workload_mode must be an ExecutionWorkloadMode")
    if (
        isinstance(result.total_requests, bool)
        or not isinstance(result.total_requests, int)
        or result.total_requests < 0
    ):
        raise ExecutionContractError("total_requests must be a non-negative integer")
    if isinstance(result.cache_hits, bool) or not isinstance(result.cache_hits, int) or result.cache_hits < 0:
        raise ExecutionContractError("cache_hits must be a non-negative integer")
    if result.cache_hits > result.total_requests or len(result.items) != result.total_requests:
        raise ExecutionContractError("batch result counts are inconsistent")
    if sum(item.cache_hit for item in result.items) != result.cache_hits:
        raise ExecutionContractError("cache_hits must equal the number of cache-hit items")
    if isinstance(result.runtime_ms, bool) or not isinstance(result.runtime_ms, int | float):
        raise ExecutionContractError("runtime_ms must be a finite non-negative number")
    runtime_ms = float(result.runtime_ms)
    if not math.isfinite(runtime_ms) or runtime_ms < 0:
        raise ExecutionContractError("runtime_ms must be a finite non-negative number")
    return {
        "executor_version": result.executor_version,
        "max_concurrency": result.max_concurrency,
        "cache_mode": result.cache_mode.value,
        "workload_mode": result.workload_mode.value,
        "total_requests": result.total_requests,
        "cache_hits": result.cache_hits,
        "runtime_ms": runtime_ms,
        "items": [batch_execution_item_to_mapping(item) for item in result.items],
    }


def _parse_cache_mode(value: object) -> ExecutionCacheMode:
    if not isinstance(value, str):
        raise ConfigError("cache_mode must be a supported string")
    try:
        return ExecutionCacheMode(value)
    except ValueError:
        raise ConfigError("cache_mode must be a supported string") from None


def _validate_batch_executor_config(config: BatchExecutorConfig) -> None:
    if not isinstance(config, BatchExecutorConfig):
        raise ConfigError("batch config must be a BatchExecutorConfig")
    if (
        isinstance(config.max_concurrency, bool)
        or not isinstance(config.max_concurrency, int)
        or not 1 <= config.max_concurrency <= 64
    ):
        raise ConfigError("max_concurrency must be an integer between 1 and 64")
    if not isinstance(config.cache_mode, ExecutionCacheMode):
        raise ConfigError("cache_mode must be an ExecutionCacheMode")
    if not isinstance(config.allow_training_cache, bool):
        raise ConfigError("allow_training_cache must be a boolean")


def batch_execution_config_from_mapping(value: object) -> BatchExecutionConfig:
    """Parse exact piston and batch mappings and reject unknown fields."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigError("Batch execution config must be an object")
    mapping = cast(dict[str, object], value)
    if set(mapping) != {"piston", "batch"}:
        raise ConfigError("Batch execution config must contain exactly piston and batch")
    batch_value = mapping["batch"]
    if not isinstance(batch_value, dict) or not all(isinstance(key, str) for key in batch_value):
        raise ConfigError("batch config must be an object")
    batch_mapping = cast(dict[str, object], batch_value)
    if set(batch_mapping) != _BATCH_CONFIG_FIELDS:
        raise ConfigError("batch config fields do not match the required schema")
    max_concurrency = batch_mapping["max_concurrency"]
    allow_training_cache = batch_mapping["allow_training_cache"]
    config = BatchExecutorConfig(
        max_concurrency=cast(int, max_concurrency),
        cache_mode=_parse_cache_mode(batch_mapping["cache_mode"]),
        allow_training_cache=cast(bool, allow_training_cache),
    )
    _validate_batch_executor_config(config)
    return BatchExecutionConfig(
        piston=piston_executor_config_from_mapping(mapping["piston"]),
        batch=config,
    )


def load_batch_execution_config(path: Path) -> BatchExecutionConfig:
    """Load one strict WP3-c batch execution YAML."""
    return batch_execution_config_from_mapping(load_yaml_mapping(path))


def _validate_executor_version(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or _EXECUTOR_VERSION_PATTERN.fullmatch(value) is None
    ):
        raise ExecutionContractError("executor_version must be a non-empty stable identifier")
    return value


def _cache_key(request: BatchExecutionRequest, executor_version: str) -> ExecutionCacheKey:
    return build_execution_cache_key(
        code=request.code,
        problem_id=request.problem_id,
        test_layer=request.test_layer,
        tests=request.tests,
        executor_version=executor_version,
        function_name=request.function_name,
        timeout_seconds=request.timeout_seconds,
        memory_limit_mb=request.memory_limit_mb,
    )


def _synthetic_sandbox_result(request: BatchExecutionRequest, runtime_ms: float) -> ExecutionResult:
    test_results = []
    if request.tests:
        test_results.append(
            TestCaseResult(
                status=ExecutionStatus.SANDBOX_ERROR,
                passed=False,
                runtime_ms=max(0.0, runtime_ms),
                stdout="",
                stderr="batch executor failed",
            )
        )
    result = ExecutionResult(
        status=ExecutionStatus.SANDBOX_ERROR,
        passed_tests=0,
        total_tests=len(request.tests),
        pass_rate=0.0,
        runtime_ms=max(0.0, runtime_ms),
        test_results=test_results,
    )
    validate_execution_result(result)
    return result


class BatchExecutor:
    """Bounded concurrent orchestration over independent executor instances."""

    def __init__(
        self,
        executor_factory: Callable[[], CodeExecutor],
        *,
        executor_version: str,
        config: BatchExecutorConfig,
        cache: ExecutionCache | None = None,
    ) -> None:
        """Create a bounded batch orchestrator over independent executor instances."""
        if not callable(executor_factory):
            raise BatchExecutionError("executor_factory must be callable")
        _validate_batch_executor_config(config)
        self._executor_factory = executor_factory
        self._executor_version = _validate_executor_version(executor_version)
        self._config = config
        if config.cache_mode is ExecutionCacheMode.DISABLED and cache is not None:
            raise BatchExecutionError("disabled cache mode must not receive a cache")
        if config.cache_mode is not ExecutionCacheMode.DISABLED and cache is None:
            raise BatchExecutionError("enabled cache mode requires a cache")
        self._cache = cache

    def execute_batch(
        self,
        requests: Sequence[BatchExecutionRequest],
        *,
        workload_mode: ExecutionWorkloadMode = ExecutionWorkloadMode.EVALUATION,
    ) -> BatchExecutionResult:
        """Validate, cache, execute concurrently, and return results in input order."""
        started = time.monotonic()
        if not isinstance(requests, Sequence):
            raise ExecutionContractError("requests must be a sequence")
        if not isinstance(workload_mode, ExecutionWorkloadMode):
            raise ExecutionContractError("workload_mode must be an ExecutionWorkloadMode")
        copied_requests = [_validate_batch_request(request) for request in list(requests)]
        request_ids: set[str] = set()
        for request in copied_requests:
            if request.request_id in request_ids:
                raise ExecutionContractError("request_id values must be unique within a batch")
            request_ids.add(request.request_id)
        if (
            workload_mode is ExecutionWorkloadMode.TRAINING
            and self._config.cache_mode is not ExecutionCacheMode.DISABLED
            and not self._config.allow_training_cache
        ):
            raise BatchExecutionError("training cache requires explicit opt-in")

        item_results: list[BatchExecutionItemResult | None] = [None] * len(copied_requests)
        misses: list[tuple[int, BatchExecutionRequest, ExecutionCacheKey | None]] = []
        for index, request in enumerate(copied_requests):
            key = None
            if self._config.cache_mode is not ExecutionCacheMode.DISABLED:
                assert self._cache is not None
                key = _cache_key(request, self._executor_version)
                cached = self._cache.get(key)
                if cached is not None:
                    if cached.status is ExecutionStatus.SANDBOX_ERROR:
                        raise BatchExecutionError("execution cache returned a sandbox error")
                    try:
                        copied_result = _copy_execution_result(cached)
                    except ExecutionContractError:
                        raise BatchExecutionError("execution cache returned an invalid result") from None
                    item_results[index] = BatchExecutionItemResult(
                        request_id=request.request_id,
                        problem_id=request.problem_id,
                        test_layer=request.test_layer,
                        cache_hit=True,
                        result=copied_result,
                    )
                    continue
            misses.append((index, request, key))

        if misses:
            future_records: dict[
                Future[ExecutionResult],
                tuple[int, BatchExecutionRequest, ExecutionCacheKey | None],
            ] = {}
            with ThreadPoolExecutor(
                max_workers=self._config.max_concurrency,
                thread_name_prefix="code-verifier",
            ) as pool:
                for index, request, key in misses:
                    future = pool.submit(self._execute_request, request)
                    future_records[future] = (index, request, key)
                for future in as_completed(future_records):
                    index, request, key = future_records[future]
                    result = future.result()
                    if (
                        self._config.cache_mode is ExecutionCacheMode.READ_WRITE
                        and result.status is not ExecutionStatus.SANDBOX_ERROR
                    ):
                        assert self._cache is not None and key is not None
                        self._cache.put(key, result)
                    item_results[index] = BatchExecutionItemResult(
                        request_id=request.request_id,
                        problem_id=request.problem_id,
                        test_layer=request.test_layer,
                        cache_hit=False,
                        result=_copy_execution_result(result),
                    )

        if any(item is None for item in item_results):
            raise BatchExecutionError("batch result assembly failed")
        completed_items = cast(list[BatchExecutionItemResult], item_results)
        runtime_ms = max(0.0, (time.monotonic() - started) * 1000.0)
        batch_result = BatchExecutionResult(
            executor_version=self._executor_version,
            max_concurrency=self._config.max_concurrency,
            cache_mode=self._config.cache_mode,
            workload_mode=workload_mode,
            total_requests=len(copied_requests),
            cache_hits=sum(item.cache_hit for item in completed_items),
            runtime_ms=runtime_ms,
            items=list(completed_items),
        )
        batch_execution_result_to_mapping(batch_result)
        return BatchExecutionResult(
            executor_version=batch_result.executor_version,
            max_concurrency=batch_result.max_concurrency,
            cache_mode=batch_result.cache_mode,
            workload_mode=batch_result.workload_mode,
            total_requests=batch_result.total_requests,
            cache_hits=batch_result.cache_hits,
            runtime_ms=batch_result.runtime_ms,
            items=list(batch_result.items),
        )

    def _execute_request(self, request: BatchExecutionRequest) -> ExecutionResult:
        started = time.monotonic()
        try:
            executor = self._executor_factory()
            result = executor.execute(
                request.code,
                request.function_name,
                copy.deepcopy(request.tests),
                request.timeout_seconds,
                request.memory_limit_mb,
            )
            return _copy_execution_result(result)
        except Exception:
            return _synthetic_sandbox_result(request, (time.monotonic() - started) * 1000.0)
