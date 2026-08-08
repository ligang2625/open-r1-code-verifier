"""Tests for deterministic evaluation prompt and generation contracts."""

from __future__ import annotations

import importlib
import math
from contextlib import nullcontext
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
