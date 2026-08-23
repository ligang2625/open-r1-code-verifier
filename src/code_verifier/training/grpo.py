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
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from types import MethodType, ModuleType
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
from code_verifier.execution.base import CodeExecutor, ExecutionResult, ExecutionStatus
from code_verifier.rewards.common import RewardContractError, compute_code_rewards
from code_verifier.training.grpo_data import build_grpo_dataset
from code_verifier.training.open_r1_adapter import import_open_r1_module
from code_verifier.training.sft import (
    SFTCheckpointIdentity,
    SFTTrainingError,
    _without_unconfigured_deepspeed_backend,
    load_completed_sft_checkpoint,
)


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
    paired_definition_sha256: str
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
_GRPO_STREAM_LOG_NAMES = ("rollouts.jsonl", "rewards.jsonl", "group_metrics.jsonl")
_GRPO_LOG_STATE_FILENAME = "code_verifier_log_state.json"
_GRPO_RECOVERY_HISTORY_DIR = "recovery-history"
_GRPO_LOG_STATE_VERSION = 1
_PAIR_SCHEMA_VERSION = 2
_GPU_HOURS_SEMANTICS = (
    "attempt wall time in hours multiplied by gpu_count_used; includes in-process paired data validation, "
    "model load, train, and save"
)


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

    adapter_paths = {name: checkpoint_dir / name for name in ("adapter_config.json", "adapter_model.safetensors")}
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
        paired_definition_sha256=_checkpoint_identity_hash(
            metadata_value.get("paired_definition_sha256"), field_name="paired_definition_sha256"
        ),
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
        "paired_definition_sha256": identity.paired_definition_sha256,
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


def _decode_test_payload_batch(value: object, *, field_name: str) -> list[list[dict[str, object]]]:
    _batch_length(value, field_name=field_name)
    batch = cast(Sequence[object], value)
    decoded_batch: list[list[dict[str, object]]] = []
    for item_index, item in enumerate(batch):
        if isinstance(item, str | bytes | bytearray | Mapping) or not isinstance(item, Sequence) or not item:
            raise GRPOTrainingError(f"{field_name}[{item_index}] must be a non-empty sequence")
        decoded_tests: list[dict[str, object]] = []
        for test_index, encoded in enumerate(cast(Sequence[object], item)):
            if isinstance(encoded, Mapping):
                parsed = dict(encoded)
            elif isinstance(encoded, str):
                try:
                    parsed = json.loads(encoded)
                except json.JSONDecodeError:
                    raise GRPOTrainingError(
                        f"{field_name}[{item_index}][{test_index}] must contain valid JSON"
                    ) from None
            else:
                raise GRPOTrainingError(
                    f"{field_name}[{item_index}][{test_index}] must be encoded JSON text or a test mapping"
                )
            if not isinstance(parsed, dict) or set(parsed) != {"input", "expected"}:
                raise GRPOTrainingError(
                    f"{field_name}[{item_index}][{test_index}] must decode to one exact test mapping"
                )
            decoded_tests.append(cast(dict[str, object], parsed))
        decoded_batch.append(decoded_tests)
    return decoded_batch


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


class _TrainingExecutorCircuitBreaker:
    """Stop repeated remote executor calls after the first infrastructure failure in one training attempt."""

    def __init__(self, executor: CodeExecutor) -> None:
        self._executor = executor
        self._tripped = False

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        if self._tripped:
            raise RuntimeError("GRPO training executor circuit breaker is open")
        try:
            result = self._executor.execute(
                code,
                function_name,
                tests,
                timeout_seconds,
                memory_limit_mb,
            )
        except Exception:
            self._tripped = True
            raise
        if result.status is ExecutionStatus.SANDBOX_ERROR:
            self._tripped = True
        return result


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
    training_executor = _TrainingExecutorCircuitBreaker(executor)

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

        selected_field = "visible_tests" if reward_mode == "public" else "train_hidden_tests"
        selected_tests = _decode_test_payload_batch(columns[selected_field], field_name=selected_field)
        try:
            rewards, component_records = compute_code_rewards(
                completions,
                selected_tests,
                columns["function_name"],
                columns["metadata"],
                training_executor,
                reward_mode,
            )
        except RewardContractError as error:
            raise GRPOTrainingError(str(error)) from None
        if len(rewards) != batch_size or len(component_records) != batch_size:
            raise GRPOTrainingError("GRPO reward core returned a misaligned batch")
        if any(not math.isfinite(reward) for reward in rewards):
            raise GRPOTrainingError("GRPO rewards must be finite")
        infrastructure_failure_count = sum(
            record.get("infrastructure_failure") is True for record in component_records
        )

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
        if infrastructure_failure_count:
            raise GRPOTrainingError(
                "GRPO reward execution infrastructure failure in "
                f"{infrastructure_failure_count}/{batch_size} completions; aborting before optimizer update"
            )
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


