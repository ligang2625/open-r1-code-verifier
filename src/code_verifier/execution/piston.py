"""Loopback-only HTTP boundary for a Piston executor.

The backend may be local or reached through loopback-only SSH forwarding. Project
configuration intentionally accepts only loopback HTTP endpoints in either mode.
"""

from __future__ import annotations

import copy
import errno
import hashlib
import http.client
import json
import math
import secrets
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.error import URLError
from urllib.parse import urlsplit

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.execution import harness as harness_module
from code_verifier.execution.base import (
    ExecutionContractError,
    ExecutionResult,
    ExecutionStatus,
    TestCaseResult,
    validate_execution_request,
    validate_execution_result,
)
from code_verifier.execution.harness import HarnessReport, build_python_test_program, parse_harness_report
from code_verifier.execution.piston_resilience import PistonTransportPolicy, PistonTransportTelemetry, sleep_backoff

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_CONFIG_FIELDS = frozenset(
    {
        "base_url",
        "language",
        "version",
        "request_timeout_margin_seconds",
        "max_response_bytes",
        "max_output_bytes",
        "stop_on_first_failure",
    }
)
PISTON_EXECUTOR_IMPLEMENTATION_VERSION = "piston-executor-v1"


class PistonTransportFailureKind(str, Enum):
    """Sanitized failure classes used for fail-closed transport decisions."""

    CONNECTION_REFUSED = "connection_refused"
    PRECONNECT_FAILURE = "preconnect_failure"
    CONNECTION_RESET = "connection_reset"
    READ_TIMEOUT = "read_timeout"
    HTTP_ERROR = "http_error"
    INVALID_RESPONSE = "invalid_response"
    OVERSIZED_RESPONSE = "oversized_response"
    INVALID_REQUEST = "invalid_request"
    OTHER = "other"


class PistonTransportError(RuntimeError):
    """Raised when the loopback Piston HTTP boundary cannot return a valid bounded response."""

    def __init__(self, message: str, *, kind: PistonTransportFailureKind | None = None) -> None:
        super().__init__(message)
        self.kind = PistonTransportFailureKind.OTHER if kind is None else kind

    @property
    def safe_to_retry(self) -> bool:
        """Return true only when the execute request is proven not to have reached Piston."""
        return self.kind in {
            PistonTransportFailureKind.CONNECTION_REFUSED,
            PistonTransportFailureKind.PRECONNECT_FAILURE,
        }

    @property
    def remote_execution_ambiguous(self) -> bool:
        """Return true when a candidate POST may have reached the remote service."""
        return self.kind in {
            PistonTransportFailureKind.CONNECTION_RESET,
            PistonTransportFailureKind.READ_TIMEOUT,
            PistonTransportFailureKind.HTTP_ERROR,
            PistonTransportFailureKind.INVALID_RESPONSE,
            PistonTransportFailureKind.OVERSIZED_RESPONSE,
            PistonTransportFailureKind.OTHER,
        }


@dataclass(frozen=True)
class PistonExecutorConfig:
    """Validated settings for one loopback-only Piston executor."""

    base_url: str
    language: str
    version: str
    request_timeout_margin_seconds: float
    max_response_bytes: int
    max_output_bytes: int
    stop_on_first_failure: bool


