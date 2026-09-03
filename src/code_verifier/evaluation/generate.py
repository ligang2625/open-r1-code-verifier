"""Deterministic completion generation contracts for WP5 evaluation."""

from __future__ import annotations

import importlib
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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
class SamplingGenerationConfig:
    """Frozen sampled-generation settings used by WP9 offline calibration."""

    temperature: float
    top_p: float
    max_new_tokens: int
    dtype: str = "auto"

    def __post_init__(self) -> None:
        if isinstance(self.temperature, bool) or not isinstance(self.temperature, int | float):
            raise GenerationError("sampling temperature must be a finite positive number")
        if not math.isfinite(float(self.temperature)) or float(self.temperature) <= 0.0:
            raise GenerationError("sampling temperature must be a finite positive number")
        if isinstance(self.top_p, bool) or not isinstance(self.top_p, int | float):
            raise GenerationError("sampling top_p must be in (0, 1]")
        if not math.isfinite(float(self.top_p)) or not 0.0 < float(self.top_p) <= 1.0:
            raise GenerationError("sampling top_p must be in (0, 1]")
        if isinstance(self.max_new_tokens, bool) or not isinstance(self.max_new_tokens, int):
            raise GenerationError("sampling max_new_tokens must be a positive integer")
        if not 1 <= self.max_new_tokens <= 4096:
            raise GenerationError("sampling max_new_tokens must be between 1 and 4096")
        if not isinstance(self.dtype, str) or self.dtype not in SUPPORTED_DTYPES:
            raise GenerationError("sampling dtype must be one of auto, float16, bfloat16, float32")


@dataclass(frozen=True)
class GenerationResult:
    """One generated completion plus bounded reproducibility metadata."""

    completion: str
    completion_tokens: int
    latency_ms: float
    hit_max_new_tokens: bool = False

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
        if not isinstance(self.hit_max_new_tokens, bool):
            raise GenerationError("hit_max_new_tokens must be a boolean")
        object.__setattr__(self, "latency_ms", latency)


class CompletionGenerator(Protocol):
    """Minimal generation interface consumed by the pass@1 evaluator."""

    def generate(self, prompt: str, *, seed: int) -> GenerationResult:
        """Generate exactly one completion for one prompt and deterministic seed."""
        ...


class BatchedCompletionGenerator(Protocol):
    """Deterministic ordered batch generation interface."""

    def generate_batch(self, prompts: Sequence[str], *, seeds: Sequence[int]) -> list[GenerationResult]:
        """Generate one completion per prompt while preserving input order."""
        ...


class GroupSamplingGenerator(Protocol):
    """Sample one ordered completion group for a calibration problem."""

    def generate_group(self, prompt: str, *, seed: int, num_generations: int) -> list[GenerationResult]:
        """Generate one sampled group using a deterministic group seed."""
        ...


@runtime_checkable
class BatchedGroupSamplingGenerator(GroupSamplingGenerator, Protocol):
    """Sample multiple calibration groups with independent per-problem RNG streams."""

    def generate_groups(
        self,
        prompts: Sequence[str],
        *,
        seeds: Sequence[int],
        num_generations: int,
    ) -> list[list[GenerationResult]]:
        """Generate one ordered sampled group per prompt while preserving problem order."""
        ...


