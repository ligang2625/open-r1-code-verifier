"""Tests for deterministic evaluation prompt and generation contracts."""

from __future__ import annotations

import importlib
import math
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import code_verifier.evaluation.generate as generation_module
from code_verifier.data.schema import CodeProblem, ProblemMetadata
from code_verifier.data.schema import TestCase as CodeTestCase
from code_verifier.evaluation.generate import (
    GenerationConfig,
    GenerationError,
    GenerationResult,
    TransformersCompletionGenerator,
    build_evaluation_prompt,
)


class _FakeTensor:
    def __init__(self, rows: list[list[int]]) -> None:
        self.rows = rows
        self.device: str | None = None

    def __getitem__(self, index: int) -> list[int]:
        return self.rows[index]

    def to(self, device: str) -> _FakeTensor:
        self.device = device
        return self


class _FakeTokenizer:
    def __init__(self) -> None:
        self.chat_template = "fake-template"
        self.messages: list[dict[str, str]] | None = None
        self.decoded_ids: list[int] | None = None

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        add_generation_prompt: bool,
        tokenize: bool,
    ) -> str:
        assert add_generation_prompt is True
        assert tokenize is False
        self.messages = messages
        return "rendered-prompt"

    def __call__(self, text: str, *, return_tensors: str, add_special_tokens: bool) -> dict[str, _FakeTensor]:
        assert text == "rendered-prompt"
        assert return_tensors == "pt"
        assert add_special_tokens is False
        return {"input_ids": _FakeTensor([[1, 2, 3]])}

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool) -> str:
        assert skip_special_tokens is True
        self.decoded_ids = list(token_ids)
        return "```python\ndef add_one(x):\n    return x + 1\n```"


class _FakeModel:
    def __init__(self) -> None:
        self.device = "cpu"
        self.dtype: Any = None
        self.eval_called = False
        self.to_device: str | None = None
        self.generate_kwargs: dict[str, object] | None = None

    def to(self, device: str) -> _FakeModel:
        self.to_device = device
        self.device = device
        return self

    def eval(self) -> None:
        self.eval_called = True

    def generate(self, **kwargs: object) -> list[list[int]]:
        self.generate_kwargs = dict(kwargs)
        return [[1, 2, 3, 9, 10]]


class _FakeLoader:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[tuple[str, dict[str, object]]] = []

    def from_pretrained(self, model_id: str, **kwargs: object) -> object:
        self.calls.append((model_id, dict(kwargs)))
        return self.value


class _FakeTransformers:
    def __init__(self, tokenizer: _FakeTokenizer, model: _FakeModel) -> None:
        self.AutoTokenizer = _FakeLoader(tokenizer)
        self.AutoModelForCausalLM = _FakeLoader(model)
        self.seeds: list[int] = []

    def set_seed(self, seed: int) -> None:
        self.seeds.append(seed)


class _FakeTorch:
    float16 = "fake-float16"
    bfloat16 = "fake-bfloat16"
    float32 = "fake-float32"

    @staticmethod
    def inference_mode() -> Any:
        return nullcontext()


class _FakePeftConfigLoader:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[tuple[str, dict[str, object]]] = []

    def from_pretrained(self, adapter_dir: str, **kwargs: object) -> object:
        self.calls.append((adapter_dir, dict(kwargs)))
        return self.value


class _FakePeftModelLoader:
    def __init__(self, runtime: _FakeTransformers, *, failure: Exception | None = None) -> None:
        self.runtime = runtime
        self.failure = failure
        self.calls: list[tuple[object, str, dict[str, object]]] = []

    def from_pretrained(self, model: object, adapter_dir: str, **kwargs: object) -> object:
        assert self.runtime.AutoModelForCausalLM.calls
        self.calls.append((model, adapter_dir, dict(kwargs)))
        if self.failure is not None:
            raise self.failure
        return model


class _FakeStackedPeftConfigLoader:
    def __init__(self, values: dict[Path, object]) -> None:
        self.values = values
        self.calls: list[tuple[str, dict[str, object]]] = []

    def from_pretrained(self, adapter_dir: str, **kwargs: object) -> object:
        self.calls.append((adapter_dir, dict(kwargs)))
        return self.values[Path(adapter_dir)]


