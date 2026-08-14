"""Strict GRPO configuration, reward wiring, runtime, and run artifacts."""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.json_strict import json_values_equal
from code_verifier.data.leakage_checks import LeakageError, TrainingArtifactKind, check_training_record
from code_verifier.execution.base import CodeExecutor
from code_verifier.rewards.common import RewardContractError, compute_code_rewards


@dataclass(frozen=True)
class GRPOTrainingConfig:
    """Resolved exact-schema Public or Hidden GRPO settings."""

    run_name: str
    reward_mode: str
    dataset_path: Path
    piston_config: Path
    num_generations: int
    max_prompt_length: int
    max_completion_length: int
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    num_train_epochs: float
    max_steps: int
    warmup_ratio: float
    lr_scheduler_type: str
    temperature: float
    top_p: float
    beta: float
    bf16: bool
    fp16: bool
    gradient_checkpointing: bool
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    logging_steps: int
    save_steps: int
    eval_steps: int
    seed: int
    min_cuda_memory_gb: float


class GRPOTrainingError(RuntimeError):
    """Raised when GRPO configuration, hardware, runtime, or artifacts fail closed."""


_CONFIG_FIELDS = {
    "run_name",
    "reward_mode",
    "dataset_path",
    "piston_config",
    "num_generations",
    "max_prompt_length",
    "max_completion_length",
    "per_device_train_batch_size",
    "gradient_accumulation_steps",
    "learning_rate",
    "num_train_epochs",
    "max_steps",
    "warmup_ratio",
    "lr_scheduler_type",
    "temperature",
    "top_p",
    "beta",
    "bf16",
    "fp16",
    "gradient_checkpointing",
    "lora_r",
    "lora_alpha",
    "lora_dropout",
    "logging_steps",
    "save_steps",
    "eval_steps",
    "seed",
    "min_cuda_memory_gb",
}
_PAIR_DIFFERENCES = {"run_name", "reward_mode", "dataset_path"}
_MIN_TRAINING_CUDA_MEMORY_GB = 20.0


