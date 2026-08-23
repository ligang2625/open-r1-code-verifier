"""Deterministic unit tests for the non-deployed Piston tunnel supervisor."""

from __future__ import annotations

import json
import signal
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from code_verifier.execution import piston_tunnel
from code_verifier.execution.piston_resilience import PistonTransportTelemetry
from code_verifier.execution.piston_tunnel import (
    DurableTunnelEventSink,
    ExclusiveTunnelLock,
    PistonTunnelSupervisorError,
    TunnelSupervisor,
    TunnelSupervisorConfig,
    assert_port_available_before_start,
    sanitized_event,
    tunnel_is_healthy,
)


class _Runtime:
    def __init__(self, result: str | BaseException) -> None:
        self.result = result
        self.calls = 0

    def validate_runtime(self) -> str:
        self.calls += 1
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _FakeProcess:
    def __init__(
        self,
        polls: list[int | None],
        rc: int,
        *,
        on_terminate: Callable[[], None] | None = None,
        timeout_after_terminate: bool = False,
    ) -> None:
        self._polls = list(polls)
        self.rc = rc
        self.on_terminate = on_terminate
        self.timeout_after_terminate = timeout_after_terminate
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls: list[float | None] = []

    def poll(self) -> int | None:
        if self._polls:
            return self._polls.pop(0)
        return None

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if timeout is not None and self.timeout_after_terminate and self.kill_calls == 0:
            raise subprocess.TimeoutExpired("ssh", timeout)
        return self.rc

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self.on_terminate is not None:
            self.on_terminate()

    def kill(self) -> None:
        self.kill_calls += 1


def _popen(process: _FakeProcess) -> subprocess.Popen[bytes]:
    return cast(subprocess.Popen[bytes], process)


def test_supervisor_ssh_contract_is_canonical_and_secret_free() -> None:
    argv = TunnelSupervisorConfig().ssh_argv()
    rendered = " ".join(argv)
    for required in [
        "BatchMode=yes",
        "ExitOnForwardFailure=yes",
        "ConnectTimeout=10",
        "ServerAliveInterval=30",
        "ServerAliveCountMax=3",
        "127.0.0.1:2000:127.0.0.1:2000",
        "1660ti-wsl",
    ]:
        assert required in rendered
    for forbidden in ["IdentityFile", "PRIVATE_KEY", "password", "candidate", "visible_tests"]:
        assert forbidden not in rendered


def test_supervisor_lock_is_exclusive(tmp_path: Path) -> None:
    lock_path = tmp_path / "piston-tunnel.lock"
    with (
        ExclusiveTunnelLock(lock_path),
        pytest.raises(PistonTunnelSupervisorError, match="already held"),
        ExclusiveTunnelLock(lock_path),
    ):
        raise AssertionError("unreachable")
    with ExclusiveTunnelLock(lock_path):
        pass


def test_unknown_port_owner_fails_closed_without_killing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(piston_tunnel, "listener_exists", lambda host, port: True)
    with pytest.raises(PistonTunnelSupervisorError, match="unknown owner"):
        assert_port_available_before_start("127.0.0.1", 2000)


def test_port_probe_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        piston_tunnel,
        "listener_exists",
        lambda host, port: (_ for _ in ()).throw(OSError("private probe detail")),
    )
    with pytest.raises(PistonTunnelSupervisorError, match="availability could not be established") as error:
        assert_port_available_before_start("127.0.0.1", 2000)
    assert "private" not in str(error.value)


def test_health_requires_listener_http_probe_and_exact_runtime() -> None:
    config = TunnelSupervisorConfig()
    runtime = _Runtime("3.10.0")
    assert tunnel_is_healthy(config, runtime, listener_probe=lambda host, port: True)
    assert runtime.calls == 1

    runtime = _Runtime("3.11.0")
    assert not tunnel_is_healthy(config, runtime, listener_probe=lambda host, port: True)
    assert runtime.calls == 1

    runtime = _Runtime("3.10.0")
    assert not tunnel_is_healthy(config, runtime, listener_probe=lambda host, port: False)
    assert runtime.calls == 0

    runtime = _Runtime(RuntimeError("probe failed"))
    assert not tunnel_is_healthy(config, runtime, listener_probe=lambda host, port: True)

    runtime = _Runtime("3.10.0")
    assert not tunnel_is_healthy(
        config,
        runtime,
        listener_probe=lambda host, port: (_ for _ in ()).throw(OSError("probe failed")),
    )
    assert runtime.calls == 0


