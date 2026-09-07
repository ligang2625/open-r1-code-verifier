#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
SOURCE_CONFIG="$ROOT/configs/data/wp9c-function-refresh-taco-audit.yaml"
AUDIT_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_taco_shard.py"
OUTPUT_DIR="/home/dzy/wp9c-function-refresh-audit-taco-shard0-C0"
LOG_PATH="/home/dzy/wp9c-function-refresh-audit-taco-shard0-C0.log"

cd "$ROOT"

if [[ ! -x "$PYTHON" || ! -f "$SOURCE_CONFIG" || ! -f "$AUDIT_SCRIPT" ]]; then
  echo "missing project python/config/audit script" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing TACO audit output/log" >&2
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
    raise SystemExit("TACO audit output incomplete")
payload = report_path.read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = digest_path.read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit("TACO audit report digest mismatch")
report = json.loads(payload)
if report.get("formal_eligible") is not False:
    raise SystemExit("shard audit must remain non-formal")
counts = report.get("counts", {})
print(json.dumps({
    "status": "verified_audit_only",
    "total_rows": counts.get("total_rows"),
    "function_call_rows": counts.get("function_call_rows"),
    "function_call_ge8_rows": counts.get("function_call_ge8_rows"),
    "unique_ge8_rows": counts.get("unique_ge8_rows"),
    "unique_ge8_with_solution_rows": counts.get("unique_ge8_with_solution_rows"),
    "direct_signature_ge8_rows": counts.get("direct_signature_ge8_rows"),
    "class_method_only_signature_ge8_rows": counts.get("class_method_only_signature_ge8_rows"),
    "no_recoverable_signature_ge8_rows": counts.get("no_recoverable_signature_ge8_rows"),
    "report_sha256": actual,
}, sort_keys=True))
PY
