"""Unit tests for strict local Piston configuration and transport behavior."""

from __future__ import annotations

import io
import json
from email.message import Message
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request

import pytest

from code_verifier.config import ConfigError
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
