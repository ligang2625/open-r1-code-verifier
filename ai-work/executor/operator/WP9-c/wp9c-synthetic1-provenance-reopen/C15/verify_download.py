#!/usr/bin/env python3
"""Verify the completed C15 provenance-only download without scanning source rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from code_verifier.config import load_yaml_mapping

ROOT = Path(__file__).resolve().parents[6]
CHECKPOINT = ROOT / "ai-work/executor/operator/WP9-c/wp9c-synthetic1-provenance-reopen/C15/checkpoint.json"
DEFAULT_CONFIG = ROOT / "configs/data/wp9c-synthetic1-provenance-reopen.yaml"
DEFAULT_MANIFEST = Path("/home/dzy/wp9c-synthetic1-provenance-download-C15/manifest.json")
DEFAULT_LOG = Path("/home/dzy/wp9c-synthetic1-provenance-download-C15.log")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _require_mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def verify(config_path: Path, manifest_path: Path, log_path: Path) -> dict[str, object]:
    config = load_yaml_mapping(config_path)
    checkpoint = _json(CHECKPOINT)
    if checkpoint.get("status") != "awaiting_operator":
        raise ValueError("C15 checkpoint must still be awaiting_operator before download verification")
    if checkpoint.get("operator_gate") != "wp9c-synthetic1-provenance-reopen":
        raise ValueError("C15 operator gate identity drift")
    if checkpoint.get("candidate_supply_increment_allowed") is not False:
        raise ValueError("C15 candidate-supply freeze drift")

    bindings = _require_mapping(checkpoint.get("bindings"), context="C15 checkpoint bindings")
    if _sha(config_path) != bindings.get("audit_config_sha256"):
        raise ValueError("C15 config digest drift")
    runner = (
        ROOT
        / "ai-work/executor/operator/WP9-c/wp9c-synthetic1-provenance-reopen/C15/01-download-provenance-index.sh"
    )
    if _sha(runner) != bindings.get("download_runner_sha256"):
        raise ValueError("C15 download runner digest drift")

    source = _require_mapping(config.get("source"), context="C15 source config")
    purpose = _require_mapping(config.get("purpose"), context="C15 purpose config")
    if purpose.get("incremental_candidate_supply_allowed") is not False:
        raise ValueError("C15 config candidate-supply freeze drift")
    if not manifest_path.is_file():
        raise ValueError(f"C15 manifest missing: {manifest_path}")
    digest_path = manifest_path.with_name("manifest.sha256")
    if not digest_path.is_file():
        raise ValueError("C15 manifest.sha256 missing")
    manifest_sha = _sha(manifest_path)
    if digest_path.read_text(encoding="ascii").strip() != manifest_sha:
        raise ValueError("C15 manifest digest sidecar mismatch")

    manifest = _json(manifest_path)
    if set(manifest) != {
        "schema_version",
        "dataset_id",
        "revision",
        "use_class",
        "incremental_candidate_supply",
        "snapshot_path",
        "shard_count",
        "total_rows",
        "shards",
    }:
        raise ValueError("C15 manifest schema drift")
    if (
        manifest.get("schema_version") != "wp9c-synthetic1-provenance-download-v1"
        or manifest.get("dataset_id") != source.get("dataset_id")
        or manifest.get("revision") != source.get("revision")
        or manifest.get("use_class") != "provenance_index_only"
        or manifest.get("incremental_candidate_supply") != 0
        or manifest.get("shard_count") != source.get("expected_shards")
        or manifest.get("total_rows") != source.get("expected_rows")
    ):
        raise ValueError("C15 manifest identity/count drift")

    snapshot_value = manifest.get("snapshot_path")
    shard_values = manifest.get("shards")
    if not isinstance(snapshot_value, str) or not isinstance(shard_values, list):
        raise ValueError("C15 snapshot/shards schema drift")
    snapshot = Path(snapshot_value).resolve()
    if snapshot.name != source.get("revision"):
        raise ValueError("C15 snapshot revision drift")
    expected_paths = [f"data/train-{index:05d}-of-00017.parquet" for index in range(17)]
    observed_paths: list[str] = []
    total_rows = 0
    total_bytes = 0
    for index, raw in enumerate(shard_values):
        row = _require_mapping(raw, context=f"C15 shard {index}")
        if set(row) != {"shard_index", "path", "sha256", "size", "rows"}:
            raise ValueError(f"C15 shard manifest schema drift: {index}")
        relative = row.get("path")
        if row.get("shard_index") != index or not isinstance(relative, str):
            raise ValueError(f"C15 shard ordering/path drift: {index}")
        observed_paths.append(relative)
        path = snapshot / relative
        if not path.is_file():
            raise ValueError(f"C15 shard missing: {relative}")
        if path.stat().st_size != row.get("size"):
            raise ValueError(f"C15 shard size drift: {relative}")
        if _sha(path) != row.get("sha256"):
            raise ValueError(f"C15 shard SHA256 drift: {relative}")
        parquet_rows = pq.ParquetFile(path).metadata.num_rows
        if parquet_rows != row.get("rows"):
            raise ValueError(f"C15 shard row-count drift: {relative}")
        total_rows += parquet_rows
        total_bytes += path.stat().st_size
    if observed_paths != expected_paths:
        raise ValueError("C15 shard filename set/order drift")
    if total_rows != source.get("expected_rows"):
        raise ValueError("C15 total parquet row count drift")

    if not log_path.is_file():
        raise ValueError("C15 download log missing")
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    canonical_manifest_line = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    if canonical_manifest_line not in log_text:
        raise ValueError("C15 download log does not contain the published manifest")
    if "Traceback (most recent call last)" in log_text:
        raise ValueError("C15 download log contains a Python traceback")

    c11_path = ROOT / cast(str, _require_mapping(config.get("bindings"), context="C15 bindings")["c11_checkpoint"])
    c11 = _json(c11_path)
    pause = _require_mapping(c11.get("pause_directive"), context="historical C11 pause directive")
    if c11.get("status") != "paused_by_user" or pause.get("download_authorized") is not False:
        raise ValueError("historical C11 pause state drift")

    return {
        "schema_version": "wp9c-synthetic1-provenance-download-verification-v1",
        "verified": True,
        "manifest_sha256": manifest_sha,
        "log_sha256": _sha(log_path),
        "snapshot_path": str(snapshot),
        "shard_count": len(shard_values),
        "total_rows": total_rows,
        "total_bytes": total_bytes,
        "incremental_candidate_supply": 0,
        "historical_c11_status": c11.get("status"),
        "response_lineage_scan_run": False,
        "piston_run": False,
        "generation_run": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()
    print(json.dumps(verify(args.config.resolve(), args.manifest.resolve(), args.log.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
