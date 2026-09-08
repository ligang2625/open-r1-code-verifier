#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-d"
GATE_ID="wp9d-recipe-a-formal"
CHECKPOINT_ID="C0"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-recipe-a-formal/C0/run.sh"
RESULT_CODE_COMMIT="7a92bb587fe34e6ae80a5d703e85a0659f05f43a"
P2_OPERATOR_COMMIT="07ccc71968bedc25b1a8fd15aa0ee35a75e05389"
P1_REPORT_SHA="5a6801024c70177e5f4f777bf524e8b263f93782f4e262ad03bbe886955d231d"
P2_EVIDENCE_SHA="d261186f323ad136ace5236e50fd218dbde1b45bf3fbdc169ce8780c22da9f37"
P2_RUN_JSON_SHA="99d715b40384c6d98aff8640cc5346f5ce0b3e613031564bfaf1481a30f57756"
P2_RECORDS_SHA="9bd47fff5c36216ede0e33c087ea98946198f6d131ff780794135aa655eb9c02"
FROZEN_PUBLIC_CONFIG_SHA="b35879d094769d21537770c64d79323da7530d2da65744f747ddf7ca86377fdd"
FROZEN_HIDDEN_CONFIG_SHA="acf04cdeefcc647fb744846fcec66502c9da2ed6767d64f9b36bcc37f1264cee"
PUBLIC_SAVE50_CONFIG_SHA="70ac70488d5d7db343d5cf5043543237c95ebaa0ca175c82e6afe4aaa6df025d"
HIDDEN_SAVE50_CONFIG_SHA="c72686685ffd25b41d0a4251ad5437a7c4ab9ddb11509945239e829440bdd8d4"
CALIBRATION_MANIFEST_SHA="5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b"
PUBLIC_DATA_SHA="558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c"
HIDDEN_DATA_SHA="9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec"
BENCHMARK_REPORT_SHA="8b18864f7652f45e6f2a271bf653de873246e8387ec1a1785ac5263f59300017"
MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
PUBLIC_RUN_NAME="wp9d-A-public-vllm-qkvo-active1354-seed42"
HIDDEN_RUN_NAME="wp9d-A-hidden-vllm-qkvo-active1354-seed42"

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh preflight
  run.sh execute

Required target bindings:
  WP9D_HANDOFF_COMMIT=<exact 40-hex tracked handoff commit>
  WP9D_P3_SCRIPT_SHA256=<sha256 of this tracked run.sh>

execute additionally requires:
  WP9D_FORMAL_EXECUTION_ACK=RUN_RECIPE_A_PUBLIC_THEN_HIDDEN_1200_SAVE50

Execution semantics:
  - fresh formal Recipe A only; no implicit resume/overwrite
  - Public runs first from frozen B
  - after strict Public postcheck, Hidden starts immediately from the SAME frozen B
  - no prompt, sleep, or manual handoff exists between Public and Hidden
  - checkpoints are saved every 50 optimizer steps through step 1200
  - P1 GRPO runtime remains sequential, vLLM colocate, memory utilization 0.40
EOF
  exit 64
}

