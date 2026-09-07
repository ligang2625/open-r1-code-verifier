#!/usr/bin/env python3
"""Write one atomic secret-free operator evidence record for a WP9-d P1 phase."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rc(value: str) -> int | None:
    if value == "null":
        return None
    try:
        result = int(value)
    except ValueError:
        raise SystemExit("operator rc values must be integers or null") from None
    if result < 0:
        raise SystemExit("operator rc values must be non-negative")
    return result


def _file_entry(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"operator evidence artifact must be a regular file: {path}")
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _artifact_inventory(paths: list[Path]) -> list[dict[str, object]]:
    seen: set[Path] = set()
    entries: list[dict[str, object]] = []
    for raw in paths:
        try:
            path = raw.resolve(strict=True)
        except OSError:
            raise SystemExit(f"operator evidence artifact is unavailable: {raw}") from None
        if path in seen:
            raise SystemExit(f"duplicate operator evidence artifact: {path}")
        seen.add(path)
        if path.is_file():
            entries.append(_file_entry(path))
            continue
        if path.is_symlink() or not path.is_dir():
            raise SystemExit(f"operator evidence artifact must be a file or directory: {path}")
        files = sorted(candidate for candidate in path.rglob("*") if candidate.is_file())
        if not files:
            raise SystemExit(f"operator evidence directory is empty: {path}")
        entries.append(
            {
                "path": str(path),
                "type": "directory",
                "files": [
                    {
                        "relative_path": candidate.relative_to(path).as_posix(),
                        "size_bytes": candidate.stat().st_size,
                        "sha256": _sha256(candidate),
                    }
                    for candidate in files
                    if not candidate.is_symlink()
                ],
            }
        )
    return entries


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--detail", required=True)
    parser.add_argument("--handoff-commit", required=True)
    parser.add_argument("--script-path", required=True)
    parser.add_argument("--script-sha256", required=True)
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--formal-data-root", required=True)
    parser.add_argument("--hf-home", required=True)
    parser.add_argument("--piston-endpoint", required=True)
    parser.add_argument("--gpu-name", default="")
    parser.add_argument("--gpu-total-mib", default="")
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--ended-at", required=True)
    parser.add_argument("--command-rc", required=True)
    parser.add_argument("--postcheck-rc", required=True)
    parser.add_argument("--gate-status", choices=("passed", "failed"), required=True)
    parser.add_argument("--artifact", action="append", type=Path, default=[])
    args = parser.parse_args()

    if re.fullmatch(r"[0-9a-f]{40}", args.handoff_commit) is None:
        raise SystemExit("operator evidence handoff commit must be exact lowercase 40-hex")
    if re.fullmatch(r"[0-9a-f]{64}", args.script_sha256) is None:
        raise SystemExit("operator evidence script SHA256 must be exact lowercase 64-hex")
    if args.piston_endpoint != "http://127.0.0.1:2000":
        raise SystemExit("operator evidence Piston endpoint drift")
    for name, raw in (
        ("artifact_root", args.artifact_root),
        ("formal_data_root", args.formal_data_root),
        ("hf_home", args.hf_home),
    ):
        path = Path(raw)
        if not path.is_absolute() or not str(path).startswith("/root/") or "/data" in str(path):
            raise SystemExit(f"operator evidence {name} is outside the current /root policy")
    command_rc = _rc(args.command_rc)
    postcheck_rc = _rc(args.postcheck_rc)
    if args.gate_status == "passed" and (command_rc != 0 or postcheck_rc != 0):
        raise SystemExit("passed operator evidence requires command_rc=0 and postcheck_rc=0")
    gpu_total_mib: int | None = None
    if args.gpu_total_mib:
        try:
            gpu_total_mib = int(args.gpu_total_mib)
        except ValueError:
            raise SystemExit("operator evidence gpu_total_mib must be an integer") from None
        if gpu_total_mib <= 0:
            raise SystemExit("operator evidence gpu_total_mib must be positive")
    inventory = _artifact_inventory(args.artifact)
    if args.gate_status == "passed" and not inventory:
        raise SystemExit("passed operator evidence requires at least one hashed artifact")

    value: dict[str, Any] = {
        "version": 1,
        "stage_id": "WP9-d",
        "gate_id": "wp9d-p1-runtime-validation",
        "checkpoint_id": "C0",
        "phase": args.phase,
        "detail": args.detail,
        "handoff_commit": args.handoff_commit,
        "operator_script_path": args.script_path,
        "operator_script_sha256": args.script_sha256,
        "target_repo": args.target_repo,
        "artifact_root": args.artifact_root,
        "formal_data_root": args.formal_data_root,
        "hf_home": args.hf_home,
        "piston_endpoint": args.piston_endpoint,
        "target_runtime": {
            "gpu_name": args.gpu_name or None,
            "gpu_total_mib": gpu_total_mib,
            "trl": "0.18.0",
            "vllm": "0.8.5.post1",
        },
        "started_at": args.started_at,
        "ended_at": args.ended_at,
        "command_rc": command_rc,
        "postcheck_rc": postcheck_rc,
        "gate_status": args.gate_status,
        "artifact_inventory": inventory,
    }
    _atomic_json(args.output, value)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
