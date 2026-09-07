#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PY="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-ready-final-piston/C19/checkpoint.json"
SELF="$ROOT/ai-work/executor/operator/WP9-c/wp9c-ready-final-piston/C19/01-run-ready-final-piston.sh"
RUNNER="$ROOT/ai-work/executor/operator/WP9-c/wp9c-ready-final-piston/C19/run_ready_final_piston.py"
C18="$ROOT/ai-work/executor/operator/WP9-c/wp9c-ready-final-piston/C18/checkpoint.json"
JOBS="/home/dzy/wp9c-ready-final-piston-prep-C18/piston_jobs.jsonl"
OUT="/home/dzy/wp9c-ready-final-piston-C19"
LOG="/home/dzy/wp9c-ready-final-piston-C19.log"
LOCK="/home/dzy/wp9c-ready-final-piston-C19.lock"
PISTON_CONFIG="$ROOT/configs/execution/piston-local.yaml"
TRANSPORT_POLICY="$ROOT/configs/execution/piston-transport-resilience.yaml"

[[ -x "$PY" ]] || { echo "workspace python is unavailable" >&2; exit 125; }

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "C19 operator lock is already held" >&2
  exit 73
fi

"$PY" - "$CHECKPOINT" "$SELF" "$RUNNER" "$C18" "$JOBS" "$PISTON_CONFIG" "$TRANSPORT_POLICY" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_, checkpoint_text, self_text, runner_text, c18_text, jobs_text, piston_text, transport_text = sys.argv
checkpoint_path = Path(checkpoint_text)
if not checkpoint_path.is_file():
    raise SystemExit("C19 checkpoint is missing")
checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
if (
    checkpoint.get("status") != "awaiting_operator"
    or checkpoint.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1"
    or checkpoint.get("operator_gate") != "wp9c-ready-final-formal-piston"
    or checkpoint.get("backfill_failed_candidates") is not False
    or checkpoint.get("minimum_pass_count") is not None
    or checkpoint.get("source_expansion_allowed") is not False
    or checkpoint.get("threshold_relaxation") is not False
):
    raise SystemExit("C19 checkpoint does not authorize the reduced-quota formal Piston run")
bindings = checkpoint.get("bindings")
if not isinstance(bindings, dict):
    raise SystemExit("C19 checkpoint bindings are invalid")
for key, path_text in (
    ("shell_runner_sha256", self_text),
    ("python_runner_sha256", runner_text),
    ("c18_checkpoint_sha256", c18_text),
    ("piston_jobs_sha256", jobs_text),
    ("piston_config_sha256", piston_text),
    ("piston_transport_policy_sha256", transport_text),
):
    actual = hashlib.sha256(Path(path_text).read_bytes()).hexdigest()
    if bindings.get(key) != actual:
        raise SystemExit(f"C19 binding mismatch: {key}")
c18 = json.loads(Path(c18_text).read_text(encoding="utf-8"))
if (
    c18.get("status") != "completed"
    or c18.get("protocol_amendment") != "wp9c-reduced-quota-current-viable-v1"
    or c18.get("counts", {}).get("piston_jobs") != 1167
    or c18.get("completed_output", {}).get("piston_jobs_sha256") != bindings.get("piston_jobs_sha256")
):
    raise SystemExit("C18 preparation prerequisite drift")
PY

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"

exec > >(tee -a "$LOG") 2>&1

echo "C19 formal Piston run starting/resuming"
"$PY" "$RUNNER" --jobs "$JOBS" --output "$OUT" --workers 8
