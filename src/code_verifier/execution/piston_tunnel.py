"""Non-deployed SSH tunnel supervisor primitives for the canonical Piston forward."""

from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import signal
import socket
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import IO, Protocol, cast

from code_verifier.execution.piston_resilience import (
    PistonTransportTelemetry,
    PistonTunnelSupervisorDefinition,
)


class PistonTunnelSupervisorError(RuntimeError):
    """Raised when tunnel ownership or recovery cannot be proven safe."""


class _SupervisorSignal(BaseException):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


class RuntimeValidator(Protocol):
    """Minimal project runtime probe used by tunnel health checks."""

    def validate_runtime(self) -> str: ...


@dataclass(frozen=True)
class TunnelSupervisorConfig:
    """Exact canonical SSH-forward definition with bounded per-outage reconnect behavior."""

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
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise PistonTunnelSupervisorError("Piston tunnel supervisor lock directory is unavailable") from None
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self._path, flags, 0o600)
        except OSError:
            raise PistonTunnelSupervisorError("Piston tunnel supervisor lock cannot be opened safely") from None
        try:
            handle = os.fdopen(fd, "a+", encoding="utf-8")
        except OSError:
            os.close(fd)
            raise PistonTunnelSupervisorError("Piston tunnel supervisor lock cannot be opened safely") from None
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise PistonTunnelSupervisorError("Piston tunnel supervisor lock is already held") from None
        except OSError:
            handle.close()
            raise PistonTunnelSupervisorError("Piston tunnel supervisor lock cannot be acquired safely") from None
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
    """Never kill an unknown owner; fail if port availability cannot be proven safe."""
    try:
        occupied = listener_exists(host, port)
    except OSError:
        raise PistonTunnelSupervisorError("Piston tunnel port availability could not be established") from None
    if occupied:
        raise PistonTunnelSupervisorError("Piston tunnel port already has an unknown owner")


def tunnel_is_healthy(
    config: TunnelSupervisorConfig,
    runtime_validator: RuntimeValidator,
    *,
    listener_probe: Callable[[str, int], bool] = listener_exists,
) -> bool:
    """Require listener presence plus successful HTTP runtime validation for exact Python 3.10.0."""
    try:
        if not listener_probe(config.local_host, config.local_port):
            return False
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
_NONNEGATIVE_INTEGER_EVENT_FIELDS = frozenset({"reconnect_count"})
_NONNEGATIVE_NUMBER_EVENT_FIELDS = frozenset({"backoff_seconds", "duration_seconds", "outage_seconds"})


