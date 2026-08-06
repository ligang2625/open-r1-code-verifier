"""Explicit real-sandbox acceptance tests for the self-hosted loopback Piston service."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from code_verifier.execution import ExecutionStatus, PistonExecutor, load_piston_executor_config

pytestmark = pytest.mark.piston

if os.environ.get("CODE_VERIFIER_RUN_PISTON") != "1":
    pytest.skip("real Piston tests require CODE_VERIFIER_RUN_PISTON=1", allow_module_level=True)


@pytest.fixture(scope="module")
def piston_executor() -> PistonExecutor:
    """Load the configured local Piston executor and validate the exact runtime once."""
    config_value = os.environ.get("CODE_VERIFIER_PISTON_CONFIG")
    if not config_value:
        pytest.fail("CODE_VERIFIER_PISTON_CONFIG must identify the local Piston YAML")
    executor = PistonExecutor(load_piston_executor_config(Path(config_value)))
    executor.validate_runtime()
    return executor


def _status(
    executor: PistonExecutor,
    code: str,
    *,
    input_value: object = None,
    expected: object = None,
    timeout_seconds: float = 1.0,
    memory_limit_mb: int = 32,
) -> ExecutionStatus:
    result = executor.execute(
        code,
        "target",
        [{"input": input_value, "expected": expected}],
        timeout_seconds,
        memory_limit_mb,
    )
    assert result.total_tests == 1
    assert len(result.test_results) == 1
    return result.status


def _assert_service_healthy(executor: PistonExecutor) -> None:
    assert (
        _status(
            executor,
            "def target(value):\n    return value + 1\n",
            input_value=1,
            expected=2,
        )
        is ExecutionStatus.PASSED
    )


def test_piston_correct_wrong_syntax_and_runtime_statuses(piston_executor: PistonExecutor) -> None:
    assert (
        _status(
            piston_executor,
            "def target(value):\n    return value * 2\n",
            input_value=3,
            expected=6,
        )
        is ExecutionStatus.PASSED
    )
    assert (
        _status(
            piston_executor,
            "def target(value):\n    return value + 1\n",
            input_value=3,
            expected=6,
        )
        is ExecutionStatus.WRONG_ANSWER
    )
    assert (
        _status(
            piston_executor,
            "def target(value)\n    return value\n",
            input_value=1,
            expected=1,
        )
        is ExecutionStatus.SYNTAX_ERROR
    )
    assert (
        _status(
            piston_executor,
            "def target(value):\n    raise RuntimeError('fixed probe')\n",
            input_value=1,
            expected=1,
        )
        is ExecutionStatus.RUNTIME_ERROR
    )


def test_piston_infinite_loop_times_out_and_service_recovers(piston_executor: PistonExecutor) -> None:
    started = time.monotonic()
    assert (
        _status(
            piston_executor,
            "def target(value):\n    while True:\n        pass\n",
            timeout_seconds=0.5,
        )
        is ExecutionStatus.TIMEOUT
    )
    assert time.monotonic() - started < 10
    _assert_service_healthy(piston_executor)


def test_piston_memory_limit_and_output_limits(piston_executor: PistonExecutor) -> None:
    memory_code = (
        "def target(value):\n    blocks = []\n    while True:\n        blocks.append(bytearray(4 * 1024 * 1024))\n"
    )
    assert (
        _status(piston_executor, memory_code, timeout_seconds=2.0, memory_limit_mb=32) is ExecutionStatus.MEMORY_LIMIT
    )
    _assert_service_healthy(piston_executor)

    stdout_code = "def target(value):\n    print('x' * 100000)\n    return value\n"
    assert _status(piston_executor, stdout_code, input_value=1, expected=1) is ExecutionStatus.OUTPUT_LIMIT
    _assert_service_healthy(piston_executor)

    stderr_code = "import sys\ndef target(value):\n    print('x' * 100000, file=sys.stderr)\n    return value\n"
    assert _status(piston_executor, stderr_code, input_value=1, expected=1) is ExecutionStatus.OUTPUT_LIMIT
    _assert_service_healthy(piston_executor)


def test_piston_blocks_network_root_and_base_filesystem_write(piston_executor: PistonExecutor) -> None:
    network_code = (
        "import socket\n"
        "def target(value):\n"
        "    try:\n"
        "        socket.create_connection(('1.1.1.1', 80), timeout=0.2)\n"
        "    except OSError:\n"
        "        return 'blocked'\n"
        "    return 'connected'\n"
    )
    assert _status(piston_executor, network_code, expected="blocked") is ExecutionStatus.PASSED
    _assert_service_healthy(piston_executor)

    root_code = "import os\ndef target(value):\n    return os.geteuid() != 0\n"
    assert _status(piston_executor, root_code, expected=True) is ExecutionStatus.PASSED
    _assert_service_healthy(piston_executor)

    write_code = (
        "def target(value):\n"
        "    try:\n"
        "        with open('/etc/code_verifier_probe', 'w', encoding='utf-8') as handle:\n"
        "            handle.write('probe')\n"
        "    except OSError:\n"
        "        return 'blocked'\n"
        "    return 'written'\n"
    )
    assert _status(piston_executor, write_code, expected="blocked") is ExecutionStatus.PASSED
    _assert_service_healthy(piston_executor)


def test_piston_cannot_read_host_sentinel_and_cleans_job_temp_state(
    piston_executor: PistonExecutor,
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "host-sentinel.txt"
    sentinel_contents = "host-only-sentinel"
    sentinel.write_text(sentinel_contents, encoding="utf-8")
    original_mtime = sentinel.stat().st_mtime_ns

    read_code = (
        "def target(path):\n"
        "    try:\n"
        "        with open(path, encoding='utf-8') as handle:\n"
        "            return handle.read()\n"
        "    except OSError:\n"
        "        return 'blocked'\n"
    )
    assert _status(piston_executor, read_code, input_value=str(sentinel), expected="blocked") is ExecutionStatus.PASSED
    assert sentinel.read_text(encoding="utf-8") == sentinel_contents
    assert sentinel.stat().st_mtime_ns == original_mtime
    _assert_service_healthy(piston_executor)

    artifact_value = "sandbox-temp-artifact"
    write_temp = (
        "def target(value):\n"
        "    with open('/tmp/code-verifier-artifact', 'w', encoding='utf-8') as handle:\n"
        "        handle.write(value)\n"
        "    return value\n"
    )
    assert (
        _status(piston_executor, write_temp, input_value=artifact_value, expected=artifact_value)
        is ExecutionStatus.PASSED
    )
    read_temp = (
        "from pathlib import Path\n"
        "def target(value):\n"
        "    path = Path('/tmp/code-verifier-artifact')\n"
        "    return path.read_text(encoding='utf-8') if path.exists() else 'clean'\n"
    )
    assert _status(piston_executor, read_temp, expected="clean") is ExecutionStatus.PASSED
    _assert_service_healthy(piston_executor)


def test_piston_pid_limit_contains_process_bomb_and_service_recovers(piston_executor: PistonExecutor) -> None:
    process_bomb = (
        "import subprocess\n"
        "def target(value):\n"
        "    children = []\n"
        "    while True:\n"
        "        children.append(subprocess.Popen(['sleep', '30']))\n"
    )
    started = time.monotonic()
    status = _status(piston_executor, process_bomb, timeout_seconds=2.0, memory_limit_mb=64)
    assert status is not ExecutionStatus.PASSED
    assert time.monotonic() - started < 15
    _assert_service_healthy(piston_executor)