class _FakeParentPolicy:
    def __init__(
        self,
        merged_model: _FakeModel,
        calls: list[tuple[Any, ...]],
        *,
        merge_available: bool = True,
    ) -> None:
        self.merged_model = merged_model
        self.calls = calls
        if not merge_available:
            self.merge_and_unload = None  # type: ignore[assignment]

    def merge_and_unload(self, *, safe_merge: bool) -> _FakeModel:
        self.calls.append(("merge_b", safe_merge))
        return self.merged_model


class _FakeStackedPeftModelLoader:
    def __init__(
        self,
        *,
        parent_dir: Path,
        grpo_dir: Path,
        merged_model: _FakeModel,
        final_model: _FakeModel,
        calls: list[tuple[Any, ...]],
        merge_available: bool = True,
        grpo_failure: Exception | None = None,
    ) -> None:
        self.parent_dir = parent_dir
        self.grpo_dir = grpo_dir
        self.merged_model = merged_model
        self.final_model = final_model
        self.calls = calls
        self.merge_available = merge_available
        self.grpo_failure = grpo_failure

    def from_pretrained(self, model: object, adapter_dir: str, **kwargs: object) -> object:
        path = Path(adapter_dir)
        self.calls.append(("attach", path, model, dict(kwargs)))
        if path == self.parent_dir:
            return _FakeParentPolicy(self.merged_model, self.calls, merge_available=self.merge_available)
        assert path == self.grpo_dir
        assert model is self.merged_model
        if self.grpo_failure is not None:
            raise self.grpo_failure
        return self.final_model


def _peft_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    adapter_model_id: str = "example/model",
    adapter_revision: str | None = None,
    failure: Exception | None = None,
) -> tuple[Path, _FakeTokenizer, _FakeModel, _FakeTransformers, _FakePeftConfigLoader, _FakePeftModelLoader]:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    transformers_runtime = _FakeTransformers(tokenizer, model)
    adapter_config = SimpleNamespace(
        base_model_name_or_path=adapter_model_id,
        revision=adapter_revision,
    )
    config_loader = _FakePeftConfigLoader(adapter_config)
    model_loader = _FakePeftModelLoader(transformers_runtime, failure=failure)
    monkeypatch.setattr(
        generation_module,
        "_load_transformers_runtime",
        lambda: (_FakeTorch(), transformers_runtime),
    )
    monkeypatch.setattr(generation_module, "_load_peft_runtime", lambda: (config_loader, model_loader))
    return adapter_dir, tokenizer, model, transformers_runtime, config_loader, model_loader


def _stacked_peft_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    parent_model_id: str = "example/model",
    grpo_model_id: str = "example/model",
    parent_revision: str | None = "revision-1",
    grpo_revision: str | None = "revision-1",
    merge_available: bool = True,
    grpo_failure: Exception | None = None,
) -> tuple[
    Path,
    Path,
    _FakeModel,
    _FakeModel,
    _FakeTransformers,
    _FakeStackedPeftConfigLoader,
    _FakeStackedPeftModelLoader,
    list[tuple[Any, ...]],
]:
    parent_dir = (tmp_path / "parent-b").resolve()
    grpo_dir = (tmp_path / "grpo-cd").resolve()
    parent_dir.mkdir()
    grpo_dir.mkdir()
    tokenizer = _FakeTokenizer()
    base_model = _FakeModel()
    merged_model = _FakeModel()
    final_model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, base_model)
    calls: list[tuple[Any, ...]] = []
    config_loader = _FakeStackedPeftConfigLoader(
        {
            parent_dir: SimpleNamespace(base_model_name_or_path=parent_model_id, revision=parent_revision),
            grpo_dir: SimpleNamespace(base_model_name_or_path=grpo_model_id, revision=grpo_revision),
        }
    )
    model_loader = _FakeStackedPeftModelLoader(
        parent_dir=parent_dir,
        grpo_dir=grpo_dir,
        merged_model=merged_model,
        final_model=final_model,
        calls=calls,
        merge_available=merge_available,
        grpo_failure=grpo_failure,
    )
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), runtime))
    monkeypatch.setattr(generation_module, "_load_peft_runtime", lambda: (config_loader, model_loader))
    return parent_dir, grpo_dir, merged_model, final_model, runtime, config_loader, model_loader, calls


