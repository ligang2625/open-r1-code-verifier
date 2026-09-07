#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-openr1-raw-python-provenance-audit/C10/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-openr1-raw-python-provenance-audit/C10/02-audit-raw-python.sh"
CONFIG="$ROOT/configs/data/wp9c-openr1-raw-python-provenance-audit.yaml"
CALIBRATION_CONFIG="$ROOT/configs/grpo/refresh-calibration.yaml"
SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-openr1-raw-python-provenance-audit/C10/audit_raw_python.py"
RUNBOOK="$ROOT/ai-work/executor/operator/WP9-c/wp9c-openr1-raw-python-provenance-audit/C10/RUNBOOK.md"
C6_FULL="$ROOT/ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/audit_full_taco_supply.py"
C6_CORRECTION="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/audit_context_correction.py"
C8_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-deepcoder-function-supply-audit/C8/audit_deepcoder_function_supply.py"
C9_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-openr1-decontaminated-full-audit/C9/audit_full_source.py"
SAMPLE_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_openr1_decontaminated_sample.py"
MANIFEST="/home/dzy/wp9c-openr1-raw-python-download-C10/manifest.json"
OUTPUT_DIR="/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10"
LOG_PATH="/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10.log"

cd "$ROOT"
for required in "$PYTHON" "$CHECKPOINT" "$SELF" "$CONFIG" "$CALIBRATION_CONFIG" "$SCRIPT" "$RUNBOOK" "$C6_FULL" "$C6_CORRECTION" "$C8_SCRIPT" "$C9_SCRIPT" "$SAMPLE_SCRIPT" "$MANIFEST"; do
  if [[ ! -e "$required" ]]; then
    echo "missing C10 dependency: $required" >&2
    exit 2
  fi
done

"$PYTHON" - "$CHECKPOINT" "$CALIBRATION_CONFIG" "$CONFIG" "$SELF" "$SCRIPT" "$RUNBOOK" "$C6_FULL" "$C6_CORRECTION" "$C8_SCRIPT" "$C9_SCRIPT" "$SAMPLE_SCRIPT" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

(
    _, checkpoint_text, calibration_text, config_text, self_text, script_text, runbook_text,
    c6_full_text, c6_correction_text, c8_text, c9_text, sample_text,
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
    raise SystemExit("C10 checkpoint state/protocol is not authorized")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C10 checkpoint bindings are invalid")
for key, value in (
    ("refresh_calibration_config_sha256", calibration_text),
    ("audit_config_sha256", config_text),
    ("audit_runner_sha256", self_text),
    ("audit_python_sha256", script_text),
    ("runbook_sha256", runbook_text),
    ("c6_full_taco_script_sha256", c6_full_text),
    ("c6_context_correction_script_sha256", c6_correction_text),
    ("c8_script_sha256", c8_text),
    ("c9_script_sha256", c9_text),
    ("historical_sample_script_sha256", sample_text),
):
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C10 checkpoint binding mismatch: {key}")
PY

if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing C10 audit output/log" >&2
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
    raise SystemExit("C10 report digest mismatch")
report = json.loads(payload)
if (
    report.get("schema_version") != "wp9c-openr1-raw-python-provenance-audit-v1"
    or report.get("formal_eligible") is not False
    or report.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
):
    raise SystemExit("C10 report identity/formal status mismatch")
artifacts = report.get("artifact_sha256")
files = {
    "deepcoder_provenance_recovery": "deepcoder_provenance_recovery.jsonl",
    "raw_candidates": "raw_candidates.jsonl",
    "dedup_decisions": "dedup_decisions.jsonl",
    "ready_context": "ready_context.jsonl",
    "under8_context": "under8_context.jsonl",
    "incremental_ready_candidates": "incremental_ready_candidates.jsonl",
    "incremental_under8_candidates": "incremental_under8_candidates.jsonl",
}
if not isinstance(artifacts, dict):
    raise SystemExit("C10 artifact digest map missing")
for key, filename in files.items():
    digest = hashlib.sha256((output / filename).read_bytes()).hexdigest()
    if artifacts.get(key) != digest:
        raise SystemExit(f"C10 artifact digest mismatch: {key}")
under8 = report.get("new_under8_preaugmentation_context")
supply = report.get("supply_projection")
provenance = report.get("deepcoder_provenance_recovery")
if (
    not isinstance(under8, dict)
    or under8.get("formal_context_eligible_count") is not None
    or under8.get("final_augmented_context_recheck_required") is not True
    or not isinstance(supply, dict)
    or not isinstance(provenance, dict)
    or provenance.get("target_deepcoder_primeintellect_rows") != 541
):
    raise SystemExit("C10 planning/provenance semantics mismatch")
matched = provenance.get("uniquely_matched_rows")
ambiguous = provenance.get("ambiguous_rows")
unmatched = provenance.get("unmatched_rows")
if not all(isinstance(value, int) for value in (matched, ambiguous, unmatched)) or matched + ambiguous + unmatched != 541:
    raise SystemExit("C10 provenance partition mismatch")
print(
    json.dumps(
        {
            "status": "verified_engineering_audit_only",
            "report_sha256": actual,
            "provenance": provenance,
            "supply_projection": supply,
        },
        sort_keys=True,
    )
)
PY