class PistonTransport(Protocol):
    """Minimal synchronous transport used by :class:`PistonExecutor`."""

    def list_runtimes(
        self,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object: ...

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object: ...


class HttpClientPistonTransport:
    """Single-connection loopback HTTP/1.1 transport with fail-closed keep-alive reuse."""

    def __init__(self, base_url: str) -> None:
        """Create one lazy sequential persistent connection for a validated loopback Piston endpoint."""
        self._base_url = _validate_base_url(base_url)
        parsed = urlsplit(self._base_url)
        host = parsed.hostname
        assert host is not None
        self._host = host
        self._port = 80 if parsed.port is None else parsed.port
        self._connection: http.client.HTTPConnection | None = None
        self._lock = threading.Lock()

    def list_runtimes(
        self,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        """GET the bounded loopback /api/v2/runtimes JSON value."""
        return self._request_json(
            method="GET",
            path="/api/v2/runtimes",
            body=None,
            headers={"Accept": "application/json"},
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        """POST one bounded loopback /api/v2/execute JSON request without ambiguous replay."""
        try:
            body = json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, RecursionError, UnicodeEncodeError):
            raise PistonTransportError(
                "invalid piston request", kind=PistonTransportFailureKind.INVALID_REQUEST
            ) from None
        return self._request_json(
            method="POST",
            path="/api/v2/execute",
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )

    def close(self) -> None:
        """Discard the current persistent connection without affecting later lazy reconnects."""
        with self._lock:
            self._discard_connection()

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        if not _is_finite_positive_number(timeout_seconds):
            raise PistonTransportError("invalid piston timeout", kind=PistonTransportFailureKind.INVALID_REQUEST)
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
            raise PistonTransportError(
                "invalid piston response limit", kind=PistonTransportFailureKind.INVALID_REQUEST
            )

        with self._lock:
            connection = self._connection
            if connection is None or connection.sock is None:
                self._discard_connection()
                connection = self._connect(float(timeout_seconds))
            else:
                self._set_connection_timeout(connection, float(timeout_seconds))

            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
            except (TimeoutError, OSError, http.client.HTTPException) as error:
                self._discard_connection()
                raise _classified_ambiguous_http_error(error) from None

            try:
                if not 200 <= response.status < 300:
                    self._discard_connection()
                    raise PistonTransportError(
                        "piston http request failed", kind=PistonTransportFailureKind.HTTP_ERROR
                    )
                content_type = response.headers.get_content_type().lower()
                if content_type != "application/json" and not (
                    content_type.startswith("application/") and content_type.endswith("+json")
                ):
                    self._discard_connection()
                    raise PistonTransportError(
                        "piston returned non-json content", kind=PistonTransportFailureKind.INVALID_RESPONSE
                    )
                try:
                    raw = response.read(max_response_bytes + 1)
                except (TimeoutError, OSError, http.client.HTTPException) as error:
                    self._discard_connection()
                    raise _classified_ambiguous_http_error(error) from None
                should_close = response.will_close or response.headers.get("Connection", "").lower() == "close"
                if len(raw) > max_response_bytes:
                    self._discard_connection()
                    raise PistonTransportError(
                        "piston response exceeded limit", kind=PistonTransportFailureKind.OVERSIZED_RESPONSE
                    )
                response.close()
                if should_close or connection.sock is None:
                    self._discard_connection()
            except PistonTransportError:
                response.close()
                raise

        try:
            text = raw.decode("utf-8")
            return cast(object, json.loads(text, parse_constant=_reject_json_constant))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise PistonTransportError(
                "invalid piston json response", kind=PistonTransportFailureKind.INVALID_RESPONSE
            ) from None

    def _connect(self, timeout_seconds: float) -> http.client.HTTPConnection:
        connection = http.client.HTTPConnection(self._host, self._port, timeout=timeout_seconds)
        try:
            connection.connect()
        except (TimeoutError, OSError, http.client.HTTPException) as error:
            connection.close()
            raise _classified_transport_error(error) from None
        self._connection = connection
        return connection

    @staticmethod
    def _set_connection_timeout(connection: http.client.HTTPConnection, timeout_seconds: float) -> None:
        connection.timeout = timeout_seconds
        if connection.sock is not None:
            connection.sock.settimeout(timeout_seconds)

    def _discard_connection(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            connection.close()


def _classified_transport_error(error: BaseException) -> PistonTransportError:
    """Classify connection failures without leaking endpoint or payload details."""
    reason: object = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ConnectionRefusedError) or (
        isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED
    ):
        return PistonTransportError("piston connection refused", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    if isinstance(reason, socket.timeout | TimeoutError):
        return PistonTransportError("piston read timeout", kind=PistonTransportFailureKind.READ_TIMEOUT)
    if isinstance(reason, ConnectionResetError) or (
        isinstance(reason, OSError) and reason.errno in {errno.ECONNRESET, errno.EPIPE}
    ):
        return PistonTransportError("piston connection reset", kind=PistonTransportFailureKind.CONNECTION_RESET)
    if isinstance(reason, OSError) and reason.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL}:
        return PistonTransportError("piston pre-connect failure", kind=PistonTransportFailureKind.PRECONNECT_FAILURE)
    return PistonTransportError("piston transport failed", kind=PistonTransportFailureKind.OTHER)


def _classified_ambiguous_http_error(error: BaseException) -> PistonTransportError:
    """Classify failures after a connection exists without ever marking the current request safe to replay."""
    if isinstance(error, socket.timeout | TimeoutError):
        return PistonTransportError("piston read timeout", kind=PistonTransportFailureKind.READ_TIMEOUT)
    if isinstance(error, ConnectionResetError | BrokenPipeError | http.client.RemoteDisconnected) or (
        isinstance(error, OSError) and error.errno in {errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED}
    ):
        return PistonTransportError("piston connection reset", kind=PistonTransportFailureKind.CONNECTION_RESET)
    if isinstance(error, http.client.HTTPException):
        return PistonTransportError("piston response stream failed", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    return PistonTransportError("piston transport failed", kind=PistonTransportFailureKind.OTHER)


def piston_executor_config_from_mapping(value: object) -> PistonExecutorConfig:
    """Parse one exact execution.piston config mapping and reject unknown fields."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigError("Piston config must be an object with string keys")
    mapping = cast(dict[str, object], value)
    if set(mapping) != _CONFIG_FIELDS:
        raise ConfigError("Piston config fields do not match the required schema")

    base_url = _require_string(mapping["base_url"], field_name="base_url")
    language = _require_string(mapping["language"], field_name="language")
    version = _require_string(mapping["version"], field_name="version")
    margin = mapping["request_timeout_margin_seconds"]
    max_response_bytes = mapping["max_response_bytes"]
    max_output_bytes = mapping["max_output_bytes"]
    stop_on_first_failure = mapping["stop_on_first_failure"]

    normalized_url = _validate_base_url(base_url)
    if language != "python":
        raise ConfigError("Piston language must be exactly python")
    if not _is_exact_semver(version):
        raise ConfigError("Piston version must be an exact MAJOR.MINOR.PATCH value")
    if not _is_finite_positive_number(margin):
        raise ConfigError("request_timeout_margin_seconds must be a finite positive number")
    if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
        raise ConfigError("max_response_bytes must be a positive integer")
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes <= 0:
        raise ConfigError("max_output_bytes must be a positive integer")
    if max_response_bytes < 2 * max_output_bytes + 4096:
        raise ConfigError("max_response_bytes is too small for the configured output limit")
    if not isinstance(stop_on_first_failure, bool):
        raise ConfigError("stop_on_first_failure must be a boolean")

    return PistonExecutorConfig(
        base_url=normalized_url,
        language=language,
        version=version,
        request_timeout_margin_seconds=float(cast(int | float, margin)),
        max_response_bytes=max_response_bytes,
        max_output_bytes=max_output_bytes,
        stop_on_first_failure=stop_on_first_failure,
    )


def load_piston_executor_config(path: Path) -> PistonExecutorConfig:
    """Load and strictly validate one loopback Piston YAML config."""
    loaded = load_yaml_mapping(path)
    if set(loaded) != {"piston"}:
        raise ConfigError("Execution config must contain exactly the piston field")
    return piston_executor_config_from_mapping(loaded["piston"])


def piston_executor_version(config: PistonExecutorConfig) -> str:
    """Return a deterministic version string for all result-affecting Piston semantics."""
    if not isinstance(config, PistonExecutorConfig):
        raise ExecutionContractError("config must be a PistonExecutorConfig")
    payload = {
        "implementation_version": PISTON_EXECUTOR_IMPLEMENTATION_VERSION,
        "harness_protocol_version": harness_module.PYTHON_HARNESS_PROTOCOL_VERSION,
        "base_url": config.base_url,
        "language": config.language,
        "version": config.version,
        "request_timeout_margin_seconds_hex": config.request_timeout_margin_seconds.hex(),
        "max_response_bytes": config.max_response_bytes,
        "max_output_bytes": config.max_output_bytes,
        "stop_on_first_failure": config.stop_on_first_failure,
    }
    encoded = json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"piston:{hashlib.sha256(encoded).hexdigest()}"


def _validate_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ConfigError("Piston base_url is invalid") from None
    if parsed.scheme != "http":
        raise ConfigError("Piston base_url must use http")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError("Piston base_url must not contain userinfo")
    if parsed.hostname not in _LOOPBACK_HOSTS:
        raise ConfigError("Piston base_url must use a loopback host")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ConfigError("Piston base_url must not contain a path, query, or fragment")
    if port is not None and not 1 <= port <= 65535:
        raise ConfigError("Piston base_url port is invalid")
    host = parsed.hostname
    assert host is not None
    host_text = f"[{host}]" if ":" in host else host
    port_text = "" if port is None else f":{port}"
    return f"http://{host_text}{port_text}"


def _require_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{field_name} must be a non-empty string")
    return value


def _is_exact_semver(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(part.isascii() and part.isdigit() and str(int(part)) == part for part in parts)


def _is_finite_positive_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except OverflowError:
        return False


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


@dataclass(frozen=True)
class _PistonStageResult:
    stdout: str
    stderr: str
    code: int | None
    signal: str | None
    message: str | None
    status: str | None
    cpu_time_ms: float
    wall_time_ms: float
    memory_bytes: int | None


def _parse_piston_stage(value: object) -> _PistonStageResult:
    """Parse one exact bounded compile/run stage without coercing malformed fields."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    stage = cast(dict[str, object], value)
    allowed_fields = {
        "stdout",
        "stderr",
        "output",
        "code",
        "signal",
        "message",
        "status",
        "cpu_time",
        "wall_time",
        "memory",
    }
    if not {"stdout", "stderr"}.issubset(stage) or not set(stage).issubset(allowed_fields):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    stdout = stage["stdout"]
    stderr = stage["stderr"]
    code = stage.get("code")
    signal_value = stage.get("signal")
    message = stage.get("message")
    status = stage.get("status")
    cpu_time = stage.get("cpu_time", 0.0)
    wall_time = stage.get("wall_time", 0.0)
    memory = stage.get("memory")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    if code is not None and (isinstance(code, bool) or not isinstance(code, int)):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    if signal_value is not None and not isinstance(signal_value, str):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    if message is not None and not isinstance(message, str):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    if status is not None and not isinstance(status, str):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    cpu_time_ms = _require_non_negative_finite_number(cpu_time)
    wall_time_ms = _require_non_negative_finite_number(wall_time)
    if memory is not None and (isinstance(memory, bool) or not isinstance(memory, int) or memory < 0):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    return _PistonStageResult(
        stdout=stdout,
        stderr=stderr,
        code=code,
        signal=signal_value,
        message=message,
        status=status,
        cpu_time_ms=cpu_time_ms,
        wall_time_ms=wall_time_ms,
        memory_bytes=memory,
    )


def _map_piston_stage_failure(
    stage: _PistonStageResult,
    *,
    memory_limit_bytes: int,
) -> ExecutionStatus | None:
    """Map a failed Piston stage to one deterministic public execution status."""
    status = None if stage.status is None else stage.status.upper()
    signal_value = None if stage.signal is None else stage.signal.upper()
    message = "" if stage.message is None else stage.message.lower()
    if status == "TO":
        return ExecutionStatus.TIMEOUT
    if status in {"OL", "EL"}:
        return ExecutionStatus.OUTPUT_LIMIT
    if status == "XX":
        return ExecutionStatus.SANDBOX_ERROR
    if status == "SG" and "memory" in message:
        return ExecutionStatus.MEMORY_LIMIT
    if (
        (signal_value == "SIGKILL" or stage.code == 137)
        and stage.memory_bytes is not None
        and stage.memory_bytes >= math.ceil(memory_limit_bytes * 0.95)
    ):
        return ExecutionStatus.MEMORY_LIMIT
    if status in {"SG", "RE"}:
        return ExecutionStatus.RUNTIME_ERROR
    if stage.signal is not None or (stage.code is not None and stage.code != 0):
        return ExecutionStatus.RUNTIME_ERROR
    return None


class PistonExecutor:
    """Synchronous single-test-job executor backed by a loopback Piston service."""

    def __init__(
        self,
        config: PistonExecutorConfig,
        *,
        transport: PistonTransport | None = None,
        marker_factory: Callable[[], str] | None = None,
        transport_policy: PistonTransportPolicy | None = None,
        transport_telemetry: PistonTransportTelemetry | None = None,
        sleep: Callable[[float], None] = sleep_backoff,
    ) -> None:
        """Create a synchronous single-request executor backed by one loopback Piston service."""
        if transport_policy is not None:
            expected_url = (
                f"http://{transport_policy.health_probe.listener_host}:{transport_policy.health_probe.listener_port}"
            )
            if config.base_url != expected_url or config.version != transport_policy.health_probe.required_runtime:
                raise ExecutionContractError(
                    "Piston transport policy does not match executor endpoint/runtime identity"
                )
        self._config = config
        self._transport = transport if transport is not None else HttpClientPistonTransport(config.base_url)
        self._marker_factory = marker_factory if marker_factory is not None else lambda: secrets.token_hex(16)
        self._transport_policy = transport_policy
        self._transport_telemetry = (
            transport_telemetry if transport_telemetry is not None else PistonTransportTelemetry()
        )
        self._sleep = sleep

    @property
    def transport_telemetry(self) -> PistonTransportTelemetry:
        """Return cumulative payload-free telemetry owned by this executor instance."""
        return self._transport_telemetry

    def validate_runtime(self) -> str:
        """Require the configured exact Python runtime to be installed and return its version."""
        try:
            value = self._transport.list_runtimes(
                timeout_seconds=self._config.request_timeout_margin_seconds,
                max_response_bytes=self._config.max_response_bytes,
            )
            if not isinstance(value, list):
                raise PistonTransportError(
                    "invalid piston runtimes response",
                    kind=PistonTransportFailureKind.INVALID_RESPONSE,
                )
            matches = 0
            for record_value in value:
                if not isinstance(record_value, dict) or not all(isinstance(key, str) for key in record_value):
                    raise PistonTransportError(
                        "invalid piston runtimes response",
                        kind=PistonTransportFailureKind.INVALID_RESPONSE,
                    )
                record = cast(dict[str, object], record_value)
                if set(record) not in (
                    {"language", "version", "aliases"},
                    {"language", "version", "aliases", "runtime"},
                ):
                    raise PistonTransportError(
                        "invalid piston runtimes response",
                        kind=PistonTransportFailureKind.INVALID_RESPONSE,
                    )
                language = record["language"]
                version = record["version"]
                aliases = record["aliases"]
                runtime = record.get("runtime")
                if (
                    not isinstance(language, str)
                    or not isinstance(version, str)
                    or not isinstance(aliases, list)
                    or not all(isinstance(alias, str) for alias in aliases)
                    or (runtime is not None and not isinstance(runtime, str))
                ):
                    raise PistonTransportError(
                        "invalid piston runtimes response",
                        kind=PistonTransportFailureKind.INVALID_RESPONSE,
                    )
                if language == self._config.language and version == self._config.version:
                    matches += 1
            if matches != 1:
                raise PistonTransportError(
                    "configured piston runtime unavailable", kind=PistonTransportFailureKind.INVALID_RESPONSE
                )
        except PistonTransportError:
            raise
        except Exception:
            raise PistonTransportError("piston runtime validation failed") from None
        return self._config.version

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        """Execute tests in request order using one isolated Piston job per test."""
        validate_execution_request(code, function_name, tests, timeout_seconds, memory_limit_mb)
        if timeout_seconds > 3600.0:
            raise ExecutionContractError("timeout_seconds exceeds the supported Piston limit")
        timeout_ms = math.ceil(timeout_seconds * 1000.0)
        memory_limit_bytes = memory_limit_mb * 1024 * 1024
        copied_tests = copy.deepcopy(tests)
        total_tests = len(copied_tests)
        if total_tests == 0:
            result = ExecutionResult(
                status=ExecutionStatus.PASSED,
                passed_tests=0,
                total_tests=0,
                pass_rate=0.0,
                runtime_ms=0.0,
                test_results=[],
            )
            validate_execution_result(result)
            return result

        test_results: list[TestCaseResult] = []
        for test in copied_tests:
            test_result = self._execute_one(
                code,
                function_name,
                test,
                timeout_seconds=timeout_seconds,
                timeout_ms=timeout_ms,
                memory_limit_bytes=memory_limit_bytes,
            )
            test_results.append(test_result)
            if self._must_stop(test_result.status):
                break

        passed_tests = sum(test_result.passed for test_result in test_results)
        status = next(
            (test_result.status for test_result in test_results if test_result.status is not ExecutionStatus.PASSED),
            ExecutionStatus.PASSED,
        )
        result = ExecutionResult(
            status=status,
            passed_tests=passed_tests,
            total_tests=total_tests,
            pass_rate=passed_tests / total_tests,
            runtime_ms=sum(test_result.runtime_ms for test_result in test_results),
            test_results=list(test_results),
        )
        validate_execution_result(result)
        return ExecutionResult(
            status=result.status,
            passed_tests=result.passed_tests,
            total_tests=result.total_tests,
            pass_rate=result.pass_rate,
            runtime_ms=result.runtime_ms,
            test_results=list(result.test_results),
        )

    def _execute_one(
        self,
        code: str,
        function_name: str,
        test: dict[str, Any],
        *,
        timeout_seconds: float,
        timeout_ms: int,
        memory_limit_bytes: int,
    ) -> TestCaseResult:
        marker = self._marker_factory()
        program = build_python_test_program(
            code,
            function_name,
            test,
            marker=marker,
            max_output_bytes=self._config.max_output_bytes,
        )
        payload: dict[str, object] = {
            "language": self._config.language,
            "version": self._config.version,
            "files": program.files,
            "stdin": program.stdin,
            "args": [],
            "compile_timeout": timeout_ms,
            "run_timeout": timeout_ms,
            "compile_cpu_time": timeout_ms,
            "run_cpu_time": timeout_ms,
            "compile_memory_limit": memory_limit_bytes,
            "run_memory_limit": memory_limit_bytes,
        }
        start = time.monotonic()
        try:
            response = self._execute_request_with_retry(
                payload,
                timeout_seconds=timeout_seconds + self._config.request_timeout_margin_seconds,
                max_response_bytes=self._config.max_response_bytes,
            )
        except PistonTransportError:
            return TestCaseResult(
                status=ExecutionStatus.SANDBOX_ERROR,
                passed=False,
                runtime_ms=max(0.0, (time.monotonic() - start) * 1000.0),
                stdout="",
                stderr="piston transport failed",
            )
        try:
            return self._parse_single_response(
                response,
                marker=marker,
                memory_limit_bytes=memory_limit_bytes,
                fallback_runtime_ms=max(0.0, (time.monotonic() - start) * 1000.0),
            )
        except PistonTransportError as error:
            if error.remote_execution_ambiguous:
                self._transport_telemetry.record_ambiguous_failure()
            return TestCaseResult(
                status=ExecutionStatus.SANDBOX_ERROR,
                passed=False,
                runtime_ms=max(0.0, (time.monotonic() - start) * 1000.0),
                stdout="",
                stderr="piston transport failed",
            )
        except Exception:
            return TestCaseResult(
                status=ExecutionStatus.SANDBOX_ERROR,
                passed=False,
                runtime_ms=max(0.0, (time.monotonic() - start) * 1000.0),
                stdout="",
                stderr="invalid piston response",
            )

    def _execute_request_with_retry(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        policy = self._transport_policy
        max_attempts = 1 if policy is None else policy.max_attempts
        had_retry = False
        for attempt in range(max_attempts):
            try:
                try:
                    response = self._transport.execute_request(
                        payload,
                        timeout_seconds=timeout_seconds,
                        max_response_bytes=max_response_bytes,
                    )
                finally:
                    self._transport_telemetry.record_transport_request()
            except PistonTransportError as error:
                if error.kind in {
                    PistonTransportFailureKind.CONNECTION_REFUSED,
                    PistonTransportFailureKind.PRECONNECT_FAILURE,
                }:
                    self._transport_telemetry.record_connect_failure()
                if policy is None or not error.safe_to_retry:
                    if error.remote_execution_ambiguous:
                        self._transport_telemetry.record_ambiguous_failure()
                    raise
                if error.kind.value not in policy.safe_retry_kinds:
                    raise
                if attempt + 1 >= max_attempts:
                    self._transport_telemetry.record_retry_exhausted()
                    raise
                self._wait_for_retry_health(policy, retry_index=attempt)
                self._transport_telemetry.record_safe_retry()
                had_retry = True
                continue
            if had_retry:
                self._transport_telemetry.record_retry_success()
            return response
        raise PistonTransportError("piston retry state invalid")

    def _wait_for_retry_health(self, policy: PistonTransportPolicy, *, retry_index: int) -> None:
        """Wait boundedly for endpoint health, then revalidate exact runtime before resend."""
        self._sleep(policy.delay_for_retry(retry_index))
        for health_index in range(policy.health_probe.max_wait_attempts):
            try:
                if self.validate_runtime() != policy.health_probe.required_runtime:
                    raise PistonTransportError("piston recovery runtime identity mismatch")
            except PistonTransportError as error:
                if error.safe_to_retry and health_index + 1 < policy.health_probe.max_wait_attempts:
                    self._sleep(policy.health_probe.delay_for_retry(health_index))
                    continue
                self._transport_telemetry.record_retry_exhausted()
                raise
            return
        self._transport_telemetry.record_retry_exhausted()
        raise PistonTransportError(
            "piston recovery endpoint did not become healthy",
            kind=PistonTransportFailureKind.CONNECTION_REFUSED,
        )

    def _parse_single_response(
        self,
        value: object,
        *,
        marker: str,
        memory_limit_bytes: int,
        fallback_runtime_ms: float,
    ) -> TestCaseResult:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
        response = cast(dict[str, object], value)
        if "run" not in response or not set(response).issubset({"language", "version", "compile", "run"}):
            raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
        if "compile" in response:
            compile_stage = _parse_piston_stage(response["compile"])
            if _map_piston_stage_failure(compile_stage, memory_limit_bytes=memory_limit_bytes) is not None:
                return TestCaseResult(
                    status=ExecutionStatus.SANDBOX_ERROR,
                    passed=False,
                    runtime_ms=compile_stage.wall_time_ms,
                    stdout="",
                    stderr="piston compile stage failed",
                )
        run_stage = _parse_piston_stage(response["run"])
        failure_status = _map_piston_stage_failure(run_stage, memory_limit_bytes=memory_limit_bytes)
        if failure_status is not None:
            return TestCaseResult(
                status=failure_status,
                passed=False,
                runtime_ms=run_stage.wall_time_ms or fallback_runtime_ms,
                stdout=_bounded_text(run_stage.stdout, self._config.max_output_bytes),
                stderr=_bounded_text(run_stage.stderr, self._config.max_output_bytes),
            )
        report = parse_harness_report(
            run_stage.stdout,
            marker=marker,
            max_output_bytes=self._config.max_output_bytes,
        )
        if report is None:
            return TestCaseResult(
                status=ExecutionStatus.SANDBOX_ERROR,
                passed=False,
                runtime_ms=run_stage.wall_time_ms or fallback_runtime_ms,
                stdout="",
                stderr="invalid harness report",
            )
        return _test_case_result_from_harness(report)

    def _must_stop(self, status: ExecutionStatus) -> bool:
        if status is ExecutionStatus.PASSED:
            return False
        if self._config.stop_on_first_failure:
            return True
        return status in {
            ExecutionStatus.SYNTAX_ERROR,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.MEMORY_LIMIT,
            ExecutionStatus.OUTPUT_LIMIT,
            ExecutionStatus.SANDBOX_ERROR,
        }


def _test_case_result_from_harness(report: HarnessReport) -> TestCaseResult:
    status_mapping: dict[str, ExecutionStatus] = {
        "passed": ExecutionStatus.PASSED,
        "wrong_answer": ExecutionStatus.WRONG_ANSWER,
        "syntax_error": ExecutionStatus.SYNTAX_ERROR,
        "runtime_error": ExecutionStatus.RUNTIME_ERROR,
        "output_limit": ExecutionStatus.OUTPUT_LIMIT,
        "harness_error": ExecutionStatus.SANDBOX_ERROR,
    }
    status = status_mapping[report.outcome]
    return TestCaseResult(
        status=status,
        passed=status is ExecutionStatus.PASSED,
        runtime_ms=report.runtime_ms,
        stdout=report.stdout,
        stderr=report.stderr,
    )


def _require_non_negative_finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    try:
        converted = float(value)
    except OverflowError:
        raise PistonTransportError(
            "invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE
        ) from None
    if not math.isfinite(converted) or converted < 0:
        raise PistonTransportError("invalid piston response", kind=PistonTransportFailureKind.INVALID_RESPONSE)
    return converted


def _bounded_text(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")
