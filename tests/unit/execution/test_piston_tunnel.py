"""Deterministic unit tests for the non-deployed Piston tunnel supervisor."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from code_verifier.execution import piston_tunnel
from code_verifier.execution.piston_resilience import PistonTransportTelemetry
from code_verifier.execution.piston_tunnel import (
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


class _ExitedProcess:
    def __init__(self, rc: int) -> None:
        self.rc = rc

    def poll(self) -> int:
        return self.rc

    def wait(self) -> int:
        return self.rc


class _PollingProcess:
    def __init__(self, polls: list[int | None], rc: int) -> None:
        self._polls = list(polls)
        self.rc = rc

    def poll(self) -> int | None:
        return self._polls.pop(0)

    def wait(self) -> int:
        return self.rc


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


def test_reconnect_state_machine_is_bounded_and_emits_required_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    processes = [_ExitedProcess(255), _ExitedProcess(255), _ExitedProcess(255)]
    events: list[str] = []
    sleeps: list[float] = []
    now = iter([10.0, 11.0])
    telemetry = PistonTransportTelemetry()

    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(reconnect_backoff_seconds=(0.5, 1.0), max_reconnects=2),
        lock_path=tmp_path / "supervisor.lock",
        health_check=lambda: False,
        emit=events.append,
        popen=lambda argv: cast(subprocess.Popen[bytes], processes.pop(0)),
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


def test_supervisor_records_outage_end_and_successful_health_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(piston_tunnel, "assert_port_available_before_start", lambda host, port: None)
    process = _PollingProcess([None, None, 255], 255)
    health = iter([False, True])
    now = iter([10.0, 12.0, 13.0, 14.0])
    events: list[str] = []
    telemetry = PistonTransportTelemetry()
    supervisor = TunnelSupervisor(
        TunnelSupervisorConfig(max_reconnects=0),
        lock_path=tmp_path / "supervisor.lock",
        health_check=lambda: next(health),
        emit=events.append,
        popen=lambda argv: cast(subprocess.Popen[bytes], process),
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
        health_check=lambda: False,
        emit=events.append,
        popen=lambda argv: cast(subprocess.Popen[bytes], _ExitedProcess(255)),
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


def test_supervisor_telemetry_has_no_candidate_test_or_secret_payload() -> None:
    line = sanitized_event("health_transition", healthy=True)
    decoded = json.loads(line)
    assert decoded == {"event": "health_transition", "healthy": True}
    for sentinel in ["candidate", "visible_tests", "train_hidden_tests", "PRIVATE_KEY", "secret"]:
        assert sentinel not in line
    with pytest.raises(PistonTunnelSupervisorError, match="schema"):
        sanitized_event("health_transition", healthy=True, reconnect_count=2)