def _install_grpo_runtime_telemetry(trainer: Any) -> None:
    """Install timing hooks and disable checkpointing only for inference-only GRPO work."""
    required = (
        "_generate_and_score_completions",
        "_get_per_token_logps",
        "training_step",
        "_maybe_log_save_evaluate",
        "_metrics",
        "accelerator",
        "model",
        "model_wrapped",
        "args",
        "state",
    )
    if any(not hasattr(trainer, name) for name in required):
        return

    original_rollout = trainer._generate_and_score_completions
    original_logps = trainer._get_per_token_logps
    original_training_step = trainer.training_step
    original_maybe_log = trainer._maybe_log_save_evaluate
    torch_runtime = _load_torch_runtime()
    step_started_at: float | None = None
    last_timed_global_step = int(getattr(trainer.state, "global_step", 0) or 0)
    no_grad_logps_runtime_seconds = 0.0
    no_grad_logps_calls = 0

    def timed_rollout(self: Any, inputs: object) -> object:
        mode = "train" if self.model.training else "eval"
        unwrapped_model = self.accelerator.unwrap_model(self.model_wrapped)
        original_generate = getattr(unwrapped_model, "generate", None)
        if not callable(original_generate):
            raise GRPOTrainingError("pinned GRPO model does not provide callable generation")
        instance_dict = getattr(unwrapped_model, "__dict__", {})
        had_instance_generate = isinstance(instance_dict, dict) and "generate" in instance_dict
        previous_instance_generate = instance_dict.get("generate") if had_instance_generate else None

        def generate_without_checkpointing(*args: object, **kwargs: object) -> object:
            was_checkpointing = bool(getattr(unwrapped_model, "is_gradient_checkpointing", False))
            if was_checkpointing:
                disable = getattr(unwrapped_model, "gradient_checkpointing_disable", None)
                enable = getattr(unwrapped_model, "gradient_checkpointing_enable", None)
                if not callable(disable) or not callable(enable):
                    raise GRPOTrainingError("pinned GRPO model cannot safely toggle gradient checkpointing")
                disable()
            generation_started = time.perf_counter()
            try:
                return original_generate(*args, **kwargs)
            finally:
                generation_elapsed = time.perf_counter() - generation_started
                if was_checkpointing:
                    unwrapped_model.gradient_checkpointing_enable()
                if not math.isfinite(generation_elapsed) or generation_elapsed < 0.0:
                    raise GRPOTrainingError("GRPO generation runtime must be finite and non-negative")
                self._metrics[mode]["generation_runtime_seconds"].append(generation_elapsed)

        unwrapped_model.generate = generate_without_checkpointing
        started = time.perf_counter()
        try:
            return original_rollout(inputs)
        finally:
            elapsed = time.perf_counter() - started
            if had_instance_generate:
                unwrapped_model.generate = previous_instance_generate
            else:
                with suppress(AttributeError):
                    del unwrapped_model.generate
            if not math.isfinite(elapsed) or elapsed < 0.0:
                raise GRPOTrainingError("GRPO rollout runtime must be finite and non-negative")
            self._metrics[mode]["rollout_runtime_seconds"].append(elapsed)

    def timed_logps(self: Any, model: Any, *args: object, **kwargs: object) -> object:
        nonlocal no_grad_logps_calls, no_grad_logps_runtime_seconds
        if bool(torch_runtime.is_grad_enabled()):
            return original_logps(model, *args, **kwargs)
        was_checkpointing = bool(getattr(model, "is_gradient_checkpointing", False))
        if was_checkpointing:
            disable = getattr(model, "gradient_checkpointing_disable", None)
            enable = getattr(model, "gradient_checkpointing_enable", None)
            if not callable(disable) or not callable(enable):
                raise GRPOTrainingError("pinned GRPO model cannot safely toggle inference gradient checkpointing")
            disable()
        started = time.perf_counter()
        try:
            return original_logps(model, *args, **kwargs)
        finally:
            elapsed = time.perf_counter() - started
            if was_checkpointing:
                model.gradient_checkpointing_enable()
            if not math.isfinite(elapsed) or elapsed < 0.0:
                raise GRPOTrainingError("GRPO no-grad log-prob runtime must be finite and non-negative")
            if self.model.training:
                no_grad_logps_runtime_seconds += elapsed
                no_grad_logps_calls += 1
            else:
                self._metrics["eval"]["no_grad_logps_runtime_seconds"].append(elapsed)
                self._metrics["eval"]["no_grad_logps_calls"].append(1.0)

    def timed_training_step(self: Any, *args: object, **kwargs: object) -> object:
        nonlocal step_started_at
        if step_started_at is None:
            step_started_at = time.perf_counter()
        try:
            return original_training_step(*args, **kwargs)
        except BaseException:
            step_started_at = None
            raise

    def timed_maybe_log(self: Any, *args: object, **kwargs: object) -> object:
        nonlocal last_timed_global_step, no_grad_logps_calls, no_grad_logps_runtime_seconds, step_started_at
        raw_global_step = getattr(self.state, "global_step", None)
        if (
            step_started_at is not None
            and isinstance(raw_global_step, int)
            and raw_global_step > last_timed_global_step
        ):
            elapsed = time.perf_counter() - step_started_at
            step_started_at = None
            if not math.isfinite(elapsed) or elapsed < 0.0:
                raise GRPOTrainingError("GRPO step runtime must be finite and non-negative")
            self._metrics["train"]["step_runtime_seconds"].append(elapsed)
            self._metrics["train"]["no_grad_logps_runtime_seconds"].append(no_grad_logps_runtime_seconds)
            self._metrics["train"]["no_grad_logps_calls"].append(float(no_grad_logps_calls))
            no_grad_logps_runtime_seconds = 0.0
            no_grad_logps_calls = 0
            last_timed_global_step = raw_global_step
        return original_maybe_log(*args, **kwargs)

    trainer._generate_and_score_completions = MethodType(timed_rollout, trainer)
    trainer._get_per_token_logps = MethodType(timed_logps, trainer)
    trainer.training_step = MethodType(timed_training_step, trainer)
    trainer._maybe_log_save_evaluate = MethodType(timed_maybe_log, trainer)


