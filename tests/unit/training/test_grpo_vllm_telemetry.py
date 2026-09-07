from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

import pytest

from code_verifier.training import grpo as grpo_module


def test_runtime_telemetry_times_colocated_vllm_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeModel:
        training = True

        def generate(self) -> str:
            raise AssertionError("colocated vLLM rollout must not use model.generate")

    class FakeLLM:
        def generate(self, prompts: object) -> str:
            assert prompts == ["hello"]
            return "vllm-generated"

    class FakeAccelerator:
        def __init__(self, model: FakeModel) -> None:
            self.model = model

        def unwrap_model(self, model: object) -> FakeModel:
            assert model is self.model
            return self.model

    class FakeTrainer:
        def __init__(self) -> None:
            self.model = FakeModel()
            self.model_wrapped = self.model
            self.accelerator = FakeAccelerator(self.model)
            self.args = SimpleNamespace(gradient_accumulation_steps=8)
            self.state = SimpleNamespace(global_step=0)
            self.use_vllm = True
            self.vllm_mode = "colocate"
            self.llm = FakeLLM()
            self._metrics: dict[str, defaultdict[str, list[float]]] = {
                "train": defaultdict(list),
                "eval": defaultdict(list),
            }

        def _generate_and_score_completions(self, inputs: object) -> object:
            assert self.llm.generate(["hello"]) == "vllm-generated"
            return inputs

        def _get_per_token_logps(self, model: FakeModel) -> str:
            del model
            return "logps"

        def training_step(self) -> str:
            return "loss"

        def _maybe_log_save_evaluate(self) -> str:
            return "logged"

    trainer = FakeTrainer()
    original_llm_generate = trainer.llm.generate
    times = iter([10.0, 11.0, 13.5, 14.0])
    monkeypatch.setattr("code_verifier.training.grpo.time.perf_counter", lambda: next(times))

    grpo_module._install_grpo_runtime_telemetry(trainer)
    result = trainer._generate_and_score_completions([{"prompt": "hello"}])

    assert result == [{"prompt": "hello"}]
    assert trainer._metrics["train"]["generation_runtime_seconds"] == [pytest.approx(2.5)]
    assert trainer._metrics["train"]["vllm_generation_runtime_seconds"] == [pytest.approx(2.5)]
    assert trainer._metrics["train"]["rollout_runtime_seconds"] == [pytest.approx(4.0)]
    assert trainer.llm.generate == original_llm_generate
    assert "generate" not in trainer.model.__dict__
