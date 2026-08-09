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
    if eval_strategy == "no":
        if eval_steps_value is not None:
            raise SFTTrainingError("eval_steps must be null when eval_strategy is no")
        eval_steps = None
    else:
        eval_steps = _positive_int(eval_steps_value, field_name="eval_steps")
    seed = root["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SFTTrainingError("seed must be an integer")
    return SFTTrainingConfig(
        run_name=run_name,
        model_id=_nonempty_string(root["model_id"], field_name="model_id"),
        model_revision=revision,
        dataset_path=_path(root["dataset_path"], field_name="dataset_path"),
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
        min_cuda_memory_gb=_finite_float(root["min_cuda_memory_gb"], field_name="min_cuda_memory_gb", positive=True),
    )


def load_sft_training_config(path: Path) -> SFTTrainingConfig:
    """Load and strictly validate one SFT YAML file."""
    try:
        return sft_training_config_from_mapping(load_yaml_mapping(path))
    except ConfigError as error:
        raise SFTTrainingError(str(error)) from None


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
        if total_memory < config.min_cuda_memory_gb:
            raise SFTTrainingError(
                f"SFT training requires at least {config.min_cuda_memory_gb:g} GiB CUDA memory; "
                f"detected {total_memory:.1f} GiB"
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


def _resolved_config_mapping(config: SFTTrainingConfig) -> dict[str, object]:
    resolved = asdict(config)
    resolved["dataset_path"] = str(config.dataset_path)
    resolved["piston_config"] = str(config.piston_config)
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
    payload = {"config": _resolved_config_mapping(config), "effective_seed": seed}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_run_dir(output_root: Path, run_name: str) -> Path:
    root = output_root.resolve(strict=False)
    if root == Path(root.anchor) or root == Path.cwd().resolve():
        raise SFTTrainingError("output_root must be a dedicated non-root directory")
    run_dir = root / "sft" / run_name
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
    config_hash: str,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "checkpoints").mkdir()
    environment = collect_environment()
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
        "config_hash": config_hash,
        "seed": seed,
        "command": "code-verifier train-sft",
        "start_time": started,
        "end_time": None,
        "gpu_hours": 0.0,
        "status": "running",
    }
    resolved = _resolved_config_mapping(config)
    resolved["effective_seed"] = seed
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
    config_hash: str,
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
        "config_hash": config_hash,
        "seed": seed,
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise SFTTrainingError("existing SFT run identity does not match the requested resume")
    required = {
        "resolved_config.yaml",
        "environment.json",
        "run.json",
        "metrics.jsonl",
        "stdout.log",
        "stderr.log",
        "checkpoints",
    }
    if {path.name for path in run_dir.iterdir()} != required:
        raise SFTTrainingError("existing SFT run does not match the strict artifact layout")
    value["status"] = "running"
    value["end_time"] = None
    _write_json(run_dir / "run.json", value)
    return cast(dict[str, object], value)


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
    dataset_hash = _dataset_hash(config.dataset_path)
    config_hash = _config_hash(config, seed=seed)
    resume_path: str | None = None
    if resume_from_checkpoint is not None:
        resolved_resume = resume_from_checkpoint.resolve(strict=False)
        if not resolved_resume.is_dir():
            raise SFTTrainingError("resume_from_checkpoint must be an existing directory")
        resume_path = str(resolved_resume)
    if run_dir.exists():
        if resume_path is None:
            raise SFTTrainingError("SFT run directory already exists; explicit resume is required")
        run_metadata = _validate_resume_run(
            run_dir=run_dir,
            config=config,
            seed=seed,
            dataset_hash=dataset_hash,
            config_hash=config_hash,
        )
    else:
        try:
            run_metadata = _initialize_run(
                run_dir=run_dir,
                config=config,
                seed=seed,
                dataset_hash=dataset_hash,
                config_hash=config_hash,
            )
        except Exception:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise

    checkpoint_dir = run_dir / "checkpoints"
    started = time.perf_counter()
    try:
        records = load_training_artifact(config.dataset_path, kind=TrainingArtifactKind.SFT)
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
        model = runtime.get_model(model_args, training_args)
        trainer = runtime.trainer_type(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=None,
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
        gpu_hours = (time.perf_counter() - started) / 3600.0
        metrics = {
            "train_loss": train_loss,
            "train_samples": len(train_dataset),
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
        run_metadata["status"] = "failed"
        run_metadata["end_time"] = datetime.now(timezone.utc).isoformat()
        run_metadata["gpu_hours"] = (time.perf_counter() - started) / 3600.0
        _write_json(run_dir / "run.json", run_metadata)
        with (run_dir / "stderr.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{type(error).__name__}\n")
        raise
