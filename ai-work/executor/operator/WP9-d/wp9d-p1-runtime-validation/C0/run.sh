#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-d"
GATE_ID="wp9d-p1-runtime-validation"
CHECKPOINT_ID="C0"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/run.sh"
HELPER_REL="ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/build_eval8_subset.py"
REPORT_REL="ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/p1_runtime_report.py"
EVIDENCE_REL="ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/operator_evidence.py"
ACCEPTED_REL="ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/accepted_pointer.py"

PUBLIC_SMOKE_SHA="6105bb2706460ee7460393205a10770a2004a93c53d2566197281138f0157723"
HIDDEN_SMOKE_SHA="0e1b9efa674ef2fd10773f2aeeb34aa04579fd0f48de7d847c6785d00df5d4a8"
C29_MANIFEST_SHA="5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b"
C29_PUBLIC_SHA="558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c"
C29_HIDDEN_SHA="9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec"

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh preflight
  run.sh single <public|hidden>
  run.sh concurrent <0.40|0.30|0.25>
  run.sh eval <single|dual>
  run.sh report

This P1 handoff intentionally has no full-eval or Recipe-A command.
Required target environment:
  WP9D_HANDOFF_COMMIT=<exact 40-hex handoff commit>
  WP9D_P1_SCRIPT_SHA256=<sha256 of this tracked run.sh>
Optional only after an affected failed attempt has been diagnosed/repaired:
  WP9D_P1_RETRY_TAG=<safe suffix, e.g. r1>
EOF
  exit 64
}

