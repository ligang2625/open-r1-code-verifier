#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
DATASET_ID="open-r1/verifiable-coding-problems-python_decontaminated-tested-shuffled"
REVISION="98191eb6eefd276b7ebb4eb8d25c4a167cc65605"
RELATIVE_PATH="data/train-00000-of-00001.parquet"
EXPECTED_SHA256="0f4967c744a1ef7acfc9aadcdefcb64be7b5567448e507f80a48d3b3d0bb2686"
EXPECTED_SIZE="146139801"

cd "$ROOT"

if [[ ! -x "$PYTHON" ]]; then
  echo "missing project python: $PYTHON" >&2
  exit 2
fi

if [[ -z "${http_proxy:-}${https_proxy:-}${HTTP_PROXY:-}${HTTPS_PROXY:-}" ]]; then
  echo "proxy variables are not set." >&2
  echo "Run this from your interactive terminal as:" >&2
  echo "  source ~/.bashrc" >&2
  echo "  bash $ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/03-download-openr1-tested.sh" >&2
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
    raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")

readme = snapshot / "README.md"
parquet = snapshot / relative_path
if not readme.is_file():
    raise SystemExit(f"missing pinned README: {readme}")
if not parquet.is_file():
    raise SystemExit(f"missing pinned parquet: {parquet}")

actual_size = parquet.stat().st_size
if actual_size != expected_size:
    raise SystemExit(f"parquet size mismatch: expected {expected_size}, got {actual_size}")

digest = hashlib.sha256()
with parquet.open("rb") as handle:
    while chunk := handle.read(8 * 1024 * 1024):
        digest.update(chunk)
actual_sha256 = digest.hexdigest()
if actual_sha256 != expected_sha256:
    raise SystemExit(f"parquet SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}")

readme_text = readme.read_text(encoding="utf-8")
has_license_metadata = any(
    line.strip().casefold().startswith("license:") for line in readme_text.splitlines()
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
            "dataset_card_declares_license": has_license_metadata,
            "formal_license_status": "unresolved" if not has_license_metadata else "requires_review",
        },
        sort_keys=True,
    )
)
PY
