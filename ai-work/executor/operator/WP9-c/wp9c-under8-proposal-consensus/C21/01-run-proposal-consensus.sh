#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PY="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-proposal-consensus/C21/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-proposal-consensus/C21/01-run-proposal-consensus.sh"
RUNNER="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-proposal-consensus/C21/run_proposal_consensus.py"
C20="$ROOT/ai-work/executor/operator/WP9-c/wp9c-under8-oracle-qualification/C20/checkpoint.json"
PREP_REPORT="/home/dzy/wp9c-under8-proposal-consensus-prep-C21-r2/report.json"
JOBS="/home/dzy/wp9c-under8-proposal-consensus-prep-C21-r2/consensus_jobs.jsonl"
OUT="/home/dzy/wp9c-under8-proposal-consensus-C21"
LOG="/home/dzy/wp9c-under8-proposal-consensus-C21.log"
LOCK="/home/dzy/wp9c-under8-proposal-consensus-C21.lock"
CONFIG="$ROOT/configs/data/wp9c-under8-proposal-consensus.yaml"
PISTON_CONFIG="$ROOT/configs/execution/piston-local.yaml"
TRANSPORT_POLICY="$ROOT/configs/execution/piston-transport-resilience.yaml"
HARNESS_SOURCE="$ROOT/src/code_verifier/execution/harness.py"
PISTON_SOURCE="$ROOT/src/code_verifier/execution/piston.py"

[[ -x "$PY" ]] || { echo "workspace python is unavailable" >&2; exit 125; }
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "C21 operator lock is already held" >&2
  exit 73
fi

"$PY" - "$CHECKPOINT" "$SELF" "$RUNNER" "$C20" "$PREP_REPORT" "$JOBS" "$CONFIG" "$PISTON_CONFIG" "$TRANSPORT_POLICY" "$HARNESS_SOURCE" "$PISTON_SOURCE" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

(
    _, checkpoint_text, self_text, runner_text, c20_text, prep_text, jobs_text, config_text,
    piston_text, transport_text, harness_text, piston_source_text,
) = sys.argv
checkpoint_path = Path(checkpoint_text)
if not checkpoint_path.is_file():
    raise SystemExit("C21 checkpoint is missing")
checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1"
    or checkpoint.get("operator_gate") != "wp9c-under8-deterministic-proposal-consensus"
    or checkpoint.get("backfill_failed_candidates") is not False
    or checkpoint.get("minimum_pass_count") is not None
    or checkpoint.get("source_expansion_allowed") is not False
    or checkpoint.get("threshold_relaxation") is not False
    or checkpoint.get("run_final_exact_b") is not False
    or checkpoint.get("run_final_formal_piston") is not False
):
    raise SystemExit("C21 checkpoint does not authorize proposal consensus")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C21 checkpoint bindings are invalid")
for key, path_text in (
    ("shell_runner_sha256", self_text),
    ("python_runner_sha256", runner_text),
    ("c20_checkpoint_sha256", c20_text),
    ("preparation_report_sha256", prep_text),
    ("consensus_jobs_sha256", jobs_text),
    ("config_sha256", config_text),
    ("piston_config_sha256", piston_text),
    ("piston_transport_policy_sha256", transport_text),
    ("harness_source_sha256", harness_text),
    ("piston_source_sha256", piston_source_text),
):
    actual = hashlib.sha256(Path(path_text).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C21 binding mismatch: {key}")
c20 = json.loads(Path(c20_text).read_text(encoding="utf-8"))
if (
    c20.get("status") != "completed_verified"
    or c20.get("verified_result", {}).get("under8_oracle_pair_survivors") != 615
    or c20.get("verified_result", {}).get("infrastructure_blocked") != 0
):
    raise SystemExit("C20 prerequisite is not verified/closed")
prep = json.loads(Path(prep_text).read_text(encoding="utf-8"))
if (
    prep.get("schema_version") != "wp9c-under8-proposal-consensus-preparation-v1"
    or prep.get("consensus_job_count") != 615
    or prep.get("artifact_sha256", {}).get("consensus_jobs") != bindings.get("consensus_jobs_sha256")
    or prep.get("execution_boundaries", {}).get("piston_run") is not False
    or prep.get("execution_boundaries", {}).get("proposal_execution_run") is not False
):
    raise SystemExit("C21 preparation evidence drift")
PY

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"
exec > >(tee -a "$LOG") 2>&1

echo "C21 deterministic two-oracle proposal consensus starting/resuming"
"$PY" "$RUNNER" --jobs "$JOBS" --output "$OUT" --workers 8
