"""Tests for safe project YAML loading."""

from pathlib import Path

import pytest

from code_verifier.config import ConfigError, load_yaml_mapping


def test_load_yaml_mapping_returns_mapping(tmp_path: Path) -> None:
    """A valid YAML mapping is returned as a plain dictionary."""
    path = tmp_path / "config.yaml"
    path.write_text("answer: 42\n", encoding="utf-8")

    assert load_yaml_mapping(path) == {"answer": 42}


def test_load_yaml_mapping_rejects_non_mapping(tmp_path: Path) -> None:
    """A sequence at the document root is unsupported."""
    path = tmp_path / "config.yaml"
    path.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="top-level mapping"):
        load_yaml_mapping(path)


def test_load_yaml_mapping_rejects_invalid_yaml(tmp_path: Path) -> None:
    """YAML syntax errors retain the configuration path."""
    path = tmp_path / "broken.yaml"
    path.write_text("key: [unterminated\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=str(path)):
        load_yaml_mapping(path)


def test_load_yaml_mapping_rejects_missing_file(tmp_path: Path) -> None:
    """A missing configuration file yields an explicit error."""
    path = tmp_path / "missing.yaml"

    with pytest.raises(ConfigError, match=str(path)):
        load_yaml_mapping(path)
