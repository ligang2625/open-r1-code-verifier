#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
SOURCE_CONFIG="$ROOT/configs/data/wp9c-apps-under8-augmentability-audit.yaml"
SOURCE_CONFIG_SHA256="0389ea01bd8e295db1870148feed2eae00bea20ef832e888c15439a2855cd547"
AUDIT_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_apps_under8_augmentable.py"
AUDIT_SCRIPT_SHA256="229ebc4dc916c0af1bc58e6c4b27b6132ca534ef85cc965c316221c1262fcd22"
REFERENCE_DATASET_DIR="/home/dzy/wp8-formal-sync/data/prepared"
REFRESH_CONFIG="$ROOT/configs/data/refresh.yaml"
BASELINE_NATIVE_REPORT="/home/dzy/wp9c-native-function-supply-audit-C4/report.json"
OUTPUT_DIR="/home/dzy/wp9c-apps-under8-augmentability-audit-C0"
LOG_PATH="/home/dzy/wp9c-apps-under8-augmentability-audit-C0.log"

cd "$ROOT"

if [[ ! -x "$PYTHON" || ! -f "$SOURCE_CONFIG" || ! -f "$AUDIT_SCRIPT" || ! -f "$REFRESH_CONFIG" ]]; then
  echo "missing project python/config/audit script" >&2
  exit 2
fi
if [[ ! -f "$REFERENCE_DATASET_DIR/canonical/problems.jsonl" ]]; then
  echo "missing frozen reference canonical dataset" >&2
  exit 2
fi
if [[ ! -f "$BASELINE_NATIVE_REPORT" || ! -f "${BASELINE_NATIVE_REPORT%report.json}report.sha256" ]]; then
  echo "missing verified C4 native baseline report/digest" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing under8 audit output/log" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_XET=1

"$PYTHON" - "$SOURCE_CONFIG" "$SOURCE_CONFIG_SHA256" "$AUDIT_SCRIPT" "$AUDIT_SCRIPT_SHA256" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_, config_text, expected_config, script_text, expected_script = sys.argv
for label, path_text, expected in (
    ("source_config", config_text, expected_config),
    ("audit_script", script_text, expected_script),
):
    path = Path(path_text)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"{label} SHA256 mismatch: expected {expected}, got {actual}")
    print(f"verified {label}: {actual}")
PY

# Static-only audit: no test generation, no source solution execution, no Piston.
# The expensive step is only frozen overlap classification against the existing
# SFT/validation/project-test/HumanEvalPlus exclusion references.
set -o pipefail
"$PYTHON" "$AUDIT_SCRIPT" \
  --source-config "$SOURCE_CONFIG" \
  --reference-dataset-dir "$REFERENCE_DATASET_DIR" \
  --refresh-config "$REFRESH_CONFIG" \
  --baseline-native-report "$BASELINE_NATIVE_REPORT" \
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
    raise SystemExit("under8 augmentability audit output is incomplete")
payload = report_path.read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = digest_path.read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit(f"under8 report digest mismatch: expected {expected}, got {actual}")
report = json.loads(payload)
if report.get("schema_version") != "wp9c-apps-under8-augmentability-audit-v1":
    raise SystemExit("under8 report schema version mismatch")
if report.get("formal_eligible") is not False:
    raise SystemExit("under8 audit must remain non-formal")
supply = report.get("wp9c_supply_context", {})
print(
    json.dumps(
        {
            "status": "verified_audit_only",
            "raw_augmentable_candidate_count": report.get("raw_augmentable_candidate_count"),
            "retained_external_new_augmentable_count": report.get("retained_external_new_augmentable_count"),
            "retained_existing_test_count_histogram": report.get("retained_existing_test_count_histogram"),
            "minimum_added_test_slots_to_reach_8": report.get("minimum_added_test_slots_to_reach_8"),
            "rejection_reason_counts": report.get("rejection_reason_counts"),
            "hypothetical_qualified_if_augmented": supply.get(
                "hypothetical_qualified_if_every_retained_candidate_is_augmented_and_later_passes_all_gates"
            ),
            "remaining_gap_zero_attrition": supply.get("remaining_gap_under_that_zero_attrition_hypothesis"),
            "report_sha256": actual,
        },
        sort_keys=True,
    )
)
PY