PHASE="${1:-}"
ARG="${2:-}"
case "$PHASE" in
  preflight|report) [[ $# -eq 1 ]] || usage ;;
  single) [[ $# -eq 2 && ( "$ARG" == "public" || "$ARG" == "hidden" ) ]] || usage ;;
  concurrent) [[ $# -eq 2 && ( "$ARG" == "0.40" || "$ARG" == "0.30" || "$ARG" == "0.25" ) ]] || usage ;;
  eval) [[ $# -eq 2 && ( "$ARG" == "single" || "$ARG" == "dual" ) ]] || usage ;;
  *) usage ;;
esac
DETAIL="${ARG:-none}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
[[ "$REPO_ROOT" == "/root/open-r1-code-verifier" ]] || { echo "P1 target repo must be /root/open-r1-code-verifier" >&2; exit 125; }
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "target .venv Python is unavailable" >&2; exit 125; }
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"

EXPECTED_COMMIT="${WP9D_HANDOFF_COMMIT:-}"
EXPECTED_SCRIPT_SHA="${WP9D_P1_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9D_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_SCRIPT_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9D_P1_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from WP9D_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean; inspect without reset/clean" >&2; exit 125; }
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || { echo "tracked P1 run.sh SHA256 drift" >&2; exit 125; }

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
readarray -t MACHINE_FIELDS < <("$PY" - "$MACHINE_POINTER" <<'PY_MACHINE'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected={
    "machine_status":"READY_FOR_VALIDATION_PLANNER",
    "artifact_root":"/root/sj-tmp/open-r1-code-verifier-outputs",
    "hf_home":"/root/huggingface",
    "formal_data_root":"/root/open-r1-code-verifier-data-4090",
    "piston_endpoint":"http://127.0.0.1:2000",
}
if not isinstance(value, dict): raise SystemExit("validation machine pointer must be an object")
for key, wanted in expected.items():
    if value.get(key) != wanted: raise SystemExit(f"validation machine {key} drift")
for key in ("artifact_root","hf_home","formal_data_root"):
    path=Path(value[key])
    if not path.is_absolute() or not str(path).startswith("/root/") or "/data" in str(path):
        raise SystemExit(f"validation machine {key} violates current /root policy")
for key in ("artifact_root","hf_home","formal_data_root","piston_endpoint"):
    print(value[key])
PY_MACHINE
)
ARTIFACT_ROOT="${MACHINE_FIELDS[0]}"
HF_HOME_TARGET="${MACHINE_FIELDS[1]}"
DATA_ROOT="${MACHINE_FIELDS[2]}"
PISTON_ENDPOINT="${MACHINE_FIELDS[3]}"

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$DATA_ROOT"
export HF_HOME="$HF_HOME_TARGET"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"
export TMPDIR="/root/tmp"
mkdir -p "$TMPDIR"

B_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
POOL_DIR="$DATA_ROOT/wp9c/final-reduced-calibration-C29"
EVAL400_DIR="$DATA_ROOT/wp9c/heldout-eval400-C34"
EVAL8_DIR="$DATA_ROOT/wp9d/p1-eval8-C0"
P1_ROOT="$ARTIFACT_ROOT/wp9d/p1-runtime-validation"
BENCHMARK_REPORT="$ARTIFACT_ROOT/wp9c/grpo-c29/benchmark/report/refresh_benchmark_report.json"
PUBLIC_CONFIG="$REPO_ROOT/configs/grpo/wp9d-runtime-smoke-public.yaml"
HIDDEN_CONFIG="$REPO_ROOT/configs/grpo/wp9d-runtime-smoke-hidden.yaml"
EVAL_CONFIG="$REPO_ROOT/configs/eval/base.yaml"
TRANSPORT_POLICY="$REPO_ROOT/configs/execution/piston-transport-resilience.yaml"
mkdir -p "$P1_ROOT" "$P1_ROOT/accepted" "$P1_ROOT/latest"

RETRY_TAG="${WP9D_P1_RETRY_TAG:-}"
if [[ -n "$RETRY_TAG" ]]; then
  [[ "$RETRY_TAG" =~ ^[A-Za-z0-9._-]+$ && "$RETRY_TAG" != *..* ]] || { echo "WP9D_P1_RETRY_TAG is unsafe" >&2; exit 64; }
  RUN_SUFFIX="-$RETRY_TAG"
  DIR_SUFFIX="-$RETRY_TAG"
else
  RUN_SUFFIX=""
  DIR_SUFFIX=""
fi

OP_DETAIL_SAFE="${DETAIL//./p}"
OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$GATE_ID/$CHECKPOINT_ID/${PHASE}-${OP_DETAIL_SAFE}${DIR_SUFFIX}"
STATUS_FILE="$OP_ROOT/status"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
OP_LOG="$OP_ROOT/terminal.log"
LOCK_FILE="$OP_ROOT/run.lock"
mkdir -p "$OP_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "operator lock is already held: $LOCK_FILE" >&2; exit 73; }
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '[%s] start phase=%s detail=%s commit=%s script_sha=%s\n' "$START_TIME" "$PHASE" "$DETAIL" "$EXPECTED_COMMIT" "$SCRIPT_SHA" >>"$OP_LOG"
printf 'running\n' >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"

COMMAND_RC="null"
POSTCHECK_RC="null"
EVIDENCE_WRITTEN=0
GPU_INDEX=""
GPU_NAME=""
GPU_TOTAL_MIB=""

write_evidence() {
  local gate_status="$1"; shift
  local ended
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local args=(
    --output "$EVIDENCE_FILE"
    --phase "$PHASE"
    --detail "$DETAIL"
    --handoff-commit "$EXPECTED_COMMIT"
    --script-path "$SCRIPT_REL"
    --script-sha256 "$SCRIPT_SHA"
    --target-repo "$REPO_ROOT"
    --artifact-root "$ARTIFACT_ROOT"
    --formal-data-root "$DATA_ROOT"
    --hf-home "$HF_HOME_TARGET"
    --piston-endpoint "$PISTON_ENDPOINT"
    --gpu-name "$GPU_NAME"
    --gpu-total-mib "$GPU_TOTAL_MIB"
    --started-at "$START_TIME"
    --ended-at "$ended"
    --command-rc "$COMMAND_RC"
    --postcheck-rc "$POSTCHECK_RC"
    --gate-status "$gate_status"
  )
  local artifact
  for artifact in "$@"; do args+=(--artifact "$artifact"); done
  "$PY" "$REPO_ROOT/$EVIDENCE_REL" "${args[@]}" >/dev/null
  printf '%s\n' "$gate_status" >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  printf '[%s] finish phase=%s detail=%s status=%s command_rc=%s postcheck_rc=%s\n' \
    "$ended" "$PHASE" "$DETAIL" "$gate_status" "$COMMAND_RC" "$POSTCHECK_RC" >>"$OP_LOG"
  EVIDENCE_WRITTEN=1
}

on_exit() {
  local rc=$?
  trap - EXIT
  if [[ "$EVIDENCE_WRITTEN" != "1" ]]; then
    set +e
    write_evidence failed
    set -e
  fi
  exit "$rc"
}
trap on_exit EXIT

write_accepted() {
  local key="$1" primary="$2" phase_meta="${3:-}"
  local args=(
    --output "$P1_ROOT/accepted/$key.json"
    --phase "$PHASE"
    --detail "$DETAIL"
    --retry-tag "$RETRY_TAG"
    --handoff-commit "$EXPECTED_COMMIT"
    --primary-artifact "$primary"
    --operator-evidence "$EVIDENCE_FILE"
  )
  [[ -z "$phase_meta" ]] || args+=(--phase-meta "$phase_meta")
  "$PY" "$REPO_ROOT/$ACCEPTED_REL" "${args[@]}" >/dev/null
}

check_accepted() {
  local key="$1" phase="$2" detail="$3"
  "$PY" - "$P1_ROOT/accepted/$key.json" "$phase" "$detail" <<'PY_ACCEPTED_CHECK'
import json, sys
from pathlib import Path
pointer=Path(sys.argv[1])
if not pointer.is_file(): raise SystemExit(1)
value=json.loads(pointer.read_text(encoding="utf-8"))
if value.get("schema_version") != "wp9d-p1-accepted-v1": raise SystemExit(1)
if value.get("phase") != sys.argv[2] or value.get("detail") != sys.argv[3]: raise SystemExit(1)
primary=Path(value.get("primary_artifact", "")); evidence=Path(value.get("operator_evidence", ""))
if not primary.exists() or not evidence.is_file(): raise SystemExit(1)
ev=json.loads(evidence.read_text(encoding="utf-8"))
if ev.get("gate_status") != "passed" or ev.get("command_rc") != 0 or ev.get("postcheck_rc") != 0: raise SystemExit(1)
if ev.get("handoff_commit") != value.get("handoff_commit"): raise SystemExit(1)
PY_ACCEPTED_CHECK
}

finalize_success() {
  local key="$1" primary="$2" phase_meta="$3"; shift 3
  write_evidence passed "$@"
  if [[ "$key" != "-" ]]; then
    set +e
    write_accepted "$key" "$primary" "$phase_meta"
    local pointer_rc=$?
    set -e
    if [[ "$pointer_rc" -ne 0 ]]; then
      EVIDENCE_WRITTEN=0
      POSTCHECK_RC=3
      write_evidence failed "$@"
      return 3
    fi
  fi
}

now_ns() { date +%s%N; }

write_phase_meta() {
  local path="$1" start_ns="$2" end_ns="$3" rc="$4" kind="$5" detail="$6"
  "$PY" - "$path" "$start_ns" "$end_ns" "$rc" "$kind" "$detail" <<'PY_META'
import json, sys
from pathlib import Path
path=Path(sys.argv[1]); start=int(sys.argv[2]); end=int(sys.argv[3]); rc=int(sys.argv[4])
value={"schema_version":"wp9d-p1-phase-v1","kind":sys.argv[5],"detail":sys.argv[6],"return_code":rc,
       "wall_seconds":(end-start)/1_000_000_000.0}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(value, sort_keys=True, indent=2)+"\n", encoding="utf-8")
PY_META
}

storage_preflight() {
  local required_bytes required_inodes
  case "$PHASE" in
    concurrent) required_bytes=$((4 * 1024 * 1024 * 1024)); required_inodes=50000 ;;
    single) required_bytes=$((2 * 1024 * 1024 * 1024)); required_inodes=30000 ;;
    eval|preflight) required_bytes=$((1 * 1024 * 1024 * 1024)); required_inodes=20000 ;;
    report) required_bytes=$((100 * 1024 * 1024)); required_inodes=5000 ;;
  esac
  local free_bytes free_inodes
  free_bytes="$(df -PB1 "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
  free_inodes="$(df -Pi "$ARTIFACT_ROOT" | awk 'NR==2 {print $4}')"
  [[ "$free_bytes" =~ ^[0-9]+$ && "$free_bytes" -ge "$required_bytes" ]] || { echo "artifact filesystem free bytes below P1 threshold" >&2; exit 125; }
  [[ "$free_inodes" =~ ^[0-9]+$ && "$free_inodes" -ge "$required_inodes" ]] || { echo "artifact filesystem free inodes below P1 threshold" >&2; exit 125; }
}

