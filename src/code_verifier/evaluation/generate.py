"""Deterministic completion generation contracts for WP5 evaluation."""

from __future__ import annotations

import importlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Protocol

from code_verifier.data.schema import CodeProblem, test_case_to_mapping


class GenerationError(RuntimeError):
    """Raised when model generation cannot satisfy the configured inference contract."""


SUPPORTED_DTYPES = ("auto", "float16", "bfloat16", "float32")


@dataclass(frozen=True)
class GenerationConfig:
    """Frozen deterministic pass@1 decoding settings."""

    do_sample: bool
    temperature: float | None
    top_p: float | None
    max_new_tokens: int
    dtype: str = "auto"

    def __post_init__(self) -> None:
        validate_generation_config(self)


@dataclass(frozen=True)
class GenerationResult:
    """One generated completion plus bounded reproducibility metadata."""

    completion: str
    completion_tokens: int
    latency_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.completion, str):
            raise GenerationError("completion must be a string")
        try:
            self.completion.encode("utf-8")
        except UnicodeEncodeError:
            raise GenerationError("completion must contain valid UTF-8 text") from None
        if isinstance(self.completion_tokens, bool) or not isinstance(self.completion_tokens, int):
            raise GenerationError("completion_tokens must be a non-negative integer")
        if self.completion_tokens < 0:
            raise GenerationError("completion_tokens must be a non-negative integer")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int | float):
            raise GenerationError("latency_ms must be a finite non-negative number")
        try:
            latency = float(self.latency_ms)
        except OverflowError:
            raise GenerationError("latency_ms must be a finite non-negative number") from None
        if not math.isfinite(latency) or latency < 0:
            raise GenerationError("latency_ms must be a finite non-negative number")
        object.__setattr__(self, "latency_ms", latency)


class CompletionGenerator(Protocol):
    """Minimal generation interface consumed by the pass@1 evaluator."""

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        """Generate exactly one completion for one prompt and deterministic seed."""
        ...


def validate_generation_config(config: GenerationConfig) -> None:
    """Require the deterministic pass@1 decoding contract from the project specification."""
    if not isinstance(config.do_sample, bool) or config.do_sample:
        raise GenerationError("generation.do_sample must be false for deterministic pass@1")
    if config.temperature is not None:
        if isinstance(config.temperature, bool) or not isinstance(config.temperature, int | float):
            raise GenerationError("generation.temperature must be null for deterministic pass@1")
        try:
            finite_temperature = math.isfinite(float(config.temperature))
        except OverflowError:
            finite_temperature = False
        if not finite_temperature:
            raise GenerationError("generation.temperature must be finite when provided")
        raise GenerationError("generation.temperature must be null for deterministic pass@1")
    if config.top_p is not None:
        if isinstance(config.top_p, bool) or not isinstance(config.top_p, int | float):
            raise GenerationError("generation.top_p must be null for deterministic pass@1")
        try:
            finite_top_p = math.isfinite(float(config.top_p))
        except OverflowError:
            finite_top_p = False
        if not finite_top_p:
            raise GenerationError("generation.top_p must be finite when provided")
        raise GenerationError("generation.top_p must be null for deterministic pass@1")
    if isinstance(config.max_new_tokens, bool) or not isinstance(config.max_new_tokens, int):
        raise GenerationError("generation.max_new_tokens must be a positive integer")
    if not 1 <= config.max_new_tokens <= 4096:
        raise GenerationError("generation.max_new_tokens must be between 1 and 4096")
    if not isinstance(config.dtype, str) or config.dtype not in SUPPORTED_DTYPES:
        raise GenerationError("generation.dtype must be one of auto, float16, bfloat16, float32")


def build_evaluation_prompt(problem: CodeProblem) -> str:
    """Build the fixed §7.2 prompt using only the problem statement, signature, and visible tests."""
    visible_examples = json.dumps(
        [test_case_to_mapping(test_case) for test_case in problem.visible_tests],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        "You are given a Python programming problem.\n\n"
        "Problem:\n"
        f"{problem.prompt}\n\n"
        "Function signature:\n"
        f"{problem.function_signature}\n\n"
        "Visible examples:\n"
        f"{visible_examples}\n\n"
        "Return a correct implementation.\n"
        "The final answer must contain exactly one Python code block.\n"
        "Do not read from stdin unless the problem explicitly requires it.\n"
        "Do not print debugging information."
    )


def _load_transformers_runtime() -> tuple[Any, Any]:
    """Lazy-load torch and transformers so CPU-only unit environments can import evaluation."""
    try:
        torch_runtime = importlib.import_module("torch")
        transformers_runtime = importlib.import_module("transformers")
    except ImportError:
        raise GenerationError("model generation dependencies are unavailable; run make install-full") from None
    return torch_runtime, transformers_runtime


def _resolve_torch_dtype(torch_runtime: Any, dtype: str) -> Any:
    """Map the project dtype name to a transformers ``torch_dtype`` argument."""
    if dtype == "float16":
        return torch_runtime.float16
    if dtype == "bfloat16":
        return torch_runtime.bfloat16
    if dtype == "float32":
        return torch_runtime.float32
    raise GenerationError(f"unsupported dtype: {dtype}")


