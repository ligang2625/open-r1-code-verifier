#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/02-audit-sft-lineage.sh"
CONFIG="$ROOT/configs/data/wp9c-synthetic1-sft-lineage-audit.yaml"
SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/audit_synthetic1_sft_lineage.py"
RUNBOOK="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/RUNBOOK.md"
CODE_EXTRACTOR="$ROOT/src/code_verifier/parsing/code_extractor.py"
DEDUP="$ROOT/src/code_verifier/data/deduplicate.py"
C8_REPORT="/home/dzy/wp9c-deepcoder-function-supply-audit-C8/report.json"
C8_TARGETS="/home/dzy/wp9c-deepcoder-function-supply-audit-C8/deepcoder_under8_candidates.jsonl"
C10_REPORT="/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/report.json"
MANIFEST="/home/dzy/wp9c-synthetic1-sft-lineage-download-C11/manifest.json"
OUTPUT_DIR="/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11"
LOG_PATH="/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11.log"

cd "$ROOT"
for required in "$PYTHON" "$CHECKPOINT" "$SELF" "$CONFIG" "$SCRIPT" "$RUNBOOK" "$CODE_EXTRACTOR" "$DEDUP" "$C8_REPORT" "$C8_TARGETS" "$C10_REPORT" "$MANIFEST"; do
  if [[ ! -e "$required" ]]; then
    echo "missing C11 dependency: $required" >&2
    exit 2
  fi
done

"$PYTHON" - "$CHECKPOINT" "$CONFIG" "$SELF" "$SCRIPT" "$RUNBOOK" "$CODE_EXTRACTOR" "$DEDUP" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, config_text, self_text, script_text, runbook_text, extractor_text, dedup_text = sys.argv
checkpoint = json.loads(Path(checkpoint_text).read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("operator_gate") != "wp9c-synthetic1-sft-response-lineage-audit"
    or checkpoint.get("generation_frozen") is not True
    or checkpoint.get("piston_frozen") is not True
    or checkpoint.get("calibration_frozen") is not True
    or checkpoint.get("grpo_frozen") is not True
    or checkpoint.get("gpu_frozen") is not True
):
    raise SystemExit("C11 checkpoint does not authorize the audit")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C11 checkpoint bindings are invalid")
pairs = (
    ("audit_config_sha256", config_text),
    ("audit_runner_sha256", self_text),
    ("audit_python_sha256", script_text),
    ("runbook_sha256", runbook_text),
    ("code_extractor_sha256", extractor_text),
    ("deduplicate_module_sha256", dedup_text),
)
for key, value in pairs:
    actual = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C11 checkpoint binding mismatch: {key}")
PY

if [[ -e "$OUTPUT_DIR" || -e "$OUTPUT_DIR.tmp" || -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing C11 audit output/log" >&2
  exit 2
fi

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
"$PYTHON" "$SCRIPT" --config "$CONFIG" --output "$OUTPUT_DIR" 2>&1 | tee "$LOG_PATH"

"$PYTHON" - "$OUTPUT_DIR" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, output_text = sys.argv
output = Path(output_text)
report_path = output / "report.json"
report_sha_path = output / "report.sha256"
report = json.loads(report_path.read_text(encoding="utf-8"))
actual_report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
if report_sha_path.read_text(encoding="ascii").strip() != actual_report_sha:
    raise SystemExit("C11 report digest mismatch")
if (
    report.get("schema_version") != "wp9c-synthetic1-sft-lineage-audit-v1"
    or report.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or report.get("formal_eligible") is not False
    or report.get("evidence_class") != "engineering_provenance_audit_only"
):
    raise SystemExit("C11 report identity drift")
artifacts = report.get("artifact_sha256")
if not isinstance(artifacts, dict):
    raise SystemExit("C11 artifact digest map missing")
for name in ("target_lineage", "response_hits", "prompt_diagnostics"):
    path = output / f"{name}.jsonl"
    if hashlib.sha256(path.read_bytes()).hexdigest() != artifacts.get(name):
        raise SystemExit(f"C11 artifact digest mismatch: {name}")
lineage = report.get("lineage_summary")
if not isinstance(lineage, dict) or lineage.get("target_count") != 541:
    raise SystemExit("C11 target count mismatch")
partition = sum(int(lineage.get(key, 0)) for key in ("unique_problem_id_rows", "ambiguous_problem_id_rows", "unmatched_rows"))
if partition != 541:
    raise SystemExit("C11 lineage partition mismatch")
score = report.get("score_isolation")
if not isinstance(score, dict) or score.get("score_field_excluded_from_scan_columns") is not True or score.get("score_value_used_for_selection") is not False or score.get("score_value_used_for_supply") is not False:
    raise SystemExit("C11 score isolation mismatch")
supply = report.get("supply_projection")
if not isinstance(supply, dict) or supply.get("incremental_supply_by_protocol") != 0 or supply.get("zero_attrition_planning_union") != 2505:
    raise SystemExit("C11 frozen supply projection drift")
print(actual_report_sha)
PY
