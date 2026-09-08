#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-d"
GATE_ID="wp9d-b-refresh-eval400"
CHECKPOINT_ID="C0"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-b-refresh-eval400/C0/run.sh"
RESULT_CODE_COMMIT="7a92bb587fe34e6ae80a5d703e85a0659f05f43a"
P1_REPORT_SHA="5a6801024c70177e5f4f777bf524e8b263f93782f4e262ad03bbe886955d231d"
EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
EVAL_DATASET_SHA="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
EVAL_ORDER_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh preflight
  run.sh generate

Required target bindings:
  WP9D_HANDOFF_COMMIT=<exact 40-hex operator handoff commit>
  WP9D_P2_SCRIPT_SHA256=<sha256 of this tracked run.sh>

Optional only after a diagnosed failed generate attempt:
  WP9D_P2_RETRY_TAG=<safe suffix>

This gate refreshes frozen B generation on canonical eval400 with the P1-frozen
single-generator topology. It does not run Recipe A training and does not verify
or aggregate the generated bundle.
EOF
  exit 64
}

PHASE="${1:-}"
case "$PHASE" in
  preflight|generate) [[ $# -eq 1 ]] || usage ;;
  *) usage ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
[[ "$REPO_ROOT" == "/root/open-r1-code-verifier" ]] || { echo "target repo must be /root/open-r1-code-verifier" >&2; exit 125; }
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "target .venv Python is unavailable" >&2; exit 125; }
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"

EXPECTED_COMMIT="${WP9D_HANDOFF_COMMIT:-}"
EXPECTED_SCRIPT_SHA="${WP9D_P2_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9D_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_SCRIPT_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9D_P2_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from WP9D_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean; inspect without reset/clean" >&2; exit 125; }
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || { echo "tracked P2 run.sh SHA256 drift" >&2; exit 125; }
git merge-base --is-ancestor "$RESULT_CODE_COMMIT" HEAD || { echo "P2 handoff is not a descendant of frozen result-code commit" >&2; exit 125; }
[[ -z "$(git ls-files .ai-bridge)" ]] || { echo ".ai-bridge must have zero tracked paths" >&2; exit 125; }

if [[ -n "${CODE_VERIFIER_VALIDATION_MACHINE:-}" ]]; then
  MACHINE_POINTER="$CODE_VERIFIER_VALIDATION_MACHINE"
else
  MACHINE_POINTER="$REPO_ROOT/.ai-bridge/validation-machine.json"
fi
[[ -f "$MACHINE_POINTER" ]] || { echo "validation machine pointer not found" >&2; exit 125; }
readarray -t MACHINE_FIELDS < <("$PY" - "$MACHINE_POINTER" <<'PY_MACHINE'
import json, sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "machine_status": "READY_FOR_VALIDATION_PLANNER",
    "artifact_root": "/root/sj-tmp/open-r1-code-verifier-outputs",
    "hf_home": "/root/huggingface",
    "formal_data_root": "/root/open-r1-code-verifier-data-4090",
    "piston_endpoint": "http://127.0.0.1:2000",
}
for key, wanted in expected.items():
    if value.get(key) != wanted:
        raise SystemExit(f"validation machine {key} drift")
for key in ("artifact_root", "hf_home", "formal_data_root"):
    path = Path(value[key])
    if not path.is_absolute() or not str(path).startswith("/root/") or "/data" in str(path):
        raise SystemExit(f"validation machine {key} violates current /root policy")
for key in ("artifact_root", "hf_home", "formal_data_root"):
    print(value[key])
PY_MACHINE
)
ARTIFACT_ROOT="${MACHINE_FIELDS[0]}"
HF_HOME_TARGET="${MACHINE_FIELDS[1]}"
DATA_ROOT="${MACHINE_FIELDS[2]}"
export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$DATA_ROOT"
export HF_HOME="$HF_HOME_TARGET"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export TMPDIR="/root/tmp"
mkdir -p "$TMPDIR"

B_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
EVAL400_DIR="$DATA_ROOT/wp9c/heldout-eval400-C34"
P1_REPORT="$ARTIFACT_ROOT/wp9d/p1-runtime-validation/report/p1-runtime-report.json"
EVAL_CONFIG="$REPO_ROOT/configs/eval/base.yaml"
P2_ROOT="$ARTIFACT_ROOT/wp9d/b-refresh-eval400"
RUN_SUFFIX=""
if [[ -n "${WP9D_P2_RETRY_TAG:-}" ]]; then
  [[ "$WP9D_P2_RETRY_TAG" =~ ^[A-Za-z0-9._-]+$ && "$WP9D_P2_RETRY_TAG" != *..* ]] || { echo "WP9D_P2_RETRY_TAG is unsafe" >&2; exit 64; }
  RUN_SUFFIX="-$WP9D_P2_RETRY_TAG"