PHASE="${1:-}"
case "$PHASE" in
  preflight|execute) [[ $# -eq 1 ]] || usage ;;
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
EXPECTED_SCRIPT_SHA="${WP9D_P3_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9D_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_SCRIPT_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9D_P3_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from WP9D_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean; inspect without reset/clean" >&2; exit 125; }
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || { echo "tracked Recipe A run.sh SHA256 drift" >&2; exit 125; }
git merge-base --is-ancestor "$RESULT_CODE_COMMIT" HEAD || { echo "handoff is not a descendant of frozen result-code commit" >&2; exit 125; }
git merge-base --is-ancestor "$P2_OPERATOR_COMMIT" HEAD || { echo "handoff is not a descendant of the P2 B-refresh operator commit" >&2; exit 125; }
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
    print(path)
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

PUBLIC_FROZEN_CONFIG="$REPO_ROOT/configs/grpo/wp9d-recipe-a-public.yaml"
HIDDEN_FROZEN_CONFIG="$REPO_ROOT/configs/grpo/wp9d-recipe-a-hidden.yaml"
PUBLIC_CONFIG="$REPO_ROOT/configs/grpo/wp9d-recipe-a-public-save50.yaml"
HIDDEN_CONFIG="$REPO_ROOT/configs/grpo/wp9d-recipe-a-hidden-save50.yaml"
TRANSPORT_POLICY="$REPO_ROOT/configs/execution/piston-transport-resilience.yaml"
B_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
POOL_DIR="$DATA_ROOT/wp9c/final-reduced-calibration-C29"
P1_REPORT="$ARTIFACT_ROOT/wp9d/p1-runtime-validation/report/p1-runtime-report.json"
P2_EVIDENCE="$ARTIFACT_ROOT/operator/WP9-d/wp9d-b-refresh-eval400/C0/generate/operator-evidence.json"
P2_GENERATION="$ARTIFACT_ROOT/wp9d/b-refresh-eval400/generation/wp9d-B-eval400-b4-p1-seed42"
BENCHMARK_REPORT="$ARTIFACT_ROOT/wp9c/grpo-c29/benchmark/report/refresh_benchmark_report.json"
OUTPUT_ROOT="$ARTIFACT_ROOT/wp9d/recipe-a"
PUBLIC_RUN="$OUTPUT_ROOT/$PUBLIC_RUN_NAME"
HIDDEN_RUN="$OUTPUT_ROOT/$HIDDEN_RUN_NAME"
OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$GATE_ID/$CHECKPOINT_ID/$PHASE"
STATUS_FILE="$OP_ROOT/status"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
PUBLIC_LOG="$OP_ROOT/public.log"
HIDDEN_LOG="$OP_ROOT/hidden.log"
LOCK_FILE="$OP_ROOT/run.lock"
mkdir -p "$OP_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "operator lock is already held: $LOCK_FILE" >&2; exit 73; }

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PUBLIC_STATUS="not_started"
HIDDEN_STATUS="not_started"
PUBLIC_RC="null"
HIDDEN_RC="null"
PUBLIC_POSTCHECK_RC="null"
HIDDEN_POSTCHECK_RC="null"
EVIDENCE_FINAL=0
printf 'running\n' >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"

write_evidence() {
  local gate_status="$1" note="$2"
  local ended
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$EXPECTED_COMMIT" "$SCRIPT_SHA" "$PHASE" "$gate_status" "$STARTED_AT" "$ended" "$note" \
    "$PUBLIC_STATUS" "$HIDDEN_STATUS" "$PUBLIC_RC" "$HIDDEN_RC" "$PUBLIC_POSTCHECK_RC" "$HIDDEN_POSTCHECK_RC" <<'PY_EVIDENCE'
import json, sys
from pathlib import Path
(out, handoff, script_sha, phase, gate_status, started, ended, note,
 public_status, hidden_status, public_rc, hidden_rc, public_post, hidden_post) = sys.argv[1:]
def rc(value):
    return None if value == "null" else int(value)
payload = {
    "schema_version": "wp9d-recipe-a-formal-operator-evidence-v1",
    "stage_id": "WP9-d",
    "gate_id": "wp9d-recipe-a-formal",
    "checkpoint_id": "C0",
    "phase": phase,
    "handoff_commit": handoff,
    "operator_script": "ai-work/executor/operator/WP9-d/wp9d-recipe-a-formal/C0/run.sh",
    "operator_script_sha256": script_sha,
    "result_code_commit": "7a92bb587fe34e6ae80a5d703e85a0659f05f43a",
    "p2_generation_evidence_sha256": "d261186f323ad136ace5236e50fd218dbde1b45bf3fbdc169ce8780c22da9f37",
    "p2_generation_records_sha256": "9bd47fff5c36216ede0e33c087ea98946198f6d131ff780794135aa655eb9c02",
    "p2_baseline_verification": "deferred_to_separate_validation_gpu_by_user_direction",
    "public_config_sha256": "70ac70488d5d7db343d5cf5043543237c95ebaa0ca175c82e6afe4aaa6df025d",
    "hidden_config_sha256": "c72686685ffd25b41d0a4251ad5437a7c4ab9ddb11509945239e829440bdd8d4",
    "checkpoint_save_steps": 50,
    "max_steps": 1200,
    "eval_steps": 300,
    "grpo_runtime": {"execution": "sequential", "use_vllm": True, "vllm_mode": "colocate", "vllm_gpu_memory_utilization": 0.4, "verification_workers": 8},
    "public": {"run_name": "wp9d-A-public-vllm-qkvo-active1354-seed42", "status": public_status, "command_rc": rc(public_rc), "postcheck_rc": rc(public_post)},
    "hidden": {"run_name": "wp9d-A-hidden-vllm-qkvo-active1354-seed42", "status": hidden_status, "command_rc": rc(hidden_rc), "postcheck_rc": rc(hidden_post)},
    "gate_status": gate_status,
    "note": note,
    "started_at": started,
    "ended_at": ended,
}
Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  printf '%s\n' "$gate_status" >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
}

on_exit() {
  local rc=$?
  trap - EXIT
  if [[ "$EVIDENCE_FINAL" != "1" ]]; then
    set +e
    write_evidence failed "unexpected operator exit"
    set -e
  fi
  exit "$rc"
}
trap on_exit EXIT

common_preflight() {
  for path in "$PUBLIC_FROZEN_CONFIG" "$HIDDEN_FROZEN_CONFIG" "$PUBLIC_CONFIG" "$HIDDEN_CONFIG" "$TRANSPORT_POLICY" "$P1_REPORT" "$P2_EVIDENCE" "$BENCHMARK_REPORT"; do
    [[ -f "$path" ]] || { echo "required file missing: $path" >&2; return 125; }
  done
  [[ -d "$B_RUN" && -d "$POOL_DIR" && -d "$P2_GENERATION" ]] || { echo "required frozen directory missing" >&2; return 125; }
  [[ "$(sha256sum "$P1_REPORT" | awk '{print $1}')" == "$P1_REPORT_SHA" ]] || { echo "P1 report SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$P2_EVIDENCE" | awk '{print $1}')" == "$P2_EVIDENCE_SHA" ]] || { echo "P2 generation evidence SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$P2_GENERATION/run.json" | awk '{print $1}')" == "$P2_RUN_JSON_SHA" ]] || { echo "P2 B-generation run.json SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$P2_GENERATION/samples/generations.jsonl" | awk '{print $1}')" == "$P2_RECORDS_SHA" ]] || { echo "P2 B-generation records SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$PUBLIC_FROZEN_CONFIG" | awk '{print $1}')" == "$FROZEN_PUBLIC_CONFIG_SHA" ]] || { echo "frozen Public Recipe A config SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$HIDDEN_FROZEN_CONFIG" | awk '{print $1}')" == "$FROZEN_HIDDEN_CONFIG_SHA" ]] || { echo "frozen Hidden Recipe A config SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$PUBLIC_CONFIG" | awk '{print $1}')" == "$PUBLIC_SAVE50_CONFIG_SHA" ]] || { echo "save50 Public config SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$HIDDEN_CONFIG" | awk '{print $1}')" == "$HIDDEN_SAVE50_CONFIG_SHA" ]] || { echo "save50 Hidden config SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$POOL_DIR/calibration_manifest.json" | awk '{print $1}')" == "$CALIBRATION_MANIFEST_SHA" ]] || { echo "C29 calibration manifest SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$POOL_DIR/training/public_grpo.jsonl" | awk '{print $1}')" == "$PUBLIC_DATA_SHA" ]] || { echo "C29 Public dataset SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$POOL_DIR/training/hidden_grpo.jsonl" | awk '{print $1}')" == "$HIDDEN_DATA_SHA" ]] || { echo "C29 Hidden dataset SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$BENCHMARK_REPORT" | awk '{print $1}')" == "$BENCHMARK_REPORT_SHA" ]] || { echo "formal benchmark report SHA drift" >&2; return 125; }

  "$PY" - "$P1_REPORT" "$P2_EVIDENCE" "$P2_GENERATION" "$B_RUN" \
    "$PUBLIC_FROZEN_CONFIG" "$HIDDEN_FROZEN_CONFIG" "$PUBLIC_CONFIG" "$HIDDEN_CONFIG" "$BENCHMARK_REPORT" <<'PY_PREFLIGHT'
