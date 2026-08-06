"""Unit tests for strict local Piston configuration and transport behavior."""

from __future__ import annotations

import io
import json
import math
from dataclasses import replace
from email.message import Message
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request

import pytest

from code_verifier.config import ConfigError
from code_verifier.execution import (
    CodeExecutor,
    ExecutionContractError,
    ExecutionStatus,
    PistonExecutor,
    execution_result_to_mapping,
    piston_executor_version,
)
from code_verifier.execution import harness as harness_module
from code_verifier.execution import piston as piston_module
from code_verifier.execution.piston import (
    PistonTransportError,
    UrlLibPistonTransport,
    load_piston_executor_config,
    piston_executor_config_from_mapping,
)


def _valid_mapping() -> dict[str, object]:
    return {
        "base_url": "http://127.0.0.1:2000",
        "language": "python",
        "version": "3.10.0",
        "request_timeout_margin_seconds": 2.0,
        "max_response_bytes": 131072,
        "max_output_bytes": 4096,
        "stop_on_first_failure": False,
    }


def test_piston_executor_version_is_stable_and_well_formed() -> None:
    config = piston_executor_config_from_mapping(_valid_mapping())
    first = piston_executor_version(config)
    second = piston_executor_version(config)
    assert first == second
    assert first.startswith("piston:")
    digest = first.removeprefix("piston:")
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(character in "0123456789abcdef" for character in digest)


def test_piston_executor_version_changes_with_every_piston_config_field() -> None:
    config = piston_executor_config_from_mapping(_valid_mapping())
    baseline = piston_executor_version(config)
    variants = [
        replace(config, base_url="http://localhost:2000"),
        replace(config, language="python-alt"),
        replace(config, version="3.11.0"),
        replace(config, request_timeout_margin_seconds=3.0),
        replace(config, max_response_bytes=config.max_response_bytes + 1),
        replace(config, max_output_bytes=config.max_output_bytes + 1),
        replace(config, stop_on_first_failure=True),
    ]
    assert all(piston_executor_version(variant) != baseline for variant in variants)


def test_piston_executor_version_changes_with_harness_and_implementation_protocol_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = piston_executor_config_from_mapping(_valid_mapping())
    baseline = piston_executor_version(config)
    monkeypatch.setattr(harness_module, "PYTHON_HARNESS_PROTOCOL_VERSION", "trusted-parent-v2")
    assert piston_executor_version(config) != baseline
    monkeypatch.setattr(harness_module, "PYTHON_HARNESS_PROTOCOL_VERSION", "trusted-parent-v1")
    monkeypatch.setattr(piston_module, "PISTON_EXECUTOR_IMPLEMENTATION_VERSION", "piston-executor-v2")
    assert piston_executor_version(config) != baseline


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self._body = io.BytesIO(body)
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeOpener:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.requests: list[Request] = []
        self.timeouts: list[float] = []

    def open(self, request: Request, *, timeout: float) -> Any:
        self.requests.append(request)
        self.timeouts.append(timeout)
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_piston_config_accepts_exact_local_mapping(tmp_path: Path) -> None:
    config = piston_executor_config_from_mapping(_valid_mapping())
    assert config.base_url == "http://127.0.0.1:2000"
    assert config.language == "python"
    assert config.version == "3.10.0"

    config_path = tmp_path / "piston.yaml"
    config_path.write_text(
        "piston:\n"
        "  base_url: http://localhost:2000/\n"
        "  language: python\n"
        '  version: "3.10.0"\n'
        "  request_timeout_margin_seconds: 2.0\n"
        "  max_response_bytes: 131072\n"
        "  max_output_bytes: 4096\n"
        "  stop_on_first_failure: false\n",
        encoding="utf-8",
    )
    assert load_piston_executor_config(config_path).base_url == "http://localhost:2000"


