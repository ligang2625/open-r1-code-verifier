"""Tests for the WP0 and WP1 command-line interface."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from code_verifier.cli import build_parser, main
from code_verifier.data.leakage_checks import TrainingArtifactKind
from code_verifier.data.prepare import DataPreparationConfig, DataPreparationError, PreparationSummary
from code_verifier.data.split_tests import TestSplitConfig as SplitConfig


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