def _backend() -> tuple[TransformersCompletionGenerator, _FakeTokenizer, _FakeModel, _FakeTransformers]:
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    generator = TransformersCompletionGenerator(
        tokenizer=tokenizer,
        model=model,
        torch_runtime=_FakeTorch(),
        transformers_runtime=runtime,
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=512),
    )
    return generator, tokenizer, model, runtime


def _problem() -> CodeProblem:
    return CodeProblem(
        problem_id="prompt-1",
        source="unit",
        split="test",
        prompt="Add one to the input.",
        function_name="add_one",
        function_signature="def add_one(x: int) -> int:",
        starter_code=None,
        visible_tests=(CodeTestCase(input=1, expected=2),),
        train_hidden_tests=(CodeTestCase(input="TRAIN_HIDDEN_SENTINEL", expected=0),),
        eval_hidden_tests=(CodeTestCase(input="EVAL_HIDDEN_SENTINEL", expected=0),),
        reference_solution="REFERENCE_SOLUTION_SENTINEL",
        sft_response="SFT_RESPONSE_SENTINEL",
        metadata=ProblemMetadata(
            difficulty="easy",
            category=("math",),
            time_limit_seconds=1.0,
            memory_limit_mb=128,
            license="test",
            source_url_hash=None,
        ),
    )


def test_build_evaluation_prompt_matches_spec_template() -> None:
    prompt = build_evaluation_prompt(_problem())
    assert prompt == (
        "You are given a Python programming problem.\n\n"
        "Problem:\n"
        "Add one to the input.\n\n"
        "Function signature:\n"
        "def add_one(x: int) -> int:\n\n"
        "Visible examples:\n"
        '[{"expected":2,"input":1}]\n\n'
        "Return a correct implementation.\n"
        "The final answer must contain exactly one Python code block.\n"
        "Do not read from stdin unless the problem explicitly requires it.\n"
        "Do not print debugging information."
    )


def test_build_evaluation_prompt_contains_visible_examples_only() -> None:
    prompt = build_evaluation_prompt(_problem())
    assert '"input":1' in prompt
    assert '"expected":2' in prompt


def test_build_evaluation_prompt_excludes_hidden_sentinels() -> None:
    prompt = build_evaluation_prompt(_problem())
    for sentinel in (
        "TRAIN_HIDDEN_SENTINEL",
        "EVAL_HIDDEN_SENTINEL",
        "REFERENCE_SOLUTION_SENTINEL",
        "SFT_RESPONSE_SENTINEL",
    ):
        assert sentinel not in prompt


def test_build_evaluation_prompt_delegates_without_behavior_change(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = _problem()
    calls: list[CodeProblem] = []

    def fake_builder(value: CodeProblem) -> str:
        calls.append(value)
        return "shared prompt"

    monkeypatch.setattr(generation_module, "build_code_prompt", fake_builder)
    assert build_evaluation_prompt(problem) == "shared prompt"
    assert calls == [problem]


def test_generation_config_accepts_exact_pass1_defaults() -> None:
    config = GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=512)
    assert config.max_new_tokens == 512