def test_piston_config_rejects_missing_and_unknown_fields() -> None:
    missing = _valid_mapping()
    del missing["version"]
    unknown = _valid_mapping()
    unknown["token"] = "secret"
    with pytest.raises(ConfigError):
        piston_executor_config_from_mapping(missing)
    with pytest.raises(ConfigError):
        piston_executor_config_from_mapping(unknown)
    with pytest.raises(ConfigError):
        piston_executor_config_from_mapping({"piston": _valid_mapping()})


def test_piston_config_rejects_remote_userinfo_query_fragment_and_path() -> None:
    invalid_urls = [
        "https://127.0.0.1:2000",
        "http://example.com:2000",
        "http://user@127.0.0.1:2000",
        "http://127.0.0.1:2000/api",
        "http://127.0.0.1:2000?next=http://example.com",
        "http://127.0.0.1:2000#fragment",
    ]
    for invalid_url in invalid_urls:
        mapping = _valid_mapping()
        mapping["base_url"] = invalid_url
        with pytest.raises(ConfigError):
            piston_executor_config_from_mapping(mapping)


def test_piston_config_rejects_runtime_selectors_and_non_python_language() -> None:
    for version in ["*", "3", "3.x", "03.10.0", "3.10", "3.10.0-beta"]:
        mapping = _valid_mapping()
        mapping["version"] = version
        with pytest.raises(ConfigError):
            piston_executor_config_from_mapping(mapping)
    mapping = _valid_mapping()
    mapping["language"] = "python3"
    with pytest.raises(ConfigError):
        piston_executor_config_from_mapping(mapping)


def test_piston_config_rejects_invalid_limits_and_bool_numbers() -> None:
    invalid_values = [
        ("request_timeout_margin_seconds", 0),
        ("request_timeout_margin_seconds", True),
        ("request_timeout_margin_seconds", float("inf")),
        ("max_response_bytes", True),
        ("max_response_bytes", 0),
        ("max_output_bytes", True),
        ("max_output_bytes", 0),
        ("stop_on_first_failure", 1),
    ]
    for field, value in invalid_values:
        mapping = _valid_mapping()
        mapping[field] = value
        with pytest.raises(ConfigError):
            piston_executor_config_from_mapping(mapping)
    too_small = _valid_mapping()
    too_small["max_response_bytes"] = 2 * 4096 + 4095
    with pytest.raises(ConfigError):
        piston_executor_config_from_mapping(too_small)


def test_transport_builds_exact_runtime_and_execute_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = _FakeOpener([_FakeResponse(b"[]"), _FakeResponse(b'{"run":{}}')])
    monkeypatch.setattr(piston_module, "build_opener", lambda *handlers: opener)
    transport = UrlLibPistonTransport("http://127.0.0.1:2000/")

    assert transport.list_runtimes(timeout_seconds=1.5, max_response_bytes=64) == []
    payload: dict[str, object] = {"language": "python", "files": []}
    assert transport.execute_request(payload, timeout_seconds=2.5, max_response_bytes=64) == {"run": {}}

    assert [request.full_url for request in opener.requests] == [
        "http://127.0.0.1:2000/api/v2/runtimes",
        "http://127.0.0.1:2000/api/v2/execute",
    ]
    assert opener.requests[0].get_method() == "GET"
    assert opener.requests[1].get_method() == "POST"
    assert json.loads(cast(bytes, opener.requests[1].data)) == payload
    assert opener.requests[1].get_header("Content-type") == "application/json"
    assert opener.timeouts == [1.5, 2.5]


def test_transport_rejects_non_utf8_request_payload_without_network() -> None:
    transport = UrlLibPistonTransport("http://127.0.0.1:2000")
    with pytest.raises(PistonTransportError, match="invalid piston request"):
        transport.execute_request(
            {"language": "python", "source": "\ud800"},
            timeout_seconds=1.0,
            max_response_bytes=64,
        )


