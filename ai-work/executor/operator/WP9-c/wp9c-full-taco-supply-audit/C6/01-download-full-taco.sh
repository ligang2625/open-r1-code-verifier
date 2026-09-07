#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/01-download-full-taco.sh"
CALIBRATION_CONFIG="$ROOT/configs/grpo/refresh-calibration.yaml"
TACO_CONFIG="$ROOT/configs/data/wp9c-taco-full-supply-audit.yaml"
OUTPUT_DIR="/home/dzy/wp9c-taco-full-download-C6"
DATASET_ID="BAAI/TACO"
REVISION="d593ed0a2becbbc952230bb89be09189bf1056dc"

cd "$ROOT"
if [[ ! -x "$PYTHON" || ! -f "$CHECKPOINT" || ! -f "$CALIBRATION_CONFIG" || ! -f "$TACO_CONFIG" || ! -f "$SELF" ]]; then
  echo "missing project python/C6 checkpoint/config/download script" >&2
  exit 2
fi

"$PYTHON" - "$CHECKPOINT" "$CALIBRATION_CONFIG" "$TACO_CONFIG" "$SELF" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, calibration_text, taco_text, self_text = sys.argv
checkpoint = json.loads(Path(checkpoint_text).read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("requires_rtx4090") is not False
    or checkpoint.get("old_calibration_retry_frozen") is not True
    or checkpoint.get("old_rtx4090_calibration_frozen") is not True
):
    raise SystemExit("C6 checkpoint state/protocol is not authorized for this download")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C6 checkpoint bindings are invalid")
for key, value in (
    ("refresh_calibration_config_sha256", calibration_text),
    ("taco_audit_config_sha256", taco_text),
    ("download_script_sha256", self_text),
):
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C6 checkpoint binding mismatch: {key}")
PY

if [[ -z "${http_proxy:-}${https_proxy:-}${HTTP_PROXY:-}${HTTPS_PROXY:-}" ]]; then
  echo "proxy variables are not set; run source ~/.bashrc first" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" ]]; then
  echo "refusing to overwrite existing output: $OUTPUT_DIR" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=0
export TRANSFORMERS_OFFLINE=1

"$PYTHON" - "$OUTPUT_DIR" "$DATASET_ID" "$REVISION" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

_, output_text, dataset_id, revision = sys.argv
output = Path(output_text)
api = HfApi()
info = api.repo_info(repo_id=dataset_id, repo_type="dataset", revision=revision, files_metadata=True)
if info.sha != revision:
    raise SystemExit(f"resolved revision mismatch: expected {revision}, got {info.sha}")
rows = []
for sibling in info.siblings or []:
    name = sibling.rfilename
    if not (name.startswith("ALL/train-") and name.endswith("-of-00009.parquet")):
        continue
    lfs = sibling.lfs
    sha = getattr(lfs, "sha256", None) if lfs is not None else None
    size = getattr(lfs, "size", None) if lfs is not None else None
    if not isinstance(sha, str) or len(sha) != 64 or not isinstance(size, int) or size <= 0:
        raise SystemExit(f"missing pinned LFS identity for {name}")
    rows.append({"path": name, "size": size, "sha256": sha})
rows.sort(key=lambda row: row["path"])
if len(rows) != 9 or [row["path"] for row in rows] != [f"ALL/train-{i:05d}-of-00009.parquet" for i in range(9)]:
    raise SystemExit(f"expected exactly nine TACO ALL/train shards, got {[row['path'] for row in rows]}")

snapshot = Path(snapshot_download(
    repo_id=dataset_id,
    repo_type="dataset",
    revision=revision,
    allow_patterns=["README.md", "ALL/train-*-of-00009.parquet"],
    local_files_only=False,
)).resolve()
if snapshot.name != revision:
    raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
for row in rows:
    path = snapshot / row["path"]
    if not path.is_file() or path.stat().st_size != row["size"]:
        raise SystemExit(f"size/missing mismatch for {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != row["sha256"]:
        raise SystemExit(f"SHA256 mismatch for {path}: expected {row['sha256']}, got {actual}")

manifest = {
    "schema_version": "wp9c-taco-full-download-v1",
    "dataset_id": dataset_id,
    "revision": revision,
    "snapshot_path": str(snapshot),
    "shards": rows,
}
payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
output.parent.mkdir(parents=True, exist_ok=True)
temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
(temporary / "manifest.json").write_text(payload, encoding="utf-8")
(temporary / "manifest.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii")
os.replace(temporary, output)
print(payload, end="")
PY
