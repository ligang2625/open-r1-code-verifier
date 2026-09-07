"""WP9-d optimized GRPO recipe configuration tests."""

from pathlib import Path

from code_verifier.training.grpo import load_grpo_training_config, validate_grpo_config_pair


def test_wp9d_recipe_a_configs_are_paired_and_use_colocated_vllm() -> None:
    public = load_grpo_training_config(Path("configs/grpo/wp9d-recipe-a-public.yaml"))
    hidden = load_grpo_training_config(Path("configs/grpo/wp9d-recipe-a-hidden.yaml"))

    validate_grpo_config_pair(public, hidden)
    assert public.max_steps == 1200
    assert public.learning_rate == 5e-6
    assert public.lr_scheduler_type == "constant_with_warmup"
    assert public.num_generations == 8
    assert public.per_device_train_batch_size == 1
    assert public.gradient_accumulation_steps == 8
    assert public.beta == 0.01
    assert public.lora_r == 16
    assert public.lora_alpha == 32
    assert public.use_vllm is True
    assert public.vllm_mode == "colocate"
    assert public.vllm_gpu_memory_utilization == 0.4
    assert public.eval_steps == 300
    assert public.save_steps == 100


def test_historical_wp9c_config_keeps_non_vllm_default() -> None:
    historical = load_grpo_training_config(Path("configs/grpo/wp9c-c29-active1354-public.yaml"))
    assert historical.use_vllm is False
    assert historical.vllm_mode == "colocate"
    assert historical.vllm_gpu_memory_utilization == 0.4


def test_wp9d_runtime_smoke_configs_are_one_step_paired_vllm() -> None:
    public = load_grpo_training_config(Path("configs/grpo/wp9d-runtime-smoke-public.yaml"))
    hidden = load_grpo_training_config(Path("configs/grpo/wp9d-runtime-smoke-hidden.yaml"))
    validate_grpo_config_pair(public, hidden)
    assert public.max_steps == 1
    assert public.save_steps == 1
    assert public.warmup_ratio == 0.0
    assert public.use_vllm is True
    assert public.vllm_mode == "colocate"
    assert public.num_generations == 8
    assert public.per_device_train_batch_size * public.gradient_accumulation_steps == 8
