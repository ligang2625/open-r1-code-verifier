"""Trusted Python harness generation and bounded result parsing for Piston jobs."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias, cast

from code_verifier.execution.base import ExecutionContractError, validate_execution_request

HarnessOutcome: TypeAlias = Literal[
    "passed",
    "wrong_answer",
    "syntax_error",
    "runtime_error",
    "output_limit",
    "harness_error",
]

_ALLOWED_OUTCOMES = frozenset(
    {"passed", "wrong_answer", "syntax_error", "runtime_error", "output_limit", "harness_error"}
)
_REPORT_FIELDS = frozenset({"outcome", "runtime_ms", "stdout", "stderr"})


@dataclass(frozen=True)
class PythonTestProgram:
    """Files, stdin, and nonce marker for one isolated Python test job."""

    files: list[dict[str, str]]
    stdin: str
    marker: str


@dataclass(frozen=True)
class HarnessReport:
    """Validated result emitted by the trusted in-sandbox runner."""

    outcome: HarnessOutcome
    runtime_ms: float
    stdout: str
    stderr: str


def build_python_test_program(
    code: str,
    function_name: str,
    test: dict[str, Any],
    *,
    marker: str,
    max_output_bytes: int,
) -> PythonTestProgram:
    """Build candidate.py, trusted main.py, and stdin JSON for one isolated function test."""
    validate_execution_request(code, function_name, [test], 1.0, 1)
    _validate_marker(marker)
    _validate_output_limit(max_output_bytes)
    try:
        stdin = json.dumps(
            {
                "function_name": function_name,
                "input": test["input"],
                "expected": test["expected"],
                "marker": marker,
                "max_output_bytes": max_output_bytes,
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError):
        raise ExecutionContractError("test contains an invalid JSON value") from None
    return PythonTestProgram(
        files=[
            {"name": "main.py", "content": _TRUSTED_RUNNER_SOURCE},
            {"name": "candidate.py", "content": code},
        ],
        stdin=stdin,
        marker=marker,
    )


def parse_harness_report(
    stdout: str,
    *,
    marker: str,
    max_output_bytes: int,
) -> HarnessReport | None:
    """Parse only the final trusted marker line and return a validated bounded report."""
    if not isinstance(stdout, str):
        return None
    try:
        _validate_marker(marker)
        _validate_output_limit(max_output_bytes)
    except (ExecutionContractError, ValueError):
        return None
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    prefix = f"__CODE_VERIFIER_RESULT__:{marker}:"
    final_line = lines[-1]
    if not final_line.startswith(prefix):
        return None
    encoded = final_line[len(prefix) :]
    try:
        value = cast(
            object,
            json.loads(
                encoded,
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_json_constant,
            ),
        )
    except (json.JSONDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    report = cast(dict[str, object], value)
    if set(report) != _REPORT_FIELDS:
        return None
    outcome = report["outcome"]
    runtime_ms = report["runtime_ms"]
    captured_stdout = report["stdout"]
    captured_stderr = report["stderr"]
    if not isinstance(outcome, str) or outcome not in _ALLOWED_OUTCOMES:
        return None
    if isinstance(runtime_ms, bool) or not isinstance(runtime_ms, int | float):
        return None
    try:
        runtime_float = float(runtime_ms)
    except OverflowError:
        return None
    if not math.isfinite(runtime_float) or runtime_float < 0:
        return None
    if not isinstance(captured_stdout, str) or not isinstance(captured_stderr, str):
        return None
    if len(captured_stdout.encode("utf-8")) > max_output_bytes:
        return None
    if len(captured_stderr.encode("utf-8")) > max_output_bytes:
        return None
    return HarnessReport(
        outcome=cast(HarnessOutcome, outcome),
        runtime_ms=runtime_float,
        stdout=captured_stdout,
        stderr=captured_stderr,
    )


def _validate_marker(marker: object) -> None:
    if not isinstance(marker, str) or not marker or len(marker) > 128 or not marker.isascii() or not marker.isalnum():
        raise ExecutionContractError("marker must be a short ASCII alphanumeric string")


def _validate_output_limit(max_output_bytes: object) -> None:
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes <= 0:
        raise ExecutionContractError("max_output_bytes must be a positive integer")


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


_TRUSTED_RUNNER_SOURCE = r"""from __future__ import annotations