static_runtime_preflight() {
  [[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" ]] || { echo "artifact root unavailable" >&2; exit 125; }
  [[ -d "$DATA_ROOT" ]] || { echo "formal data root unavailable" >&2; exit 125; }
  [[ -d "$B_RUN" ]] || { echo "frozen B unavailable" >&2; exit 125; }
  [[ "$(sha256sum "$PUBLIC_CONFIG" | awk '{print $1}')" == "$PUBLIC_SMOKE_SHA" ]] || { echo "Public smoke config hash drift" >&2; exit 125; }
  [[ "$(sha256sum "$HIDDEN_CONFIG" | awk '{print $1}')" == "$HIDDEN_SMOKE_SHA" ]] || { echo "Hidden smoke config hash drift" >&2; exit 125; }
  "$PY" - "$PUBLIC_CONFIG" "$HIDDEN_CONFIG" "$B_RUN" <<'PY_STATIC'
import importlib.metadata as md, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
import torch
import torch.distributed as dist
from peft import LoraConfig, get_peft_model
from torch.nn.parallel import DistributedDataParallel as DDP
from transformers import Qwen2Config, Qwen2ForCausalLM
from code_verifier.training.grpo import (
    _clear_stale_merged_peft_metadata,
    _enforce_nonreentrant_gradient_checkpointing,
    _load_grpo_runtime,
    _runtime_arguments,
    load_grpo_training_config,
)
from code_verifier.training.sft import load_completed_sft_checkpoint
pub=load_grpo_training_config(Path(sys.argv[1])); hid=load_grpo_training_config(Path(sys.argv[2]))
for cfg, mode in ((pub,"public"),(hid,"hidden")):
    if cfg.reward_mode != mode or cfg.max_steps != 1 or cfg.save_steps != 1 or cfg.num_generations != 8:
        raise SystemExit(f"{mode} smoke config semantics drift")
    if cfg.per_device_train_batch_size != 1 or cfg.gradient_accumulation_steps != 8:
        raise SystemExit(f"{mode} scientific batch semantics drift")
    if not cfg.gradient_checkpointing:
        raise SystemExit(f"{mode} gradient checkpointing drift")
    if tuple(cfg.lora_target_modules or ()) != ("q_proj", "k_proj", "v_proj", "o_proj"):
        raise SystemExit(f"{mode} GRPO LoRA qkvo target semantics drift")
    if not cfg.use_vllm or cfg.vllm_mode != "colocate" or cfg.vllm_gpu_memory_utilization != 0.4:
        raise SystemExit(f"{mode} vLLM smoke semantics drift")
identity=load_completed_sft_checkpoint(Path(sys.argv[3]))
if identity.run_id != "B-sft-formal-seed42" or identity.model_id != "Qwen/Qwen2.5-Coder-1.5B-Instruct":
    raise SystemExit("frozen B identity drift")
if identity.model_revision != "2e1fd397ee46e1388853d2af2c993145b0f1098a" or identity.seed != 42:
    raise SystemExit("frozen B revision/seed drift")
expected={"trl":"0.18.0","vllm":"0.8.5.post1","transformers":"4.52.3","accelerate":"1.4.0","peft":"0.14.0","setuptools":"83.0.0"}
for package, version in expected.items():
    actual=md.version(package)
    if actual != version: raise SystemExit(f"{package} version drift: {actual} != {version}")
runtime=_load_grpo_runtime()
_, training_args=_runtime_arguments(pub, checkpoint_dir=Path("/root/tmp/wp9d-p1-preflight-checkpoints"), parent_sft=identity, seed=42, runtime=runtime)
if getattr(training_args, "gradient_checkpointing_kwargs", None) != {"use_reentrant": False}:
    raise SystemExit("pinned GRPO runtime must use non-reentrant gradient checkpointing")
tiny_cfg=Qwen2Config(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=64, use_cache=False)
tiny_lora=LoraConfig(r=4, lora_alpha=8, lora_dropout=0.0, target_modules=["q_proj","k_proj","v_proj","o_proj"], task_type="CAUSAL_LM")
tiny_parent=get_peft_model(Qwen2ForCausalLM(tiny_cfg), tiny_lora)
tiny_merged=_clear_stale_merged_peft_metadata(tiny_parent.merge_and_unload(safe_merge=True))
if hasattr(tiny_merged, "peft_config"):
    raise SystemExit("tiny safe-merge retained stale PEFT metadata")
tiny_policy=get_peft_model(tiny_merged, tiny_lora)
tiny_trainer=SimpleNamespace(model=tiny_policy)
tiny_args=SimpleNamespace(gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False})
_enforce_nonreentrant_gradient_checkpointing(tiny_trainer, training_args=tiny_args, runtime=runtime)
rdzv=tempfile.NamedTemporaryFile(delete=False); rdzv.close()
try:
    dist.init_process_group("gloo", init_method="file://"+rdzv.name, rank=0, world_size=1)
    ddp=DDP(tiny_policy, find_unused_parameters=True)
    ids=torch.randint(0, 64, (2, 16))
    loss=ddp(input_ids=ids, labels=ids).loss
    loss.backward()
    grads=[p.grad for n,p in ddp.named_parameters() if "lora_" in n and p.requires_grad]
    if not grads or any(g is None for g in grads):
        raise SystemExit("tiny qkvo DDP non-reentrant backward did not populate all LoRA gradients")
finally:
    if dist.is_initialized():
        dist.destroy_process_group()
    os.unlink(rdzv.name)
print("static_runtime_identity=ok")
PY_STATIC
}

grpo_input_preflight() {
  [[ -d "$POOL_DIR" ]] || { echo "C29 active pool unavailable" >&2; exit 125; }
  [[ -f "$BENCHMARK_REPORT" ]] || { echo "C29 formal benchmark report unavailable" >&2; exit 125; }
  [[ "$(sha256sum "$POOL_DIR/calibration_manifest.json" | awk '{print $1}')" == "$C29_MANIFEST_SHA" ]] || { echo "C29 manifest hash drift" >&2; exit 125; }
  [[ "$(sha256sum "$POOL_DIR/training/public_grpo.jsonl" | awk '{print $1}')" == "$C29_PUBLIC_SHA" ]] || { echo "C29 Public hash drift" >&2; exit 125; }
  [[ "$(sha256sum "$POOL_DIR/training/hidden_grpo.jsonl" | awk '{print $1}')" == "$C29_HIDDEN_SHA" ]] || { echo "C29 Hidden hash drift" >&2; exit 125; }
  "$PY" - "$BENCHMARK_REPORT" <<'PY_BENCH'
import sys
from pathlib import Path
from code_verifier.throughput import check_refresh_benchmark_report
report=check_refresh_benchmark_report(Path(sys.argv[1]))
if report.evidence_class != "formal" or report.selected_grpo_verification_workers != 8:
    raise SystemExit("C29 benchmark binding is not formal/w8")
PY_BENCH
}

eval_input_preflight() {
  [[ -d "$EVAL400_DIR" ]] || { echo "canonical eval400 source unavailable" >&2; exit 125; }
  if check_accepted preflight preflight none >/dev/null 2>&1; then
    "$PY" "$REPO_ROOT/$HELPER_REL" --source "$EVAL400_DIR" --output "$EVAL8_DIR" --verify-existing-only >/dev/null
  else
    "$PY" "$REPO_ROOT/$HELPER_REL" --source "$EVAL400_DIR" --output "$EVAL8_DIR" >/dev/null
  fi
}

gpu_preflight() {
  command -v nvidia-smi >/dev/null 2>&1 || { echo "nvidia-smi unavailable" >&2; exit 125; }
  local gpu_list gpu_row free_mib
  gpu_list="$(nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits)"
  gpu_row="$(printf '%s\n' "$gpu_list" | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$1); gsub(/ /,"",$3); gsub(/ /,"",$4); if ($3+0 >= 22528 && $4+0 >= 20000) {print $1"|"$2"|"$3"|"$4; exit}}')"
  [[ -n "$gpu_row" ]] || { echo "P1 requires RTX 4090 with >=22528 MiB total and >=20000 MiB free VRAM" >&2; exit 125; }
  IFS='|' read -r GPU_INDEX GPU_NAME GPU_TOTAL_MIB free_mib <<<"$gpu_row"
  GPU_NAME="$(printf '%s' "$GPU_NAME" | sed 's/^ *//;s/ *$//')"
  export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
  "$PY" - <<'PY_CUDA'
import torch
if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise SystemExit("P1 requires exactly one visible CUDA device")
name=torch.cuda.get_device_name(0)
if "RTX 4090" not in name: raise SystemExit("visible CUDA device is not RTX 4090")
if not torch.cuda.is_bf16_supported(): raise SystemExit("BF16 unavailable")
print(name)
PY_CUDA
}

piston_preflight() {
  "$PY" - "$REPO_ROOT/configs/execution/piston-local.yaml" <<'PY_PISTON'
import sys
from pathlib import Path
from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config
print(PistonExecutor(load_piston_executor_config(Path(sys.argv[1]))).validate_runtime())
PY_PISTON
}

make_fraction_configs() {
  local fraction="$1" out="$2"
  mkdir -p "$out"
  "$PY" - "$PUBLIC_CONFIG" "$HIDDEN_CONFIG" "$fraction" "$out" <<'PY_CFG'
import sys, yaml
from pathlib import Path
pub, hid, fraction, out = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])
for src, name in ((pub,"public.yaml"),(hid,"hidden.yaml")):
    value=yaml.safe_load(src.read_text(encoding="utf-8"))
    value["vllm_gpu_memory_utilization"]=fraction
    target=out/name
    text=yaml.safe_dump(value, sort_keys=False)
    if target.exists() and target.read_text(encoding="utf-8") != text:
        raise SystemExit(f"existing generated config drift: {target}")
    target.write_text(text, encoding="utf-8")