@pytest.mark.parametrize(
    "kwargs",
    [
        {"do_sample": True, "temperature": None, "top_p": None, "max_new_tokens": 512},
        {"do_sample": False, "temperature": 0.0, "top_p": None, "max_new_tokens": 512},
        {"do_sample": False, "temperature": math.nan, "top_p": None, "max_new_tokens": 512},
        {"do_sample": False, "temperature": None, "top_p": 1.0, "max_new_tokens": 512},
        {"do_sample": False, "temperature": None, "top_p": math.inf, "max_new_tokens": 512},
        {"do_sample": False, "temperature": None, "top_p": None, "max_new_tokens": 0},
        {"do_sample": False, "temperature": None, "top_p": None, "max_new_tokens": 4097},
    ],
)
def test_generation_config_rejects_sampling_or_nonfinite_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(GenerationError):
        GenerationConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("completion", "tokens", "latency"),
    [
        ("ok", -1, 0.0),
        ("ok", 1, -1.0),
        ("ok", 1, math.nan),
        ("ok", 1, math.inf),
        ("\ud800", 1, 0.0),
    ],
)
def test_generation_result_contract_rejects_invalid_values(completion: str, tokens: int, latency: float) -> None:
    with pytest.raises(GenerationError):
        GenerationResult(completion=completion, completion_tokens=tokens, latency_ms=latency)


def test_transformers_generator_lazy_imports_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    calls = 0

    def fake_runtime() -> tuple[object, object]:
        nonlocal calls
        calls += 1
        return _FakeTorch(), runtime

    monkeypatch.setattr(generation_module, "_load_transformers_runtime", fake_runtime)
    generator = TransformersCompletionGenerator.from_pretrained(
        "example/model",
        model_revision="revision-1",
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=512),
    )

    assert isinstance(generator, TransformersCompletionGenerator)
    assert calls == 1
    assert model.eval_called is True
    assert model.to_device == "cpu"
    assert runtime.AutoTokenizer.calls[0][0] == "example/model"
    assert runtime.AutoModelForCausalLM.calls[0][0] == "example/model"
    safety_key = "trust_" + "remote_code"
    assert runtime.AutoTokenizer.calls[0][1][safety_key] is False
    assert runtime.AutoModelForCausalLM.calls[0][1][safety_key] is False


def test_from_peft_checkpoint_loads_base_then_adapter_with_safe_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_dir, _, model, runtime, config_loader, model_loader = _peft_runtime(tmp_path, monkeypatch)
    config = GenerationConfig(
        do_sample=False,
        temperature=None,
        top_p=None,
        max_new_tokens=8,
        dtype="float16",
    )

    generator = TransformersCompletionGenerator.from_peft_checkpoint(
        base_model_id="example/model",
        base_model_revision="revision-1",
        adapter_dir=adapter_dir,
        device="cpu",
        config=config,
        local_files_only=True,
    )

    assert isinstance(generator, TransformersCompletionGenerator)
    assert runtime.AutoTokenizer.calls == [
        (
            "example/model",
            {"revision": "revision-1", "trust_remote_code": False, "local_files_only": True},
        )
    ]
    assert runtime.AutoModelForCausalLM.calls == [
        (
            "example/model",
            {
                "revision": "revision-1",
                "trust_remote_code": False,
                "torch_dtype": "fake-float16",
                "local_files_only": True,
            },
        )
    ]
    assert config_loader.calls == [(str(adapter_dir.resolve()), {"local_files_only": True})]
    assert model_loader.calls[0][0] is model
    assert model_loader.calls[0][1] == str(adapter_dir.resolve())
    assert model_loader.calls[0][2]["is_trainable"] is False
    assert model_loader.calls[0][2]["local_files_only"] is True
    assert model.eval_called is True
    assert model.to_device == "cpu"


def test_from_peft_checkpoint_accepts_run_revision_when_adapter_revision_is_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_dir, _, _, runtime, _, model_loader = _peft_runtime(
        tmp_path,
        monkeypatch,
        adapter_revision=None,
    )

    TransformersCompletionGenerator.from_peft_checkpoint(
        base_model_id="example/model",
        base_model_revision="revision-1",
        adapter_dir=adapter_dir,
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
    )

    assert runtime.AutoTokenizer.calls[0][1]["revision"] == "revision-1"
    assert runtime.AutoModelForCausalLM.calls[0][1]["revision"] == "revision-1"
    assert model_loader.calls


