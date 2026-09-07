#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-deepcoder-function-supply-audit/C8/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-deepcoder-function-supply-audit/C8/run.sh"
CONFIG="$ROOT/configs/data/wp9c-deepcoder-function-supply-audit.yaml"
CALIBRATION_CONFIG="$ROOT/configs/grpo/refresh-calibration.yaml"
SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-deepcoder-function-supply-audit/C8/audit_deepcoder_function_supply.py"
RUNBOOK="$ROOT/ai-work/executor/operator/WP9-c/wp9c-deepcoder-function-supply-audit/C8/RUNBOOK.md"
C6_FULL_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/audit_full_taco_supply.py"
C6_CORRECTION_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/audit_context_correction.py"
REFRESH_SOURCES="$ROOT/src/code_verifier/data/refresh_sources.py"
JSON_STRICT="$ROOT/src/code_verifier/data/json_strict.py"
OUTPUT_DIR="/home/dzy/wp9c-deepcoder-function-supply-audit-C8"
LOG_PATH="/home/dzy/wp9c-deepcoder-function-supply-audit-C8.log"

cd "$ROOT"
for required in "$PYTHON" "$CHECKPOINT" "$SELF" "$CONFIG" "$CALIBRATION_CONFIG" "$SCRIPT" "$RUNBOOK" "$C6_FULL_SCRIPT" "$C6_CORRECTION_SCRIPT" "$REFRESH_SOURCES" "$JSON_STRICT"; do
  if [[ ! -e "$required" ]]; then
    echo "missing C8 dependency: $required" >&2
    exit 2
  fi
done

"$PYTHON" - "$CHECKPOINT" "$CALIBRATION_CONFIG" "$CONFIG" "$SELF" "$SCRIPT" "$RUNBOOK" "$C6_FULL_SCRIPT" "$C6_CORRECTION_SCRIPT" "$REFRESH_SOURCES" "$JSON_STRICT" <<'PY'
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
    refresh_sources_text,
    json_strict_text,
) = sys.argv
checkpoint = json.loads(Path(checkpoint_text).read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("requires_rtx4090") is not False
    or checkpoint.get("generation_frozen") is not True
    or checkpoint.get("piston_frozen") is not True
    or checkpoint.get("old_calibration_retry_frozen") is not True
    or checkpoint.get("old_rtx4090_calibration_frozen") is not True
):
    raise SystemExit("C8 checkpoint state/protocol is not authorized")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C8 checkpoint bindings are invalid")
for key, value in (
    ("refresh_calibration_config_sha256", calibration_text),
    ("audit_config_sha256", config_text),
    ("runner_sha256", self_text),
    ("audit_python_sha256", script_text),
    ("runbook_sha256", runbook_text),
    ("c6_full_taco_script_sha256", c6_full_text),
    ("c6_context_correction_script_sha256", c6_correction_text),
    ("refresh_sources_sha256", refresh_sources_text),
    ("json_strict_sha256", json_strict_text),
):
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C8 checkpoint binding mismatch: {key}")
PY

if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing C8 output/log" >&2
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
    raise SystemExit("C8 report digest mismatch")
report = json.loads(payload)
if (
    report.get("schema_version") != "wp9c-deepcoder-function-supply-audit-v1"
    or report.get("formal_eligible") is not False
    or report.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
):
    raise SystemExit("C8 report identity/formal status mismatch")
artifacts = report.get("artifact_sha256")
artifact_files = {
    "deepcoder_ready_candidates": "deepcoder_ready_candidates.jsonl",
    "deepcoder_under8_candidates": "deepcoder_under8_candidates.jsonl",
    "ready_context": "ready_context.jsonl",
    "under8_context": "under8_context.jsonl",
    "ready_dedup_decisions": "ready_dedup_decisions.jsonl",
    "under8_dedup_decisions": "under8_dedup_decisions.jsonl",
    "c7_under8_after_deepcoder_decisions": "c7_under8_after_deepcoder_decisions.jsonl",
}
if not isinstance(artifacts, dict):
    raise SystemExit("C8 artifact digest map is missing")
for key, filename in artifact_files.items():
    artifact_path = output / filename
    artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if artifacts.get(key) != artifact_sha256:
        raise SystemExit(f"C8 artifact digest mismatch: {key}")
under8_context = report.get("under8_preaugmentation_context")
c7 = report.get("c7_under8_after_deepcoder_dedup")
supply = report.get("supply_projection")
if (
    not isinstance(under8_context, dict)
    or not isinstance(c7, dict)
    or not isinstance(supply, dict)
    or under8_context.get("formal_context_eligible_count") is not None
    or under8_context.get("final_augmented_context_recheck_required") is not True
    or c7.get("formal_context_eligible_count") is not None
    or c7.get("post_augmentation_context_recheck_required") is not True
):
    raise SystemExit("C8 under8 formal/planning semantics mismatch")
ready = report.get("incremental_deepcoder_ready_context_eligible")
under8 = report.get("incremental_deepcoder_under8_preaugmentation_planning")
c7_retained = c7.get("retained_preaugmentation_planning_count")
if not all(isinstance(value, int) for value in (ready, under8, c7_retained)):
    raise SystemExit("C8 supply counts are missing")
if supply.get("zero_attrition_planning_union") != 1276 + ready + under8 + c7_retained:
    raise SystemExit("C8 supply union arithmetic mismatch")
print(
    json.dumps(
        {
            "status": "verified_engineering_audit_only",
            "incremental_deepcoder_ready_context_eligible": ready,
            "incremental_deepcoder_under8_preaugmentation_planning": under8,
            "c7_under8_after_deepcoder_dedup": c7,
            "supply_projection": supply,
            "report_sha256": actual,
        },
        sort_keys=True,
    )
)
PY