def test_reconnect_state_machine_is_bounded_and_emits_required_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    processes = [_FakeProcess([255], 255), _FakeProcess([255], 255), _FakeProcess([255], 255)]
    events: list[str] = []
    sleeps: list[float] = []
    now = iter([10.0, 11.0])
    telemetry = PistonTransportTelemetry()

    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(reconnect_backoff_seconds=(0.5, 1.0), max_reconnects=2),
        lock_path=tmp_path / "supervisor.lock",
        runtime_validator=_Runtime("3.10.0"),
        emit=events.append,
        popen=lambda argv: _popen(processes.pop(0)),
        sleep=sleeps.append,
        monotonic=lambda: next(now),
        telemetry=telemetry,
    )
    with pytest.raises(PistonTunnelSupervisorError, match="budget exhausted"):
        supervisor.run()

    decoded = [json.loads(item) for item in events]
    names = [item["event"] for item in decoded]
    assert names == [
        "supervisor_start",
        "ssh_process_start",
        "ssh_process_exit",
        "outage_begin",
        "reconnect",
        "ssh_process_start",
        "ssh_process_exit",
        "reconnect",
        "ssh_process_start",
        "ssh_process_exit",
        "final_failure",
    ]
    assert sleeps == [0.5, 1.0]
    assert [item.get("reconnect_count") for item in decoded if item["event"] == "reconnect"] == [1, 2]
    assert decoded[-1]["outage_seconds"] == 1.0
    assert telemetry.tunnel_reconnect_count == 2
    assert telemetry.tunnel_total_outage_seconds == 1.0
    assert telemetry.tunnel_max_outage_seconds == 1.0


def test_reconnect_budget_resets_after_successful_health_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    processes = [
        _FakeProcess([255], 255),
        _FakeProcess([None, 255], 255),
        _FakeProcess([255], 255),
    ]
    events: list[str] = []
    now = iter([10.0, 11.0, 12.0, 13.0])
    telemetry = PistonTransportTelemetry()
    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(reconnect_backoff_seconds=(0.0,), max_reconnects=1),
        lock_path=tmp_path / "supervisor.lock",
        runtime_validator=_Runtime("3.10.0"),
        listener_probe=lambda host, port: True,
        emit=events.append,
        popen=lambda argv: _popen(processes.pop(0)),
        sleep=lambda seconds: None,
        monotonic=lambda: next(now),
        telemetry=telemetry,
    )
    with pytest.raises(PistonTunnelSupervisorError, match="budget exhausted"):
        supervisor.run()

    decoded = [json.loads(item) for item in events]
    assert [item["reconnect_count"] for item in decoded if item["event"] == "reconnect"] == [1, 2]
    assert any(item["event"] == "health_transition" for item in decoded)
    assert telemetry.tunnel_reconnect_count == 2
    assert telemetry.tunnel_total_outage_seconds == 2.0
    assert telemetry.tunnel_max_outage_seconds == 1.0


def test_supervisor_records_outage_end_and_successful_health_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    process = _FakeProcess([None, None, 255], 255)
    listener = iter([False, True])
    now = iter([10.0, 12.0, 13.0, 14.0])
    events: list[str] = []
    telemetry = PistonTransportTelemetry()
    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(max_reconnects=0),
        lock_path=tmp_path / "supervisor.lock",
        runtime_validator=_Runtime("3.10.0"),
        listener_probe=lambda host, port: next(listener),
        emit=events.append,
        popen=lambda argv: _popen(process),
        sleep=lambda seconds: None,
        monotonic=lambda: next(now),
        telemetry=telemetry,
    )
    with pytest.raises(PistonTunnelSupervisorError, match="budget exhausted"):
        supervisor.run()

    decoded = [json.loads(item) for item in events]
    assert [item["event"] for item in decoded] == [
        "supervisor_start",
        "ssh_process_start",
        "outage_begin",
        "outage_end",
        "health_transition",
        "ssh_process_exit",
        "outage_begin",
        "final_failure",
    ]
    assert decoded[3]["duration_seconds"] == 2.0
    assert decoded[4] == {"event": "health_transition", "healthy": True}
    assert decoded[-1]["outage_seconds"] == 1.0
    assert telemetry.tunnel_total_outage_seconds == 3.0
    assert telemetry.tunnel_max_outage_seconds == 2.0


def test_reconnect_refuses_unknown_new_port_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probes = 0

    def port_check(host: str, port: int) -> None:
        nonlocal probes
        assert (host, port) == ("127.0.0.1", 2000)
        probes += 1
        if probes == 2:
            raise PistonTunnelSupervisorError("Piston tunnel port already has an unknown owner")

    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", port_check)
    events: list[str] = []
    telemetry = PistonTransportTelemetry()
    now = iter([10.0, 11.0])
    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(reconnect_backoff_seconds=(0.0,), max_reconnects=2),
        lock_path=tmp_path / "supervisor.lock",
        runtime_validator=_Runtime("3.10.0"),
        emit=events.append,
        popen=lambda argv: _popen(_FakeProcess([255], 255)),
        sleep=lambda seconds: None,
        monotonic=lambda: next(now),
        telemetry=telemetry,
    )
    with pytest.raises(PistonTunnelSupervisorError, match="unknown owner"):
        supervisor.run()
    assert probes == 2
    assert [json.loads(item)["event"] for item in events] == [
        "supervisor_start",
        "ssh_process_start",
        "ssh_process_exit",
        "outage_begin",
        "reconnect",
        "final_failure",
    ]
    assert telemetry.tunnel_reconnect_count == 1
    assert telemetry.tunnel_total_outage_seconds == 1.0


