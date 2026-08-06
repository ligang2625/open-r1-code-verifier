"""Unit tests for stable execution cache keys and the SQLite cache."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from code_verifier.execution import (
    ExecutionCacheError,
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTestLayer,
    SQLiteExecutionCache,
    build_execution_cache_key,
    execution_cache_key_digest,
    execution_result_to_mapping,
)
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult


def _tests() -> list[dict[str, object]]:
    return [{"input": [1], "expected": 2}]


def _key(**overrides: object):  # type: ignore[no-untyped-def]
    values: dict[str, object] = {
        "code": "def target(value):\n    return value + 1\n",
        "problem_id": "problem-1",
        "test_layer": ExecutionTestLayer.VISIBLE,
        "tests": _tests(),
        "executor_version": f"piston:{'a' * 64}",
        "function_name": "target",
        "timeout_seconds": 1.0,
        "memory_limit_mb": 64,
    }
    values.update(overrides)
    return build_execution_cache_key(**values)  # type: ignore[arg-type]


def _result(status: ExecutionStatus = ExecutionStatus.PASSED) -> ExecutionResult:
    passed = status is ExecutionStatus.PASSED
    test_result = ExecutionTestCaseResult(status=status, passed=passed, runtime_ms=1.0, stdout="visible", stderr="")
    return ExecutionResult(
        status=status,
        passed_tests=1 if passed else 0,
        total_tests=1,
        pass_rate=1.0 if passed else 0.0,
        runtime_ms=1.0,
        test_results=[test_result],
    )


def test_cache_key_contains_all_spec_required_fields() -> None:
    key = _key()
    assert len(key.code_hash) == 64
    assert key.problem_id == "problem-1"
    assert key.test_layer is ExecutionTestLayer.VISIBLE
    assert len(key.tests_hash) == 64
    assert key.executor_version == f"piston:{'a' * 64}"
    assert key.function_name == "target"
    assert key.timeout_seconds_hex == (1.0).hex()
    assert key.memory_limit_mb == 64
    assert len(execution_cache_key_digest(key)) == 64


def test_cache_key_changes_for_code_problem_layer_tests_and_executor_version() -> None:
    baseline = _key()
    variants = [
        _key(code="def target(value):\n    return value + 2\n"),
        _key(problem_id="problem-2"),
        _key(test_layer=ExecutionTestLayer.TRAIN_HIDDEN),
        _key(tests=[{"input": [2], "expected": 3}]),
        _key(executor_version=f"piston:{'b' * 64}"),
    ]
    assert all(execution_cache_key_digest(variant) != execution_cache_key_digest(baseline) for variant in variants)


def test_cache_key_also_changes_for_function_timeout_and_memory() -> None:
    baseline = _key()
    variants = [
        _key(function_name="other"),
        _key(timeout_seconds=2.0),
        _key(memory_limit_mb=128),
    ]
    assert all(execution_cache_key_digest(variant) != execution_cache_key_digest(baseline) for variant in variants)


def test_code_hash_is_exact_and_tests_hash_is_order_sensitive() -> None:
    baseline = _key()
    assert _key(code="def target(value):\n    return value + 1\n ").code_hash != baseline.code_hash
    reversed_tests = [
        {"input": [2], "expected": 3},
        {"input": [1], "expected": 2},
    ]
    forward_tests = list(reversed(reversed_tests))
    assert _key(tests=forward_tests).tests_hash != _key(tests=reversed_tests).tests_hash


@pytest.mark.parametrize(
    "overrides",
    [
        {"code": "\ud800"},
        {"problem_id": "problem-\ud800"},
        {"tests": [{"input": "\ud800", "expected": 1}]},
    ],
)
def test_cache_key_rejects_non_utf8_request_fields(overrides: dict[str, object]) -> None:
    with pytest.raises(ExecutionContractError, match="invalid UTF-8 text"):
        _key(**overrides)


def test_cache_key_digest_rejects_non_utf8_manual_key() -> None:
    with pytest.raises(ExecutionCacheError, match="serialization failed"):
        execution_cache_key_digest(replace(_key(), problem_id="\ud800"))


def test_sqlite_cache_miss_put_hit_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    key = _key()
    result = _result()
    with SQLiteExecutionCache(path) as cache:
        assert cache.get(key) is None
        cache.put(key, result)
        hit = cache.get(key)
    assert hit == result
    assert hit is not result
    assert hit is not None and hit.test_results is not result.test_results


def test_sqlite_cache_rejects_non_utf8_cached_output_as_cache_error(tmp_path: Path) -> None:
    result = _result()
    invalid_test = replace(result.test_results[0], stdout="\ud800")
    invalid_result = replace(result, test_results=[invalid_test])
    with (
        SQLiteExecutionCache(tmp_path / "cache.sqlite3") as cache,
        pytest.raises(ExecutionCacheError, match="write failed"),
    ):
        cache.put(_key(), invalid_result)


def test_sqlite_cache_rejects_sandbox_error_result(tmp_path: Path) -> None:
    with (
        SQLiteExecutionCache(tmp_path / "cache.sqlite3") as cache,
        pytest.raises(ExecutionCacheError, match="must not be cached"),
    ):
        cache.put(_key(), _result(ExecutionStatus.SANDBOX_ERROR))


def test_sqlite_cache_rejects_structurally_valid_cached_sandbox_error(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    key = _key()
    with SQLiteExecutionCache(path) as cache:
        cache.put(key, _result())
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE entries SET result_json = ?",
        (json.dumps(execution_result_to_mapping(_result(ExecutionStatus.SANDBOX_ERROR))),),
    )
    connection.commit()
    connection.close()
    with (
        SQLiteExecutionCache(path) as cache,
        pytest.raises(ExecutionCacheError, match="contains a sandbox error"),
    ):
        cache.get(key)


def test_sqlite_cache_rejects_symlink_and_insecure_permissions(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    with SQLiteExecutionCache(target):
        pass
    symlink = tmp_path / "link.sqlite3"
    symlink.symlink_to(target)
    with pytest.raises(ExecutionCacheError, match="symbolic link"):
        SQLiteExecutionCache(symlink)

    os.chmod(target, 0o640)
    with pytest.raises(ExecutionCacheError, match="user-only"):
        SQLiteExecutionCache(target)


def test_sqlite_cache_file_is_created_with_user_only_permissions(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    with SQLiteExecutionCache(path):
        pass
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_sqlite_cache_detects_schema_key_and_result_corruption(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.sqlite3"
    with SQLiteExecutionCache(schema_path):
        pass
    connection = sqlite3.connect(schema_path)
    connection.execute("UPDATE metadata SET value = 'wrong'")
    connection.commit()
    connection.close()
    with pytest.raises(ExecutionCacheError, match="schema version"):
        SQLiteExecutionCache(schema_path)

    key_path = tmp_path / "key.sqlite3"
    key = _key()
    with SQLiteExecutionCache(key_path) as cache:
        cache.put(key, _result())
    connection = sqlite3.connect(key_path)
    connection.execute('UPDATE entries SET key_json = \'{"problem_id":"corrupt"}\'')
    connection.commit()
    connection.close()
    with (
        SQLiteExecutionCache(key_path) as cache,
        pytest.raises(ExecutionCacheError, match="key is corrupted"),
    ):
        cache.get(key)

    result_path = tmp_path / "result.sqlite3"
    with SQLiteExecutionCache(result_path) as cache:
        cache.put(key, _result())
    connection = sqlite3.connect(result_path)
    connection.execute('UPDATE entries SET result_json = \'{"status":"passed"}\'')
    connection.commit()
    connection.close()
    with (
        SQLiteExecutionCache(result_path) as cache,
        pytest.raises(ExecutionCacheError, match="entry is corrupted"),
    ):
        cache.get(key)


def test_sqlite_cache_database_does_not_contain_code_or_test_sentinels(tmp_path: Path) -> None:
    code_sentinel = "PRIVATE_CODE_SENTINEL_123456"
    input_sentinel = "PRIVATE_INPUT_SENTINEL_123456"
    expected_sentinel = "PRIVATE_EXPECTED_SENTINEL_123456"
    key = _key(
        code=f"def target(value):\n    # {code_sentinel}\n    return value\n",
        tests=[{"input": input_sentinel, "expected": expected_sentinel}],
    )
    path = tmp_path / "cache.sqlite3"
    with SQLiteExecutionCache(path) as cache:
        cache.put(key, _result())
    raw = path.read_bytes()
    assert code_sentinel.encode() not in raw
    assert input_sentinel.encode() not in raw
    assert expected_sentinel.encode() not in raw


def test_sqlite_cache_close_is_idempotent(tmp_path: Path) -> None:
    cache = SQLiteExecutionCache(tmp_path / "cache.sqlite3")
    cache.close()
    cache.close()


def test_cache_key_dataclass_changes_digest_for_each_field() -> None:
    key = _key()
    variants = [
        replace(key, code_hash="b" * 64),
        replace(key, problem_id="other"),
        replace(key, test_layer=ExecutionTestLayer.EVAL_HIDDEN),
        replace(key, tests_hash="c" * 64),
        replace(key, executor_version=f"piston:{'d' * 64}"),
        replace(key, function_name="other"),
        replace(key, timeout_seconds_hex=(2.0).hex()),
        replace(key, memory_limit_mb=65),
    ]
    baseline = execution_cache_key_digest(key)
    assert all(execution_cache_key_digest(variant) != baseline for variant in variants)
