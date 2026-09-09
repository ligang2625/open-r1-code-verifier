#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-d"
GATE_ID="wp9d-recipe-a-eval400"
CHECKPOINT_ID="C0"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-recipe-a-eval400/C0/run.sh"
HELPER_REL="ai-work/executor/operator/WP9-d/wp9d-recipe-a-eval400/C0/generate_checkpoint_eval.py"
HELPER_SHA="0c8dcedd3415ed615f53a6b34c1705e1b9eec8f820bffcc5ad5467c01e6d7337"
TRAINING_COMMIT="7b5e097b448b6c42fb9faf1f27711a65e00d2075"
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
  WP9D_RECIPE_A_EVAL_SCRIPT_SHA256=<sha256 of this tracked run.sh>

Optional only after a diagnosed failed generation attempt:
  WP9D_RECIPE_A_EVAL_RETRY_TAG=<safe suffix>

The generate phase creates eight generation-only bundles: Public and Hidden at
steps 300/600/900/1200. It runs two independent checkpoint jobs concurrently
per wave while keeping each checkpoint at batch_size=4/parallel_generators=1.
It never contacts Piston and never verifies/aggregates.
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
EXPECTED_SCRIPT_SHA="${WP9D_RECIPE_A_EVAL_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9D_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_SCRIPT_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9D_RECIPE_A_EVAL_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from WP9D_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean; inspect without reset/clean" >&2; exit 125; }
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
ACTUAL_HELPER_SHA="$(sha256sum "$REPO_ROOT/$HELPER_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || { echo "tracked eval run.sh SHA256 drift" >&2; exit 125; }
[[ "$ACTUAL_HELPER_SHA" == "$HELPER_SHA" ]] || { echo "tracked checkpoint generation helper SHA256 drift" >&2; exit 125; }
git merge-base --is-ancestor "$TRAINING_COMMIT" HEAD || { echo "eval handoff must descend from formal Recipe A training commit" >&2; exit 125; }
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

EVAL400_DIR="$DATA_ROOT/wp9c/heldout-eval400-C34"
P1_REPORT="$ARTIFACT_ROOT/wp9d/p1-runtime-validation/report/p1-runtime-report.json"
EVAL_CONFIG="$REPO_ROOT/configs/eval/base.yaml"
RECIPE_ROOT="$ARTIFACT_ROOT/wp9d/recipe-a"
PUBLIC_RUN="$RECIPE_ROOT/wp9d-A-public-vllm-qkvo-active1354-seed42"
HIDDEN_RUN="$RECIPE_ROOT/wp9d-A-hidden-vllm-qkvo-active1354-seed42"
OUT_ROOT="$ARTIFACT_ROOT/wp9d/recipe-a-eval400"
RUN_SUFFIX=""
if [[ -n "${WP9D_RECIPE_A_EVAL_RETRY_TAG:-}" ]]; then
  [[ "$WP9D_RECIPE_A_EVAL_RETRY_TAG" =~ ^[A-Za-z0-9._-]+$ && "$WP9D_RECIPE_A_EVAL_RETRY_TAG" != *..* ]] || { echo "WP9D_RECIPE_A_EVAL_RETRY_TAG is unsafe" >&2; exit 64; }
  RUN_SUFFIX="-$WP9D_RECIPE_A_EVAL_RETRY_TAG"
fi
OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$GATE_ID/$CHECKPOINT_ID/$PHASE${RUN_SUFFIX}"
STATUS_FILE="$OP_ROOT/status"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOG_FILE="$OP_ROOT/terminal.log"
LOCK_FILE="$OP_ROOT/run.lock"
JOB_DIR="$OP_ROOT/jobs"
mkdir -p "$OP_ROOT" "$JOB_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "operator lock is already held: $LOCK_FILE" >&2; exit 73; }
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'running\n' >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
printf '[%s] start phase=%s commit=%s script_sha=%s helper_sha=%s\n' "$START_TIME" "$PHASE" "$EXPECTED_COMMIT" "$SCRIPT_SHA" "$ACTUAL_HELPER_SHA" >>"$LOG_FILE"

COMMAND_RC="null"
POSTCHECK_RC="null"
EVIDENCE_WRITTEN=0

