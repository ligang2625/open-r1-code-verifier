"""Tests for reproducibility metadata collection."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import code_verifier.environment as environment_module
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


def test_gpu_identity_without_torch_returns_cpu_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing torch must not make environment collection fail or invent CUDA identity."""

    def missing_torch(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", missing_torch)

    assert environment_module._gpu_identity() == (None, None, 0)


def test_gpu_identity_without_available_cuda_returns_cpu_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """A CUDA-built torch with no available CUDA device is still a CPU/no-CUDA environment."""
    fake_torch = SimpleNamespace(
        version=SimpleNamespace(cuda="12.1"),
        cuda=SimpleNamespace(is_available=lambda: False),
    )
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch)

    assert environment_module._gpu_identity() == (None, None, 0)


def test_gpu_identity_with_available_cuda_records_runtime_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Available CUDA records the CUDA version, first GPU name, and device count."""
    fake_torch = SimpleNamespace(
        version=SimpleNamespace(cuda="12.1"),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: 2,
            get_device_name=lambda index: "Mock GPU 0" if index == 0 else "Mock GPU 1",
        ),
    )
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch)

    assert environment_module._gpu_identity() == ("12.1", "Mock GPU 0", 2)


def test_gpu_capabilities_without_cuda_returns_nulls(monkeypatch: pytest.MonkeyPatch) -> None:
    """No available CUDA device yields null capability and BF16 support."""
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch)

    assert environment_module._gpu_capabilities() == (None, None)


def test_gpu_capabilities_records_capability_and_bf16(monkeypatch: pytest.MonkeyPatch) -> None:
    """Available CUDA records compute capability and BF16 support."""
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_device_capability=lambda index: (7, 5),
            is_bf16_supported=lambda: False,
        ),
    )
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch)

    assert environment_module._gpu_capabilities() == ("7.5", False)
