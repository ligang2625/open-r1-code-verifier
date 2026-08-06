"""Unit tests for the trusted Python function harness protocol."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from code_verifier.execution.harness import (
    HarnessReport,
    PythonTestProgram,
    build_python_test_program,
    parse_harness_report,
)

_MARKER = "abc123def456"


def _program(code: str, input_value: object, expected: object, *, max_output_bytes: int = 256) -> PythonTestProgram:
    return build_python_test_program(
        code,
        "target",
        {"input": input_value, "expected": expected},
        marker=_MARKER,
        max_output_bytes=max_output_bytes,
    )


def _run_program(tmp_path: Path, program: PythonTestProgram, *, max_output_bytes: int = 256) -> HarnessReport:
    for file_record in program.files:
        (tmp_path / file_record["name"]).write_text(file_record["content"], encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "main.py"],
        cwd=tmp_path,
        input=program.stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert completed.returncode == 0
    report = parse_harness_report(completed.stdout, marker=program.marker, max_output_bytes=max_output_bytes)
    assert report is not None
    return report


def test_build_program_uses_main_then_candidate_files() -> None:
    program = _program("def target(value):\n    return value\n", 1, 1)
    assert [file_record["name"] for file_record in program.files] == ["main.py", "candidate.py"]
    assert program.files[0]["content"].startswith("from __future__ import annotations")


def test_build_program_keeps_candidate_code_exact() -> None:
    code = "# exact whitespace\ndef target(value):\n\treturn value  \n"
    program = _program(code, "x", "x")
    assert program.files[1]["content"] == code


def test_build_program_serializes_test_only_in_stdin() -> None:
    sentinel = "EXPECTED_ONLY_SENTINEL"
    program = _program("def target(value):\n    return value\n", "input", sentinel)
    assert sentinel in program.stdin
    assert sentinel not in program.files[0]["content"]
    assert sentinel not in program.files[1]["content"]


def test_harness_list_input_uses_positional_arguments(tmp_path: Path) -> None:
    report = _run_program(tmp_path, _program("def target(left, right):\n    return left + right\n", [2, 3], 5))
    assert report.outcome == "passed"


def test_harness_dict_input_uses_keyword_arguments(tmp_path: Path) -> None:
    report = _run_program(
        tmp_path,
        _program("def target(*, left, right):\n    return left * right\n", {"left": 3, "right": 4}, 12),
    )
    assert report.outcome == "passed"


def test_harness_scalar_input_uses_single_argument(tmp_path: Path) -> None:
    report = _run_program(tmp_path, _program("def target(value):\n    return [value]\n", "x", ["x"]))
    assert report.outcome == "passed"


@pytest.mark.parametrize(
    ("actual_expression", "expected"),
    [("True", 1), ("1", 1.0), ("1.0", True)],
)
def test_harness_comparison_is_type_sensitive(
    tmp_path: Path,
    actual_expression: str,
    expected: object,
) -> None:
    report = _run_program(tmp_path, _program(f"def target(value):\n    return {actual_expression}\n", None, expected))
    assert report.outcome == "wrong_answer"


@pytest.mark.parametrize(
    ("code", "expected_outcome"),
    [
        ("def target(value):\n    return value\n", "passed"),
        ("def target(value):\n    return value + 1\n", "wrong_answer"),
        ("def target(value)\n    return value\n", "syntax_error"),
        ("def target(value):\n    raise RuntimeError('private')\n", "runtime_error"),
    ],
)
def test_harness_reports_syntax_runtime_wrong_answer_and_passed(
    tmp_path: Path,
    code: str,
    expected_outcome: str,
) -> None:
    report = _run_program(tmp_path, _program(code, 1, 1))
    assert report.outcome == expected_outcome


def test_harness_rejects_non_json_actual_as_wrong_answer(tmp_path: Path) -> None:
    report = _run_program(tmp_path, _program("def target(value):\n    return {1, 2}\n", None, None))
    assert report.outcome == "wrong_answer"


@pytest.mark.parametrize(
    "code",
    [
        (
            "import __main__\n"
            "__main__._strict_equal = lambda actual, expected: True\n"
            "def target(value):\n"
            "    return value + 999\n"
        ),
        (
            "import __main__\n"
            "_original_dumps = __main__.json.dumps\n"
            "def _fake_dumps(value, *args, **kwargs):\n"
            "    if isinstance(value, dict) and 'outcome' in value:\n"
            "        value = dict(value)\n"
            "        value['outcome'] = 'passed'\n"
            "    return _original_dumps(value, *args, **kwargs)\n"
            "__main__.json.dumps = _fake_dumps\n"
            "def target(value):\n"
            "    return value + 999\n"
        ),
        (
            "import __main__\n"
            "__main__._emit = lambda *args, **kwargs: None\n"
            "def target(value):\n"
            "    return value + 999\n"
        ),
        (
            "import sys\n"
            "class _FakeStdout:\n"
            "    def write(self, value):\n"
            "        return len(value)\n"
            "    def flush(self):\n"
            "        return None\n"
            "sys.__stdout__ = _FakeStdout()\n"
            "def target(value):\n"
            "    return value + 999\n"
        ),
        (
            "import inspect\n"
            "def target(value):\n"
            "    for frame_info in inspect.stack():\n"
            "        for local_value in frame_info.frame.f_locals.values():\n"
            "            if isinstance(local_value, dict) and (\n"
            "                'expected' in local_value or 'marker' in local_value\n"
            "            ):\n"
            "                return 2\n"
            "    return value + 999\n"
        ),
    ],
)
def test_candidate_cannot_tamper_with_parent_verdict(tmp_path: Path, code: str) -> None:
    report = _run_program(tmp_path, _program(code, 1, 2))
    assert report.outcome == "wrong_answer"


@pytest.mark.parametrize(
    "code",
    [
        "def target(value):\n    print('x' * 300)\n    return value\n",
        "import sys\ndef target(value):\n    print('x' * 300, file=sys.stderr)\n    return value\n",
    ],
)
def test_harness_bounded_stdout_and_stderr_report_output_limit(tmp_path: Path, code: str) -> None:
    report = _run_program(tmp_path, _program(code, 1, 1, max_output_bytes=64), max_output_bytes=64)
    assert report.outcome == "output_limit"
    assert len(report.stdout.encode()) <= 64
    assert len(report.stderr.encode()) <= 64


def _marker_line(payload: str, *, marker: str = _MARKER) -> str:
    return f"__CODE_VERIFIER_RESULT__:{marker}:{payload}"


def _valid_report_json(outcome: str = "passed") -> str:
    return json.dumps(
        {"outcome": outcome, "runtime_ms": 1.25, "stdout": "visible", "stderr": ""},
        separators=(",", ":"),
    )


def test_parse_report_uses_only_final_matching_marker() -> None:
    stdout = "\n".join(
        [
            _marker_line(_valid_report_json("wrong_answer")),
            "ordinary candidate output",
            _marker_line(_valid_report_json("passed")),
        ]
    )
    report = parse_harness_report(stdout, marker=_MARKER, max_output_bytes=256)
    assert report is not None
    assert report.outcome == "passed"
    assert parse_harness_report(stdout + "\ntrailing spoof", marker=_MARKER, max_output_bytes=256) is None


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        '{"outcome":"passed","outcome":"wrong_answer","runtime_ms":1,"stdout":"","stderr":""}',
        '{"outcome":"passed","runtime_ms":1,"stdout":"","stderr":"","extra":1}',
        '{"outcome":"passed","runtime_ms":NaN,"stdout":"","stderr":""}',
        '{"outcome":"unknown","runtime_ms":1,"stdout":"","stderr":""}',
    ],
)
def test_parse_report_rejects_spoof_malformed_duplicate_key_unknown_field_and_nonfinite_runtime(payload: str) -> None:
    assert parse_harness_report(_marker_line(payload), marker=_MARKER, max_output_bytes=256) is None
    assert (
        parse_harness_report(
            _marker_line(_valid_report_json(), marker="wrong"),
            marker=_MARKER,
            max_output_bytes=256,
        )
        is None
    )


def test_reports_do_not_contain_input_expected_or_traceback_sentinels(tmp_path: Path) -> None:
    input_sentinel = "PRIVATE_INPUT_SENTINEL"
    expected_sentinel = "PRIVATE_EXPECTED_SENTINEL"
    traceback_sentinel = "PRIVATE_TRACEBACK_SENTINEL"
    code = f"def target(value):\n    raise RuntimeError('{traceback_sentinel}')\n"
    report = _run_program(tmp_path, _program(code, input_sentinel, expected_sentinel))
    serialized = json.dumps(report.__dict__, sort_keys=True)
    assert report.outcome == "runtime_error"
    assert input_sentinel not in serialized
    assert expected_sentinel not in serialized
    assert traceback_sentinel not in serialized