PY_CFG
}

train_one() {
  local mode="$1" output_root="$2" public_name="$3" hidden_name="$4" pub_cfg="$5" hid_cfg="$6" log="$7"
  "$PY" -m torch.distributed.run \
    --standalone \
    --nnodes=1 \
    --nproc-per-node=1 \
    --max-restarts=0 \
    -m code_verifier.cli train-grpo \
    --public-config "$pub_cfg" \
    --hidden-config "$hid_cfg" \
    --dataset-dir "$POOL_DIR" \
    --public-run-name "$public_name" \
    --hidden-run-name "$hidden_name" \
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
    --output-dir "$output_root" >"$log" 2>&1
}

postcheck_grpo() {
  local run_dir="$1" mode="$2" fraction="$3"
  "$PY" - "$run_dir" "$mode" "$fraction" <<'PY_POST'
import json, math, sys
from pathlib import Path
from peft import PeftConfig
from code_verifier.training.grpo import load_completed_grpo_checkpoint
run=Path(sys.argv[1]); mode=sys.argv[2]; fraction=float(sys.argv[3])
identity=load_completed_grpo_checkpoint(run)
if identity.reward_mode != mode or identity.parent_sft.run_id != "B-sft-formal-seed42":
    raise SystemExit("completed GRPO identity drift")
meta=json.loads((run/"run.json").read_text(encoding="utf-8"))
if meta.get("status") != "completed" or meta.get("global_step") != 1:
    raise SystemExit("GRPO smoke did not complete exactly one optimizer step")
util=meta.get("runtime_utilization", {})
if util.get("status") != "available" or not util.get("sample_count"):
    raise SystemExit("GRPO runtime utilization telemetry unavailable")
resolved=(run/"resolved_config.yaml").read_text(encoding="utf-8")
for expected in ("num_generations: 8", "per_device_train_batch_size: 1", "gradient_accumulation_steps: 8"):
    if expected not in resolved: raise SystemExit("GRPO scientific batch semantics drift in resolved config")
if f"vllm_gpu_memory_utilization: {fraction}" not in resolved:
    raise SystemExit("resolved vLLM memory fraction drift")
rows=[json.loads(line) for line in (run/"metrics.jsonl").read_text(encoding="utf-8").splitlines() if line]
timing=[row for row in rows if "step_runtime_seconds" in row]
if len(timing) != 1: raise SystemExit("one-step GRPO must have exactly one timing row")
for field in ("vllm_generation_runtime_seconds","step_runtime_seconds","backward_runtime_total_seconds","backward_calls"):
    value=timing[0].get(field)
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)) or float(value)<0:
        raise SystemExit(f"GRPO timing field unavailable: {field}")
