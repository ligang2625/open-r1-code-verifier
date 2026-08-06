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

PYTHON_HARNESS_PROTOCOL_VERSION = "trusted-parent-v1"

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

import ctypes
import importlib.util
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_CHILD_RESULT_LIMIT_BYTES = 8 * 1024 * 1024
_READ_CHUNK_BYTES = 8192
_PR_SET_DUMPABLE = 4

_CHILD_RUNNER_SOURCE = r'''from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_candidate() -> Any:
    spec = importlib.util.spec_from_file_location("candidate", Path("candidate.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _main() -> None:
    result_fd = int(sys.argv[1])
    trusted_json_loads = json.loads
    trusted_json_dumps = json.dumps
    trusted_os_write = os.write

    def write_packet(packet: object) -> None:
        encoded = trusted_json_dumps(
            packet,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        offset = 0
        while offset < len(encoded):
            written = trusted_os_write(result_fd, encoded[offset:])
            if written <= 0:
                raise RuntimeError("candidate result pipe closed")
            offset += written

    try:
        raw_payload = sys.stdin.buffer.read()
    finally:
        try:
            sys.stdin.close()
        except BaseException:
            pass
        try:
            os.close(0)
        except OSError:
            pass

    try:
        payload = trusted_json_loads(raw_payload)
        raw_payload = b""
        if not isinstance(payload, dict) or set(payload) != {"function_name", "input"}:
            raise ValueError("invalid candidate payload")
        function_name = payload["function_name"]
        if not isinstance(function_name, str) or not function_name.isidentifier():
            raise ValueError("invalid function name")
    except BaseException:
        write_packet({"kind": "runtime_error"})
        return

    try:
        module = _load_candidate()
    except SyntaxError:
        write_packet({"kind": "syntax_error"})
        return
    except BaseException:
        write_packet({"kind": "runtime_error"})
        return

    try:
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
    except BaseException:
        write_packet({"kind": "runtime_error"})
        return

    try:
        write_packet({"kind": "returned", "actual": actual})
    except (TypeError, ValueError, RecursionError):
        write_packet({"kind": "non_json"})


if __name__ == "__main__":
    _main()
'''


def _strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_strict_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_strict_equal(actual[key], expected[key]) for key in actual)
    return bool(actual == expected)


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


def _parse_child_result(encoded: bytes) -> dict[str, object] | None:
    try:
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    result = value
    kind = result.get("kind")
    if kind == "returned":
        return result if set(result) == {"kind", "actual"} else None
    if kind in {"non_json", "syntax_error", "runtime_error"}:
        return result if set(result) == {"kind"} else None
    return None


def _append_bounded(buffer: bytearray, chunk: bytes, limit: int) -> bool:
    remaining = max(0, limit + 1 - len(buffer))
    if remaining:
        buffer.extend(chunk[:remaining])
    return len(buffer) > limit or len(chunk) > remaining


def _drain_ready(
    selector: selectors.BaseSelector,
    buffers: dict[str, bytearray],
    limits: dict[str, int],
    exceeded: dict[str, bool],
    *,
    timeout: float,
) -> bool:
    events = selector.select(timeout)
    for key, _ in events:
        stream = key.fileobj
        name = key.data
        try:
            chunk = os.read(stream.fileno(), _READ_CHUNK_BYTES)
        except BlockingIOError:
            continue
        if not chunk:
            selector.unregister(stream)
            stream.close()
            continue
        if _append_bounded(buffers[name], chunk, limits[name]):
            exceeded[name] = True
    return bool(events)


def _bounded_text(value: bytes, limit: int) -> str:
    text = value[:limit].decode("utf-8", errors="replace")
    while len(text.encode("utf-8")) > limit:
        text = text[:-1]
    return text


def _disable_process_dumping() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "unable to protect trusted harness memory")


def _propagate_child_failure(return_code: int) -> None:
    if return_code < 0:
        os.kill(os.getpid(), -return_code)
        os._exit(128 - return_code)
    os._exit(min(return_code, 255))


