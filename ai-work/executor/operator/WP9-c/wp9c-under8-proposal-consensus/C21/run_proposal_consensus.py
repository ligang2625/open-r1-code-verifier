#!/usr/bin/env python3
"""Run C21 two-oracle Piston output consensus and freeze exactly eight tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
from collections import Counter
from collections.abc import Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.json_strict import loads_strict
from code_verifier.execution.base import ExecutionStatus
from code_verifier.execution.piston import (
    PistonExecutor,
    PistonTransportError,
    _map_piston_stage_failure,
    _parse_piston_stage,
    load_piston_executor_config,
)
from code_verifier.execution.piston_resilience import load_piston_transport_policy

ROOT = Path(__file__).resolve().parents[6]
PISTON_CONFIG = ROOT / "configs/execution/piston-local.yaml"
TRANSPORT_POLICY = ROOT / "configs/execution/piston-transport-resilience.yaml"
ENTRY = "__wp9c_reference_entry__"
PROBE_PROTOCOL = "wp9c-piston-json-output-probe-v1"
PROBE_TIMEOUT_SECONDS = 2.0
PROBE_MEMORY_LIMIT_MB = 512
PROBE_RESULT_MAX_BYTES = 65536

_PROBE_PARENT_SOURCE = r'''from __future__ import annotations

import ctypes
import json
import os
import selectors
import subprocess
import sys
from pathlib import Path
from typing import Any

_CHILD_SOURCE = r"""from __future__ import annotations
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

