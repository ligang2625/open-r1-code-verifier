"""Non-deployed SSH tunnel supervisor primitives for the canonical Piston forward."""

from __future__ import annotations

import fcntl
import json
import math
import os
import socket
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from code_verifier.execution.piston_resilience import (
    PistonTransportTelemetry,
    PistonTunnelSupervisorDefinition,
)


class PistonTunnelSupervisorError(RuntimeError):
    """Raised when tunnel ownership or recovery cannot be proven safe."""


class RuntimeValidator(Protocol):
    """Minimal project runtime probe used by tunnel health checks."""

    def validate_runtime(self) -> str: ...


@dataclass(frozen=True)
class TunnelSupervisorConfig:
    """Exact canonical SSH-forward definition with bounded reconnect behavior."""

    ssh_target: str = "1660ti-wsl"
    local_host: str = "127.0.0.1"
    local_port: int = 2000
    remote_host: str = "127.0.0.1"
    remote_port: int = 2000
    connect_timeout_seconds: int = 10
    server_alive_interval_seconds: int = 30
    server_alive_count_max: int = 3
    reconnect_backoff_seconds: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0)
    reconnect_backoff_cap_seconds: float = 10.0
    max_reconnects: int = 8

    @classmethod
    def from_definition(cls, definition: PistonTunnelSupervisorDefinition) -> TunnelSupervisorConfig:
        """Construct the runtime supervisor config from the tracked policy identity."""
        if not definition.exclusive_lock_required or definition.unknown_port_owner_action != "fail_closed":
            raise PistonTunnelSupervisorError("tracked tunnel ownership policy is not fail closed")
        return cls(
            ssh_target=definition.ssh_target,
            local_host=definition.local_host,
            local_port=definition.local_port,
            remote_host=definition.remote_host,
            remote_port=definition.remote_port,
            connect_timeout_seconds=definition.connect_timeout_seconds,
            server_alive_interval_seconds=definition.server_alive_interval_seconds,
            server_alive_count_max=definition.server_alive_count_max,
            reconnect_backoff_seconds=definition.reconnect_backoff_seconds,
            reconnect_backoff_cap_seconds=definition.reconnect_backoff_cap_seconds,
            max_reconnects=definition.max_reconnects,
        )

    def __post_init__(self) -> None:
        if (
            self.ssh_target != "1660ti-wsl"
            or self.local_host != "127.0.0.1"
            or self.local_port != 2000
            or self.remote_host != "127.0.0.1"
            or self.remote_port != 2000
        ):
            raise PistonTunnelSupervisorError("Piston tunnel supervisor topology must remain canonical")
        integer_bounds = (
            (self.connect_timeout_seconds, 1, 60),
            (self.server_alive_interval_seconds, 1, 300),
            (self.server_alive_count_max, 1, 10),
            (self.max_reconnects, 0, 100),
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high
            for value, low, high in integer_bounds
        ):
            raise PistonTunnelSupervisorError("Piston tunnel supervisor integer limits are invalid")
        if (
            not math.isfinite(self.reconnect_backoff_cap_seconds)
            or not 0 <= self.reconnect_backoff_cap_seconds <= 60
            or not self.reconnect_backoff_seconds
            or any(
                not math.isfinite(value) or not 0 <= value <= self.reconnect_backoff_cap_seconds
                for value in self.reconnect_backoff_seconds
            )
        ):
            raise PistonTunnelSupervisorError("Piston tunnel reconnect backoff is invalid")

    def reconnect_delay(self, reconnect_index: int) -> float:
        if reconnect_index < 0:
            raise PistonTunnelSupervisorError("reconnect index must be nonnegative")
        selected = self.reconnect_backoff_seconds[min(reconnect_index, len(self.reconnect_backoff_seconds) - 1)]
        return min(selected, self.reconnect_backoff_cap_seconds)

    def ssh_argv(self) -> tuple[str, ...]:
        """Build the secret-free SSH argv for the canonical local forward."""
        return (
            "ssh",
            "-N",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            f"ConnectTimeout={self.connect_timeout_seconds}",
            "-o",
            f"ServerAliveInterval={self.server_alive_interval_seconds}",
            "-o",
            f"ServerAliveCountMax={self.server_alive_count_max}",
            "-L",
            f"{self.local_host}:{self.local_port}:{self.remote_host}:{self.remote_port}",
            self.ssh_target,
        )


class ExclusiveTunnelLock:
    """Exclusive nonblocking file lock; a second supervisor must fail closed."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: IO[str] | None = None

    def __enter__(self) -> ExclusiveTunnelLock:
        if not self._path.is_absolute():
            raise PistonTunnelSupervisorError("Piston tunnel lock path must be absolute")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self._path, flags, 0o600)
        except OSError:
            raise PistonTunnelSupervisorError("Piston tunnel supervisor lock cannot be opened safely") from None
        handle = os.fdopen(fd, "a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise PistonTunnelSupervisorError("Piston tunnel supervisor lock is already held") from None
        self._handle = handle
        return self

    def __exit__(self, *_args: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def listener_exists(host: str, port: int, *, timeout_seconds: float = 0.2) -> bool:
    """Probe only whether a loopback listener accepts a TCP connection."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_seconds)
        return sock.connect_ex((host, port)) == 0


