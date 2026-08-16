"""Loopback-only HTTP boundary for a Piston executor.

The backend may be local or reached through an SSH local forward. Project
configuration intentionally accepts only loopback HTTP endpoints in either mode.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, ProxyHandler, Request, build_opener

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


class PistonTransportError(RuntimeError):
    """Raised when the loopback Piston HTTP boundary cannot return a valid bounded response."""


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


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


class UrlLibPistonTransport:
    """No-proxy, no-redirect urllib transport for one validated loopback endpoint."""

    def __init__(self, base_url: str) -> None:
        """Create a no-proxy, no-redirect transport for one validated loopback Piston base URL."""
        self._base_url = _validate_base_url(base_url)
        self._opener: OpenerDirector = build_opener(ProxyHandler({}), _RejectRedirects())

    def list_runtimes(
        self,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        """GET the bounded loopback /api/v2/runtimes JSON value."""
        request = Request(f"{self._base_url}/api/v2/runtimes", method="GET")
        return self._request_json(request, timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes)

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        """POST one bounded loopback /api/v2/execute JSON request."""
        try:
            body = json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, RecursionError, UnicodeEncodeError):
            raise PistonTransportError("invalid piston request") from None
        request = Request(
            f"{self._base_url}/api/v2/execute",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        return self._request_json(request, timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes)

    def _request_json(self, request: Request, *, timeout_seconds: float, max_response_bytes: int) -> object:
        if not _is_finite_positive_number(timeout_seconds):
            raise PistonTransportError("invalid piston timeout")
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
            raise PistonTransportError("invalid piston response limit")
        try:
            with self._opener.open(request, timeout=float(timeout_seconds)) as response:
                content_type = response.headers.get_content_type().lower()
                if content_type != "application/json" and not (
                    content_type.startswith("application/") and content_type.endswith("+json")
                ):
                    raise PistonTransportError("piston returned non-json content")
                raw = response.read(max_response_bytes + 1)
        except PistonTransportError:
            raise
        except HTTPError:
            raise PistonTransportError("piston http request failed") from None
        except (URLError, TimeoutError, OSError):
            raise PistonTransportError("piston transport failed") from None

        if len(raw) > max_response_bytes:
            raise PistonTransportError("piston response exceeded limit")
        try:
            text = raw.decode("utf-8")
            return cast(object, json.loads(text, parse_constant=_reject_json_constant))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise PistonTransportError("invalid piston json response") from None


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
        raise PistonTransportError("invalid piston response")
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
        raise PistonTransportError("invalid piston response")
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
        raise PistonTransportError("invalid piston response")
    if code is not None and (isinstance(code, bool) or not isinstance(code, int)):
        raise PistonTransportError("invalid piston response")
    if signal_value is not None and not isinstance(signal_value, str):
        raise PistonTransportError("invalid piston response")
    if message is not None and not isinstance(message, str):
        raise PistonTransportError("invalid piston response")
    if status is not None and not isinstance(status, str):
        raise PistonTransportError("invalid piston response")
    cpu_time_ms = _require_non_negative_finite_number(cpu_time)
    wall_time_ms = _require_non_negative_finite_number(wall_time)
    if memory is not None and (isinstance(memory, bool) or not isinstance(memory, int) or memory < 0):
        raise PistonTransportError("invalid piston response")
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
    ) -> None:
        """Create a synchronous single-request executor backed by one loopback Piston service."""
        self._config = config
        self._transport = transport if transport is not None else UrlLibPistonTransport(config.base_url)
        self._marker_factory = marker_factory if marker_factory is not None else lambda: secrets.token_hex(16)

    def validate_runtime(self) -> str:
        """Require the configured exact Python runtime to be installed and return its version."""
        try:
            value = self._transport.list_runtimes(
                timeout_seconds=self._config.request_timeout_margin_seconds,
                max_response_bytes=self._config.max_response_bytes,
            )
            if not isinstance(value, list):
                raise PistonTransportError("invalid piston runtimes response")
            matches = 0
            for record_value in value:
                if not isinstance(record_value, dict) or not all(isinstance(key, str) for key in record_value):
                    raise PistonTransportError("invalid piston runtimes response")
                record = cast(dict[str, object], record_value)
                if set(record) not in (
                    {"language", "version", "aliases"},
                    {"language", "version", "aliases", "runtime"},
                ):
                    raise PistonTransportError("invalid piston runtimes response")
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
                    raise PistonTransportError("invalid piston runtimes response")
                if language == self._config.language and version == self._config.version:
                    matches += 1
            if matches != 1:
                raise PistonTransportError("configured piston runtime unavailable")
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
            response = self._transport.execute_request(
                payload,
                timeout_seconds=timeout_seconds + self._config.request_timeout_margin_seconds,
                max_response_bytes=self._config.max_response_bytes,
            )
            return self._parse_single_response(
                response,
                marker=marker,
                memory_limit_bytes=memory_limit_bytes,
                fallback_runtime_ms=max(0.0, (time.monotonic() - start) * 1000.0),
            )
        except PistonTransportError:
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

    def _parse_single_response(
        self,
        value: object,
        *,
        marker: str,
        memory_limit_bytes: int,
        fallback_runtime_ms: float,
    ) -> TestCaseResult:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise PistonTransportError("invalid piston response")
        response = cast(dict[str, object], value)
        if "run" not in response or not set(response).issubset({"language", "version", "compile", "run"}):
            raise PistonTransportError("invalid piston response")
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
        raise PistonTransportError("invalid piston response")
    try:
        converted = float(value)
    except OverflowError:
        raise PistonTransportError("invalid piston response") from None
    if not math.isfinite(converted) or converted < 0:
        raise PistonTransportError("invalid piston response")
    return converted


def _bounded_text(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")
