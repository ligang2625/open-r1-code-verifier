"""Colocated-vLLM generation timing hooks for the pinned GRPO runtime."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any


class GRPOVLLMTelemetryError(RuntimeError):
    """Raised when the pinned colocated-vLLM timing surface is unavailable."""


def install_colocated_vllm_generation_timing(trainer: Any, *, mode: str) -> Callable[[], None]:
    """Wrap ``trainer.llm.generate`` when colocated vLLM is active and return a restore callback."""
    if mode not in {"train", "eval"}:
        raise GRPOVLLMTelemetryError("GRPO vLLM telemetry mode must be train or eval")
    if not bool(getattr(trainer, "use_vllm", False)) or getattr(trainer, "vllm_mode", None) != "colocate":
        return lambda: None

    llm = getattr(trainer, "llm", None)
    original_generate = getattr(llm, "generate", None)
    if llm is None or not callable(original_generate):
        raise GRPOVLLMTelemetryError("pinned colocated vLLM trainer does not provide callable llm.generate")

    instance_dict = getattr(llm, "__dict__", {})
    had_instance_generate = isinstance(instance_dict, dict) and "generate" in instance_dict
    previous_instance_generate = instance_dict.get("generate") if had_instance_generate else None
    restored = False

    def timed_generate(*args: object, **kwargs: object) -> object:
        started = time.perf_counter()
        try:
            return original_generate(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - started
            if not math.isfinite(elapsed) or elapsed < 0.0:
                raise GRPOVLLMTelemetryError("GRPO vLLM generation runtime must be finite and non-negative")
            trainer._metrics[mode]["generation_runtime_seconds"].append(elapsed)
            trainer._metrics[mode]["vllm_generation_runtime_seconds"].append(elapsed)

    llm.generate = timed_generate

    def restore() -> None:
        nonlocal restored
        if restored:
            return
        restored = True
        if had_instance_generate:
            llm.generate = previous_instance_generate
            return
        with suppress(AttributeError):
            del llm.generate

    return restore