def _exact_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise GRPOTrainingError("GRPO config must be a mapping with string keys")
    missing = _CONFIG_FIELDS - set(value)
    unknown = set(value) - _CONFIG_FIELDS
    if missing:
        raise GRPOTrainingError(f"GRPO config is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise GRPOTrainingError(f"GRPO config contains unknown field(s): {', '.join(sorted(unknown))}")
    return cast(Mapping[str, object], value)


def _nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GRPOTrainingError(f"{field_name} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise GRPOTrainingError(f"{field_name} must contain valid UTF-8 text") from None
    return value


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GRPOTrainingError(f"{field_name} must be a positive integer")
    return value


def _finite_float(value: object, *, field_name: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise GRPOTrainingError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = " positive" if positive else ""
        raise GRPOTrainingError(f"{field_name} must be a finite{qualifier} number")
    return number


def _path(value: object, *, field_name: str) -> Path:
    candidate = Path(_nonempty_string(value, field_name=field_name))
    resolved = candidate if candidate.is_absolute() else Path.cwd() / candidate
    if resolved.resolve(strict=False) == Path(resolved.anchor):
        raise GRPOTrainingError(f"{field_name} must not resolve to the filesystem root")
    return resolved


def grpo_training_config_from_mapping(value: object) -> GRPOTrainingConfig:
    """Parse one exact flat GRPO mapping and reject unsafe experiment settings."""
    root = _exact_mapping(value)
    run_name = _nonempty_string(root["run_name"], field_name="run_name")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_name) or ".." in run_name:
        raise GRPOTrainingError("run_name contains unsafe path characters")
    reward_mode = _nonempty_string(root["reward_mode"], field_name="reward_mode")
    if reward_mode not in {"public", "hidden"}:
        raise GRPOTrainingError("reward_mode must be public or hidden")
    learning_rate = _finite_float(root["learning_rate"], field_name="learning_rate", positive=True)
    epochs = _finite_float(root["num_train_epochs"], field_name="num_train_epochs", positive=True)
    warmup_ratio = _finite_float(root["warmup_ratio"], field_name="warmup_ratio")
    if not 0.0 <= warmup_ratio <= 1.0:
        raise GRPOTrainingError("warmup_ratio must be between 0 and 1")
    temperature = _finite_float(root["temperature"], field_name="temperature", positive=True)
    top_p = _finite_float(root["top_p"], field_name="top_p", positive=True)
    if top_p > 1.0:
        raise GRPOTrainingError("top_p must be at most 1")
    beta = _finite_float(root["beta"], field_name="beta")
    if beta < 0.0:
        raise GRPOTrainingError("beta must be non-negative")
    lora_dropout = _finite_float(root["lora_dropout"], field_name="lora_dropout")
    if not 0.0 <= lora_dropout < 1.0:
        raise GRPOTrainingError("lora_dropout must be between 0 and 1")
    bf16 = root["bf16"]
    fp16 = root["fp16"]
    gradient_checkpointing = root["gradient_checkpointing"]
    if not all(isinstance(item, bool) for item in (bf16, fp16, gradient_checkpointing)):
        raise GRPOTrainingError("bf16, fp16, and gradient_checkpointing must be booleans")
    if bf16 is fp16:
        raise GRPOTrainingError("exactly one of bf16 and fp16 must be true")
    if gradient_checkpointing is not True:
        raise GRPOTrainingError("gradient_checkpointing must be true")
    scheduler = _nonempty_string(root["lr_scheduler_type"], field_name="lr_scheduler_type")
    if scheduler != "cosine":
        raise GRPOTrainingError("lr_scheduler_type must be cosine")
    seed = root["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise GRPOTrainingError("seed must be an integer")
    min_memory = _finite_float(root["min_cuda_memory_gb"], field_name="min_cuda_memory_gb", positive=True)
    if min_memory < _MIN_TRAINING_CUDA_MEMORY_GB:
        raise GRPOTrainingError(f"min_cuda_memory_gb must be at least {_MIN_TRAINING_CUDA_MEMORY_GB:g} GiB")
    return GRPOTrainingConfig(
        run_name=run_name,
        reward_mode=reward_mode,
        dataset_path=_path(root["dataset_path"], field_name="dataset_path"),
        piston_config=_path(root["piston_config"], field_name="piston_config"),
        num_generations=_positive_int(root["num_generations"], field_name="num_generations"),
        max_prompt_length=_positive_int(root["max_prompt_length"], field_name="max_prompt_length"),
        max_completion_length=_positive_int(root["max_completion_length"], field_name="max_completion_length"),
        per_device_train_batch_size=_positive_int(
            root["per_device_train_batch_size"], field_name="per_device_train_batch_size"
        ),
        gradient_accumulation_steps=_positive_int(
            root["gradient_accumulation_steps"], field_name="gradient_accumulation_steps"
        ),
        learning_rate=learning_rate,
        num_train_epochs=epochs,
        max_steps=_positive_int(root["max_steps"], field_name="max_steps"),
        warmup_ratio=warmup_ratio,
        lr_scheduler_type=scheduler,
        temperature=temperature,
        top_p=top_p,
        beta=beta,
        bf16=cast(bool, bf16),
        fp16=cast(bool, fp16),
        gradient_checkpointing=cast(bool, gradient_checkpointing),
        lora_r=_positive_int(root["lora_r"], field_name="lora_r"),
        lora_alpha=_positive_int(root["lora_alpha"], field_name="lora_alpha"),
        lora_dropout=lora_dropout,
        logging_steps=_positive_int(root["logging_steps"], field_name="logging_steps"),
        save_steps=_positive_int(root["save_steps"], field_name="save_steps"),
        eval_steps=_positive_int(root["eval_steps"], field_name="eval_steps"),
        seed=seed,
        min_cuda_memory_gb=min_memory,
    )


def load_grpo_training_config(path: Path) -> GRPOTrainingConfig:
    """Load and strictly validate one GRPO YAML file."""
    try:
        return grpo_training_config_from_mapping(load_yaml_mapping(path))
    except ConfigError as error:
        raise GRPOTrainingError(str(error)) from None


def validate_grpo_config_pair(public: GRPOTrainingConfig, hidden: GRPOTrainingConfig) -> None:
    """Require C/D configs to differ only in reward-source identity fields."""
    if public.reward_mode != "public" or hidden.reward_mode != "hidden":
        raise GRPOTrainingError("GRPO config pair must be ordered public then hidden")
    public_values = asdict(public)
    hidden_values = asdict(hidden)
    differing = {field for field in _CONFIG_FIELDS if public_values[field] != hidden_values[field]}
    if differing - _PAIR_DIFFERENCES:
        raise GRPOTrainingError("Public and Hidden GRPO experiment settings must match")


def validate_grpo_artifact_pair(
    public_records: Sequence[Mapping[str, object]],
    hidden_records: Sequence[Mapping[str, object]],
) -> None:
    """Require ordered C/D artifacts to share every field except hidden reward tests."""
    if len(public_records) != len(hidden_records) or not public_records:
        raise GRPOTrainingError("Public and Hidden GRPO artifacts must have equal non-zero length")
    shared_fields = {"problem_id", "prompt", "function_name", "function_signature", "visible_tests", "metadata"}
    for index in range(len(public_records)):
        public = public_records[index]
        hidden = hidden_records[index]
        try:
            check_training_record(public, kind=TrainingArtifactKind.PUBLIC_GRPO)
            check_training_record(hidden, kind=TrainingArtifactKind.HIDDEN_GRPO)
        except LeakageError as error:
            raise GRPOTrainingError(str(error)) from None
        if any(not json_values_equal(public[field], hidden[field]) for field in shared_fields):
            raise GRPOTrainingError(f"Public and Hidden GRPO artifact row {index} does not share identical inputs")


def _batch_length(value: object, *, field_name: str) -> int:
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
        raise GRPOTrainingError(f"{field_name} must be a non-string sequence")
    return len(value)


def _completion_text(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, bytes | bytearray | Mapping) or not isinstance(item, Sequence) or not item:
        raise GRPOTrainingError("completion item must be a string or non-empty chat sequence")
    message = item[-1]
    if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
        raise GRPOTrainingError("chat completion must end with string content")
    return cast(str, message["content"])


def _completion_token_count(value: object) -> int:
    if isinstance(value, str | bytes | bytearray | Mapping):
        raise GRPOTrainingError("completion_ids items must be token sequences")
    try:
        count = len(cast(Any, value))
    except (TypeError, OverflowError):
        raise GRPOTrainingError("completion_ids items must be token sequences") from None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise GRPOTrainingError("completion_ids items must have a valid length")
    return count


def _jsonl_line(value: Mapping[str, object]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    except (TypeError, ValueError, OverflowError):
        raise GRPOTrainingError("GRPO log record must be finite and JSON safe") from None


def _append_lines(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)
        handle.flush()
        os.fsync(handle.fileno())


def build_grpo_reward_callback(
    *,
    reward_mode: str,
    executor: CodeExecutor,
    rollout_log_path: Path,
    reward_log_path: Path,
    group_metrics_log_path: Path,
    num_generations: int,
    max_completion_length: int,
) -> Callable[..., list[float]]:
    """Build one pinned-TRL reward function with strict alignment and sanitized logs."""
    if reward_mode not in {"public", "hidden"}:
        raise GRPOTrainingError("reward_mode must be public or hidden")
    if isinstance(num_generations, bool) or not isinstance(num_generations, int) or num_generations <= 0:
        raise GRPOTrainingError("num_generations must be a positive integer")
    if (
        isinstance(max_completion_length, bool)
        or not isinstance(max_completion_length, int)
        or max_completion_length <= 0
    ):
        raise GRPOTrainingError("max_completion_length must be a positive integer")

    expected_columns = {"problem_id", "function_name", "metadata", "visible_tests"}
    if reward_mode == "hidden":
        expected_columns.add("train_hidden_tests")

    def reward_callback(
        *,
        prompts: object,
        completions: object,
        completion_ids: object,
        **columns: object,
    ) -> list[float]:
        if set(columns) != expected_columns:
            raise GRPOTrainingError("GRPO reward callback received unexpected or missing dataset columns")
        lengths = {
            "prompts": _batch_length(prompts, field_name="prompts"),
            "completions": _batch_length(completions, field_name="completions"),
            "completion_ids": _batch_length(completion_ids, field_name="completion_ids"),
        }
        lengths.update({field: _batch_length(value, field_name=field) for field, value in columns.items()})
        batch_size = lengths["completions"]
        if batch_size == 0 or any(length != batch_size for length in lengths.values()):
            details = ", ".join(f"{name}={length}" for name, length in sorted(lengths.items()))
            raise GRPOTrainingError(f"GRPO reward batch lengths must match and be non-zero: {details}")

        problem_ids = cast(Sequence[object], columns["problem_id"])
        normalized_ids = [_nonempty_string(value, field_name="problem_id") for value in problem_ids]
        groups: dict[str, list[int]] = {}
        for index, problem_id in enumerate(normalized_ids):
            groups.setdefault(problem_id, []).append(index)
        if any(len(indices) != num_generations for indices in groups.values()):
            raise GRPOTrainingError("each GRPO problem group must contain exactly num_generations completions")

        selected_tests = columns["visible_tests"] if reward_mode == "public" else columns["train_hidden_tests"]
        try:
            rewards, component_records = compute_code_rewards(
                completions,
                selected_tests,
                columns["function_name"],
                columns["metadata"],
                executor,
                reward_mode,
            )
        except RewardContractError as error:
            raise GRPOTrainingError(str(error)) from None
        if len(rewards) != batch_size or len(component_records) != batch_size:
            raise GRPOTrainingError("GRPO reward core returned a misaligned batch")
        if any(not math.isfinite(reward) for reward in rewards):
            raise GRPOTrainingError("GRPO rewards must be finite")

        completion_values = cast(Sequence[object], completions)
        completion_id_values = cast(Sequence[object], completion_ids)
        group_index_by_item: dict[int, tuple[int, int]] = {}
        group_lines: list[str] = []
        for group_index, (problem_id, item_indices) in enumerate(groups.items()):
            group_rewards = [rewards[item_index] for item_index in item_indices]
            mean = sum(group_rewards) / len(group_rewards)
            variance = sum((reward - mean) ** 2 for reward in group_rewards) / len(group_rewards)
            std = math.sqrt(variance)
            if not math.isfinite(mean) or not math.isfinite(std):
                raise GRPOTrainingError("GRPO group metrics must be finite")
            for group_item_index, item_index in enumerate(item_indices):
                group_index_by_item[item_index] = (group_index, group_item_index)
            group_lines.append(
                _jsonl_line(
                    {
                        "group_index": group_index,
                        "problem_id": problem_id,
                        "reward_mode": reward_mode,
                        "sample_count": len(group_rewards),
                        "mean": mean,
                        "std": std,
                        "all_equal": all(reward == group_rewards[0] for reward in group_rewards),
                    }
                )
            )

        rollout_lines: list[str] = []
        reward_lines: list[str] = []
        for item_index in range(batch_size):
            group_index, group_item_index = group_index_by_item[item_index]
            token_count = _completion_token_count(completion_id_values[item_index])
            rollout_lines.append(
                _jsonl_line(
                    {
                        "item_index": item_index,
                        "group_index": group_index,
                        "group_item_index": group_item_index,
                        "problem_id": normalized_ids[item_index],
                        "reward_mode": reward_mode,
                        "completion": _completion_text(completion_values[item_index]),
                        "completion_token_count": token_count,
                        "truncated": token_count >= max_completion_length,
                        "total_reward": rewards[item_index],
                    }
                )
            )
            reward_lines.append(
                _jsonl_line(
                    {
                        "item_index": item_index,
                        "group_index": group_index,
                        "group_item_index": group_item_index,
                        "problem_id": normalized_ids[item_index],
                        **component_records[item_index],
                    }
                )
            )
        _append_lines(rollout_log_path, rollout_lines)
        _append_lines(reward_log_path, reward_lines)
        _append_lines(group_metrics_log_path, group_lines)
        return rewards

    reward_callback.__name__ = f"{reward_mode}_code_reward"
    return reward_callback