def load_candidate() -> Any:
    spec = importlib.util.spec_from_file_location('candidate', Path('candidate.py'))
    if spec is None or spec.loader is None:
        raise RuntimeError('candidate module unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main() -> None:
    result_fd = int(sys.argv[1])
    def write_packet(packet: object) -> None:
        encoded = json.dumps(packet, allow_nan=False, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        offset = 0
        while offset < len(encoded):
            written = os.write(result_fd, encoded[offset:])
            if written <= 0:
                raise RuntimeError('result pipe closed')
            offset += written
    try:
        payload = json.loads(sys.stdin.buffer.read())
        if not isinstance(payload, dict) or set(payload) != {'function_name', 'input'}:
            raise ValueError('invalid payload')
        fn = payload['function_name']
        if not isinstance(fn, str) or not fn.isidentifier():
            raise ValueError('invalid function')
    except BaseException:
        write_packet({'kind': 'runtime_error'})
        return
    try:
        module = load_candidate()
        target = getattr(module, fn)
        if not callable(target):
            raise TypeError('target not callable')
        value = payload['input']
        if isinstance(value, list):
            actual = target(*value)
        elif isinstance(value, dict):
            actual = target(**value)
        else:
            actual = target(value)
    except BaseException:
        write_packet({'kind': 'runtime_error'})
        return
    try:
        write_packet({'kind': 'returned', 'actual': actual})
    except (TypeError, ValueError, RecursionError):
        write_packet({'kind': 'non_json'})

if __name__ == '__main__':
    main()
"""

def append_bounded(buffer: bytearray, chunk: bytes, limit: int) -> bool:
    remaining = max(0, limit + 1 - len(buffer))
    if remaining:
        buffer.extend(chunk[:remaining])
    return len(buffer) > limit or len(chunk) > remaining

def strict_loads(data: bytes) -> dict[str, object] | None:
    def no_dupes(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    def reject_constant(value: str) -> object:
        raise ValueError(value)
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=no_dupes, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    kind = value.get('kind')
    if kind == 'returned' and set(value) == {'kind', 'actual'}:
        return value
    if kind in {'runtime_error', 'non_json'} and set(value) == {'kind'}:
        return value
    return None

def emit(marker: str, packet: object) -> None:
    encoded = json.dumps(packet, allow_nan=False, ensure_ascii=False, separators=(',', ':'))
    os.write(1, f'__WP9C_PROBE_RESULT__:{marker}:{encoded}\n'.encode('utf-8'))

def disable_process_dumping() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(4, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'unable to protect trusted probe memory')

def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict) or set(payload) != {
            'function_name', 'input', 'marker', 'max_output_bytes', 'result_max_bytes'
        }:
            raise ValueError('invalid payload')
        fn = payload['function_name']
        marker = payload['marker']
        max_output = payload['max_output_bytes']
        result_max = payload['result_max_bytes']
        if not isinstance(fn, str) or not fn.isidentifier():
            raise ValueError('invalid fn')
        if not isinstance(marker, str) or not marker.isascii() or not marker.isalnum():
            raise ValueError('invalid marker')
        if not isinstance(max_output, int) or isinstance(max_output, bool) or max_output <= 0:
            raise ValueError('invalid max output')
        if not isinstance(result_max, int) or isinstance(result_max, bool) or result_max <= 0:
            raise ValueError('invalid result max')
    except BaseException:
        emit('invalid', {'kind': 'harness_error'})
        return

    try:
        sys.stdin.close()
        try:
            os.close(0)
        except OSError:
            pass
        disable_process_dumping()
    except BaseException:
        emit(marker, {'kind': 'harness_error'})
        return

    child_payload = json.dumps(
        {'function_name': fn, 'input': payload['input']},
        allow_nan=False,
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')
    result_read, result_write = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, '-I', '-S', '-c', _CHILD_SOURCE, str(result_write)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(result_write,),
            close_fds=True,
            cwd='.',
            env={},
            bufsize=0,
            start_new_session=True,
        )
    finally:
        os.close(result_write)
        if process is None:
            os.close(result_read)
    if process is None or process.stdin is None or process.stdout is None or process.stderr is None:
        emit(marker, {'kind': 'harness_error'})
        return
    try:
        process.stdin.write(child_payload)
        process.stdin.close()
    except BrokenPipeError:
        process.stdin.close()

    result_stream = os.fdopen(result_read, 'rb', buffering=0)
    streams = {'stdout': process.stdout, 'stderr': process.stderr, 'result': result_stream}
    selector = selectors.DefaultSelector()
    for name, stream in streams.items():
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    buffers = {name: bytearray() for name in streams}
    limits = {'stdout': max_output, 'stderr': max_output, 'result': result_max}
    exceeded = {name: False for name in streams}
    try:
        while True:
            for key, _ in selector.select(0.01):
                stream = key.fileobj
                name = key.data
                try:
                    chunk = os.read(stream.fileno(), 8192)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if append_bounded(buffers[name], chunk, limits[name]):
                    exceeded[name] = True
            if any(exceeded.values()) and process.poll() is None:
                process.kill()
            if process.poll() is not None:
                for _ in range(8):
                    events = selector.select(0.0)
                    if not events:
                        break
                    for key, _ in events:
                        stream = key.fileobj
                        name = key.data
                        chunk = os.read(stream.fileno(), 8192)
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                        elif append_bounded(buffers[name], chunk, limits[name]):
                            exceeded[name] = True
                break
    finally:
        for key in list(selector.get_map().values()):
            stream = key.fileobj
            selector.unregister(stream)
            stream.close()
        selector.close()
    return_code = process.wait()
    if any(exceeded.values()):
        emit(marker, {'kind': 'output_limit'})
        return
    if return_code != 0:
        emit(marker, {'kind': 'runtime_error'})
        return
    child = strict_loads(bytes(buffers['result']))
    if child is None:
        emit(marker, {'kind': 'harness_error'})
        return
    emit(marker, child)

if __name__ == '__main__':
    main()
'''


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _name(row: Mapping[str, object]) -> str:
    value = row.get("candidate_id")
    return value if isinstance(value, str) and value else "row"


def _str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{_name(row)}.{key} must be a non-empty string")
    return value


def _int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{_name(row)}.{key} must be an integer")
    return value


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            value = loads_strict(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = canonical_json(row) + "\n"
            handle.write(payload)
            digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def _strict_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_strict_equal(a, b) for a, b in zip(left, right, strict=True))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_strict_equal(left[key], right[key]) for key in left)
    return bool(left == right)


def _no_dupes(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(value)


def _parse_probe_packet(stdout: str, marker: str) -> dict[str, object] | None:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    prefix = f"__WP9C_PROBE_RESULT__:{marker}:"
    final_line = lines[-1]
    if not final_line.startswith(prefix):
        return None
    try:
        value = json.loads(
            final_line[len(prefix) :],
            object_pairs_hook=_no_dupes,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    packet = cast(dict[str, object], value)
    kind = packet.get("kind")
    if kind == "returned" and set(packet) == {"kind", "actual"}:
        return packet
    if kind in {"runtime_error", "non_json", "output_limit", "harness_error"} and set(packet) == {"kind"}:
        return packet
    return None


def _probe(executor: PistonExecutor, code: str, input_value: object) -> dict[str, object]:
    marker = secrets.token_hex(16)
    config = load_piston_executor_config(PISTON_CONFIG)
    timeout_ms = math.ceil(PROBE_TIMEOUT_SECONDS * 1000.0)
    memory_bytes = PROBE_MEMORY_LIMIT_MB * 1024 * 1024
    try:
        stdin = json.dumps(
            {
                "function_name": ENTRY,
                "input": input_value,
                "marker": marker,
                "max_output_bytes": config.max_output_bytes,
                "result_max_bytes": PROBE_RESULT_MAX_BYTES,
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError):
        return {"kind": "invalid_input", "infrastructure_failure": False}
    payload: dict[str, object] = {
        "language": config.language,
        "version": config.version,
        "files": [
            {"name": "main.py", "content": _PROBE_PARENT_SOURCE},
            {"name": "candidate.py", "content": code},
        ],
        "stdin": stdin,
        "args": [],
        "compile_timeout": timeout_ms,
        "run_timeout": timeout_ms,
        "compile_cpu_time": timeout_ms,
        "run_cpu_time": timeout_ms,
        "compile_memory_limit": memory_bytes,
        "run_memory_limit": memory_bytes,
    }
    try:
        response = executor._execute_request_with_retry(
            payload,
            timeout_seconds=PROBE_TIMEOUT_SECONDS + config.request_timeout_margin_seconds,
            max_response_bytes=config.max_response_bytes,
        )
    except PistonTransportError as error:
        return {
            "kind": "infrastructure_failure",
            "infrastructure_failure": True,
            "infrastructure_failure_kind": f"piston_transport:{error.kind.value}",
        }
    try:
        if not isinstance(response, dict) or not all(isinstance(key, str) for key in response):
            raise PistonTransportError("invalid response")
        response_map = cast(dict[str, object], response)
        if "run" not in response_map or not set(response_map).issubset({"language", "version", "compile", "run"}):
            raise PistonTransportError("invalid response")
        if "compile" in response_map:
            compile_stage = _parse_piston_stage(response_map["compile"])
            compile_failure = _map_piston_stage_failure(compile_stage, memory_limit_bytes=memory_bytes)
            if compile_failure is not None:
                if compile_failure is ExecutionStatus.SANDBOX_ERROR:
                    return {
                        "kind": "infrastructure_failure",
                        "infrastructure_failure": True,
                        "infrastructure_failure_kind": "piston_internal_compile",
                    }
                return {
                    "kind": f"compile_{compile_failure.value}",
                    "infrastructure_failure": False,
                }
        run_stage = _parse_piston_stage(response_map["run"])
        run_failure = _map_piston_stage_failure(run_stage, memory_limit_bytes=memory_bytes)
        if run_failure is not None:
            if run_failure is ExecutionStatus.SANDBOX_ERROR:
                return {
                    "kind": "infrastructure_failure",
                    "infrastructure_failure": True,
                    "infrastructure_failure_kind": "piston_internal_run",
                }
            return {"kind": run_failure.value, "infrastructure_failure": False}
        packet = _parse_probe_packet(run_stage.stdout, marker)
        if packet is None or packet.get("kind") == "harness_error":
            return {
                "kind": "infrastructure_failure",
                "infrastructure_failure": True,
                "infrastructure_failure_kind": "harness_protocol",
            }
        kind = cast(str, packet["kind"])
        if kind != "returned":
            return {"kind": kind, "infrastructure_failure": False}
        actual = packet.get("actual")
        try:
            output_sha = stable_json_hash(actual)
        except (TypeError, ValueError, RecursionError):
            return {"kind": "non_json", "infrastructure_failure": False}
        return {
            "kind": "returned",
            "infrastructure_failure": False,
            "actual": actual,
            "output_sha256": output_sha,
        }
    except PistonTransportError:
        return {
            "kind": "infrastructure_failure",
            "infrastructure_failure": True,
            "infrastructure_failure_kind": "piston_response_protocol",
        }
    except Exception:
        return {
            "kind": "infrastructure_failure",
            "infrastructure_failure": True,
            "infrastructure_failure_kind": "probe_response_protocol",
        }


def _validate_job(job: Mapping[str, object]) -> None:
    _str(job, "candidate_id")
    _str(job, "candidate_binding_sha256")
    _str(job, "source_name")
    if _str(job, "execution_function_name") != ENTRY:
        raise ValueError(f"{_name(job)} entry drift")
    existing = job.get("existing_tests")
    proposals = job.get("input_proposals")
    oracle_pair = job.get("oracle_pair")
    existing_count = _int(job, "existing_test_count")
    slots = _int(job, "additional_tests_required")
    proposal_count = _int(job, "proposal_count")
    if not isinstance(existing, list) or len(existing) != existing_count or not 1 <= existing_count <= 7:
        raise ValueError(f"{_name(job)} existing tests drift")
    if existing_count + slots != 8:
        raise ValueError(f"{_name(job)} slot count drift")
    if not isinstance(proposals, list) or len(proposals) != proposal_count or proposal_count < slots:
        raise ValueError(f"{_name(job)} proposal payload drift")
    ranks: list[str] = []
    for value in proposals:
        proposal = _mapping(value, context=f"{_name(job)} proposal")
        if set(proposal) != {"proposal_id", "proposal_rank_sha256", "input"}:
            raise ValueError(f"{_name(job)} proposal schema drift")
        _str(proposal, "proposal_id")
        ranks.append(_str(proposal, "proposal_rank_sha256"))
    if ranks != sorted(ranks):
        raise ValueError(f"{_name(job)} proposal ordering drift")
    if not isinstance(oracle_pair, list) or len(oracle_pair) != 2:
        raise ValueError(f"{_name(job)} oracle pair drift")
    oracle_hashes: list[str] = []
    for value in oracle_pair:
        oracle = _mapping(value, context=f"{_name(job)} oracle")
        code = _str(oracle, "code")
        digest = _str(oracle, "transformed_code_sha256")
        if hashlib.sha256(code.encode()).hexdigest() != digest:
            raise ValueError(f"{_name(job)} oracle digest drift")
        oracle_hashes.append(digest)
    if oracle_hashes != sorted(set(oracle_hashes)):
        raise ValueError(f"{_name(job)} oracle ordering drift")
    protocol = _mapping(job.get("consensus_protocol"), context=f"{_name(job)} protocol")
    if (
        protocol.get("output_protocol") != PROBE_PROTOCOL
        or protocol.get("oracle_pair_size") != 2
        or protocol.get("proposal_order") != "c13_input_proposals_in_frozen_rank_order"
        or protocol.get("consensus_rule") != "strict_same_json_type_and_value_from_both_qualified_oracles"
        or protocol.get("correctness_retry_allowed") is not False
        or float(cast(int | float, protocol.get("probe_timeout_seconds"))) != PROBE_TIMEOUT_SECONDS
        or protocol.get("probe_memory_limit_mb") != PROBE_MEMORY_LIMIT_MB
        or protocol.get("probe_result_max_bytes") != PROBE_RESULT_MAX_BYTES
    ):
        raise ValueError(f"{_name(job)} consensus protocol drift")


def _job_sha(job: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json(job).encode()).hexdigest()


def _run_candidate(job: Mapping[str, object]) -> dict[str, object]:
    _validate_job(job)
    executor = PistonExecutor(
        load_piston_executor_config(PISTON_CONFIG),
        transport_policy=load_piston_transport_policy(TRANSPORT_POLICY),
    )
    proposals = cast(list[object], job["input_proposals"])
    pair = cast(list[object], job["oracle_pair"])
    slots = _int(job, "additional_tests_required")
    accepted_tests: list[dict[str, object]] = []
    proposal_results: list[dict[str, object]] = []
    infrastructure_kinds: set[str] = set()
    classification = "proposal_consensus_fail"

    for proposal_value in proposals:
        proposal = _mapping(proposal_value, context="proposal")
        proposal_id = _str(proposal, "proposal_id")
        rank = _str(proposal, "proposal_rank_sha256")
        input_value = proposal.get("input")
        first_oracle = _mapping(pair[0], context="first oracle")
        second_oracle = _mapping(pair[1], context="second oracle")
        first = _probe(executor, _str(first_oracle, "code"), input_value)
        if first.get("infrastructure_failure") is True:
            kind = first.get("infrastructure_failure_kind")
            if isinstance(kind, str):
                infrastructure_kinds.add(kind)
            proposal_results.append(
                {
                    "proposal_id": proposal_id,
                    "proposal_rank_sha256": rank,
                    "classification": "infrastructure_blocked",
                    "first_oracle_kind": first.get("kind"),
                    "second_oracle_kind": "not_run",
                }
            )
            classification = "infrastructure_blocked"
            break
        if first.get("kind") != "returned":
            proposal_results.append(
                {
                    "proposal_id": proposal_id,
                    "proposal_rank_sha256": rank,
                    "classification": "oracle_runtime_or_non_json_rejected",
                    "first_oracle_kind": first.get("kind"),
                    "second_oracle_kind": "not_run",
                }
            )
            continue

        second = _probe(executor, _str(second_oracle, "code"), input_value)
        if second.get("infrastructure_failure") is True:
            kind = second.get("infrastructure_failure_kind")
            if isinstance(kind, str):
                infrastructure_kinds.add(kind)
            proposal_results.append(
                {
                    "proposal_id": proposal_id,
                    "proposal_rank_sha256": rank,
                    "classification": "infrastructure_blocked",
                    "first_oracle_kind": "returned",
                    "first_output_sha256": first.get("output_sha256"),
                    "second_oracle_kind": second.get("kind"),
                }
            )
            classification = "infrastructure_blocked"
            break
        if second.get("kind") != "returned":
            proposal_results.append(
                {
                    "proposal_id": proposal_id,
                    "proposal_rank_sha256": rank,
                    "classification": "oracle_runtime_or_non_json_rejected",
                    "first_oracle_kind": "returned",
                    "first_output_sha256": first.get("output_sha256"),
                    "second_oracle_kind": second.get("kind"),
                }
            )
            continue
        first_actual = first.get("actual")
        second_actual = second.get("actual")
        if not _strict_equal(first_actual, second_actual):
            proposal_results.append(
                {
                    "proposal_id": proposal_id,
                    "proposal_rank_sha256": rank,
                    "classification": "oracle_disagreement_rejected",
                    "first_oracle_kind": "returned",
                    "first_output_sha256": first.get("output_sha256"),
                    "second_oracle_kind": "returned",
                    "second_output_sha256": second.get("output_sha256"),
                }
            )
            continue
        accepted_test = {"input": input_value, "expected": first_actual}
        accepted_tests.append(accepted_test)
        proposal_results.append(
            {
                "proposal_id": proposal_id,
                "proposal_rank_sha256": rank,
                "classification": "consensus_test_accepted",
                "first_oracle_kind": "returned",
                "second_oracle_kind": "returned",
                "output_sha256": first.get("output_sha256"),
                "test_sha256": stable_json_hash(accepted_test),
            }
        )
        if len(accepted_tests) == slots:
            classification = "consensus_frozen"
            break

    existing = cast(list[dict[str, object]], job["existing_tests"])
    frozen_tests: list[dict[str, object]] = []
    frozen_sha: str | None = None
    if classification == "consensus_frozen":
        frozen_tests = [*existing, *accepted_tests]
        if len(frozen_tests) != 8:
            raise ValueError(f"{_name(job)} did not freeze exactly eight tests")
        test_hashes = [stable_json_hash(test) for test in frozen_tests]
        if len(test_hashes) != len(set(test_hashes)):
            raise ValueError(f"{_name(job)} frozen tests are not unique")
        frozen_sha = stable_json_hash(frozen_tests)
    elif classification == "proposal_consensus_fail" and len(proposal_results) != len(proposals):
        raise ValueError(f"{_name(job)} consensus failure did not exhaust proposals")

    return {
        "candidate_id": _str(job, "candidate_id"),
        "candidate_binding_sha256": _str(job, "candidate_binding_sha256"),
        "source_name": _str(job, "source_name"),
        "c13_job_sha256": _str(job, "c13_job_sha256"),
        "c20_qualified_row_sha256": _str(job, "c20_qualified_row_sha256"),
        "job_sha256": _job_sha(job),
        "classification": classification,
        "existing_test_count": _int(job, "existing_test_count"),
        "additional_tests_required": slots,
        "proposal_count": len(proposals),
        "attempted_proposal_count": len(proposal_results),
        "accepted_consensus_test_count": len(accepted_tests),
        "proposal_results": proposal_results,
        "accepted_consensus_tests": accepted_tests,
        "frozen_tests": frozen_tests,
        "frozen_tests_sha256": frozen_sha,
        "infrastructure_failure_kinds": sorted(infrastructure_kinds),
        "backfill_required": False,
    }


def _read_checkpoint(path: Path, jobs: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    completed: dict[str, dict[str, object]] = {}
    for row in _jsonl(path):
        candidate_id = _str(row, "candidate_id")
        job = jobs.get(candidate_id)
        if job is None or row.get("job_sha256") != _job_sha(job):
            raise ValueError(f"checkpoint job binding drift: {candidate_id}")
        if candidate_id in completed:
            raise ValueError(f"duplicate checkpoint candidate: {candidate_id}")
        completed[candidate_id] = row
    return completed


def _compact(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "candidate_id": _str(row, "candidate_id"),
        "candidate_binding_sha256": _str(row, "candidate_binding_sha256"),
        "source_name": _str(row, "source_name"),
        "c13_job_sha256": _str(row, "c13_job_sha256"),
        "c20_qualified_row_sha256": _str(row, "c20_qualified_row_sha256"),
        "classification": _str(row, "classification"),
        "existing_test_count": _int(row, "existing_test_count"),
        "additional_tests_required": _int(row, "additional_tests_required"),
        "proposal_count": _int(row, "proposal_count"),
        "attempted_proposal_count": _int(row, "attempted_proposal_count"),
        "accepted_consensus_test_count": _int(row, "accepted_consensus_test_count"),
        "frozen_tests_sha256": row.get("frozen_tests_sha256"),
        "infrastructure_failure_kinds": row.get("infrastructure_failure_kinds"),
        "backfill_required": False,
    }


def run(jobs_path: Path, output_dir: Path, workers: int) -> dict[str, object]:
    if not 1 <= workers <= 32:
        raise ValueError("workers must be in [1, 32]")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite completed C21 report: {report_path}")
    job_rows = _jsonl(jobs_path)
    if len(job_rows) != 615:
        raise ValueError(f"C21 expected 615 jobs, got {len(job_rows)}")
    jobs: dict[str, Mapping[str, object]] = {}
    for row in job_rows:
        _validate_job(row)
        candidate_id = _str(row, "candidate_id")
        if candidate_id in jobs:
            raise ValueError(f"duplicate C21 candidate: {candidate_id}")
        jobs[candidate_id] = row

    runtime = PistonExecutor(
        load_piston_executor_config(PISTON_CONFIG),
        transport_policy=load_piston_transport_policy(TRANSPORT_POLICY),
    ).validate_runtime()
    checkpoint_path = output_dir / "checkpoint_results.jsonl"
    completed = _read_checkpoint(checkpoint_path, jobs)
    pending = [candidate_id for candidate_id in sorted(jobs) if candidate_id not in completed]
    if pending:
        with (
            checkpoint_path.open("a", encoding="utf-8") as checkpoint_handle,
            ThreadPoolExecutor(max_workers=workers) as pool,
        ):
            futures: dict[Future[dict[str, object]], str] = {
                pool.submit(_run_candidate, jobs[candidate_id]): candidate_id for candidate_id in pending
            }
            for future in as_completed(futures):
                candidate_id = futures[future]
                result = future.result()
                if result.get("candidate_id") != candidate_id:
                    raise ValueError("C21 worker identity drift")
                checkpoint_handle.write(canonical_json(result) + "\n")
                checkpoint_handle.flush()
                os.fsync(checkpoint_handle.fileno())
                completed[candidate_id] = result
                print(
                    canonical_json(
                        {
                            "candidate_id": candidate_id,
                            "classification": result["classification"],
                            "attempted_proposals": result["attempted_proposal_count"],
                            "accepted_tests": result["accepted_consensus_test_count"],
                            "completed": len(completed),
                            "total": len(jobs),
                        }
                    ),
                    flush=True,
                )

    if set(completed) != set(jobs):
        raise ValueError("C21 checkpoint does not cover all jobs")
    ordered = [completed[candidate_id] for candidate_id in sorted(completed)]
    counts = Counter(_str(row, "classification") for row in ordered)
    if set(counts) - {"consensus_frozen", "proposal_consensus_fail", "infrastructure_blocked"}:
        raise ValueError("C21 classification drift")
    frozen = [row for row in ordered if row.get("classification") == "consensus_frozen"]
    failures = [_compact(row) for row in ordered if row.get("classification") == "proposal_consensus_fail"]
    blocked = [_compact(row) for row in ordered if row.get("classification") == "infrastructure_blocked"]
    frozen_manifest: list[dict[str, object]] = []
    for row in frozen:
        tests = row.get("frozen_tests")
        if not isinstance(tests, list) or len(tests) != 8:
            raise ValueError("C21 frozen row does not contain eight tests")
        frozen_manifest.append(
            {
                **_compact(row),
                "frozen_tests": tests,
            }
        )

    source_frozen = Counter(_str(row, "source_name") for row in frozen_manifest)
    source_failed = Counter(_str(row, "source_name") for row in failures)
    source_blocked = Counter(_str(row, "source_name") for row in blocked)
    proposal_class_counts = Counter(
        cast(str, value["classification"])
        for row in ordered
        for value in cast(list[dict[str, object]], row["proposal_results"])
    )
    total_probe_calls = 0
    for row in ordered:
        for value in cast(list[dict[str, object]], row["proposal_results"]):
            first = value.get("first_oracle_kind")
            second = value.get("second_oracle_kind")
            if first != "not_run":
                total_probe_calls += 1
            if second != "not_run":
                total_probe_calls += 1

    candidate_sha = _write_jsonl(output_dir / "candidate_results.jsonl", ordered)
    frozen_sha = _write_jsonl(output_dir / "frozen_exact8.jsonl", frozen_manifest)
    failure_sha = _write_jsonl(output_dir / "proposal_consensus_failures.jsonl", failures)
    blocked_sha = _write_jsonl(output_dir / "infrastructure_blocked.jsonl", blocked)
    report: dict[str, object] = {
        "schema_version": "wp9c-under8-proposal-consensus-v1",
        "protocol_amendment": "wp9c-reduced-quota-current-viable-v1",
        "formal_eligible": False,
        "jobs_input_count": 615,
        "consensus_frozen_count": counts["consensus_frozen"],
        "proposal_consensus_fail_count": counts["proposal_consensus_fail"],
        "infrastructure_blocked_count": counts["infrastructure_blocked"],
        "source_frozen_counts": dict(sorted(source_frozen.items())),
        "source_fail_counts": dict(sorted(source_failed.items())),
        "source_infrastructure_blocked_counts": dict(sorted(source_blocked.items())),
        "proposal_classification_counts": dict(sorted(proposal_class_counts.items())),
        "total_probe_calls": total_probe_calls,
        "piston_runtime": runtime,
        "workers": workers,
        "output_protocol": PROBE_PROTOCOL,
        "probe_timeout_seconds": PROBE_TIMEOUT_SECONDS,
        "probe_memory_limit_mb": PROBE_MEMORY_LIMIT_MB,
        "probe_result_max_bytes": PROBE_RESULT_MAX_BYTES,
        "freeze_rule": "existing_tests_then_first_consensus_valid_proposals_exactly_8",
        "backfill_required": False,
        "minimum_pass_count": None,
        "next_gate": "final_exact_b_context_recheck_for_frozen_exact8_candidates",
        "artifact_sha256": {
            "checkpoint_results": _sha(checkpoint_path),
            "candidate_results": candidate_sha,
            "frozen_exact8": frozen_sha,
            "proposal_consensus_failures": failure_sha,
            "infrastructure_blocked": blocked_sha,
        },
        "input_bindings": {
            "consensus_jobs_sha256": _sha(jobs_path),
            "piston_config_sha256": _sha(PISTON_CONFIG),
            "piston_transport_policy_sha256": _sha(TRANSPORT_POLICY),
            "runner_sha256": _sha(Path(__file__)),
        },
    }
    payload = canonical_json(report) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    (output_dir / "report.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii")
    print(payload, end="")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(args.jobs.resolve(), args.output.resolve(), args.workers)


if __name__ == "__main__":
    main()