def test_from_peft_checkpoint_rejects_base_model_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_dir, _, _, runtime, _, model_loader = _peft_runtime(
        tmp_path,
        monkeypatch,
        adapter_model_id="different/model",
    )

    with pytest.raises(GenerationError, match="base model identity"):
        TransformersCompletionGenerator.from_peft_checkpoint(
            base_model_id="example/model",
            base_model_revision="revision-1",
            adapter_dir=adapter_dir,
            device="cpu",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        )

    assert runtime.AutoTokenizer.calls == []
    assert runtime.AutoModelForCausalLM.calls == []
    assert model_loader.calls == []


def test_from_peft_checkpoint_rejects_base_model_revision_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_dir, _, _, _, _, _ = _peft_runtime(
        tmp_path,
        monkeypatch,
        adapter_revision="different-revision",
    )

    with pytest.raises(GenerationError, match="base model revision"):
        TransformersCompletionGenerator.from_peft_checkpoint(
            base_model_id="example/model",
            base_model_revision="revision-1",
            adapter_dir=adapter_dir,
            device="cpu",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        )


def test_from_peft_checkpoint_wraps_runtime_failure_without_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_dir, _, _, _, _, _ = _peft_runtime(
        tmp_path,
        monkeypatch,
        failure=RuntimeError("PRIVATE_PAYLOAD_SENTINEL"),
    )

    with pytest.raises(GenerationError) as error:
        TransformersCompletionGenerator.from_peft_checkpoint(
            base_model_id="example/model",
            base_model_revision="revision-1",
            adapter_dir=adapter_dir,
            device="cpu",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        )

    assert str(error.value) == "could not load PEFT adapter for inference: RuntimeError"
    assert "PRIVATE_PAYLOAD_SENTINEL" not in str(error.value)


def test_from_grpo_checkpoint_loads_a_merges_b_then_loads_cd_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir, grpo_dir, merged, final, runtime, _, _, calls = _stacked_peft_runtime(tmp_path, monkeypatch)

    generator = TransformersCompletionGenerator.from_grpo_checkpoint(
        base_model_id="example/model",
        base_model_revision="revision-1",
        parent_sft_adapter_dir=parent_dir,
        grpo_adapter_dir=grpo_dir,
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
    )

    assert isinstance(generator, TransformersCompletionGenerator)
    assert runtime.AutoModelForCausalLM.calls[0][0] == "example/model"
    assert calls[0][0:2] == ("attach", parent_dir)
    assert calls[0][3]["is_trainable"] is False
    assert calls[1] == ("merge_b", True)
    assert calls[2][0:3] == ("attach", grpo_dir, merged)
    assert calls[2][3]["is_trainable"] is False
    assert final.eval_called is True


def test_from_grpo_checkpoint_requires_safe_merge_before_cd_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir, grpo_dir, _, _, _, _, _, calls = _stacked_peft_runtime(
        tmp_path,
        monkeypatch,
        merge_available=False,
    )

    with pytest.raises(GenerationError, match="safe merge"):
        TransformersCompletionGenerator.from_grpo_checkpoint(
            base_model_id="example/model",
            base_model_revision="revision-1",
            parent_sft_adapter_dir=parent_dir,
            grpo_adapter_dir=grpo_dir,
            device="cpu",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        )

    assert [call for call in calls if isinstance(call, tuple) and call[0] == "attach"] == [calls[0]]


@pytest.mark.parametrize("role", ["parent", "grpo"])
def test_from_grpo_checkpoint_rejects_parent_or_grpo_adapter_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    parent_dir, grpo_dir, _, _, runtime, _, _, _ = _stacked_peft_runtime(
        tmp_path,
        monkeypatch,
        parent_model_id="other/model" if role == "parent" else "example/model",
        grpo_model_id="other/model" if role == "grpo" else "example/model",
    )

    with pytest.raises(GenerationError, match="base model identity"):
        TransformersCompletionGenerator.from_grpo_checkpoint(
            base_model_id="example/model",
            base_model_revision="revision-1",
            parent_sft_adapter_dir=parent_dir,
            grpo_adapter_dir=grpo_dir,
            device="cpu",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        )

    assert runtime.AutoModelForCausalLM.calls == []


