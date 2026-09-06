#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-c"
GATE_ID="wp9c-grpo-active1354"
CHECKPOINT_ID="C34"
SCRIPT_REL="ai-work/executor/operator/WP9-c/wp9c-grpo-active1354/C34/run.sh"
AUDIT_REL="ai-work/executor/operator/WP9-c/wp9c-grpo-active1354/C34/verify_grpo_active1354.py"
PILOT_CHECK_REL="ai-work/executor/operator/WP9-c/wp9c-grpo-active1354/C34/check_pilot.py"
POOL_REL="wp9c/final-reduced-calibration-C29"
B_RUN_NAME="B-sft-formal-seed42"
EXPECTED_POOL_MANIFEST_SHA="5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b"
EXPECTED_PUBLIC_SHA="558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c"
EXPECTED_HIDDEN_SHA="9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec"
EXPECTED_ACTIVE_COUNT=1354

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh audit
  run.sh benchmark-k8 <public|hidden> <8|16|32|64> <tag>
  run.sh benchmark-k4 <public|hidden> 8 <tag>
  run.sh pilot <public|hidden> <workers> <benchmark-report>
  run.sh formal <public|hidden> <workers> <benchmark-report>

Required environment on the target:
  WP9C_HANDOFF_COMMIT=<exact git commit>
  WP9C_SCRIPT_SHA256=<sha256 of this tracked run.sh>

Optional resume environment for pilot/formal only:
  WP9C_RESUME_CHECKPOINT=<absolute checkpoint-N directory>
  WP9C_RESUME_RUN_GIT_COMMIT=<40-hex original run commit>
  WP9C_RESUME_CODE_MIGRATION=operational_reward_resilience_v1

Benchmark timing sources deliberately do not resume. Use a fresh tag after an interrupted timing attempt.
EOF
  exit 64
}