import json, sys, yaml
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
from code_verifier.throughput import check_refresh_benchmark_report
(p1_path, p2e_path, p2run_path, b_path, pub0_path, hid0_path, pub_path, hid_path, bench_path) = map(Path, sys.argv[1:])
p1 = json.loads(p1_path.read_text(encoding="utf-8"))
freeze = p1.get("runtime_freeze_candidate", {})
grpo_freeze = freeze.get("GRPO", {})
for key, wanted in {
    "public_hidden_execution": "sequential",
    "use_vllm": True,
    "vllm_mode": "colocate",
    "vllm_gpu_memory_utilization": 0.4,
    "reward_workers": 8,
}.items():
    if grpo_freeze.get(key) != wanted:
        raise SystemExit(f"P1 GRPO runtime freeze drift: {key}")
if grpo_freeze.get("lora_target_modules") not in (["q_proj", "k_proj", "v_proj", "o_proj"], ("q_proj", "k_proj", "v_proj", "o_proj")):
    raise SystemExit("P1 GRPO LoRA target freeze drift")
p2e = json.loads(p2e_path.read_text(encoding="utf-8"))
if p2e.get("gate_status") != "passed" or p2e.get("command_rc") != 0 or p2e.get("postcheck_rc") != 0:
    raise SystemExit("P2 B-generation operator evidence did not pass")
