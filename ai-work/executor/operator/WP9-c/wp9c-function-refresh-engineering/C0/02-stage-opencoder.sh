#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
SOURCE_CONFIG="$ROOT/configs/data/wp9c-function-refresh-sources.yaml"
OUTPUT_DIR="/home/dzy/wp9c-function-refresh-stage-opencoder-C0"
LOG_PATH="/home/dzy/wp9c-function-refresh-stage-opencoder-C0.log"

cd "$ROOT"

if [[ ! -x "$PYTHON" ]]; then
  echo "missing project python: $PYTHON" >&2
  exit 2
fi
if [[ ! -f "$SOURCE_CONFIG" ]]; then
  echo "missing source config: $SOURCE_CONFIG" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" ]]; then
  echo "refusing to overwrite existing output: $OUTPUT_DIR" >&2
  exit 2
fi
if [[ -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing log: $LOG_PATH" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# This is intentionally a user-run long task. It reads only the pinned local
# OpenCoder snapshot and writes a fresh engineering stage. It does not touch
# WP9-a formal artifacts, calibration retry state, or any 4090 operator gate.
set -o pipefail
"$PYTHON" -m code_verifier.data.function_refresh_engineering \
  stage-opencoder \
  --source-config "$SOURCE_CONFIG" \
  --output-dir "$OUTPUT_DIR" \
  2>&1 | tee "$LOG_PATH"

"$PYTHON" - "$OUTPUT_DIR" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, output_text = sys.argv
output = Path(output_text)
manifest_path = output / "stage_manifest.json"
candidates_path = output / "candidates.jsonl"
if not manifest_path.is_file() or not candidates_path.is_file():
    raise SystemExit("stage output is incomplete")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
expected_digest = manifest.get("records_digest")
if not isinstance(expected_digest, str):
    raise SystemExit("stage manifest is missing records_digest")

digest = hashlib.sha256()
count = 0
with candidates_path.open("rb") as handle:
    for line in handle:
        if not line.strip():
            continue
        digest.update(line)
        count += 1
actual_digest = digest.hexdigest()
if actual_digest != expected_digest:
    raise SystemExit(
        f"candidate digest mismatch: expected {expected_digest}, got {actual_digest}"
    )
if count != manifest.get("candidate_count"):
    raise SystemExit(
        f"candidate count mismatch: manifest={manifest.get('candidate_count')} file={count}"
    )

summary = {
    "status": "verified",
    "output_dir": str(output),
    "candidate_count": count,
    "quality_safe_ge8_count": manifest.get("quality_safe_ge8_count"),
    "quality_gate_lt8_count": manifest.get("quality_gate_lt8_count"),
    "records_digest": actual_digest,
    "source": manifest.get("source"),
}
print(json.dumps(summary, sort_keys=True))
PY
