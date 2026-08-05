"""Command-line entry point for CodeVerifier.

Example:
    python -m code_verifier.cli --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from code_verifier import __version__
from code_verifier.config import ConfigError
from code_verifier.data.adapters import InputAdapterError
from code_verifier.data.deduplicate import DuplicateDataError
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

CommandHandler = Callable[[argparse.Namespace], int]
DATA_ERRORS = (
    ConfigError,
    SchemaError,
    InputAdapterError,
    DuplicateDataError,
    LeakageError,
    DataPreparationError,
)


def _add_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_required: bool = False,
) -> None:
    """Add --config, --seed, --output-dir, and --log-level to one command parser."""
    parser.add_argument(
        "--config",
        type=Path,
        required=config_required,
        help="YAML config path (required for prepare-data)",
    )
    parser.add_argument("--seed", type=int, default=42, help="deterministic seed (default: 42)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=config_required,
        default=None if config_required else Path("outputs/check-data"),
        help="output root; check-data accepts it for CLI consistency and does not modify data",
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


def build_parser() -> argparse.ArgumentParser:
    """Build the CodeVerifier command-line parser with WP0 and WP1 commands."""
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
    _add_common_arguments(check_parser)
    check_parser.set_defaults(handler=_check_data)
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
    except DATA_ERRORS as error:
        print(f"error: {' '.join(str(error).splitlines())}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