PHASE="${1:-}"
[[ -n "$PHASE" ]] || usage
MODE="${2:-}"
WORKERS="${3:-}"
EXTRA="${4:-}"
case "$PHASE" in
  audit) [[ $# -eq 1 ]] || usage ;;
  benchmark-k8|benchmark-k4) [[ $# -eq 4 ]] || usage ;;
  pilot|formal) [[ $# -eq 4 ]] || usage ;;
  *) usage ;;
esac
if [[ "$PHASE" != "audit" ]]; then
  [[ "$MODE" == "public" || "$MODE" == "hidden" ]] || usage
  [[ "$WORKERS" =~ ^[0-9]+$ ]] || usage
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
[[ -x "$PY" && -x "$CV" ]] || { echo "target checkout .venv is unavailable" >&2; exit 125; }

EXPECTED_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
EXPECTED_SCRIPT_SHA="${WP9C_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9C_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_SCRIPT_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9C_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
HEAD_COMMIT="$(git rev-parse HEAD)"
[[ "$HEAD_COMMIT" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from WP9C_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean" >&2; exit 125; }
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || { echo "tracked run.sh SHA256 differs from WP9C_SCRIPT_SHA256" >&2; exit 125; }

if [[ -n "${CODE_VERIFIER_VALIDATION_MACHINE:-}" ]]; then
  MACHINE_POINTER="$CODE_VERIFIER_VALIDATION_MACHINE"
else
  MACHINE_POINTER="$REPO_ROOT/.ai-bridge/validation-machine.json"
  if [[ ! -f "$MACHINE_POINTER" ]]; then
    COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"
    MACHINE_POINTER="$(dirname "$COMMON_DIR")/.ai-bridge/validation-machine.json"
  fi
fi
[[ -f "$MACHINE_POINTER" ]] || { echo "validation machine pointer not found" >&2; exit 125; }

MACHINE_FIELDS="$($PY - "$MACHINE_POINTER" <<'PY_MACHINE'
import json
import sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(value, dict):
    raise SystemExit("validation machine pointer must be a JSON object")
required = ("machine_status", "artifact_root", "hf_home", "formal_data_root", "piston_endpoint")
for key in required:
    if key not in value:
        raise SystemExit(f"validation machine pointer missing {key}")
if value["machine_status"] != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine is not READY_FOR_VALIDATION_PLANNER")
for key in ("artifact_root", "hf_home", "formal_data_root"):
    path = Path(value[key])
    if not path.is_absolute() or not str(path).startswith("/root/"):
        raise SystemExit(f"validation machine {key} must be an absolute /root path")
    if "/data" in str(path):
        raise SystemExit(f"validation machine {key} may not use retired /data")
if value["piston_endpoint"] != "http://127.0.0.1:2000":
    raise SystemExit("validation machine Piston endpoint drift")
print("\t".join(str(value[key]) for key in required[1:]))
PY_MACHINE
)"
TAB="$(printf '\t')"
IFS="$TAB" read -r ARTIFACT_ROOT TARGET_HF_HOME FORMAL_DATA_ROOT PISTON_ENDPOINT <<<"$MACHINE_FIELDS"
export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$TARGET_HF_HOME"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"
export TMPDIR="/root/tmp"
mkdir -p "$TMPDIR"

POOL_DIR="$FORMAL_DATA_ROOT/$POOL_REL"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
BASE_ROOT="$ARTIFACT_ROOT/wp9c/grpo-c29"
AUDIT_OUT="$BASE_ROOT/audit/c29-active1354-audit.json"
mkdir -p "$BASE_ROOT/audit"

case "$PHASE" in
  audit)
    RUN_NAME="audit"
    OUTPUT_ROOT="$BASE_ROOT/audit"
    ;;
  benchmark-k8)
    [[ "$WORKERS" == "8" || "$WORKERS" == "16" || "$WORKERS" == "32" || "$WORKERS" == "64" ]] || usage
    TAG="$EXTRA"
    [[ "$TAG" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "benchmark tag is not safe" >&2; exit 64; }
    RUN_NAME="wp9c-c29-${MODE}-benchmark20-seed42"
    SOURCE_ID="k8-${MODE}-w${WORKERS}-${TAG}"
    OUTPUT_ROOT="$BASE_ROOT/benchmark-sources/$SOURCE_ID"
    ;;
  benchmark-k4)
    [[ "$WORKERS" == "8" ]] || { echo "k4 diagnostic is frozen at workers=8" >&2; exit 64; }
    TAG="$EXTRA"
    [[ "$TAG" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "benchmark tag is not safe" >&2; exit 64; }
    RUN_NAME="wp9c-c29-${MODE}-k4-diagnostic20-seed42"
    SOURCE_ID="k4-${MODE}-w8-${TAG}"
    OUTPUT_ROOT="$BASE_ROOT/benchmark-sources/$SOURCE_ID"
    ;;
  pilot)
    BENCHMARK_REPORT="$EXTRA"
    [[ "$BENCHMARK_REPORT" = /* ]] || { echo "pilot benchmark report must be absolute" >&2; exit 64; }
    RUN_NAME="wp9c-c29-${MODE}-pilot100-seed42"
    OUTPUT_ROOT="$BASE_ROOT/pilot"
    ;;
  formal)
    BENCHMARK_REPORT="$EXTRA"
    [[ "$BENCHMARK_REPORT" = /* ]] || { echo "formal benchmark report must be absolute" >&2; exit 64; }
    if [[ "$MODE" == "public" ]]; then
      RUN_NAME="C-public-grpo-c29-active1354-seed42"
    else
      RUN_NAME="D-hidden-grpo-c29-active1354-seed42"
    fi
    OUTPUT_ROOT="$BASE_ROOT/formal"
    ;;
esac

OP_KEY="${SOURCE_ID:-$RUN_NAME}"
OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$GATE_ID/$CHECKPOINT_ID/$PHASE/$OP_KEY"
LOG_FILE="$OP_ROOT/terminal.log"
STATUS_FILE="$OP_ROOT/status"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOCK_FILE="$OP_ROOT/run.lock"
mkdir -p "$OP_ROOT" "$OUTPUT_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "operator lock is already held: $LOCK_FILE" >&2; exit 73; }
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '[%s] start phase=%s mode=%s run=%s commit=%s\n' "$START_TIME" "$PHASE" "${MODE:-n/a}" "$RUN_NAME" "$HEAD_COMMIT" >>"$LOG_FILE"

fail() {
  local rc="$1" note="$2"
  printf '%s\n' "$note" >&2
  printf 'failed\n' >"$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  "$PY" - "$EVIDENCE_FILE.tmp" "$PHASE" "$MODE" "$RUN_NAME" "$HEAD_COMMIT" "$SCRIPT_SHA" "$POOL_DIR" "$B_RUN" "$note" "$START_TIME" <<'PY_FAIL'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
out, phase, mode, run_name, commit, script_sha, pool, b_run, note, started = sys.argv[1:]
value = {
    "version": 1,
    "stage_id": "WP9-c",
    "gate_id": "wp9c-grpo-active1354",
    "checkpoint_id": "C34",
    "phase": phase,
    "reward_mode": mode or None,
    "run_name": run_name,
    "handoff_commit": commit,
    "operator_script_sha256": script_sha,
    "pool_dir": pool,
    "parent_b_run_dir": b_run,
    "gate_status": "failed",
    "note": note,
    "started_at": started,
    "ended_at": datetime.now(timezone.utc).isoformat(),
}
Path(out).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY_FAIL
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  exit "$rc"
}

[[ -d "$POOL_DIR" ]] || fail 125 "C29 pool directory is missing; rsync the frozen data first"
[[ -d "$B_RUN" ]] || fail 125 "formal B run directory is missing"
[[ "$(sha256sum "$POOL_DIR/calibration_manifest.json" | awk '{print $1}')" == "$EXPECTED_POOL_MANIFEST_SHA" ]] || fail 125 "C29 calibration manifest hash mismatch"
[[ "$(sha256sum "$POOL_DIR/training/public_grpo.jsonl" | awk '{print $1}')" == "$EXPECTED_PUBLIC_SHA" ]] || fail 125 "C29 Public dataset hash mismatch"
[[ "$(sha256sum "$POOL_DIR/training/hidden_grpo.jsonl" | awk '{print $1}')" == "$EXPECTED_HIDDEN_SHA" ]] || fail 125 "C29 Hidden dataset hash mismatch"

if ! "$PY" "$REPO_ROOT/$AUDIT_REL" --pool-dir "$POOL_DIR" --output "$AUDIT_OUT" >>"$LOG_FILE" 2>&1; then
  fail 125 "strict C29 active-1354 audit failed"
fi
if ! "$PY" - "$B_RUN" <<'PY_B' >>"$LOG_FILE" 2>&1
import sys
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
identity = load_completed_sft_checkpoint(Path(sys.argv[1]))
if identity.run_id != "B-sft-formal-seed42":
    raise SystemExit("parent B run_id drift")
if identity.model_id != "Qwen/Qwen2.5-Coder-1.5B-Instruct":
    raise SystemExit("parent B model_id drift")
if identity.model_revision != "2e1fd397ee46e1388853d2af2c993145b0f1098a":
    raise SystemExit("parent B revision drift")
if identity.seed != 42:
    raise SystemExit("parent B seed drift")
print(f"parent_b_checkpoint={identity.checkpoint_dir}")
PY_B
then
  fail 125 "formal B strict checkpoint load failed"
fi

if [[ "$PHASE" != "audit" ]]; then
  command -v nvidia-smi >/dev/null 2>&1 || fail 125 "nvidia-smi is unavailable"
  GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits | head -n 1)"
  IFS=',' read -r GPU_NAME GPU_TOTAL_MIB GPU_FREE_MIB <<<"$GPU_LINE"
  GPU_NAME="${GPU_NAME# }"; GPU_TOTAL_MIB="${GPU_TOTAL_MIB// /}"; GPU_FREE_MIB="${GPU_FREE_MIB// /}"
  [[ "$GPU_TOTAL_MIB" =~ ^[0-9]+$ && "$GPU_TOTAL_MIB" -ge 22528 ]] || fail 125 "target GPU total VRAM is below 22528 MiB"
  if [[ "${WP9C_CONCURRENT_CHILD:-0}" == "1" ]]; then
    CONCURRENT_CHILD_OK=0
    if [[ "$PHASE" == "benchmark-k8" && "$WORKERS" == "8" && "$EXTRA" == "concurrent" ]]; then
      CONCURRENT_CHILD_OK=1
    elif [[ "$PHASE" == "pilot" || "$PHASE" == "formal" ]]; then
      CONCURRENT_CHILD_OK=1
    fi
    [[ "$CONCURRENT_CHILD_OK" == "1" ]] || fail 125 "concurrent child mode is not authorized for this phase"
    [[ "$GPU_FREE_MIB" =~ ^[0-9]+$ && "$GPU_FREE_MIB" -ge 1024 ]] || fail 125 "concurrent child has less than 1024 MiB free VRAM before model load"
  else
    [[ "$GPU_FREE_MIB" =~ ^[0-9]+$ && "$GPU_FREE_MIB" -ge 20000 ]] || fail 125 "target GPU free VRAM is below 20000 MiB"
  fi
  if ! "$PY" - <<'PY_CUDA' >>"$LOG_FILE" 2>&1
import torch
if not torch.cuda.is_available():
    raise SystemExit("CUDA unavailable")
if not torch.cuda.is_bf16_supported():
    raise SystemExit("BF16 unavailable")
print(torch.cuda.get_device_name(0))
PY_CUDA
  then
    fail 125 "CUDA/BF16 preflight failed"
  fi
  if ! "$PY" - "$REPO_ROOT/configs/execution/piston-local.yaml" <<'PY_PISTON' >>"$LOG_FILE" 2>&1
import sys
from pathlib import Path
from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config
executor = PistonExecutor(load_piston_executor_config(Path(sys.argv[1])))
print(executor.validate_runtime())
PY_PISTON
  then
    fail 125 "loopback Piston exact-runtime preflight failed"
  fi
fi

case "$PHASE" in
  benchmark-k8|benchmark-k4) REQUIRED_BYTES=$((2 * 1024 * 1024 * 1024)); REQUIRED_INODES=50000 ;;
  pilot) REQUIRED_BYTES=$((4 * 1024 * 1024 * 1024)); REQUIRED_INODES=75000 ;;
  formal) REQUIRED_BYTES=$((8 * 1024 * 1024 * 1024)); REQUIRED_INODES=100000 ;;
  audit) REQUIRED_BYTES=$((1 * 1024 * 1024 * 1024)); REQUIRED_INODES=10000 ;;
esac
FREE_BYTES="$(df -PB1 "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
FREE_INODES="$(df -Pi "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
[[ "$FREE_BYTES" =~ ^[0-9]+$ && "$FREE_BYTES" -ge "$REQUIRED_BYTES" ]] || fail 125 "artifact filesystem free bytes below phase threshold"
[[ "$FREE_INODES" =~ ^[0-9]+$ && "$FREE_INODES" -ge "$REQUIRED_INODES" ]] || fail 125 "artifact filesystem free inodes below phase threshold"

if [[ "$PHASE" == "audit" ]]; then
  printf 'passed\n' >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  cp "$AUDIT_OUT" "$OP_ROOT/c29-active1354-audit.json"
  "$PY" - "$EVIDENCE_FILE.tmp" "$HEAD_COMMIT" "$SCRIPT_SHA" "$POOL_DIR" "$B_RUN" "$AUDIT_OUT" "$START_TIME" <<'PY_AUDIT_EVIDENCE'
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
out, commit, script_sha, pool, b_run, audit, started = sys.argv[1:]
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
value = {
    "version": 1, "stage_id": "WP9-c", "gate_id": "wp9c-grpo-active1354", "checkpoint_id": "C34",
    "phase": "audit", "gate_status": "passed", "handoff_commit": commit,
    "operator_script_sha256": script_sha, "pool_dir": pool, "parent_b_run_dir": b_run,
    "calibration_manifest_sha256": sha(Path(pool) / "calibration_manifest.json"),
    "public_training_sha256": sha(Path(pool) / "training/public_grpo.jsonl"),
    "hidden_training_sha256": sha(Path(pool) / "training/hidden_grpo.jsonl"),
    "audit_sha256": sha(Path(audit)), "active_problem_count": 1354,
    "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
}
Path(out).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY_AUDIT_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  printf 'C29 active-1354 audit PASS: %s\n' "$AUDIT_OUT"
  exit 0
fi

if [[ "$PHASE" == "benchmark-k8" ]]; then
  PUBLIC_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-benchmark-public.yaml"
  HIDDEN_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-benchmark-hidden.yaml"
  BENCHMARK_ROLE="k8_candidate"
elif [[ "$PHASE" == "benchmark-k4" ]]; then
  PUBLIC_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-benchmark-k4-public.yaml"
  HIDDEN_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-benchmark-k4-hidden.yaml"
  BENCHMARK_ROLE="k4_diagnostic"
elif [[ "$PHASE" == "pilot" ]]; then
  PUBLIC_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-pilot-public.yaml"
  HIDDEN_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-pilot-hidden.yaml"
else
  PUBLIC_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-public.yaml"
  HIDDEN_CONFIG="$REPO_ROOT/configs/grpo/wp9c-c29-active1354-hidden.yaml"
fi

if [[ "$PHASE" == "pilot" || "$PHASE" == "formal" ]]; then
  [[ -f "$BENCHMARK_REPORT" ]] || fail 125 "formal benchmark report is missing"
  if ! "$PY" - "$BENCHMARK_REPORT" "$WORKERS" <<'PY_BENCH' >>"$LOG_FILE" 2>&1
import sys
from pathlib import Path
from code_verifier.throughput import check_refresh_benchmark_report
summary = check_refresh_benchmark_report(Path(sys.argv[1]))
workers = int(sys.argv[2])
if summary.evidence_class != "formal":
    raise SystemExit("benchmark report is not formal")
if summary.selected_grpo_verification_workers != workers:
    raise SystemExit("requested workers differ from formal benchmark selection")
if summary.calibration_manifest_sha256 != "5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b":
    raise SystemExit("benchmark calibration manifest differs from C29")
print(f"paired_grpo_mode={summary.paired_grpo_mode}")
PY_BENCH
  then
    fail 125 "formal benchmark report strict check failed"
  fi
  BENCHMARK_SHA="$(sha256sum "$BENCHMARK_REPORT" | awk '{print $1}')"
  PAIRED_MODE="$($PY - "$BENCHMARK_REPORT" <<'PY_PAIRED_MODE'
import sys
from pathlib import Path
from code_verifier.throughput import check_refresh_benchmark_report
print(check_refresh_benchmark_report(Path(sys.argv[1])).paired_grpo_mode)
PY_PAIRED_MODE
)"
  if [[ "${WP9C_CONCURRENT_CHILD:-0}" == "1" ]]; then
    [[ "$PAIRED_MODE" == "concurrent" ]] || fail 125 "concurrent child requested but benchmark selected sequential"
  elif [[ "$PAIRED_MODE" == "concurrent" ]]; then
    fail 125 "benchmark selected concurrent; use the tracked run_concurrent_pair.sh wrapper"
  fi
fi

if [[ "$PHASE" == "formal" ]]; then
  echo "pilot_gate=waived reason=C29_k8_calibration_plus_reviewed_public_partial_pilot" >>"$LOG_FILE"
fi

RUN_DIR="$OUTPUT_ROOT/$RUN_NAME"
if [[ "$PHASE" == benchmark-* ]]; then
  [[ ! -e "$RUN_DIR" ]] || fail 125 "benchmark timing run already exists; use a fresh tag rather than resume/overwrite"
  [[ -z "${WP9C_RESUME_CHECKPOINT:-}" ]] || fail 125 "benchmark timing sources forbid resume"
else
  if [[ -e "$RUN_DIR" && -z "${WP9C_RESUME_CHECKPOINT:-}" ]]; then
    if "$PY" - "$RUN_DIR" <<'PY_DONE' >>"$LOG_FILE" 2>&1
import sys
from pathlib import Path
from code_verifier.training.grpo import load_completed_grpo_checkpoint
load_completed_grpo_checkpoint(Path(sys.argv[1]))
PY_DONE
    then
      printf '[%s] completed run already strict-loads; training command skipped\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
      SKIP_TRAINING=1
    else
      fail 125 "run directory exists but is not completed; set explicit WP9C_RESUME_CHECKPOINT"
    fi
  else
    SKIP_TRAINING=0
  fi
fi

RESUME_ARGS=()
if [[ -n "${WP9C_RESUME_CHECKPOINT:-}" ]]; then
  [[ "$PHASE" == "pilot" || "$PHASE" == "formal" ]] || fail 125 "resume is only supported for pilot/formal"
  [[ "$WP9C_RESUME_CHECKPOINT" = "$RUN_DIR"/checkpoints/checkpoint-* ]] || fail 125 "resume checkpoint must belong to the selected run"
  RESUME_ARGS+=(--resume-from-checkpoint "$WP9C_RESUME_CHECKPOINT")
  if [[ -n "${WP9C_RESUME_RUN_GIT_COMMIT:-}" ]]; then
    [[ "$WP9C_RESUME_RUN_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail 125 "WP9C_RESUME_RUN_GIT_COMMIT must be 40-hex"
    RESUME_ARGS+=(--resume-run-git-commit "$WP9C_RESUME_RUN_GIT_COMMIT")
  fi
  if [[ -n "${WP9C_RESUME_CODE_MIGRATION:-}" ]]; then
    [[ "$WP9C_RESUME_CODE_MIGRATION" == "operational_reward_resilience_v1" ]] || fail 125 "unsupported resume migration"
    RESUME_ARGS+=(--resume-code-migration "$WP9C_RESUME_CODE_MIGRATION")
  fi
  SKIP_TRAINING=0
fi

if [[ "$MODE" == "public" ]]; then
  PUBLIC_RUN_NAME="$RUN_NAME"
  HIDDEN_RUN_NAME="${RUN_NAME/public/hidden}"
else
  HIDDEN_RUN_NAME="$RUN_NAME"
  PUBLIC_RUN_NAME="${RUN_NAME/hidden/public}"
fi

COMMON_ARGS=(
  --public-config "$PUBLIC_CONFIG"
  --hidden-config "$HIDDEN_CONFIG"
  --dataset-dir "$POOL_DIR"
  --public-run-name "$PUBLIC_RUN_NAME"
  --hidden-run-name "$HIDDEN_RUN_NAME"
  --public-sft-run-dir "$B_RUN"
  --hidden-sft-run-dir "$B_RUN"
  --reward-mode "$MODE"
  --piston-transport-policy "$REPO_ROOT/configs/execution/piston-transport-resilience.yaml"
  --calibration-manifest "$POOL_DIR/calibration_manifest.json"
  --refresh-dataset-dir "$POOL_DIR"
  --reference-dataset-dir "$POOL_DIR"
  --verification-workers "$WORKERS"
  --seed 42
  --output-dir "$OUTPUT_ROOT"
)
# For the reduced C29 schema, refresh/reference paths are legacy CLI presence arguments;
# load_grpo_*_binding dispatches to check_reduced_calibrated_pool() and ignores those roots.
if [[ "$PHASE" == benchmark-* ]]; then
  COMMON_ARGS+=(--benchmark-role "$BENCHMARK_ROLE")
else
  COMMON_ARGS+=(--benchmark-report "$BENCHMARK_REPORT")
fi

if [[ "${SKIP_TRAINING:-0}" != "1" ]]; then
  printf '[%s] invoking train-grpo phase=%s mode=%s workers=%s run=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PHASE" "$MODE" "$WORKERS" "$RUN_NAME" >>"$LOG_FILE"
  if ! "$CV" train-grpo "${COMMON_ARGS[@]}" "${RESUME_ARGS[@]}" >>"$LOG_FILE" 2>&1; then
    fail 2 "train-grpo exited nonzero"
  fi
fi

if ! "$PY" - "$RUN_DIR" "$MODE" "$B_RUN_NAME" "$PHASE" <<'PY_POST' >>"$LOG_FILE" 2>&1
import json, math, sys
from pathlib import Path
from code_verifier.training.grpo import load_completed_grpo_checkpoint
run_dir = Path(sys.argv[1])
mode, parent_name, phase = sys.argv[2:5]
identity = load_completed_grpo_checkpoint(run_dir)
if identity.reward_mode != mode:
    raise SystemExit("completed GRPO reward mode drift")
if identity.parent_sft.run_id != parent_name:
    raise SystemExit("completed GRPO parent B drift")
config = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
if config.get("status") != "completed":
    raise SystemExit("completed GRPO run status drift")
for name in ("metrics.jsonl", "rewards.jsonl", "group_metrics.jsonl"):
    path = run_dir / name
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"completed GRPO artifact is empty: {name}")
resolved = (run_dir / "resolved_config.yaml").read_text(encoding="utf-8")
if "max_prompt_length: 2048" not in resolved:
    raise SystemExit("completed GRPO resolved prompt cap is not 2048")
print(f"completed_checkpoint={identity.checkpoint_dir}")
print(f"phase={phase}")
PY_POST
then
  fail 125 "completed GRPO postcheck failed"
fi

if [[ "$PHASE" == "pilot" ]]; then
  PILOT_SUMMARY="$BASE_ROOT/pilot-acceptance/$MODE.json"
  if ! "$PY" "$REPO_ROOT/$PILOT_CHECK_REL" --run-dir "$RUN_DIR" --reward-mode "$MODE" --output "$PILOT_SUMMARY" >>"$LOG_FILE" 2>&1; then
    fail 3 "pilot acceptance is warning/stop or otherwise invalid; formal GRPO remains blocked"
  fi
fi

RUN_JSON_SHA="$(sha256sum "$RUN_DIR/run.json" | awk '{print $1}')"
END_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'passed\n' >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
"$PY" - "$EVIDENCE_FILE.tmp" "$PHASE" "$MODE" "$RUN_NAME" "$HEAD_COMMIT" "$SCRIPT_SHA" "$POOL_DIR" "$B_RUN" "$RUN_DIR" "$RUN_JSON_SHA" "$WORKERS" "$START_TIME" "$END_TIME" <<'PY_EVIDENCE'
import hashlib, json, sys
from pathlib import Path
(out, phase, mode, run_name, commit, script_sha, pool, b_run, run_dir, run_json_sha, workers, started, ended) = sys.argv[1:]
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
value = {
    "version": 1,
    "stage_id": "WP9-c",
    "gate_id": "wp9c-grpo-active1354",
    "checkpoint_id": "C34",
    "phase": phase,
    "reward_mode": mode,
    "run_name": run_name,
    "handoff_commit": commit,
    "operator_script_sha256": script_sha,
    "pool_dir": pool,
    "parent_b_run_dir": b_run,
    "active_problem_count": 1354,
    "calibration_manifest_sha256": sha(Path(pool) / "calibration_manifest.json"),
    "public_training_sha256": sha(Path(pool) / "training/public_grpo.jsonl"),
    "hidden_training_sha256": sha(Path(pool) / "training/hidden_grpo.jsonl"),
    "verification_workers": int(workers),
    "run_dir": run_dir,
    "run_json_sha256": run_json_sha,
    "gate_status": "passed",
    "started_at": started,
    "ended_at": ended,
}
Path(out).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY_EVIDENCE
mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
printf 'PASS phase=%s mode=%s run=%s\n' "$PHASE" "$MODE" "$RUN_NAME"