def assert_port_available_before_start(host: str, port: int) -> None:
    """Never kill an unknown owner; fail if the desired listener already exists."""
    if listener_exists(host, port):
        raise PistonTunnelSupervisorError("Piston tunnel port already has an unknown owner")


def tunnel_is_healthy(
    config: TunnelSupervisorConfig,
    runtime_validator: RuntimeValidator,
    *,
    listener_probe: Callable[[str, int], bool] = listener_exists,
) -> bool:
    """Require listener presence plus successful HTTP runtime validation for exact Python 3.10.0."""
    if not listener_probe(config.local_host, config.local_port):
        return False
    try:
        return runtime_validator.validate_runtime() == "3.10.0"
    except Exception:
        return False


_EVENT_FIELDS: dict[str, frozenset[str]] = {
    "supervisor_start": frozenset(),
    "ssh_process_start": frozenset({"reconnect_count"}),
    "ssh_process_exit": frozenset({"returncode"}),
    "reconnect": frozenset({"reconnect_count", "backoff_seconds"}),
    "outage_begin": frozenset(),
    "outage_end": frozenset({"duration_seconds"}),
    "health_transition": frozenset({"healthy"}),
    "final_failure": frozenset({"reconnect_count", "outage_seconds"}),
}


def sanitized_event(event: str, **fields: int | float | bool) -> str:
    """Serialize only fixed, payload-free supervisor telemetry fields."""
    if event not in _EVENT_FIELDS or set(fields) != _EVENT_FIELDS[event]:
        raise PistonTunnelSupervisorError("supervisor telemetry event schema is invalid")
    for value in fields.values():
        if isinstance(value, float) and not math.isfinite(value):
            raise PistonTunnelSupervisorError("supervisor telemetry floats must be finite")
    record: dict[str, int | float | str | bool] = {"event": event, **fields}
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)


class TunnelSupervisor:
    """Exclusive-lock, unknown-owner-safe, bounded-reconnect SSH supervisor."""

    def __init__(
        self,
        config: TunnelSupervisorConfig,
        *,
        lock_path: Path,
        health_check: Callable[[], bool],
        emit: Callable[[str], None],
        popen: Callable[[Sequence[str]], subprocess.Popen[bytes]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        telemetry: PistonTransportTelemetry | None = None,
    ) -> None:
        self._config = config
        self._lock_path = lock_path
        self._health_check = health_check
        self._emit = emit
        self._popen = popen if popen is not None else lambda argv: subprocess.Popen(argv, close_fds=True)
        self._sleep = sleep
        self._monotonic = monotonic
        self._telemetry = telemetry if telemetry is not None else PistonTransportTelemetry()

    def run(self) -> None:
        """Run until unrecoverable failure; never take over an unknown port owner."""
        with ExclusiveTunnelLock(self._lock_path):
            self._run_locked()

    def _run_locked(self) -> None:
        self._emit(sanitized_event("supervisor_start"))
        reconnect_count = 0
        outage_started: float | None = None
        last_health: bool | None = None
        while True:
            try:
                assert_port_available_before_start(self._config.local_host, self._config.local_port)
            except PistonTunnelSupervisorError:
                duration = 0.0 if outage_started is None else max(0.0, self._monotonic() - outage_started)
                if outage_started is not None:
                    self._record_outage(duration)
                self._emit(
                    sanitized_event(
                        "final_failure",
                        reconnect_count=reconnect_count,
                        outage_seconds=duration,
                    )
                )
                raise
            self._emit(sanitized_event("ssh_process_start", reconnect_count=reconnect_count))
            try:
                process = self._popen(self._config.ssh_argv())
            except OSError:
                self._emit(
                    sanitized_event(
                        "final_failure",
                        reconnect_count=reconnect_count,
                        outage_seconds=0.0,
                    )
                )
                raise PistonTunnelSupervisorError("SSH process could not be started") from None
            while process.poll() is None:
                healthy = self._health_check()
                if healthy:
                    if outage_started is not None:
                        duration = max(0.0, self._monotonic() - outage_started)
                        self._record_outage(duration)
                        self._emit(sanitized_event("outage_end", duration_seconds=duration))
                        outage_started = None
                    if last_health is not True:
                        self._emit(sanitized_event("health_transition", healthy=True))
                    last_health = True
                    self._sleep(1.0)
                    continue
                if outage_started is None:
                    outage_started = self._monotonic()
                    self._emit(sanitized_event("outage_begin"))
                last_health = False
                self._sleep(1.0)
            rc = process.wait()
            self._emit(sanitized_event("ssh_process_exit", returncode=rc))
            last_health = False
            if outage_started is None:
                outage_started = self._monotonic()
                self._emit(sanitized_event("outage_begin"))
            if reconnect_count >= self._config.max_reconnects:
                duration = max(0.0, self._monotonic() - outage_started)
                self._record_outage(duration)
                self._emit(
                    sanitized_event(
                        "final_failure",
                        reconnect_count=reconnect_count,
                        outage_seconds=duration,
                    )
                )
                raise PistonTunnelSupervisorError("Piston tunnel reconnect budget exhausted")
            delay = self._config.reconnect_delay(reconnect_count)
            reconnect_count += 1
            self._telemetry.record_tunnel_reconnect()
            self._emit(sanitized_event("reconnect", reconnect_count=reconnect_count, backoff_seconds=delay))
            self._sleep(delay)

    def _record_outage(self, duration: float) -> None:
        self._telemetry.record_tunnel_outage(duration)
