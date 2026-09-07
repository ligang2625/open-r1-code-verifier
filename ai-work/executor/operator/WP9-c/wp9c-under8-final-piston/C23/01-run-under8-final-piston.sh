#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PY="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-final-piston/C23/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-final-piston/C23/01-run-under8-final-piston.sh"
RUNNER="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-final-piston/C23/run_final_piston.py"
C22="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-final-exact-b/C22/checkpoint.json"
PREP_REPORT="/home/dzy/wp9c-under8-final-piston-prep-C23/report.json"
JOBS="/home/dzy/wp9c-under8-final-piston-prep-C23/final_piston_jobs.jsonl"
OUT="/home/dzy/wp9c-under8-final-piston-C23"
LOG="/home/dzy/wp9c-under8-final-piston-C23.log"
LOCK="/home/dzy/wp9c-under8-final-piston-C23.lock"
PISTON_CONFIG="$ROOT/configs/execution/piston-local.yaml"
TRANSPORT_POLICY="$ROOT/configs/execution/piston-transport-resilience.yaml"

[[ -x "$PY" ]] || { echo "workspace python is unavailable" >&2; exit 125; }
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "C23 operator lock is already held" >&2
  exit 73
fi

"$PY" - "$CHECKPOINT" "$SELF" "$RUNNER" "$C22" "$PREP_REPORT" "$JOBS" "$PISTON_CONFIG" "$TRANSPORT_POLICY" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, self_text, runner_text, c22_text, prep_text, jobs_text, piston_text, transport_text = sys.argv
checkpoint_path = Path(checkpoint_text)
if not checkpoint_path.is_file():
    raise SystemExit("C23 checkpoint is missing")
checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1"
    or checkpoint.get("operator_gate") != "wp9c-under8-final-formal-piston"
    or checkpoint.get("backfill_failed_candidates") is not False
    or checkpoint.get("minimum_pass_count") is not None
    or checkpoint.get("correctness_retry_allowed") is not False
    or checkpoint.get("formal_pass_rule") != "both_frozen_qualified_oracles_pass_all_final_exact8_tests"
):
    raise SystemExit("C23 checkpoint does not authorize the frozen final Piston run")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C23 checkpoint bindings are invalid")
for key, path_text in (
    ("shell_runner_sha256", self_text),
    ("python_runner_sha256", runner_text),
    ("c22_checkpoint_sha256", c22_text),
    ("preparation_report_sha256", prep_text),
    ("final_piston_jobs_sha256", jobs_text),
    ("piston_config_sha256", piston_text),
    ("piston_transport_policy_sha256", transport_text),
):
    actual = hashlib.sha256(Path(path_text).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C23 binding mismatch: {key}")
c22 = json.loads(Path(c22_text).read_text(encoding="utf-8"))
if (
    c22.get("status") != "completed_verified"
    or c22.get("verified_result", {}).get("context_pass") != 572
    or c22.get("verified_result", {}).get("context_fail") != 0
):
    raise SystemExit("C22 prerequisite is not verified/closed")
prep = json.loads(Path(prep_text).read_text(encoding="utf-8"))
if (
    prep.get("schema_version") != "wp9c-under8-final-formal-piston-preparation-v1"
    or prep.get("job_count") != 572
    or prep.get("test_count_exact") != 8
    or prep.get("oracle_pair_size_exact") != 2
    or prep.get("formal_pass_rule") != "both_frozen_qualified_oracles_pass_all_final_exact8_tests"
    or prep.get("artifact_sha256", {}).get("final_piston_jobs") != bindings.get("final_piston_jobs_sha256")
    or prep.get("execution_boundaries", {}).get("piston_run") is not False
):
    raise SystemExit("C23 preparation evidence drift")
PY

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"
exec > >(tee -a "$LOG") 2>&1

echo "C23 under8 final formal Piston starting/resuming"
"$PY" "$RUNNER" --jobs "$JOBS" --output "$OUT" --workers 8
