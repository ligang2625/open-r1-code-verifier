"""Durable exact-prefix checkpoints for WP9 calibration scoring."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from code_verifier.data.json_strict import StrictJsonError, loads_strict

SCORING_CHECKPOINT_VERSION = 1


class ScoringCheckpointError(RuntimeError):
    """Raised when a scoring checkpoint is missing, corrupt, or bound to different inputs."""


def scoring_checkpoint_dir(output_dir: Path) -> Path:
    """Return the stable sidecar checkpoint directory for one formal scoring output."""
    return output_dir.parent / f"{output_dir.name}.checkpoint"


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=None if pretty else (",", ":"),
            indent=2 if pretty else None,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError):
        raise ScoringCheckpointError("calibration scoring checkpoint must be finite and JSON serializable") from None
    return (text + "\n").encode()


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _write_json(path: Path, value: object) -> None:
    _atomic_bytes(path, _json_bytes(value, pretty=True))


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise ScoringCheckpointError(f"could not load calibration scoring checkpoint {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ScoringCheckpointError(f"calibration scoring checkpoint {path.name} must contain an object")
    return cast(dict[str, object], value)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeError) as error:
        raise ScoringCheckpointError(f"could not load calibration scoring checkpoint {path.name}") from error
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = loads_strict(line)
        except StrictJsonError as error:
            raise ScoringCheckpointError(f"calibration scoring checkpoint line {line_number} is invalid") from error
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ScoringCheckpointError(f"calibration scoring checkpoint line {line_number} must contain an object")
        records.append(cast(dict[str, object], value))
    return records


def _write_progress(checkpoint_dir: Path, *, problem_count: int, byte_count: int) -> None:
    if problem_count < 0 or byte_count < 0:
        raise ScoringCheckpointError("calibration scoring checkpoint progress is invalid")
    _write_json(
        checkpoint_dir / "progress.json",
        {
            "version": SCORING_CHECKPOINT_VERSION,
            "problem_count": problem_count,
            "byte_count": byte_count,
        },
    )


def load_or_initialize_scoring_checkpoint(
    checkpoint_dir: Path,
    *,
    expected_manifest: Mapping[str, object],
    expected_problem_ids: Sequence[str],
) -> tuple[list[dict[str, object]], int]:
    """Load one durable exact problem prefix, trimming only bytes newer than its atomic marker."""
    manifest_path = checkpoint_dir / "checkpoint_manifest.json"
    records_path = checkpoint_dir / "records" / "scoring.jsonl"
    progress_path = checkpoint_dir / "progress.json"
    expected = dict(expected_manifest)

    if not checkpoint_dir.exists():
        checkpoint_dir.mkdir(parents=True)
        _write_json(manifest_path, expected)
        _write_progress(checkpoint_dir, problem_count=0, byte_count=0)
        return [], 0
    if not checkpoint_dir.is_dir():
        raise ScoringCheckpointError("calibration scoring checkpoint path is not a directory")
    if not manifest_path.exists():
        if any(checkpoint_dir.iterdir()):
            raise ScoringCheckpointError("calibration scoring checkpoint is missing its manifest")
        _write_json(manifest_path, expected)
        _write_progress(checkpoint_dir, problem_count=0, byte_count=0)
        return [], 0
    if _load_json(manifest_path) != expected:
        raise ScoringCheckpointError("calibration scoring checkpoint binding does not match this run")
    if not progress_path.exists():
        raise ScoringCheckpointError("calibration scoring checkpoint is missing its progress marker")

    progress = _load_json(progress_path)
    if set(progress) != {"version", "problem_count", "byte_count"}:
        raise ScoringCheckpointError("calibration scoring checkpoint progress fields are invalid")
    problem_count = progress.get("problem_count")
    byte_count = progress.get("byte_count")
    if (
        progress.get("version") != SCORING_CHECKPOINT_VERSION
        or isinstance(problem_count, bool)
        or not isinstance(problem_count, int)
        or problem_count < 0
        or problem_count > len(expected_problem_ids)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
    ):
        raise ScoringCheckpointError("calibration scoring checkpoint progress values are invalid")

    if not records_path.exists():
        if problem_count != 0 or byte_count != 0:
            raise ScoringCheckpointError("calibration scoring checkpoint points to missing committed data")
        return [], 0
    current_size = records_path.stat().st_size
    if current_size < byte_count:
        raise ScoringCheckpointError("calibration scoring checkpoint data is shorter than its progress marker")
    if current_size > byte_count:
        with records_path.open("r+b") as handle:
            handle.truncate(byte_count)
            handle.flush()
            os.fsync(handle.fileno())
    if byte_count:
        with records_path.open("rb") as handle:
            handle.seek(byte_count - 1)
            if handle.read(1) != b"\n":
                raise ScoringCheckpointError("calibration scoring checkpoint does not end on a JSONL boundary")

    records = _load_jsonl(records_path)
    if len(records) != problem_count:
        raise ScoringCheckpointError("calibration scoring checkpoint problem count mismatch")
    actual_problem_ids = [record.get("problem_id") for record in records]
    if actual_problem_ids != list(expected_problem_ids[:problem_count]):
        raise ScoringCheckpointError("calibration scoring checkpoint is not the expected exact problem prefix")
    if any(record.get("infrastructure_failure_count") != 0 for record in records):
        raise ScoringCheckpointError("calibration scoring checkpoint contains an infrastructure failure")
    return records, byte_count


def append_scoring_checkpoint_record(
    checkpoint_dir: Path,
    record: Mapping[str, object],
    *,
    committed_problem_count: int,
    committed_byte_count: int,
) -> tuple[int, int]:
    """Durably append one complete problem record and then atomically advance its commit marker."""
    if record.get("infrastructure_failure_count") != 0:
        raise ScoringCheckpointError("refusing to checkpoint a calibration scoring infrastructure failure")
    records_path = checkpoint_dir / "records" / "scoring.jsonl"
    records_path.parent.mkdir(parents=True, exist_ok=True)
    current_size = records_path.stat().st_size if records_path.exists() else 0
    if current_size != committed_byte_count:
        raise ScoringCheckpointError("calibration scoring checkpoint changed after progress recovery")
    content = _json_bytes(dict(record))
    with records_path.open("ab") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    next_problem_count = committed_problem_count + 1
    next_byte_count = committed_byte_count + len(content)
    _write_progress(checkpoint_dir, problem_count=next_problem_count, byte_count=next_byte_count)
    return next_problem_count, next_byte_count


def checkpoint_records_sha256(checkpoint_dir: Path) -> str:
    """Return the durable checkpoint record hash for audit/debug output."""
    path = checkpoint_dir / "records" / "scoring.jsonl"
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()
