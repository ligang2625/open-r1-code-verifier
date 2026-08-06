"""Stable execution cache keys and a user-private SQLite result cache."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, cast

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.execution.base import (
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    execution_result_from_mapping,
    execution_result_to_mapping,
    validate_execution_request,
    validate_execution_result,
)

_CACHE_SCHEMA_VERSION = "wp3c-execution-cache-v1"
_KEY_FIELDS = (
    "code_hash",
    "problem_id",
    "test_layer",
    "tests_hash",
    "executor_version",
    "function_name",
    "timeout_seconds_hex",
    "memory_limit_mb",
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ExecutionCacheError(RuntimeError):
    """Raised when a configured execution cache cannot be used safely."""


class ExecutionTestLayer(str, Enum):
    """Canonical test layer associated with one execution request."""

    VISIBLE = "visible"
    TRAIN_HIDDEN = "train_hidden"
    EVAL_HIDDEN = "eval_hidden"


@dataclass(frozen=True)
class ExecutionCacheKey:
    """Exact non-sensitive identity for one cacheable execution request."""

    code_hash: str
    problem_id: str
    test_layer: ExecutionTestLayer
    tests_hash: str
    executor_version: str
    function_name: str
    timeout_seconds_hex: str
    memory_limit_mb: int


class ExecutionCache(Protocol):
    """Minimal cache interface consumed by the batch orchestrator."""

    def get(self, key: ExecutionCacheKey) -> ExecutionResult | None: ...

    def put(self, key: ExecutionCacheKey, result: ExecutionResult) -> None: ...

    def close(self) -> None: ...


def _require_nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionContractError(f"{field_name} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ExecutionContractError(f"{field_name} contains invalid UTF-8 text") from None
    return value


def _validate_execution_cache_key(key: object) -> ExecutionCacheKey:
    if not isinstance(key, ExecutionCacheKey):
        raise ExecutionContractError("cache key must be an ExecutionCacheKey")
    if not isinstance(key.code_hash, str) or _SHA256_PATTERN.fullmatch(key.code_hash) is None:
        raise ExecutionContractError("cache key code_hash must be a lowercase SHA-256 digest")
    problem_id = _require_nonempty_string(key.problem_id, field_name="cache key problem_id")
    if not isinstance(key.test_layer, ExecutionTestLayer):
        raise ExecutionContractError("cache key test_layer must be an ExecutionTestLayer")
    if not isinstance(key.tests_hash, str) or _SHA256_PATTERN.fullmatch(key.tests_hash) is None:
        raise ExecutionContractError("cache key tests_hash must be a lowercase SHA-256 digest")
    executor_version = _require_nonempty_string(key.executor_version, field_name="cache key executor_version")
    function_name = _require_nonempty_string(key.function_name, field_name="cache key function_name")
    timeout_hex = _require_nonempty_string(key.timeout_seconds_hex, field_name="cache key timeout_seconds_hex")
    if len(timeout_hex) > 64:
        raise ExecutionContractError("cache key timeout_seconds_hex is invalid")
    try:
        timeout_seconds = float.fromhex(timeout_hex)
    except (ValueError, OverflowError):
        raise ExecutionContractError("cache key timeout_seconds_hex is invalid") from None
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds.hex() != timeout_hex:
        raise ExecutionContractError("cache key timeout_seconds_hex is invalid")
    if isinstance(key.memory_limit_mb, bool) or not isinstance(key.memory_limit_mb, int) or key.memory_limit_mb <= 0:
        raise ExecutionContractError("cache key memory_limit_mb must be a positive integer")
    return ExecutionCacheKey(
        code_hash=key.code_hash,
        problem_id=problem_id,
        test_layer=key.test_layer,
        tests_hash=key.tests_hash,
        executor_version=executor_version,
        function_name=function_name,
        timeout_seconds_hex=timeout_hex,
        memory_limit_mb=key.memory_limit_mb,
    )


def build_execution_cache_key(
    *,
    code: str,
    problem_id: str,
    test_layer: ExecutionTestLayer,
    tests: list[dict[str, Any]],
    executor_version: str,
    function_name: str,
    timeout_seconds: float,
    memory_limit_mb: int,
) -> ExecutionCacheKey:
    """Build one exact cache key containing all required and safety-relevant fields."""
    validate_execution_request(code, function_name, tests, timeout_seconds, memory_limit_mb)
    problem_id = _require_nonempty_string(problem_id, field_name="problem_id")
    executor_version = _require_nonempty_string(executor_version, field_name="executor_version")
    if not isinstance(test_layer, ExecutionTestLayer):
        raise ExecutionContractError("test_layer must be an ExecutionTestLayer")
    key = ExecutionCacheKey(
        code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        problem_id=problem_id,
        test_layer=test_layer,
        tests_hash=stable_json_hash(tests),
        executor_version=executor_version,
        function_name=function_name,
        timeout_seconds_hex=float(timeout_seconds).hex(),
        memory_limit_mb=memory_limit_mb,
    )
    return _validate_execution_cache_key(key)


def _cache_key_mapping(key: ExecutionCacheKey) -> dict[str, object]:
    key = _validate_execution_cache_key(key)
    return {
        "code_hash": key.code_hash,
        "problem_id": key.problem_id,
        "test_layer": key.test_layer.value,
        "tests_hash": key.tests_hash,
        "executor_version": key.executor_version,
        "function_name": key.function_name,
        "timeout_seconds_hex": key.timeout_seconds_hex,
        "memory_limit_mb": key.memory_limit_mb,
    }


def _canonical_json(value: object) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        text.encode("utf-8")
        return text
    except (TypeError, ValueError, RecursionError, UnicodeEncodeError):
        raise ExecutionCacheError("execution cache serialization failed") from None


def execution_cache_key_digest(key: ExecutionCacheKey) -> str:
    """Return the SHA-256 digest of the exact canonical cache-key mapping."""
    encoded = _canonical_json(_cache_key_mapping(key)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SQLiteExecutionCache:
    """Versioned SQLite cache that stores only hashes, metadata, and validated results."""

    def __init__(self, path: Path) -> None:
        """Open or create a user-private versioned SQLite execution cache."""
        if not isinstance(path, Path):
            raise ExecutionCacheError("execution cache path must be a Path")
        self._path = path
        self._connection: sqlite3.Connection | None = None
        created = False
        try:
            if path.is_symlink():
                raise ExecutionCacheError("execution cache path must not be a symbolic link")
            if path.exists():
                file_stat = path.stat()
                if not stat.S_ISREG(file_stat.st_mode):
                    raise ExecutionCacheError("execution cache path must be a regular file")
                if stat.S_IMODE(file_stat.st_mode) & 0o077:
                    raise ExecutionCacheError("execution cache permissions must be user-only")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
                created = True
            os.chmod(path, 0o600)
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            self._connection = connection
            if created:
                self._initialize_new_database()
            else:
                self._validate_existing_database()
        except ExecutionCacheError:
            self.close()
            if created:
                path.unlink(missing_ok=True)
            raise
        except (OSError, sqlite3.Error):
            self.close()
            if created:
                path.unlink(missing_ok=True)
            raise ExecutionCacheError("execution cache could not be opened safely") from None

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise ExecutionCacheError("execution cache is closed")
        return self._connection

    def _initialize_new_database(self) -> None:
        connection = self._require_connection()
        try:
            connection.executescript(
                """
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE entries (
                    key_digest TEXT PRIMARY KEY,
                    key_json TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                ("schema_version", _CACHE_SCHEMA_VERSION),
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise ExecutionCacheError("execution cache initialization failed") from None

    def _validate_existing_database(self) -> None:
        connection = self._require_connection()
        try:
            tables = {
                cast(str, row["name"])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            if tables != {"metadata", "entries"}:
                raise ExecutionCacheError("execution cache schema is invalid")
            rows = list(connection.execute("SELECT key, value FROM metadata"))
            if len(rows) != 1 or rows[0]["key"] != "schema_version" or rows[0]["value"] != _CACHE_SCHEMA_VERSION:
                raise ExecutionCacheError("execution cache schema version is invalid")
        except ExecutionCacheError:
            raise
        except sqlite3.Error:
            raise ExecutionCacheError("execution cache schema is invalid") from None

    def get(self, key: ExecutionCacheKey) -> ExecutionResult | None:
        """Return one validated cached result or None for a true miss."""
        connection = self._require_connection()
        try:
            key_mapping = _cache_key_mapping(key)
            key_json = _canonical_json(key_mapping)
            digest = execution_cache_key_digest(key)
        except ExecutionContractError:
            raise ExecutionCacheError("execution cache key is invalid") from None
        try:
            row = connection.execute(
                "SELECT key_json, result_json FROM entries WHERE key_digest = ?",
                (digest,),
            ).fetchone()
            if row is None:
                return None
            stored_key_json = cast(str, row["key_json"])
            stored_result_json = cast(str, row["result_json"])
            parsed_key = loads_strict(stored_key_json)
            if (
                not isinstance(parsed_key, dict)
                or tuple(sorted(parsed_key)) != tuple(sorted(_KEY_FIELDS))
                or canonical_json(parsed_key) != key_json
                or stored_key_json != key_json
            ):
                raise ExecutionCacheError("execution cache key is corrupted")
            parsed_result = loads_strict(stored_result_json)
            result = execution_result_from_mapping(parsed_result)
            if result.status is ExecutionStatus.SANDBOX_ERROR:
                raise ExecutionCacheError("execution cache contains a sandbox error")
            return ExecutionResult(
                status=result.status,
                passed_tests=result.passed_tests,
                total_tests=result.total_tests,
                pass_rate=result.pass_rate,
                runtime_ms=result.runtime_ms,
                test_results=list(result.test_results),
            )
        except ExecutionCacheError:
            raise
        except (ExecutionContractError, StrictJsonError, TypeError, ValueError, UnicodeEncodeError, sqlite3.Error):
            raise ExecutionCacheError("execution cache entry is corrupted") from None

    def put(self, key: ExecutionCacheKey, result: ExecutionResult) -> None:
        """Atomically insert or replace one validated non-sandbox result."""
        connection = self._require_connection()
        try:
            key_json = _canonical_json(_cache_key_mapping(key))
            digest = execution_cache_key_digest(key)
        except ExecutionContractError:
            raise ExecutionCacheError("execution cache key is invalid") from None
        try:
            validate_execution_result(result)
            if result.status is ExecutionStatus.SANDBOX_ERROR:
                raise ExecutionCacheError("sandbox errors must not be cached")
            result_json = _canonical_json(execution_result_to_mapping(result))
            connection.execute(
                "INSERT OR REPLACE INTO entries(key_digest, key_json, result_json) VALUES (?, ?, ?)",
                (digest, key_json, result_json),
            )
            connection.commit()
        except ExecutionCacheError:
            connection.rollback()
            raise
        except (ExecutionContractError, UnicodeEncodeError, sqlite3.Error):
            connection.rollback()
            raise ExecutionCacheError("execution cache write failed") from None

    def close(self) -> None:
        """Commit pending work and close the SQLite connection."""
        connection = self._connection
        if connection is None:
            return
        self._connection = None
        try:
            connection.commit()
            connection.close()
        except sqlite3.Error:
            raise ExecutionCacheError("execution cache close failed") from None

    def __enter__(self) -> SQLiteExecutionCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        connection = self._connection
        if connection is not None and exc_type is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                self.close()
                raise ExecutionCacheError("execution cache rollback failed") from None
        self.close()
