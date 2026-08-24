"""Command-line entry point for CodeVerifier.

Example:
    python -m code_verifier.cli --help
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

from code_verifier import __version__
from code_verifier.analysis import AnalysisError, analyze_experiment, load_analysis_config
from code_verifier.config import ConfigError
from code_verifier.data.adapters import InputAdapterError
from code_verifier.data.deduplicate import DuplicateDataError
from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.data.leakage_checks import LeakageError
from code_verifier.data.prepare import (
    DataPreparationError,
    PreparationSummary,
    check_prepared_data,
    load_data_preparation_config,
    prepare_data,
)
from code_verifier.data.schema import SchemaError
from code_verifier.environment import write_environment_record
from code_verifier.evaluation.evaluate import (
    EvaluationConfig,
    EvaluationError,
    load_evaluation_config,
    run_pass1_evaluation,
)
from code_verifier.evaluation.generate import GenerationError, TransformersCompletionGenerator
from code_verifier.evaluation.metrics import MetricsError, aggregate_evaluation_run
from code_verifier.evaluation.staged import (
    load_generation_bundle_source,
    run_generation_bundle,
    run_verification_from_generation_bundle,
)
from code_verifier.execution import (
    BatchExecutionConfig,
    BatchExecutionError,
    BatchExecutionRequest,
    BatchExecutionResult,
    BatchExecutor,
    BatchExecutorConfig,
    ExecutionCacheError,
    ExecutionCacheMode,
    ExecutionContractError,
    ExecutionStatus,
    ExecutionWorkloadMode,
    PistonExecutor,
    PistonTransportError,
    SQLiteExecutionCache,
    batch_execution_item_to_mapping,
    batch_execution_request_from_mapping,
    load_batch_execution_config,
    load_piston_executor_config,
    piston_executor_version,
    validate_batch_cache_policy,
)
from code_verifier.parsing import extract_python_code
from code_verifier.training import (
    GRPOCheckpointIdentity,
    GRPODataError,
    GRPOTrainingError,
    SFTCheckpointIdentity,
    SFTDataError,
    SFTPrevalidationError,
    SFTTrainingError,
    grpo_evaluation_checkpoint_id,
    load_completed_grpo_checkpoint,
    load_completed_sft_checkpoint,
    load_grpo_training_config,
    load_sft_training_config,
    run_grpo_training,
    run_sft_prevalidation,
    run_sft_training,
)

CommandHandler = Callable[[argparse.Namespace], int]
DATA_ERRORS = (
    ConfigError,
    SchemaError,
    InputAdapterError,
    DuplicateDataError,
    LeakageError,
    DataPreparationError,
)
EXECUTION_ERRORS = (
    ExecutionContractError,
    BatchExecutionError,
    ExecutionCacheError,
    PistonTransportError,
    StrictJsonError,
    OSError,
    UnicodeError,
)
EVALUATION_ERRORS = (EvaluationError, GenerationError, MetricsError)
TRAINING_ERRORS = (SFTDataError, SFTPrevalidationError, SFTTrainingError, GRPODataError, GRPOTrainingError)
ANALYSIS_ERRORS = (AnalysisError,)
ARTIFACT_ROOT_ENV = "CODE_VERIFIER_ARTIFACT_ROOT"


def _default_artifact_output(relative: str | None = None) -> Path:
    """Resolve an optional persistent artifact root for commands with default outputs."""
    configured = os.environ.get(ARTIFACT_ROOT_ENV)
    root = Path(configured).expanduser() if configured else Path("outputs")
    return root if relative is None else root / relative


def _add_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_required: bool = False,
    output_dir_default: Path | None = None,
    output_dir_required: bool | None = None,
    seed_default: int | None = 42,
) -> None:
    """Add common project options while allowing independent config/output requirements."""
    parser.add_argument(
        "--config",
        type=Path,
        required=config_required,
        help="YAML config path; required by commands that execute configured workflows",
    )
    seed_help = (
        "deterministic seed (default: config seed)" if seed_default is None else "deterministic seed (default: 42)"
    )
    parser.add_argument("--seed", type=int, default=seed_default, help=seed_help)
    resolved_output_required = config_required if output_dir_required is None else output_dir_required
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=resolved_output_required,
        default=None if resolved_output_required else output_dir_default,
        help=("command output root; commands with model/training defaults honor CODE_VERIFIER_ARTIFACT_ROOT when set"),
    )
    parser.add_argument("--log-level", default="INFO", help="standard logging level (default: INFO)")


def _configure_logging(level: str) -> None:
    """Validate and configure the requested standard-library log level."""
    normalized = level.upper()
    numeric_level = getattr(logging, normalized, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"unsupported log level {level!r}")
    logging.basicConfig(level=numeric_level, force=True)


def _print_summary(action: str, summary: PreparationSummary) -> None:
    """Print one non-sensitive data preparation or verification summary."""
    split_text = ", ".join(f"{name}={summary.split_counts[name]}" for name in ("train", "validation", "test"))
    print(f"{action} {summary.total_problems} problems ({split_text})")
    if summary.canonical_jsonl is not None:
        print(f"canonical_jsonl={summary.canonical_jsonl}")
    if summary.hf_dataset_dir is not None:
        print(f"hf_dataset={summary.hf_dataset_dir}")
    for kind, path in sorted(summary.training_artifacts.items(), key=lambda item: item[0].value):
        print(f"training_{kind.value}={path}")
    print(f"training_sft_validation={summary.sft_validation_artifact}")


def _record_environment(args: argparse.Namespace) -> int:
    """Write an environment record requested by the CLI."""
    output = Path(str(args.output))
    write_environment_record(output)
    print(f"Wrote environment record to {output}")
    return 0


def _prepare_data(args: argparse.Namespace) -> int:
    """Run the configured WP1 data pipeline and print a non-sensitive summary."""
    config_path = Path(str(args.config))
    output_dir = Path(str(args.output_dir))
    summary = prepare_data(
        load_data_preparation_config(config_path),
        seed=int(args.seed),
        output_dir=output_dir,
    )
    _print_summary("prepared", summary)
    return 0


def _check_data(args: argparse.Namespace) -> int:
    """Validate an existing WP1 prepared dataset and print a summary."""
    summary = check_prepared_data(Path(str(args.dataset)))
    _print_summary("checked", summary)
    return 0


def _read_completion(path_text: str) -> str:
    """Read UTF-8 completion text from stdin for '-' or from one local file."""
    if path_text == "-":
        return sys.stdin.read()
    return Path(path_text).read_text(encoding="utf-8")


def _parse_code(args: argparse.Namespace) -> int:
    """Run the WP2 parser and print one deterministic JSON ParseResult."""
    try:
        completion = _read_completion(str(args.completion_file))
    except (OSError, UnicodeError) as error:
        print(f"error: {' '.join(str(error).splitlines())}", file=sys.stderr)
        return 2
    result = extract_python_code(completion, expected_function_name=args.expected_function_name)
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.success else 1


def _load_batch_requests(path: Path) -> list[BatchExecutionRequest]:
    """Read strict UTF-8 JSONL requests and reject blank, duplicate-key, or malformed records."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        raise BatchExecutionError("batch request JSONL must contain at least one record")
    requests: list[BatchExecutionRequest] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise BatchExecutionError(f"batch request JSONL line {line_number} must not be blank")
        try:
            value = loads_strict(line)
            request = batch_execution_request_from_mapping(value)
        except (StrictJsonError, ExecutionContractError):
            raise BatchExecutionError(f"batch request JSONL line {line_number} is invalid") from None
        requests.append(request)
    return requests


