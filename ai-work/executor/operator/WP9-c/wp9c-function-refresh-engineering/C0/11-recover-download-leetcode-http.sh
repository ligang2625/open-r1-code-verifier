#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
APPS_SNAPSHOT="$HOME/.cache/huggingface/hub/datasets--codeparrot--apps/snapshots/21e74ddf8de1a21436da12e3e653065c5213e9d1/train.jsonl"
APPS_SHA256="45e82ef22ed8e7c0c04d881a21b923e9dd233157896b0b8d5b3493e887499cae"
DATASET_ID="tkeskin/leetcode-solutions"
REVISION="ac62251a3fa13388bf4dd348160adb1e0f95bbaf"
RELATIVE_PATH="leetcode-solutions.parquet"
EXPECTED_SHA256="48f49b9967f4bb059d7d55080f208f74c1ef957e380fcdd0ea08f0eeb1b560ea"

cd "$ROOT"

if [[ ! -x "$PYTHON" ]]; then
  echo "missing project python: $PYTHON" >&2
  exit 2
fi
if [[ -z "${http_proxy:-}${https_proxy:-}${HTTP_PROXY:-}${HTTPS_PROXY:-}" ]]; then
  echo "proxy variables are not set; run source ~/.bashrc first" >&2
  exit 2
fi

# Preserve the successfully downloaded APPS source and verify it before recovery.
"$PYTHON" - "$APPS_SNAPSHOT" "$APPS_SHA256" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_, path_text, expected = sys.argv
path = Path(path_text)
if not path.is_file():
    raise SystemExit(f"cached APPS source is missing: {path}")
digest = hashlib.sha256()
with path.open("rb") as handle:
    while chunk := handle.read(8 * 1024 * 1024):
        digest.update(chunk)
actual = digest.hexdigest()
if actual != expected:
    raise SystemExit(f"cached APPS SHA256 mismatch: expected {expected}, got {actual}")
print(f"APPS cache verified: {actual}")
PY

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=0
export TRANSFORMERS_OFFLINE=1
# The failed C0 run had hf_xet enabled. This recovery deliberately disables
# the Xet client so the Xet-backed parquet is fetched through regular Hub HTTP.
export HF_HUB_DISABLE_XET=1

"$PYTHON" - "$DATASET_ID" "$REVISION" "$RELATIVE_PATH" "$EXPECTED_SHA256" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

_, dataset_id, revision, relative_path, expected_sha = sys.argv
snapshot = Path(
    snapshot_download(
        repo_id=dataset_id,
        repo_type="dataset",
        revision=revision,
        allow_patterns=["README.md", relative_path],
        local_files_only=False,
    )
)
if snapshot.name != revision:
    raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
path = snapshot / relative_path
if not path.is_file():
    raise SystemExit(f"missing pinned LeetCode parquet: {path}")
digest = hashlib.sha256()
with path.open("rb") as handle:
    while chunk := handle.read(8 * 1024 * 1024):
        digest.update(chunk)
actual_sha = digest.hexdigest()
if actual_sha != expected_sha:
    raise SystemExit(f"LeetCode SHA256 mismatch: expected {expected_sha}, got {actual_sha}")
print(
    json.dumps(
        {
            "status": "verified",
            "transport": "hub_http_xet_disabled",
            "snapshot": str(snapshot),
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": actual_sha,
        },
        sort_keys=True,
    )
)
PY
