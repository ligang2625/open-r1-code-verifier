#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CONFIG="$ROOT/configs/data/wp9c-native-function-supply-audit.yaml"

cd "$ROOT"

if [[ ! -x "$PYTHON" || ! -f "$CONFIG" ]]; then
  echo "missing project python or source config" >&2
  exit 2
fi
if [[ -z "${http_proxy:-}${https_proxy:-}${HTTP_PROXY:-}${HTTPS_PROXY:-}" ]]; then
  echo "proxy variables are not set; run source ~/.bashrc first" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=0
export TRANSFORMERS_OFFLINE=1
# Disable hf_xet explicitly: the pinned LeetCode parquet is Xet-backed and
# this proxy environment is more reliable through regular Hub HTTP.
export HF_HUB_DISABLE_XET=1

"$PYTHON" - "$CONFIG" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

from code_verifier.config import load_yaml_mapping

_, config_text = sys.argv
config_path = Path(config_text)
config = load_yaml_mapping(config_path)
sources = config.get("sources")
if not isinstance(sources, dict):
    raise SystemExit("native supply config is missing sources")

verified = []
for key in ("apps_train", "leetcode_merged"):
    source = sources.get(key)
    if not isinstance(source, dict):
        raise SystemExit(f"missing source config: {key}")
    dataset_id = source.get("dataset_id")
    revision = source.get("revision")
    relative_path = source.get("parquet_or_json_path")
    expected_sha = source.get("file_sha256")
    if not all(isinstance(value, str) and value for value in (dataset_id, revision, relative_path, expected_sha)):
        raise SystemExit(f"invalid source identity: {key}")
    snapshot = Path(
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=["README.md", relative_path],
            local_files_only=False,
        )
    ).resolve()
    if snapshot.name != revision:
        raise SystemExit(f"snapshot identity mismatch for {key}: expected {revision}, got {snapshot.name}")
    path = snapshot / relative_path
    if not path.is_file():
        raise SystemExit(f"missing pinned source file for {key}: {path}")
    expected_size = source.get("file_size")
    if expected_size is not None:
        if not isinstance(expected_size, int) or path.stat().st_size != expected_size:
            raise SystemExit(
                f"size mismatch for {key}: expected {expected_size}, got {path.stat().st_size}"
            )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    actual_sha = digest.hexdigest()
    if actual_sha != expected_sha:
        raise SystemExit(f"SHA256 mismatch for {key}: expected {expected_sha}, got {actual_sha}")
    verified.append(
        {
            "source_key": key,
            "dataset_id": dataset_id,
            "revision": revision,
            "snapshot": str(snapshot),
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": actual_sha,
        }
    )

print(json.dumps({"status": "verified", "files": verified}, sort_keys=True))
PY
