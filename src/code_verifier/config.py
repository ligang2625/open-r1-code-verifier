"""Safe, minimal loading for project YAML configuration files.

Example:
    config = load_yaml_mapping(Path("configs/data/smoke.yaml"))
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml


class ConfigError(ValueError):
    """Raised when a project YAML config is missing, malformed, or unsupported."""


def load_yaml_mapping(path: Path) -> dict[str, object]:
    """Load one YAML file and require a top-level mapping."""
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"Could not read config {path}: {error}") from error

    try:
        loaded = cast(object, yaml.safe_load(contents))
    except yaml.YAMLError as error:
        raise ConfigError(f"Invalid YAML in config {path}: {error}") from error

    if not isinstance(loaded, dict):
        raise ConfigError(f"Config {path} must contain a non-empty top-level mapping")
    if not all(isinstance(key, str) for key in loaded):
        raise ConfigError(f"Config {path} must use string keys")
    return cast(dict[str, object], loaded)