def test_from_grpo_checkpoint_accepts_none_adapter_revision_under_pinned_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir, grpo_dir, _, final, _, _, _, _ = _stacked_peft_runtime(
        tmp_path,
        monkeypatch,
        parent_revision=None,
        grpo_revision=None,
    )

    TransformersCompletionGenerator.from_grpo_checkpoint(
        base_model_id="example/model",
        base_model_revision="revision-1",
        parent_sft_adapter_dir=parent_dir,
        grpo_adapter_dir=grpo_dir,
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
    )

    assert final.eval_called is True


def test_from_grpo_checkpoint_preserves_dtype_device_local_only_and_eval_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir, grpo_dir, _, final, runtime, config_loader, _, calls = _stacked_peft_runtime(
        tmp_path,
        monkeypatch,
    )

    TransformersCompletionGenerator.from_grpo_checkpoint(
        base_model_id="example/model",
        base_model_revision="revision-1",
        parent_sft_adapter_dir=parent_dir,
        grpo_adapter_dir=grpo_dir,
        device="cuda",
        config=GenerationConfig(
            do_sample=False,
            temperature=None,
            top_p=None,
            max_new_tokens=8,
            dtype="float16",
        ),
        local_files_only=True,
    )

    assert runtime.AutoModelForCausalLM.calls[0][1]["torch_dtype"] == "fake-float16"
    assert runtime.AutoModelForCausalLM.calls[0][1]["local_files_only"] is True
    assert all(options["local_files_only"] is True for _, options in config_loader.calls)
    assert all(call[3]["local_files_only"] is True for call in calls if call[0] == "attach")
    assert final.to_device == "cuda"
    assert final.eval_called is True


def test_from_grpo_checkpoint_wraps_runtime_failure_without_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir, grpo_dir, _, _, _, _, _, _ = _stacked_peft_runtime(
        tmp_path,
        monkeypatch,
        grpo_failure=RuntimeError("PRIVATE_GRPO_PAYLOAD_SENTINEL"),
    )

    with pytest.raises(GenerationError) as error:
        TransformersCompletionGenerator.from_grpo_checkpoint(
            base_model_id="example/model",
            base_model_revision="revision-1",
            parent_sft_adapter_dir=parent_dir,
            grpo_adapter_dir=grpo_dir,
            device="cpu",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        )

    assert str(error.value) == "could not load GRPO adapter for inference: RuntimeError"
    assert "PRIVATE_GRPO_PAYLOAD_SENTINEL" not in str(error.value)


def test_transformers_generator_uses_user_chat_template() -> None:
    generator, tokenizer, _, runtime = _backend()
    result = generator.generate("PROMPT_SENTINEL", seed=7)

    assert tokenizer.messages == [{"role": "user", "content": "PROMPT_SENTINEL"}]
    assert runtime.seeds == [7]
    assert result.completion.startswith("```python")


def test_transformers_generator_calls_eval_and_inference_path(monkeypatch: pytest.MonkeyPatch) -> None:
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), runtime))

    generator = TransformersCompletionGenerator.from_pretrained(
        "example/model",
        model_revision=None,
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=512),
    )
    generator.generate("prompt", seed=42)

    assert model.eval_called is True
    assert model.generate_kwargs is not None
    assert model.generate_kwargs["do_sample"] is False
    token_key = "max_new_" + "tokens"
    assert model.generate_kwargs[token_key] == 512
    assert "temperature" not in model.generate_kwargs
    assert "top_p" not in model.generate_kwargs


def test_generation_config_rejects_unsupported_dtype() -> None:
    """Only the supported dtype names may be configured."""

    with pytest.raises(GenerationError, match="dtype"):
        GenerationConfig(
            do_sample=False,
            temperature=None,
            top_p=None,
            max_new_tokens=8,
            dtype="float64",
        )


