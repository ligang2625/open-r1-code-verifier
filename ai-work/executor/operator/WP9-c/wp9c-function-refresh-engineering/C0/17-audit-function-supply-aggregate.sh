#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CONFIG="$ROOT/configs/data/wp9c-function-supply-aggregate-audit.yaml"
CONFIG_SHA256="c857b4df0665f42c210e23caa608a4c3ef29f95184743b2328638a52667e090e"
AUDIT_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_function_supply_aggregate.py"
AUDIT_SCRIPT_SHA256="0cd9f91dfddffec42e4d0cda83e70320818820d77f8c565c2d485e944b2559b4"
OUTPUT_DIR="/home/dzy/wp9c-function-supply-aggregate-audit-C0"
LOG_PATH="/home/dzy/wp9c-function-supply-aggregate-audit-C0.log"

cd "$ROOT"

if [[ ! -x "$PYTHON" || ! -f "$CONFIG" || ! -f "$AUDIT_SCRIPT" ]]; then
  echo "missing project python/config/aggregate audit script" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing aggregate audit output/log" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_XET=1

"$PYTHON" - "$CONFIG" "$CONFIG_SHA256" "$AUDIT_SCRIPT" "$AUDIT_SCRIPT_SHA256" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_, config_text, expected_config, script_text, expected_script = sys.argv
for label, path_text, expected in (
    ("aggregate_config", config_text, expected_config),
    ("aggregate_script", script_text, expected_script),
):
    path = Path(path_text)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"{label} SHA256 mismatch: expected {expected}, got {actual}")
    print(f"verified {label}: {actual}")
PY

# Long, offline, audit-only operation. It performs no candidate code execution,
# no test generation, no Piston calls, no calibration work, and no RTX4090 work.
set -o pipefail
"$PYTHON" "$AUDIT_SCRIPT" \
  --config "$CONFIG" \
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
    raise SystemExit("aggregate supply audit output is incomplete")
payload = report_path.read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = digest_path.read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit(f"aggregate report digest mismatch: expected {expected}, got {actual}")
report = json.loads(payload)
if report.get("schema_version") != "wp9c-function-supply-aggregate-audit-v1":
    raise SystemExit("aggregate report schema mismatch")
if report.get("formal_eligible") is not False:
    raise SystemExit("aggregate audit must remain non-formal")
supply = report.get("aggregate_supply", {})
print(
    json.dumps(
        {
            "status": "verified_audit_only",
            "ready_context_eligible_count": supply.get("ready_context_eligible_count"),
            "augmentable_context_eligible_count": supply.get("augmentable_context_eligible_count"),
            "zero_attrition_potential_count": supply.get("zero_attrition_potential_count"),
            "remaining_gap_zero_attrition": supply.get("remaining_gap_zero_attrition"),
            "ready_source_counts": supply.get("ready_source_counts"),
            "minimum_added_test_slots_to_reach_8": supply.get("minimum_added_test_slots_to_reach_8"),
            "report_sha256": actual,
        },
        sort_keys=True,
    )
)
PY
