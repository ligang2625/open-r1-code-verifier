"""Tests for the WP0 and WP1 command-line interface."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

from code_verifier import cli as cli_module
from code_verifier.cli import build_parser, main
from code_verifier.config import ConfigError
from code_verifier.data.leakage_checks import TrainingArtifactKind
from code_verifier.data.prepare import DataPreparationConfig, DataPreparationError, PreparationSummary
from code_verifier.data.split_tests import TestSplitConfig as SplitConfig
from code_verifier.execution import (
    BatchExecutionError,
    BatchExecutionItemResult,
    BatchExecutionResult,
    BatchExecutorConfig,
    ExecutionCacheMode,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTestLayer,
    ExecutionWorkloadMode,
    PistonExecutor,
)
from code_verifier.execution import TestCaseResult as ExecutionTestCaseResult


def test_help_lists_environment_command() -> None:
    """The root help exposes the WP0 environment command."""
    help_text = build_parser().format_help()

    assert "record-environment" in help_text


def test_root_help_lists_wp1_commands() -> None:
    """The root help exposes both WP1 data commands."""
    help_text = build_parser().format_help()

    assert "prepare-data" in help_text
    assert "check-data" in help_text


def test_root_help_lists_wp2_parse_command() -> None:
    """The root help exposes the WP2 parser command."""
    assert "parse-code" in build_parser().format_help()


def test_no_command_prints_help(capsys: Any) -> None:
    """Invoking the CLI without a command is a successful help operation."""
    assert main([]) == 0

    output = capsys.readouterr()
    assert "Open-R1 CodeVerifier project commands" in output.out


@pytest.mark.parametrize("command", ["record-environment", "prepare-data", "check-data", "parse-code"])
def test_all_subcommands_expose_common_arguments(command: str, capsys: Any) -> None:
    """Every command advertises the common WP1 CLI options."""
    with pytest.raises(SystemExit) as error:
        main([command, "--help"])

    assert error.value.code == 0
    help_text = capsys.readouterr().out
    for option in ("--help", "--config", "--seed", "--output-dir", "--log-level"):
        assert option in help_text


@pytest.mark.parametrize(
    "argv",
    [
        ["prepare-data", "--output-dir", "prepared"],
        ["prepare-data", "--config", "config.yaml"],
    ],
)
def test_prepare_data_requires_config_and_output_dir(argv: list[str]) -> None:
    """prepare-data rejects either missing required path at parse time."""
    with pytest.raises(SystemExit) as error:
        main(argv)

    assert error.value.code == 2


def _summary(root: Path) -> PreparationSummary:
    return PreparationSummary(
        total_problems=20,
        split_counts={"train": 12, "validation": 4, "test": 4},
        canonical_jsonl=root / "canonical" / "problems.jsonl",
        hf_dataset_dir=root / "hf_dataset",
        training_artifacts={kind: root / "training" / f"{kind.value}.jsonl" for kind in TrainingArtifactKind},
    )


def test_prepare_data_handler_forwards_seed_and_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """prepare-data forwards parsed config, seed, and output root to the pipeline."""
    config_path = tmp_path / "config.yaml"
    output_dir = tmp_path / "prepared"
    config = DataPreparationConfig(
        input_path=tmp_path / "raw.jsonl",
        input_format="raw_jsonl",
        test_split=SplitConfig(visible_count=2, train_hidden_count=2, eval_hidden_count=2),
        output_formats=("jsonl",),
    )
    seen: dict[str, object] = {}

    def fake_load(path: Path) -> DataPreparationConfig:
        seen["config_path"] = path
        return config

    def fake_prepare(
        received_config: DataPreparationConfig,
        *,
        seed: int,
        output_dir: Path,
    ) -> PreparationSummary:
        seen["config"] = received_config
        seen["seed"] = seed
        seen["output_dir"] = output_dir
        return _summary(output_dir)

    monkeypatch.setattr("code_verifier.cli.load_data_preparation_config", fake_load)
    monkeypatch.setattr("code_verifier.cli.prepare_data", fake_prepare)

    assert (
        main(
            [
                "prepare-data",
                "--config",
                str(config_path),
                "--seed",
                "17",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    assert seen == {
        "config_path": config_path,
        "config": config,
        "seed": 17,
        "output_dir": output_dir,
    }


def test_check_data_handler_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: Any,
) -> None:
    """check-data reports only counts and artifact paths."""
    dataset = tmp_path / "prepared"
    monkeypatch.setattr("code_verifier.cli.check_prepared_data", lambda path: _summary(path))

    assert main(["check-data", "--dataset", str(dataset)]) == 0
    output = capsys.readouterr().out
    assert "checked 20 problems (train=12, validation=4, test=4)" in output
    assert str(dataset / "canonical" / "problems.jsonl") in output


def test_data_error_returns_two_without_hidden_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: Any,
) -> None:
    """Expected data failures return two and do not print hidden test values."""
    hidden_payload = "SECRET-HIDDEN-VALUE"

    def fail(_: Path) -> PreparationSummary:
        raise DataPreparationError("dataset validation failed")

    monkeypatch.setattr("code_verifier.cli.check_prepared_data", fail)

    assert main(["check-data", "--dataset", str(tmp_path)]) == 2
    output = capsys.readouterr()
    assert "dataset validation failed" in output.err
    assert hidden_payload not in output.err


def test_record_environment_behavior_remains_compatible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """WP0 environment recording keeps forwarding the requested output path."""
    output = tmp_path / "environment.json"
    seen: list[Path] = []
    monkeypatch.setattr("code_verifier.cli.write_environment_record", seen.append)

    assert main(["record-environment", "--output", str(output)]) == 0
    assert seen == [output]


def test_parse_code_reads_stdin_and_emits_success_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    """parse-code reads '-' from stdin and emits exactly the ParseResult JSON fields."""
    monkeypatch.setattr(
        "code_verifier.cli.sys.stdin",
        StringIO("```python\ndef solve(value):\n    return value\n```\n"),
    )

    assert main(["parse-code", "--completion-file", "-", "--expected-function-name", "solve"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"success", "code", "error_type", "num_code_blocks"}
    assert payload == {
        "success": True,
        "code": "def solve(value):\n    return value\n",
        "error_type": None,
        "num_code_blocks": 1,
    }


def test_parse_code_reads_file_and_forwards_expected_function(tmp_path: Path, capsys: Any) -> None:
    """parse-code reads UTF-8 files and applies target-function validation."""
    completion = tmp_path / "completion.txt"
    completion.write_text("```python\ndef other():\n    return 1\n```\n", encoding="utf-8")

    assert (
        main(
            [
                "parse-code",
                "--completion-file",
                str(completion),
                "--expected-function-name",
                "solve",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_type"] == "missing_target_function"
    assert payload["code"] == ""


def test_parse_code_failure_emits_json_and_returns_one(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """Structured parser failures remain machine-readable on stdout."""
    monkeypatch.setattr("code_verifier.cli.sys.stdin", StringIO("explanation only"))

    assert main(["parse-code"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "success": False,
        "code": "",
        "error_type": "no_supported_code_block",
        "num_code_blocks": 0,
    }


def test_parse_code_null_byte_file_returns_structured_failure(tmp_path: Path, capsys: Any) -> None:
    """AST text failures remain JSON parser failures rather than CLI tracebacks."""
    completion = tmp_path / "null-byte.txt"
    completion.write_text("```python\ndef solve():\n    return 1\x00\n```\n", encoding="utf-8")

    assert (
        main(
            [
                "parse-code",
                "--completion-file",
                str(completion),
                "--expected-function-name",
                "solve",
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.err == ""
    assert "Traceback" not in output.err
    assert json.loads(output.out) == {
        "success": False,
        "code": "",
        "error_type": "invalid_python_syntax",
        "num_code_blocks": 1,
    }


def test_parse_code_deep_unary_file_returns_structured_failure(tmp_path: Path, capsys: Any) -> None:
    """AST complexity failures remain JSON parser failures rather than CLI tracebacks."""
    completion = tmp_path / "deep-unary.txt"
    completion.write_text(
        f"```python\ndef solve():\n    return {'+' * 10_000}1\n```\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "parse-code",
                "--completion-file",
                str(completion),
                "--expected-function-name",
                "solve",
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.err == ""
    assert "Traceback" not in output.err
    assert json.loads(output.out) == {
        "success": False,
        "code": "",
        "error_type": "invalid_python_syntax",
        "num_code_blocks": 1,
    }


def test_parse_code_missing_file_returns_two_without_traceback(tmp_path: Path, capsys: Any) -> None:
    """Input I/O failures use exit code two and a concise stderr error."""
    missing = tmp_path / "missing.txt"

    assert main(["parse-code", "--completion-file", str(missing)]) == 2
    output = capsys.readouterr()
    assert str(missing) in output.err
    assert "Traceback" not in output.err
    assert output.out == ""


def test_wp1_command_defaults_remain_compatible_after_common_argument_refactor() -> None:
    """The common option refactor preserves WP1 required and default values."""
    parser = build_parser()
    check_args = parser.parse_args(["check-data", "--dataset", "prepared"])
    parse_args = parser.parse_args(["parse-code"])

    assert check_args.output_dir == Path("outputs/check-data")
    assert parse_args.output_dir is None
    with pytest.raises(SystemExit) as error:
        parser.parse_args(["prepare-data", "--config", "config.yaml"])
    assert error.value.code == 2


def _cli_execution_result(status: ExecutionStatus = ExecutionStatus.PASSED) -> ExecutionResult:
    passed = status is ExecutionStatus.PASSED
    return ExecutionResult(
        status=status,
        passed_tests=1 if passed else 0,
        total_tests=1,
        pass_rate=1.0 if passed else 0.0,
        runtime_ms=1.0,
        test_results=[
            ExecutionTestCaseResult(
                status=status,
                passed=passed,
                runtime_ms=1.0,
                stdout="",
                stderr="batch executor failed" if status is ExecutionStatus.SANDBOX_ERROR else "",
            )
        ],
    )


def _cli_batch_result(statuses: list[ExecutionStatus]) -> BatchExecutionResult:
    items = [
        BatchExecutionItemResult(
            request_id=f"request-{index}",
            problem_id=f"problem-{index}",
            test_layer=ExecutionTestLayer.VISIBLE,
            cache_hit=False,
            result=_cli_execution_result(status),
        )
        for index, status in enumerate(statuses)
    ]
    return BatchExecutionResult(
        executor_version="executor-v1",
        max_concurrency=2,
        cache_mode=ExecutionCacheMode.DISABLED,
        workload_mode=ExecutionWorkloadMode.EVALUATION,
        total_requests=len(items),
        cache_hits=0,
        runtime_ms=2.0,
        items=items,
    )


def test_execute_batch_help_includes_common_and_batch_arguments(capsys: Any) -> None:
    with pytest.raises(SystemExit) as error:
        main(["execute-batch", "--help"])
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    for option in (
        "--help",
        "--config",
        "--seed",
        "--output-dir",
        "--log-level",
        "--requests",
        "--workload-mode",
        "--max-concurrency",
        "--cache-mode",
        "--cache-path",
    ):
        assert option in help_text


def test_load_batch_requests_rejects_empty_blank_duplicate_key_and_invalid_record(tmp_path: Path) -> None:
    cases = [
        "",
        "\n",
        '{"request_id":"a","request_id":"b"}\n',
        '{"request_id":"a"}\n',
    ]
    for index, contents in enumerate(cases):
        path = tmp_path / f"invalid-{index}.jsonl"
        path.write_text(contents, encoding="utf-8")
        with pytest.raises(BatchExecutionError):
            cli_module._load_batch_requests(path)


def test_load_batch_requests_error_does_not_echo_code_or_test_sentinel(tmp_path: Path) -> None:
    sentinel = "PRIVATE_BATCH_INPUT_SENTINEL"
    path = tmp_path / "requests.jsonl"
    path.write_text(
        json.dumps(
            {
                "request_id": "request-1",
                "problem_id": "problem-1",
                "test_layer": "visible",
                "code": sentinel,
                "function_name": "target",
                "tests": [{"input": sentinel}],
                "timeout_seconds": 1.0,
                "memory_limit_mb": 64,
            },
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BatchExecutionError) as exc_info:
        cli_module._load_batch_requests(path)
    assert sentinel not in str(exc_info.value)
    assert "line 1" in str(exc_info.value)


def test_execute_batch_rejects_cache_path_mode_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: Any,
) -> None:
    requests = Path("tests/fixtures/wp3c/batch_requests.jsonl")
    output = tmp_path / "output"
    assert (
        main(
            [
                "execute-batch",
                "--config",
                "configs/execution/batch-local.yaml",
                "--requests",
                str(requests),
                "--output-dir",
                str(output),
                "--cache-path",
                str(tmp_path / "cache.sqlite3"),
            ]
        )
        == 2
    )
    assert "cache path is not allowed" in capsys.readouterr().err
    assert not output.exists()

    monkeypatch.setattr(PistonExecutor, "validate_runtime", lambda self: "3.10.0")
    assert (
        main(
            [
                "execute-batch",
                "--config",
                "configs/execution/batch-local.yaml",
                "--requests",
                str(requests),
                "--output-dir",
                str(output),
                "--cache-mode",
                "read_only",
            ]
        )
        == 2
    )
    assert "cache path is required" in capsys.readouterr().err


def test_execute_batch_rejects_training_cache_before_piston_or_cache_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: Any,
) -> None:
    seen: list[str] = []

    class UnexpectedPistonExecutor:
        def __init__(self, config: object) -> None:
            del config
            seen.append("piston")

    class UnexpectedCache:
        def __init__(self, path: Path) -> None:
            del path
            seen.append("cache")

    class UnexpectedBatchExecutor:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            seen.append("batch")

    monkeypatch.setattr(cli_module, "PistonExecutor", UnexpectedPistonExecutor)
    monkeypatch.setattr(cli_module, "SQLiteExecutionCache", UnexpectedCache)
    monkeypatch.setattr(cli_module, "BatchExecutor", UnexpectedBatchExecutor)
    output = tmp_path / "output"
    cache_path = tmp_path / "cache.sqlite3"
    assert (
        main(
            [
                "execute-batch",
                "--config",
                "configs/execution/batch-local.yaml",
                "--requests",
                "tests/fixtures/wp3c/batch_requests.jsonl",
                "--output-dir",
                str(output),
                "--workload-mode",
                "training",
                "--cache-mode",
                "read_only",
                "--cache-path",
                str(cache_path),
            ]
        )
        == 2
    )
    assert seen == []
    assert not cache_path.exists()
    assert not output.exists()
    assert "training cache requires explicit opt-in" in capsys.readouterr().err


def test_execute_batch_applies_concurrency_and_cache_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen: dict[str, object] = {}

    class FakePistonExecutor:
        def __init__(self, config: object) -> None:
            configs = cast(list[object], seen.setdefault("piston_configs", []))
            configs.append(config)

        def validate_runtime(self) -> str:
            seen["validated"] = True
            return "3.10.0"

    class FakeCache:
        def __init__(self, path: Path) -> None:
            seen["cache_path"] = path

        def close(self) -> None:
            seen["cache_closed"] = True

    class FakeBatchExecutor:
        def __init__(self, factory: object, *, executor_version: str, config: object, cache: object) -> None:
            del factory
            seen["executor_version"] = executor_version
            seen["batch_config"] = config
            seen["cache"] = cache

        def execute_batch(self, requests: object, *, workload_mode: object) -> BatchExecutionResult:
            seen["requests"] = requests
            seen["workload_mode"] = workload_mode
            return _cli_batch_result([ExecutionStatus.PASSED])

    monkeypatch.setattr(cli_module, "PistonExecutor", FakePistonExecutor)
    monkeypatch.setattr(cli_module, "SQLiteExecutionCache", FakeCache)
    monkeypatch.setattr(cli_module, "BatchExecutor", FakeBatchExecutor)
    monkeypatch.setattr(cli_module, "piston_executor_version", lambda config: "executor-v1")
    output = tmp_path / "output"
    cache = tmp_path / "cache.sqlite3"
    assert (
        main(
            [
                "execute-batch",
                "--config",
                "configs/execution/batch-local.yaml",
                "--requests",
                "tests/fixtures/wp3c/batch_requests.jsonl",
                "--output-dir",
                str(output),
                "--max-concurrency",
                "7",
                "--cache-mode",
                "read_write",
                "--cache-path",
                str(cache),
                "--workload-mode",
                "training",
            ]
        )
        == 0
    )
    batch_config = cast(BatchExecutorConfig, seen["batch_config"])
    assert batch_config.max_concurrency == 7
    assert batch_config.cache_mode is ExecutionCacheMode.READ_WRITE
    assert seen["workload_mode"] is ExecutionWorkloadMode.TRAINING
    assert seen["cache_path"] == cache
    assert seen["cache_closed"] is True


def test_execute_batch_writes_exact_results_and_summary_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "output"
    result = _cli_batch_result([ExecutionStatus.PASSED, ExecutionStatus.WRONG_ANSWER])
    cli_module._write_batch_outputs(result, output)
    assert sorted(path.name for path in output.iterdir()) == ["results.jsonl", "summary.json"]
    lines = output.joinpath("results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["request_id"] for line in lines] == ["request-0", "request-1"]
    summary = json.loads(output.joinpath("summary.json").read_text(encoding="utf-8"))
    assert summary["total_requests"] == 2
    assert summary["status_counts"]["passed"] == 1
    assert summary["status_counts"]["wrong_answer"] == 1
    assert summary["results_file"] == "results.jsonl"


def test_execute_batch_outputs_omit_code_input_and_expected(tmp_path: Path) -> None:
    output = tmp_path / "output"
    cli_module._write_batch_outputs(_cli_batch_result([ExecutionStatus.PASSED]), output)
    encoded = output.joinpath("results.jsonl").read_text(encoding="utf-8")
    for forbidden in ("code", "tests", "input", "expected"):
        assert f'"{forbidden}"' not in encoded


def test_execute_batch_returns_zero_for_model_failures_one_for_sandbox_error_two_for_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakePistonExecutor:
        def __init__(self, config: object) -> None:
            del config

        def validate_runtime(self) -> str:
            return "3.10.0"

    results = [
        _cli_batch_result([ExecutionStatus.WRONG_ANSWER]),
        _cli_batch_result([ExecutionStatus.SANDBOX_ERROR]),
    ]

    class FakeBatchExecutor:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def execute_batch(self, requests: object, *, workload_mode: object) -> BatchExecutionResult:
            del requests, workload_mode
            return results.pop(0)

    monkeypatch.setattr(cli_module, "PistonExecutor", FakePistonExecutor)
    monkeypatch.setattr(cli_module, "BatchExecutor", FakeBatchExecutor)
    monkeypatch.setattr(cli_module, "piston_executor_version", lambda config: "executor-v1")
    base = [
        "execute-batch",
        "--config",
        "configs/execution/batch-local.yaml",
        "--requests",
        "tests/fixtures/wp3c/batch_requests.jsonl",
    ]
    assert main([*base, "--output-dir", str(tmp_path / "model")]) == 0
    assert main([*base, "--output-dir", str(tmp_path / "sandbox")]) == 1

    def fail_config(path: Path) -> object:
        del path
        raise ConfigError("fixed")

    monkeypatch.setattr(cli_module, "load_batch_execution_config", fail_config)
    assert main([*base, "--output-dir", str(tmp_path / "infra")]) == 2


def test_execute_batch_refuses_any_existing_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(BatchExecutionError, match="already exist"):
        cli_module._write_batch_outputs(_cli_batch_result([ExecutionStatus.PASSED]), output)


def test_execute_batch_rejects_cache_path_inside_output_directory(tmp_path: Path, capsys: Any) -> None:
    output = tmp_path / "output"
    assert (
        main(
            [
                "execute-batch",
                "--config",
                "configs/execution/batch-local.yaml",
                "--requests",
                "tests/fixtures/wp3c/batch_requests.jsonl",
                "--output-dir",
                str(output),
                "--cache-mode",
                "read_write",
                "--cache-path",
                str(output / "cache.sqlite3"),
            ]
        )
        == 2
    )
    assert "must not be inside" in capsys.readouterr().err
    assert not output.exists()


def test_execute_batch_partial_write_failure_leaves_no_final_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    original_write_text = Path.write_text

    def fail_summary(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if path.name == "summary.json":
            raise OSError("fixed write failure")
        return original_write_text(path, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", fail_summary)
    with pytest.raises(OSError, match="fixed write failure"):
        cli_module._write_batch_outputs(_cli_batch_result([ExecutionStatus.PASSED]), output)
    assert not output.exists()
    assert not list(tmp_path.glob(".output.*"))