ckpt=run/"checkpoints/checkpoint-1"
if not ckpt.is_dir(): raise SystemExit("checkpoint-1 missing")
state=json.loads((ckpt/"trainer_state.json").read_text(encoding="utf-8"))
if state.get("global_step") != 1: raise SystemExit("checkpoint-1 trainer_state global_step drift")
adapter=PeftConfig.from_pretrained(str(ckpt), local_files_only=True)
if set(adapter.target_modules or ()) != {"q_proj","k_proj","v_proj","o_proj"}:
    raise SystemExit("checkpoint-1 PEFT adapter target_modules are not qkvo")
for required in ("adapter_model.safetensors","optimizer.pt","scheduler.pt","rng_state.pth","training_args.bin"):
    if not (ckpt/required).is_file(): raise SystemExit(f"checkpoint-1 missing {required}")
print(f"checkpoint_1_readback=ok mode={mode}")
PY_POST
}

start_pair_sampler() {
  local csv="$1" stop="$2"
  : >"$csv"; rm -f "$stop"
  (
    while [[ ! -e "$stop" ]]; do
      local_row="$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits --id="$GPU_INDEX" 2>/dev/null || true)"
      [[ -n "$local_row" ]] && printf '%s,%s\n' "$(date +%s.%N)" "$local_row" >>"$csv"
      sleep 1
    done
  ) &
  PAIR_SAMPLER_PID=$!
}

stop_pair_sampler() {
  local stop="$1"
  : >"$stop"
  wait "$PAIR_SAMPLER_PID" || true
}