def test_transport_disables_proxy_and_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_handlers: tuple[object, ...] = ()
    opener = _FakeOpener([_FakeResponse(b"[]")])

    def fake_build_opener(*handlers: object) -> _FakeOpener:
        nonlocal captured_handlers
        captured_handlers = handlers
        return opener

    monkeypatch.setattr(piston_module, "build_opener", fake_build_opener)
    transport = UrlLibPistonTransport("http://localhost:2000")
    transport.list_runtimes(timeout_seconds=1.0, max_response_bytes=16)

    proxy_handler = next(handler for handler in captured_handlers if isinstance(handler, ProxyHandler))
    redirect_handler = next(handler for handler in captured_handlers if isinstance(handler, HTTPRedirectHandler))
    assert cast(Any, proxy_handler).proxies == {}
    assert type(redirect_handler).__name__ == "_RejectRedirects"


def test_transport_rejects_non_json_and_oversized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = _FakeOpener([_FakeResponse(b"{}", "text/plain"), _FakeResponse(b"0123456789")])
    monkeypatch.setattr(piston_module, "build_opener", lambda *handlers: opener)
    transport = UrlLibPistonTransport("http://127.0.0.1:2000")
    with pytest.raises(PistonTransportError, match="non-json"):
        transport.list_runtimes(timeout_seconds=1.0, max_response_bytes=8)
    with pytest.raises(PistonTransportError, match="exceeded"):
        transport.list_runtimes(timeout_seconds=1.0, max_response_bytes=8)


def test_transport_sanitizes_http_and_json_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "HIDDEN_RESPONSE_SENTINEL"
    error = HTTPError("http://127.0.0.1:2000", 500, sentinel, Message(), io.BytesIO(sentinel.encode()))
    opener = _FakeOpener([error, _FakeResponse(sentinel.encode())])
    monkeypatch.setattr(piston_module, "build_opener", lambda *handlers: opener)
    transport = UrlLibPistonTransport("http://127.0.0.1:2000")

    with pytest.raises(PistonTransportError) as http_error:
        transport.list_runtimes(timeout_seconds=1.0, max_response_bytes=128)
    assert sentinel not in str(http_error.value)
    with pytest.raises(PistonTransportError) as json_error:
        transport.list_runtimes(timeout_seconds=1.0, max_response_bytes=128)
    assert sentinel not in str(json_error.value)


class _FakeTransport:
    def __init__(self, *, runtimes: object | None = None, responses: list[object] | None = None) -> None:
        self.runtimes = [] if runtimes is None else runtimes
        self.responses = [] if responses is None else list(responses)
        self.runtime_calls = 0
        self.execute_calls: list[tuple[dict[str, object], float, int]] = []

    def list_runtimes(self, *, timeout_seconds: float, max_response_bytes: int) -> object:
        self.runtime_calls += 1
        if isinstance(self.runtimes, BaseException):
            raise self.runtimes
        return self.runtimes

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        self.execute_calls.append((payload, timeout_seconds, max_response_bytes))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _runtime_record(version: str = "3.10.0") -> dict[str, object]:
    return {"language": "python", "version": version, "aliases": ["py3"], "runtime": "python"}


def _harness_line(
    outcome: str,
    *,
    marker: str = "fixedmarker123",
    stdout: str = "",
    stderr: str = "",
    runtime_ms: float = 1.5,
) -> str:
    report = json.dumps(
        {"outcome": outcome, "runtime_ms": runtime_ms, "stdout": stdout, "stderr": stderr},
        separators=(",", ":"),
    )
    return f"__CODE_VERIFIER_RESULT__:{marker}:{report}\n"


def _run_response(
    *,
    outcome: str = "passed",
    marker: str = "fixedmarker123",
    status: str | None = None,
    code: int | None = 0,
    signal: str | None = None,
    message: str | None = None,
    memory: int | None = 1024,
    stdout: str | None = None,
    stderr: str = "",
) -> dict[str, object]:
    stage: dict[str, object] = {
        "stdout": _harness_line(outcome, marker=marker) if stdout is None else stdout,
        "stderr": stderr,
        "code": code,
        "signal": signal,
        "message": message,
        "status": status,
        "cpu_time": 1.0,
        "wall_time": 2.0,
        "memory": memory,
    }
    return {"language": "python", "version": "3.10.0", "run": stage}


