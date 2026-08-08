"""CUDA smoke tests for the frozen WP5-a generation backend on the GPU machine.

These tests are GPU-required: they auto-run in the default suite when a CUDA-capable
GPU with the full inference dependencies is detected, and are skipped with an
explicit reason on CPU-only machines so developers know a GPU is needed.

The model load is explicitly ``local_files_only=True``: the smoke contract assumes
the debug model is already cached locally, so it never performs Hugging Face network
retries when the network is unreachable. If the model is not cached, the test fails
fast with a message telling the user to cache it first.
"""

from __future__ import annotations

import importlib
import os

import pytest

from code_verifier.environment import collect_environment
from code_verifier.evaluation.generate import GenerationConfig, TransformersCompletionGenerator

_NO_GPU_REASON = (
    "GPU-required tests cannot run on this machine: no CUDA-capable GPU with the full "
    "inference dependencies (make install-full) was detected. CPU-only machines run the "
    "CPU suite only; run the full suite on the GPU development machine (GTX 1660 Ti)."
)


def _gpu_ready() -> bool:
    """Return True only when the machine exposes CUDA and the full inference stack."""
    record = collect_environment()
    return bool(
        record["gpu_count"] > 0
        and record["cuda_version"]
        and record["gpu_name"]
        and record["packages"]["transformers"] is not None
    )


pytestmark = [pytest.mark.gpu, pytest.mark.skipif(not _gpu_ready(), reason=_NO_GPU_REASON)]


def test_environment_records_cuda_identity() -> None:
    """A CUDA-capable machine must record runtime CUDA/GPU identity for resume reproducibility."""
    record = collect_environment()
    assert record["cuda_version"] is not None
    assert record["gpu_name"] is not None
    assert record["gpu_count"] >= 1
    assert record["packages"]["torch"] is not None


def test_frozen_generation_runs_on_cuda_in_fp16() -> None:
    """The frozen pass@1 generator must load in fp16 and generate on the CUDA device."""
    model_id = os.environ.get("CODE_VERIFIER_GPU_MODEL", "Qwen/Qwen2.5-Coder-0.5B-Instruct")
    config = GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8, dtype="float16")
    generator = TransformersCompletionGenerator.from_pretrained(
        model_id,
        model_revision=None,
        device="cuda",
        config=config,
        local_files_only=True,
    )
    assert generator.model_dtype == "float16"
    result = generator.generate(
        "Return a correct Python implementation for:\ndef solve(value):\n    return value + 1\n",
        seed=42,
    )
    assert isinstance(result.completion, str)
    assert result.completion
    assert result.completion_tokens >= 0


def test_cuda_autograd_forward_backward_smoke() -> None:
    """A minimal real CUDA autograd smoke; not a training acceptance test."""
    torch_runtime = importlib.import_module("torch")
    x = torch_runtime.randn(256, 256, device="cuda", requires_grad=True)
    loss = (x * x).mean()
    loss.backward()
    assert x.device.type == "cuda"
    assert x.grad is not None
    assert torch_runtime.isfinite(loss)