classify_concurrent_result() {
  local result="$1" wall="$2" public_rc="$3" hidden_rc="$4" csv="$5" public_log="$6" hidden_log="$7" fraction="$8" handoff_commit="$9"
  "$PY" - "$result" "$wall" "$public_rc" "$hidden_rc" "$csv" "$public_log" "$hidden_log" "$fraction" "$handoff_commit" <<'PY_PAIR'
import json, math, re, sys
from pathlib import Path
out=Path(sys.argv[1]); wall=float(sys.argv[2]); prc=int(sys.argv[3]); hrc=int(sys.argv[4]); csv=Path(sys.argv[5])
text="\n".join(Path(p).read_text(encoding="utf-8", errors="replace") if Path(p).exists() else "" for p in sys.argv[6:8]).lower()
util=[]; mem=[]; total=[]
for line in csv.read_text(encoding="utf-8").splitlines() if csv.exists() else []:
    parts=[x.strip() for x in line.split(",")]
    if len(parts)==4:
        try: util.append(float(parts[1])); mem.append(float(parts[2])); total.append(float(parts[3]))
        except ValueError: pass
memory_pattern=r"out of memory|outofmemory|kv cache|gpu memory|vllm.*memory|memory.*vllm|free memory"
if prc==0 and hrc==0: reason="completed"
elif re.search(memory_pattern, text): reason="memory_pressure"
else: reason="other_failure"
peak=max(mem) if mem else None; gpu_total=max(total) if total else None
value={"schema_version":"wp9d-p1-concurrent-v1","result_path":str(out),"fraction":float(sys.argv[8]),
       "handoff_commit":sys.argv[9],"public_rc":prc,"hidden_rc":hrc,"wall_seconds":wall,"reason_class":reason,
       "gpu_utilization_mean_percent":sum(util)/len(util) if util else None,
       "gpu_utilization_p95_percent":sorted(util)[max(0, math.ceil(.95*len(util))-1)] if util else None,
       "gpu_memory_used_peak_mib":peak,"gpu_total_mib":gpu_total,
       "headroom_mib":(gpu_total-peak) if peak is not None and gpu_total is not None else None}
out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(value, sort_keys=True, indent=2)+"\n", encoding="utf-8")
print(json.dumps(value, sort_keys=True))
PY_PAIR
}

update_latest_concurrent() {
  local source="$1" tag="$2" target="$P1_ROOT/latest/concurrent-$tag.json"
  cp "$source" "$target.tmp"; mv "$target.tmp" "$target"
}

static_runtime_preflight
storage_preflight

if [[ "$PHASE" == "preflight" ]]; then
  grpo_input_preflight
  eval_input_preflight
  gpu_preflight
  piston_preflight
  COMMAND_RC=0; POSTCHECK_RC=0
  finalize_success preflight "$EVAL8_DIR/wp9d_p1_eval8_manifest.json" ""     "$EVAL8_DIR/wp9d_p1_eval8_manifest.json"
  echo "WP9-d P1 target preflight PASS; no training/generation launched"
  exit 0
fi

if [[ "$PHASE" == "report" ]]; then
  [[ -f "$EVAL8_DIR/wp9d_p1_eval8_manifest.json" ]] || { echo "eval8 systems subset is missing; report does not rebuild target data" >&2; exit 125; }
  START="$(now_ns)"
  set +e
  "$PY" "$REPO_ROOT/$REPORT_REL" --p1-root "$P1_ROOT" --eval8-dir "$EVAL8_DIR" >"$OP_ROOT/report-command.log" 2>&1
  COMMAND_RC=$?
  set -e
  END="$(now_ns)"
  [[ "$COMMAND_RC" -eq 0 ]] || exit "$COMMAND_RC"
  REPORT_JSON="$P1_ROOT/report/p1-runtime-report.json"
  set +e
  "$PY" - "$REPORT_JSON" <<'PY_REPORT_POST'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("schema_version") != "wp9d-p1-runtime-report-v1": raise SystemExit("P1 report schema drift")
if value.get("evidence_class") != "systems_validation_only": raise SystemExit("P1 report evidence class drift")
PY_REPORT_POST
  POSTCHECK_RC=$?
  set -e
  [[ "$POSTCHECK_RC" -eq 0 ]] || exit 3
  write_evidence passed "$REPORT_JSON" "$EVAL8_DIR/wp9d_p1_eval8_manifest.json"
  echo "P1 report PASS: $REPORT_JSON"
  exit 0
fi

if [[ "$PHASE" == "single" ]]; then
  grpo_input_preflight
  gpu_preflight
  piston_preflight
  MODE="$ARG"
  OUT="$P1_ROOT/single/$MODE$DIR_SUFFIX"
  RUN_ROOT="$OUT/grpo"
  RUN_NAME="wp9d-P1-$MODE-vllm-qkvo-smoke-seed42$RUN_SUFFIX"
  PUBLIC_NAME="wp9d-P1-public-vllm-qkvo-smoke-seed42$RUN_SUFFIX"
  HIDDEN_NAME="wp9d-P1-hidden-vllm-qkvo-smoke-seed42$RUN_SUFFIX"
  RUN_DIR="$RUN_ROOT/$RUN_NAME"
  [[ ! -e "$RUN_DIR" ]] || { echo "single-arm run exists; preserve it and use WP9D_P1_RETRY_TAG after repair" >&2; exit 125; }
  mkdir -p "$RUN_ROOT"
  START="$(now_ns)"
  set +e
  train_one "$MODE" "$RUN_ROOT" "$PUBLIC_NAME" "$HIDDEN_NAME" "$PUBLIC_CONFIG" "$HIDDEN_CONFIG" "$OUT/terminal.log"
  COMMAND_RC=$?
  set -e
  END="$(now_ns)"
  write_phase_meta "$OUT/phase-meta.json" "$START" "$END" "$COMMAND_RC" "single" "$MODE"
  if [[ "$COMMAND_RC" -ne 0 ]]; then
    failure_artifacts=("$OUT/phase-meta.json")
    [[ ! -f "$RUN_DIR/run.json" ]] || failure_artifacts+=("$RUN_DIR/run.json")
    write_evidence failed "${failure_artifacts[@]}"
    echo "single $MODE smoke failed; inspect minimal attempt before any retry" >&2
    exit "$COMMAND_RC"
  fi
  set +e
  postcheck_grpo "$RUN_DIR" "$MODE" "0.4"
  POSTCHECK_RC=$?
  set -e
  if [[ "$POSTCHECK_RC" -ne 0 ]]; then
    write_evidence failed "$OUT/phase-meta.json" "$RUN_DIR/run.json" "$RUN_DIR/metrics.jsonl"
    exit 3
  fi
  finalize_success "single-$MODE" "$RUN_DIR" "$OUT/phase-meta.json" \
    "$OUT/phase-meta.json" "$RUN_DIR/run.json" "$RUN_DIR/resolved_config.yaml" "$RUN_DIR/metrics.jsonl" \
    "$RUN_DIR/group_metrics.jsonl" "$RUN_DIR/checkpoints/checkpoint-1/adapter_config.json" \
    "$RUN_DIR/checkpoints/checkpoint-1/trainer_state.json" "$RUN_DIR/checkpoints/checkpoint-1/adapter_model.safetensors"
  echo "single $MODE P1 smoke PASS: $RUN_DIR"
  exit 0