if p2e.get("generation_records_file_sha256") != "9bd47fff5c36216ede0e33c087ea98946198f6d131ff780794135aa655eb9c02":
    raise SystemExit("P2 B-generation evidence records hash drift")
p2run = json.loads((p2run_path / "run.json").read_text(encoding="utf-8"))
for key, wanted in {
    "status": "completed", "completed_records": 400, "total_problems": 400,
    "batch_size": 4, "parallel_generators": 1, "seed": 42,
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "records_sha256": "9bd47fff5c36216ede0e33c087ea98946198f6d131ff780794135aa655eb9c02",
}.items():
    if p2run.get(key) != wanted:
        raise SystemExit(f"P2 B-generation identity drift: {key}")
identity = load_completed_sft_checkpoint(b_path)
if (identity.run_id, identity.model_id, identity.model_revision, identity.seed) != (
    "B-sft-formal-seed42", "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "2e1fd397ee46e1388853d2af2c993145b0f1098a", 42,
):
    raise SystemExit("frozen B strict identity drift")

pairs = []
for original_path, save50_path in ((pub0_path, pub_path), (hid0_path, hid_path)):
    original = yaml.safe_load(original_path.read_text(encoding="utf-8"))
    save50 = yaml.safe_load(save50_path.read_text(encoding="utf-8"))
    expected = dict(original)
    expected["save_steps"] = 50
    if save50 != expected:
        raise SystemExit(f"save50 config changes fields other than save_steps: {save50_path.name}")
    pairs.append(save50)
public, hidden = pairs
expected_common = {
    "num_generations": 8,
    "max_prompt_length": 2048,
    "max_completion_length": 512,
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 8,
    "learning_rate": 0.000005,
    "num_train_epochs": 1.0,
    "max_steps": 1200,
    "warmup_ratio": 0.05,
    "lr_scheduler_type": "constant_with_warmup",
    "temperature": 0.8,
    "top_p": 0.95,
    "beta": 0.01,
    "bf16": True,
    "fp16": False,
    "gradient_checkpointing": True,
    "lora_r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "lora_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "logging_steps": 1,
    "save_steps": 50,
    "eval_steps": 300,
    "seed": 42,
    "min_cuda_memory_gb": 20.0,
    "use_vllm": True,
    "vllm_mode": "colocate",
    "vllm_gpu_memory_utilization": 0.4,
}
for mode, value, run_name, dataset in (
    ("public", public, "wp9d-A-public-vllm-qkvo-active1354-seed42", "wp9c/final-reduced-calibration-C29/training/public_grpo.jsonl"),
    ("hidden", hidden, "wp9d-A-hidden-vllm-qkvo-active1354-seed42", "wp9c/final-reduced-calibration-C29/training/hidden_grpo.jsonl"),
):
    if value.get("reward_mode") != mode or value.get("run_name") != run_name or value.get("dataset_path") != dataset:
        raise SystemExit(f"Recipe A {mode} identity drift")
    for key, wanted in expected_common.items():
        if value.get(key) != wanted:
            raise SystemExit(f"Recipe A {mode} config drift: {key}={value.get(key)!r}, expected={wanted!r}")
