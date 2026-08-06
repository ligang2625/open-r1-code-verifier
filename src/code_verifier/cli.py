"""Command-line entry point for CodeVerifier.

Example:
    python -m code_verifier.cli --help
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

from code_verifier import __version__
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
    piston_executor_version,
)
from code_verifier.parsing import extract_python_code

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


def _add_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_required: bool = False,
    output_dir_default: Path | None = None,
) -> None:
    """Add the common project options while allowing command-specific output defaults."""
    parser.add_argument(
        "--config",
        type=Path,
        required=config_required,
        help="YAML config path; required by commands that execute configured workflows",
    )
    parser.add_argument("--seed", type=int, default=42, help="deterministic seed (default: 42)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=config_required,
        default=None if config_required else output_dir_default,
        help="command output root; accepted by read-only commands for CLI consistency",
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
    """Run configured local Piston batch execution and emit non-sensitive artifacts."""
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


def build_parser() -> argparse.ArgumentParser:
    """Build the CodeVerifier command-line parser with WP0-WP3 commands."""
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
        help="execute strict JSONL requests with bounded local Piston concurrency",
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
    except DATA_ERRORS + EXECUTION_ERRORS as error:
        print(f"error: {' '.join(str(error).splitlines())}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
