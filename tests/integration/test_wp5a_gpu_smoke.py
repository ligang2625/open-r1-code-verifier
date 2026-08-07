"""CUDA smoke tests for the frozen WP5-a generation backend on the GPU machine.

These tests are GPU-required: they auto-run in the default suite when a CUDA-capable
GPU with the full inference dependencies is detected, and are skipped with an
explicit reason on CPU-only machines so developers know a GPU is needed.
"""

from __future__ import annotations

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


def test_frozen_generation_runs_on_cuda() -> None:
    """The frozen pass@1 generator must load and generate on the CUDA device."""
    model_id = os.environ.get("CODE_VERIFIER_GPU_MODEL", "Qwen/Qwen2.5-Coder-0.5B-Instruct")
    config = GenerationConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=8)
    generator = TransformersCompletionGenerator.from_pretrained(
        model_id,
        model_revision=None,
        device="cuda",
        config=config,
    )
    result = generator.generate(
        "Return a correct Python implementation for:\ndef solve(value):\n    return value + 1\n",
        seed=42,
    )
    assert isinstance(result.completion, str)
    assert result.completion
    assert result.completion_tokens >= 0
