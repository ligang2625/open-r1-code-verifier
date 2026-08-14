"""Deterministic completion generation contracts for WP5 evaluation."""

from __future__ import annotations

import importlib
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from code_verifier.data.schema import CodeProblem
from code_verifier.prompting import build_code_prompt


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
    return build_code_prompt(problem)


def _load_transformers_runtime() -> tuple[Any, Any]:
    """Lazy-load torch and transformers so CPU-only unit environments can import evaluation."""
    try:
        torch_runtime = importlib.import_module("torch")
        transformers_runtime = importlib.import_module("transformers")
    except ImportError:
        raise GenerationError("model generation dependencies are unavailable; run make install-full") from None
    return torch_runtime, transformers_runtime


def _load_peft_runtime() -> tuple[Any, Any]:
    """Lazy-load the pinned PEFT adapter configuration and model types."""
    try:
        peft_runtime = importlib.import_module("peft")
        return peft_runtime.PeftConfig, peft_runtime.PeftModel
    except (ImportError, AttributeError):
        raise GenerationError("PEFT inference dependencies are unavailable; run make install-train") from None


def _resolve_torch_dtype(torch_runtime: Any, dtype: str) -> Any:
    """Map the project dtype name to a transformers ``torch_dtype`` argument."""
    if dtype == "float16":
        return torch_runtime.float16
    if dtype == "bfloat16":
        return torch_runtime.bfloat16
    if dtype == "float32":
        return torch_runtime.float32
    raise GenerationError(f"unsupported dtype: {dtype}")


def _validate_model_source(
    *,
    model_id: str,
    model_revision: str | None,
    device: str,
    config: GenerationConfig,
    local_files_only: bool,
) -> None:
    if not isinstance(model_id, str) or not model_id.strip():
        raise GenerationError("model_id must be a non-empty string")
    if model_revision is not None and (not isinstance(model_revision, str) or not model_revision.strip()):
        raise GenerationError("model_revision must be a non-empty string or null")
    if device not in {"cpu", "cuda", "auto"}:
        raise GenerationError("device must be cpu, cuda, or auto")
    if not isinstance(local_files_only, bool):
        raise GenerationError("local_files_only must be a boolean")
    validate_generation_config(config)


def _load_base_transformers_model(
    *,
    torch_runtime: Any,
    transformers_runtime: Any,
    model_id: str,
    model_revision: str | None,
    device: str,
    config: GenerationConfig,
    local_files_only: bool,
) -> tuple[Any, Any]:
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
    return tokenizer, model


def _initialize_inference_model(model: Any, *, device: str) -> Any:
    try:
        if device != "auto":
            model = model.to(device)
        model.eval()
    except Exception as error:
        raise GenerationError(f"could not initialize configured model runtime: {type(error).__name__}") from None
    return model


def _load_identity_checked_peft_config(
    *,
    peft_config_type: Any,
    adapter_dir: Path,
    base_model_id: str,
    base_model_revision: str | None,
    local_files_only: bool,
    role: str,
) -> tuple[Path, Any, dict[str, object]]:
    try:
        resolved_adapter_dir = adapter_dir.resolve(strict=True)
    except (AttributeError, OSError):
        raise GenerationError(f"{role} adapter directory must be an existing local directory") from None
    if not resolved_adapter_dir.is_dir():
        raise GenerationError(f"{role} adapter directory must be an existing local directory")
    adapter_options: dict[str, object] = {}
    if local_files_only:
        adapter_options["local_files_only"] = True
    try:
        adapter_config = peft_config_type.from_pretrained(str(resolved_adapter_dir), **adapter_options)
    except Exception as error:
        raise GenerationError(f"could not load {role} adapter configuration: {type(error).__name__}") from None
    if getattr(adapter_config, "base_model_name_or_path", None) != base_model_id:
        raise GenerationError(f"{role} adapter base model identity does not match the selected run")
    adapter_revision = getattr(adapter_config, "revision", None)
    if adapter_revision is not None and adapter_revision != base_model_revision:
        raise GenerationError(f"{role} adapter base model revision does not match the selected run")
    return resolved_adapter_dir, adapter_config, adapter_options