for key in set(public) | set(hidden):
    if key in {"reward_mode", "run_name", "dataset_path"}:
        continue
    if public.get(key) != hidden.get(key):
        raise SystemExit(f"Public/Hidden paired non-reward parameter drift: {key}")
bench = check_refresh_benchmark_report(bench_path)
if bench.evidence_class != "formal" or bench.selected_grpo_verification_workers != 8 or bench.paired_grpo_mode != "sequential":
    raise SystemExit("formal GRPO benchmark selection drift")
if bench.calibration_manifest_sha256 != "5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b":
    raise SystemExit("benchmark calibration manifest drift")
if bench.active_public_training_sha256 != "558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c" or bench.active_hidden_training_sha256 != "9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec":
    raise SystemExit("benchmark active training hashes drift")
print("formal_identity=passed save_steps=50 max_steps=1200 public_then_hidden=sequential")
print("p2_generation_gate=passed baseline_verification=deferred_to_separate_validation_gpu")
PY_PREFLIGHT

  "$PY" - <<'PY_DEP'
from importlib.metadata import version
if version("setuptools") != "83.0.0":
    raise SystemExit(f"setuptools drift: {version('setuptools')}")
PY_DEP

  local runtimes execute_result
  runtimes="$(curl -fsS http://127.0.0.1:2000/api/v2/runtimes)" || { echo "Piston runtimes endpoint unavailable" >&2; return 125; }
  execute_result="$(curl -fsS -H 'Content-Type: application/json' -d '{"language":"python","version":"3.10.0","files":[{"content":"print(6*7)"}]}' http://127.0.0.1:2000/api/v2/execute)" || { echo "Piston execute endpoint unavailable" >&2; return 125; }
  "$PY" - "$runtimes" "$execute_result" <<'PY_PISTON'
import json, sys
runtimes = json.loads(sys.argv[1])
if not any(item.get("language") == "python" and item.get("version") == "3.10.0" for item in runtimes):
    raise SystemExit("Piston Python 3.10.0 runtime missing")
value = json.loads(sys.argv[2])
run = value.get("run", {})
if run.get("code") != 0 or run.get("stdout") != "42\n":
    raise SystemExit("Piston execution smoke failed")
PY_PISTON

  local gpu_row
  gpu_row="$(nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$3); gsub(/ /,"",$4); if ($3+0 >= 22528 && $4+0 >= 20000) {print $1"|"$2"|"$3"|"$4; exit}}')"
  [[ -n "$gpu_row" ]] || { echo "formal GRPO requires RTX 4090 with >=22528 MiB total and >=20000 MiB free VRAM" >&2; return 125; }
  local avail_kb avail_inodes
  avail_kb="$(df -Pk "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
  avail_inodes="$(df -Pi "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
  [[ "$avail_kb" =~ ^[0-9]+$ && "$avail_kb" -ge 31457280 ]] || { echo "artifact filesystem has <30 GiB free" >&2; return 125; }
  [[ "$avail_inodes" =~ ^[0-9]+$ && "$avail_inodes" -ge 100000 ]] || { echo "artifact filesystem has insufficient free inodes" >&2; return 125; }
  [[ ! -e "$PUBLIC_RUN" ]] || { echo "Public formal run already exists; fresh operator refuses overwrite/resume" >&2; return 125; }
  [[ ! -e "$HIDDEN_RUN" ]] || { echo "Hidden formal run already exists; fresh operator refuses overwrite/resume" >&2; return 125; }
}