def _executor(
    responses: list[object],
    *,
    stop_on_first_failure: bool = False,
    runtimes: object | None = None,
) -> tuple[PistonExecutor, _FakeTransport]:
    mapping = _valid_mapping()
    mapping["stop_on_first_failure"] = stop_on_first_failure
    transport = _FakeTransport(
        runtimes=[_runtime_record()] if runtimes is None else runtimes,
        responses=responses,
    )
    executor = PistonExecutor(
        piston_executor_config_from_mapping(mapping),
        transport=transport,
        marker_factory=lambda: "fixedmarker123",
    )
    return executor, transport


def _execute(executor: PistonExecutor, tests: list[dict[str, Any]] | None = None) -> Any:
    selected_tests = [{"input": [1], "expected": 1}] if tests is None else tests
    return executor.execute("def target(value):\n    return value\n", "target", selected_tests, 1.25, 32)


def test_validate_runtime_requires_exact_installed_python_version() -> None:
    executor, transport = _executor([], runtimes=[_runtime_record()])
    assert executor.validate_runtime() == "3.10.0"
    assert transport.runtime_calls == 1

    unavailable, _ = _executor([], runtimes=[_runtime_record("3.11.0")])
    with pytest.raises(PistonTransportError, match="unavailable"):
        unavailable.validate_runtime()


def test_validate_runtime_rejects_duplicate_and_malformed_runtime_records() -> None:
    duplicate, _ = _executor([], runtimes=[_runtime_record(), _runtime_record()])
    with pytest.raises(PistonTransportError):
        duplicate.validate_runtime()
    malformed, _ = _executor([], runtimes=[{"language": "python", "version": "3.10.0"}])
    with pytest.raises(PistonTransportError):
        malformed.validate_runtime()


def test_execute_payload_contains_exact_files_stdin_and_resource_limits() -> None:
    executor, transport = _executor([_run_response()])
    result = _execute(executor)
    assert result.status is ExecutionStatus.PASSED
    payload, timeout_seconds, max_response_bytes = transport.execute_calls[0]
    assert set(payload) == {
        "language",
        "version",
        "files",
        "stdin",
        "args",
        "compile_timeout",
        "run_timeout",
        "compile_cpu_time",
        "run_cpu_time",
        "compile_memory_limit",
        "run_memory_limit",
    }
    files = cast(list[dict[str, str]], payload["files"])
    assert [file_record["name"] for file_record in files] == ["main.py", "candidate.py"]
    assert files[1]["content"] == "def target(value):\n    return value\n"
    stdin = json.loads(cast(str, payload["stdin"]))
    assert stdin["input"] == [1]
    assert stdin["expected"] == 1
    assert payload["run_timeout"] == 1250
    assert payload["compile_cpu_time"] == 1250
    assert payload["run_memory_limit"] == 32 * 1024 * 1024
    assert timeout_seconds == 3.25
    assert max_response_bytes == 131072


@pytest.mark.parametrize("timeout_seconds", [3600.0001, 1e308, float.fromhex("0x1.fffffffffffffp+1023")])
def test_execute_rejects_timeouts_above_supported_limit_without_overflow(timeout_seconds: float) -> None:
    executor, transport = _executor([])
    with pytest.raises(ExecutionContractError, match="supported Piston limit"):
        executor.execute(
            "def target(value):\n    return value\n",
            "target",
            [{"input": 1, "expected": 1}],
            timeout_seconds,
            32,
        )
    assert transport.execute_calls == []