def _install_grpo_checkpoint_log_snapshots(trainer: Any, *, run_dir: Path) -> None:
    """Attach one post-save hook that binds canonical streaming logs to each Trainer checkpoint."""
    original_save = getattr(trainer, "_save_checkpoint", None)
    if not callable(original_save):
        raise GRPOTrainingError("pinned GRPO trainer does not expose checkpoint save hook")
    args = getattr(trainer, "args", None)
    output_dir = getattr(args, "output_dir", None)
    if not isinstance(output_dir, str) or not output_dir:
        raise GRPOTrainingError("pinned GRPO trainer output_dir is unavailable")
    try:
        expected_root = (run_dir / "checkpoints").resolve(strict=True)
        actual_root = Path(output_dir).resolve(strict=True)
    except OSError:
        raise GRPOTrainingError("pinned GRPO trainer checkpoint root is unavailable") from None
    if actual_root != expected_root:
        raise GRPOTrainingError("pinned GRPO trainer checkpoint root differs from the GRPO run")

    def save_with_log_snapshot(self: Any, model: object, trial: object) -> object:
        result = original_save(model, trial)
        raw_step = getattr(self.state, "global_step", None)
        if isinstance(raw_step, bool) or not isinstance(raw_step, int) or raw_step <= 0:
            raise GRPOTrainingError("pinned GRPO trainer saved a checkpoint without a valid global_step")
        checkpoint_dir = expected_root / f"checkpoint-{raw_step}"
        _write_grpo_log_checkpoint_state(run_dir=run_dir, checkpoint_dir=checkpoint_dir, global_step=raw_step)
        return result

    trainer._save_checkpoint = MethodType(save_with_log_snapshot, trainer)


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
            skip_memory_metrics=False,
            logging_nan_inf_filter=False,
            save_total_limit=None,
            save_only_model=False,
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


def _stream_log_file_state(path: Path, *, limit_bytes: int | None = None) -> dict[str, object]:
    """Return a finite JSONL prefix identity for one canonical streaming evidence file."""
    if not path.is_file() or path.is_symlink():
        raise GRPOTrainingError("GRPO streaming evidence file is missing or unsafe")
    try:
        size = path.stat().st_size
        if limit_bytes is None:
            selected_size = size
        else:
            if isinstance(limit_bytes, bool) or not isinstance(limit_bytes, int) or limit_bytes < 0:
                raise GRPOTrainingError("GRPO checkpoint log boundary is invalid")
            if size < limit_bytes:
                raise GRPOTrainingError("GRPO streaming evidence is shorter than its checkpoint boundary")
            selected_size = limit_bytes
        digest = hashlib.sha256()
        line_count = 0
        remaining = selected_size
        last_byte = b""
        with path.open("rb") as handle:
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise GRPOTrainingError("GRPO streaming evidence ended before its checkpoint boundary")
                digest.update(chunk)
                line_count += chunk.count(b"\n")
                last_byte = chunk[-1:]
                remaining -= len(chunk)
        if selected_size and last_byte != b"\n":
            raise GRPOTrainingError("GRPO checkpoint log boundary does not end on a complete JSONL row")
        return {
            "size_bytes": selected_size,
            "line_count": line_count,
            "sha256": digest.hexdigest(),
        }
    except GRPOTrainingError:
        raise
    except OSError as error:
        raise GRPOTrainingError(f"could not read GRPO streaming evidence: {type(error).__name__}") from None


def _checkpoint_step(checkpoint_dir: Path) -> int:
    match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", checkpoint_dir.name)
    if match is None:
        raise GRPOTrainingError("GRPO checkpoint directory name is invalid")
    return int(match.group(1))