def _write_batch_outputs(result: BatchExecutionResult, output_dir: Path) -> None:
    """Atomically write results.jsonl and summary.json without request payloads."""
    if output_dir.exists():
        raise BatchExecutionError("output directory must not already exist")
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=parent))
    try:
        item_mappings = [batch_execution_item_to_mapping(item) for item in result.items]
        results_text = "".join(
            f"{json.dumps(item, ensure_ascii=False, sort_keys=True, allow_nan=False)}\n" for item in item_mappings
        )
        (temporary / "results.jsonl").write_text(results_text, encoding="utf-8")
        status_counts = {status.value: 0 for status in ExecutionStatus}
        for item in result.items:
            status_counts[item.result.status.value] += 1
        summary: dict[str, object] = {
            "executor_version": result.executor_version,
            "workload_mode": result.workload_mode.value,
            "cache_mode": result.cache_mode.value,
            "max_concurrency": result.max_concurrency,
            "total_requests": result.total_requests,
            "cache_hits": result.cache_hits,
            "status_counts": status_counts,
            "runtime_ms": result.runtime_ms,
            "results_file": "results.jsonl",
        }
        (temporary / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.rename(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _resolve_batch_options(
    args: argparse.Namespace,
    config: BatchExecutionConfig,
) -> tuple[BatchExecutorConfig, ExecutionWorkloadMode]:
    max_concurrency = config.batch.max_concurrency if args.max_concurrency is None else int(args.max_concurrency)
    if not 1 <= max_concurrency <= 64:
        raise ConfigError("max_concurrency must be an integer between 1 and 64")
    cache_mode = config.batch.cache_mode
    if args.cache_mode is not None:
        try:
            cache_mode = ExecutionCacheMode(str(args.cache_mode))
        except ValueError:
            raise ConfigError("cache_mode must be disabled, read_only, or read_write") from None
    try:
        workload_mode = ExecutionWorkloadMode(str(args.workload_mode))
    except ValueError:
        raise ConfigError("workload_mode must be evaluation or training") from None
    return replace(config.batch, max_concurrency=max_concurrency, cache_mode=cache_mode), workload_mode


def _execute_batch(args: argparse.Namespace) -> int:
    """Run configured loopback Piston batch execution and emit non-sensitive artifacts."""
    config = load_batch_execution_config(Path(str(args.config)))
    batch_config, workload_mode = _resolve_batch_options(args, config)
    requests = _load_batch_requests(Path(str(args.requests)))
    output_dir = Path(str(args.output_dir))
    if output_dir.exists():
        raise BatchExecutionError("output directory must not already exist")

    cache_path = None if args.cache_path is None else Path(str(args.cache_path))
    if batch_config.cache_mode is ExecutionCacheMode.DISABLED:
        if cache_path is not None:
            raise BatchExecutionError("cache path is not allowed when cache mode is disabled")
    elif cache_path is None:
        raise BatchExecutionError("cache path is required when cache mode is enabled")
    if cache_path is not None:
        resolved_output = output_dir.resolve(strict=False)
        resolved_cache = cache_path.resolve(strict=False)
        if resolved_cache == resolved_output or resolved_output in resolved_cache.parents:
            raise BatchExecutionError("cache path must not be inside the output directory")
    validate_batch_cache_policy(batch_config, workload_mode)

    probe = PistonExecutor(config.piston)
    probe.validate_runtime()
    executor_version = piston_executor_version(config.piston)
    cache = None if cache_path is None else SQLiteExecutionCache(cache_path)
    try:
        executor = BatchExecutor(
            lambda: PistonExecutor(config.piston),
            executor_version=executor_version,
            config=batch_config,
            cache=cache,
        )
        result = executor.execute_batch(requests, workload_mode=workload_mode)
    finally:
        if cache is not None:
            cache.close()
    _write_batch_outputs(result, output_dir)
    print(f"executed {result.total_requests} requests (cache_hits={result.cache_hits})")
    print(f"results={output_dir / 'results.jsonl'}")
    print(f"summary={output_dir / 'summary.json'}")
    return 1 if any(item.result.status is ExecutionStatus.SANDBOX_ERROR for item in result.items) else 0


def _safe_run_name(value: str) -> str:
    if not value.strip() or not re.fullmatch(r"[A-Za-z0-9._-]+", value) or ".." in value:
        raise argparse.ArgumentTypeError(
            "run name must use only A-Z, a-z, 0-9, dot, underscore, or hyphen and must not contain '..'"
        )
    return value


def _nonempty_model_id(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("model id must be a non-empty string")
    return value


def _resolve_generation_source(
    args: argparse.Namespace, config: EvaluationConfig
) -> tuple[EvaluationConfig, str, SFTCheckpointIdentity | None, GRPOCheckpointIdentity | None]:
    """Resolve a strict evaluation checkpoint without constructing an executor."""
    sft_checkpoint: SFTCheckpointIdentity | None = None
    grpo_checkpoint: GRPOCheckpointIdentity | None = None
    if args.model_id is not None:
        model_id = str(args.model_id)
    elif args.sft_run_dir is not None:
        sft_checkpoint = load_completed_sft_checkpoint(Path(str(args.sft_run_dir)))
        model_id = sft_checkpoint.model_id
        config = replace(
            config,
            model_revision=sft_checkpoint.model_revision,
            checkpoint=str(sft_checkpoint.checkpoint_dir),
        )
    else:
        grpo_checkpoint = load_completed_grpo_checkpoint(Path(str(args.grpo_run_dir)))
        model_id = grpo_checkpoint.parent_sft.model_id
        config = replace(
            config,
            model_revision=grpo_checkpoint.parent_sft.model_revision,
            checkpoint=grpo_evaluation_checkpoint_id(grpo_checkpoint),
        )
    return config, model_id, sft_checkpoint, grpo_checkpoint


def _build_generation_model(
    config: EvaluationConfig,
    model_id: str,
    sft_checkpoint: SFTCheckpointIdentity | None,
    grpo_checkpoint: GRPOCheckpointIdentity | None,
) -> TransformersCompletionGenerator:
    """Load only the frozen generation model for a resolved evaluation source."""
    if sft_checkpoint is None and grpo_checkpoint is None:
        return TransformersCompletionGenerator.from_pretrained(
            model_id,
            model_revision=config.model_revision,
            device=config.device,
            config=config.generation,
        )
    if sft_checkpoint is not None:
        return TransformersCompletionGenerator.from_peft_checkpoint(
            base_model_id=sft_checkpoint.model_id,
            base_model_revision=sft_checkpoint.model_revision,
            adapter_dir=sft_checkpoint.checkpoint_dir,
            device=config.device,
            config=config.generation,
        )
    assert grpo_checkpoint is not None
    return TransformersCompletionGenerator.from_grpo_checkpoint(
        base_model_id=grpo_checkpoint.parent_sft.model_id,
        base_model_revision=grpo_checkpoint.parent_sft.model_revision,
        parent_sft_adapter_dir=grpo_checkpoint.parent_sft.checkpoint_dir,
        grpo_adapter_dir=grpo_checkpoint.checkpoint_dir,
        device=config.device,
        config=config.generation,
    )


def _generate_eval(args: argparse.Namespace) -> int:
    """Generate a durable evaluation bundle without contacting Piston."""
    config = load_evaluation_config(Path(str(args.config)))
    if args.dataset_dir is not None:
        dataset_dir = Path(str(args.dataset_dir))
        print(f"override: dataset_dir: {config.dataset_dir} -> {dataset_dir}", file=sys.stderr)
        config = replace(config, dataset_dir=dataset_dir)
    config, model_id, sft_checkpoint, grpo_checkpoint = _resolve_generation_source(args, config)
    generator = _build_generation_model(config, model_id, sft_checkpoint, grpo_checkpoint)
    summary = run_generation_bundle(
        config=config,
        model_id=model_id,
        generator=generator,
        run_id=str(args.run_name),
        output_root=Path(str(args.output_dir)),
        seed=int(args.seed),
    )
    print(
        f"generated {summary.total_problems} evaluation prompts "
        f"(resumed={summary.completed_before_run}, generated={summary.generated_this_run})"
    )
    print(f"generation_run={summary.run_dir}")
    print(f"generations={summary.records_path}")
    return 0


def _verify_eval(args: argparse.Namespace) -> int:
    """Verify a completed generation bundle through the configured local Piston service."""
    config = load_evaluation_config(Path(str(args.config)))
    if args.dataset_dir is not None:
        dataset_dir = Path(str(args.dataset_dir))
        print(f"override: dataset_dir: {config.dataset_dir} -> {dataset_dir}", file=sys.stderr)
        config = replace(config, dataset_dir=dataset_dir)
    generation_run_dir = Path(str(args.generation_run_dir))
    source = load_generation_bundle_source(generation_run_dir)
    if str(args.run_name) != source.run_id:
        raise EvaluationError("verify-eval run-name must match the completed generation bundle")
    if int(args.seed) != source.seed:
        raise EvaluationError("verify-eval seed must match the completed generation bundle")
    config = replace(config, model_revision=source.model_revision, checkpoint=source.checkpoint)
    piston_config = load_piston_executor_config(config.piston_config)
    PistonExecutor(piston_config).validate_runtime()
    summary = run_verification_from_generation_bundle(
        config=config,
        generation_run_dir=generation_run_dir,
        executor_factory=lambda: PistonExecutor(piston_config),
        run_id=source.run_id,
        output_root=Path(str(args.output_dir)),
        seed=source.seed,
        workers=int(args.workers),
    )
    print(
        f"verified {summary.total_problems} generated completions "
        f"(resumed={summary.completed_before_run}, verified={summary.verified_this_run})"
    )
    print(f"results={summary.results_path}")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    """Run one deterministic, resumable pass@1 evaluation."""
    config = load_evaluation_config(Path(str(args.config)))
    if args.dataset_dir is not None:
        dataset_dir = Path(str(args.dataset_dir))
        print(f"override: dataset_dir: {config.dataset_dir} -> {dataset_dir}", file=sys.stderr)
        config = replace(config, dataset_dir=dataset_dir)
    sft_checkpoint = None
    grpo_checkpoint = None
    if args.model_id is not None:
        model_id = str(args.model_id)
    elif args.sft_run_dir is not None:
        sft_checkpoint = load_completed_sft_checkpoint(Path(str(args.sft_run_dir)))
        model_id = sft_checkpoint.model_id
        config = replace(
            config,
            model_revision=sft_checkpoint.model_revision,
            checkpoint=str(sft_checkpoint.checkpoint_dir),
        )
    else:
        grpo_checkpoint = load_completed_grpo_checkpoint(Path(str(args.grpo_run_dir)))
        model_id = grpo_checkpoint.parent_sft.model_id
        config = replace(
            config,
            model_revision=grpo_checkpoint.parent_sft.model_revision,
            checkpoint=grpo_evaluation_checkpoint_id(grpo_checkpoint),
        )
    piston_config = load_piston_executor_config(config.piston_config)
    executor = PistonExecutor(piston_config)
    executor.validate_runtime()
    if sft_checkpoint is None and grpo_checkpoint is None:
        generator = TransformersCompletionGenerator.from_pretrained(
            model_id,
            model_revision=config.model_revision,
            device=config.device,
            config=config.generation,
        )
    elif sft_checkpoint is not None:
        generator = TransformersCompletionGenerator.from_peft_checkpoint(
            base_model_id=sft_checkpoint.model_id,
            base_model_revision=sft_checkpoint.model_revision,
            adapter_dir=sft_checkpoint.checkpoint_dir,
            device=config.device,
            config=config.generation,
        )
    else:
        assert grpo_checkpoint is not None
        generator = TransformersCompletionGenerator.from_grpo_checkpoint(
            base_model_id=grpo_checkpoint.parent_sft.model_id,
            base_model_revision=grpo_checkpoint.parent_sft.model_revision,
            parent_sft_adapter_dir=grpo_checkpoint.parent_sft.checkpoint_dir,
            grpo_adapter_dir=grpo_checkpoint.checkpoint_dir,
            device=config.device,
            config=config.generation,
        )
    run_summary = run_pass1_evaluation(
        config=config,
        model_id=model_id,
        generator=generator,
        executor=executor,
        run_id=str(args.run_name),
        output_root=Path(str(args.output_dir)),
        seed=int(args.seed),
    )
    aggregate_summary = aggregate_evaluation_run(
        run_summary.results_path.parent.parent,
        bootstrap_seed=int(args.seed),
    )
    print(
        f"evaluated {run_summary.total_problems} problems "
        f"(resumed={run_summary.completed_before_run}, generated={run_summary.generated_this_run})"
    )
    print(f"results={run_summary.results_path}")
    print(f"summary={aggregate_summary.summary_path}")
    print(f"main_results={aggregate_summary.main_results_path}")
    return 0


def _aggregate_eval(args: argparse.Namespace) -> int:
    """Aggregate one completed verification run without model or Piston work."""
    summary = aggregate_evaluation_run(Path(str(args.run_dir)), bootstrap_seed=int(args.seed))
    print(f"aggregated {summary.total_problems} problems")
    print(f"summary={summary.summary_path}")
    print(f"main_results={summary.main_results_path}")
    return 0


def _prevalidate_sft(args: argparse.Namespace) -> int:
    """Run the visible-only SFT data gate on a non-training Piston host."""
    config = load_sft_training_config(Path(str(args.config)))
    if args.dataset_dir is not None:
        prepared_dir = Path(str(args.dataset_dir))
        dataset_path = prepared_dir / "training" / "sft.jsonl"
        validation_dataset_path = (
            None if config.eval_strategy == "no" else prepared_dir / "training" / "sft_validation.jsonl"
        )
        print(f"override: dataset_path: {config.dataset_path} -> {dataset_path}", file=sys.stderr)
        if config.eval_strategy != "no":
            print(
                f"override: validation_dataset_path: {config.validation_dataset_path} -> {validation_dataset_path}",
                file=sys.stderr,
            )
        config = replace(
            config,
            dataset_path=dataset_path,
            validation_dataset_path=validation_dataset_path,
        )

    workers = int(args.workers)
    progress_every = int(args.progress_every)

    def progress(split: str, completed: int, total: int, elapsed_seconds: float) -> None:
        rate = completed / elapsed_seconds if elapsed_seconds > 0 else 0.0
        print(
            f"prevalidation-progress split={split} completed={completed}/{total} "
            f"elapsed_seconds={elapsed_seconds:.1f} rate={rate:.2f}_records_per_second",
            file=sys.stderr,
            flush=True,
        )

    print(
        f"prevalidation-start workers={workers} train={config.dataset_path} "
        f"validation={config.validation_dataset_path}",
        file=sys.stderr,
        flush=True,
    )
    summary = run_sft_prevalidation(
        dataset_path=config.dataset_path,
        validation_dataset_path=config.validation_dataset_path,
        model_id=config.model_id,
        model_revision=config.model_revision,
        max_seq_length=config.max_seq_length,
        piston_config_path=config.piston_config,
        output_manifest=Path(str(args.output_manifest)),
        workers=workers,
        progress_every=progress_every,
        progress_callback=progress,
    )
    print(
        f"prevalidated {summary.total_samples} samples "
        f"(train={summary.train_samples}, validation={summary.validation_samples}, "
        f"max_tokens={summary.max_token_count}, elapsed_seconds={summary.elapsed_seconds:.1f})"
    )
    print(f"manifest={summary.manifest_path}")
    return 0


def _train_sft(args: argparse.Namespace) -> int:
    """Run LoRA SFT only after strict off-GPU prevalidation evidence is supplied."""
    config = load_sft_training_config(Path(str(args.config)))
    if args.dataset_dir is not None:
        prepared_dir = Path(str(args.dataset_dir))
        dataset_path = prepared_dir / "training" / "sft.jsonl"
        validation_dataset_path = (
            None if config.eval_strategy == "no" else prepared_dir / "training" / "sft_validation.jsonl"
        )
        print(f"override: dataset_path: {config.dataset_path} -> {dataset_path}", file=sys.stderr)
        if config.eval_strategy != "no":
            print(
                f"override: validation_dataset_path: {config.validation_dataset_path} -> {validation_dataset_path}",
                file=sys.stderr,
            )
        config = replace(
            config,
            dataset_path=dataset_path,
            validation_dataset_path=validation_dataset_path,
        )
    if args.run_name is not None:
        run_name = str(args.run_name)
        print(f"override: run_name: {config.run_name} -> {run_name}", file=sys.stderr)
        config = replace(config, run_name=run_name)
    cli_seed = None if args.seed is None else int(args.seed)
    effective_seed = config.seed if cli_seed is None else cli_seed
    if cli_seed is not None and cli_seed != config.seed:
        print(f"override: seed: {config.seed} -> {cli_seed}", file=sys.stderr)
    resume = None if args.resume_from_checkpoint is None else Path(str(args.resume_from_checkpoint))
    summary = run_sft_training(
        config,
        output_root=Path(str(args.output_dir)),
        seed=effective_seed,
        prevalidation_manifest=Path(str(args.prevalidation_manifest)),
        resume_from_checkpoint=resume,
    )
    print(f"trained {summary.train_samples} samples (train_loss={summary.train_loss:g})")
    print(f"run_dir={summary.run_dir}")
    print(f"checkpoint_dir={summary.checkpoint_dir}")
    return 0


def _train_grpo(args: argparse.Namespace) -> int:
    """Validate one complete C/D definition pair, then run the selected mode."""
    public_config = load_grpo_training_config(Path(str(args.public_config)))
    hidden_config = load_grpo_training_config(Path(str(args.hidden_config)))
    if args.dataset_dir is not None:
        prepared_dir = Path(str(args.dataset_dir))
        public_dataset_path = prepared_dir / "training" / "public_grpo.jsonl"
        hidden_dataset_path = prepared_dir / "training" / "hidden_grpo.jsonl"
        print(f"override: public dataset_path: {public_config.dataset_path} -> {public_dataset_path}", file=sys.stderr)
        print(f"override: hidden dataset_path: {hidden_config.dataset_path} -> {hidden_dataset_path}", file=sys.stderr)
        public_config = replace(public_config, dataset_path=public_dataset_path)
        hidden_config = replace(hidden_config, dataset_path=hidden_dataset_path)
    if (args.public_run_name is None) != (args.hidden_run_name is None):
        raise GRPOTrainingError("--public-run-name and --hidden-run-name must be provided together")
    if args.public_run_name is not None:
        public_run_name = str(args.public_run_name)
        hidden_run_name = str(args.hidden_run_name)
        print(f"override: public run_name: {public_config.run_name} -> {public_run_name}", file=sys.stderr)
        print(f"override: hidden run_name: {hidden_config.run_name} -> {hidden_run_name}", file=sys.stderr)
        public_config = replace(public_config, run_name=public_run_name)
        hidden_config = replace(hidden_config, run_name=hidden_run_name)
    selected_config = public_config if args.reward_mode == "public" else hidden_config
    cli_seed = None if args.seed is None else int(args.seed)
    effective_seed = selected_config.seed if cli_seed is None else cli_seed
    if cli_seed is not None and cli_seed != selected_config.seed:
        print(f"override: seed: {selected_config.seed} -> {cli_seed}", file=sys.stderr)
    piston_config = load_piston_executor_config(selected_config.piston_config)
    executor = PistonExecutor(piston_config)
    executor.validate_runtime()
    resume = None if args.resume_from_checkpoint is None else Path(str(args.resume_from_checkpoint))
    resume_run_git_commit = None if args.resume_run_git_commit is None else str(args.resume_run_git_commit)
    summary = run_grpo_training(
        public_config,
        hidden_config,
        reward_mode=str(args.reward_mode),
        public_sft_run_dir=Path(str(args.public_sft_run_dir)),
        hidden_sft_run_dir=Path(str(args.hidden_sft_run_dir)),
        output_root=Path(str(args.output_dir)),
        seed=effective_seed,
        executor=executor,
        resume_from_checkpoint=resume,
        resume_run_git_commit=resume_run_git_commit,
    )
    print(
        f"trained {summary.train_samples} samples "
        f"(train_loss={summary.train_loss:g}, reward_mode={summary.reward_mode})"
    )
    print(f"run_dir={summary.run_dir}")
    print(f"checkpoint_dir={summary.checkpoint_dir}")
    return 0


def _analyze_results(args: argparse.Namespace) -> int:
    """Generate strict traceable A-D report inputs from one analysis manifest."""
    config = load_analysis_config(Path(str(args.manifest)))
    summary = analyze_experiment(config, output_dir=Path(str(args.output_dir)))
    print(f"analyzed {summary.total_problems} problems")
    print(f"report_data={summary.report_data_path}")
    print(f"main_results={summary.main_results_path}")
    print(f"paired_comparisons={summary.paired_comparisons_path}")
    print(f"costs={summary.cost_path}")
    print(f"candidates={summary.candidate_count} manual_labels={summary.manual_label_count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CodeVerifier command-line parser with WP0-WP8 commands."""
    parser = argparse.ArgumentParser(
        prog="code-verifier",
        description="Open-R1 CodeVerifier project commands.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", title="commands")
    environment_parser = subparsers.add_parser(
        "record-environment",
        help="record Git and dependency versions as JSON",
    )
    environment_parser.add_argument(
        "--output",
        type=Path,
        default=Path("environment.json"),
        help="output JSON path (default: environment.json)",
    )
    _add_common_arguments(environment_parser)
    environment_parser.set_defaults(handler=_record_environment)

    prepare_parser = subparsers.add_parser(
        "prepare-data",
        help="prepare canonical, Dataset, and training-safe WP1 artifacts",
    )
    _add_common_arguments(prepare_parser, config_required=True)
    prepare_parser.set_defaults(handler=_prepare_data)

    check_parser = subparsers.add_parser(
        "check-data",
        help="verify an existing WP1 prepared dataset",
    )
    check_parser.add_argument("--dataset", type=Path, required=True, help="prepared dataset root to verify")
    _add_common_arguments(check_parser, output_dir_default=Path("outputs/check-data"))
    check_parser.set_defaults(handler=_check_data)

    parse_parser = subparsers.add_parser(
        "parse-code",
        help="extract the deterministic final Python fenced code block",
    )
    parse_parser.add_argument(
        "--completion-file",
        default="-",
        help="UTF-8 completion file path, or '-' for stdin (default: -)",
    )
    parse_parser.add_argument(
        "--expected-function-name",
        default=None,
        help="optional top-level function name to validate",
    )
    _add_common_arguments(parse_parser)
    parse_parser.set_defaults(handler=_parse_code)

    execute_parser = subparsers.add_parser(
        "execute-batch",
        help="execute strict JSONL requests with bounded loopback Piston concurrency",
    )
    execute_parser.add_argument("--requests", type=Path, required=True, help="strict UTF-8 JSONL request path")
    execute_parser.add_argument(
        "--workload-mode",
        choices=[mode.value for mode in ExecutionWorkloadMode],
        default=ExecutionWorkloadMode.EVALUATION.value,
        help="execution workload mode (default: evaluation)",
    )
    execute_parser.add_argument("--max-concurrency", type=int, default=None, help="optional YAML concurrency override")
    execute_parser.add_argument(
        "--cache-mode",
        choices=[mode.value for mode in ExecutionCacheMode],
        default=None,
        help="optional YAML cache policy override",
    )
    execute_parser.add_argument(
        "--cache-path",
        type=Path,
        default=None,
        help="SQLite cache path for enabled cache modes",
    )
    _add_common_arguments(execute_parser, config_required=True)
    execute_parser.set_defaults(handler=_execute_batch)

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="run deterministic resumable pass@1 model evaluation",
    )
    model_source = evaluate_parser.add_mutually_exclusive_group(required=True)
    model_source.add_argument("--model-id", type=_nonempty_model_id, help="base model or checkpoint id")
    model_source.add_argument(
        "--sft-run-dir",
        type=Path,
        help="completed SFT run containing the PEFT checkpoint to evaluate",
    )
    model_source.add_argument(
        "--grpo-run-dir",
        type=Path,
        help="completed GRPO run containing the C/D PEFT checkpoint to evaluate",
    )
    evaluate_parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="optional prepared dataset root override for this evaluation run",
    )
    evaluate_parser.add_argument("--run-name", type=_safe_run_name, required=True, help="safe evaluation run id")
    _add_common_arguments(
        evaluate_parser,
        config_required=True,
        output_dir_default=_default_artifact_output(),
        output_dir_required=False,
    )
    evaluate_parser.set_defaults(handler=_evaluate)

    generate_eval_parser = subparsers.add_parser(
        "generate-eval",
        help="generate a resumable evaluation bundle without contacting Piston",
    )
    generation_source = generate_eval_parser.add_mutually_exclusive_group(required=True)
    generation_source.add_argument("--model-id", type=_nonempty_model_id, help="base model or checkpoint id")
    generation_source.add_argument(
        "--sft-run-dir",
        type=Path,
        help="completed SFT run containing the PEFT checkpoint to generate from",
    )
    generation_source.add_argument(
        "--grpo-run-dir",
        type=Path,
        help="completed GRPO run containing the C/D PEFT checkpoint to generate from",
    )
    generate_eval_parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="optional prepared dataset root override",
    )
    generate_eval_parser.add_argument("--run-name", type=_safe_run_name, required=True, help="safe evaluation run id")
    _add_common_arguments(
        generate_eval_parser,
        config_required=True,
        output_dir_default=_default_artifact_output(),
        output_dir_required=False,
    )
    generate_eval_parser.set_defaults(handler=_generate_eval)

    verify_eval_parser = subparsers.add_parser(
        "verify-eval",
        help="verify a completed generation bundle through local Piston",
    )
    verify_eval_parser.add_argument(
        "--generation-run-dir",
        type=Path,
        required=True,
        help="completed generation/<run> bundle directory",
    )
    verify_eval_parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="optional prepared dataset root override",
    )
    verify_eval_parser.add_argument("--run-name", type=_safe_run_name, required=True, help="same run id as the bundle")
    verify_eval_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="bounded concurrent local-Piston verification workers (default: 4, maximum: 32)",
    )
    _add_common_arguments(
        verify_eval_parser,
        config_required=True,
        output_dir_default=_default_artifact_output(),
        output_dir_required=False,
    )
    verify_eval_parser.set_defaults(handler=_verify_eval)

    aggregate_eval_parser = subparsers.add_parser(
        "aggregate-eval",
        help="aggregate one completed evaluation run without generation or Piston work",
    )
    aggregate_eval_parser.add_argument(
        "--run-dir", type=Path, required=True, help="completed evaluation run directory"
    )
    aggregate_eval_parser.add_argument("--seed", type=int, default=42, help="bootstrap seed (default: 42)")
    aggregate_eval_parser.add_argument("--log-level", default="INFO", help="standard logging level (default: INFO)")
    aggregate_eval_parser.set_defaults(handler=_aggregate_eval)

    prevalidate_sft_parser = subparsers.add_parser(
        "prevalidate-sft",
        help="validate SFT trajectories through local Piston and write a durable manifest",
    )
    prevalidate_sft_parser.add_argument("--config", type=Path, required=True, help="SFT YAML config path")
    prevalidate_sft_parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="optional prepared dataset root override for SFT train/validation artifacts",
    )
    prevalidate_sft_parser.add_argument(
        "--output-manifest",
        type=Path,
        required=True,
        help="new immutable prevalidation manifest path",
    )
    prevalidate_sft_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="bounded concurrent Piston workers (default: 4, maximum: 32)",
    )
    prevalidate_sft_parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="print progress after this many completed records (default: 25)",
    )
    prevalidate_sft_parser.add_argument("--log-level", default="INFO", help="standard logging level (default: INFO)")
    prevalidate_sft_parser.set_defaults(handler=_prevalidate_sft)

    train_sft_parser = subparsers.add_parser(
        "train-sft",
        help="run visible-validated LoRA supervised fine-tuning",
    )
    train_sft_parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="optional prepared dataset root override for SFT train/validation artifacts",
    )
    train_sft_parser.add_argument(
        "--run-name",
        type=_safe_run_name,
        default=None,
        help="optional safe SFT run id override",
    )
    train_sft_parser.add_argument(
        "--prevalidation-manifest",
        type=Path,
        required=True,
        help="completed off-GPU SFT prevalidation manifest",
    )
    train_sft_parser.add_argument(
        "--resume-from-checkpoint",
        type=Path,
        default=None,
        help="explicit checkpoint directory to resume",
    )
    _add_common_arguments(
        train_sft_parser,
        config_required=True,
        output_dir_default=_default_artifact_output("sft"),
        output_dir_required=False,
        seed_default=None,
    )
    train_sft_parser.set_defaults(handler=_train_sft)

    train_grpo_parser = subparsers.add_parser(
        "train-grpo",
        help="validate a fair C/D pair and run one GRPO reward mode",
    )
    train_grpo_parser.add_argument(
        "--public-config",
        type=Path,
        required=True,
        help="Public GRPO YAML config path",
    )
    train_grpo_parser.add_argument(
        "--hidden-config",
        type=Path,
        required=True,
        help="Hidden GRPO YAML config path",
    )
    train_grpo_parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="optional prepared dataset root override for the complete Public/Hidden pair",
    )
    train_grpo_parser.add_argument(
        "--public-run-name",
        type=_safe_run_name,
        default=None,
        help="optional safe Public GRPO run id override; requires --hidden-run-name",
    )
    train_grpo_parser.add_argument(
        "--hidden-run-name",
        type=_safe_run_name,
        default=None,
        help="optional safe Hidden GRPO run id override; requires --public-run-name",
    )
    train_grpo_parser.add_argument(
        "--public-sft-run-dir",
        type=Path,
        required=True,
        help="completed SFT B run bound to the Public definition",
    )
    train_grpo_parser.add_argument(
        "--hidden-sft-run-dir",
        type=Path,
        required=True,
        help="completed SFT B run bound to the Hidden definition",
    )
    train_grpo_parser.add_argument(
        "--reward-mode",
        choices=("public", "hidden"),
        required=True,
        help="validated pair member to execute",
    )
    train_grpo_parser.add_argument(
        "--resume-from-checkpoint",
        type=Path,
        default=None,
        help="explicit checkpoint directory to resume",
    )
    train_grpo_parser.add_argument(
        "--resume-run-git-commit",
        default=None,
        help="explicit preserved run commit required when resuming across a later operator/code commit",
    )
    train_grpo_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="deterministic seed (default: paired config seed)",
    )
    train_grpo_parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_artifact_output("grpo"),
        help="command output root; defaults honor CODE_VERIFIER_ARTIFACT_ROOT",
    )
    train_grpo_parser.add_argument("--log-level", default="INFO", help="standard logging level (default: INFO)")
    train_grpo_parser.set_defaults(handler=_train_grpo)

    analyze_parser = subparsers.add_parser(
        "analyze-results",
        help="validate A-D artifacts and generate traceable report inputs",
    )
    analyze_parser.add_argument("--manifest", type=Path, required=True, help="strict analysis YAML manifest")
    analyze_parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_artifact_output("analysis"),
        help="new analysis output directory; defaults honor CODE_VERIFIER_ARTIFACT_ROOT",
    )
    analyze_parser.add_argument("--log-level", default="INFO", help="standard logging level (default: INFO)")
    analyze_parser.set_defaults(handler=_analyze_results)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler_value = getattr(args, "handler", None)
    if handler_value is None:
        parser.print_help()
        return 0

    handler = cast(CommandHandler, handler_value)
    try:
        _configure_logging(str(args.log_level))
    except ValueError as error:
        print(f"error: {' '.join(str(error).splitlines())}", file=sys.stderr)
        return 2

    try:
        return handler(args)
    except DATA_ERRORS + EXECUTION_ERRORS + EVALUATION_ERRORS + TRAINING_ERRORS + ANALYSIS_ERRORS as error:
        print(f"error: {' '.join(str(error).splitlines())}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
