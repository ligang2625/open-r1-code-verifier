#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
SOURCE_CONFIG="$ROOT/configs/data/wp9c-native-function-supply-audit.yaml"
AUDIT_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_native_function_supply.py"
REFERENCE_DATASET_DIR="/home/dzy/wp8-formal-sync/data/prepared"
REFRESH_CONFIG="$ROOT/configs/data/refresh.yaml"
OUTPUT_DIR="/home/dzy/wp9c-native-function-supply-audit-C0"
LOG_PATH="/home/dzy/wp9c-native-function-supply-audit-C0.log"

cd "$ROOT"

if [[ ! -x "$PYTHON" || ! -f "$SOURCE_CONFIG" || ! -f "$AUDIT_SCRIPT" || ! -f "$REFRESH_CONFIG" ]]; then
  echo "missing project python/config/audit script" >&2
  exit 2
fi
if [[ ! -f "$REFERENCE_DATASET_DIR/canonical/problems.jsonl" ]]; then
  echo "missing frozen reference canonical dataset" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing native supply audit output/log" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# Engineering-only supply audit. It parses and fingerprints source tests but
# executes no source solution/test payload, materializes no candidate pool,
# and does not touch calibration retry or the RTX4090 operator state.
set -o pipefail
"$PYTHON" "$AUDIT_SCRIPT" \
  --source-config "$SOURCE_CONFIG" \
  --reference-dataset-dir "$REFERENCE_DATASET_DIR" \
  --refresh-config "$REFRESH_CONFIG" \
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
    raise SystemExit("native supply audit output is incomplete")
payload = report_path.read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = digest_path.read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit(f"native supply audit report digest mismatch: expected {expected}, got {actual}")
report = json.loads(payload)
if report.get("formal_eligible") is not False:
    raise SystemExit("native supply audit must remain non-formal")
source_reports = report.get("source_reports", {})
supply = report.get("wp9c_supply_context", {})
print(
    json.dumps(
        {
            "status": "verified_audit_only",
            "apps": source_reports.get("apps_train"),
            "leetcode": source_reports.get("leetcode_merged"),
            "raw_structural_candidate_count": report.get("raw_structural_candidate_count"),
            "retained_external_new_count": report.get("retained_external_new_count"),
            "retained_source_counts": report.get("retained_source_counts"),
            "remaining_gap_before_context_and_piston": supply.get("remaining_gap_before_context_and_piston"),
            "rejection_reason_counts": report.get("rejection_reason_counts"),
            "report_sha256": actual,
        },
        sort_keys=True,
    )
)
PY
