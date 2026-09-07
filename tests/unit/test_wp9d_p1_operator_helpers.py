from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

EVIDENCE = Path("ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/operator_evidence.py")
ACCEPTED = Path("ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/accepted_pointer.py")
COMMIT = "a" * 40
SCRIPT_SHA = "b" * 64


def _evidence_command(output: Path, artifact: Path | None = None, *, command_rc: str = "0") -> list[str]:
    command = [
        sys.executable,
        str(EVIDENCE),
        "--output",
        str(output),
        "--phase",
        "single",
        "--detail",
        "public",
        "--handoff-commit",
        COMMIT,
        "--script-path",
        "ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/run.sh",
        "--script-sha256",
        SCRIPT_SHA,
        "--target-repo",
        "/root/open-r1-code-verifier",
        "--artifact-root",
        "/root/sj-tmp/open-r1-code-verifier-outputs",
        "--formal-data-root",
        "/root/open-r1-code-verifier-data-4090",
        "--hf-home",
        "/root/huggingface",
        "--piston-endpoint",
        "http://127.0.0.1:2000",
        "--gpu-name",
        "NVIDIA GeForce RTX 4090",
        "--gpu-total-mib",
        "24564",
        "--started-at",
        "2026-09-07T00:00:00Z",
        "--ended-at",
        "2026-09-07T00:01:00Z",
        "--command-rc",
        command_rc,
        "--postcheck-rc",
        "0",
        "--gate-status",
        "passed",
    ]
    if artifact is not None:
        command.extend(["--artifact", str(artifact)])
    return command


def test_operator_evidence_and_accepted_pointer_round_trip(tmp_path: Path) -> None:
    artifact = tmp_path / "run.json"
    artifact.write_text('{"status":"completed"}\n', encoding="utf-8")
    evidence = tmp_path / "operator-evidence.json"
    result = subprocess.run(_evidence_command(evidence, artifact), check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    value = json.loads(evidence.read_text(encoding="utf-8"))
    assert value["gate_status"] == "passed"
    assert value["handoff_commit"] == COMMIT
    assert value["artifact_inventory"][0]["path"] == str(artifact.resolve())
    assert len(value["artifact_inventory"][0]["sha256"]) == 64

    pointer = tmp_path / "accepted.json"
    accepted = subprocess.run(
        [
            sys.executable,
            str(ACCEPTED),
            "--output",
            str(pointer),
            "--phase",
            "single",
            "--detail",
            "public",
            "--retry-tag",
            "r1",
            "--handoff-commit",
            COMMIT,
            "--primary-artifact",
            str(artifact),
            "--operator-evidence",
            str(evidence),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert accepted.returncode == 0, accepted.stderr
    pointer_value = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_value["schema_version"] == "wp9d-p1-accepted-v1"
    assert pointer_value["retry_tag"] == "r1"
    assert pointer_value["primary_artifact"] == str(artifact.resolve())


def test_passed_operator_evidence_requires_artifact_inventory(tmp_path: Path) -> None:
    result = subprocess.run(
        _evidence_command(tmp_path / "operator-evidence.json"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "at least one hashed artifact" in result.stderr


def test_passed_operator_evidence_rejects_nonzero_command_rc(tmp_path: Path) -> None:
    artifact = tmp_path / "run.json"
    artifact.write_text("{}\n", encoding="utf-8")
    result = subprocess.run(
        _evidence_command(tmp_path / "operator-evidence.json", artifact, command_rc="2"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "requires command_rc=0" in result.stderr
