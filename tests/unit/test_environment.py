"""Tests for reproducibility metadata collection."""

import json
from pathlib import Path

from code_verifier.environment import collect_environment, write_environment_record

PINNED_OPEN_R1_COMMIT = "1416fa0cf21595d2083b399a2a0bbddd7f6e9563"


def test_collect_environment_records_pinned_submodule() -> None:
    """The checked-out submodule matches the repository's documented pin."""
    repository_root = Path(__file__).resolve().parents[2]

    record = collect_environment(repository_root)

    assert record["open_r1_commit"] == PINNED_OPEN_R1_COMMIT
    assert record["python_version"]
    assert len(record["dependency_lock_hash"]) == 64
    assert isinstance(record["gpu_count"], int)
    assert record["gpu_count"] >= 0
    assert record["gpu_name"] is None or record["gpu_name"]
    assert record["cuda_version"] is None or record["cuda_version"]


def test_write_environment_record_is_json(tmp_path: Path) -> None:
    """The environment writer produces reusable JSON metadata."""
    repository_root = Path(__file__).resolve().parents[2]
    output_path = tmp_path / "run" / "environment.json"

    record = write_environment_record(output_path, repository_root)

    assert json.loads(output_path.read_text(encoding="utf-8")) == record