def _write_grpo_log_checkpoint_state(*, run_dir: Path, checkpoint_dir: Path, global_step: int) -> None:
    """Persist the exact streaming-log boundary that belongs to one Trainer checkpoint."""
    if isinstance(global_step, bool) or not isinstance(global_step, int) or global_step <= 0:
        raise GRPOTrainingError("GRPO checkpoint global_step is invalid")
    try:
        resolved_run = run_dir.resolve(strict=True)
        checkpoint_root = (resolved_run / "checkpoints").resolve(strict=True)
        resolved_checkpoint = checkpoint_dir.resolve(strict=True)
    except OSError:
        raise GRPOTrainingError("GRPO checkpoint log-state path is unavailable") from None
    if (
        resolved_checkpoint.parent != checkpoint_root
        or _checkpoint_step(resolved_checkpoint) != global_step
        or resolved_checkpoint.is_symlink()
    ):
        raise GRPOTrainingError("GRPO checkpoint log-state path does not match trainer global_step")
    logs = {name: _stream_log_file_state(resolved_run / name) for name in _GRPO_STREAM_LOG_NAMES}
    _write_json(
        resolved_checkpoint / _GRPO_LOG_STATE_FILENAME,
        {
            "version": _GRPO_LOG_STATE_VERSION,
            "global_step": global_step,
            "logs": logs,
        },
    )


def _validate_resume_log_checkpoint(run_dir: Path, checkpoint_dir: Path) -> dict[str, object]:
    """Read-only validation that current canonical logs contain the selected checkpoint prefix exactly."""
    try:
        resolved_run = run_dir.resolve(strict=True)
        resolved_checkpoint = checkpoint_dir.resolve(strict=True)
        state_path = resolved_checkpoint / _GRPO_LOG_STATE_FILENAME
        if not state_path.is_file() or state_path.is_symlink():
            raise GRPOTrainingError("resume checkpoint is missing canonical GRPO log-state evidence")
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except GRPOTrainingError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise GRPOTrainingError("resume checkpoint canonical GRPO log-state evidence is unreadable") from None
    if not isinstance(value, dict) or set(value) != {"version", "global_step", "logs"}:
        raise GRPOTrainingError("resume checkpoint canonical GRPO log-state schema is invalid")
    step = _checkpoint_step(resolved_checkpoint)
    if value.get("version") != _GRPO_LOG_STATE_VERSION or value.get("global_step") != step:
        raise GRPOTrainingError("resume checkpoint canonical GRPO log-state identity is invalid")
    raw_logs = value.get("logs")
    if not isinstance(raw_logs, Mapping) or set(raw_logs) != set(_GRPO_STREAM_LOG_NAMES):
        raise GRPOTrainingError("resume checkpoint canonical GRPO log-state files are invalid")
    normalized_logs: dict[str, dict[str, object]] = {}
    for name in _GRPO_STREAM_LOG_NAMES:
        raw_state = raw_logs[name]
        if not isinstance(raw_state, Mapping) or set(raw_state) != {"size_bytes", "line_count", "sha256"}:
            raise GRPOTrainingError("resume checkpoint canonical GRPO log-state record is invalid")
        size_bytes = raw_state.get("size_bytes")
        line_count = raw_state.get("line_count")
        digest = raw_state.get("sha256")
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or isinstance(line_count, bool)
            or not isinstance(line_count, int)
            or line_count < 0
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise GRPOTrainingError("resume checkpoint canonical GRPO log-state values are invalid")
        expected = {"size_bytes": size_bytes, "line_count": line_count, "sha256": digest}
        actual = _stream_log_file_state(resolved_run / name, limit_bytes=size_bytes)
        if actual != expected:
            raise GRPOTrainingError("canonical GRPO streaming evidence prefix differs from resume checkpoint")
        normalized_logs[name] = expected
    return {"version": _GRPO_LOG_STATE_VERSION, "global_step": step, "logs": normalized_logs}


def _copy_file_with_fsync(source: Path, destination: Path) -> None:
    try:
        with source.open("rb") as src, destination.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
    except OSError as error:
        raise GRPOTrainingError(f"could not archive GRPO recovery evidence: {type(error).__name__}") from None


