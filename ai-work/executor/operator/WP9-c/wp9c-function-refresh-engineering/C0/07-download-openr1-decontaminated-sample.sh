#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
DATASET_ID="open-r1/verifiable-coding-problems-python_decontaminated"
REVISION="0d251c23dcff7f7e525e7a4e184be5232bf63db6"

cd "$ROOT"

if [[ ! -x "$PYTHON" ]]; then
  echo "missing project python: $PYTHON" >&2
  exit 2
fi
if [[ -z "${http_proxy:-}${https_proxy:-}${HTTP_PROXY:-}${HTTPS_PROXY:-}" ]]; then
  echo "proxy variables are not set; run source ~/.bashrc first" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=0
export TRANSFORMERS_OFFLINE=1

"$PYTHON" - "$DATASET_ID" "$REVISION" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

_, dataset_id, revision = sys.argv
expected = {
    "data/train-00000-of-00006.parquet": (
        36295672,
        "181d2e480df556e10e49f6dd1c6160a98adf5c1ae77c5e44fb03accc19129c89",
    ),
    "data/train-00005-of-00006.parquet": (
        218679740,
        "f302c5aaa01d126c0dc72a541b3d445d0dd6259577a88a930cdd02c771c903b6",
    ),
}

snapshot = Path(
    snapshot_download(
        repo_id=dataset_id,
        repo_type="dataset",
        revision=revision,
        allow_patterns=["README.md", *expected],
        local_files_only=False,
    )
).resolve()
if snapshot.name != revision:
    raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")

verified = []
for relative_path, (expected_size, expected_sha) in expected.items():
    path = snapshot / relative_path
    if not path.is_file():
        raise SystemExit(f"missing pinned shard: {path}")
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise SystemExit(f"size mismatch for {relative_path}: expected {expected_size}, got {actual_size}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    actual_sha = digest.hexdigest()
    if actual_sha != expected_sha:
        raise SystemExit(f"SHA256 mismatch for {relative_path}: expected {expected_sha}, got {actual_sha}")
    verified.append({"path": str(path), "size": actual_size, "sha256": actual_sha})

print(json.dumps({"status": "verified", "snapshot": str(snapshot), "files": verified}, sort_keys=True))
PY
