"""Bounded Piston transport resilience policy and payload-free telemetry."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from code_verifier.config import ConfigError, load_yaml_mapping

PISTON_TRANSPORT_RETRY_IMPLEMENTATION_VERSION = "piston-transport-retry-v2"
PISTON_TRANSPORT_CLASSIFIER_IMPLEMENTATION_VERSION = "httpclient-loopback-classifier-v3"
PISTON_TRANSPORT_CONNECTION_IMPLEMENTATION_VERSION = "httpclient-single-keepalive-v2"
PISTON_TUNNEL_SUPERVISOR_IMPLEMENTATION_VERSION = "piston-tunnel-supervisor-v3"

_POLICY_FIELDS = {
    "version",
    "safe_retry_kinds",
    "max_attempts",
    "backoff_seconds",
    "backoff_cap_seconds",
    "health_probe",
    "tunnel_supervisor",
}
_SAFE_RETRY_KINDS = ("connection_refused", "preconnect_failure")
_HEALTH_FIELDS = {
    "listener_host",
    "listener_port",
    "http_path",
    "required_runtime",
    "max_wait_attempts",
    "backoff_seconds",
    "backoff_cap_seconds",
}
_SUPERVISOR_FIELDS = {
    "ssh_target",
    "local_host",
    "local_port",
    "remote_host",
    "remote_port",
    "connect_timeout_seconds",
    "server_alive_interval_seconds",
    "server_alive_count_max",
    "reconnect_backoff_seconds",
    "reconnect_backoff_cap_seconds",
    "max_reconnects",
    "exclusive_lock_required",
    "unknown_port_owner_action",
}


@dataclass(frozen=True)
class PistonHealthProbeDefinition:
    """Exact endpoint identity and bounded wait policy required before a safe candidate resend."""

    listener_host: str
    listener_port: int
    http_path: str
    required_runtime: str
    max_wait_attempts: int
    backoff_seconds: tuple[float, ...]
    backoff_cap_seconds: float

    def delay_for_retry(self, retry_index: int) -> float:
        if retry_index < 0:
            raise ValueError("retry_index must be nonnegative")
        selected = self.backoff_seconds[min(retry_index, len(self.backoff_seconds) - 1)]
        return min(selected, self.backoff_cap_seconds)


@dataclass(frozen=True)
class PistonTunnelSupervisorDefinition:
    """Tracked operational definition for the future 4090 tunnel supervisor."""

    ssh_target: str
    local_host: str
    local_port: int
    remote_host: str
    remote_port: int
    connect_timeout_seconds: int
    server_alive_interval_seconds: int
    server_alive_count_max: int
    reconnect_backoff_seconds: tuple[float, ...]
    reconnect_backoff_cap_seconds: float
    max_reconnects: int
    exclusive_lock_required: bool
    unknown_port_owner_action: str


@dataclass(frozen=True)
class PistonTransportPolicy:
    """Operational retry policy kept separate from verifier scientific identity."""

    version: int
    safe_retry_kinds: tuple[str, ...]
    max_attempts: int
    backoff_seconds: tuple[float, ...]
    backoff_cap_seconds: float
    health_probe: PistonHealthProbeDefinition
    tunnel_supervisor: PistonTunnelSupervisorDefinition

    def delay_for_retry(self, retry_index: int) -> float:
        if retry_index < 0:
            raise ValueError("retry_index must be nonnegative")
        return min(self.backoff_seconds[min(retry_index, len(self.backoff_seconds) - 1)], self.backoff_cap_seconds)


@dataclass
class PistonTransportTelemetry:
    """Durable cumulative run-level counters; never contains request payloads."""

    transport_requests: int = 0
    transport_connect_failures: int = 0
    transport_safe_retries: int = 0
    transport_retry_successes: int = 0
    transport_retry_exhausted: int = 0
    transport_ambiguous_failures: int = 0
    tunnel_reconnect_count: int = 0
    tunnel_total_outage_seconds: float = 0.0
    tunnel_max_outage_seconds: float = 0.0
    _on_change: Callable[[Mapping[str, int | float]], None] | None = field(default=None, repr=False, compare=False)

    def to_mapping(self) -> dict[str, int | float]:
        counters = {
            "transport_requests": self.transport_requests,
            "transport_connect_failures": self.transport_connect_failures,
            "transport_safe_retries": self.transport_safe_retries,
            "transport_retry_successes": self.transport_retry_successes,
            "transport_retry_exhausted": self.transport_retry_exhausted,
            "transport_ambiguous_failures": self.transport_ambiguous_failures,
            "tunnel_reconnect_count": self.tunnel_reconnect_count,
        }
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counters.values()):
            raise ValueError("transport telemetry counters must be nonnegative integers")
        durations = {
            "tunnel_total_outage_seconds": self.tunnel_total_outage_seconds,
            "tunnel_max_outage_seconds": self.tunnel_max_outage_seconds,
        }
        normalized_durations: dict[str, float] = {}
        for field_name, value in durations.items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError("transport telemetry durations must be finite and nonnegative")
            try:
                converted = float(value)
            except OverflowError:
                raise ValueError("transport telemetry durations must be finite and nonnegative") from None
            if not math.isfinite(converted) or converted < 0:
                raise ValueError("transport telemetry durations must be finite and nonnegative")
            normalized_durations[field_name] = converted
        return {**counters, **normalized_durations}

    def set_on_change(self, callback: Callable[[Mapping[str, int | float]], None] | None) -> None:
        """Install a durable snapshot callback without changing counter values."""
        self._on_change = callback

    def restore(self, mapping: object) -> None:
        """Restore cumulative counters from strict run telemetry during resume."""
        expected = set(self.to_mapping())
        if not isinstance(mapping, dict) or set(mapping) != expected:
            raise ValueError("transport telemetry mapping does not match the required schema")
        restored = PistonTransportTelemetry(**cast(Any, mapping))
        restored_mapping = restored.to_mapping()
        for field_name, value in restored_mapping.items():
            setattr(self, field_name, value)

    def record_transport_request(self) -> None:
        self.transport_requests += 1
        self._changed()

    def record_connect_failure(self) -> None:
        self.transport_connect_failures += 1
        self._changed()

    def record_safe_retry(self) -> None:
        self.transport_safe_retries += 1
        self._changed()

    def record_retry_success(self) -> None:
        self.transport_retry_successes += 1
        self._changed()

    def record_retry_exhausted(self) -> None:
        self.transport_retry_exhausted += 1
        self._changed()

    def record_ambiguous_failure(self) -> None:
        self.transport_ambiguous_failures += 1
        self._changed()

    def record_tunnel_reconnect(self) -> None:
        self.tunnel_reconnect_count += 1
        self._changed()

    def record_tunnel_outage(self, duration_seconds: float) -> None:
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int | float):
            raise ValueError("tunnel outage duration must be finite and nonnegative")
        try:
            converted = float(duration_seconds)
            total = float(self.tunnel_total_outage_seconds) + converted
        except OverflowError:
            raise ValueError("tunnel outage duration must be finite and nonnegative") from None
        if not math.isfinite(converted) or converted < 0 or not math.isfinite(total):
            raise ValueError("tunnel outage duration must be finite and nonnegative")
        self.tunnel_total_outage_seconds = total
        self.tunnel_max_outage_seconds = max(float(self.tunnel_max_outage_seconds), converted)
        self._changed()

    def flush(self) -> None:
        self._changed()

    def _changed(self) -> None:
        mapping = self.to_mapping()
        if self._on_change is not None:
            self._on_change(mapping)


def _require_exact_mapping(value: object, fields: set[str], *, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value) or set(value) != fields:
        raise ConfigError(f"{context} fields do not match the required schema")
    return cast(dict[str, object], value)


def _bounded_positive_int(value: object, *, field_name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ConfigError(f"{field_name} must be an integer in [1, {maximum}]")
    return value


def _bounded_nonnegative_float(value: object, *, field_name: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{field_name} must be finite in [0, {maximum:g}]")
    try:
        converted = float(value)
    except OverflowError:
        raise ConfigError(f"{field_name} must be finite in [0, {maximum:g}]") from None
    if not math.isfinite(converted) or not 0 <= converted <= maximum:
        raise ConfigError(f"{field_name} must be finite in [0, {maximum:g}]")
    return converted


def _bounded_backoff(value: object, *, field_name: str, cap: float) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{field_name} must be a non-empty list")
    converted = tuple(_bounded_nonnegative_float(item, field_name=field_name, maximum=cap) for item in value)
    return converted


def load_piston_transport_policy(path: Path) -> PistonTransportPolicy:
    """Load one exact, bounded, loopback-only resilience policy."""
    loaded = load_yaml_mapping(path)
    if set(loaded) != _POLICY_FIELDS:
        raise ConfigError("Piston transport policy fields do not match the required schema")
    if loaded["version"] != 1:
        raise ConfigError("Piston transport policy version must be exactly 1")
    safe = loaded["safe_retry_kinds"]
    if not isinstance(safe, list) or tuple(safe) != _SAFE_RETRY_KINDS:
        raise ConfigError("Piston transport safe retry classification is not exact")
    attempts = _bounded_positive_int(loaded["max_attempts"], field_name="max_attempts", maximum=5)
    backoff_cap = _bounded_nonnegative_float(
        loaded["backoff_cap_seconds"], field_name="backoff_cap_seconds", maximum=30.0
    )
    backoff = _bounded_backoff(loaded["backoff_seconds"], field_name="backoff_seconds", cap=backoff_cap)

    health = _require_exact_mapping(loaded["health_probe"], _HEALTH_FIELDS, context="Piston health probe")
    required_health_scalars = {
        "listener_host": "127.0.0.1",
        "listener_port": 2000,
        "http_path": "/api/v2/runtimes",
        "required_runtime": "3.10.0",
    }
    if any(health.get(key) != expected for key, expected in required_health_scalars.items()):
        raise ConfigError("Piston health probe must use canonical loopback Python 3.10.0 identity")
    health_attempts = _bounded_positive_int(
        health["max_wait_attempts"], field_name="health_probe.max_wait_attempts", maximum=20
    )
    health_backoff_cap = _bounded_nonnegative_float(
        health["backoff_cap_seconds"], field_name="health_probe.backoff_cap_seconds", maximum=30.0
    )
    health_backoff = _bounded_backoff(
        health["backoff_seconds"], field_name="health_probe.backoff_seconds", cap=health_backoff_cap
    )
    health_definition = PistonHealthProbeDefinition(
        listener_host="127.0.0.1",
        listener_port=2000,
        http_path="/api/v2/runtimes",
        required_runtime="3.10.0",
        max_wait_attempts=health_attempts,
        backoff_seconds=health_backoff,
        backoff_cap_seconds=health_backoff_cap,
    )

    supervisor = _require_exact_mapping(
        loaded["tunnel_supervisor"], _SUPERVISOR_FIELDS, context="Piston tunnel supervisor"
    )
    required_scalars: dict[str, object] = {
        "ssh_target": "1660ti-wsl",
        "local_host": "127.0.0.1",
        "local_port": 2000,
        "remote_host": "127.0.0.1",
        "remote_port": 2000,
        "exclusive_lock_required": True,
        "unknown_port_owner_action": "fail_closed",
    }
    if any(supervisor.get(key) != expected for key, expected in required_scalars.items()):
        raise ConfigError("Piston tunnel supervisor topology or ownership policy is not canonical")
    connect_timeout = _bounded_positive_int(
        supervisor["connect_timeout_seconds"], field_name="connect_timeout_seconds", maximum=60
    )
    alive_interval = _bounded_positive_int(
        supervisor["server_alive_interval_seconds"], field_name="server_alive_interval_seconds", maximum=300
    )
    alive_count = _bounded_positive_int(
        supervisor["server_alive_count_max"], field_name="server_alive_count_max", maximum=10
    )
    reconnect_cap = _bounded_nonnegative_float(
        supervisor["reconnect_backoff_cap_seconds"], field_name="reconnect_backoff_cap_seconds", maximum=60.0
    )
    reconnect_backoff = _bounded_backoff(
        supervisor["reconnect_backoff_seconds"], field_name="reconnect_backoff_seconds", cap=reconnect_cap
    )
    max_reconnects = _bounded_positive_int(supervisor["max_reconnects"], field_name="max_reconnects", maximum=100)
    supervisor_definition = PistonTunnelSupervisorDefinition(
        ssh_target="1660ti-wsl",
        local_host="127.0.0.1",
        local_port=2000,
        remote_host="127.0.0.1",
        remote_port=2000,
        connect_timeout_seconds=connect_timeout,
        server_alive_interval_seconds=alive_interval,
        server_alive_count_max=alive_count,
        reconnect_backoff_seconds=reconnect_backoff,
        reconnect_backoff_cap_seconds=reconnect_cap,
        max_reconnects=max_reconnects,
        exclusive_lock_required=True,
        unknown_port_owner_action="fail_closed",
    )
    return PistonTransportPolicy(
        version=1,
        safe_retry_kinds=_SAFE_RETRY_KINDS,
        max_attempts=attempts,
        backoff_seconds=backoff,
        backoff_cap_seconds=backoff_cap,
        health_probe=health_definition,
        tunnel_supervisor=supervisor_definition,
    )


def _policy_mapping(policy: PistonTransportPolicy) -> dict[str, object]:
    return {
        "version": policy.version,
        "safe_retry_kinds": list(policy.safe_retry_kinds),
        "max_attempts": policy.max_attempts,
        "backoff_seconds": list(policy.backoff_seconds),
        "backoff_cap_seconds": policy.backoff_cap_seconds,
        "health_probe": {
            "listener_host": policy.health_probe.listener_host,
            "listener_port": policy.health_probe.listener_port,
            "http_path": policy.health_probe.http_path,
            "required_runtime": policy.health_probe.required_runtime,
            "max_wait_attempts": policy.health_probe.max_wait_attempts,
            "backoff_seconds": list(policy.health_probe.backoff_seconds),
            "backoff_cap_seconds": policy.health_probe.backoff_cap_seconds,
        },
        "tunnel_supervisor": {
            "ssh_target": policy.tunnel_supervisor.ssh_target,
            "local_host": policy.tunnel_supervisor.local_host,
            "local_port": policy.tunnel_supervisor.local_port,
            "remote_host": policy.tunnel_supervisor.remote_host,
            "remote_port": policy.tunnel_supervisor.remote_port,
            "connect_timeout_seconds": policy.tunnel_supervisor.connect_timeout_seconds,
            "server_alive_interval_seconds": policy.tunnel_supervisor.server_alive_interval_seconds,
            "server_alive_count_max": policy.tunnel_supervisor.server_alive_count_max,
            "reconnect_backoff_seconds": list(policy.tunnel_supervisor.reconnect_backoff_seconds),
            "reconnect_backoff_cap_seconds": policy.tunnel_supervisor.reconnect_backoff_cap_seconds,
            "max_reconnects": policy.tunnel_supervisor.max_reconnects,
            "exclusive_lock_required": policy.tunnel_supervisor.exclusive_lock_required,
            "unknown_port_owner_action": policy.tunnel_supervisor.unknown_port_owner_action,
        },
        "implementation_versions": {
            "retry": PISTON_TRANSPORT_RETRY_IMPLEMENTATION_VERSION,
            "classifier": PISTON_TRANSPORT_CLASSIFIER_IMPLEMENTATION_VERSION,
            "connection": PISTON_TRANSPORT_CONNECTION_IMPLEMENTATION_VERSION,
            "tunnel_supervisor": PISTON_TUNNEL_SUPERVISOR_IMPLEMENTATION_VERSION,
        },
    }


def piston_transport_policy_sha256(path: Path) -> str:
    """Hash normalized policy semantics, independently of Piston scientific definition."""
    encoded = json.dumps(
        _policy_mapping(load_piston_transport_policy(path)),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sleep_backoff(seconds: float) -> None:
    time.sleep(seconds)