fi

if [[ "$PHASE" == "concurrent" ]]; then
  grpo_input_preflight
  gpu_preflight
  piston_preflight
  for mode in public hidden; do
    check_accepted "single-$mode" single "$mode" >/dev/null 2>&1 || {
      echo "concurrent P1 requires accepted single-$mode smoke first" >&2; exit 125;
    }
  done
  FRACTION="$ARG"
  FRACTION_TAG="m${FRACTION/./}"
  OUT="$P1_ROOT/concurrent/$FRACTION_TAG$DIR_SUFFIX"
  RESULT="$OUT/concurrent-result.json"
  [[ ! -e "$RESULT" ]] || { echo "concurrent result exists; preserve it and use WP9D_P1_RETRY_TAG after repair" >&2; exit 125; }
  if [[ "$FRACTION" == "0.30" || "$FRACTION" == "0.25" ]]; then
    if [[ "$FRACTION" == "0.30" ]]; then PREV_TAG="m040"; else PREV_TAG="m030"; fi
    PREV="$P1_ROOT/latest/concurrent-$PREV_TAG.json"
    "$PY" - "$PREV" <<'PY_PREV'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
if not p.is_file(): raise SystemExit("previous memory-fraction result is required before lowering vLLM memory")
v=json.loads(p.read_text(encoding="utf-8")); reason=v.get("reason_class"); head=v.get("headroom_mib")
unsafe_completed=reason=="completed" and isinstance(head,(int,float)) and not isinstance(head,bool) and head < 1024
if reason != "memory_pressure" and not unsafe_completed:
    raise SystemExit("previous fraction does not justify lowering vLLM memory utilization")
PY_PREV
  fi
  mkdir -p "$OUT"
  CFG_DIR="$OUT/configs"
  make_fraction_configs "$FRACTION" "$CFG_DIR"
  PUB_OUT="$OUT/public"; HID_OUT="$OUT/hidden"
  PUB_ROOT="$PUB_OUT/grpo"; HID_ROOT="$HID_OUT/grpo"
  mkdir -p "$PUB_ROOT" "$HID_ROOT"
  PUB_NAME="wp9d-P1-public-vllm-qkvo-concurrent-$FRACTION_TAG-seed42$RUN_SUFFIX"
  HID_NAME="wp9d-P1-hidden-vllm-qkvo-concurrent-$FRACTION_TAG-seed42$RUN_SUFFIX"
  PUB_RUN="$PUB_ROOT/$PUB_NAME"; HID_RUN="$HID_ROOT/$HID_NAME"
  [[ ! -e "$PUB_RUN" && ! -e "$HID_RUN" ]] || { echo "concurrent arm run exists; preserve before retry" >&2; exit 125; }
  CSV="$OUT/gpu-pair-telemetry.csv"; STOP="$OUT/.gpu-sampler-stop"
  start_pair_sampler "$CSV" "$STOP"
  START="$(now_ns)"
  set +e
  train_one public "$PUB_ROOT" "$PUB_NAME" "$HID_NAME" "$CFG_DIR/public.yaml" "$CFG_DIR/hidden.yaml" "$PUB_OUT/terminal.log" & PUB_PID=$!
  train_one hidden "$HID_ROOT" "$PUB_NAME" "$HID_NAME" "$CFG_DIR/public.yaml" "$CFG_DIR/hidden.yaml" "$HID_OUT/terminal.log" & HID_PID=$!
  wait "$PUB_PID"; PUB_RC=$?
  wait "$HID_PID"; HID_RC=$?
  set -e
  END="$(now_ns)"
  stop_pair_sampler "$STOP"
  rm -f "$STOP"
  WALL="$($PY - "$START" "$END" <<'PY_WALL'