def test_execute_accepts_exact_timeout_limit() -> None:
    executor, transport = _executor([_run_response()])
    result = executor.execute(
        "def target(value):\n    return value\n",
        "target",
        [{"input": 1, "expected": 1}],
        3600.0,
        32,
    )
    assert result.status is ExecutionStatus.PASSED
    payload, timeout_seconds, _ = transport.execute_calls[0]
    assert payload["run_timeout"] == 3_600_000
    assert timeout_seconds == 3602.0


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("passed", ExecutionStatus.PASSED),
        ("wrong_answer", ExecutionStatus.WRONG_ANSWER),
        ("syntax_error", ExecutionStatus.SYNTAX_ERROR),
        ("runtime_error", ExecutionStatus.RUNTIME_ERROR),
        ("output_limit", ExecutionStatus.OUTPUT_LIMIT),
    ],
)
def test_execute_maps_harness_pass_wrong_answer_syntax_runtime_and_output_limit(
    outcome: str,
    expected_status: ExecutionStatus,
) -> None:
    executor, _ = _executor([_run_response(outcome=outcome)])
    result = _execute(executor)
    assert result.status is expected_status
    assert result.test_results[0].status is expected_status


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (_run_response(status="TO", code=None), ExecutionStatus.TIMEOUT),
        (_run_response(status="OL", code=None), ExecutionStatus.OUTPUT_LIMIT),
        (_run_response(status="EL", code=None), ExecutionStatus.OUTPUT_LIMIT),
        (_run_response(status="XX", code=None), ExecutionStatus.SANDBOX_ERROR),
        (_run_response(status="RE", code=1), ExecutionStatus.RUNTIME_ERROR),
        (_run_response(status="SG", code=None, signal="SIGTERM"), ExecutionStatus.RUNTIME_ERROR),
    ],
)
def test_execute_maps_piston_timeout_output_internal_and_signal_statuses(
    response: dict[str, object],
    expected_status: ExecutionStatus,
) -> None:
    executor, _ = _executor([response])
    assert _execute(executor).status is expected_status


def test_execute_maps_memory_signal_only_with_message_or_threshold() -> None:
    memory_limit = 32 * 1024 * 1024
    with_message, _ = _executor([_run_response(status="SG", signal="SIGKILL", message="memory limit")])
    assert _execute(with_message).status is ExecutionStatus.MEMORY_LIMIT
    near_limit, _ = _executor([_run_response(status="SG", signal="SIGKILL", memory=math.ceil(memory_limit * 0.95))])
    assert _execute(near_limit).status is ExecutionStatus.MEMORY_LIMIT
    exit_137, _ = _executor([_run_response(status="RE", code=137, memory=math.ceil(memory_limit * 0.95))])
    assert _execute(exit_137).status is ExecutionStatus.MEMORY_LIMIT
    below_limit, _ = _executor([_run_response(status="SG", signal="SIGKILL", memory=1024)])
    assert _execute(below_limit).status is ExecutionStatus.RUNTIME_ERROR


def test_execute_missing_or_spoofed_marker_is_sandbox_error() -> None:
    missing, _ = _executor([_run_response(stdout="ordinary output")])
    assert _execute(missing).status is ExecutionStatus.SANDBOX_ERROR
    spoofed, _ = _executor([_run_response(marker="wrongmarker")])
    assert _execute(spoofed).status is ExecutionStatus.SANDBOX_ERROR


def test_execute_transport_error_is_sanitized_sandbox_error() -> None:
    sentinel = "PRIVATE_TRANSPORT_SENTINEL"
    executor, _ = _executor([PistonTransportError(sentinel)])
    result = _execute(executor)
    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert sentinel not in result.test_results[0].stderr
    assert result.test_results[0].stderr == "piston transport failed"


def test_execute_empty_tests_does_not_call_transport() -> None:
    executor, transport = _executor([])
    result = _execute(executor, [])
    assert result.status is ExecutionStatus.PASSED
    assert result.total_tests == 0
    assert result.pass_rate == 0.0
    assert result.test_results == []
    assert transport.execute_calls == []