def test_supervisor_stops_owned_child_before_releasing_lock_on_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    lock_path = tmp_path / "supervisor.lock"
    lock_was_held_during_cleanup = False

    def on_terminate() -> None:
        nonlocal lock_was_held_during_cleanup
        with pytest.raises(PistonTunnelSupervisorError, match="already held"), ExclusiveTunnelLock(lock_path):
            pass
        lock_was_held_during_cleanup = True

    process = _FakeProcess([None], 255, on_terminate=on_terminate)
    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(),
        lock_path=lock_path,
        runtime_validator=_Runtime("3.10.0"),
        listener_probe=lambda host, port: True,
        emit=lambda line: None,
        popen=lambda argv: _popen(process),
        sleep=lambda seconds: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    with pytest.raises(RuntimeError, match="stop"):
        supervisor.run()
    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert lock_was_held_during_cleanup is True
    with ExclusiveTunnelLock(lock_path):
        pass


def test_supervisor_kills_owned_child_if_graceful_stop_times_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    process = _FakeProcess([None], 255, timeout_after_terminate=True)
    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(),
        lock_path=tmp_path / "supervisor.lock",
        runtime_validator=_Runtime("3.10.0"),
        listener_probe=lambda host, port: True,
        emit=lambda line: None,
        popen=lambda argv: _popen(process),
        sleep=lambda seconds: (_ for _ in ()).throw(RuntimeError("stop")),
        child_stop_timeout_seconds=0.1,
    )
    with pytest.raises(RuntimeError, match="stop"):
        supervisor.run()
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.wait_calls == [0.1, None]


def test_signal_handler_install_failure_emits_final_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(),
        lock_path=tmp_path / "supervisor.lock",
        runtime_validator=_Runtime("3.10.0"),
        emit=events.append,
    )
    monkeypatch.setattr(
        supervisor,
        "_install_signal_handlers",
        lambda: (_ for _ in ()).throw(PistonTunnelSupervisorError("handlers unavailable")),
    )
    with pytest.raises(PistonTunnelSupervisorError, match="handlers unavailable"):
        supervisor.run()
    assert [json.loads(item)["event"] for item in events] == ["final_failure"]


def test_supervisor_signal_shutdown_is_fail_closed_and_stops_owned_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    process = _FakeProcess([None], 255)
    events: list[str] = []
    supervisor: TunnelSupervisor

    def interrupt(_seconds: float) -> None:
        supervisor._handle_shutdown_signal(signal.SIGTERM, None)

    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(),
        lock_path=tmp_path / "supervisor.lock",
        runtime_validator=_Runtime("3.10.0"),
        listener_probe=lambda host, port: True,
        emit=events.append,
        popen=lambda argv: _popen(process),
        sleep=interrupt,
    )
    with pytest.raises(PistonTunnelSupervisorError, match="signal"):
        supervisor.run()
    assert process.terminate_calls == 1
    assert [json.loads(item)["event"] for item in events][-2:] == ["final_failure", "ssh_process_exit"]


def test_durable_supervisor_jsonl_sink_accepts_only_sanitized_events(tmp_path: Path) -> None:
    path = tmp_path / "tunnel-events.jsonl"
    sink = DurableTunnelEventSink(path)
    first = sanitized_event("supervisor_start")
    second = sanitized_event("reconnect", reconnect_count=1, backoff_seconds=0.5)
    sink(first)
    sink(second)
    assert path.read_text(encoding="utf-8").splitlines() == [first, second]
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(PistonTunnelSupervisorError, match="line is invalid"):
        sink(json.dumps({"event": "supervisor_start", "candidate": "SECRET"}))


def test_supervisor_telemetry_has_no_candidate_test_or_secret_payload() -> None:
    line = sanitized_event("health_transition", healthy=True)
    decoded = json.loads(line)
    assert decoded == {"event": "health_transition", "healthy": True}
    for sentinel in ["candidate", "visible_tests", "train_hidden_tests", "PRIVATE_KEY", "secret"]:
        assert sentinel not in line
    with pytest.raises(PistonTunnelSupervisorError, match="schema"):
        sanitized_event("health_transition", healthy=True, reconnect_count=2)
    with pytest.raises(PistonTunnelSupervisorError, match="nonnegative integers"):
        sanitized_event("reconnect", reconnect_count=1.5, backoff_seconds=0.5)