set +e
common_preflight >>"$OP_ROOT/preflight.log" 2>&1
PREFLIGHT_RC=$?
set -e
if [[ "$PREFLIGHT_RC" -ne 0 ]]; then
  write_evidence failed "formal Recipe A preflight failed"
  EVIDENCE_FINAL=1
  exit "$PREFLIGHT_RC"
fi

if [[ "$PHASE" == "preflight" ]]; then
  write_evidence passed "formal Recipe A preflight passed; no training started"
  EVIDENCE_FINAL=1
  echo "WP9-d Recipe A formal preflight PASS"
  exit 0
fi

[[ "${WP9D_FORMAL_EXECUTION_ACK:-}" == "RUN_RECIPE_A_PUBLIC_THEN_HIDDEN_1200_SAVE50" ]] || {
  write_evidence failed "execute acknowledgement missing or incorrect"
  EVIDENCE_FINAL=1
  echo "formal execution requires WP9D_FORMAL_EXECUTION_ACK=RUN_RECIPE_A_PUBLIC_THEN_HIDDEN_1200_SAVE50" >&2
  exit 125
}
mkdir -p "$OUTPUT_ROOT"

train_one() {
  local mode="$1" log="$2"
  "$PY" -m torch.distributed.run \
    --standalone \
    --nnodes=1 \
    --nproc-per-node=1 \
    --max-restarts=0 \
    -m code_verifier.cli train-grpo \
    --public-config "$PUBLIC_CONFIG" \
    --hidden-config "$HIDDEN_CONFIG" \
    --dataset-dir "$POOL_DIR" \
    --public-run-name "$PUBLIC_RUN_NAME" \
    --hidden-run-name "$HIDDEN_RUN_NAME" \
    --public-sft-run-dir "$B_RUN" \
    --hidden-sft-run-dir "$B_RUN" \
    --reward-mode "$mode" \
    --piston-transport-policy "$TRANSPORT_POLICY" \
    --calibration-manifest "$POOL_DIR/calibration_manifest.json" \
    --refresh-dataset-dir "$POOL_DIR" \
    --reference-dataset-dir "$POOL_DIR" \
    --benchmark-report "$BENCHMARK_REPORT" \
    --verification-workers 8 \
    --seed 42 \
    --output-dir "$OUTPUT_ROOT" >"$log" 2>&1
}

postcheck_one() {
  local run_dir="$1" mode="$2"
  "$PY" - "$run_dir" "$mode" "$EXPECTED_COMMIT" <<'PY_POST'
import json, sys, yaml
from pathlib import Path
from peft import PeftConfig
from code_verifier.training.grpo import load_completed_grpo_checkpoint
run = Path(sys.argv[1]); mode = sys.argv[2]; handoff = sys.argv[3]
identity = load_completed_grpo_checkpoint(run)
if identity.reward_mode != mode:
    raise SystemExit("completed GRPO reward mode drift")
if (identity.parent_sft.run_id, identity.parent_sft.model_id, identity.parent_sft.model_revision, identity.parent_sft.seed) != (
    "B-sft-formal-seed42", "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "2e1fd397ee46e1388853d2af2c993145b0f1098a", 42,
):
    raise SystemExit("completed GRPO parent B identity drift")
meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
if meta.get("status") != "completed" or meta.get("global_step") != 1200:
    raise SystemExit("formal GRPO did not complete exactly 1200 optimizer steps")
if meta.get("git_commit") != handoff:
    raise SystemExit("formal GRPO git_commit differs from handoff commit")
for name in ("metrics.jsonl", "rewards.jsonl", "group_metrics.jsonl"):
    path = run / name
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"formal GRPO artifact missing/empty: {name}")
resolved = yaml.safe_load((run / "resolved_config.yaml").read_text(encoding="utf-8"))
for key, wanted in {
    "num_generations": 8,
    "max_prompt_length": 2048,
    "max_completion_length": 512,
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 8,
    "learning_rate": 0.000005,
    "max_steps": 1200,
    "save_steps": 50,
    "eval_steps": 300,
    "seed": 42,
    "use_vllm": True,
    "vllm_mode": "colocate",
    "vllm_gpu_memory_utilization": 0.4,
}.items():
    if resolved.get(key) != wanted:
        raise SystemExit(f"resolved formal GRPO config drift: {key}={resolved.get(key)!r}, expected={wanted!r}")
