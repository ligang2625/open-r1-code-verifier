"""Loopback-only HTTP boundary for a self-hosted Piston executor."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, ProxyHandler, Request, build_opener

from code_verifier.config import ConfigError, load_yaml_mapping

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


class PistonTransportError(RuntimeError):
    """Raised when the local Piston HTTP boundary cannot return a valid bounded response."""


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
    """No-proxy, no-redirect urllib transport for one validated local endpoint."""

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
        """GET the bounded local /api/v2/runtimes JSON value."""
        request = Request(f"{self._base_url}/api/v2/runtimes", method="GET")
        return self._request_json(request, timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes)

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        """POST one bounded local /api/v2/execute JSON request."""
        try:
            body = json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, RecursionError):
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
    """Load and strictly validate one local Piston YAML config."""
    loaded = load_yaml_mapping(path)
    if set(loaded) != {"piston"}:
        raise ConfigError("Execution config must contain exactly the piston field")
    return piston_executor_config_from_mapping(loaded["piston"])


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