import contextlib
import importlib.util
import json
import math
import sys
import time
from pathlib import Path
from typing import Any


class _OutputLimit(Exception):
    pass


class _BoundedWriter:
    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._parts: list[str] = []
        self._used_bytes = 0

    def write(self, value: str) -> int:
        if not isinstance(value, str):
            raise TypeError("text output required")
        encoded_size = len(value.encode("utf-8"))
        if self._used_bytes + encoded_size > self._max_bytes:
            raise _OutputLimit
        self._parts.append(value)
        self._used_bytes += encoded_size
        return len(value)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self._parts)


def _strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_strict_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_strict_equal(actual[key], expected[key]) for key in actual)
    return bool(actual == expected)


def _json_serializable(value: Any) -> bool:
    try:
        json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError):
        return False
    return True


def _load_candidate() -> Any:
    spec = importlib.util.spec_from_file_location("candidate", Path("candidate.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _emit(marker: str, outcome: str, runtime_ms: float, stdout: str, stderr: str) -> None:
    report = json.dumps(
        {"outcome": outcome, "runtime_ms": runtime_ms, "stdout": stdout, "stderr": stderr},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    sys.__stdout__.write(f"__CODE_VERIFIER_RESULT__:{marker}:{report}\n")
    sys.__stdout__.flush()


def _main() -> None:
    trusted_json_loads = json.loads
    trusted_perf_counter = time.perf_counter
    trusted_emit = _emit
    stdout_writer: _BoundedWriter | None = None
    stderr_writer: _BoundedWriter | None = None
    start = trusted_perf_counter()
    marker = "invalid"
    outcome = "harness_error"
    try:
        payload = trusted_json_loads(sys.stdin.read())
        if not isinstance(payload, dict) or set(payload) != {
            "function_name", "input", "expected", "marker", "max_output_bytes"
        }:
            raise ValueError("invalid harness payload")
        function_name = payload["function_name"]
        marker = payload["marker"]
        max_output_bytes = payload["max_output_bytes"]
        if not isinstance(function_name, str) or not function_name.isidentifier():
            raise ValueError("invalid function name")
        if not isinstance(marker, str) or not marker or not marker.isascii() or not marker.isalnum():
            raise ValueError("invalid marker")
        if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes <= 0:
            raise ValueError("invalid output limit")
        stdout_writer = _BoundedWriter(max_output_bytes)
        stderr_writer = _BoundedWriter(max_output_bytes)
        try:
            with contextlib.redirect_stdout(stdout_writer), contextlib.redirect_stderr(stderr_writer):
                module = _load_candidate()
                target = getattr(module, function_name)
                if not callable(target):
                    raise TypeError("target is not callable")
                input_value = payload["input"]
                if isinstance(input_value, list):
                    actual = target(*input_value)
                elif isinstance(input_value, dict):
                    actual = target(**input_value)
                else:
                    actual = target(input_value)
            if not _json_serializable(actual):
                outcome = "wrong_answer"
            elif _strict_equal(actual, payload["expected"]):
                outcome = "passed"
            else:
                outcome = "wrong_answer"
        except SyntaxError:
            outcome = "syntax_error"
        except _OutputLimit:
            outcome = "output_limit"
        except BaseException:
            outcome = "runtime_error"
    except BaseException:
        outcome = "harness_error"
    runtime_ms = max(0.0, (trusted_perf_counter() - start) * 1000.0)
    trusted_emit(
        marker,
        outcome,
        runtime_ms,
        "" if stdout_writer is None else stdout_writer.getvalue(),
        "" if stderr_writer is None else stderr_writer.getvalue(),
    )


if __name__ == "__main__":
    _main()
"""