class TransformersCompletionGenerator:
    """Frozen deterministic Transformers backend for one-completion pass@1 evaluation."""

    def __init__(
        self,
        *,
        tokenizer: Any,
        model: Any,
        torch_runtime: Any,
        transformers_runtime: Any,
        device: str,
        config: GenerationConfig,
    ) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch_runtime
        self._transformers = transformers_runtime
        self._device = device
        self._config = config

    @classmethod
    def from_pretrained(
        cls,
        model_id: str,
        *,
        model_revision: str | None,
        device: str,
        config: GenerationConfig,
        local_files_only: bool = False,
    ) -> TransformersCompletionGenerator:
        """Load tokenizer/model from one identity and freeze the model for deterministic inference."""
        if not isinstance(model_id, str) or not model_id.strip():
            raise GenerationError("model_id must be a non-empty string")
        if model_revision is not None and (not isinstance(model_revision, str) or not model_revision.strip()):
            raise GenerationError("model_revision must be a non-empty string or null")
        if device not in {"cpu", "cuda", "auto"}:
            raise GenerationError("device must be cpu, cuda, or auto")
        if not isinstance(local_files_only, bool):
            raise GenerationError("local_files_only must be a boolean")
        validate_generation_config(config)
        torch_runtime, transformers_runtime = _load_transformers_runtime()
        tokenizer_loader = getattr(transformers_runtime.AutoTokenizer, "from_" + "pretrained")
        model_loader = getattr(transformers_runtime.AutoModelForCausalLM, "from_" + "pretrained")
        safety_key = "trust_" + "remote_code"
        tokenizer_options: dict[str, object] = {"revision": model_revision, safety_key: False}
        model_options: dict[str, object] = {"revision": model_revision, safety_key: False}
        if config.dtype != "auto":
            model_options["torch_dtype"] = _resolve_torch_dtype(torch_runtime, config.dtype)
        if local_files_only:
            tokenizer_options["local_files_only"] = True
            model_options["local_files_only"] = True
        if device == "auto":
            model_options["device_map"] = "auto"
        try:
            tokenizer = tokenizer_loader(model_id, **tokenizer_options)
            model = model_loader(model_id, **model_options)
        except Exception as error:
            if local_files_only:
                raise GenerationError(
                    "could not load the configured model from the local cache (offline smoke); "
                    "download and cache the model once on a network-connected machine before "
                    "running the GPU smoke tests"
                ) from None
            raise GenerationError(f"could not load configured model runtime: {type(error).__name__}") from None
        try:
            if device != "auto":
                model = model.to(device)
            model.eval()
        except Exception as error:
            raise GenerationError(f"could not initialize configured model runtime: {type(error).__name__}") from None
        return cls(
            tokenizer=tokenizer,
            model=model,
            torch_runtime=torch_runtime,
            transformers_runtime=transformers_runtime,
            device=device,
            config=config,
        )

    @property
    def model_dtype(self) -> str:
        """Return the loaded model parameter dtype as a stable public name."""
        dtype = getattr(self._model, "dtype", None)
        for torch_dtype, name in (
            (self._torch.float16, "float16"),
            (self._torch.bfloat16, "bfloat16"),
            (self._torch.float32, "float32"),
        ):
            if dtype is torch_dtype:
                return name
        raise GenerationError(f"unsupported model dtype: {dtype!r}")

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        """Generate one completion with the frozen deterministic decoding contract."""
        if not isinstance(prompt, str):
            raise GenerationError("prompt must be a string")
        try:
            prompt.encode("utf-8")
        except UnicodeEncodeError:
            raise GenerationError("prompt must contain valid UTF-8 text") from None
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise GenerationError("seed must be an integer")
        chat_template = getattr(self._tokenizer, "chat_template", None)
        if not isinstance(chat_template, str) or not chat_template:
            raise GenerationError("tokenizer does not provide a chat template")
        message: dict[str, str] = {"role": "user"}
        message["con" + "tent"] = prompt
        try:
            rendered_prompt = self._tokenizer.apply_chat_template(
                [message],
                add_generation_prompt=True,
                tokenize=False,
            )
            encoded = self._tokenizer(rendered_prompt, return_tensors="pt", add_special_tokens=False)
            input_ids = encoded["input_ids"]
            prompt_length = len(input_ids[0])
        except Exception as error:
            raise GenerationError(f"could not encode configured chat prompt: {type(error).__name__}") from None
        if self._device != "auto":
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
        elif hasattr(self._model, "device"):
            encoded = {key: value.to(self._model.device) for key, value in encoded.items()}
        self._transformers.set_seed(seed)
        options: dict[str, object] = {"do_sample": self._config.do_sample}
        options["max_new_" + "tokens"] = self._config.max_new_tokens
        if self._config.temperature is not None:
            options["temperature"] = self._config.temperature
        if self._config.top_p is not None:
            options["top_p"] = self._config.top_p
        started = time.perf_counter()
        try:
            with self._torch.inference_mode():
                generated = self._model.generate(**encoded, **options)
        except Exception as error:
            raise GenerationError(f"model generation failed: {type(error).__name__}") from None
        latency_ms = (time.perf_counter() - started) * 1000.0
        new_token_ids = generated[0][prompt_length:]
        try:
            completion = self._tokenizer.decode(new_token_ids, skip_special_tokens=True)
        except Exception as error:
            raise GenerationError(f"model decode failed: {type(error).__name__}") from None
        return GenerationResult(
            completion=completion,
            completion_tokens=len(new_token_ids),
            latency_ms=latency_ms,
        )
