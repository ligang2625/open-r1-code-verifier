"""Tests for GRPO transport policy identity and cumulative telemetry sidecar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_verifier import cli
from code_verifier.execution import PistonTransportTelemetry
from code_verifier.training import GRPOTrainingError


def test_transport_sidecar_round_trip_preserves_cumulative_telemetry(tmp_path: Path) -> None:
    path = tmp_path / "transport-telemetry" / "C-public.json"
    telemetry = PistonTransportTelemetry(
        transport_requests=7,
        transport_connect_failures=2,
        transport_safe_retries=2,
        transport_retry_successes=1,
        transport_retry_exhausted=1,
        transport_ambiguous_failures=3,
        tunnel_reconnect_count=4,
        tunnel_total_outage_seconds=5.5,
        tunnel_max_outage_seconds=3.25,
    )
    cli._write_transport_sidecar(
        path,
        run_name="C-public",
        piston_definition_sha256="a" * 64,
        piston_transport_policy_sha256="b" * 64,
        telemetry=telemetry,
    )
    restored = PistonTransportTelemetry()
    cli._restore_transport_sidecar(
        path,
        run_name="C-public",
        piston_definition_sha256="a" * 64,
        piston_transport_policy_sha256="b" * 64,
        telemetry=restored,
    )
    assert restored.to_mapping() == telemetry.to_mapping()
    decoded = json.loads(path.read_text(encoding="utf-8"))
    assert set(decoded) == {
        "version",
        "run_name",
        "piston_definition_sha256",
        "piston_transport_policy_sha256",
        "telemetry_semantics",
        "telemetry",
    }
    assert decoded["telemetry_semantics"] == "cumulative_durable_snapshot_per_mutation_v1"
    for forbidden in ["candidate", "visible_tests", "train_hidden_tests", "PRIVATE_KEY", "secret"]:
        assert forbidden not in path.read_text(encoding="utf-8")


def test_transport_sidecar_missing_on_resume_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(GRPOTrainingError, match="required for resume"):
        cli._restore_transport_sidecar(
            tmp_path / "missing.json",
            run_name="C-public",
            piston_definition_sha256="a" * 64,
            piston_transport_policy_sha256="b" * 64,
            telemetry=PistonTransportTelemetry(),
        )


def test_transport_sidecar_resume_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.json"
    cli._write_transport_sidecar(
        path,
        run_name="C-public",
        piston_definition_sha256="a" * 64,
        piston_transport_policy_sha256="b" * 64,
        telemetry=PistonTransportTelemetry(transport_requests=1),
    )
    with pytest.raises(GRPOTrainingError, match="identity does not match"):
        cli._restore_transport_sidecar(
            path,
            run_name="C-public",
            piston_definition_sha256="a" * 64,
            piston_transport_policy_sha256="c" * 64,
            telemetry=PistonTransportTelemetry(),
        )


def test_transport_sidecar_rejects_malformed_or_negative_telemetry(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.json"
    telemetry_mapping = PistonTransportTelemetry().to_mapping()
    telemetry_mapping["transport_requests"] = -1
    value = {
        "version": 1,
        "run_name": "C-public",
        "piston_definition_sha256": "a" * 64,
        "piston_transport_policy_sha256": "b" * 64,
        "telemetry_semantics": "cumulative_durable_snapshot_per_mutation_v1",
        "telemetry": telemetry_mapping,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(GRPOTrainingError, match="finite and nonnegative"):
        cli._restore_transport_sidecar(
            path,
            run_name="C-public",
            piston_definition_sha256="a" * 64,
            piston_transport_policy_sha256="b" * 64,
            telemetry=PistonTransportTelemetry(),
        )
