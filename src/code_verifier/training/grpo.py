"""Strict GRPO configuration, reward wiring, runtime, and run artifacts."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import yaml

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.json_strict import json_values_equal
from code_verifier.data.leakage_checks import (
    LeakageError,
    TrainingArtifactKind,
    check_training_record,
    load_training_artifact,
)
from code_verifier.environment import collect_environment
from code_verifier.execution.base import CodeExecutor
from code_verifier.rewards.common import RewardContractError, compute_code_rewards
from code_verifier.training.grpo_data import build_grpo_dataset
from code_verifier.training.open_r1_adapter import import_open_r1_module
from code_verifier.training.sft import SFTCheckpointIdentity, SFTTrainingError, load_completed_sft_checkpoint


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


@dataclass(frozen=True)
class GRPOTrainingSummary:
    """Non-sensitive completed GRPO training summary."""

    run_dir: Path
    checkpoint_dir: Path
    reward_mode: str
    train_loss: float
    train_samples: int
    gpu_hours: float


@dataclass(frozen=True)
class GRPOCheckpointIdentity:
    """Non-sensitive identity for one completed GRPO adapter checkpoint."""

    run_dir: Path
    checkpoint_dir: Path
    run_id: str
    reward_mode: str
    dataset_hash: str
    config_hash: str
    dependency_lock_hash: str
    seed: int
    parent_sft: SFTCheckpointIdentity


class GRPOTrainingError(RuntimeError):
    """Raised when GRPO configuration, hardware, runtime, or artifacts fail closed."""


@dataclass(frozen=True)
class _GRPORuntime:
    """Pinned runtime surface kept injectable for non-training engineering tests."""

    model_config_type: Any
    training_config_type: Any
    trainer_type: Any
    get_peft_config: Any
    get_tokenizer: Any
    get_model: Any
    peft_config_type: Any
    peft_model_type: Any


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
_RUNTIME_VERSIONS = {
    "trl": "0.18.0",
    "transformers": "4.52.3",
    "accelerate": "1.4.0",
    "peft": "0.14.0",
}
_GRPO_RUN_LAYOUT = {
    "resolved_config.yaml",
    "environment.json",
    "run.json",
    "metrics.jsonl",
    "rollouts.jsonl",
    "rewards.jsonl",
    "group_metrics.jsonl",
    "stdout.log",
    "stderr.log",
    "checkpoints",
}


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
    num_generations = _positive_int(root["num_generations"], field_name="num_generations")
    if num_generations < 2:
        raise GRPOTrainingError("num_generations must be at least 2")
    per_device_train_batch_size = _positive_int(
        root["per_device_train_batch_size"], field_name="per_device_train_batch_size"
    )
    gradient_accumulation_steps = _positive_int(
        root["gradient_accumulation_steps"], field_name="gradient_accumulation_steps"
    )
    generation_batch_size = per_device_train_batch_size * gradient_accumulation_steps
    if generation_batch_size % num_generations != 0:
        raise GRPOTrainingError("num_generations must evenly divide the single-GPU effective generation batch size")
    return GRPOTrainingConfig(
        run_name=run_name,
        reward_mode=reward_mode,
        dataset_path=_path(root["dataset_path"], field_name="dataset_path"),
        piston_config=_path(root["piston_config"], field_name="piston_config"),
        num_generations=num_generations,
        max_prompt_length=_positive_int(root["max_prompt_length"], field_name="max_prompt_length"),
        max_completion_length=_positive_int(root["max_completion_length"], field_name="max_completion_length"),
        per_device_train_batch_size=per_device_train_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
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


def _checkpoint_identity_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GRPOTrainingError(f"completed GRPO run has invalid {field_name}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise GRPOTrainingError(f"completed GRPO run has invalid {field_name}") from None
    return value


def _checkpoint_identity_hash(value: object, *, field_name: str) -> str:
    text = _checkpoint_identity_string(value, field_name=field_name)
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise GRPOTrainingError(f"completed GRPO run has invalid {field_name}")
    return text


def load_completed_grpo_checkpoint(run_dir: Path) -> GRPOCheckpointIdentity:
    """Load a completed GRPO adapter identity and revalidate its parent SFT run."""
    try:
        resolved_run_dir = run_dir.resolve(strict=True)
    except OSError:
        raise GRPOTrainingError("completed GRPO run must be an existing directory") from None
    if not resolved_run_dir.is_dir():
        raise GRPOTrainingError("completed GRPO run must be an existing directory")
    try:
        if {path.name for path in resolved_run_dir.iterdir()} != _GRPO_RUN_LAYOUT:
            raise GRPOTrainingError("completed GRPO run does not match the strict artifact layout")
        checkpoint_path = resolved_run_dir / "checkpoints"
        if checkpoint_path.is_symlink():
            raise GRPOTrainingError("completed GRPO checkpoint must belong directly to its GRPO run")
        checkpoint_dir = checkpoint_path.resolve(strict=True)
        if not checkpoint_dir.is_dir() or checkpoint_dir.parent != resolved_run_dir:
            raise GRPOTrainingError("completed GRPO checkpoint must belong directly to its GRPO run")
        metadata_value = json.loads((resolved_run_dir / "run.json").read_text(encoding="utf-8"))
    except GRPOTrainingError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise GRPOTrainingError("completed GRPO run metadata is unreadable") from None
    if not isinstance(metadata_value, dict) or metadata_value.get("status") != "completed":
        raise GRPOTrainingError("GRPO checkpoint loading requires a completed run")

    adapter_paths = {
        name: checkpoint_dir / name for name in ("adapter_config.json", "adapter_model.safetensors")
    }
    if any(not path.is_file() or path.is_symlink() for path in adapter_paths.values()):
        raise GRPOTrainingError("completed GRPO run has an incomplete PEFT adapter artifact")
    try:
        adapter_config = json.loads(adapter_paths["adapter_config.json"].read_text(encoding="utf-8"))
        adapter_size = adapter_paths["adapter_model.safetensors"].stat().st_size
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise GRPOTrainingError("completed GRPO run has an invalid PEFT adapter artifact") from None
    if not isinstance(adapter_config, dict) or adapter_size <= 0:
        raise GRPOTrainingError("completed GRPO run has an invalid PEFT adapter artifact")

    parent_run_path = metadata_value.get("parent_sft_run_path")
    if not isinstance(parent_run_path, str) or not parent_run_path.strip():
        raise GRPOTrainingError("completed GRPO run has invalid parent_sft_run_path")
    try:
        parent_sft = load_completed_sft_checkpoint(Path(parent_run_path))
    except SFTTrainingError as error:
        raise GRPOTrainingError(f"completed GRPO parent SFT identity is invalid: {error}") from None
    expected_parent = _parent_identity_mapping(parent_sft)
    if any(metadata_value.get(field) != value for field, value in expected_parent.items()):
        raise GRPOTrainingError("completed GRPO parent SFT identity does not match its completed run")

    if adapter_config.get("base_model_name_or_path") != parent_sft.model_id:
        raise GRPOTrainingError("GRPO adapter base model identity does not match the parent SFT run")
    adapter_revision = adapter_config.get("revision")
    if adapter_revision is not None and adapter_revision != parent_sft.model_revision:
        raise GRPOTrainingError("GRPO adapter revision does not match the parent SFT run")
    reward_mode = _checkpoint_identity_string(metadata_value.get("reward_mode"), field_name="reward_mode")
    if reward_mode not in {"public", "hidden"}:
        raise GRPOTrainingError("completed GRPO run has invalid reward_mode")
    seed = metadata_value.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise GRPOTrainingError("completed GRPO run has invalid seed")
    return GRPOCheckpointIdentity(
        run_dir=resolved_run_dir,
        checkpoint_dir=checkpoint_dir,
        run_id=_checkpoint_identity_string(metadata_value.get("run_id"), field_name="run_id"),
        reward_mode=reward_mode,
        dataset_hash=_checkpoint_identity_hash(metadata_value.get("dataset_hash"), field_name="dataset_hash"),
        config_hash=_checkpoint_identity_hash(metadata_value.get("config_hash"), field_name="config_hash"),
        dependency_lock_hash=_checkpoint_identity_hash(
            metadata_value.get("dependency_lock_hash"), field_name="dependency_lock_hash"
        ),
        seed=seed,
        parent_sft=parent_sft,
    )


def grpo_evaluation_checkpoint_id(identity: GRPOCheckpointIdentity) -> str:
    """Return a stable checkpoint string binding C/D and its completed parent B."""
    parent = identity.parent_sft
    canonical = {
        "checkpoint_dir": str(identity.checkpoint_dir),
        "config_hash": identity.config_hash,
        "dataset_hash": identity.dataset_hash,
        "dependency_lock_hash": identity.dependency_lock_hash,
        "parent_sft": {
            "checkpoint_dir": str(parent.checkpoint_dir),
            "config_hash": parent.config_hash,
            "dataset_hash": parent.dataset_hash,
            "dependency_lock_hash": parent.dependency_lock_hash,
            "model_id": parent.model_id,
            "model_revision": parent.model_revision,
            "run_dir": str(parent.run_dir),
            "run_id": parent.run_id,
            "seed": parent.seed,
        },
        "reward_mode": identity.reward_mode,
        "run_dir": str(identity.run_dir),
        "run_id": identity.run_id,
        "seed": identity.seed,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{identity.checkpoint_dir}#identity={digest}"


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


def _load_torch_runtime() -> ModuleType:
    try:
        return importlib.import_module("torch")
    except ImportError:
        raise GRPOTrainingError("PyTorch training runtime is unavailable; run make install-train") from None


def validate_grpo_training_hardware(config: GRPOTrainingConfig) -> None:
    """Fail before model loading unless a compatible training-class CUDA GPU is available."""
    torch_runtime = _load_torch_runtime()
    try:
        if not bool(torch_runtime.cuda.is_available()):
            raise GRPOTrainingError("GRPO training requires a CUDA-capable 24GB-class GPU")
        total_memory = float(torch_runtime.cuda.get_device_properties(0).total_memory) / (1024**3)
        required_memory = max(config.min_cuda_memory_gb, _MIN_TRAINING_CUDA_MEMORY_GB)
        if total_memory < required_memory:
            raise GRPOTrainingError(
                f"GRPO training requires at least {required_memory:g} GiB CUDA memory; detected {total_memory:.1f} GiB"
            )
        if config.bf16 and not bool(torch_runtime.cuda.is_bf16_supported(including_emulation=False)):
            raise GRPOTrainingError("configured bf16 training requires native CUDA BF16 support")
    except GRPOTrainingError:
        raise
    except Exception as error:
        raise GRPOTrainingError(f"could not validate CUDA training hardware: {type(error).__name__}") from None


def _load_grpo_runtime() -> _GRPORuntime:
    """Lazy-load and verify the exact pinned TRL/Open-R1/PEFT runtime surface."""
    for distribution, expected in _RUNTIME_VERSIONS.items():
        try:
            actual = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            raise GRPOTrainingError(f"{distribution} is unavailable; run make install-train") from None
        if actual != expected:
            raise GRPOTrainingError(f"{distribution} must be exactly {expected}, found {actual}")
    try:
        peft_runtime = importlib.import_module("peft")
        trl_runtime = importlib.import_module("trl")
        configs_runtime = import_open_r1_module("open_r1.configs")
        model_runtime = import_open_r1_module("open_r1.utils.model_utils")
        return _GRPORuntime(
            model_config_type=trl_runtime.ModelConfig,
            training_config_type=configs_runtime.GRPOConfig,
            trainer_type=trl_runtime.GRPOTrainer,
            get_peft_config=trl_runtime.get_peft_config,
            get_tokenizer=model_runtime.get_tokenizer,
            get_model=model_runtime.get_model,
            peft_config_type=peft_runtime.PeftConfig,
            peft_model_type=peft_runtime.PeftModel,
        )
    except (ImportError, AttributeError) as error:
        raise GRPOTrainingError(f"pinned GRPO runtime contract is unavailable: {type(error).__name__}") from None


def _runtime_arguments(
    config: GRPOTrainingConfig,
    *,
    checkpoint_dir: Path,
    parent_sft: SFTCheckpointIdentity,
    seed: int,
    runtime: _GRPORuntime,
) -> tuple[Any, Any]:
    """Map frozen project settings to pinned TRL/Open-R1 argument objects."""
    dtype = "bfloat16" if config.bf16 else "float16"
    try:
        model_args = runtime.model_config_type(
            model_name_or_path=parent_sft.model_id,
            model_revision=parent_sft.model_revision or "main",
            torch_dtype=dtype,
            trust_remote_code=False,
            use_peft=True,
            lora_r=config.lora_r,
            lora_alpha=config.lora_alpha,
            lora_dropout=config.lora_dropout,
            lora_target_modules=None,
            load_in_4bit=False,
            load_in_8bit=False,
        )
        training_args = runtime.training_config_type(
            output_dir=str(checkpoint_dir),
            run_name=config.run_name,
            do_train=True,
            do_eval=False,
            eval_strategy="no",
            num_generations=config.num_generations,
            max_prompt_length=config.max_prompt_length,
            max_completion_length=config.max_completion_length,
            per_device_train_batch_size=config.per_device_train_batch_size,
            gradient_accumulation_steps=config.gradient_accumulation_steps,
            learning_rate=config.learning_rate,
            num_train_epochs=config.num_train_epochs,
            max_steps=config.max_steps,
            warmup_ratio=config.warmup_ratio,
            lr_scheduler_type=config.lr_scheduler_type,
            temperature=config.temperature,
            top_p=config.top_p,
            beta=config.beta,
            bf16=config.bf16,
            fp16=config.fp16,
            gradient_checkpointing=config.gradient_checkpointing,
            logging_steps=config.logging_steps,
            save_strategy="steps",
            save_steps=config.save_steps,
            seed=seed,
            data_seed=seed,
            use_vllm=False,
            report_to=[],
            push_to_hub=False,
        )
    except ValueError:
        raise GRPOTrainingError("pinned GRPO argument constructor rejected the resolved config") from None
    return model_args, training_args


def _load_merged_sft_policy(
    *,
    parent_sft: SFTCheckpointIdentity,
    model_args: Any,
    training_args: Any,
    runtime: _GRPORuntime,
) -> Any:
    """Load base A, attach completed B read-only, then safe-merge B before GRPO LoRA."""
    try:
        adapter_config = runtime.peft_config_type.from_pretrained(str(parent_sft.checkpoint_dir))
    except Exception as error:
        raise GRPOTrainingError(f"could not load parent SFT adapter config: {type(error).__name__}") from None
    if getattr(adapter_config, "base_model_name_or_path", None) != parent_sft.model_id:
        raise GRPOTrainingError("parent SFT adapter base model identity does not match the completed SFT run")
    adapter_revision = getattr(adapter_config, "revision", None)
    if adapter_revision is not None and adapter_revision != parent_sft.model_revision:
        raise GRPOTrainingError("parent SFT adapter revision does not match the completed SFT run")
    try:
        base_model = runtime.get_model(model_args, training_args)
        parent_policy = runtime.peft_model_type.from_pretrained(
            base_model,
            str(parent_sft.checkpoint_dir),
            is_trainable=False,
            config=adapter_config,
        )
        merge = getattr(parent_policy, "merge_and_unload", None)
        if not callable(merge):
            raise GRPOTrainingError("parent SFT PEFT instance does not provide merge_and_unload")
        return merge(safe_merge=True)
    except GRPOTrainingError:
        raise
    except Exception as error:
        raise GRPOTrainingError(f"could not construct merged SFT policy: {type(error).__name__}") from None


def _resolved_config_mapping(config: GRPOTrainingConfig, *, effective_seed: int) -> dict[str, object]:
    resolved = asdict(config)
    resolved["dataset_path"] = str(config.dataset_path)
    resolved["piston_config"] = str(config.piston_config)
    resolved["seed"] = effective_seed
    resolved["use_peft"] = True
    resolved["use_vllm"] = False
    resolved["report_to"] = []
    resolved["push_to_hub"] = False
    resolved["trust_remote_code"] = False
    resolved["load_in_4bit"] = False
    resolved["load_in_8bit"] = False
    resolved["do_eval"] = False
    resolved["eval_strategy"] = "no"
    resolved["eval_steps_purpose"] = "external_checkpoint_evaluation_cadence"
    return resolved


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n")


def _append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    _append_lines(path, [_jsonl_line(value)])


def _file_hash(path: Path, *, description: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise GRPOTrainingError(f"could not read {description}: {type(error).__name__}") from None


def _config_hash(config: GRPOTrainingConfig, *, seed: int) -> str:
    encoded = json.dumps(
        _resolved_config_mapping(config, effective_seed=seed),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_run_dir(output_root: Path, run_name: str) -> Path:
    root = output_root.resolve(strict=False)
    if root == Path(root.anchor) or root == Path.cwd().resolve():
        raise GRPOTrainingError("output_root must be a dedicated non-root directory")
    run_dir = root / run_name
    if root not in run_dir.parents:
        raise GRPOTrainingError("resolved GRPO run directory escapes output_root")
    return run_dir


def _parent_identity_mapping(parent_sft: SFTCheckpointIdentity) -> dict[str, object]:
    return {
        "parent_sft_run_id": parent_sft.run_id,
        "parent_sft_model_id": parent_sft.model_id,
        "parent_sft_model_revision": parent_sft.model_revision,
        "parent_sft_dataset_hash": parent_sft.dataset_hash,
        "parent_sft_config_hash": parent_sft.config_hash,
        "parent_sft_dependency_lock_hash": parent_sft.dependency_lock_hash,
        "parent_sft_seed": parent_sft.seed,
        "parent_sft_run_path": str(parent_sft.run_dir),
        "parent_sft_checkpoint_path": str(parent_sft.checkpoint_dir),
    }


def _initialize_run(
    *,
    run_dir: Path,
    config: GRPOTrainingConfig,
    seed: int,
    parent_sft: SFTCheckpointIdentity,
    dataset_hash: str,
    config_hash: str,
    environment: Mapping[str, Any],
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "checkpoints").mkdir()
    started = datetime.now(timezone.utc).isoformat()
    packages = cast(Mapping[str, object], environment["packages"])
    run_metadata: dict[str, object] = {
        "run_id": config.run_name,
        "reward_mode": config.reward_mode,
        "timestamp": started,
        "git_commit": environment["project_commit"],
        "open_r1_commit": environment["open_r1_commit"],
        "python_version": environment["python_version"],
        "torch_version": packages["torch"],
        "cuda_version": environment["cuda_version"],
        "gpu_name": environment["gpu_name"],
        "gpu_count": environment["gpu_count"],
        "dependency_lock_hash": environment["dependency_lock_hash"],
        "dataset_hash": dataset_hash,
        "config_hash": config_hash,
        "seed": seed,
        "seed_override": None if seed == config.seed else {"config": config.seed, "cli": seed},
        **_parent_identity_mapping(parent_sft),
        "resume_from_checkpoint": None,
        "command": "code-verifier train-grpo",
        "start_time": started,
        "end_time": None,
        "gpu_hours": 0.0,
        "status": "running",
    }
    _atomic_write(
        run_dir / "resolved_config.yaml",
        yaml.safe_dump(_resolved_config_mapping(config, effective_seed=seed), sort_keys=True, allow_unicode=True),
    )
    _write_json(run_dir / "environment.json", environment)
    _write_json(run_dir / "run.json", run_metadata)
    for name in (
        "metrics.jsonl",
        "rollouts.jsonl",
        "rewards.jsonl",
        "group_metrics.jsonl",
        "stdout.log",
        "stderr.log",
    ):
        (run_dir / name).touch(exist_ok=False)
    return run_metadata


def _resolve_resume_checkpoint(run_dir: Path, requested: Path) -> tuple[Path, str]:
    try:
        resolved_run = run_dir.resolve(strict=True)
        checkpoint_root = (resolved_run / "checkpoints").resolve(strict=True)
        resolved_checkpoint = requested.resolve(strict=True)
    except OSError:
        raise GRPOTrainingError("resume_from_checkpoint must be an existing checkpoint directory") from None
    if (
        not resolved_checkpoint.is_dir()
        or resolved_checkpoint.parent != checkpoint_root
        or re.fullmatch(r"checkpoint-[1-9][0-9]*", resolved_checkpoint.name) is None
    ):
        raise GRPOTrainingError("resume_from_checkpoint must be a checkpoint-* directory from the same GRPO run")
    return resolved_checkpoint, resolved_checkpoint.relative_to(resolved_run).as_posix()


def _validate_resume_run(
    *,
    run_dir: Path,
    config: GRPOTrainingConfig,
    seed: int,
    parent_sft: SFTCheckpointIdentity,
    dataset_hash: str,
    config_hash: str,
    environment: Mapping[str, Any],
    resume_source: str,
) -> dict[str, object]:
    try:
        value = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise GRPOTrainingError("existing GRPO run metadata is unreadable") from None
    if not isinstance(value, dict):
        raise GRPOTrainingError("existing GRPO run metadata is invalid")
    packages = cast(Mapping[str, object], environment["packages"])
    expected: dict[str, object] = {
        "run_id": config.run_name,
        "reward_mode": config.reward_mode,
        "dataset_hash": dataset_hash,
        "config_hash": config_hash,
        "seed": seed,
        "git_commit": environment["project_commit"],
        "open_r1_commit": environment["open_r1_commit"],
        "dependency_lock_hash": environment["dependency_lock_hash"],
        "python_version": environment["python_version"],
        "torch_version": packages["torch"],
        "cuda_version": environment["cuda_version"],
        "gpu_name": environment["gpu_name"],
        "gpu_count": environment["gpu_count"],
        **_parent_identity_mapping(parent_sft),
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise GRPOTrainingError("existing GRPO run identity does not match the requested resume")
    if {path.name for path in run_dir.iterdir()} != _GRPO_RUN_LAYOUT:
        raise GRPOTrainingError("existing GRPO run does not match the strict artifact layout")
    if value.get("status") not in {"running", "failed"}:
        raise GRPOTrainingError("only an interrupted or failed GRPO run may be resumed")
    previous_gpu_hours = value.get("gpu_hours")
    if (
        isinstance(previous_gpu_hours, bool)
        or not isinstance(previous_gpu_hours, int | float)
        or not math.isfinite(float(previous_gpu_hours))
        or float(previous_gpu_hours) < 0.0
    ):
        raise GRPOTrainingError("existing GRPO run has invalid cumulative gpu_hours")
    value["status"] = "running"
    value["end_time"] = None
    value["resume_from_checkpoint"] = resume_source
    _write_json(run_dir / "run.json", value)
    return cast(dict[str, object], value)


def _append_trainer_metrics(path: Path, log_history: object) -> None:
    if not isinstance(log_history, list):
        raise GRPOTrainingError("GRPO trainer state must provide log_history")
    for entry in log_history:
        if not isinstance(entry, Mapping):
            raise GRPOTrainingError("GRPO trainer log history entries must be mappings")
        scalars: dict[str, object] = {"record_type": "trainer"}
        for key, value in entry.items():
            if not isinstance(key, str):
                raise GRPOTrainingError("GRPO trainer metric names must be strings")
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            number = float(value)
            if not math.isfinite(number):
                raise GRPOTrainingError("GRPO trainer metrics must be finite")
            scalars[key] = number
        if len(scalars) > 1:
            _append_jsonl(path, scalars)


def run_grpo_training(
    public_config: GRPOTrainingConfig,
    hidden_config: GRPOTrainingConfig,
    *,
    reward_mode: str,
    public_sft_run_dir: Path,
    hidden_sft_run_dir: Path,
    output_root: Path,
    seed: int,
    executor: CodeExecutor,
    resume_from_checkpoint: Path | None = None,
) -> GRPOTrainingSummary:
    """Preflight one fair C/D pair, then run the selected reward mode."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise GRPOTrainingError("seed must be an integer")
    validate_grpo_config_pair(public_config, hidden_config)
    if reward_mode not in {"public", "hidden"}:
        raise GRPOTrainingError("reward_mode must select public or hidden from the validated pair")
    config = public_config if reward_mode == "public" else hidden_config
    validate_grpo_training_hardware(config)
    public_parent_sft = load_completed_sft_checkpoint(public_sft_run_dir)
    hidden_parent_sft = load_completed_sft_checkpoint(hidden_sft_run_dir)
    if public_parent_sft != hidden_parent_sft:
        raise GRPOTrainingError("Public and Hidden GRPO runs must use the same completed SFT B identity")
    public_records = load_training_artifact(public_config.dataset_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden_records = load_training_artifact(hidden_config.dataset_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
    validate_grpo_artifact_pair(public_records, hidden_records)
    parent_sft = public_parent_sft
    records = public_records if reward_mode == "public" else hidden_records
    run_dir = _safe_run_dir(output_root, config.run_name)
    checkpoint_dir = run_dir / "checkpoints"
    dataset_hash = _file_hash(config.dataset_path, description="GRPO dataset")
    config_hash = _config_hash(config, seed=seed)
    environment = collect_environment()
    resume_path: str | None = None
    if resume_from_checkpoint is not None:
        if not run_dir.is_dir():
            raise GRPOTrainingError("resume requires an existing GRPO run directory")
        resolved_resume, resume_source = _resolve_resume_checkpoint(run_dir, resume_from_checkpoint)
        resume_path = str(resolved_resume)
        run_metadata = _validate_resume_run(
            run_dir=run_dir,
            config=config,
            seed=seed,
            parent_sft=parent_sft,
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            environment=environment,
            resume_source=resume_source,
        )
    else:
        if run_dir.exists():
            raise GRPOTrainingError("GRPO run directory already exists; explicit resume is required")
        try:
            run_metadata = _initialize_run(
                run_dir=run_dir,
                config=config,
                seed=seed,
                parent_sft=parent_sft,
                dataset_hash=dataset_hash,
                config_hash=config_hash,
                environment=environment,
            )
        except Exception:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise

    previous_gpu_hours = float(cast(int | float, run_metadata["gpu_hours"]))
    started = time.perf_counter()
    try:
        train_dataset = build_grpo_dataset(records, reward_mode=config.reward_mode)
        runtime = _load_grpo_runtime()
        model_args, training_args = _runtime_arguments(
            config,
            checkpoint_dir=checkpoint_dir,
            parent_sft=parent_sft,
            seed=seed,
            runtime=runtime,
        )
        tokenizer = runtime.get_tokenizer(model_args, training_args)
        model = _load_merged_sft_policy(
            parent_sft=parent_sft,
            model_args=model_args,
            training_args=training_args,
            runtime=runtime,
        )
        reward_callback = build_grpo_reward_callback(
            reward_mode=config.reward_mode,
            executor=executor,
            rollout_log_path=run_dir / "rollouts.jsonl",
            reward_log_path=run_dir / "rewards.jsonl",
            group_metrics_log_path=run_dir / "group_metrics.jsonl",
            num_generations=config.num_generations,
            max_completion_length=config.max_completion_length,
        )
        trainer = runtime.trainer_type(
            model=model,
            reward_funcs=reward_callback,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=None,
            processing_class=tokenizer,
            peft_config=runtime.get_peft_config(model_args),
        )
        train_result = trainer.train(resume_from_checkpoint=resume_path)
        raw_loss = getattr(train_result, "metrics", {}).get("train_loss")
        if isinstance(raw_loss, bool) or not isinstance(raw_loss, int | float) or not math.isfinite(float(raw_loss)):
            raise GRPOTrainingError("GRPO training must produce a finite train_loss")
        train_loss = float(raw_loss)
        trainer.save_state()
        trainer.save_model(str(checkpoint_dir))
        trainer_state = getattr(trainer, "state", None)
        _append_trainer_metrics(run_dir / "metrics.jsonl", getattr(trainer_state, "log_history", None))
        attempt_gpu_hours = (time.perf_counter() - started) / 3600.0
        gpu_hours = previous_gpu_hours + attempt_gpu_hours
        _append_jsonl(
            run_dir / "metrics.jsonl",
            {
                "record_type": "summary",
                "train_loss": train_loss,
                "train_samples": len(train_dataset),
                "attempt_gpu_hours": attempt_gpu_hours,
                "gpu_hours": gpu_hours,
            },
        )
        with (run_dir / "stdout.log").open("a", encoding="utf-8") as handle:
            handle.write(f"completed train_samples={len(train_dataset)} reward_mode={config.reward_mode}\n")
        run_metadata["status"] = "completed"
        run_metadata["end_time"] = datetime.now(timezone.utc).isoformat()
        run_metadata["gpu_hours"] = gpu_hours
        _write_json(run_dir / "run.json", run_metadata)
        return GRPOTrainingSummary(
            run_dir=run_dir,
            checkpoint_dir=checkpoint_dir,
            reward_mode=config.reward_mode,
            train_loss=train_loss,
            train_samples=len(train_dataset),
            gpu_hours=gpu_hours,
        )
    except Exception as error:
        gpu_hours = previous_gpu_hours + (time.perf_counter() - started) / 3600.0
        run_metadata["status"] = "failed"
        run_metadata["end_time"] = datetime.now(timezone.utc).isoformat()
        run_metadata["gpu_hours"] = gpu_hours
        _write_json(run_dir / "run.json", run_metadata)
        with (run_dir / "stderr.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{type(error).__name__}\n")
        raise
