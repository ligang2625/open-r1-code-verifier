"""Collect reproducibility metadata for CodeVerifier runs.

Example:
    record = collect_environment()
"""

from __future__ import annotations

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
    """Serializable versions needed to reproduce a run."""

    project_commit: str | None
    open_r1_commit: str | None
    python_version: str
    platform: str
    packages: dict[str, str | None]


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


def _distribution_version(distribution: str) -> str | None:
    """Return an installed distribution version without importing the package."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def collect_environment(repository_root: Path | None = None) -> EnvironmentRecord:
    """Collect project, submodule, runtime, and dependency versions."""
    root = (repository_root or _find_repository_root()).resolve()
    return {
        "project_commit": _git_commit(root),
        "open_r1_commit": _git_commit(root / OPEN_R1_SUBMODULE),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {name: _distribution_version(name) for name in TRACKED_DISTRIBUTIONS},
    }


def write_environment_record(output_path: Path, repository_root: Path | None = None) -> EnvironmentRecord:
    """Collect and write a deterministic, human-readable JSON record."""
    record = collect_environment(repository_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
