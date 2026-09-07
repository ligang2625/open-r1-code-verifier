#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
SOURCE_CONFIG="$ROOT/configs/data/wp9c-native-function-supply-audit-v2.yaml"
SOURCE_CONFIG_SHA256="892b3544bb46ca34f397cf3a602c67c15e7e61fffe4a8047a0669e281063ae04"
AUDIT_SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/audit_native_function_supply.py"
REFERENCE_DATASET_DIR="/home/dzy/wp8-formal-sync/data/prepared"
REFRESH_CONFIG="$ROOT/configs/data/refresh.yaml"
OUTPUT_DIR="/home/dzy/wp9c-native-function-supply-audit-C4"
LOG_PATH="/home/dzy/wp9c-native-function-supply-audit-C4.log"

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
  echo "refusing to overwrite existing C4 audit output/log" >&2
  exit 2
fi

for prior_log in \
  /home/dzy/wp9c-native-function-supply-audit-C0.log \
  /home/dzy/wp9c-native-function-supply-audit-C1.log \
  /home/dzy/wp9c-native-function-supply-audit-C2.log \
  /home/dzy/wp9c-native-function-supply-audit-C3.log; do
  if [[ -f "$prior_log" ]]; then
    echo "preserving prior audit log: $prior_log"
  fi
done

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_XET=1

"$PYTHON" - "$SOURCE_CONFIG" "$SOURCE_CONFIG_SHA256" <<'PY'
from __future__ import annotations

import hashlib
import sys
from dataclasses import asdict, fields
from pathlib import Path

from code_verifier.config import load_yaml_mapping
from code_verifier.data.deduplicate import canonical_json
from code_verifier.data.refresh_dedup import RefreshDedupDecision

_, config_text, expected_config_sha = sys.argv
config_path = Path(config_text)
actual_config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
if actual_config_sha != expected_config_sha:
    raise SystemExit(
        f"C4 source config SHA256 mismatch: expected {expected_config_sha}, got {actual_config_sha}"
    )
config = load_yaml_mapping(config_path)
if config.get("version") != "wp9c-native-function-supply-audit-v2":
    raise SystemExit("C4 source config version mismatch")
apps = config.get("sources", {}).get("apps_train", {})
if apps.get("adapter") != "apps_native_fn_name_audit_v2":
    raise SystemExit("C4 APPS adapter identity mismatch")
expected_fields = {
    "candidate_id",
    "retained",
    "rejection_reason",
    "overlap_class",
    "matched_record_id",
    "similarity",
}
actual_fields = {field.name for field in fields(RefreshDedupDecision)}
if actual_fields != expected_fields:
    raise SystemExit(
        f"RefreshDedupDecision schema drift: expected {sorted(expected_fields)}, got {sorted(actual_fields)}"
    )
probe = RefreshDedupDecision(
    candidate_id="probe",
    retained=False,
    rejection_reason="probe",
    overlap_class="sft",
    matched_record_id="probe-ref",
    similarity=1.0,
)
payload = asdict(probe)
payload["source_name"] = "probe-source"
payload["source_record_id"] = "probe-record"
canonical_json(payload)
print(f"C4 preflight passed: source_config_sha256={actual_config_sha}")
PY

# C4 is offline and audit-only. Both source artifacts are already cached and
# SHA-pinned; no source solution or testcase code is executed.
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
    raise SystemExit("C4 native supply audit output is incomplete")
payload = report_path.read_bytes()
actual = hashlib.sha256(payload).hexdigest()
expected = digest_path.read_text(encoding="ascii").strip()
if actual != expected:
    raise SystemExit(f"C4 audit report digest mismatch: expected {expected}, got {actual}")
report = json.loads(payload)
if report.get("schema_version") != "wp9c-native-function-supply-audit-v2":
    raise SystemExit("C4 report schema version mismatch")
if report.get("formal_eligible") is not False:
    raise SystemExit("C4 native supply audit must remain non-formal")
source_reports = report.get("source_reports", {})
supply = report.get("wp9c_supply_context", {})
print(
    json.dumps(
        {
            "status": "verified_audit_only_C4",
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
