#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/01-download-sft-lineage.sh"
CONFIG="$ROOT/configs/data/wp9c-synthetic1-sft-lineage-audit.yaml"
OUT="/home/dzy/wp9c-synthetic1-sft-lineage-download-C11"
LOG_PATH="/home/dzy/wp9c-synthetic1-sft-lineage-download-C11.log"
DATASET_ID="PrimeIntellect/SYNTHETIC-1-SFT-Data"
REVISION="e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8"

if [[ -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing C11 download log" >&2
  exit 2
fi
exec > >(tee "$LOG_PATH") 2>&1

"$PYTHON" - "$CHECKPOINT" "$SELF" "$CONFIG" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, self_text, config_text = sys.argv
checkpoint = json.loads(Path(checkpoint_text).read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("operator_gate") != "wp9c-synthetic1-sft-response-lineage-audit"
    or checkpoint.get("generation_frozen") is not True
    or checkpoint.get("piston_frozen") is not True
    or checkpoint.get("calibration_frozen") is not True
    or checkpoint.get("grpo_frozen") is not True
):
    raise SystemExit("C11 checkpoint does not authorize the download")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C11 checkpoint bindings are invalid")
for key, value in (("download_runner_sha256", self_text), ("audit_config_sha256", config_text)):
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C11 checkpoint binding mismatch: {key}")
PY

if [[ -e "$OUT" || -e "$OUT.tmp" ]]; then
  echo "refusing to overwrite existing C11 download directory or temporary directory" >&2
  exit 2
fi
mkdir -p "$OUT.tmp"
trap 'rm -rf "$OUT.tmp"' EXIT

"$PYTHON" - "$OUT.tmp" "$DATASET_ID" "$REVISION" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import snapshot_download

_, out_text, dataset_id, revision = sys.argv
out = Path(out_text)
snapshot = Path(
    snapshot_download(
        repo_id=dataset_id,
        repo_type="dataset",
        revision=revision,
        allow_patterns=["data/train-*-of-00017.parquet"],
    )
).resolve()
if snapshot.name != revision:
    raise SystemExit(f"snapshot identity mismatch: expected {revision}, got {snapshot.name}")
files = sorted((snapshot / "data").glob("train-*-of-00017.parquet"))
expected_names = [f"train-{index:05d}-of-00017.parquet" for index in range(17)]
if [path.name for path in files] != expected_names:
    raise SystemExit(f"expected exact 17-shard file set, got {[path.name for path in files]}")
rows = []
total_rows = 0
for index, path in enumerate(files):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    row_count = pq.ParquetFile(path).metadata.num_rows
    total_rows += row_count
    rows.append(
        {
            "shard_index": index,
            "path": str(path.relative_to(snapshot)),
            "sha256": digest.hexdigest(),
            "size": path.stat().st_size,
            "rows": row_count,
        }
    )
if total_rows != 894086:
    raise SystemExit(f"expected 894086 total rows, got {total_rows}")
manifest = {
    "schema_version": "wp9c-synthetic1-sft-lineage-download-v1",
    "dataset_id": dataset_id,
    "revision": revision,
    "snapshot_path": str(snapshot),
    "shard_count": len(rows),
    "total_rows": total_rows,
    "shards": rows,
}
payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
(out / "manifest.json").write_text(payload, encoding="utf-8")
(out / "manifest.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n", encoding="ascii")
print(payload, end="")
PY

mv "$OUT.tmp" "$OUT"
trap - EXIT
