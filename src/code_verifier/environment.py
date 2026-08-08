"""Collect reproducibility metadata for CodeVerifier runs.

Example:
    record = collect_environment()
"""

from __future__ import annotations

import hashlib
import importlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import TypedDict

OPEN_R1_SUBMODULE = Path("third_party/open-r1")
TRACKED_DISTRIBUTIONS = (
    "accelerate",
    "datasets",
    "open-r1",
    "peft",
    "torch",
    "transformers",
    "trl",
)


class EnvironmentRecord(TypedDict):
    """Serializable versions and hardware identity needed to reproduce a run."""

    project_commit: str | None
    open_r1_commit: str | None
    python_version: str
    platform: str
    packages: dict[str, str | None]
    cuda_version: str | None
    gpu_name: str | None
    gpu_count: int
    compute_capability: str | None
    bf16_supported: bool | None
    dependency_lock_hash: str


def _find_repository_root() -> Path:
    """Find the checkout that contains the project pyproject file."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / OPEN_R1_SUBMODULE).is_dir():
            return candidate
    raise RuntimeError("Could not locate the CodeVerifier repository root")


def _git_commit(repository: Path) -> str | None:
    """Return a repository HEAD, or None when Git metadata is unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    commit = result.stdout.strip()
    return commit or None


def _gitlink_commit(repository: Path, relative_path: Path) -> str | None:
    """Return the commit recorded by one submodule gitlink without requiring its worktree checkout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", f"HEAD:{relative_path.as_posix()}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    commit = result.stdout.strip()
    return commit or None


def _distribution_version(distribution: str) -> str | None:
    """Return an installed distribution version without importing the package."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def _dependency_lock_hash(root: Path, packages: dict[str, str | None]) -> str:
    """Hash uv.lock when present, otherwise hash pyproject plus tracked installed versions."""
    lock_path = root / "uv.lock"
    digest = hashlib.sha256()
    if lock_path.is_file():
        digest.update(b"uv.lock\0")
        digest.update(lock_path.read_bytes())
    else:
        digest.update(b"pyproject+installed-versions\0")
        digest.update((root / "pyproject.toml").read_bytes())
        digest.update(json.dumps(packages, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def _gpu_identity() -> tuple[str | None, str | None, int]:
    """Collect CUDA/GPU identity when torch is installed, otherwise return stable nulls."""
    try:
        torch_runtime = importlib.import_module("torch")
    except ImportError:
        return None, None, 0
    try:
        available = bool(torch_runtime.cuda.is_available())
        if not available:
            return None, None, 0
        cuda = getattr(torch_runtime.version, "cuda", None)
        count = int(torch_runtime.cuda.device_count())
        name = str(torch_runtime.cuda.get_device_name(0)) if count > 0 else None
    except Exception:
        return None, None, 0
    return None if cuda is None else str(cuda), name, count


def _gpu_capabilities() -> tuple[str | None, bool | None]:
    """Collect compute capability and native BF16 support when a CUDA device is available.

    ``bf16_supported`` records native hardware support only: torch's default
    ``is_bf16_supported()`` treats software/emulated BF16 tensors as supported
    (e.g. True on Turing), so the emulation path is explicitly excluded here.
    """
    try:
        torch_runtime = importlib.import_module("torch")
        if not bool(torch_runtime.cuda.is_available()):
            return None, None
        capability = ".".join(str(part) for part in torch_runtime.cuda.get_device_capability(0))
        bf16 = bool(torch_runtime.cuda.is_bf16_supported(including_emulation=False))
    except Exception:
        return None, None
    return capability, bf16


def collect_environment(repository_root: Path | None = None) -> EnvironmentRecord:
    """Collect project, submodule, runtime, dependency, and optional GPU identity."""
    root = (repository_root or _find_repository_root()).resolve()
    packages = {name: _distribution_version(name) for name in TRACKED_DISTRIBUTIONS}
    cuda_version, gpu_name, gpu_count = _gpu_identity()
    compute_capability, bf16_supported = _gpu_capabilities()
    return {
        "project_commit": _git_commit(root),
        "open_r1_commit": _gitlink_commit(root, OPEN_R1_SUBMODULE),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": packages,
        "cuda_version": cuda_version,
        "gpu_name": gpu_name,
        "gpu_count": gpu_count,
        "compute_capability": compute_capability,
        "bf16_supported": bf16_supported,
        "dependency_lock_hash": _dependency_lock_hash(root, packages),
    }


def write_environment_record(output_path: Path, repository_root: Path | None = None) -> EnvironmentRecord:
    """Collect and write a deterministic, human-readable JSON record."""
    record = collect_environment(repository_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
