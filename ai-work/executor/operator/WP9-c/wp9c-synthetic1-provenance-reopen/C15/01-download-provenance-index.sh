#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-provenance-reopen/C15/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-provenance-reopen/C15/01-download-provenance-index.sh"
CONFIG="$ROOT/configs/data/wp9c-synthetic1-provenance-reopen.yaml"
OUT="/home/dzy/wp9c-synthetic1-provenance-download-C15"
LOG_PATH="/home/dzy/wp9c-synthetic1-provenance-download-C15.log"
DATASET_ID="PrimeIntellect/SYNTHETIC-1-SFT-Data"
REVISION="e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8"

if [[ -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing C15 download log" >&2
  exit 2
fi
exec > >(tee "$LOG_PATH") 2>&1

"$PYTHON" - "$CHECKPOINT" "$SELF" "$CONFIG" "$ROOT" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

_, checkpoint_text, self_text, config_text, root_text = sys.argv
checkpoint_path = Path(checkpoint_text)
config_path = Path(config_text)
root = Path(root_text)
checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
if not isinstance(config, dict):
    raise SystemExit("C15 config is invalid")
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("operator_gate") != "wp9c-synthetic1-provenance-reopen"
    or checkpoint.get("candidate_supply_increment_allowed") is not False
    or checkpoint.get("generation_frozen") is not True
    or checkpoint.get("piston_frozen") is not True
    or checkpoint.get("grpo_frozen") is not True
    or checkpoint.get("gpu_frozen") is not True
):
    raise SystemExit("C15 checkpoint does not authorize provenance-only download")
if config.get("version") != "wp9c-synthetic1-provenance-reopen-v1":
    raise SystemExit("C15 config identity drift")
necessity = config.get("necessity")
purpose = config.get("purpose")
source = config.get("source")
if not isinstance(necessity, dict) or not isinstance(purpose, dict) or not isinstance(source, dict):
    raise SystemExit("C15 config structure is invalid")
if (
    necessity.get("fixed_candidate_universe") != 2505
    or necessity.get("under8_successes_required_if_all_ready_pass") != 999
    or necessity.get("non_primeintellect_under8_maximum") != 688
    or necessity.get("minimum_deepcoder_primeintellect_successes_required") != 311
    or purpose.get("incremental_candidate_supply_allowed") is not False
    or purpose.get("response_lineage_only") is not True
    or source.get("dataset_id") != "PrimeIntellect/SYNTHETIC-1-SFT-Data"
    or source.get("revision") != "e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8"
):
    raise SystemExit("C15 necessity/source contract drift")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C15 checkpoint bindings are invalid")
for key, path in (("download_runner_sha256", Path(self_text)), ("audit_config_sha256", config_path)):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C15 checkpoint binding mismatch: {key}")
for config_key, sha_key in (
    ("c12_report", "c12_report_sha256"),
    ("c13_report", "c13_report_sha256"),
    ("c14_report", "c14_report_sha256"),
):
    config_bindings = config.get("bindings")
    if not isinstance(config_bindings, dict):
        raise SystemExit("C15 config bindings are invalid")
    path = Path(str(config_bindings[config_key]))
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != config_bindings.get(sha_key):
        raise SystemExit(f"C15 prerequisite digest mismatch: {config_key}")
c11_rel = str(config["bindings"]["c11_checkpoint"])
c11 = json.loads((root / c11_rel).read_text(encoding="utf-8"))
if c11.get("status") != "paused_by_user":
    raise SystemExit("historical C11 must remain paused")
pause = c11.get("pause_directive")
if not isinstance(pause, dict) or pause.get("download_authorized") is not False:
    raise SystemExit("historical C11 pause directive drift")
PY

if [[ -e "$OUT" || -e "$OUT.tmp" ]]; then
  echo "refusing to overwrite existing C15 download directory or temporary directory" >&2
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
    "schema_version": "wp9c-synthetic1-provenance-download-v1",
    "dataset_id": dataset_id,
    "revision": revision,
    "use_class": "provenance_index_only",
    "incremental_candidate_supply": 0,
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