def sanitized_event(event: str, **fields: int | float | bool) -> str:
    """Serialize only fixed, payload-free supervisor telemetry fields."""
    if event not in _EVENT_FIELDS or set(fields) != _EVENT_FIELDS[event]:
        raise PistonTunnelSupervisorError("supervisor telemetry event schema is invalid")
    for field_name, value in fields.items():
        if field_name == "healthy":
            if not isinstance(value, bool):
                raise PistonTunnelSupervisorError("supervisor telemetry healthy field must be boolean")
            continue
        if field_name in _NONNEGATIVE_INTEGER_EVENT_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PistonTunnelSupervisorError("supervisor telemetry counters must be nonnegative integers")
            continue
        if field_name == "returncode":
            if isinstance(value, bool) or not isinstance(value, int):
                raise PistonTunnelSupervisorError("supervisor telemetry returncode must be an integer")
            continue
        if field_name in _NONNEGATIVE_NUMBER_EVENT_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise PistonTunnelSupervisorError("supervisor telemetry durations must be finite and nonnegative")
            try:
                converted = float(value)
            except OverflowError:
                raise PistonTunnelSupervisorError(
                    "supervisor telemetry durations must be finite and nonnegative"
                ) from None
            if not math.isfinite(converted) or converted < 0:
                raise PistonTunnelSupervisorError("supervisor telemetry durations must be finite and nonnegative")
    record: dict[str, int | float | str | bool] = {"event": event, **fields}
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_event_line(line: str) -> str:
    try:
        value = json.loads(line)
    except (TypeError, json.JSONDecodeError):
        raise PistonTunnelSupervisorError("supervisor telemetry line is invalid") from None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PistonTunnelSupervisorError("supervisor telemetry line is invalid")
    event = value.get("event")
    if not isinstance(event, str):
        raise PistonTunnelSupervisorError("supervisor telemetry line is invalid")
    fields = {key: item for key, item in value.items() if key != "event"}
    if not all(isinstance(item, int | float | bool) for item in fields.values()):
        raise PistonTunnelSupervisorError("supervisor telemetry line is invalid")
    canonical = sanitized_event(event, **cast(dict[str, int | float | bool], fields))
    if json.loads(canonical) != value:
        raise PistonTunnelSupervisorError("supervisor telemetry line is invalid")
    return canonical


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DurableTunnelEventSink:
    """Append only validated, payload-free supervisor events to a durable JSONL file."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise PistonTunnelSupervisorError("supervisor telemetry path must be absolute")
        self._path = path

    def __call__(self, line: str) -> None:
        canonical = _validate_event_line(line)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        existed = self._path.exists()
        flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self._path, flags, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(canonical + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            if not existed:
                _fsync_directory(self._path.parent)
        except OSError:
            raise PistonTunnelSupervisorError("supervisor telemetry could not be persisted") from None


class TunnelSupervisor:
    """Exclusive-lock, owned-child, bounded-per-outage reconnect SSH supervisor."""

    def __init__(
        self,
        config: TunnelSupervisorConfig,
        *,
        lock_path: Path,
        runtime_validator: RuntimeValidator,
        emit: Callable[[str], None],
        listener_probe: Callable[[str, int], bool] = listener_exists,
        popen: Callable[[Sequence[str]], subprocess.Popen[bytes]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        telemetry: PistonTransportTelemetry | None = None,
        child_stop_timeout_seconds: float = 5.0,
    ) -> None:
        if not math.isfinite(child_stop_timeout_seconds) or child_stop_timeout_seconds <= 0:
            raise PistonTunnelSupervisorError("child stop timeout must be finite and positive")
        self._config = config
        self._lock_path = lock_path
        self._runtime_validator = runtime_validator
        self._listener_probe = listener_probe
        self._emit = emit
        self._popen = popen if popen is not None else lambda argv: subprocess.Popen(argv, close_fds=True)
        self._sleep = sleep
        self._monotonic = monotonic
        self._telemetry = telemetry if telemetry is not None else PistonTransportTelemetry()
        self._child_stop_timeout_seconds = child_stop_timeout_seconds
        self._owned_process: subprocess.Popen[bytes] | None = None
        self._total_reconnect_count = 0
        self._outage_started: float | None = None
        self._final_failure_emitted = False

    def run(self) -> None:
        """Run until unrecoverable failure; keep the lock until any owned SSH child is stopped."""
        try:
            previous_handlers = self._install_signal_handlers()
        except PistonTunnelSupervisorError:
            self._emit_final_failure()
            raise
        try:
            try:
                with ExclusiveTunnelLock(self._lock_path):
                    try:
                        self._run_locked()
                    except _SupervisorSignal as error:
                        self._emit_final_failure()
                        raise PistonTunnelSupervisorError(
                            f"Piston tunnel supervisor stopped by signal {error.signum}"
                        ) from None
                    except BaseException:
                        self._emit_final_failure()
                        raise
                    finally:
                        self._stop_owned_process()
            except PistonTunnelSupervisorError:
                self._emit_final_failure()
                raise
        finally:
            self._restore_signal_handlers(previous_handlers)

    def _run_locked(self) -> None:
        self._emit(sanitized_event("supervisor_start"))
        outage_reconnect_count = 0
        last_health: bool | None = None
        while True:
            try:
                assert_port_available_before_start(self._config.local_host, self._config.local_port)
            except PistonTunnelSupervisorError:
                self._emit_final_failure()
                raise
            self._emit(sanitized_event("ssh_process_start", reconnect_count=self._total_reconnect_count))
            try:
                process = self._start_owned_process()
            except OSError:
                self._emit_final_failure()
                raise PistonTunnelSupervisorError("SSH process could not be started") from None
            while process.poll() is None:
                healthy = tunnel_is_healthy(
                    self._config,
                    self._runtime_validator,
                    listener_probe=self._listener_probe,
                )
                if healthy:
                    if self._outage_started is not None:
                        duration = self._finish_outage()
                        self._emit(sanitized_event("outage_end", duration_seconds=duration))
                    if last_health is not True:
                        self._emit(sanitized_event("health_transition", healthy=True))
                    last_health = True
                    outage_reconnect_count = 0
                    self._sleep(1.0)
                    continue
                if self._outage_started is None:
                    self._outage_started = self._monotonic()
                    self._emit(sanitized_event("outage_begin"))
                last_health = False
                self._sleep(1.0)
            rc = process.wait()
            self._owned_process = None
            self._emit(sanitized_event("ssh_process_exit", returncode=rc))
            last_health = False
            if self._outage_started is None:
                self._outage_started = self._monotonic()
                self._emit(sanitized_event("outage_begin"))
            if outage_reconnect_count >= self._config.max_reconnects:
                self._emit_final_failure()
                raise PistonTunnelSupervisorError("Piston tunnel reconnect budget exhausted")
            delay = self._config.reconnect_delay(outage_reconnect_count)
            outage_reconnect_count += 1
            self._total_reconnect_count += 1
            self._telemetry.record_tunnel_reconnect()
            self._emit(
                sanitized_event(
                    "reconnect",
                    reconnect_count=self._total_reconnect_count,
                    backoff_seconds=delay,
                )
            )
            self._sleep(delay)

    def _start_owned_process(self) -> subprocess.Popen[bytes]:
        blocked = {signal.SIGTERM, signal.SIGINT}
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        try:
            process = self._popen(self._config.ssh_argv())
            self._owned_process = process
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        return process

    def _finish_outage(self) -> float:
        if self._outage_started is None:
            return 0.0
        duration = max(0.0, self._monotonic() - self._outage_started)
        self._telemetry.record_tunnel_outage(duration)
        self._outage_started = None
        return duration

    def _emit_final_failure(self) -> None:
        if self._final_failure_emitted:
            return
        try:
            duration = self._finish_outage()
        except Exception:
            duration = 0.0
        self._final_failure_emitted = True
        with contextlib.suppress(Exception):
            self._emit(
                sanitized_event(
                    "final_failure",
                    reconnect_count=self._total_reconnect_count,
                    outage_seconds=duration,
                )
            )

    def _stop_owned_process(self) -> None:
        process = self._owned_process
        if process is None:
            return
        blocked = {signal.SIGTERM, signal.SIGINT}
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        returncode: int | None = process.poll()
        try:
            if returncode is None:
                process.terminate()
                try:
                    returncode = process.wait(timeout=self._child_stop_timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    returncode = process.wait()
            else:
                returncode = process.wait()
        except OSError:
            raise PistonTunnelSupervisorError("owned SSH process could not be stopped safely") from None
        finally:
            self._owned_process = None
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        with contextlib.suppress(Exception):
            self._emit(sanitized_event("ssh_process_exit", returncode=returncode))

    def _handle_shutdown_signal(self, signum: int, _frame: FrameType | None) -> None:
        raise _SupervisorSignal(signum)

    def _install_signal_handlers(self) -> list[tuple[signal.Signals, object]]:
        previous: list[tuple[signal.Signals, object]] = []
        try:
            for configured_signal in (signal.SIGTERM, signal.SIGINT):
                previous.append((configured_signal, signal.getsignal(configured_signal)))
                signal.signal(configured_signal, self._handle_shutdown_signal)
        except (OSError, ValueError):
            for saved_signal, handler in reversed(previous):
                signal.signal(saved_signal, cast(signal.Handlers, handler))
            raise PistonTunnelSupervisorError("supervisor signal handlers could not be installed") from None
        return previous

    @staticmethod
    def _restore_signal_handlers(previous: list[tuple[signal.Signals, object]]) -> None:
        for signum, handler in previous:
            signal.signal(signum, cast(signal.Handlers, handler))