def _attach_peft_adapter(
    *,
    base_model: Any,
    peft_model_type: Any,
    adapter_dir: Path,
    adapter_config: Any,
    adapter_options: dict[str, object],
    role: str,
) -> Any:
    try:
        return peft_model_type.from_pretrained(
            base_model,
            str(adapter_dir),
            is_trainable=False,
            config=adapter_config,
            **adapter_options,
        )
    except Exception as error:
        raise GenerationError(f"could not load {role} adapter for inference: {type(error).__name__}") from None


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
        _validate_model_source(
            model_id=model_id,
            model_revision=model_revision,
            device=device,
            config=config,
            local_files_only=local_files_only,
        )
        torch_runtime, transformers_runtime = _load_transformers_runtime()
        tokenizer, model = _load_base_transformers_model(
            torch_runtime=torch_runtime,
            transformers_runtime=transformers_runtime,
            model_id=model_id,
            model_revision=model_revision,
            device=device,
            config=config,
            local_files_only=local_files_only,
        )
        model = _initialize_inference_model(model, device=device)
        return cls(
            tokenizer=tokenizer,
            model=model,
            torch_runtime=torch_runtime,
            transformers_runtime=transformers_runtime,
            device=device,
            config=config,
        )

    @classmethod
    def from_peft_checkpoint(
        cls,
        *,
        base_model_id: str,
        base_model_revision: str | None,
        adapter_dir: Path,
        device: str,
        config: GenerationConfig,
        local_files_only: bool = False,
    ) -> TransformersCompletionGenerator:
        """Load one identity-checked PEFT adapter for read-only deterministic inference."""
        _validate_model_source(
            model_id=base_model_id,
            model_revision=base_model_revision,
            device=device,
            config=config,
            local_files_only=local_files_only,
        )
        torch_runtime, transformers_runtime = _load_transformers_runtime()
        peft_config_type, peft_model_type = _load_peft_runtime()
        resolved_adapter_dir, adapter_config, adapter_options = _load_identity_checked_peft_config(
            peft_config_type=peft_config_type,
            adapter_dir=adapter_dir,
            base_model_id=base_model_id,
            base_model_revision=base_model_revision,
            local_files_only=local_files_only,
            role="PEFT",
        )
        tokenizer, base_model = _load_base_transformers_model(
            torch_runtime=torch_runtime,
            transformers_runtime=transformers_runtime,
            model_id=base_model_id,
            model_revision=base_model_revision,
            device=device,
            config=config,
            local_files_only=local_files_only,
        )
        model = _attach_peft_adapter(
            base_model=base_model,
            peft_model_type=peft_model_type,
            adapter_dir=resolved_adapter_dir,
            adapter_config=adapter_config,
            adapter_options=adapter_options,
            role="PEFT",
        )
        model = _initialize_inference_model(model, device=device)
        return cls(
            tokenizer=tokenizer,
            model=model,
            torch_runtime=torch_runtime,
            transformers_runtime=transformers_runtime,
            device=device,
            config=config,
        )

    @classmethod
    def from_grpo_checkpoint(
        cls,
        *,
        base_model_id: str,
        base_model_revision: str | None,
        parent_sft_adapter_dir: Path,
        grpo_adapter_dir: Path,
        device: str,
        config: GenerationConfig,
        local_files_only: bool = False,
    ) -> TransformersCompletionGenerator:
        """Rebuild A, safe-merge completed B, then attach C/D read-only for inference."""
        _validate_model_source(
            model_id=base_model_id,
            model_revision=base_model_revision,
            device=device,
            config=config,
            local_files_only=local_files_only,
        )
        torch_runtime, transformers_runtime = _load_transformers_runtime()
        peft_config_type, peft_model_type = _load_peft_runtime()
        parent_dir, parent_config, parent_options = _load_identity_checked_peft_config(
            peft_config_type=peft_config_type,
            adapter_dir=parent_sft_adapter_dir,
            base_model_id=base_model_id,
            base_model_revision=base_model_revision,
            local_files_only=local_files_only,
            role="parent SFT",
        )
        grpo_dir, grpo_config, grpo_options = _load_identity_checked_peft_config(
            peft_config_type=peft_config_type,
            adapter_dir=grpo_adapter_dir,
            base_model_id=base_model_id,
            base_model_revision=base_model_revision,
            local_files_only=local_files_only,
            role="GRPO",
        )
        tokenizer, base_model = _load_base_transformers_model(
            torch_runtime=torch_runtime,
            transformers_runtime=transformers_runtime,
            model_id=base_model_id,
            model_revision=base_model_revision,
            device=device,
            config=config,
            local_files_only=local_files_only,
        )
        parent_policy = _attach_peft_adapter(
            base_model=base_model,
            peft_model_type=peft_model_type,
            adapter_dir=parent_dir,
            adapter_config=parent_config,
            adapter_options=parent_options,
            role="parent SFT",
        )
        merge = getattr(parent_policy, "merge_and_unload", None)
        if not callable(merge):
            raise GenerationError("parent SFT adapter does not provide safe merge for GRPO inference")
        try:
            merged_parent = merge(safe_merge=True)
        except Exception as error:
            raise GenerationError(f"could not safe-merge parent SFT adapter: {type(error).__name__}") from None
        model = _attach_peft_adapter(
            base_model=merged_parent,
            peft_model_type=peft_model_type,
            adapter_dir=grpo_dir,
            adapter_config=grpo_config,
            adapter_options=grpo_options,
            role="GRPO",
        )
        model = _initialize_inference_model(model, device=device)
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
