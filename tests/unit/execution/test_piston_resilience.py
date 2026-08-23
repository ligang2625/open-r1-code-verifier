"""CPU-only tests for bounded Piston transport recovery and policy identity."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

import code_verifier.execution.piston_resilience as resilience_module
from code_verifier.execution import ExecutionStatus
from code_verifier.execution.piston import (
    PistonExecutor,
    PistonTransportError,
    PistonTransportFailureKind,
    piston_executor_config_from_mapping,
)
from code_verifier.execution.piston_resilience import (
    PistonTransportPolicy,
    PistonTransportTelemetry,
    load_piston_transport_policy,
    piston_transport_policy_sha256,
)


def _config() -> Any:
    return piston_executor_config_from_mapping(
        {
            "base_url": "http://127.0.0.1:2000",
            "language": "python",
            "version": "3.10.0",
            "request_timeout_margin_seconds": 2.0,
            "max_response_bytes": 131072,
            "max_output_bytes": 4096,
            "stop_on_first_failure": False,
        }
    )


def _policy(*, max_attempts: int = 3, backoff: tuple[float, ...] = (0.25, 1.0)) -> PistonTransportPolicy:
    base = load_piston_transport_policy(Path("configs/execution/piston-transport-resilience.yaml"))
    return replace(
        base,
        max_attempts=max_attempts,
        backoff_seconds=backoff,
        backoff_cap_seconds=max(backoff),
    )


def _runtime_record() -> dict[str, object]:
    return {"language": "python", "version": "3.10.0", "aliases": ["py3"], "runtime": "python"}


def _response(marker: str = "marker") -> dict[str, object]:
    report = json.dumps({"outcome": "passed", "runtime_ms": 1.0, "stdout": "", "stderr": ""})
    return {
        "language": "python",
        "version": "3.10.0",
        "run": {
            "stdout": f"__CODE_VERIFIER_RESULT__:{marker}:{report}\n",
            "stderr": "",
            "code": 0,
            "signal": None,
            "message": None,
            "status": None,
            "cpu_time": 1.0,
            "wall_time": 1.0,
            "memory": 1024,
        },
    }


class _ScriptedTransport:
    def __init__(self, responses: list[object], *, runtimes: list[object] | None = None) -> None:
        self.responses = list(responses)
        self.runtimes = list(runtimes or [[_runtime_record()]])
        self.execute_calls: list[dict[str, object]] = []
        self.execute_serialized: list[bytes] = []
        self.runtime_calls = 0

    def list_runtimes(self, *, timeout_seconds: float, max_response_bytes: int) -> object:
        del timeout_seconds, max_response_bytes
        self.runtime_calls += 1
        value = self.runtimes.pop(0) if self.runtimes else [_runtime_record()]
        if isinstance(value, BaseException):
            raise value
        return value

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        del timeout_seconds, max_response_bytes
        self.execute_calls.append(payload)
        self.execute_serialized.append(
            json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def _execute(
    responses: list[object],
    *,
    policy: PistonTransportPolicy | None = None,
    runtimes: list[object] | None = None,
) -> tuple[Any, _ScriptedTransport, PistonTransportTelemetry, list[float]]:
    transport = _ScriptedTransport(responses, runtimes=runtimes)
    telemetry = PistonTransportTelemetry()
    sleeps: list[float] = []
    executor = PistonExecutor(
        _config(),
        transport=transport,
        marker_factory=lambda: "marker",
        transport_policy=policy,
        transport_telemetry=telemetry,
        sleep=sleeps.append,
    )
    result = executor.execute(
        "def target(value):\n    return value\n",
        "target",
        [{"input": [1], "expected": 1}],
        1.0,
        32,
    )
    return result, transport, telemetry, sleeps


def test_connection_refused_revalidates_runtime_and_retries_exact_request() -> None:
    refused = PistonTransportError(
        "refused",
        kind=PistonTransportFailureKind.CONNECTION_REFUSED,
    )
    result, transport, telemetry, sleeps = _execute([refused, _response()], policy=_policy())
    assert result.status is ExecutionStatus.PASSED
    assert len(transport.execute_calls) == 2
    assert transport.execute_calls[0] is transport.execute_calls[1]
    assert transport.execute_serialized[0] == transport.execute_serialized[1]
    assert transport.runtime_calls == 1
    assert sleeps == [0.25]
    assert telemetry.to_mapping() == {
        "transport_requests": 2,
        "transport_connect_failures": 1,
        "transport_safe_retries": 1,
        "transport_retry_successes": 1,
        "transport_retry_exhausted": 0,
        "transport_ambiguous_failures": 0,
        "tunnel_reconnect_count": 0,
        "tunnel_total_outage_seconds": 0.0,
        "tunnel_max_outage_seconds": 0.0,
    }


def test_safe_retry_exhausted_is_sanitized_infrastructure_failure() -> None:
    refused = PistonTransportError("private", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    result, transport, telemetry, sleeps = _execute(
        [refused, refused, refused],
        policy=_policy(max_attempts=3),
        runtimes=[[_runtime_record()], [_runtime_record()]],
    )
    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert result.test_results[0].stderr == "piston transport failed"
    assert len(transport.execute_calls) == 3
    assert sleeps == [0.25, 1.0]
    assert telemetry.transport_requests == 3
    assert telemetry.transport_safe_retries == 2
    assert telemetry.transport_retry_exhausted == 1


@pytest.mark.parametrize(
    ("kind", "expected_ambiguous"),
    [
        (PistonTransportFailureKind.READ_TIMEOUT, 1),
        (PistonTransportFailureKind.CONNECTION_RESET, 1),
        (PistonTransportFailureKind.HTTP_ERROR, 1),
        (PistonTransportFailureKind.INVALID_RESPONSE, 1),
        (PistonTransportFailureKind.OVERSIZED_RESPONSE, 1),
        (PistonTransportFailureKind.INVALID_REQUEST, 0),
    ],
)
def test_ambiguous_or_unsafe_failures_are_never_retried(
    kind: PistonTransportFailureKind,
    expected_ambiguous: int,
) -> None:
    failure = PistonTransportError("private", kind=kind)
    result, transport, telemetry, sleeps = _execute([failure], policy=_policy())
    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert len(transport.execute_calls) == 1
    assert transport.runtime_calls == 0
    assert sleeps == []
    assert telemetry.transport_requests == 1
    assert telemetry.transport_safe_retries == 0
    assert telemetry.transport_ambiguous_failures == expected_ambiguous


def test_safe_health_wait_can_recover_before_exact_resend() -> None:
    refused = PistonTransportError("refused", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    runtime_failure = PistonTransportError("still down", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    result, transport, telemetry, sleeps = _execute(
        [refused, _response()],
        policy=_policy(),
        runtimes=[runtime_failure, [_runtime_record()]],
    )
    assert result.status is ExecutionStatus.PASSED
    assert len(transport.execute_calls) == 2
    assert transport.execute_serialized[0] == transport.execute_serialized[1]
    assert transport.runtime_calls == 2
    assert sleeps == [0.25, 0.5]
    assert telemetry.transport_safe_retries == 1
    assert telemetry.transport_retry_successes == 1


def test_safe_health_wait_exhausts_without_candidate_resend() -> None:
    refused = PistonTransportError("refused", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    runtime_failure = PistonTransportError("still down", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    result, transport, telemetry, sleeps = _execute(
        [refused],
        policy=_policy(),
        runtimes=[runtime_failure] * 7,
    )
    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert len(transport.execute_calls) == 1
    assert transport.runtime_calls == 7
    assert sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 10.0]
    assert telemetry.transport_retry_exhausted == 1


def test_unsafe_health_revalidation_failure_fails_closed_without_resend() -> None:
    refused = PistonTransportError("refused", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    runtime_failure = PistonTransportError("timeout", kind=PistonTransportFailureKind.READ_TIMEOUT)
    result, transport, telemetry, sleeps = _execute(
        [refused],
        policy=_policy(),
        runtimes=[runtime_failure],
    )
    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert len(transport.execute_calls) == 1
    assert transport.runtime_calls == 1
    assert sleeps == [0.25]
    assert telemetry.transport_retry_exhausted == 1


def test_legitimate_sandbox_and_candidate_verdicts_do_not_retry() -> None:
    wrong_answer = _response()
    wrong_report = json.dumps({"outcome": "wrong_answer", "runtime_ms": 1.0, "stdout": "", "stderr": ""})
    cast(dict[str, object], wrong_answer["run"])["stdout"] = f"__CODE_VERIFIER_RESULT__:marker:{wrong_report}\n"
    sandbox = _response()
    cast(dict[str, object], sandbox["run"]).update({"status": "XX", "code": None})
    timeout = _response()
    cast(dict[str, object], timeout["run"]).update({"status": "TO", "code": None})
    runtime_error = _response()
    cast(dict[str, object], runtime_error["run"]).update({"status": "RE", "code": 1})
    memory = _response()
    cast(dict[str, object], memory["run"]).update(
        {"status": "SG", "code": None, "signal": "SIGKILL", "message": "memory limit"}
    )
    cases = [
        (_response(), ExecutionStatus.PASSED),
        (wrong_answer, ExecutionStatus.WRONG_ANSWER),
        (sandbox, ExecutionStatus.SANDBOX_ERROR),
        (timeout, ExecutionStatus.TIMEOUT),
        (runtime_error, ExecutionStatus.RUNTIME_ERROR),
        (memory, ExecutionStatus.MEMORY_LIMIT),
    ]
    for response, expected in cases:
        result, transport, telemetry, sleeps = _execute([response], policy=_policy())
        assert result.status is expected
        assert len(transport.execute_calls) == 1
        assert telemetry.transport_safe_retries == 0
        assert sleeps == []


def test_retry_attempts_and_backoff_are_bounded_by_policy() -> None:
    refused = PistonTransportError("refused", kind=PistonTransportFailureKind.CONNECTION_REFUSED)
    result, transport, telemetry, sleeps = _execute(
        [refused, refused, refused, _response()],
        policy=_policy(max_attempts=3, backoff=(0.1,)),
        runtimes=[[_runtime_record()], [_runtime_record()]],
    )
    assert result.status is ExecutionStatus.SANDBOX_ERROR
    assert len(transport.execute_calls) == 3
    assert telemetry.transport_retry_exhausted == 1
    assert sleeps == [0.1, 0.1]


def test_policy_identity_is_separate_deterministic_and_binds_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path("configs/execution/piston-transport-resilience.yaml")
    policy = load_piston_transport_policy(path)
    first = piston_transport_policy_sha256(path)
    second = piston_transport_policy_sha256(path)
    assert policy.max_attempts == 3
    assert policy.backoff_cap_seconds == 1.0
    assert policy.health_probe.required_runtime == "3.10.0"
    assert policy.health_probe.max_wait_attempts == 7
    assert policy.health_probe.backoff_seconds == (0.5, 1.0, 2.0, 4.0, 8.0, 10.0)
    assert policy.tunnel_supervisor.ssh_target == "1660ti-wsl"
    assert policy.tunnel_supervisor.max_reconnects == 8
    assert first == second
    monkeypatch.setattr(resilience_module, "PISTON_TRANSPORT_CLASSIFIER_IMPLEMENTATION_VERSION", "changed")
    assert piston_transport_policy_sha256(path) != first
    assert len(first) == 64
    assert all(character in "0123456789abcdef" for character in first)
    assert Path("configs/execution/piston-local.yaml").read_bytes() == (
        b'piston:\n  base_url: http://127.0.0.1:2000\n  language: python\n  version: "3.10.0"\n'
        b"  request_timeout_margin_seconds: 30.0\n  max_response_bytes: 131072\n"
        b"  max_output_bytes: 4096\n  stop_on_first_failure: false\n"
    )


def test_telemetry_rejects_nonfinite_or_negative_values_and_has_no_payload_fields() -> None:
    telemetry = PistonTransportTelemetry(transport_requests=1, transport_safe_retries=1)
    encoded = json.dumps(telemetry.to_mapping(), sort_keys=True)
    for sentinel in ["candidate", "visible_tests", "train_hidden_tests", "PRIVATE_KEY", "secret"]:
        assert sentinel not in encoded
    telemetry.transport_requests = -1
    with pytest.raises(ValueError, match="nonnegative integers"):
        telemetry.to_mapping()
    telemetry.transport_requests = 1.5  # type: ignore[assignment]
    with pytest.raises(ValueError, match="nonnegative integers"):
        telemetry.to_mapping()
    telemetry.transport_requests = 10**10000
    mapping = telemetry.to_mapping()
    assert mapping["transport_requests"] == 10**10000


def test_transport_request_counter_is_recorded_only_after_transport_invocation() -> None:
    transport = _ScriptedTransport([_response()])
    telemetry = PistonTransportTelemetry()

    def fail_snapshot(_mapping: object) -> None:
        assert len(transport.execute_calls) == 1
        raise RuntimeError("telemetry persistence failed")

    telemetry.set_on_change(fail_snapshot)
    executor = PistonExecutor(
        _config(),
        transport=transport,
        marker_factory=lambda: "marker",
        transport_policy=_policy(),
        transport_telemetry=telemetry,
        sleep=lambda seconds: None,
    )
    with pytest.raises(RuntimeError, match="telemetry persistence failed"):
        executor.execute(
            "def target(value):\n    return value\n",
            "target",
            [{"input": [1], "expected": 1}],
            1.0,
            32,
        )
    assert telemetry.transport_requests == 1


def test_telemetry_restore_is_cumulative_and_every_mutation_can_be_durably_snapshotted() -> None:
    snapshots: list[dict[str, int | float]] = []
    telemetry = PistonTransportTelemetry()
    telemetry.restore(
        {
            "transport_requests": 7,
            "transport_connect_failures": 2,
            "transport_safe_retries": 1,
            "transport_retry_successes": 1,
            "transport_retry_exhausted": 0,
            "transport_ambiguous_failures": 1,
            "tunnel_reconnect_count": 3,
            "tunnel_total_outage_seconds": 4.5,
            "tunnel_max_outage_seconds": 2.5,
        }
    )
    telemetry.set_on_change(lambda mapping: snapshots.append(dict(mapping)))
    telemetry.record_transport_request()
    telemetry.record_safe_retry()
    assert telemetry.transport_requests == 8
    assert telemetry.transport_safe_retries == 2
    assert len(snapshots) == 2
    assert snapshots[-1] == telemetry.to_mapping()