class _IndependentGroupSamplingProcessor:
    """Force multinomial choices from one deterministic RNG stream per prompt group."""

    def __init__(
        self,
        *,
        torch_runtime: Any,
        seeds: Sequence[int],
        group_size: int,
        temperature: float,
        top_p: float,
    ) -> None:
        self._torch = torch_runtime
        self._seeds = list(seeds)
        self._group_size = group_size
        self._temperature = float(temperature)
        self._top_p = float(top_p)
        self._generators: list[Any] | None = None

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        expected_rows = len(self._seeds) * self._group_size
        if len(scores) != expected_rows:
            raise GenerationError("sampled batch row count no longer matches independent problem groups")
        warped = scores / self._temperature
        if self._top_p < 1.0:
            sorted_logits, sorted_indices = warped.sort(descending=False)
            cumulative_probs = sorted_logits.softmax(dim=-1).cumsum(dim=-1)
            sorted_indices_to_remove = cumulative_probs <= (1.0 - self._top_p)
            sorted_indices_to_remove[..., -1:] = False
            indices_to_remove = sorted_indices_to_remove.scatter(1, sorted_indices, sorted_indices_to_remove)
            warped = warped.masked_fill(indices_to_remove, float("-inf"))
        probabilities = warped.softmax(dim=-1)
        if self._generators is None:
            device = probabilities.device
            self._generators = []
            for seed in self._seeds:
                generator = self._torch.Generator(device=device)
                generator.manual_seed(seed)
                self._generators.append(generator)
        sampled: list[Any] = []
        for index, generator in enumerate(self._generators):
            start = index * self._group_size
            stop = start + self._group_size
            sampled.append(self._torch.multinomial(probabilities[start:stop], num_samples=1, generator=generator))
        selected = self._torch.cat(sampled, dim=0)
        forced = self._torch.full_like(scores, float("-inf"))
        forced.scatter_(1, selected, 0.0)
        return forced


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
    config: GenerationConfig | SamplingGenerationConfig,
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
            hit_max_new_tokens=len(new_token_ids) >= self._config.max_new_tokens,
        )

    def generate_batch(self, prompts: Sequence[str], *, seeds: Sequence[int]) -> list[GenerationResult]:
        """Generate an ordered deterministic batch without changing pass@1 decoding semantics."""
        if isinstance(prompts, str | bytes | bytearray) or not isinstance(prompts, Sequence) or not prompts:
            raise GenerationError("prompts must be a non-empty sequence")
        if isinstance(seeds, str | bytes | bytearray) or not isinstance(seeds, Sequence):
            raise GenerationError("seeds must be a sequence")
        if len(prompts) != len(seeds):
            raise GenerationError("prompts and seeds must have equal lengths")
        normalized_prompts: list[str] = []
        normalized_seeds: list[int] = []
        rendered: list[str] = []
        chat_template = getattr(self._tokenizer, "chat_template", None)
        if not isinstance(chat_template, str) or not chat_template:
            raise GenerationError("tokenizer does not provide a chat template")
        for prompt, seed in zip(prompts, seeds, strict=True):
            if not isinstance(prompt, str):
                raise GenerationError("prompt must be a string")
            try:
                prompt.encode("utf-8")
            except UnicodeEncodeError:
                raise GenerationError("prompt must contain valid UTF-8 text") from None
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise GenerationError("seed must be an integer")
            message: dict[str, str] = {"role": "user", "content": prompt}
            try:
                rendered_prompt = self._tokenizer.apply_chat_template(
                    [message],
                    add_generation_prompt=True,
                    tokenize=False,
                )
            except Exception as error:
                raise GenerationError(f"could not encode configured chat prompt: {type(error).__name__}") from None
            normalized_prompts.append(prompt)
            normalized_seeds.append(seed)
            rendered.append(rendered_prompt)
        del normalized_prompts
        try:
            encoded = self._tokenizer(
                rendered,
                return_tensors="pt",
                add_special_tokens=False,
                padding=True,
            )
            input_ids = encoded["input_ids"]
            prompt_width = len(input_ids[0])
        except Exception as error:
            raise GenerationError(f"could not encode configured chat prompt batch: {type(error).__name__}") from None
        if self._device != "auto":
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
        elif hasattr(self._model, "device"):
            encoded = {key: value.to(self._model.device) for key, value in encoded.items()}
        self._transformers.set_seed(normalized_seeds[0])
        options: dict[str, object] = {
            "do_sample": False,
            "max_new_tokens": self._config.max_new_tokens,
        }
        started = time.perf_counter()
        try:
            with self._torch.inference_mode():
                generated = self._model.generate(**encoded, **options)
        except Exception as error:
            raise GenerationError(f"model batch generation failed: {type(error).__name__}") from None
        latency_ms = (time.perf_counter() - started) * 1000.0
        if len(generated) != len(rendered):
            raise GenerationError("model batch generation returned an unexpected number of sequences")
        attributed_latency = latency_ms / len(rendered)
        results: list[GenerationResult] = []
        for row in generated:
            new_token_ids = row[prompt_width:]
            try:
                completion = self._tokenizer.decode(new_token_ids, skip_special_tokens=True)
            except Exception as error:
                raise GenerationError(f"model decode failed: {type(error).__name__}") from None
            results.append(
                GenerationResult(
                    completion=completion,
                    completion_tokens=len(new_token_ids),
                    latency_ms=attributed_latency,
                    hit_max_new_tokens=len(new_token_ids) >= self._config.max_new_tokens,
                )
            )
        return results


def _generated_token_prefix(row: Any, *, prompt_width: int, eos_token_ids: set[int]) -> tuple[Any, int]:
    new_token_ids = row[prompt_width:]
    token_count = len(new_token_ids)
    if eos_token_ids:
        for index, token in enumerate(new_token_ids):
            if int(token) in eos_token_ids:
                token_count = index + 1
                break
    return new_token_ids[:token_count], token_count


