"""Strict LoRA SFT configuration, runtime construction, and run artifacts."""

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
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import yaml

from code_verifier.config import ConfigError, load_yaml_mapping
from code_verifier.data.leakage_checks import TrainingArtifactKind, load_training_artifact
from code_verifier.environment import collect_environment
from code_verifier.execution.base import CodeExecutor
from code_verifier.training.open_r1_adapter import import_open_r1_module
from code_verifier.training.sft_data import build_sft_dataset


@dataclass(frozen=True)
class SFTTrainingConfig:
    """Resolved exact-schema LoRA SFT settings."""

    run_name: str
    model_id: str
    model_revision: str | None
    dataset_path: Path
    validation_dataset_path: Path | None
    piston_config: Path
    max_seq_length: int
    max_steps: int
    num_train_epochs: float
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    warmup_ratio: float
    lr_scheduler_type: str
    logging_steps: int
    save_strategy: str
    save_steps: int
    eval_strategy: str
    eval_steps: int | None
    bf16: bool
    fp16: bool
    gradient_checkpointing: bool
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    seed: int
    min_cuda_memory_gb: float


@dataclass(frozen=True)
class SFTTrainingSummary:
    """Non-sensitive completed training summary."""

    run_dir: Path
    checkpoint_dir: Path
    train_loss: float
    train_samples: int
    gpu_hours: float


@dataclass(frozen=True)
class SFTCheckpointIdentity:
    """Non-sensitive identity for one completed SFT adapter checkpoint."""

    run_dir: Path
    checkpoint_dir: Path
    run_id: str
    model_id: str
    model_revision: str | None
    dataset_hash: str
    config_hash: str
    dependency_lock_hash: str
    seed: int


class SFTTrainingError(RuntimeError):
    """Raised when SFT configuration, hardware, runtime, or artifacts fail closed."""


@dataclass(frozen=True)
class _SFTRuntime:
    model_config_type: Any
    training_config_type: Any
    trainer_type: Any
    get_peft_config: Any
    get_tokenizer: Any
    get_model: Any


_CONFIG_FIELDS = {
    "run_name",
    "model_id",
    "model_revision",
    "dataset_path",
    "validation_dataset_path",
    "piston_config",
    "max_seq_length",
    "max_steps",
    "num_train_epochs",
    "per_device_train_batch_size",
    "gradient_accumulation_steps",
    "learning_rate",
    "warmup_ratio",
    "lr_scheduler_type",
    "logging_steps",
    "save_strategy",
    "save_steps",
    "eval_strategy",
    "eval_steps",
    "bf16",
    "fp16",
    "gradient_checkpointing",
    "lora_r",
    "lora_alpha",
    "lora_dropout",
    "seed",
    "min_cuda_memory_gb",
}
_RUNTIME_VERSIONS = {
    "trl": "0.18.0",
    "transformers": "4.52.3",
    "accelerate": "1.4.0",
    "peft": "0.14.0",
}
_MIN_TRAINING_CUDA_MEMORY_GB = 20.0
_SFT_RUN_LAYOUT = {
    "resolved_config.yaml",
    "environment.json",
    "run.json",
    "metrics.jsonl",
    "stdout.log",
    "stderr.log",
    "checkpoints",
}
_PEFT_ADAPTER_FILES = {"adapter_config.json", "adapter_model.safetensors"}