@pytest.mark.parametrize(
    ("dtype", "torch_dtype_name"),
    [("float16", "fake-float16"), ("bfloat16", "fake-bfloat16"), ("float32", "fake-float32")],
)
def test_transformers_generator_passes_configured_dtype_to_model_loader(
    monkeypatch: pytest.MonkeyPatch,
    dtype: str,
    torch_dtype_name: str,
) -> None:
    """The configured dtype must reach the model loader and be exposed publicly."""
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), runtime))

    generator = TransformersCompletionGenerator.from_pretrained(
        "example/model",
        model_revision=None,
        device="cpu",
        config=GenerationConfig(
            do_sample=False,
            temperature=None,
            top_p=None,
            max_new_tokens=8,
            dtype=dtype,
        ),
    )

    assert runtime.AutoModelForCausalLM.calls[0][1]["torch_dtype"] == torch_dtype_name
    model.dtype = getattr(_FakeTorch, dtype)
    assert generator.model_dtype == dtype


def test_transformers_generator_default_dtype_does_not_override_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dtype=auto must not pass torch_dtype, preserving the legacy loader behavior."""
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), runtime))

    TransformersCompletionGenerator.from_pretrained(
        "example/model",
        model_revision=None,
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
    )

    assert "torch_dtype" not in runtime.AutoModelForCausalLM.calls[0][1]


def test_transformers_generator_local_files_only_reaches_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """local_files_only must be forwarded only when the offline smoke requests it."""
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), runtime))

    TransformersCompletionGenerator.from_pretrained(
        "example/model",
        model_revision=None,
        device="cpu",
        config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
        local_files_only=True,
    )

    assert runtime.AutoTokenizer.calls[0][1]["local_files_only"] is True
    assert runtime.AutoModelForCausalLM.calls[0][1]["local_files_only"] is True


def test_local_files_only_loader_failure_reports_cache_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loader failure under local_files_only must report the missing local cache."""
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), runtime))
    seen_kwargs: dict[str, object] = {}

    def failing_model_loader(model_id: str, **kwargs: object) -> object:
        seen_kwargs.update(kwargs)
        raise RuntimeError("fake load failure")

    monkeypatch.setattr(runtime.AutoModelForCausalLM, "from_pretrained", failing_model_loader)

    with pytest.raises(GenerationError, match="local cache"):
        TransformersCompletionGenerator.from_pretrained(
            "example/model",
            model_revision=None,
            device="cpu",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
            local_files_only=True,
        )
    assert seen_kwargs["local_files_only"] is True


def test_local_files_only_device_failure_does_not_report_cache_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model.to() CUDA failure under local_files_only must not be misreported as cache missing."""
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    runtime = _FakeTransformers(tokenizer, model)
    monkeypatch.setattr(generation_module, "_load_transformers_runtime", lambda: (_FakeTorch(), runtime))

    def failing_to(device: str) -> _FakeModel:
        raise RuntimeError("fake cuda failure")

    monkeypatch.setattr(model, "to", failing_to)

    with pytest.raises(GenerationError) as error:
        TransformersCompletionGenerator.from_pretrained(
            "example/model",
            model_revision=None,
            device="cuda",
            config=GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8),
            local_files_only=True,
        )
    message = str(error.value)
    assert "could not initialize configured model runtime: RuntimeError" in message
    assert "local cache" not in message
    assert "download and cache" not in message


def test_transformers_generator_decodes_only_new_tokens() -> None:
    generator, tokenizer, _, _ = _backend()
    result = generator.generate("prompt", seed=42)

    assert tokenizer.decoded_ids == [9, 10]
    assert result.completion_tokens == 2


def test_transformers_generator_reports_completion_token_count_and_latency() -> None:
    generator, _, _, _ = _backend()
    result = generator.generate("prompt", seed=42)
    assert result.completion_tokens == 2
    assert math.isfinite(result.latency_ms)
    assert result.latency_ms >= 0.0


def test_transformers_generator_rejects_missing_chat_template() -> None:
    generator, tokenizer, model, _ = _backend()
    tokenizer.chat_template = ""
    with pytest.raises(GenerationError, match="chat template"):
        generator.generate("prompt", seed=42)
    assert model.generate_kwargs is None


def test_transformers_generator_missing_dependencies_mentions_install_full(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import_module(name: str) -> object:
        if name == "torch":
            raise ImportError("missing")
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    with pytest.raises(GenerationError, match="make install-full"):
        generation_module._load_transformers_runtime()