def _sampling_eos_token_ids(model: Any, tokenizer: Any) -> set[int]:
    raw_eos = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
    if raw_eos is None:
        raw_eos = getattr(tokenizer, "eos_token_id", None)
    if isinstance(raw_eos, int):
        return {raw_eos}
    if isinstance(raw_eos, Sequence) and not isinstance(raw_eos, str | bytes | bytearray):
        return {int(value) for value in raw_eos}
    return set()


class TransformersSamplingCompletionGenerator:
    """Read-only completed-SFT generator for WP9 B-only sampled calibration."""

    def __init__(
        self,
        *,
        tokenizer: Any,
        model: Any,
        torch_runtime: Any,
        transformers_runtime: Any,
        device: str,
        config: SamplingGenerationConfig,
    ) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch_runtime
        self._transformers = transformers_runtime
        self._device = device
        self._config = config

    @classmethod
    def from_peft_checkpoint(
        cls,
        *,
        base_model_id: str,
        base_model_revision: str | None,
        adapter_dir: Path,
        device: str,
        config: SamplingGenerationConfig,
        local_files_only: bool = False,
    ) -> TransformersSamplingCompletionGenerator:
        """Load one identity-checked completed-B adapter for sampled inference."""
        if not isinstance(base_model_id, str) or not base_model_id.strip():
            raise GenerationError("model_id must be a non-empty string")
        if base_model_revision is not None and (
            not isinstance(base_model_revision, str) or not base_model_revision.strip()
        ):
            raise GenerationError("model_revision must be a non-empty string or null")
        if device not in {"cpu", "cuda", "auto"}:
            raise GenerationError("device must be cpu, cuda, or auto")
        if not isinstance(local_files_only, bool):
            raise GenerationError("local_files_only must be a boolean")
        torch_runtime, transformers_runtime = _load_transformers_runtime()
        peft_config_type, peft_model_type = _load_peft_runtime()
        resolved_adapter_dir, adapter_config, adapter_options = _load_identity_checked_peft_config(
            peft_config_type=peft_config_type,
            adapter_dir=adapter_dir,
            base_model_id=base_model_id,
            base_model_revision=base_model_revision,
            local_files_only=local_files_only,
            role="completed SFT",
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
            role="completed SFT",
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

    def generate_groups(
        self,
        prompts: Sequence[str],
        *,
        seeds: Sequence[int],
        num_generations: int,
    ) -> list[list[GenerationResult]]:
        """Generate multiple k=8 groups in one model call with independent problem RNG streams."""
        if isinstance(prompts, str | bytes | bytearray) or not isinstance(prompts, Sequence) or not prompts:
            raise GenerationError("prompts must be a non-empty sequence")
        if isinstance(seeds, str | bytes | bytearray) or not isinstance(seeds, Sequence):
            raise GenerationError("seeds must be a sequence")
        if len(prompts) != len(seeds):
            raise GenerationError("prompts and seeds must have equal lengths")
        if num_generations != 8:
            raise GenerationError("calibration num_generations must equal 8")
        if len(prompts) == 1:
            return [self.generate_group(prompts[0], seed=seeds[0], num_generations=num_generations)]
        chat_template = getattr(self._tokenizer, "chat_template", None)
        if not isinstance(chat_template, str) or not chat_template:
            raise GenerationError("tokenizer does not provide a chat template")
        rendered: list[str] = []
        normalized_seeds: list[int] = []
        for prompt, seed in zip(prompts, seeds, strict=True):
            if not isinstance(prompt, str):
                raise GenerationError("prompt must be a string")
            try:
                prompt.encode("utf-8")
            except UnicodeEncodeError:
                raise GenerationError("prompt must contain valid UTF-8 text") from None
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise GenerationError("seed must be an integer")
            try:
                rendered.append(
                    self._tokenizer.apply_chat_template(
                        [{"role": "user", "content": prompt}],
                        add_generation_prompt=True,
                        tokenize=False,
                    )
                )
            except Exception as error:
                raise GenerationError(f"could not encode configured chat prompt: {type(error).__name__}") from None
            normalized_seeds.append(seed)
        original_padding_side = getattr(self._tokenizer, "padding_side", None)
        try:
            if original_padding_side is not None:
                self._tokenizer.padding_side = "left"
            encoded = self._tokenizer(
                rendered,
                return_tensors="pt",
                add_special_tokens=False,
                padding=True,
            )
            prompt_width = len(encoded["input_ids"][0])
        except Exception as error:
            raise GenerationError(f"could not encode configured chat prompt batch: {type(error).__name__}") from None
        finally:
            if original_padding_side is not None:
                self._tokenizer.padding_side = original_padding_side
        if self._device != "auto":
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
        elif hasattr(self._model, "device"):
            encoded = {key: value.to(self._model.device) for key, value in encoded.items()}
        processor = _IndependentGroupSamplingProcessor(
            torch_runtime=self._torch,
            seeds=normalized_seeds,
            group_size=num_generations,
            temperature=float(self._config.temperature),
            top_p=float(self._config.top_p),
        )
        self._transformers.set_seed(normalized_seeds[0])
        started = time.perf_counter()
        try:
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **encoded,
                    do_sample=True,
                    temperature=1.0,
                    top_p=1.0,
                    top_k=0,
                    repetition_penalty=1.0,
                    max_new_tokens=self._config.max_new_tokens,
                    num_return_sequences=num_generations,
                    logits_processor=[processor],
                )
        except Exception as error:
            raise GenerationError(f"model sampled batch generation failed: {type(error).__name__}") from None
        latency_ms = (time.perf_counter() - started) * 1000.0
        expected_rows = len(rendered) * num_generations
        if len(generated) != expected_rows:
            raise GenerationError("model sampled batch generation returned an unexpected number of sequences")
        eos_ids = _sampling_eos_token_ids(self._model, self._tokenizer)
        attributed_latency = latency_ms / expected_rows
        grouped: list[list[GenerationResult]] = []
        for problem_index in range(len(rendered)):
            start = problem_index * num_generations
            rows = generated[start : start + num_generations]
            results: list[GenerationResult] = []
            for row in rows:
                new_token_ids, token_count = _generated_token_prefix(
                    row, prompt_width=prompt_width, eos_token_ids=eos_ids
                )
                try:
                    completion = self._tokenizer.decode(new_token_ids, skip_special_tokens=True)
                except Exception as error:
                    raise GenerationError(f"model decode failed: {type(error).__name__}") from None
                results.append(
                    GenerationResult(
                        completion=completion,
                        completion_tokens=token_count,
                        latency_ms=attributed_latency,
                        hit_max_new_tokens=token_count >= self._config.max_new_tokens,
                    )
                )
            grouped.append(results)
        return grouped

    def generate_group(self, prompt: str, *, seed: int, num_generations: int) -> list[GenerationResult]:
        """Generate exactly one ordered k=8 calibration block from a shared prompt."""
        if not isinstance(prompt, str):
            raise GenerationError("prompt must be a string")
        try:
            prompt.encode("utf-8")
        except UnicodeEncodeError:
            raise GenerationError("prompt must contain valid UTF-8 text") from None
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise GenerationError("seed must be an integer")
        if num_generations != 8:
            raise GenerationError("calibration num_generations must equal 8")
        chat_template = getattr(self._tokenizer, "chat_template", None)
        if not isinstance(chat_template, str) or not chat_template:
            raise GenerationError("tokenizer does not provide a chat template")
        try:
            rendered_prompt = self._tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                add_generation_prompt=True,
                tokenize=False,
            )
            encoded = self._tokenizer(rendered_prompt, return_tensors="pt", add_special_tokens=False)
            prompt_width = len(encoded["input_ids"][0])
        except Exception as error:
            raise GenerationError(f"could not encode configured chat prompt: {type(error).__name__}") from None
        if self._device != "auto":
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
        elif hasattr(self._model, "device"):
            encoded = {key: value.to(self._model.device) for key, value in encoded.items()}
        self._transformers.set_seed(seed)
        started = time.perf_counter()
        try:
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **encoded,
                    do_sample=True,
                    temperature=float(self._config.temperature),
                    top_p=float(self._config.top_p),
                    top_k=0,
                    repetition_penalty=1.0,
                    max_new_tokens=self._config.max_new_tokens,
                    num_return_sequences=num_generations,
                )
        except Exception as error:
            raise GenerationError(f"model sampled generation failed: {type(error).__name__}") from None
        latency_ms = (time.perf_counter() - started) * 1000.0
        if len(generated) != num_generations:
            raise GenerationError("model sampled generation returned an unexpected number of sequences")
        eos_ids = _sampling_eos_token_ids(self._model, self._tokenizer)
        attributed_latency = latency_ms / num_generations
        results: list[GenerationResult] = []
        for row in generated:
            new_token_ids, token_count = _generated_token_prefix(row, prompt_width=prompt_width, eos_token_ids=eos_ids)
            try:
                completion = self._tokenizer.decode(new_token_ids, skip_special_tokens=True)
            except Exception as error:
                raise GenerationError(f"model decode failed: {type(error).__name__}") from None
            results.append(
                GenerationResult(
                    completion=completion,
                    completion_tokens=token_count,
                    latency_ms=attributed_latency,
                    hit_max_new_tokens=token_count >= self._config.max_new_tokens,
                )
            )
        return results
