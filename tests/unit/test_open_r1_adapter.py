"""Tests for the Open-R1 integration boundary."""

import pytest

from code_verifier.training.open_r1_adapter import import_open_r1_module, open_r1_version


def test_adapter_imports_editable_open_r1() -> None:
    """The dual-editable install exposes the pinned upstream package."""
    assert import_open_r1_module().__name__ == "open_r1"
    assert open_r1_version() == "0.1.0.dev0"


def test_adapter_rejects_non_open_r1_modules() -> None:
    """Callers cannot use the adapter as an unrestricted import helper."""
    with pytest.raises(ValueError, match="open_r1 module name"):
        import_open_r1_module("transformers")


def test_open_r1_sft_modules_resolve_only_through_adapter() -> None:
    configs = import_open_r1_module("open_r1.configs")
    model_utils = import_open_r1_module("open_r1.utils.model_utils")

    assert hasattr(configs, "SFTConfig")
    assert hasattr(model_utils, "get_model")
    assert hasattr(model_utils, "get_tokenizer")
