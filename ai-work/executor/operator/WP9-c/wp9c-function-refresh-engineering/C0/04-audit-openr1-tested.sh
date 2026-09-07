#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
SOURCE_CONFIG="$ROOT/configs/data/wp9c-function-refresh-openr1-audit.yaml"
AUDIT_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_openr1_tested.py"
OUTPUT_DIR="/home/dzy/wp9c-function-refresh-audit-openr1-tested-C0"
LOG_PATH="/home/dzy/wp9c-function-refresh-audit-openr1-tested-C0.log"

cd "$ROOT"

if [[ ! -x "$PYTHON" ]]; then
  echo "missing project python: $PYTHON" >&2
  exit 2
fi
if [[ ! -f "$SOURCE_CONFIG" || ! -f "$AUDIT_SCRIPT" ]]; then
  echo "missing source config or audit script" >&2
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

# Audit-only. No source testcase string is executed, no candidate pool is
# materialized, and no Piston/calibration/RTX4090 work is started.
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
    raise SystemExit("audit output is incomplete")

payload = report_path.read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = digest_path.read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit(f"audit report digest mismatch: expected {expected}, got {actual}")
report = json.loads(payload)
if report.get("formal_eligible") is not False:
    raise SystemExit("audit-only source must not be marked formal eligible")

counts = report.get("counts", {})
summary = {
    "status": "verified_audit_only",
    "output_dir": str(output),
    "total_rows": counts.get("total_rows"),
    "pure_function_call_rows": counts.get("pure_function_call_rows"),
    "pure_function_call_ge8_raw": counts.get("pure_function_call_ge8_raw"),
    "raw_unique_ge8_rows": counts.get("raw_unique_ge8_rows"),
    "unique_supported_signature_rows": counts.get("unique_supported_signature_rows"),
    "strict_json_unambiguous_ge8_rows": counts.get("strict_json_unambiguous_ge8_rows"),
    "safe_literal_unambiguous_ge8_rows": counts.get("safe_literal_unambiguous_ge8_rows"),
    "formal_blockers": report.get("formal_blockers"),
    "report_sha256": actual,
}
print(json.dumps(summary, sort_keys=True))
PY
