#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/02-audit-full-taco.sh"
CONFIG="$ROOT/configs/data/wp9c-taco-full-supply-audit.yaml"
CALIBRATION_CONFIG="$ROOT/configs/grpo/refresh-calibration.yaml"
DOWNLOAD_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/01-download-full-taco.sh"
SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/audit_full_taco_supply.py"
RUNBOOK="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/RUNBOOK.md"
JSON_STRICT="$ROOT/src/code_verifier/data/json_strict.py"
OUTPUT_DIR="/home/dzy/wp9c-taco-full-supply-audit-C6-r1"
LOG_PATH="/home/dzy/wp9c-taco-full-supply-audit-C6-r1.log"

cd "$ROOT"
if [[ ! -x "$PYTHON" || ! -f "$CHECKPOINT" || ! -f "$SELF" || ! -f "$CONFIG" || ! -f "$CALIBRATION_CONFIG" || ! -f "$DOWNLOAD_SCRIPT" || ! -f "$SCRIPT" || ! -f "$RUNBOOK" || ! -f "$JSON_STRICT" ]]; then
  echo "missing project python/C6 checkpoint/config/sidecar file" >&2
  exit 2
fi

"$PYTHON" - "$CHECKPOINT" "$CALIBRATION_CONFIG" "$CONFIG" "$DOWNLOAD_SCRIPT" "$SELF" "$SCRIPT" "$RUNBOOK" "$JSON_STRICT" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, calibration_text, config_text, download_text, self_text, script_text, runbook_text, json_strict_text = sys.argv
checkpoint = json.loads(Path(checkpoint_text).read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("requires_rtx4090") is not False
    or checkpoint.get("old_calibration_retry_frozen") is not True
    or checkpoint.get("old_rtx4090_calibration_frozen") is not True
):
    raise SystemExit("C6 checkpoint state/protocol is not authorized for this audit")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C6 checkpoint bindings are invalid")
for key, value in (
    ("refresh_calibration_config_sha256", calibration_text),
    ("taco_audit_config_sha256", config_text),
    ("download_script_sha256", download_text),
    ("audit_runner_sha256", self_text),
    ("audit_python_sha256", script_text),
    ("runbook_sha256", runbook_text),
    ("json_strict_sha256", json_strict_text),
):
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C6 checkpoint binding mismatch: {key}")
PY

if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing full-TACO audit output/log" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

set -o pipefail
"$PYTHON" "$SCRIPT" --config "$CONFIG" --output-dir "$OUTPUT_DIR" 2>&1 | tee "$LOG_PATH"

"$PYTHON" - "$OUTPUT_DIR" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, output_text = sys.argv
output = Path(output_text)
payload = (output / "report.json").read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = (output / "report.sha256").read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit("full-TACO report digest mismatch")
report = json.loads(payload)
if (
    report.get("formal_eligible") is not False
    or report.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
):
    raise SystemExit("full-TACO supply audit identity/formal status mismatch")
under8 = report.get("apps_under8_after_taco_dedup")
supply = report.get("supply_projection")
if (
    not isinstance(under8, dict)
    or not isinstance(supply, dict)
    or under8.get("baseline_preaugmentation_planning_count") != 1119
    or under8.get("formal_context_eligible_count") is not None
    or under8.get("post_augmentation_context_recheck_required") is not True
    or supply.get("apps_under8_preaugmentation_planning_after_taco_dedup")
    != under8.get("retained_preaugmentation_planning_count")
):
    raise SystemExit("full-TACO report is missing TACO-aware APPS-under8 dedup evidence")
print(json.dumps({
    "status": "verified_engineering_audit_only",
    "incremental_taco_context_eligible": report.get("incremental_taco_context_eligible"),
    "apps_under8_after_taco_dedup": under8,
    "supply_projection": supply,
    "report_sha256": actual,
}, sort_keys=True))
PY
