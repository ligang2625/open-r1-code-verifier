#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
SOURCE_CONFIG="$ROOT/configs/data/wp9c-function-refresh-openr1-decontaminated-audit.yaml"
AUDIT_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_openr1_decontaminated_sample.py"
OUTPUT_DIR="/home/dzy/wp9c-function-refresh-audit-openr1-decontaminated-sample-C0"
LOG_PATH="/home/dzy/wp9c-function-refresh-audit-openr1-decontaminated-sample-C0.log"

cd "$ROOT"

if [[ ! -x "$PYTHON" || ! -f "$SOURCE_CONFIG" || ! -f "$AUDIT_SCRIPT" ]]; then
  echo "missing project python/config/audit script" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing audit output/log" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

set -o pipefail
"$PYTHON" "$AUDIT_SCRIPT" \
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
report_path = output / "report.json"
digest_path = output / "report.sha256"
if not report_path.is_file() or not digest_path.is_file():
    raise SystemExit("audit output incomplete")
payload = report_path.read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = digest_path.read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit("audit report digest mismatch")
report = json.loads(payload)
if report.get("formal_eligible") is not False:
    raise SystemExit("sample audit must remain non-formal")
print(json.dumps({
    "status": "verified_audit_only",
    "aggregate_counts": report.get("aggregate_counts"),
    "aggregate_function_source_counts": report.get("aggregate_function_source_counts"),
    "shards": [
        {
            "shard_index": shard.get("shard_index"),
            "counts": shard.get("counts"),
            "source_counts": shard.get("source_counts"),
            "function_source_counts": shard.get("function_source_counts"),
        }
        for shard in report.get("shards", [])
    ],
    "report_sha256": actual,
}, sort_keys=True))
PY
