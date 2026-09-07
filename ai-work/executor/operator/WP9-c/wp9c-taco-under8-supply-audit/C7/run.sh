#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-taco-under8-supply-audit/C7/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-taco-under8-supply-audit/C7/run.sh"
CONFIG="$ROOT/configs/data/wp9c-taco-under8-supply-audit.yaml"
CALIBRATION_CONFIG="$ROOT/configs/grpo/refresh-calibration.yaml"
SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-taco-under8-supply-audit/C7/audit_taco_under8_supply.py"
RUNBOOK="$ROOT/ai-work/executor/operator/WP9-c/wp9c-taco-under8-supply-audit/C7/RUNBOOK.md"
C6_FULL_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/audit_full_taco_supply.py"
C6_CORRECTION_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/audit_context_correction.py"
JSON_STRICT="$ROOT/src/code_verifier/data/json_strict.py"
OUTPUT_DIR="/home/dzy/wp9c-taco-under8-supply-audit-C7"
LOG_PATH="/home/dzy/wp9c-taco-under8-supply-audit-C7.log"

cd "$ROOT"
for required in "$PYTHON" "$CHECKPOINT" "$SELF" "$CONFIG" "$CALIBRATION_CONFIG" "$SCRIPT" "$RUNBOOK" "$C6_FULL_SCRIPT" "$C6_CORRECTION_SCRIPT" "$JSON_STRICT"; do
  if [[ ! -e "$required" ]]; then
    echo "missing C7 dependency: $required" >&2
    exit 2
  fi
done

"$PYTHON" - "$CHECKPOINT" "$CALIBRATION_CONFIG" "$CONFIG" "$SELF" "$SCRIPT" "$RUNBOOK" "$C6_FULL_SCRIPT" "$C6_CORRECTION_SCRIPT" "$JSON_STRICT" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

(
    _,
    checkpoint_text,
    calibration_text,
    config_text,
    self_text,
    script_text,
    runbook_text,
    c6_full_text,
    c6_correction_text,
    json_strict_text,
) = sys.argv
checkpoint = json.loads(Path(checkpoint_text).read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("requires_rtx4090") is not False
    or checkpoint.get("old_calibration_retry_frozen") is not True
    or checkpoint.get("old_rtx4090_calibration_frozen") is not True
):
    raise SystemExit("C7 checkpoint state/protocol is not authorized")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C7 checkpoint bindings are invalid")
for key, value in (
    ("refresh_calibration_config_sha256", calibration_text),
    ("audit_config_sha256", config_text),
    ("runner_sha256", self_text),
    ("audit_python_sha256", script_text),
    ("runbook_sha256", runbook_text),
    ("c6_full_taco_script_sha256", c6_full_text),
    ("c6_context_correction_script_sha256", c6_correction_text),
    ("json_strict_sha256", json_strict_text),
):
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C7 checkpoint binding mismatch: {key}")
PY

if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing C7 output/log" >&2
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
    raise SystemExit("C7 report digest mismatch")
report = json.loads(payload)
if (
    report.get("schema_version") != "wp9c-taco-under8-supply-audit-v1"
    or report.get("formal_eligible") is not False
    or report.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
):
    raise SystemExit("C7 report identity/formal status mismatch")
context = report.get("taco_under8_preaugmentation_context")
apps = report.get("apps_under8_after_taco_under8_dedup")
supply = report.get("supply_projection")
if (
    not isinstance(context, dict)
    or not isinstance(apps, dict)
    or not isinstance(supply, dict)
    or context.get("formal_context_eligible_count") is not None
    or context.get("final_augmented_context_recheck_required") is not True
    or apps.get("formal_context_eligible_count") is not None
    or apps.get("post_augmentation_context_recheck_required") is not True
    or supply.get("zero_attrition_planning_union")
    != 1276
    + report.get("incremental_taco_under8_preaugmentation_planning", -1)
    + apps.get("retained_preaugmentation_planning_count", -1)
):
    raise SystemExit("C7 report planning/formal semantics mismatch")
print(
    json.dumps(
        {
            "status": "verified_engineering_audit_only",
            "incremental_taco_under8_preaugmentation_planning": report.get(
                "incremental_taco_under8_preaugmentation_planning"
            ),
            "apps_under8_after_taco_under8_dedup": apps,
            "supply_projection": supply,
            "report_sha256": actual,
        },
        sort_keys=True,
    )
)
PY