def _restore_stream_log_prefix(path: Path, *, size_bytes: int, staging_dir: Path) -> None:
    temporary: Path | None = None
    try:
        mode = path.stat().st_mode & 0o777
        with (
            path.open("rb") as source,
            tempfile.NamedTemporaryFile(
                mode="wb",
                dir=staging_dir,
                prefix=f".{path.name}.resume-",
                suffix=".tmp",
                delete=False,
            ) as destination,
        ):
            temporary = Path(destination.name)
            remaining = size_bytes
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise GRPOTrainingError("GRPO streaming evidence became shorter during resume restoration")
                destination.write(chunk)
                remaining -= len(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except GRPOTrainingError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise GRPOTrainingError(f"could not restore GRPO streaming evidence: {type(error).__name__}") from None


def _archive_future_grpo_checkpoints(
    *,
    run_dir: Path,
    selected_step: int,
    archive_dir: Path,
) -> list[str]:
    """Move every checkpoint newer than the selected resume point into preserved recovery history."""
    if isinstance(selected_step, bool) or not isinstance(selected_step, int) or selected_step <= 0:
        raise GRPOTrainingError("selected GRPO resume checkpoint step is invalid")
    try:
        checkpoint_root = (run_dir / "checkpoints").resolve(strict=True)
    except OSError:
        raise GRPOTrainingError("GRPO checkpoint root is unavailable during resume recovery") from None
    future_root = archive_dir / "superseded-future-checkpoints"
    archived: list[str] = []
    candidates: list[tuple[int, Path]] = []
    for candidate in checkpoint_root.glob("checkpoint-*"):
        match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", candidate.name)
        if match is None:
            continue
        step = int(match.group(1))
        if step <= selected_step:
            continue
        if candidate.is_symlink() or not candidate.is_dir():
            raise GRPOTrainingError("superseded future GRPO checkpoint path is unsafe")
        candidates.append((step, candidate))
    for _, candidate in sorted(candidates):
        future_root.mkdir(exist_ok=True)
        try:
            os.replace(candidate, future_root / candidate.name)
        except OSError as error:
            raise GRPOTrainingError(
                f"could not archive superseded future GRPO checkpoint: {type(error).__name__}"
            ) from None
        archived.append(candidate.name)
    return archived


def _archive_and_restore_grpo_logs(
    *,
    run_dir: Path,
    checkpoint_dir: Path,
    attempt_number: int,
) -> Path:
    """Archive a failed-attempt suffix, then restore canonical streaming logs to a checkpoint boundary."""
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int) or attempt_number < 2:
        raise GRPOTrainingError("GRPO resume attempt number is invalid")
    state = _validate_resume_log_checkpoint(run_dir, checkpoint_dir)
    step = cast(int, state["global_step"])
    target_logs = cast(dict[str, dict[str, object]], state["logs"])
    history_root = run_dir / "checkpoints" / _GRPO_RECOVERY_HISTORY_DIR
    history_root.mkdir(parents=False, exist_ok=True)
    archive = history_root / f"before-attempt-{attempt_number}-resume-checkpoint-{step}"
    if archive.exists():
        raise GRPOTrainingError("GRPO recovery archive already exists for this attempt")
    incomplete = Path(tempfile.mkdtemp(prefix=f".{archive.name}.incomplete-", dir=history_root))
    before_logs: dict[str, dict[str, object]] = {}
    manifest: dict[str, object] = {
        "version": 1,
        "attempt": attempt_number,
        "resume_checkpoint": checkpoint_dir.name,
        "global_step": step,
        "before_logs": before_logs,
        "restored_checkpoint_logs": target_logs,
        "superseded_future_checkpoints": [],
    }
    try:
        for name in _GRPO_STREAM_LOG_NAMES:
            source = run_dir / name
            before_logs[name] = _stream_log_file_state(source)
            _copy_file_with_fsync(source, incomplete / name)
        _write_json(incomplete / "manifest.json", manifest)
        os.replace(incomplete, archive)
    except Exception:
        shutil.rmtree(incomplete, ignore_errors=True)
        raise
    future_checkpoints = _archive_future_grpo_checkpoints(
        run_dir=run_dir,
        selected_step=step,
        archive_dir=archive,
    )
    manifest["superseded_future_checkpoints"] = future_checkpoints
    _write_json(archive / "manifest.json", manifest)
    for name in _GRPO_STREAM_LOG_NAMES:
        path = run_dir / name
        expected = target_logs[name]
        current = _stream_log_file_state(path)
        if current == expected:
            continue
        _restore_stream_log_prefix(
            path,
            size_bytes=cast(int, expected["size_bytes"]),
            staging_dir=history_root,
        )
        if _stream_log_file_state(path) != expected:
            raise GRPOTrainingError("GRPO streaming evidence restoration did not reach checkpoint boundary")
    return archive