write_evidence() {
  local gate_status="$1" note="$2"
  local ended
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$EXPECTED_COMMIT" "$SCRIPT_SHA" "$ACTUAL_HELPER_SHA" "$gate_status" "$COMMAND_RC" "$POSTCHECK_RC" "$START_TIME" "$ended" "$note" "$OUT_ROOT" "$RUN_SUFFIX" "$JOB_DIR" <<'PY_EVIDENCE'
import hashlib, json, sys
from pathlib import Path
(out, handoff, script_sha, helper_sha, gate_status, command_rc, postcheck_rc,
 started, ended, note, out_root, suffix, job_dir) = sys.argv[1:]
steps = (300, 600, 900, 1200)
runs = []
for arm in ("public", "hidden"):
    for step in steps:
        name = f"wp9d-A-{arm}-step{step}-eval400-b4-p1-seed42{suffix}"
        run_dir = Path(out_root) / "generation" / name
        run_json = run_dir / "run.json"
        records = run_dir / "samples" / "generations.jsonl"
        job_log = Path(job_dir) / f"{arm}-step{step}.log"
        job_rc = Path(job_dir) / f"{arm}-step{step}.rc"
        def sha(path):
            if not path.is_file():
                return None
            h = hashlib.sha256()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()
        runs.append({
            "arm": arm,
            "checkpoint_step": step,
            "run_name": name,
            "run_dir": str(run_dir),
            "run_json_sha256": sha(run_json),
            "generation_records_file_sha256": sha(records),
            "job_log_path": str(job_log),
            "job_log_sha256": sha(job_log),
            "job_rc": int(job_rc.read_text(encoding="utf-8").strip()) if job_rc.is_file() else None,
        })
def rc(value):
    return None if value == "null" else int(value)
payload = {
    "schema_version": "wp9d-recipe-a-eval400-operator-evidence-v2",
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP9-d",
    "gate_id": "wp9d-recipe-a-eval400",
    "checkpoint_id": "C0",
    "phase": Path(out).parent.name.split("-")[0],
    "handoff_commit": handoff,
    "formal_training_commit": "7b5e097b448b6c42fb9faf1f27711a65e00d2075",
    "operator_script_sha256": script_sha,
    "generation_helper_sha256": helper_sha,
    "artifact_root": "/root/sj-tmp/open-r1-code-verifier-outputs",
    "formal_data_root": "/root/open-r1-code-verifier-data-4090",
    "hf_home": "/root/huggingface",
    "p1_runtime_report_sha256": "5a6801024c70177e5f4f777bf524e8b263f93782f4e262ad03bbe886955d231d",
    "runtime_freeze": {"batch_size": 4, "parallel_generators": 1, "dedicated_cuda_streams": False},
    "checkpoint_parallelism": 2,
    "checkpoint_waves": [
        ["public:300", "public:600"],
        ["public:900", "public:1200"],
        ["hidden:300", "hidden:600"],
        ["hidden:900", "hidden:1200"],
    ],
    "checkpoint_parallelism_basis": "user-directed scheduling amendment; per-checkpoint P1 eval topology remains frozen",
    "eval_dataset_sha256": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "eval_order_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "eval_config_sha256": "3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3",
    "checkpoint_steps": [300, 600, 900, 1200],
    "arms": ["public", "hidden"],
    "generation_only": True,
    "verification_scoring_aggregation": "deferred_to_1660ti_by_user_direction",
    "runs": runs,
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

ACTIVE_PIDS=()
terminate_active_children() {
  local pid
  for pid in "${ACTIVE_PIDS[@]}"; do
    kill -0 "$pid" 2>/dev/null && kill -TERM "$pid" 2>/dev/null || true
  done
  for pid in "${ACTIVE_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  ACTIVE_PIDS=()
}

on_signal() {
  local signal_name="$1" rc=130
  [[ "$signal_name" != "TERM" ]] || rc=143
  trap - INT TERM
  terminate_active_children
  COMMAND_RC="$rc"; POSTCHECK_RC="null"
  write_evidence failed "operator interrupted by $signal_name; active checkpoint jobs terminated"
  exit "$rc"
}
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM

common_preflight() {
  [[ -f "$P1_REPORT" ]] || { echo "P1 report is missing" >&2; return 125; }
  [[ "$(sha256sum "$P1_REPORT" | awk '{print $1}')" == "$P1_REPORT_SHA" ]] || { echo "P1 report SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$EVAL_CONFIG" | awk '{print $1}')" == "$EVAL_CONFIG_SHA" ]] || { echo "eval config SHA drift" >&2; return 125; }
  [[ -d "$EVAL400_DIR" ]] || { echo "canonical eval400 source is missing" >&2; return 125; }
  [[ -d "$PUBLIC_RUN" && -d "$HIDDEN_RUN" ]] || { echo "completed Recipe A run directory missing" >&2; return 125; }
  "$PY" - "$P1_REPORT" "$PUBLIC_RUN" "$HIDDEN_RUN" "$REPO_ROOT/$HELPER_REL" <<'PY_PREFLIGHT'
import importlib.util, json, sys
from pathlib import Path
from code_verifier.training import load_completed_grpo_checkpoint
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
freeze = report.get("runtime_freeze_candidate", {})
if freeze.get("Eval") != {"batch_size": 4, "dedicated_cuda_streams": False, "parallel_generators": 1, "verification_workers": 64}:
    raise SystemExit("P1 eval runtime freeze drift")
spec = importlib.util.spec_from_file_location("wp9d_recipe_a_eval_helper", sys.argv[4])
if spec is None or spec.loader is None:
    raise SystemExit("cannot load checkpoint generation helper")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
for run_path, arm in ((Path(sys.argv[2]), "public"), (Path(sys.argv[3]), "hidden")):
    identity = load_completed_grpo_checkpoint(run_path)
    if identity.reward_mode != arm or identity.seed != 42:
        raise SystemExit(f"Recipe A {arm} run identity drift")
    meta = json.loads((run_path / "run.json").read_text(encoding="utf-8"))
    if meta.get("status") != "completed" or meta.get("global_step") != 1200:
        raise SystemExit(f"Recipe A {arm} run not completed at step 1200")
    if meta.get("git_commit") != "7b5e097b448b6c42fb9faf1f27711a65e00d2075":
        raise SystemExit(f"Recipe A {arm} training commit drift")
    for step in (300, 600, 900, 1200):
        selected = module.select_checkpoint(run_path, step)
        if selected.reward_mode != arm:
            raise SystemExit(f"Recipe A {arm} checkpoint reward-mode drift")
PY_PREFLIGHT
  local gpu_row free_mib
  gpu_row="$(nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$3); gsub(/ /,"",$4); if ($3+0 >= 22528 && $4+0 >= 20000) {print $2"|"$3"|"$4; exit}}')"
  [[ -n "$gpu_row" ]] || { echo "Recipe A eval requires RTX 4090 with >=22528 MiB total and >=20000 MiB free VRAM" >&2; return 125; }
  IFS='|' read -r _ _ free_mib <<<"$gpu_row"
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
  write_evidence passed "Recipe A eval400 preflight passed; no generation was started"
  echo "Recipe A eval400 preflight PASS"
  exit 0
fi

for arm in public hidden; do
  if [[ "$arm" == "public" ]]; then SOURCE_RUN="$PUBLIC_RUN"; else SOURCE_RUN="$HIDDEN_RUN"; fi
  for step in 300 600 900 1200; do
    RUN_NAME="wp9d-A-${arm}-step${step}-eval400-b4-p1-seed42${RUN_SUFFIX}"
    RUN_DIR="$OUT_ROOT/generation/$RUN_NAME"
    [[ ! -e "$RUN_DIR" ]] || { COMMAND_RC=125; POSTCHECK_RC=125; write_evidence failed "generation run already exists; preserve it and use retry tag only after diagnosis"; exit 125; }
  done
done
mkdir -p "$OUT_ROOT"

COMMAND_RC=0
for WAVE in "public 300 600" "public 900 1200" "hidden 300 600" "hidden 900 1200"; do
  read -r ARM STEP_A STEP_B <<<"$WAVE"
  if [[ "$ARM" == "public" ]]; then SOURCE_RUN="$PUBLIC_RUN"; else SOURCE_RUN="$HIDDEN_RUN"; fi
  RUN_NAME_A="wp9d-A-${ARM}-step${STEP_A}-eval400-b4-p1-seed42${RUN_SUFFIX}"
  RUN_NAME_B="wp9d-A-${ARM}-step${STEP_B}-eval400-b4-p1-seed42${RUN_SUFFIX}"
  JOB_LOG_A="$JOB_DIR/${ARM}-step${STEP_A}.log"
  JOB_LOG_B="$JOB_DIR/${ARM}-step${STEP_B}.log"
  JOB_RC_A="$JOB_DIR/${ARM}-step${STEP_A}.rc"
  JOB_RC_B="$JOB_DIR/${ARM}-step${STEP_B}.rc"
  printf '[%s] launch wave arm=%s steps=%s,%s checkpoint_parallelism=2\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ARM" "$STEP_A" "$STEP_B" >>"$LOG_FILE"

  "$PY" "$REPO_ROOT/$HELPER_REL" \
    --config "$EVAL_CONFIG" \
    --dataset-dir "$EVAL400_DIR" \
    --grpo-run-dir "$SOURCE_RUN" \
    --checkpoint-step "$STEP_A" \
    --run-name "$RUN_NAME_A" \
    --batch-size 4 \
    --seed 42 \
    --output-dir "$OUT_ROOT" >"$JOB_LOG_A" 2>&1 &
  PID_A=$!

  "$PY" "$REPO_ROOT/$HELPER_REL" \
    --config "$EVAL_CONFIG" \
    --dataset-dir "$EVAL400_DIR" \
    --grpo-run-dir "$SOURCE_RUN" \
    --checkpoint-step "$STEP_B" \
    --run-name "$RUN_NAME_B" \
    --batch-size 4 \
    --seed 42 \
    --output-dir "$OUT_ROOT" >"$JOB_LOG_B" 2>&1 &
  PID_B=$!
  ACTIVE_PIDS=("$PID_A" "$PID_B")

  set +e
  wait "$PID_A"; RC_A=$?
  wait "$PID_B"; RC_B=$?
  set -e
  ACTIVE_PIDS=()
  printf '%s\n' "$RC_A" >"$JOB_RC_A.tmp"; mv "$JOB_RC_A.tmp" "$JOB_RC_A"
  printf '%s\n' "$RC_B" >"$JOB_RC_B.tmp"; mv "$JOB_RC_B.tmp" "$JOB_RC_B"
  printf '[%s] complete wave arm=%s step%s_rc=%s step%s_rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ARM" "$STEP_A" "$RC_A" "$STEP_B" "$RC_B" >>"$LOG_FILE"

  if [[ "$RC_A" -ne 0 || "$RC_B" -ne 0 ]]; then
    if [[ "$RC_A" -ne 0 ]]; then COMMAND_RC="$RC_A"; else COMMAND_RC="$RC_B"; fi
    POSTCHECK_RC="null"
    write_evidence failed "generation wave failed for arm=$ARM steps=$STEP_A,$STEP_B; both jobs were awaited and preserved"
    exit "$COMMAND_RC"
  fi
done

set +e
"$PY" - "$OUT_ROOT" "$EXPECTED_COMMIT" "$RUN_SUFFIX" "$PUBLIC_RUN" "$HIDDEN_RUN" "$JOB_DIR" <<'PY_POST' >>"$LOG_FILE" 2>&1
import json, sys
from pathlib import Path
out_root = Path(sys.argv[1]); handoff = sys.argv[2]; suffix = sys.argv[3]
sources = {"public": Path(sys.argv[4]), "hidden": Path(sys.argv[5])}
job_dir = Path(sys.argv[6])
for arm in ("public", "hidden"):
    for step in (300, 600, 900, 1200):
        name = f"wp9d-A-{arm}-step{step}-eval400-b4-p1-seed42{suffix}"
        run_dir = out_root / "generation" / name
        meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        expected = {
            "status": "completed",
            "artifact_type": "evaluation_generation_bundle",
            "run_id": name,
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
                raise SystemExit(f"{name} generation drift: {key}={meta.get(key)!r}, expected={wanted!r}")
        checkpoint = meta.get("checkpoint")
        expected_prefix = str(sources[arm] / "checkpoints" / f"checkpoint-{step}") + "#identity="
        if not isinstance(checkpoint, str) or not checkpoint.startswith(expected_prefix):
            raise SystemExit(f"{name} checkpoint identity does not bind checkpoint-{step}")
        records = run_dir / "samples" / "generations.jsonl"
        rows = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines() if line]
        if len(rows) != 400 or len({row.get("problem_id") for row in rows}) != 400:
            raise SystemExit(f"{name} generation row count/IDs invalid")
        util = meta.get("runtime_utilization", {})
        if util.get("status") != "available" or not util.get("sample_count"):
            raise SystemExit(f"{name} runtime utilization unavailable")
        job_rc = job_dir / f"{arm}-step{step}.rc"
        job_log = job_dir / f"{arm}-step{step}.log"
        if not job_rc.is_file() or job_rc.read_text(encoding="utf-8").strip() != "0":
            raise SystemExit(f"{name} missing successful per-job rc evidence")
        if not job_log.is_file() or job_log.stat().st_size == 0:
            raise SystemExit(f"{name} missing per-job terminal log")
print("formal_postcheck=PASS bundles=8 records=3200 checkpoint_parallelism=2 per_checkpoint_parallel_generators=1 scoring=deferred_to_1660ti")
PY_POST
POSTCHECK_RC=$?
set -e
if [[ "$POSTCHECK_RC" -ne 0 ]]; then
  write_evidence failed "Recipe A eval400 strict postcheck failed"
  exit 3
fi
write_evidence passed "Recipe A Public/Hidden steps 300/600/900/1200 generation completed; 1660Ti scoring remains deferred"
echo "Recipe A eval400 generation PASS: 8 bundles / 3200 records"
