from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from code_verifier.training.sft import (
    SFTCheckpointIdentity,
    SFTTrainingConfig,
    SFTTrainingError,
    _load_merged_parent_sft_policy,
    _parent_sft_mapping,
    _validate_parent_sft,
)


def _parent(tmp_path: Path) -> SFTCheckpointIdentity:
    return SFTCheckpointIdentity(
        run_dir=tmp_path / "parent",
        checkpoint_dir=tmp_path / "parent" / "checkpoints",
        run_id="B-test",
        model_id="example/model",
        model_revision="rev-test",
        dataset_hash="a" * 64,
        config_hash="b" * 64,
        dependency_lock_hash="c" * 64,
        seed=42,
    )


def test_parent_identity_mapping_and_model_guard(tmp_path: Path) -> None:
    parent = _parent(tmp_path)
    config = cast(
        SFTTrainingConfig,
        SimpleNamespace(model_id="example/model", model_revision="rev-test"),
    )
    _validate_parent_sft(config, parent)
    assert _parent_sft_mapping(parent) == {
        "run_id": "B-test",
        "model_id": "example/model",
        "model_revision": "rev-test",
        "dataset_hash": "a" * 64,
        "config_hash": "b" * 64,
        "dependency_lock_hash": "c" * 64,
        "seed": 42,
    }

    wrong = cast(SFTTrainingConfig, SimpleNamespace(model_id="other/model", model_revision="rev-test"))
    with pytest.raises(SFTTrainingError, match="model identity"):
        _validate_parent_sft(wrong, parent)


def test_parent_policy_is_loaded_read_only_and_safe_merged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _parent(tmp_path)
    base_model = object()
    merged_model = object()
    calls: dict[str, object] = {}

    class FakeConfigType:
        @classmethod
        def from_pretrained(cls, path: str) -> SimpleNamespace:
            calls["config_path"] = path
            return SimpleNamespace(base_model_name_or_path="example/model", revision="rev-test")

    class FakeParentPolicy:
        def merge_and_unload(self, *, safe_merge: bool) -> object:
            calls["safe_merge"] = safe_merge
            return merged_model

    class FakeModelType:
        @classmethod
        def from_pretrained(
            cls,
            model: object,
            path: str,
            *,
            is_trainable: bool,
            config: object,
        ) -> FakeParentPolicy:
            calls["base_model"] = model
            calls["model_path"] = path
            calls["is_trainable"] = is_trainable
            calls["adapter_config"] = config
            return FakeParentPolicy()

    fake_peft = SimpleNamespace(PeftConfig=FakeConfigType, PeftModel=FakeModelType)
    original_import = importlib.import_module

    def fake_import(name: str, package: str | None = None) -> Any:
        if name == "peft":
            return fake_peft
        return original_import(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    runtime = cast(
        Any,
        SimpleNamespace(get_model=lambda model_args, training_args: base_model),
    )
    result = _load_merged_parent_sft_policy(
        parent_sft=parent,
        model_args=object(),
        training_args=object(),
        runtime=runtime,
    )

    assert result is merged_model
    assert calls["config_path"] == str(parent.checkpoint_dir)
    assert calls["model_path"] == str(parent.checkpoint_dir)
    assert calls["base_model"] is base_model
    assert calls["is_trainable"] is False
    assert calls["safe_merge"] is True