def _exact_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise SFTTrainingError("SFT config must be a mapping with string keys")
    missing = _CONFIG_FIELDS - set(value)
    unknown = set(value) - _CONFIG_FIELDS
    if missing:
        raise SFTTrainingError(f"SFT config is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise SFTTrainingError(f"SFT config contains unknown field(s): {', '.join(sorted(unknown))}")
    return cast(Mapping[str, object], value)


def _nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SFTTrainingError(f"{field_name} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise SFTTrainingError(f"{field_name} must contain valid UTF-8 text") from None
    return value


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SFTTrainingError(f"{field_name} must be a positive integer")
    return value


def _finite_float(value: object, *, field_name: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SFTTrainingError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        qualifier = " positive" if positive else ""
        raise SFTTrainingError(f"{field_name} must be a finite{qualifier} number")
    return number


def _path(value: object, *, field_name: str) -> Path:
    text = _nonempty_string(value, field_name=field_name)
    candidate = Path(text)
    resolved = candidate if candidate.is_absolute() else Path.cwd() / candidate
    if resolved.resolve(strict=False) == Path(resolved.anchor):
        raise SFTTrainingError(f"{field_name} must not resolve to the filesystem root")
    return resolved


def sft_training_config_from_mapping(value: object) -> SFTTrainingConfig:
    """Parse one exact flat SFT mapping and reject unsafe or unsupported settings."""
    root = _exact_mapping(value)
    run_name = _nonempty_string(root["run_name"], field_name="run_name")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_name) or ".." in run_name:
        raise SFTTrainingError("run_name contains unsafe path characters")
    revision = root["model_revision"]
    if revision is not None:
        revision = _nonempty_string(revision, field_name="model_revision")
    max_steps = root["max_steps"]
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps == 0 or max_steps < -1:
        raise SFTTrainingError("max_steps must be -1 or a positive integer")
    epochs = _finite_float(root["num_train_epochs"], field_name="num_train_epochs", positive=True)
    learning_rate = _finite_float(root["learning_rate"], field_name="learning_rate", positive=True)
    warmup_ratio = _finite_float(root["warmup_ratio"], field_name="warmup_ratio")
    if not 0.0 <= warmup_ratio <= 1.0:
        raise SFTTrainingError("warmup_ratio must be between 0 and 1")
    lora_dropout = _finite_float(root["lora_dropout"], field_name="lora_dropout")
    if not 0.0 <= lora_dropout < 1.0:
        raise SFTTrainingError("lora_dropout must be between 0 and 1")
    bf16 = root["bf16"]
    fp16 = root["fp16"]
    gradient_checkpointing = root["gradient_checkpointing"]
    if not all(isinstance(value, bool) for value in (bf16, fp16, gradient_checkpointing)):
        raise SFTTrainingError("bf16, fp16, and gradient_checkpointing must be booleans")
    if bf16 is fp16:
        raise SFTTrainingError("exactly one of bf16 and fp16 must be true")
    if gradient_checkpointing is not True:
        raise SFTTrainingError("gradient_checkpointing must be true")
    scheduler = _nonempty_string(root["lr_scheduler_type"], field_name="lr_scheduler_type")
    if scheduler != "cosine":
        raise SFTTrainingError("lr_scheduler_type must be cosine")
    save_strategy = _nonempty_string(root["save_strategy"], field_name="save_strategy")
    if save_strategy != "steps":
        raise SFTTrainingError("save_strategy must be steps")
    eval_strategy = _nonempty_string(root["eval_strategy"], field_name="eval_strategy")
    if eval_strategy not in {"no", "steps"}:
        raise SFTTrainingError("eval_strategy must be no or steps")
    eval_steps_value = root["eval_steps"]
    validation_dataset_value = root["validation_dataset_path"]
    if eval_strategy == "no":
        if eval_steps_value is not None:
            raise SFTTrainingError("eval_steps must be null when eval_strategy is no")
        if validation_dataset_value is not None:
            raise SFTTrainingError("validation_dataset_path must be null when eval_strategy is no")
        eval_steps = None
        validation_dataset_path = None
    else:
        eval_steps = _positive_int(eval_steps_value, field_name="eval_steps")
        validation_dataset_path = _path(validation_dataset_value, field_name="validation_dataset_path")
    seed = root["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SFTTrainingError("seed must be an integer")
    min_cuda_memory_gb = _finite_float(
        root["min_cuda_memory_gb"],
        field_name="min_cuda_memory_gb",
        positive=True,
    )
    if min_cuda_memory_gb < _MIN_TRAINING_CUDA_MEMORY_GB:
        raise SFTTrainingError(f"min_cuda_memory_gb must be at least {_MIN_TRAINING_CUDA_MEMORY_GB:g} GiB")
    return SFTTrainingConfig(
        run_name=run_name,
        model_id=_nonempty_string(root["model_id"], field_name="model_id"),
        model_revision=revision,
        dataset_path=_path(root["dataset_path"], field_name="dataset_path"),
        validation_dataset_path=validation_dataset_path,
        piston_config=_path(root["piston_config"], field_name="piston_config"),
        max_seq_length=_positive_int(root["max_seq_length"], field_name="max_seq_length"),
        max_steps=max_steps,
        num_train_epochs=epochs,
        per_device_train_batch_size=_positive_int(
            root["per_device_train_batch_size"], field_name="per_device_train_batch_size"
        ),
        gradient_accumulation_steps=_positive_int(
            root["gradient_accumulation_steps"], field_name="gradient_accumulation_steps"
        ),
        learning_rate=learning_rate,
        warmup_ratio=warmup_ratio,
        lr_scheduler_type=scheduler,
        logging_steps=_positive_int(root["logging_steps"], field_name="logging_steps"),
        save_strategy=save_strategy,
        save_steps=_positive_int(root["save_steps"], field_name="save_steps"),
        eval_strategy=eval_strategy,
        eval_steps=eval_steps,
        bf16=cast(bool, bf16),
        fp16=cast(bool, fp16),
        gradient_checkpointing=cast(bool, gradient_checkpointing),
        lora_r=_positive_int(root["lora_r"], field_name="lora_r"),
        lora_alpha=_positive_int(root["lora_alpha"], field_name="lora_alpha"),
        lora_dropout=lora_dropout,
        seed=seed,
        min_cuda_memory_gb=min_cuda_memory_gb,
    )


def load_sft_training_config(path: Path) -> SFTTrainingConfig:
    """Load and strictly validate one SFT YAML file."""
    try:
        return sft_training_config_from_mapping(load_yaml_mapping(path))
    except ConfigError as error:
        raise SFTTrainingError(str(error)) from None


def _checkpoint_identity_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SFTTrainingError(f"completed SFT run has invalid {field_name}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise SFTTrainingError(f"completed SFT run has invalid {field_name}") from None
    return value


def _checkpoint_identity_hash(value: object, *, field_name: str) -> str:
    text = _checkpoint_identity_string(value, field_name=field_name)
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise SFTTrainingError(f"completed SFT run has invalid {field_name}")
    return text


def load_completed_sft_checkpoint(run_dir: Path) -> SFTCheckpointIdentity:
    """Load the identity of one completed, directly contained PEFT SFT checkpoint."""
    try:
        resolved_run_dir = run_dir.resolve(strict=True)
    except OSError:
        raise SFTTrainingError("completed SFT run must be an existing directory") from None
    if not resolved_run_dir.is_dir():
        raise SFTTrainingError("completed SFT run must be an existing directory")
    try:
        if {path.name for path in resolved_run_dir.iterdir()} != _SFT_RUN_LAYOUT:
            raise SFTTrainingError("completed SFT run does not match the strict artifact layout")
        checkpoint_dir = (resolved_run_dir / "checkpoints").resolve(strict=True)
        if not checkpoint_dir.is_dir() or checkpoint_dir.parent != resolved_run_dir:
            raise SFTTrainingError("completed SFT checkpoint must belong directly to its SFT run")
        metadata_value = json.loads((resolved_run_dir / "run.json").read_text(encoding="utf-8"))
    except SFTTrainingError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SFTTrainingError("completed SFT run metadata is unreadable") from None
    if not isinstance(metadata_value, dict) or metadata_value.get("status") != "completed":
        raise SFTTrainingError("SFT checkpoint loading requires a completed run")

    adapter_paths = {name: checkpoint_dir / name for name in _PEFT_ADAPTER_FILES}
    if any(not path.is_file() or path.is_symlink() for path in adapter_paths.values()):
        raise SFTTrainingError("completed SFT run has an incomplete PEFT adapter artifact")
    try:
        adapter_config = json.loads(adapter_paths["adapter_config.json"].read_text(encoding="utf-8"))
        adapter_size = adapter_paths["adapter_model.safetensors"].stat().st_size
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SFTTrainingError("completed SFT run has an invalid PEFT adapter artifact") from None
    if (
        not isinstance(adapter_config, dict)
        or not isinstance(adapter_config.get("base_model_name_or_path"), str)
        or not adapter_config["base_model_name_or_path"].strip()
        or not isinstance(adapter_config.get("peft_type"), str)
        or not adapter_config["peft_type"].strip()
        or adapter_size <= 0
    ):
        raise SFTTrainingError("completed SFT run has an invalid PEFT adapter artifact")

    revision = metadata_value.get("model_revision")
    if revision is not None:
        revision = _checkpoint_identity_string(revision, field_name="model_revision")
    seed = metadata_value.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SFTTrainingError("completed SFT run has invalid seed")
    return SFTCheckpointIdentity(
        run_dir=resolved_run_dir,
        checkpoint_dir=checkpoint_dir,
        run_id=_checkpoint_identity_string(metadata_value.get("run_id"), field_name="run_id"),
        model_id=_checkpoint_identity_string(metadata_value.get("model_id"), field_name="model_id"),
        model_revision=revision,
        dataset_hash=_checkpoint_identity_hash(metadata_value.get("dataset_hash"), field_name="dataset_hash"),
        config_hash=_checkpoint_identity_hash(metadata_value.get("config_hash"), field_name="config_hash"),
        dependency_lock_hash=_checkpoint_identity_hash(
            metadata_value.get("dependency_lock_hash"), field_name="dependency_lock_hash"
        ),
        seed=seed,
    )


def _load_torch_runtime() -> ModuleType:
    try:
        return importlib.import_module("torch")
    except ImportError:
        raise SFTTrainingError("PyTorch training runtime is unavailable; run make install-train") from None


def validate_sft_training_hardware(config: SFTTrainingConfig) -> None:
    """Fail before model loading unless a compatible training-class CUDA GPU is available."""
    torch_runtime = _load_torch_runtime()
    try:
        if not bool(torch_runtime.cuda.is_available()):
            raise SFTTrainingError("SFT training requires a CUDA-capable 24GB-class GPU")
        total_memory = float(torch_runtime.cuda.get_device_properties(0).total_memory) / (1024**3)
        required_memory = max(config.min_cuda_memory_gb, _MIN_TRAINING_CUDA_MEMORY_GB)
        if total_memory < required_memory:
            raise SFTTrainingError(
                f"SFT training requires at least {required_memory:g} GiB CUDA memory; detected {total_memory:.1f} GiB"
            )
        if config.bf16 and not bool(torch_runtime.cuda.is_bf16_supported(including_emulation=False)):
            raise SFTTrainingError("configured bf16 training requires native CUDA BF16 support")
    except SFTTrainingError:
        raise
    except Exception as error:
        raise SFTTrainingError(f"could not validate CUDA training hardware: {type(error).__name__}") from None


def _load_sft_runtime() -> _SFTRuntime:
    """Lazy-load and verify the exact pinned TRL/Open-R1/PEFT runtime surface."""
    for distribution, expected in _RUNTIME_VERSIONS.items():
        try:
            actual = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            raise SFTTrainingError(f"{distribution} is unavailable; run make install-train") from None
        if actual != expected:
            raise SFTTrainingError(f"{distribution} must be exactly {expected}, found {actual}")
    try:
        importlib.import_module("peft")
        trl_runtime = importlib.import_module("trl")
        configs_runtime = import_open_r1_module("open_r1.configs")
        model_runtime = import_open_r1_module("open_r1.utils.model_utils")
        return _SFTRuntime(
            model_config_type=trl_runtime.ModelConfig,
            training_config_type=configs_runtime.SFTConfig,
            trainer_type=trl_runtime.SFTTrainer,
            get_peft_config=trl_runtime.get_peft_config,
            get_tokenizer=model_runtime.get_tokenizer,
            get_model=model_runtime.get_model,
        )
    except (ImportError, AttributeError) as error:
        raise SFTTrainingError(f"pinned SFT runtime contract is unavailable: {type(error).__name__}") from None


def _resolved_config_mapping(config: SFTTrainingConfig, *, effective_seed: int) -> dict[str, object]:
    resolved = asdict(config)
    resolved["dataset_path"] = str(config.dataset_path)
    resolved["validation_dataset_path"] = (
        None if config.validation_dataset_path is None else str(config.validation_dataset_path)
    )
    resolved["piston_config"] = str(config.piston_config)
    resolved["seed"] = effective_seed
    resolved["use_peft"] = True
    resolved["load_in_4bit"] = False
    resolved["load_in_8bit"] = False
    resolved["trust_remote_code"] = False
    resolved["lora_target_modules"] = "auto"
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
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _dataset_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise SFTTrainingError(f"could not read SFT dataset: {type(error).__name__}") from None


def _config_hash(config: SFTTrainingConfig, *, seed: int) -> str:
    payload = _resolved_config_mapping(config, effective_seed=seed)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_run_dir(output_root: Path, run_name: str) -> Path:
    root = output_root.resolve(strict=False)
    if root == Path(root.anchor) or root == Path.cwd().resolve():
        raise SFTTrainingError("output_root must be a dedicated non-root directory")
    run_dir = root / run_name
    if root not in run_dir.parents:
        raise SFTTrainingError("resolved SFT run directory escapes output_root")
    return run_dir


def _runtime_arguments(
    config: SFTTrainingConfig,
    *,
    checkpoint_dir: Path,
    seed: int,
    runtime: _SFTRuntime,
) -> tuple[Any, Any]:
    dtype = "bfloat16" if config.bf16 else "float16"
    model_args = runtime.model_config_type(
        model_name_or_path=config.model_id,
        model_revision=config.model_revision or "main",
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
        do_eval=config.eval_strategy != "no",
        max_length=config.max_seq_length,
        max_steps=config.max_steps,
        num_train_epochs=config.num_train_epochs,
        per_device_train_batch_size=config.per_device_train_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_ratio=config.warmup_ratio,
        lr_scheduler_type=config.lr_scheduler_type,
        logging_steps=config.logging_steps,
        save_strategy=config.save_strategy,
        save_steps=config.save_steps,
        eval_strategy=config.eval_strategy,
        eval_steps=config.eval_steps,
        bf16=config.bf16,
        fp16=config.fp16,
        gradient_checkpointing=config.gradient_checkpointing,
        seed=seed,
        data_seed=seed,
        report_to=[],
        push_to_hub=False,
    )
    return model_args, training_args


def _initialize_run(
    *,
    run_dir: Path,
    config: SFTTrainingConfig,
    seed: int,
    dataset_hash: str,
    validation_dataset_hash: str | None,
    config_hash: str,
    environment: Mapping[str, Any],
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "checkpoints").mkdir()
    started = datetime.now(timezone.utc).isoformat()
    run_metadata: dict[str, object] = {
        "run_id": config.run_name,
        "timestamp": started,
        "git_commit": environment["project_commit"],
        "open_r1_commit": environment["open_r1_commit"],
        "python_version": environment["python_version"],
        "torch_version": environment["packages"]["torch"],
        "cuda_version": environment["cuda_version"],
        "gpu_name": environment["gpu_name"],
        "gpu_count": environment["gpu_count"],
        "dependency_lock_hash": environment["dependency_lock_hash"],
        "model_id": config.model_id,
        "model_revision": config.model_revision,
        "dataset_hash": dataset_hash,
        "validation_dataset_hash": validation_dataset_hash,
        "config_hash": config_hash,
        "seed": seed,
        "seed_override": None if seed == config.seed else {"config": config.seed, "cli": seed},
        "resume_from_checkpoint": None,
        "command": "code-verifier train-sft",
        "start_time": started,
        "end_time": None,
        "gpu_hours": 0.0,
        "status": "running",
    }
    resolved = _resolved_config_mapping(config, effective_seed=seed)
    _atomic_write(run_dir / "resolved_config.yaml", yaml.safe_dump(resolved, sort_keys=True, allow_unicode=True))
    _write_json(run_dir / "environment.json", environment)
    _write_json(run_dir / "run.json", run_metadata)
    for name in ("metrics.jsonl", "stdout.log", "stderr.log"):
        (run_dir / name).touch(exist_ok=False)
    return run_metadata


def _validate_resume_run(
    *,
    run_dir: Path,
    config: SFTTrainingConfig,
    seed: int,
    dataset_hash: str,
    validation_dataset_hash: str | None,
    config_hash: str,
    environment: Mapping[str, Any],
    resume_source: str,
) -> dict[str, object]:
    try:
        value = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SFTTrainingError("existing SFT run metadata is unreadable") from None
    if not isinstance(value, dict):
        raise SFTTrainingError("existing SFT run metadata is invalid")
    expected = {
        "run_id": config.run_name,
        "model_id": config.model_id,
        "model_revision": config.model_revision,
        "dataset_hash": dataset_hash,
        "validation_dataset_hash": validation_dataset_hash,
        "config_hash": config_hash,
        "seed": seed,
        "git_commit": environment["project_commit"],
        "open_r1_commit": environment["open_r1_commit"],
        "dependency_lock_hash": environment["dependency_lock_hash"],
        "python_version": environment["python_version"],
        "torch_version": environment["packages"]["torch"],
        "cuda_version": environment["cuda_version"],
        "gpu_name": environment["gpu_name"],
        "gpu_count": environment["gpu_count"],
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise SFTTrainingError("existing SFT run identity does not match the requested resume")
    if {path.name for path in run_dir.iterdir()} != _SFT_RUN_LAYOUT:
        raise SFTTrainingError("existing SFT run does not match the strict artifact layout")
    if value.get("status") not in {"running", "failed"}:
        raise SFTTrainingError("only an interrupted or failed SFT run may be resumed")
    previous_gpu_hours = value.get("gpu_hours")
    if (
        isinstance(previous_gpu_hours, bool)
        or not isinstance(previous_gpu_hours, int | float)
        or not math.isfinite(float(previous_gpu_hours))
        or float(previous_gpu_hours) < 0.0
    ):
        raise SFTTrainingError("existing SFT run has invalid cumulative gpu_hours")
    value["status"] = "running"
    value["end_time"] = None
    value["resume_from_checkpoint"] = resume_source
    _write_json(run_dir / "run.json", value)
    return cast(dict[str, object], value)


def _resolve_resume_checkpoint(run_dir: Path, requested: Path) -> tuple[Path, str]:
    """Resolve one Trainer checkpoint that belongs directly to the requested run."""
    try:
        resolved_run_dir = run_dir.resolve(strict=True)
        checkpoint_root = (resolved_run_dir / "checkpoints").resolve(strict=True)
        resolved_checkpoint = requested.resolve(strict=True)
    except OSError:
        raise SFTTrainingError("resume_from_checkpoint must be an existing checkpoint directory") from None
    if (
        not resolved_checkpoint.is_dir()
        or resolved_checkpoint.parent != checkpoint_root
        or re.fullmatch(r"checkpoint-[1-9][0-9]*", resolved_checkpoint.name) is None
    ):
        raise SFTTrainingError("resume_from_checkpoint must be a checkpoint-* directory from the same SFT run")
    return resolved_checkpoint, resolved_checkpoint.relative_to(resolved_run_dir).as_posix()


def _ensure_disjoint_sft_splits(
    train_records: list[dict[str, Any]],
    validation_records: list[dict[str, Any]],
) -> None:
    """Reject train/validation artifact identity overlap before trainer construction."""

    def problem_ids(records: list[dict[str, Any]], *, split_name: str) -> set[str]:
        identifiers: set[str] = set()
        for record in records:
            problem_id = record.get("problem_id")
            if not isinstance(problem_id, str) or not problem_id.strip():
                raise SFTTrainingError(f"{split_name} SFT artifact contains an invalid problem_id")
            if problem_id in identifiers:
                raise SFTTrainingError(f"{split_name} SFT artifact contains duplicate problem_id values")
            identifiers.add(problem_id)
        return identifiers

    overlap = problem_ids(train_records, split_name="train") & problem_ids(
        validation_records,
        split_name="validation",
    )
    if overlap:
        raise SFTTrainingError("SFT train and validation artifacts contain overlapping problem_id values")


def run_sft_training(
    config: SFTTrainingConfig,
    *,
    output_root: Path,
    seed: int,
    executor: CodeExecutor,
    resume_from_checkpoint: Path | None = None,
) -> SFTTrainingSummary:
    """Validate trajectories and run one local-only pinned LoRA SFT lifecycle."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SFTTrainingError("seed must be an integer")
    validate_sft_training_hardware(config)
    runtime = _load_sft_runtime()
    run_dir = _safe_run_dir(output_root, config.run_name)
    checkpoint_dir = run_dir / "checkpoints"
    dataset_hash = _dataset_hash(config.dataset_path)
    validation_dataset_hash = (
        None if config.validation_dataset_path is None else _dataset_hash(config.validation_dataset_path)
    )
    config_hash = _config_hash(config, seed=seed)
    environment = collect_environment()
    resume_path: str | None = None
    resume_source: str | None = None
    if resume_from_checkpoint is not None:
        if not run_dir.is_dir():
            raise SFTTrainingError("resume requires an existing SFT run directory")
        resolved_resume, resume_source = _resolve_resume_checkpoint(run_dir, resume_from_checkpoint)
        resume_path = str(resolved_resume)
        run_metadata = _validate_resume_run(
            run_dir=run_dir,
            config=config,
            seed=seed,
            dataset_hash=dataset_hash,
            validation_dataset_hash=validation_dataset_hash,
            config_hash=config_hash,
            environment=environment,
            resume_source=resume_source,
        )
    else:
        if run_dir.exists():
            raise SFTTrainingError("SFT run directory already exists; explicit resume is required")
        try:
            run_metadata = _initialize_run(
                run_dir=run_dir,
                config=config,
                seed=seed,
                dataset_hash=dataset_hash,
                validation_dataset_hash=validation_dataset_hash,
                config_hash=config_hash,
                environment=environment,
            )
        except Exception:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise

    previous_gpu_hours = float(cast(int | float, run_metadata["gpu_hours"]))
    started = time.perf_counter()
    try:
        records = load_training_artifact(config.dataset_path, kind=TrainingArtifactKind.SFT)
        validation_records = (
            None
            if config.validation_dataset_path is None
            else load_training_artifact(config.validation_dataset_path, kind=TrainingArtifactKind.SFT)
        )
        if validation_records is not None:
            _ensure_disjoint_sft_splits(records, validation_records)
        model_args, training_args = _runtime_arguments(
            config,
            checkpoint_dir=checkpoint_dir,
            seed=seed,
            runtime=runtime,
        )
        tokenizer = runtime.get_tokenizer(model_args, training_args)
        train_dataset = build_sft_dataset(
            records,
            executor=executor,
            tokenizer=tokenizer,
            max_seq_length=config.max_seq_length,
        )
        eval_dataset = (
            None
            if validation_records is None
            else build_sft_dataset(
                validation_records,
                executor=executor,
                tokenizer=tokenizer,
                max_seq_length=config.max_seq_length,
            )
        )
        model = runtime.get_model(model_args, training_args)
        trainer = runtime.trainer_type(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            processing_class=tokenizer,
            peft_config=runtime.get_peft_config(model_args),
        )
        train_result = trainer.train(resume_from_checkpoint=resume_path)
        raw_loss = getattr(train_result, "metrics", {}).get("train_loss")
        if isinstance(raw_loss, bool) or not isinstance(raw_loss, int | float) or not math.isfinite(float(raw_loss)):
            raise SFTTrainingError("SFT training must produce a finite train_loss")
        train_loss = float(raw_loss)
        trainer.save_state()
        trainer.save_model(str(checkpoint_dir))
        attempt_gpu_hours = (time.perf_counter() - started) / 3600.0
        gpu_hours = previous_gpu_hours + attempt_gpu_hours
        metrics = {
            "train_loss": train_loss,
            "train_samples": len(train_dataset),
            "eval_samples": 0 if eval_dataset is None else len(eval_dataset),
            "attempt_gpu_hours": attempt_gpu_hours,
            "gpu_hours": gpu_hours,
        }
        _append_jsonl(run_dir / "metrics.jsonl", metrics)
        with (run_dir / "stdout.log").open("a", encoding="utf-8") as handle:
            handle.write(f"completed train_samples={len(train_dataset)}\n")
        run_metadata["status"] = "completed"
        run_metadata["end_time"] = datetime.now(timezone.utc).isoformat()
        run_metadata["gpu_hours"] = gpu_hours
        _write_json(run_dir / "run.json", run_metadata)
        return SFTTrainingSummary(
            run_dir=run_dir,
            checkpoint_dir=checkpoint_dir,
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