import sys
print((int(sys.argv[2])-int(sys.argv[1]))/1_000_000_000.0)
PY_WALL
)"
  classify_concurrent_result "$RESULT" "$WALL" "$PUB_RC" "$HID_RC" "$CSV" "$PUB_OUT/terminal.log" "$HID_OUT/terminal.log" "$FRACTION" "$EXPECTED_COMMIT" >/dev/null
  update_latest_concurrent "$RESULT" "$FRACTION_TAG"
  if [[ "$PUB_RC" -ne 0 || "$HID_RC" -ne 0 ]]; then
    COMMAND_RC=2
    write_evidence failed "$RESULT" "$CSV"
    echo "concurrent $FRACTION failed; classification recorded in $RESULT" >&2
    exit 2
  fi
  COMMAND_RC=0
  set +e
  postcheck_grpo "$PUB_RUN" public "$FRACTION"; PUB_POST=$?
  postcheck_grpo "$HID_RUN" hidden "$FRACTION"; HID_POST=$?
  set -e
  if [[ "$PUB_POST" -ne 0 || "$HID_POST" -ne 0 ]]; then
    POSTCHECK_RC=3
    write_evidence failed "$RESULT" "$CSV" "$PUB_RUN/run.json" "$HID_RUN/run.json"
    exit 3
  fi
  POSTCHECK_RC=0
  finalize_success "concurrent-$FRACTION_TAG" "$OUT" "" \
    "$RESULT" "$CSV" "$CFG_DIR/public.yaml" "$CFG_DIR/hidden.yaml" \
    "$PUB_RUN/run.json" "$PUB_RUN/metrics.jsonl" "$PUB_RUN/group_metrics.jsonl" \
    "$PUB_RUN/checkpoints/checkpoint-1/adapter_config.json" "$PUB_RUN/checkpoints/checkpoint-1/trainer_state.json" \
    "$HID_RUN/run.json" "$HID_RUN/metrics.jsonl" "$HID_RUN/group_metrics.jsonl" \
    "$HID_RUN/checkpoints/checkpoint-1/adapter_config.json" "$HID_RUN/checkpoints/checkpoint-1/trainer_state.json"
  echo "concurrent $FRACTION P1 smoke PASS: $RESULT"
  exit 0
fi

if [[ "$PHASE" == "eval" ]]; then
  eval_input_preflight
  gpu_preflight
  MODE="$ARG"
  if [[ "$MODE" == "single" ]]; then PARALLEL=1; else PARALLEL=2; fi
  OUT="$P1_ROOT/eval/$MODE$DIR_SUFFIX"
  RUN_NAME="wp9d-P1-b-eval8-b4-p${PARALLEL}-seed42$RUN_SUFFIX"
  RUN_DIR="$OUT/generation/$RUN_NAME"
  [[ ! -e "$RUN_DIR" ]] || { echo "eval P1 run exists; preserve it and use WP9D_P1_RETRY_TAG after repair" >&2; exit 125; }
  mkdir -p "$OUT"
  START="$(now_ns)"
  set +e
  "$PY" -m code_verifier.cli generate-eval \
    --config "$EVAL_CONFIG" \
    --dataset-dir "$EVAL8_DIR" \
    --sft-run-dir "$B_RUN" \
    --run-name "$RUN_NAME" \
    --batch-size 4 \
    --parallel-generators "$PARALLEL" \
    --seed 42 \
    --output-dir "$OUT" >"$OUT/terminal.log" 2>&1
  COMMAND_RC=$?
  set -e
  END="$(now_ns)"
  write_phase_meta "$OUT/phase-meta.json" "$START" "$END" "$COMMAND_RC" "eval" "$MODE"
  if [[ "$COMMAND_RC" -ne 0 ]]; then
    failure_artifacts=("$OUT/phase-meta.json")
    [[ ! -f "$RUN_DIR/run.json" ]] || failure_artifacts+=("$RUN_DIR/run.json")
    write_evidence failed "${failure_artifacts[@]}"
    echo "eval $MODE smoke failed" >&2
    exit "$COMMAND_RC"
  fi
  set +e
  "$PY" - "$RUN_DIR" "$PARALLEL" "$EVAL8_DIR/wp9d_p1_eval8_manifest.json" <<'PY_EVAL_POST'
import json, sys
from pathlib import Path
run=Path(sys.argv[1]); parallel=int(sys.argv[2]); manifest=json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
meta=json.loads((run/"run.json").read_text(encoding="utf-8"))
if meta.get("status") != "completed" or meta.get("completed_records") != 8 or meta.get("total_problems") != 8:
    raise SystemExit("eval8 generation count/status drift")
if meta.get("batch_size") != 4 or meta.get("parallel_generators") != parallel:
    raise SystemExit("eval8 generation topology drift")
rows=[json.loads(x) for x in (run/"samples/generations.jsonl").read_text(encoding="utf-8").splitlines() if x]
ids=[r["problem_id"] for r in rows]
if ids != manifest["problem_ids"]: raise SystemExit("persisted eval8 order differs from canonical input order")
util=meta.get("runtime_utilization", {})
if util.get("status") != "available" or not util.get("sample_count"):
    raise SystemExit("eval8 runtime utilization unavailable")
if parallel == 2 and meta.get("parallel_generators") != 2:
    raise SystemExit("dual eval did not persist two generators")
print(f"eval8_order_integrity=ok parallel={parallel}")
PY_EVAL_POST
  POSTCHECK_RC=$?
  set -e
  if [[ "$POSTCHECK_RC" -ne 0 ]]; then
    write_evidence failed "$OUT/phase-meta.json" "$RUN_DIR/run.json" "$RUN_DIR/samples/generations.jsonl"
    exit 3
  fi
  finalize_success "eval-$MODE" "$RUN_DIR" "$OUT/phase-meta.json" \
    "$OUT/phase-meta.json" "$RUN_DIR/run.json" "$RUN_DIR/environment.json" "$RUN_DIR/resolved_config.yaml" \
    "$RUN_DIR/samples/generations.jsonl" "$EVAL8_DIR/wp9d_p1_eval8_manifest.json"
  echo "eval $MODE P1 smoke PASS: $RUN_DIR"
  exit 0
fi

usage
