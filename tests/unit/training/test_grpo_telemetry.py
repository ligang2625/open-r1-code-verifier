from __future__ import annotations

import math
from collections import defaultdict
from types import SimpleNamespace

from code_verifier.training.grpo import _install_grpo_runtime_telemetry
from code_verifier.training.grpo_telemetry import GRPORollingTelemetry


def test_rolling_telemetry_keeps_bounded_suffix_and_finite_snapshot() -> None:
    telemetry = GRPORollingTelemetry(window_size=2)
    telemetry.observe(
        all_test_correct=True,
        all_test_zero=False,
        total_reward_std=0.0,
        verifier_runtime_seconds=1.0,
    )
    telemetry.observe(
        all_test_correct=False,
        all_test_zero=True,
        total_reward_std=0.5,
        verifier_runtime_seconds=2.0,
    )
    telemetry.observe(
        all_test_correct=False,
        all_test_zero=False,
        total_reward_std=1.0,
        verifier_runtime_seconds=3.0,
    )

    snapshot = telemetry.snapshot()
    assert snapshot["rolling_window_groups"] == 2.0
    assert snapshot["rolling_all_test_correct_fraction"] == 0.0
    assert snapshot["rolling_all_test_zero_fraction"] == 0.5
    assert snapshot["rolling_total_reward_zero_variance_fraction"] == 0.0
    assert snapshot["rolling_effective_nonzero_variance_groups"] == 2.0
    assert snapshot["rolling_verifier_runtime_seconds"] == 5.0
    assert all(math.isfinite(value) and value >= 0.0 for value in snapshot.values())


def test_refresh_runtime_telemetry_times_backward_optimizer_and_exports_rolling_metrics() -> None:
    class FakeModel:
        training = True
        is_gradient_checkpointing = False

        @staticmethod
        def generate(*args: object, **kwargs: object) -> str:
            return "generated"

    class FakeOptimizer:
        @staticmethod
        def step() -> str:
            return "stepped"

    class FakeAccelerator:
        def __init__(self, model: FakeModel) -> None:
            self.model = model

        def unwrap_model(self, model: object) -> FakeModel:
            assert model is self.model
            return self.model

        @staticmethod
        def backward(loss: object) -> object:
            return loss

    class FakeTrainer:
        def __init__(self) -> None:
            self.model = FakeModel()
            self.model_wrapped = self.model
            self.accelerator = FakeAccelerator(self.model)
            self.args = SimpleNamespace()
            self.state = SimpleNamespace(global_step=0)
            self.optimizer: FakeOptimizer | None = None
            self._metrics: dict[str, defaultdict[str, list[float]]] = {
                "train": defaultdict(list),
                "eval": defaultdict(list),
            }

        def _generate_and_score_completions(self, inputs: object) -> object:
            return inputs

        def _get_per_token_logps(self, model: object, *args: object, **kwargs: object) -> str:
            return "logps"

        def training_step(self, *args: object, **kwargs: object) -> str:
            return "loss"

        def _maybe_log_save_evaluate(self, *args: object, **kwargs: object) -> str:
            return "logged"

        def create_optimizer_and_scheduler(self, num_training_steps: int) -> None:
            assert num_training_steps > 0
            self.optimizer = FakeOptimizer()

    rolling = GRPORollingTelemetry(window_size=4)
    rolling.observe(
        all_test_correct=False,
        all_test_zero=False,
        total_reward_std=0.25,
        verifier_runtime_seconds=0.5,
    )
    trainer = FakeTrainer()
    _install_grpo_runtime_telemetry(
        trainer,
        rolling_telemetry=rolling,
        require_optimizer_breakdown=True,
    )

    assert trainer.accelerator.backward("loss") == "loss"
    trainer.create_optimizer_and_scheduler(1)
    optimizer = trainer.optimizer
    assert optimizer is not None
    assert optimizer.step() == "stepped"
    assert trainer.training_step() == "loss"
    trainer.state.global_step = 1
    assert trainer._maybe_log_save_evaluate() == "logged"

    train_metrics = trainer._metrics["train"]
    assert len(train_metrics["backward_runtime_seconds"]) == 1
    assert len(train_metrics["optimizer_runtime_seconds"]) == 1
    assert len(train_metrics["step_runtime_seconds"]) == 1
    assert train_metrics["rolling_window_groups"] == [1.0]
    assert train_metrics["rolling_group_reward_std_mean"] == [0.25]
    assert train_metrics["rolling_verifier_runtime_seconds"] == [0.5]
    assert all(math.isfinite(value) and value >= 0.0 for values in train_metrics.values() for value in values)