@pytest.mark.parametrize("failure_outcome", ["wrong_answer", "runtime_error"])
def test_execute_stop_on_first_failure_controls_wrong_answer_and_runtime_error(failure_outcome: str) -> None:
    tests = [{"input": [1], "expected": 1}, {"input": [2], "expected": 2}]
    continuing, continuing_transport = _executor(
        [_run_response(outcome=failure_outcome), _run_response(outcome="passed")],
        stop_on_first_failure=False,
    )
    assert len(_execute(continuing, tests).test_results) == 2
    assert len(continuing_transport.execute_calls) == 2
    stopping, stopping_transport = _executor(
        [_run_response(outcome=failure_outcome), _run_response(outcome="passed")],
        stop_on_first_failure=True,
    )
    assert len(_execute(stopping, tests).test_results) == 1
    assert len(stopping_transport.execute_calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        _run_response(status="TO", code=None),
        _run_response(status="OL", code=None),
        _run_response(status="SG", signal="SIGKILL", message="memory limit"),
        _run_response(status="XX", code=None),
        _run_response(outcome="syntax_error"),
    ],
)
def test_execute_always_stops_on_resource_and_infrastructure_failures(response: dict[str, object]) -> None:
    executor, transport = _executor([response, _run_response()])
    result = _execute(executor, [{"input": [1], "expected": 1}, {"input": [2], "expected": 2}])
    assert len(result.test_results) == 1
    assert len(transport.execute_calls) == 1


def test_execute_preserves_test_order_and_pass_rate_denominator() -> None:
    executor, _ = _executor(
        [_run_response(outcome="passed"), _run_response(outcome="wrong_answer"), _run_response(outcome="passed")]
    )
    result = _execute(
        executor,
        [
            {"input": [1], "expected": 1},
            {"input": [2], "expected": 2},
            {"input": [3], "expected": 3},
        ],
    )
    assert [item.status for item in result.test_results] == [
        ExecutionStatus.PASSED,
        ExecutionStatus.WRONG_ANSWER,
        ExecutionStatus.PASSED,
    ]
    assert result.status is ExecutionStatus.WRONG_ANSWER
    assert result.passed_tests == 2
    assert result.total_tests == 3
    assert result.pass_rate == pytest.approx(2 / 3)


def test_execute_returns_result_accepted_by_execution_contract_and_json_mapping() -> None:
    executor, _ = _executor([_run_response(stdout=_harness_line("passed", stdout="visible"))])
    result = _execute(executor)
    mapping = execution_result_to_mapping(result)
    assert json.loads(json.dumps(mapping, allow_nan=False)) == mapping
    assert mapping["status"] == "passed"


def test_piston_executor_satisfies_code_executor_protocol_under_mypy() -> None:
    executor, _ = _executor([_run_response()])
    protocol_executor: CodeExecutor = executor
    assert _execute(cast(PistonExecutor, protocol_executor)).status is ExecutionStatus.PASSED


def test_result_and_errors_do_not_echo_code_input_expected_marker_or_response_sentinels() -> None:
    code_sentinel = "PRIVATE_CODE_SENTINEL"
    input_sentinel = "PRIVATE_INPUT_SENTINEL"
    expected_sentinel = "PRIVATE_EXPECTED_SENTINEL"
    response_sentinel = "PRIVATE_RESPONSE_SENTINEL"
    executor, _ = _executor([{"run": {"stdout": response_sentinel, "stderr": "", "unknown": True}}])
    result = executor.execute(
        f"def target(value):\n    return '{code_sentinel}'\n",
        "target",
        [{"input": input_sentinel, "expected": expected_sentinel}],
        1.0,
        32,
    )
    serialized = json.dumps(execution_result_to_mapping(result), sort_keys=True)
    for sentinel in [code_sentinel, input_sentinel, expected_sentinel, response_sentinel, "fixedmarker123"]:
        assert sentinel not in serialized
