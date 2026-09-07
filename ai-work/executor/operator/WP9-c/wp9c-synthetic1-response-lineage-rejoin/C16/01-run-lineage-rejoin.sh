#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PYTHON="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/C16/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/C16/01-run-lineage-rejoin.sh"
AUDIT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/C16/audit_response_lineage_rejoin.py"
CONFIG="$ROOT/configs/data/wp9c-synthetic1-response-lineage-rejoin.yaml"
C15="$ROOT/ai-work/executor/operator/WP9-c/wp9c-synthetic1-provenance-reopen/C15/checkpoint.json"
OUT="/home/dzy/wp9c-synthetic1-response-lineage-rejoin-C16"
LOG_PATH="/home/dzy/wp9c-synthetic1-response-lineage-rejoin-C16.log"

if [[ -e "$LOG_PATH" ]]; then
  echo "refusing to overwrite existing C16 log" >&2
  exit 2
fi
if [[ -e "$OUT" || -e "$OUT.tmp" ]]; then
  echo "refusing to overwrite existing C16 output or temporary output" >&2
  exit 2
fi

"$PYTHON" - "$CHECKPOINT" "$SELF" "$AUDIT" "$CONFIG" "$C15" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, self_text, audit_text, config_text, c15_text = sys.argv
checkpoint_path = Path(checkpoint_text)
checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-active-pool-2500-amendment-v1"
    or checkpoint.get("operator_gate") != "wp9c-synthetic1-response-lineage-rejoin"
    or checkpoint.get("candidate_supply_increment_allowed") is not False
    or checkpoint.get("source_solution_execution_frozen") is not True
    or checkpoint.get("test_generation_frozen") is not True
    or checkpoint.get("piston_frozen") is not True
    or checkpoint.get("grpo_frozen") is not True
    or checkpoint.get("gpu_frozen") is not True
):
    raise SystemExit("C16 checkpoint does not authorize the offline lineage/rejoin scan")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C16 checkpoint bindings are invalid")
for key, path_text in (
    ("runner_sha256", self_text),
    ("audit_script_sha256", audit_text),
    ("config_sha256", config_text),
    ("c15_checkpoint_sha256", c15_text),
):
    actual = hashlib.sha256(Path(path_text).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C16 binding mismatch: {key}")
c15 = json.loads(Path(c15_text).read_text(encoding="utf-8"))
verified = c15.get("verified_download")
if (
    c15.get("status") != "completed_download_verified"
    or c15.get("candidate_supply_increment_allowed") is not False
    or not isinstance(verified, dict)
    or verified.get("manifest_sha256") != "b910233e8adf693834f122de74db440bcbd64b562f5fe24cec800c2b62210858"
    or verified.get("response_lineage_scan_run") is not False
):
    raise SystemExit("C15 verified-download prerequisite drift")
PY

exec > >(tee "$LOG_PATH") 2>&1

"$PYTHON" "$AUDIT" --config "$CONFIG" --output "$OUT"
