#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/run.sh"
CONFIG="$ROOT/configs/data/wp9c-function-supply-context-correction.yaml"
SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/audit_context_correction.py"
RUNBOOK="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/RUNBOOK.md"
OUTPUT_DIR="/home/dzy/wp9c-function-supply-context-correction-C6-r1"
LOG_PATH="/home/dzy/wp9c-function-supply-context-correction-C6-r1.log"

cd "$ROOT"
if [[ ! -x "$PYTHON" || ! -f "$CHECKPOINT" || ! -f "$SELF" || ! -f "$CONFIG" || ! -f "$SCRIPT" || ! -f "$RUNBOOK" ]]; then
  echo "missing project python/context-correction sidecar file" >&2
  exit 2
fi

"$PYTHON" - "$CHECKPOINT" "$CONFIG" "$SELF" "$SCRIPT" "$RUNBOOK" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, config_text, self_text, script_text, runbook_text = sys.argv
checkpoint = json.loads(Path(checkpoint_text).read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("requires_rtx4090") is not False
    or checkpoint.get("old_calibration_retry_frozen") is not True
    or checkpoint.get("old_rtx4090_calibration_frozen") is not True
):
    raise SystemExit("context-correction checkpoint state/protocol is not authorized")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("context-correction checkpoint bindings are invalid")
for key, value in (
    ("config_sha256", config_text),
    ("runner_sha256", self_text),
    ("audit_script_sha256", script_text),
    ("runbook_sha256", runbook_text),
):
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"context-correction checkpoint binding mismatch: {key}")
PY

if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing context-correction output/log" >&2
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
    raise SystemExit("context-correction report digest mismatch")
report = json.loads(payload)
corrected = report.get("corrected_supply")
if (
    report.get("schema_version") != "wp9c-function-supply-context-correction-v1"
    or report.get("formal_eligible") is not False
    or report.get("historical_evidence_mutated") is not False
    or not isinstance(corrected, dict)
    or type(corrected.get("corrected_ready_context_eligible_count")) is not int
    or type(corrected.get("corrected_augmentable_preaugmentation_planning_count")) is not int
    or corrected.get("under8_formal_context_eligible_count") is not None
    or corrected.get("under8_post_augmentation_context_recheck_required") is not True
):
    raise SystemExit("context-correction report identity/status mismatch")
print(json.dumps({
    "status": "verified_engineering_correction_only",
    "corrected_supply": corrected,
    "report_sha256": actual,
}, sort_keys=True))
PY