def _config_hash(config: GRPOTrainingConfig, *, seed: int) -> str:
    encoded = json.dumps(
        _resolved_config_mapping(config, effective_seed=seed),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _paired_config_hash(config: GRPOTrainingConfig, *, seed: int) -> str:
    """Return a machine-portable config fingerprint for the C/D pair identity."""
    resolved = _resolved_config_mapping(config, effective_seed=seed)
    resolved["dataset_path"] = {
        "sha256": _file_hash(config.dataset_path, description=f"{config.reward_mode} GRPO dataset")
    }
    resolved["piston_config"] = {"sha256": _file_hash(config.piston_config, description="Piston config")}
    encoded = json.dumps(
        resolved,
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


def _portable_parent_identity_mapping(parent_sft: SFTCheckpointIdentity) -> dict[str, object]:
    """Return the semantic SFT identity without machine-local artifact paths."""
    value = _parent_identity_mapping(parent_sft)
    value.pop("parent_sft_run_path")
    value.pop("parent_sft_checkpoint_path")
    return value


def _paired_definition(
    public_config: GRPOTrainingConfig,
    hidden_config: GRPOTrainingConfig,
    *,
    seed: int,
    parent_sft: SFTCheckpointIdentity,
) -> tuple[str, dict[str, object]]:
    """Build one payload-free canonical identity for the complete C/D definition pair."""
    components: dict[str, object] = {
        "paired_definition_version": _PAIR_SCHEMA_VERSION,
        "paired_public_config_hash": _paired_config_hash(public_config, seed=seed),
        "paired_hidden_config_hash": _paired_config_hash(hidden_config, seed=seed),
        "paired_public_dataset_hash": _file_hash(public_config.dataset_path, description="Public GRPO dataset"),
        "paired_hidden_dataset_hash": _file_hash(hidden_config.dataset_path, description="Hidden GRPO dataset"),
    }
    canonical = {**components, "seed": seed, "parent_sft": _portable_parent_identity_mapping(parent_sft)}
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest(), components


def _gpu_count_used(environment: Mapping[str, Any]) -> int:
    available = environment.get("gpu_count")
    if isinstance(available, bool) or not isinstance(available, int) or available < 1:
        raise GRPOTrainingError("GRPO environment must report at least one GPU")
    return 1


def _attempt_gpu_hours_total(attempts: object) -> float:
    if not isinstance(attempts, list):
        raise GRPOTrainingError("GRPO run metadata has invalid attempt history")
    total = 0.0
    for index, value in enumerate(attempts, 1):
        if not isinstance(value, Mapping) or value.get("attempt") != index:
            raise GRPOTrainingError("GRPO run metadata has invalid attempt history")
        status = value.get("status")
        if status not in {"completed", "failed"}:
            raise GRPOTrainingError("GRPO run metadata has invalid attempt history")
        gpu_hours = value.get("gpu_hours")
        if (
            isinstance(gpu_hours, bool)
            or not isinstance(gpu_hours, int | float)
            or not math.isfinite(float(gpu_hours))
            or float(gpu_hours) < 0.0
        ):
            raise GRPOTrainingError("GRPO run metadata has invalid attempt history")
        total += float(gpu_hours)
    return total


def _begin_attempt(run_metadata: dict[str, object], *, resume_source: str | None) -> None:
    attempts = run_metadata.get("attempts")
    if not isinstance(attempts, list):
        raise GRPOTrainingError("GRPO run metadata has invalid attempt history")
    attempts.append(
        {
            "attempt": len(attempts) + 1,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
            "status": "running",
            "resume_from_checkpoint": resume_source,
            "gpu_hours": 0.0,
        }
    )
    run_metadata["status"] = "running"
    run_metadata["end_time"] = None
    run_metadata["resume_from_checkpoint"] = resume_source


def _finish_attempt(run_metadata: dict[str, object], *, status: str, attempt_gpu_hours: float) -> None:
    if status not in {"completed", "failed"} or not math.isfinite(attempt_gpu_hours) or attempt_gpu_hours < 0.0:
        raise GRPOTrainingError("GRPO attempt telemetry is invalid")
    attempts = run_metadata.get("attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
        raise GRPOTrainingError("GRPO run metadata has invalid attempt history")
    latest = cast(dict[str, object], attempts[-1])
    latest["status"] = status
    latest["end_time"] = datetime.now(timezone.utc).isoformat()
    latest["gpu_hours"] = attempt_gpu_hours
    cumulative = _attempt_gpu_hours_total(attempts)
    run_metadata["gpu_hours"] = cumulative
    run_metadata["status"] = status
    run_metadata["end_time"] = latest["end_time"]


def _reset_cuda_peak_memory() -> None:
    torch_runtime = _load_torch_runtime()
    if bool(torch_runtime.cuda.is_available()):
        torch_runtime.cuda.reset_peak_memory_stats(0)


def _peak_cuda_memory_bytes() -> tuple[int, int]:
    torch_runtime = _load_torch_runtime()
    if not bool(torch_runtime.cuda.is_available()):
        return 0, 0
    allocated = int(torch_runtime.cuda.max_memory_allocated(0))
    reserved = int(torch_runtime.cuda.max_memory_reserved(0))
    if allocated < 0 or reserved < 0:
        raise GRPOTrainingError("CUDA peak memory metrics must be non-negative")
    return allocated, reserved


def _initialize_run(
    *,
    run_dir: Path,
    config: GRPOTrainingConfig,
    seed: int,
    parent_sft: SFTCheckpointIdentity,
    dataset_hash: str,
    config_hash: str,
    paired_definition_sha256: str,
    paired_components: Mapping[str, object],
    environment: Mapping[str, Any],
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "checkpoints").mkdir()
    started = datetime.now(timezone.utc).isoformat()
    packages = cast(Mapping[str, object], environment["packages"])
    gpu_count_used = _gpu_count_used(environment)
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
        "gpu_count_used": gpu_count_used,
        "gpu_hours_semantics": _GPU_HOURS_SEMANTICS,
        "dependency_lock_hash": environment["dependency_lock_hash"],
        "dataset_hash": dataset_hash,
        "config_hash": config_hash,
        "paired_definition_sha256": paired_definition_sha256,
        **paired_components,
        "seed": seed,
        "seed_override": None if seed == config.seed else {"config": config.seed, "cli": seed},
        **_parent_identity_mapping(parent_sft),
        "resume_from_checkpoint": None,
        "command": "code-verifier train-grpo",
        "start_time": started,
        "end_time": None,
        "gpu_hours": 0.0,
        "attempts": [],
        "global_step": None,
        "peak_cuda_memory_allocated_bytes": 0,
        "peak_cuda_memory_reserved_bytes": 0,
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
    paired_definition_sha256: str,
    paired_components: Mapping[str, object],
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
        "paired_definition_sha256": paired_definition_sha256,
        **paired_components,
        "seed": seed,
        "git_commit": environment["project_commit"],
        "open_r1_commit": environment["open_r1_commit"],
        "dependency_lock_hash": environment["dependency_lock_hash"],
        "python_version": environment["python_version"],
        "torch_version": packages["torch"],
        "cuda_version": environment["cuda_version"],
        "gpu_name": environment["gpu_name"],
        "gpu_count": environment["gpu_count"],
        "gpu_count_used": _gpu_count_used(environment),
        "gpu_hours_semantics": _GPU_HOURS_SEMANTICS,
        **_parent_identity_mapping(parent_sft),
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise GRPOTrainingError("existing GRPO run identity does not match the requested resume")
    if {path.name for path in run_dir.iterdir()} != _GRPO_RUN_LAYOUT:
        raise GRPOTrainingError("existing GRPO run does not match the strict artifact layout")
    if value.get("status") != "failed":
        raise GRPOTrainingError("only a gracefully failed GRPO run may be resumed")
    previous_gpu_hours = value.get("gpu_hours")
    attempts_total = _attempt_gpu_hours_total(value.get("attempts"))
    if (
        isinstance(previous_gpu_hours, bool)
        or not isinstance(previous_gpu_hours, int | float)
        or not math.isfinite(float(previous_gpu_hours))
        or float(previous_gpu_hours) < 0.0
        or not math.isclose(float(previous_gpu_hours), attempts_total, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise GRPOTrainingError("existing GRPO run has invalid cumulative gpu_hours")
    return cast(dict[str, object], value)


def _trainer_metric_rows(log_history: object) -> list[dict[str, object]]:
    if not isinstance(log_history, list):
        raise GRPOTrainingError("GRPO trainer state must provide log_history")
    rows: list[dict[str, object]] = []
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
            rows.append(scalars)
    return rows


def _write_training_metrics(path: Path, *, log_history: object, summary: Mapping[str, object]) -> None:
    rows = [*_trainer_metric_rows(log_history), dict(summary)]
    content = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in rows
    )
    _atomic_write(path, content)


def _finite_numeric_mapping(value: object, *, context: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise GRPOTrainingError(f"{context} must be a mapping")
    scalars: dict[str, float] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str):
            raise GRPOTrainingError(f"{context} metric names must be strings")
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            continue
        number = float(raw_value)
        if not math.isfinite(number):
            raise GRPOTrainingError(f"{context} must contain only finite numeric metrics")
        scalars[key] = number
    return scalars


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
    paired_definition_sha256, paired_components = _paired_definition(
        public_config, hidden_config, seed=seed, parent_sft=parent_sft
    )
    records = public_records if reward_mode == "public" else hidden_records
    run_dir = _safe_run_dir(output_root, config.run_name)
    checkpoint_dir = run_dir / "checkpoints"
    dataset_hash = _file_hash(config.dataset_path, description="GRPO dataset")
    config_hash = _config_hash(config, seed=seed)
    environment = collect_environment()
    resume_path: str | None = None
    resume_source: str | None = None
    if resume_from_checkpoint is not None:
        if not run_dir.is_dir():
            raise GRPOTrainingError("resume requires an existing GRPO run directory")
        resolved_resume, resume_source = _resolve_resume_checkpoint(run_dir, resume_from_checkpoint)
        _validate_resume_log_checkpoint(run_dir, resolved_resume)
        resume_path = str(resolved_resume)
        run_metadata = _validate_resume_run(
            run_dir=run_dir,
            config=config,
            seed=seed,
            parent_sft=parent_sft,
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            paired_definition_sha256=paired_definition_sha256,
            paired_components=paired_components,
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
                paired_definition_sha256=paired_definition_sha256,
                paired_components=paired_components,
                environment=environment,
            )
        except Exception:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise

    gpu_count_used = cast(int, run_metadata["gpu_count_used"])
    _begin_attempt(run_metadata, resume_source=resume_source)
    _write_json(run_dir / "run.json", run_metadata)
    started = time.perf_counter()
    peak_reset = False
    try:
        if resume_path is not None:
            attempts = run_metadata.get("attempts")
            if not isinstance(attempts, list) or len(attempts) < 2:
                raise GRPOTrainingError("GRPO resume attempt history is invalid")
            recovery_archive = _archive_and_restore_grpo_logs(
                run_dir=run_dir,
                checkpoint_dir=Path(resume_path),
                attempt_number=len(attempts),
            )
            with (run_dir / "stdout.log").open("a", encoding="utf-8") as handle:
                handle.write(
                    f"restored canonical streaming logs from {resume_source}; archive={recovery_archive.name}\n"
                )
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
        _reset_cuda_peak_memory()
        peak_reset = True
        with _without_unconfigured_deepspeed_backend():
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
            _install_grpo_runtime_telemetry(trainer)
            _install_grpo_checkpoint_log_snapshots(trainer, run_dir=run_dir)
            train_result = trainer.train(resume_from_checkpoint=resume_path)
            raw_train_metrics = getattr(train_result, "metrics", {})
            if isinstance(raw_train_metrics, Mapping):
                raw_train_loss = raw_train_metrics.get("train_loss")
                if (
                    isinstance(raw_train_loss, int | float)
                    and not isinstance(raw_train_loss, bool)
                    and not math.isfinite(float(raw_train_loss))
                ):
                    raise GRPOTrainingError("GRPO training must produce a finite train_loss")
            train_metrics = _finite_numeric_mapping(
                raw_train_metrics,
                context="GRPO train result metrics",
            )
            raw_loss = train_metrics.get("train_loss")
            if raw_loss is None:
                raise GRPOTrainingError("GRPO training must produce a finite train_loss")
            train_loss = raw_loss
            trainer.save_state()
            trainer.save_model(str(checkpoint_dir))
        trainer_state = getattr(trainer, "state", None)
        raw_global_step = getattr(trainer_state, "global_step", None)
        if isinstance(raw_global_step, bool) or not isinstance(raw_global_step, int) or raw_global_step < 0:
            raise GRPOTrainingError("GRPO trainer state must provide a non-negative integer global_step")
        peak_allocated, peak_reserved = _peak_cuda_memory_bytes()
        attempt_gpu_hours = (time.perf_counter() - started) * gpu_count_used / 3600.0
        _finish_attempt(run_metadata, status="completed", attempt_gpu_hours=attempt_gpu_hours)
        gpu_hours = cast(float, run_metadata["gpu_hours"])
        run_metadata["global_step"] = raw_global_step
        run_metadata["peak_cuda_memory_allocated_bytes"] = peak_allocated
        run_metadata["peak_cuda_memory_reserved_bytes"] = peak_reserved
        summary_metrics: dict[str, object] = {
            "record_type": "summary",
            **train_metrics,
            "global_step": raw_global_step,
            "train_samples": len(train_dataset),
            "peak_cuda_memory_allocated_bytes": peak_allocated,
            "peak_cuda_memory_reserved_bytes": peak_reserved,
            "gpu_count_used": gpu_count_used,
            "attempt_gpu_hours": attempt_gpu_hours,
            "gpu_hours": gpu_hours,
        }
        _write_training_metrics(
            run_dir / "metrics.jsonl",
            log_history=getattr(trainer_state, "log_history", None),
            summary=summary_metrics,
        )
        with (run_dir / "stdout.log").open("a", encoding="utf-8") as handle:
            handle.write(f"completed train_samples={len(train_dataset)} reward_mode={config.reward_mode}\n")
        _write_json(run_dir / "run.json", run_metadata)
        return GRPOTrainingSummary(
            run_dir=run_dir,
            checkpoint_dir=checkpoint_dir,
            reward_mode=config.reward_mode,
            train_loss=train_loss,
            train_samples=len(train_dataset),
            gpu_hours=gpu_hours,
        )
    except BaseException as error:
        attempt_gpu_hours = (time.perf_counter() - started) * gpu_count_used / 3600.0
        if peak_reset:
            try:
                peak_allocated, peak_reserved = _peak_cuda_memory_bytes()
            except Exception:
                peak_allocated = peak_reserved = 0
        else:
            peak_allocated = peak_reserved = 0
        run_metadata["peak_cuda_memory_allocated_bytes"] = peak_allocated
        run_metadata["peak_cuda_memory_reserved_bytes"] = peak_reserved
        _finish_attempt(run_metadata, status="failed", attempt_gpu_hours=attempt_gpu_hours)
        _write_json(run_dir / "run.json", run_metadata)
        with (run_dir / "stderr.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{type(error).__name__}\n")
        raise