expected_steps = list(range(50, 1201, 50))
observed = sorted(
    int(path.name.removeprefix("checkpoint-"))
    for path in (run / "checkpoints").glob("checkpoint-*")
    if path.is_dir() and path.name.removeprefix("checkpoint-").isdigit()
)
if observed != expected_steps:
    raise SystemExit(f"save50 checkpoint cadence drift: observed={observed}")
for step in expected_steps:
    ckpt = run / "checkpoints" / f"checkpoint-{step}"
    state = json.loads((ckpt / "trainer_state.json").read_text(encoding="utf-8"))
    if state.get("global_step") != step:
        raise SystemExit(f"checkpoint-{step} trainer_state global_step drift")
final = run / "checkpoints" / "checkpoint-1200"
adapter = PeftConfig.from_pretrained(str(final), local_files_only=True)
if set(adapter.target_modules or ()) != {"q_proj", "k_proj", "v_proj", "o_proj"}:
    raise SystemExit("final PEFT adapter target_modules are not qkvo")
for required in ("adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth", "training_args.bin"):
    if not (final / required).is_file():
        raise SystemExit(f"checkpoint-1200 missing {required}")
util = meta.get("runtime_utilization", {})
if util.get("status") != "available" or not util.get("sample_count"):
    raise SystemExit("formal GRPO runtime utilization telemetry unavailable")
print(f"formal_postcheck=PASS mode={mode} checkpoints=24 final_step=1200")
PY_POST
}

PUBLIC_STATUS="running"
write_evidence running "Public formal GRPO started; Hidden has not started"
set +e
train_one public "$PUBLIC_LOG"
PUBLIC_RC=$?
set -e
if [[ "$PUBLIC_RC" -ne 0 ]]; then
  PUBLIC_STATUS="failed"
  write_evidence failed "Public formal GRPO command exited nonzero; Hidden was not started"
  EVIDENCE_FINAL=1
  exit "$PUBLIC_RC"
fi
set +e
postcheck_one "$PUBLIC_RUN" public >>"$PUBLIC_LOG" 2>&1
PUBLIC_POSTCHECK_RC=$?
set -e
if [[ "$PUBLIC_POSTCHECK_RC" -ne 0 ]]; then
  PUBLIC_STATUS="failed_postcheck"
  write_evidence failed "Public formal GRPO postcheck failed; Hidden was not started"
  EVIDENCE_FINAL=1
  exit 3
fi
PUBLIC_STATUS="passed"

# Intentionally no prompt, sleep, or manual gate here. Hidden starts immediately
# after the successful Public strict postcheck and independently rebuilds from B.
HIDDEN_STATUS="running"
write_evidence running "Public passed; Hidden formal GRPO started immediately from the same frozen B"
set +e
train_one hidden "$HIDDEN_LOG"
HIDDEN_RC=$?
set -e
if [[ "$HIDDEN_RC" -ne 0 ]]; then
  HIDDEN_STATUS="failed"
  write_evidence failed "Hidden formal GRPO command exited nonzero after Public passed"
  EVIDENCE_FINAL=1
  exit "$HIDDEN_RC"
fi
set +e
postcheck_one "$HIDDEN_RUN" hidden >>"$HIDDEN_LOG" 2>&1
HIDDEN_POSTCHECK_RC=$?
set -e
if [[ "$HIDDEN_POSTCHECK_RC" -ne 0 ]]; then
  HIDDEN_STATUS="failed_postcheck"
  write_evidence failed "Hidden formal GRPO postcheck failed after Public passed"
  EVIDENCE_FINAL=1
  exit 3
fi
HIDDEN_STATUS="passed"
write_evidence passed "Public and Hidden formal Recipe A completed sequentially with save_steps=50"
EVIDENCE_FINAL=1
echo "WP9-d Recipe A formal PASS: Public -> Hidden, 1200 steps each, checkpoint every 50 steps"
