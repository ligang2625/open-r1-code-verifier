#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
DATASET_ID="OpenCoder-LLM/opc-sft-stage2"
REVISION="87a3b8da70131b3cf5ef6504c26a51b8c17347a4"
RELATIVE_PATH="educational_instruct/train-00000-of-00001.parquet"
EXPECTED_SHA256="59cc262e240140ca265655a8d14d2a0f28139164a8e532294308692408095759"
EXPECTED_SIZE="53572508"

cd "$ROOT"

if [[ ! -x "$PYTHON" ]]; then
  echo "missing project python: $PYTHON" >&2
  exit 2
fi

# The user's proxy exports live in the interactive shell. If this script is
# launched without them, fail closed rather than silently attempting a direct
# long download.
if [[ -z "${http_proxy:-}${https_proxy:-}${HTTP_PROXY:-}${HTTPS_PROXY:-}" ]]; then
  echo "proxy variables are not set." >&2
  echo "Run this from your interactive terminal as:" >&2
  echo "  source ~/.bashrc" >&2
  echo "  bash $ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/01-download-opencoder.sh" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=0
export TRANSFORMERS_OFFLINE=1

"$PYTHON" - \
  "$DATASET_ID" \
  "$REVISION" \
  "$RELATIVE_PATH" \
  "$EXPECTED_SHA256" \
  "$EXPECTED_SIZE" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

_, dataset_id, revision, relative_path, expected_sha256, expected_size_text = sys.argv
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
    raise SystemExit(
        f"snapshot identity mismatch: expected directory {revision}, got {snapshot.name}"
    )

readme = snapshot / "README.md"
parquet = snapshot / relative_path
if not readme.is_file():
    raise SystemExit(f"missing pinned README: {readme}")
if not parquet.is_file():
    raise SystemExit(f"missing pinned parquet: {parquet}")

actual_size = parquet.stat().st_size
if actual_size != expected_size:
    raise SystemExit(
        f"parquet size mismatch: expected {expected_size}, got {actual_size}"
    )

digest = hashlib.sha256()
with parquet.open("rb") as handle:
    while chunk := handle.read(8 * 1024 * 1024):
        digest.update(chunk)
actual_sha256 = digest.hexdigest()
if actual_sha256 != expected_sha256:
    raise SystemExit(
        f"parquet SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}"
    )

print(
    json.dumps(
        {
            "status": "verified",
            "dataset_id": dataset_id,
            "revision": revision,
            "snapshot": str(snapshot),
            "parquet": str(parquet),
            "parquet_size": actual_size,
            "parquet_sha256": actual_sha256,
            "hf_home": os.environ["HF_HOME"],
        },
        sort_keys=True,
    )
)
PY