fi
RUN_NAME="wp9d-B-eval400-b4-p1-seed42${RUN_SUFFIX}"
RUN_DIR="$P2_ROOT/generation/$RUN_NAME"
OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$GATE_ID/$CHECKPOINT_ID/$PHASE${RUN_SUFFIX}"
STATUS_FILE="$OP_ROOT/status"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOG_FILE="$OP_ROOT/terminal.log"
LOCK_FILE="$OP_ROOT/run.lock"
mkdir -p "$OP_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "operator lock is already held: $LOCK_FILE" >&2; exit 73; }
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'running\n' >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
printf '[%s] start phase=%s commit=%s script_sha=%s\n' "$START_TIME" "$PHASE" "$EXPECTED_COMMIT" "$SCRIPT_SHA" >>"$LOG_FILE"

COMMAND_RC="null"
POSTCHECK_RC="null"
GPU_NAME=""
GPU_TOTAL_MIB=""
EVIDENCE_WRITTEN=0

write_evidence() {
  local gate_status="$1" note="$2"
  local ended run_json_sha records_sha
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  run_json_sha=""; records_sha=""
  [[ ! -f "$RUN_DIR/run.json" ]] || run_json_sha="$(sha256sum "$RUN_DIR/run.json" | awk '{print $1}')"
  [[ ! -f "$RUN_DIR/samples/generations.jsonl" ]] || records_sha="$(sha256sum "$RUN_DIR/samples/generations.jsonl" | awk '{print $1}')"
  "$PY" - "$EVIDENCE_FILE.tmp" "$EXPECTED_COMMIT" "$SCRIPT_SHA" "$gate_status" "$COMMAND_RC" "$POSTCHECK_RC" "$START_TIME" "$ended" "$note" "$GPU_NAME" "$GPU_TOTAL_MIB" "$RUN_DIR" "$run_json_sha" "$records_sha" <<'PY_EVIDENCE'
import json, sys
from pathlib import Path
(
    out, handoff, script_sha, gate_status, command_rc, postcheck_rc,
    started, ended, note, gpu_name, gpu_total_mib, run_dir, run_json_sha, records_sha,
) = sys.argv[1:]
def rc(value):
    return None if value == "null" else int(value)
payload = {
    "schema_version": "wp9d-b-refresh-operator-evidence-v1",
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP9-d",
    "gate_id": "wp9d-b-refresh-eval400",
    "checkpoint_id": "C0",
    "phase": Path(out).parent.name.split("-")[0],
    "handoff_commit": handoff,
    "result_code_commit": "7a92bb587fe34e6ae80a5d703e85a0659f05f43a",
    "operator_script": "ai-work/executor/operator/WP9-d/wp9d-b-refresh-eval400/C0/run.sh",
    "operator_script_sha256": script_sha,
    "target_repo": "/root/open-r1-code-verifier",
    "artifact_root": "/root/sj-tmp/open-r1-code-verifier-outputs",
    "formal_data_root": "/root/open-r1-code-verifier-data-4090",
    "hf_home": "/root/huggingface",
    "p1_runtime_report_sha256": "5a6801024c70177e5f4f777bf524e8b263f93782f4e262ad03bbe886955d231d",
    "runtime_freeze": {"batch_size": 4, "parallel_generators": 1, "dedicated_cuda_streams": False, "verification_workers": 64},
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "parent_sft": "B-sft-formal-seed42",
    "eval_dataset_sha256": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "eval_order_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "eval_config_sha256": "3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3",
    "gpu_name": gpu_name or None,
    "gpu_total_mib": float(gpu_total_mib) if gpu_total_mib else None,
    "run_dir": run_dir,
    "run_json_sha256": run_json_sha or None,
    "generation_records_file_sha256": records_sha or None,
    "started_at": started,
    "ended_at": ended,
    "command_rc": rc(command_rc),
    "postcheck_rc": rc(postcheck_rc),
    "gate_status": gate_status,
    "note": note,
}
Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  printf '%s\n' "$gate_status" >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  EVIDENCE_WRITTEN=1
}

on_exit() {
  local rc=$?
  trap - EXIT
  if [[ "$EVIDENCE_WRITTEN" != "1" ]]; then
    set +e
    write_evidence failed "unexpected operator exit"
    set -e
  fi
  exit "$rc"
}
trap on_exit EXIT