def _run_candidate(function_name: str, input_value: object, max_output_bytes: int) -> tuple[str, object, str, str]:
    child_payload = json.dumps(
        {"function_name": function_name, "input": input_value},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    result_read_fd, result_write_fd = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _CHILD_RUNNER_SOURCE, str(result_write_fd)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(result_write_fd,),
            close_fds=True,
            cwd=".",
            env={},
            bufsize=0,
            start_new_session=True,
        )
    finally:
        os.close(result_write_fd)
        if process is None:
            os.close(result_read_fd)

    if process is None or process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("candidate process unavailable")

    try:
        process.stdin.write(child_payload)
        process.stdin.close()
    except BrokenPipeError:
        process.stdin.close()

    result_stream = os.fdopen(result_read_fd, "rb", buffering=0)
    streams = {
        "stdout": process.stdout,
        "stderr": process.stderr,
        "result": result_stream,
    }
    selector = selectors.DefaultSelector()
    for name, stream in streams.items():
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)

    buffers = {name: bytearray() for name in streams}
    limits = {
        "stdout": max_output_bytes,
        "stderr": max_output_bytes,
        "result": _CHILD_RESULT_LIMIT_BYTES,
    }
    exceeded = {name: False for name in streams}
    killed_for_limit = False
    try:
        while True:
            _drain_ready(selector, buffers, limits, exceeded, timeout=0.01)
            if (exceeded["stdout"] or exceeded["stderr"] or exceeded["result"]) and process.poll() is None:
                process.kill()
                killed_for_limit = True
            return_code = process.poll()
            if return_code is None:
                continue
            for _ in range(8):
                if not _drain_ready(selector, buffers, limits, exceeded, timeout=0.0):
                    break
            break
    finally:
        for key in list(selector.get_map().values()):
            stream = key.fileobj
            selector.unregister(stream)
            stream.close()
        selector.close()

    return_code = process.wait()
    captured_stdout = _bounded_text(bytes(buffers["stdout"]), max_output_bytes)
    captured_stderr = _bounded_text(bytes(buffers["stderr"]), max_output_bytes)
    if exceeded["stdout"] or exceeded["stderr"]:
        return "output_limit", None, captured_stdout, captured_stderr
    if exceeded["result"] or killed_for_limit:
        return "harness_error", None, captured_stdout, captured_stderr
    if return_code != 0:
        _propagate_child_failure(return_code)

    child_result = _parse_child_result(bytes(buffers["result"]))
    if child_result is None:
        return "harness_error", None, captured_stdout, captured_stderr
    kind = child_result["kind"]
    return str(kind), child_result.get("actual"), captured_stdout, captured_stderr


def _emit(marker: str, outcome: str, runtime_ms: float, stdout: str, stderr: str) -> None:
    report = json.dumps(
        {"outcome": outcome, "runtime_ms": runtime_ms, "stdout": stdout, "stderr": stderr},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    os.write(1, f"__CODE_VERIFIER_RESULT__:{marker}:{report}\n".encode("utf-8"))


def _main() -> None:
    trusted_json_loads = json.loads
    trusted_perf_counter = time.perf_counter
    trusted_emit = _emit
    start = trusted_perf_counter()
    marker = "invalid"
    outcome = "harness_error"
    captured_stdout = ""
    captured_stderr = ""
    try:
        raw_payload = sys.stdin.read()
        try:
            sys.stdin.close()
        finally:
            try:
                os.close(0)
            except OSError:
                pass
        payload = trusted_json_loads(raw_payload)
        raw_payload = ""
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
        _disable_process_dumping()
        kind, actual, captured_stdout, captured_stderr = _run_candidate(
            function_name,
            payload["input"],
            max_output_bytes,
        )
        if kind == "returned":
            outcome = "passed" if _strict_equal(actual, payload["expected"]) else "wrong_answer"
        elif kind == "non_json":
            outcome = "wrong_answer"
        elif kind in {"syntax_error", "runtime_error", "output_limit", "harness_error"}:
            outcome = kind
        else:
            outcome = "harness_error"
    except BaseException:
        outcome = "harness_error"
    runtime_ms = max(0.0, (trusted_perf_counter() - start) * 1000.0)
    trusted_emit(marker, outcome, runtime_ms, captured_stdout, captured_stderr)


if __name__ == "__main__":
    _main()
"""
