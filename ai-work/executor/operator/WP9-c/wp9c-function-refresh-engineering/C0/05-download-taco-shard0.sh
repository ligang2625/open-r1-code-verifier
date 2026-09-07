#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
DATASET_ID="BAAI/TACO"
REVISION="d593ed0a2becbbc952230bb89be09189bf1056dc"
RELATIVE_PATH="ALL/train-00000-of-00009.parquet"
EXPECTED_SHA256="bee336c14dda183b1f700d54a149173418c7b3def295666159dd72c32aa8b326"
EXPECTED_SIZE="286917870"

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

"$PYTHON" - "$DATASET_ID" "$REVISION" "$RELATIVE_PATH" "$EXPECTED_SHA256" "$EXPECTED_SIZE" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

_, dataset_id, revision, relative_path, expected_sha, expected_size_text = sys.argv
expected_size = int(expected_size_text)
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
    raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
path = snapshot / relative_path
if not path.is_file():
    raise SystemExit(f"missing pinned shard: {path}")
if path.stat().st_size != expected_size:
    raise SystemExit(f"size mismatch: expected {expected_size}, got {path.stat().st_size}")
digest = hashlib.sha256()
with path.open("rb") as handle:
    while chunk := handle.read(8 * 1024 * 1024):
        digest.update(chunk)
actual_sha = digest.hexdigest()
if actual_sha != expected_sha:
    raise SystemExit(f"SHA256 mismatch: expected {expected_sha}, got {actual_sha}")
print(json.dumps({"status":"verified","snapshot":str(snapshot),"path":str(path),"size":expected_size,"sha256":actual_sha}, sort_keys=True))
PY