common_preflight() {
  [[ -f "$P1_REPORT" ]] || { echo "P1 report is missing" >&2; return 125; }
  [[ "$(sha256sum "$P1_REPORT" | awk '{print $1}')" == "$P1_REPORT_SHA" ]] || { echo "P1 report SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$EVAL_CONFIG" | awk '{print $1}')" == "$EVAL_CONFIG_SHA" ]] || { echo "eval config SHA drift" >&2; return 125; }
  [[ -d "$EVAL400_DIR" ]] || { echo "canonical eval400 source is missing" >&2; return 125; }
  [[ -d "$B_RUN" ]] || { echo "frozen B run is missing" >&2; return 125; }
  "$PY" - "$P1_REPORT" "$B_RUN" <<'PY_PREFLIGHT'
import json, sys
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
freeze = report.get("runtime_freeze_candidate", {})
if freeze.get("GRPO", {}).get("public_hidden_execution") != "sequential":
    raise SystemExit("P1 did not freeze sequential Public/Hidden GRPO")
if freeze.get("GRPO", {}).get("vllm_mode") != "colocate" or freeze.get("GRPO", {}).get("vllm_gpu_memory_utilization") != 0.4:
    raise SystemExit("P1 GRPO vLLM freeze drift")
if freeze.get("Eval") != {"batch_size": 4, "dedicated_cuda_streams": False, "parallel_generators": 1, "verification_workers": 64}:
    raise SystemExit("P1 eval runtime freeze drift")
identity = load_completed_sft_checkpoint(Path(sys.argv[2]))
if identity.run_id != "B-sft-formal-seed42" or identity.model_id != "Qwen/Qwen2.5-Coder-1.5B-Instruct":
    raise SystemExit("frozen B identity drift")
if identity.model_revision != "2e1fd397ee46e1388853d2af2c993145b0f1098a" or identity.seed != 42:
    raise SystemExit("frozen B revision/seed drift")
PY_PREFLIGHT
  local gpu_row free_mib
  gpu_row="$(nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$3); gsub(/ /,"",$4); if ($3+0 >= 22528 && $4+0 >= 20000) {print $2"|"$3"|"$4; exit}}')"
  [[ -n "$gpu_row" ]] || { echo "P2 requires RTX 4090 with >=22528 MiB total and >=20000 MiB free VRAM" >&2; return 125; }
  IFS='|' read -r GPU_NAME GPU_TOTAL_MIB free_mib <<<"$gpu_row"
  GPU_NAME="${GPU_NAME# }"
  local avail_kb avail_inodes
  avail_kb="$(df -Pk "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
  avail_inodes="$(df -Pi "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
  [[ "$avail_kb" =~ ^[0-9]+$ && "$avail_kb" -ge 10485760 ]] || { echo "artifact filesystem has <10 GiB free" >&2; return 125; }
  [[ "$avail_inodes" =~ ^[0-9]+$ && "$avail_inodes" -ge 10000 ]] || { echo "artifact filesystem has insufficient free inodes" >&2; return 125; }
}

set +e
common_preflight >>"$LOG_FILE" 2>&1
PREFLIGHT_RC=$?
set -e
if [[ "$PREFLIGHT_RC" -ne 0 ]]; then
  COMMAND_RC="$PREFLIGHT_RC"; POSTCHECK_RC="$PREFLIGHT_RC"
  write_evidence failed "preflight failed"
  exit "$PREFLIGHT_RC"
fi

if [[ "$PHASE" == "preflight" ]]; then
  COMMAND_RC=0; POSTCHECK_RC=0
  write_evidence passed "P2 preflight passed; no generation was started"
  echo "P2 preflight PASS"
  exit 0
fi

[[ ! -e "$RUN_DIR" ]] || { COMMAND_RC=125; POSTCHECK_RC=125; write_evidence failed "generation run already exists; preserve it and use a retry tag only after diagnosis"; exit 125; }
mkdir -p "$P2_ROOT"
set +e
"$PY" -m code_verifier.cli generate-eval \
  --config "$EVAL_CONFIG" \
  --dataset-dir "$EVAL400_DIR" \
  --sft-run-dir "$B_RUN" \
  --run-name "$RUN_NAME" \
  --batch-size 4 \
  --parallel-generators 1 \
  --seed 42 \
  --output-dir "$P2_ROOT" >>"$LOG_FILE" 2>&1
COMMAND_RC=$?
set -e
if [[ "$COMMAND_RC" -ne 0 ]]; then
  POSTCHECK_RC="null"
  write_evidence failed "generate-eval exited nonzero"
  exit "$COMMAND_RC"
fi

set +e
"$PY" - "$RUN_DIR" "$EXPECTED_COMMIT" <<'PY_POST' >>"$LOG_FILE" 2>&1
import json, sys
from pathlib import Path
run_dir = Path(sys.argv[1]); handoff = sys.argv[2]
meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
expected = {
    "status": "completed",
    "artifact_type": "evaluation_generation_bundle",
    "run_id": run_dir.name,
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "batch_size": 4,
    "parallel_generators": 1,
    "seed": 42,
    "completed_records": 400,
    "total_problems": 400,
    "project_commit": handoff,
}
for key, wanted in expected.items():
    if meta.get(key) != wanted:
        raise SystemExit(f"B eval400 generation drift: {key}={meta.get(key)!r}, expected={wanted!r}")
records = run_dir / "samples" / "generations.jsonl"
if not records.is_file() or records.stat().st_size == 0:
    raise SystemExit("B eval400 generation records missing/empty")
rows = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines() if line]
if len(rows) != 400 or len({row.get("problem_id") for row in rows}) != 400:
    raise SystemExit("B eval400 generation row count/IDs invalid")
util = meta.get("runtime_utilization", {})
if util.get("status") != "available" or not util.get("sample_count"):
    raise SystemExit("B eval400 runtime utilization unavailable")
PY_POST
POSTCHECK_RC=$?
set -e
if [[ "$POSTCHECK_RC" -ne 0 ]]; then
  write_evidence failed "B eval400 postcheck failed"
  exit 3
fi
write_evidence passed "B eval400 generation completed and strict postcheck passed"
echo "P2 B eval400 generation PASS: $RUN_DIR"
