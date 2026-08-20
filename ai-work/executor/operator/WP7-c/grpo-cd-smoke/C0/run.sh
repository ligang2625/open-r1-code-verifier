#!/usr/bin/env bash
set -Eeuo pipefail
STAGE_ID="WP7-c"
GATE_ID="grpo-cd-smoke"
CHECKPOINT_ID="C0"
PLAN_COMMIT="8464e69691c527c726a2e28e5a7ca81fa2001bbf"
RESULT_CODE_COMMIT="66199d9434290394a55c5c15b0262ff8db322549"
B_RUN_NAME="B-sft-formal-seed42"
PUBLIC_RUN_NAME="C-public-grpo-smoke20-seed42"
HIDDEN_RUN_NAME="D-hidden-grpo-smoke20-seed42"
PUBLIC_CONFIG_REL="configs/grpo/validation-smoke-public.yaml"
HIDDEN_CONFIG_REL="configs/grpo/validation-smoke-hidden.yaml"
PISTON_CONFIG_REL="configs/execution/piston-local.yaml"
PLAN_REL="ai-work/planner/WP7-c-plan.md"
REPORT_REL="ai-work/executor/WP7-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP7-c/grpo-cd-smoke/C0/run.sh"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"

if [[ -n "${CODE_VERIFIER_VALIDATION_MACHINE:-}" ]]; then
  MACHINE_POINTER="$CODE_VERIFIER_VALIDATION_MACHINE"
else
  MACHINE_POINTER="$REPO_ROOT/.ai-bridge/validation-machine.json"
  if [[ ! -f "$MACHINE_POINTER" ]]; then
    COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"
    MACHINE_POINTER="$(dirname "$COMMON_DIR")/.ai-bridge/validation-machine.json"
  fi
fi
[[ -f "$MACHINE_POINTER" ]] || { echo "validation machine pointer not found: $MACHINE_POINTER" >&2; exit 125; }

MACHINE_FIELDS="$($PY - "$MACHINE_POINTER" <<'PY'
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
v = json.loads(p.read_text(encoding="utf-8"))
required = (
    "version", "machine_status", "bootstrap_project_commit", "open_r1_commit",
    "artifact_root", "hf_home", "formal_data_root", "readiness_record",
    "piston_identity_record", "piston_endpoint", "piston_host_id",
)
if not isinstance(v, dict) or any(k not in v for k in required):
    raise SystemExit("validation machine pointer schema is invalid")
if v["version"] != 1 or v["machine_status"] != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine pointer is not READY_FOR_VALIDATION_PLANNER")
for k in ("artifact_root", "hf_home", "formal_data_root", "readiness_record", "piston_identity_record"):
    if not isinstance(v[k], str) or not Path(v[k]).is_absolute():
        raise SystemExit(f"validation machine pointer {k} must be absolute")
for k in ("bootstrap_project_commit", "open_r1_commit", "piston_endpoint", "piston_host_id"):
    if not isinstance(v[k], str) or not v[k].strip():
        raise SystemExit(f"validation machine pointer {k} is invalid")
print("\t".join(str(v[k]) for k in required[2:]))
PY
)"
TAB="$(printf '\t')"
IFS="$TAB" read -r BOOTSTRAP_COMMIT MACHINE_OPEN_R1 ARTIFACT_ROOT TARGET_HF_HOME FORMAL_DATA_ROOT READINESS_RECORD PISTON_IDENTITY_RECORD PISTON_ENDPOINT PISTON_HOST_ID <<<"$MACHINE_FIELDS"

OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/$GATE_ID/$CHECKPOINT_ID"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
POSTCHECK_FILE="$OP_ROOT/postcheck-summary.json"
LOCK_FILE="$OP_ROOT/run.lock"
DATA_DIR="$FORMAL_DATA_ROOT/prepared"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
SMOKE_ROOT="$ARTIFACT_ROOT/grpo-validation/smoke"
PUBLIC_RUN="$SMOKE_ROOT/$PUBLIC_RUN_NAME"
HIDDEN_RUN="$SMOKE_ROOT/$HIDDEN_RUN_NAME"
TUNNEL_HELPER="$ARTIFACT_ROOT/machine/ensure-piston-1660ti-tunnel.sh"

mkdir -p "$OP_ROOT"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "operator lock is already held: $LOCK_FILE" >&2
  exit 73
fi
ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-${BASHPID}"
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
[[ ! -f "$STATUS_FILE" ]] || cp -a "$STATUS_FILE" "$OP_ROOT/status.before-$ATTEMPT_ID"
[[ ! -f "$EVIDENCE_FILE" ]] || cp -a "$EVIDENCE_FILE" "$OP_ROOT/operator-evidence.before-$ATTEMPT_ID.json"
rm -f "$STATUS_FILE.tmp" "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE.tmp"
printf '[%s] attempt=%s start checkpoint=%s gate=%s\n' "$START_TIME" "$ATTEMPT_ID" "$CHECKPOINT_ID" "$GATE_ID" >>"$LOG_FILE"

HEAD_COMMIT=""
SCRIPT_SHA=""
MACHINE_SHA="$(sha256sum "$MACHINE_POINTER" | awk '{print $1}')"
READINESS_SHA=""
PISTON_IDENTITY_SHA=""
GPU_NAME=""
GPU_VRAM_MIB="0"
EXPECTED_PAIR_SHA=""
CURRENT_OPEN_R1=""
CURRENT_LOCK_SHA=""
PLAN_PUBLIC_SHA=""
PLAN_HIDDEN_SHA=""
PLAN_PISTON_SHA=""
CURRENT_PHASE="preflight"

write_evidence() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$REPO_ROOT" "$MACHINE_POINTER" "$READINESS_RECORD" "$PISTON_IDENTITY_RECORD" \
    "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" "$HEAD_COMMIT" "$SCRIPT_SHA" "$MACHINE_SHA" "$READINESS_SHA" \
    "$PISTON_IDENTITY_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" "$PISTON_ENDPOINT" "$PISTON_HOST_ID" "$EXPECTED_PAIR_SHA" \
    "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$PLAN_PISTON_SHA" "$command_rc" "$postcheck_rc" "$gate_status" "$note" \
    "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY'
import hashlib
import json
import sys
from pathlib import Path
(
    output, postcheck_path, repo_root, machine_pointer, readiness_record, piston_identity_record,
    artifact_root, hf_home, formal_data_root, checkpoint_commit, script_sha, machine_sha, readiness_sha,
    piston_identity_sha, gpu_name, gpu_vram_mib, piston_endpoint, piston_host_id, pair_sha, open_r1_commit,
    dependency_lock_sha, piston_definition_sha, command_rc, postcheck_rc, gate_status, note, start_time,
    end_time, attempt_id,
) = sys.argv[1:]

def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inventory(path: Path, with_digest: bool) -> dict[str, object]:
    out: dict[str, object] = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        out["size_bytes"] = path.stat().st_size
        if with_digest:
            out["sha256"] = digest(path)
    return out

postcheck = None
p = Path(postcheck_path)
if p.is_file():
    v = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(v, dict):
        postcheck = v
smoke = Path(artifact_root) / "grpo-validation" / "smoke"
files = []
for run_name in ("C-public-grpo-smoke20-seed42", "D-hidden-grpo-smoke20-seed42"):
    run = smoke / run_name
    for name, with_digest in (
        ("run.json", True), ("resolved_config.yaml", True), ("environment.json", True),
        ("metrics.jsonl", True), ("rollouts.jsonl", False), ("rewards.jsonl", True),
        ("group_metrics.jsonl", True), ("checkpoints/adapter_config.json", True),
        ("checkpoints/adapter_model.safetensors", False),
    ):
        files.append(inventory(run / name, with_digest))
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP7-c",
    "source_plan_commit": "8464e69691c527c726a2e28e5a7ca81fa2001bbf",
    "operator_checkpoint_commit": checkpoint_commit or None,
    "result_code_commit": "66199d9434290394a55c5c15b0262ff8db322549",
    "checkpoint_id": "C0",
    "operator_gate_id": "grpo-cd-smoke",
    "operator_script": "ai-work/executor/operator/WP7-c/grpo-cd-smoke/C0/run.sh",
    "operator_script_sha256": script_sha or None,
    "target_machine_pointer": machine_pointer,
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record": readiness_record,
    "target_readiness_record_sha256": readiness_sha or None,
    "piston_identity_record": piston_identity_record,
    "piston_identity_record_sha256": piston_identity_sha or None,
    "gpu_name": gpu_name or None,
    "gpu_vram_mib": int(gpu_vram_mib or 0),
    "resolved_roots": {"repo_root": repo_root, "artifact_root": artifact_root, "hf_home": hf_home, "formal_data_root": formal_data_root},
    "runtime_identity": {"open_r1_commit": open_r1_commit or None, "dependency_lock_sha256": dependency_lock_sha or None},
    "piston": {"endpoint": piston_endpoint, "host_id": piston_host_id, "definition_sha256": piston_definition_sha or None, "python_runtime": "3.10.0"},
    "formal_pair": {"public_run_name": "C-public-grpo-smoke20-seed42", "hidden_run_name": "D-hidden-grpo-smoke20-seed42", "seed": 42, "paired_definition_sha256": pair_sha or None, "parent_b_run_name": "B-sft-formal-seed42"},
    "attempt_id": attempt_id,
    "start_time": start_time,
    "end_time": end_time,
    "command_rc": int(command_rc),
    "postcheck_rc": int(postcheck_rc),
    "gate_status": gate_status,
    "note": note,
    "postcheck": postcheck,
    "expected_artifact_inventory": files,
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  local final_rc=1
  if [[ "$gate_status" == "passed" && "$command_rc" == "0" && "$postcheck_rc" == "0" ]]; then
    final_rc=0
  elif [[ "$command_rc" =~ ^[0-9]+$ ]] && (( command_rc > 0 && command_rc < 126 )); then
    final_rc="$command_rc"
  fi
  printf '%s\n' "$final_rc" >"$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  printf '[%s] attempt=%s end phase=%s command_rc=%s postcheck_rc=%s gate_status=%s note=%s\n' "$end_time" "$ATTEMPT_ID" "$CURRENT_PHASE" "$command_rc" "$postcheck_rc" "$gate_status" "$note" >>"$LOG_FILE"
  return "$final_rc"
}

fail_preflight() {
  local message="$1"
  printf '[%s] preflight FAIL: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$message" >>"$LOG_FILE"
  write_evidence 125 125 preflight_failed "$message"
  exit $?
}

on_interrupt() {
  local rc="$1"
  trap - INT TERM
  printf '[%s] interrupted phase=%s rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$CURRENT_PHASE" "$rc" >>"$LOG_FILE"
  write_evidence "$rc" 125 interrupted "operator interrupted during $CURRENT_PHASE"
  exit "$rc"
}
trap 'on_interrupt 130' INT
trap 'on_interrupt 143' TERM

[[ -x "$PY" ]] || fail_preflight "stage .venv python is unavailable"
[[ -x "$CV" ]] || fail_preflight "stage .venv code-verifier is unavailable"
[[ -f "$REPO_ROOT/$SCRIPT_REL" && -f "$REPO_ROOT/$REPORT_REL" && -f "$REPO_ROOT/$PLAN_REL" ]] || fail_preflight "tracked checkpoint files are unavailable"
HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve checkpoint HEAD"
PARENT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve checkpoint parent"
[[ "$PARENT_COMMIT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "checkpoint parent does not equal result_code_commit"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge contains tracked paths"
git -C "$REPO_ROOT" diff --quiet "$PLAN_COMMIT" HEAD -- "$PLAN_REL" || fail_preflight "sealed plan differs from source_plan_commit"
git -C "$REPO_ROOT" merge-base --is-ancestor "$BOOTSTRAP_COMMIT" HEAD || fail_preflight "bootstrap project commit is not an ancestor of checkpoint HEAD"

mapfile -t CHECKPOINT_DIFF < <(git -C "$REPO_ROOT" diff --name-only "$PARENT_COMMIT" "$HEAD_COMMIT")
[[ "${#CHECKPOINT_DIFF[@]}" -eq 2 ]] || fail_preflight "checkpoint commit must contain exactly report plus one script"
printf '%s\n' "${CHECKPOINT_DIFF[@]}" | grep -Fxq "$REPORT_REL" || fail_preflight "checkpoint commit does not contain execution report"
printf '%s\n' "${CHECKPOINT_DIFF[@]}" | grep -Fxq "$SCRIPT_REL" || fail_preflight "checkpoint commit does not contain tracked C0 script"

CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" "$CHECKPOINT_ID" <<'PY'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind(f"checkpoint_id: {sys.argv[2]}")
if pos < 0:
    raise SystemExit(2)
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit(2)
block = text[start:end]
def field(name: str) -> str:
    m = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not m:
        raise SystemExit(2)
    return m.group(1).strip().strip('"').strip("'")
print("\t".join([field("operator_script_sha256"), field("operator_handoff_mode"), field("operator_gate_id"), field("result_code_commit"), field("source_plan_commit")]))
PY
)" || fail_preflight "cannot parse C0 checkpoint provenance"
TAB="$(printf '\t')"
IFS="$TAB" read -r EXPECTED_SCRIPT_SHA CHECKPOINT_MODE CHECKPOINT_GATE CHECKPOINT_RESULT CHECKPOINT_PLAN <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_GATE" == "$GATE_ID" ]] || fail_preflight "checkpoint handoff/gate mismatch"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" && "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" ]] || fail_preflight "checkpoint source provenance mismatch"
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked operator script SHA mismatch"

PLAN_FIELDS="$($PY - "$REPO_ROOT/$PLAN_REL" <<'PY'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
def one(pattern: str, name: str) -> str:
    m = re.search(pattern, text)
    if not m:
        raise SystemExit(f"cannot parse sealed plan field: {name}")
    return m.group(1)
public_sha = one(r"formal `public_grpo\.jsonl`[^\n]*SHA256 `([0-9a-f]{64})`", "public data SHA")
hidden_sha = one(r"formal `hidden_grpo\.jsonl`[^\n]*SHA256 `([0-9a-f]{64})`", "hidden data SHA")
b = re.search(r"run `B-sft-formal-seed42`[^\n]*model `([^`]+)@([0-9a-f]{40})`[^\n]*dataset hash `([0-9a-f]{64})`[^\n]*config hash `([0-9a-f]{64})`[^\n]*dependency lock hash `([0-9a-f]{64})`", text)
if not b:
    raise SystemExit("cannot parse sealed formal B identity")
piston_sha = one(r"Piston definition SHA256 `([0-9a-f]{64})`", "Piston SHA")
print("\t".join([public_sha, hidden_sha, *b.groups(), piston_sha]))
PY
)" || fail_preflight "cannot parse sealed plan identities"
IFS="$TAB" read -r PLAN_PUBLIC_SHA PLAN_HIDDEN_SHA PLAN_MODEL_ID PLAN_MODEL_REVISION PLAN_B_DATASET_SHA PLAN_B_CONFIG_SHA PLAN_B_LOCK_SHA PLAN_PISTON_SHA <<<"$PLAN_FIELDS"

[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -d "$DATA_DIR" ]] || fail_preflight "target persistent roots are unavailable"
[[ -f "$READINESS_RECORD" && -f "$PISTON_IDENTITY_RECORD" ]] || fail_preflight "target readiness/Piston records are unavailable"
READINESS_SHA="$(sha256sum "$READINESS_RECORD" | awk '{print $1}')"
PISTON_IDENTITY_SHA="$(sha256sum "$PISTON_IDENTITY_RECORD" | awk '{print $1}')"
if ! "$PY" - "$READINESS_RECORD" "$PISTON_IDENTITY_RECORD" "$PISTON_ENDPOINT" "$PISTON_HOST_ID" <<'PY'
import json
import sys
from pathlib import Path
readiness = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
piston = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
endpoint, host_id = sys.argv[3:]
def ready(v: object) -> bool:
    if isinstance(v, str):
        return v == "READY_FOR_VALIDATION_PLANNER"
    if isinstance(v, dict):
        return any(ready(x) for x in v.values())
    if isinstance(v, list):
        return any(ready(x) for x in v)
    return False
if not ready(readiness):
    raise SystemExit("readiness record is not READY_FOR_VALIDATION_PLANNER")
expected = {"deployment_mode": "ssh_tunneled_remote", "endpoint": endpoint, "python_runtime": "3.10.0", "piston_host_id": host_id, "real_piston_acceptance": "PASS"}
if not isinstance(piston, dict) or any(piston.get(k) != v for k, v in expected.items()):
    raise SystemExit("Piston identity record mismatch")
if endpoint != "http://127.0.0.1:2000" or host_id != "1660ti-wsl":
    raise SystemExit("canonical Piston topology mismatch")
PY
then
  fail_preflight "target readiness/Piston identity validation failed"
fi

RUNTIME_FIELDS="$($PY - "$REPO_ROOT" "$MACHINE_OPEN_R1" "$PLAN_B_LOCK_SHA" <<'PY'
import inspect
import sys
from importlib import metadata
from pathlib import Path
import code_verifier
import open_r1
from code_verifier.environment import collect_environment
from code_verifier.training.grpo import _load_grpo_runtime
root = Path(sys.argv[1]).resolve()
for module, name in ((code_verifier, "code_verifier"), (open_r1, "open_r1")):
    module_file = getattr(module, "__file__", None)
    if module_file is None or root not in Path(module_file).resolve().parents:
        raise SystemExit(f"{name} does not resolve inside target checkout")
for dist, expected in {"trl":"0.18.0","transformers":"4.52.3","accelerate":"1.4.0","peft":"0.14.0"}.items():
    if metadata.version(dist) != expected:
        raise SystemExit(f"pinned package mismatch: {dist}")
env = collect_environment()
if env.get("open_r1_commit") != sys.argv[2]:
    raise SystemExit("Open-R1 commit differs from machine pointer")
if env.get("dependency_lock_hash") != sys.argv[3]:
    raise SystemExit("dependency lock differs from sealed B identity")
runtime = _load_grpo_runtime()
params = inspect.signature(runtime.training_config_type.__init__).parameters
for name in ("skip_memory_metrics", "logging_nan_inf_filter", "save_total_limit", "save_only_model"):
    if name not in params:
        raise SystemExit(f"GRPOConfig missing telemetry field: {name}")
print(f"{env['open_r1_commit']}\t{env['dependency_lock_hash']}")
PY
)" || fail_preflight "stage .venv/runtime identity validation failed"
IFS="$TAB" read -r CURRENT_OPEN_R1 CURRENT_LOCK_SHA <<<"$RUNTIME_FIELDS"

GPU_INDEX="$(nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$1); gsub(/ /,"",$3); if ($3+0 >= 22528) {print $1; exit}}')"
[[ -n "$GPU_INDEX" ]] || fail_preflight "no RTX 4090 with at least 22528 MiB VRAM detected"
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
GPU_FIELDS="$($PY - <<'PY'
import torch
if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise SystemExit("operator requires exactly one visible CUDA device")
p = torch.cuda.get_device_properties(0)
name = p.name
mib = int(p.total_memory // (1024 * 1024))
if "RTX 4090" not in name or mib < 22528:
    raise SystemExit("visible GPU is not RTX 4090 class")
if not bool(torch.cuda.is_bf16_supported(including_emulation=False)):
    raise SystemExit("native BF16 is unavailable")
print(f"{name}\t{mib}")
PY
)" || fail_preflight "CUDA/BF16 target validation failed"
IFS="$TAB" read -r GPU_NAME GPU_VRAM_MIB <<<"$GPU_FIELDS"

export HF_HOME="$TARGET_HF_HOME"
export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
if ! "$PY" - "$PLAN_MODEL_ID" "$PLAN_MODEL_REVISION" <<'PY'
import sys
from pathlib import Path
from huggingface_hub import snapshot_download
p = Path(snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_files_only=True)).resolve()
if not p.is_dir():
    raise SystemExit("exact model snapshot is not available local-only")
print(p)
PY
then
  fail_preflight "exact 1.5B model revision is not available local-only"
fi

if ! "$CV" check-data --dataset "$DATA_DIR" >>"$LOG_FILE" 2>&1; then
  fail_preflight "formal data check-data failed"
fi
PAIR_FIELDS="$($PY - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" "$PLAN_PUBLIC_SHA" "$PLAN_HIDDEN_SHA" "$PLAN_MODEL_ID" "$PLAN_MODEL_REVISION" "$PLAN_B_DATASET_SHA" "$PLAN_B_CONFIG_SHA" "$PLAN_B_LOCK_SHA" <<'PY'
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.data.leakage_checks import TrainingArtifactKind
from code_verifier.training import load_completed_sft_checkpoint
from code_verifier.training.grpo import _paired_definition, load_grpo_training_config, load_training_artifact, validate_grpo_artifact_pair, validate_grpo_config_pair
repo, data_dir, b_run = map(Path, sys.argv[1:4])
public_sha, hidden_sha, model_id, revision, b_dataset, b_config, b_lock = sys.argv[4:]
pub_path = data_dir / "training" / "public_grpo.jsonl"
hid_path = data_dir / "training" / "hidden_grpo.jsonl"
if hashlib.sha256(pub_path.read_bytes()).hexdigest() != public_sha:
    raise SystemExit("formal Public GRPO dataset SHA mismatch")
if hashlib.sha256(hid_path.read_bytes()).hexdigest() != hidden_sha:
    raise SystemExit("formal Hidden GRPO dataset SHA mismatch")
pub_rows = load_training_artifact(pub_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
hid_rows = load_training_artifact(hid_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
if len(pub_rows) != 2500 or len(hid_rows) != 2500:
    raise SystemExit("formal GRPO row count mismatch")
validate_grpo_artifact_pair(pub_rows, hid_rows)
parent = load_completed_sft_checkpoint(b_run)
expected = {"run_id":"B-sft-formal-seed42","model_id":model_id,"model_revision":revision,"dataset_hash":b_dataset,"config_hash":b_config,"dependency_lock_hash":b_lock,"seed":42}
for k, v in expected.items():
    if getattr(parent, k) != v:
        raise SystemExit(f"formal B identity mismatch: {k}")
pub = replace(load_grpo_training_config(repo / "configs/grpo/validation-smoke-public.yaml"), dataset_path=pub_path, run_name="C-public-grpo-smoke20-seed42")
hid = replace(load_grpo_training_config(repo / "configs/grpo/validation-smoke-hidden.yaml"), dataset_path=hid_path, run_name="D-hidden-grpo-smoke20-seed42")
validate_grpo_config_pair(pub, hid)
if (pub.max_steps, hid.max_steps, pub.save_steps, hid.save_steps) != (20, 20, 10, 10):
    raise SystemExit("smoke phase contract mismatch")
pair_sha, components = _paired_definition(pub, hid, seed=42, parent_sft=parent)
print(f"{pair_sha}\t{json.dumps(components, sort_keys=True, separators=(',', ':'))}")
PY
)" || fail_preflight "formal C/D pair or B identity validation failed"
IFS="$TAB" read -r EXPECTED_PAIR_SHA PAIR_COMPONENTS_JSON <<<"$PAIR_FIELDS"
[[ "$EXPECTED_PAIR_SHA" =~ ^[0-9a-f]{64}$ ]] || fail_preflight "computed paired definition SHA is invalid"

[[ "$(sha256sum "$REPO_ROOT/$PISTON_CONFIG_REL" | awk '{print $1}')" == "$PLAN_PISTON_SHA" ]] || fail_preflight "tracked Piston definition SHA differs from sealed plan"
[[ -x "$TUNNEL_HELPER" ]] || fail_preflight "1660ti-wsl Piston tunnel helper is unavailable"
if ! "$TUNNEL_HELPER" >>"$LOG_FILE" 2>&1; then
  fail_preflight "1660ti-wsl Piston tunnel helper failed"
fi
if ! "$PY" - "$REPO_ROOT/$PISTON_CONFIG_REL" <<'PY'
import sys
from pathlib import Path
from code_verifier.execution import PistonExecutor, load_piston_executor_config
executor = PistonExecutor(load_piston_executor_config(Path(sys.argv[1])))
if executor.validate_runtime() != "3.10.0":
    raise SystemExit("Piston Python runtime mismatch")
PY
then
  fail_preflight "loopback Piston runtime validation failed"
fi

if ! "$PY" - "$ARTIFACT_ROOT" <<'PY'
import os
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1])
usage = shutil.disk_usage(root)
free_inodes = os.statvfs(root).f_favail
if usage.free < 20 * 1024**3:
    raise SystemExit("less than 20 GiB free")
if free_inodes < 100000:
    raise SystemExit("fewer than 100000 free inodes")
print(f"free_bytes={usage.free} free_inodes={free_inodes}")
PY
then
  fail_preflight "operator-start storage gate failed"
fi
printf '[%s] preflight PASS: checkpoint/machine/GPU/runtime/data/B/pair/Piston/storage identities\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"

resolve_run_action() {
  local mode="$1" run_dir="$2"
  "$PY" - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" "$run_dir" "$mode" "$HEAD_COMMIT" "$EXPECTED_PAIR_SHA" <<'PY'
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.environment import collect_environment
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint
from code_verifier.training.grpo import _config_hash, _file_hash, _paired_definition, _resolve_resume_checkpoint, _validate_resume_run, load_grpo_training_config
repo, data_dir, b_run, run_dir = map(Path, sys.argv[1:5])
mode, head, expected_pair = sys.argv[5:8]
pub = replace(load_grpo_training_config(repo / "configs/grpo/validation-smoke-public.yaml"), dataset_path=data_dir / "training/public_grpo.jsonl", run_name="C-public-grpo-smoke20-seed42")
hid = replace(load_grpo_training_config(repo / "configs/grpo/validation-smoke-hidden.yaml"), dataset_path=data_dir / "training/hidden_grpo.jsonl", run_name="D-hidden-grpo-smoke20-seed42")
config = pub if mode == "public" else hid
parent = load_completed_sft_checkpoint(b_run)
pair_sha, components = _paired_definition(pub, hid, seed=42, parent_sft=parent)
if pair_sha != expected_pair:
    raise SystemExit("pair SHA changed after preflight")
if not run_dir.exists():
    print("fresh")
    raise SystemExit(0)
if not run_dir.is_dir() or not (run_dir / "run.json").is_file():
    raise SystemExit("existing run path is invalid")
metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
if metadata.get("git_commit") != head:
    raise SystemExit("existing run belongs to a different checkpoint commit")
if metadata.get("status") == "completed":
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.run_id != config.run_name or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != expected_pair:
        raise SystemExit("completed run identity mismatch")
    print("completed")
    raise SystemExit(0)
if metadata.get("status") not in {"running", "failed"}:
    raise SystemExit("existing run status is not resumable")
root = run_dir / "checkpoints"
valid = []
required = {"adapter_config.json", "adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth", "trainer_state.json", "training_args.bin"}
for path in root.glob("checkpoint-*"):
    match = re.fullmatch(r"checkpoint-(\d+)", path.name)
    if not match or not path.is_dir() or not all((path / name).is_file() for name in required):
        continue
    step = int(match.group(1))
    state = json.loads((path / "trainer_state.json").read_text(encoding="utf-8"))
    if state.get("global_step") == step:
        valid.append((step, path))
if not valid:
    raise SystemExit("incomplete run has no valid Trainer checkpoint; quarantine is required")
_, selected = max(valid)
resolved, source = _resolve_resume_checkpoint(run_dir, selected)
_validate_resume_run(
    run_dir=run_dir,
    config=config,
    seed=42,
    parent_sft=parent,
    dataset_hash=_file_hash(config.dataset_path, description="GRPO dataset"),
    config_hash=_config_hash(config, seed=42),
    paired_definition_sha256=expected_pair,
    paired_components=components,
    environment=collect_environment(),
    resume_source=source,
)
print(f"resume:{resolved}")
PY
}

run_one() {
  local mode="$1" run_name="$2" run_dir="$3" action
  action="$(resolve_run_action "$mode" "$run_dir")" || {
    write_evidence 125 125 identity_failed "$mode run is not safely fresh/resumable/completed"
    exit $?
  }
  if [[ "$action" == "completed" ]]; then
    printf '[%s] %s smoke already completed; command skipped\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
    return 0
  fi
  local resume_args=()
  if [[ "$action" == resume:* ]]; then
    resume_args=(--resume-from-checkpoint "${action#resume:}")
    printf '[%s] %s smoke resume=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "${action#resume:}" >>"$LOG_FILE"
  else
    printf '[%s] %s smoke fresh run=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "$run_name" >>"$LOG_FILE"
  fi
  CURRENT_PHASE="train-$mode"
  if "$CV" train-grpo \
      --public-config "$REPO_ROOT/$PUBLIC_CONFIG_REL" \
      --hidden-config "$REPO_ROOT/$HIDDEN_CONFIG_REL" \
      --dataset-dir "$DATA_DIR" \
      --public-run-name "$PUBLIC_RUN_NAME" \
      --hidden-run-name "$HIDDEN_RUN_NAME" \
      --public-sft-run-dir "$B_RUN" \
      --hidden-sft-run-dir "$B_RUN" \
      --reward-mode "$mode" \
      --seed 42 \
      --output-dir "$SMOKE_ROOT" \
      "${resume_args[@]}" > >(tee -a "$LOG_FILE") 2>&1; then
    printf '[%s] %s smoke command rc=0\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
  else
    local rc=$?
    write_evidence "$rc" 125 command_failed "$mode smoke train-grpo exited nonzero"
    exit $?
  fi
}

mkdir -p "$SMOKE_ROOT"
run_one public "$PUBLIC_RUN_NAME" "$PUBLIC_RUN"
run_one hidden "$HIDDEN_RUN_NAME" "$HIDDEN_RUN"

CURRENT_PHASE="postcheck"
if "$PY" - "$PUBLIC_RUN" "$HIDDEN_RUN" "$B_RUN" "$HEAD_COMMIT" "$EXPECTED_PAIR_SHA" "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$POSTCHECK_FILE.tmp" <<'PY'
import json
import math
import sys
from pathlib import Path
from code_verifier.analysis import build_cost_row, load_training_curve_rows
from code_verifier.analysis.report import _REWARD_FIELDS, _ROLLOUT_FIELDS
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint

public_run, hidden_run, b_run = map(Path, sys.argv[1:4])
head, pair_sha, open_r1, lock_sha, output = sys.argv[4:9]
parent = load_completed_sft_checkpoint(b_run)
forbidden = ('"prompt"', '"visible_tests"', '"train_hidden_tests"', '"eval_hidden_tests"', '"reference_solution"', '"starter_code"', '"sft_response"')

def load_rows(path: Path) -> list[dict[str, object]]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise SystemExit(f"blank JSONL row: {path.name}")
        value = json.loads(line, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
        if not isinstance(value, dict):
            raise SystemExit(f"non-object JSONL row: {path.name}")
        result.append(value)
    return result

def require_finite(value: object, context: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise SystemExit(f"nonfinite value: {context}")
        return
    if isinstance(value, list):
        for item in value:
            require_finite(item, context)
        return
    if isinstance(value, dict):
        for item in value.values():
            require_finite(item, context)
        return
    raise SystemExit(f"unsupported persisted value: {context}")

def checkpoint_inventory(run_dir: Path) -> dict[str, object]:
    required = {"adapter_config.json", "adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth", "trainer_state.json", "training_args.bin"}
    inventory = []
    for step in (10, 20):
        path = run_dir / "checkpoints" / f"checkpoint-{step}"
        if not path.is_dir() or not all((path / name).is_file() for name in required):
            raise SystemExit(f"missing complete checkpoint-{step}")
        state = json.loads((path / "trainer_state.json").read_text(encoding="utf-8"))
        if state.get("global_step") != step:
            raise SystemExit(f"checkpoint-{step} global_step mismatch")
        files = [item for item in path.rglob("*") if item.is_file()]
        inventory.append({"step": step, "bytes": sum(item.stat().st_size for item in files), "files": len(files)})
    return {"checkpoints": inventory, "max_checkpoint_bytes": max(item["bytes"] for item in inventory), "max_checkpoint_files": max(item["files"] for item in inventory)}

def check_run(run_dir: Path, mode: str, run_id: str) -> dict[str, object]:
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.run_id != run_id or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != pair_sha:
        raise SystemExit(f"{mode} strict identity mismatch")
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    expected = {
        "status": "completed", "run_id": run_id, "reward_mode": mode,
        "paired_definition_sha256": pair_sha, "seed": 42, "git_commit": head,
        "open_r1_commit": open_r1, "dependency_lock_hash": lock_sha,
        "gpu_count_used": 1, "global_step": 20,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise SystemExit(f"{mode} metadata mismatch: {key}")
    attempts = metadata.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise SystemExit(f"{mode} attempts missing")
    attempt_total = 0.0
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict) or attempt.get("attempt") != index or attempt.get("status") not in {"failed", "completed"}:
            raise SystemExit(f"{mode} attempt schema invalid")
        hours = attempt.get("gpu_hours")
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(float(hours)) or hours < 0:
            raise SystemExit(f"{mode} attempt gpu_hours invalid")
        attempt_total += float(hours)
    gpu_hours = metadata.get("gpu_hours")
    if attempts[-1].get("status") != "completed" or isinstance(gpu_hours, bool) or not isinstance(gpu_hours, (int, float)):
        raise SystemExit(f"{mode} cumulative gpu_hours invalid")
    if not math.isfinite(float(gpu_hours)) or float(gpu_hours) <= 0 or not math.isclose(float(gpu_hours), attempt_total, rel_tol=0.0, abs_tol=1e-12):
        raise SystemExit(f"{mode} cumulative gpu_hours is not recomputable")
    for key in ("peak_cuda_memory_allocated_bytes", "peak_cuda_memory_reserved_bytes"):
        if isinstance(metadata.get(key), bool) or not isinstance(metadata.get(key), int) or metadata[key] <= 0:
            raise SystemExit(f"{mode} {key} invalid")

    metrics = load_rows(run_dir / "metrics.jsonl")
    require_finite(metrics, f"{mode} metrics")
    trainer_rows = [row for row in metrics if row.get("record_type") == "trainer"]
    if not trainer_rows or metrics[-1].get("record_type") != "summary" or metrics[-1].get("global_step") != 20:
        raise SystemExit(f"{mode} metrics incomplete")
    rollouts = load_rows(run_dir / "rollouts.jsonl")
    rewards = load_rows(run_dir / "rewards.jsonl")
    groups = load_rows(run_dir / "group_metrics.jsonl")
    if not rollouts or not rewards or not groups:
        raise SystemExit(f"{mode} reward evidence empty")
    if any(set(row) != _ROLLOUT_FIELDS or row.get("reward_mode") != mode for row in rollouts):
        raise SystemExit(f"{mode} rollout schema/source mismatch")
    if any(set(row) != _REWARD_FIELDS or row.get("mode") != mode for row in rewards):
        raise SystemExit(f"{mode} reward schema/source mismatch")
    if any(row.get("reward_mode") != mode for row in groups):
        raise SystemExit(f"{mode} group source mismatch")
    require_finite(rewards, f"{mode} rewards")
    require_finite(groups, f"{mode} groups")

    for name in ("run.json", "resolved_config.yaml", "environment.json", "metrics.jsonl", "rewards.jsonl", "group_metrics.jsonl", "stdout.log", "stderr.log"):
        text = (run_dir / name).read_text(encoding="utf-8")
        if any(marker in text for marker in forbidden):
            raise SystemExit(f"{mode} forbidden payload marker in {name}")
    if any(any(key in row for key in ("prompt", "visible_tests", "train_hidden_tests", "eval_hidden_tests")) for row in rollouts):
        raise SystemExit(f"{mode} rollout contains forbidden payload")

    curve = load_training_curve_rows(run_dir, method=f"{mode}-smoke")
    cost = build_cost_row(run_dir, method=f"{mode}-smoke", gpu_hour_cost_usd=None)
    if not curve or not math.isfinite(cost.gpu_hours) or cost.gpu_hours <= 0:
        raise SystemExit(f"{mode} curve/cost loader failed")
    return {
        "run_id": run_id, "reward_mode": mode, "paired_definition_sha256": pair_sha,
        "parent_sft_run_id": identity.parent_sft.run_id, "global_step": 20,
        "gpu_hours": float(gpu_hours), "attempt_count": len(attempts),
        "peak_cuda_memory_allocated_bytes": metadata["peak_cuda_memory_allocated_bytes"],
        "peak_cuda_memory_reserved_bytes": metadata["peak_cuda_memory_reserved_bytes"],
        "trainer_metric_rows": len(trainer_rows), "curve_rows": len(curve),
        "rollout_rows": len(rollouts), "reward_rows": len(rewards), "group_rows": len(groups),
        "executor_hours": cost.executor_hours,
        **checkpoint_inventory(run_dir),
    }

public = check_run(public_run, "public", "C-public-grpo-smoke20-seed42")
hidden = check_run(hidden_run, "hidden", "D-hidden-grpo-smoke20-seed42")
summary = {
    "version": 1, "status": "passed", "paired_definition_sha256": pair_sha,
    "public": public, "hidden": hidden,
    "max_complete_trainer_checkpoint_bytes": max(public["max_checkpoint_bytes"], hidden["max_checkpoint_bytes"]),
    "max_complete_trainer_checkpoint_files": max(public["max_checkpoint_files"], hidden["max_checkpoint_files"]),
}
Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY
then
  mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"
else
  rc=$?
  rm -f "$POSTCHECK_FILE.tmp"
  write_evidence 0 "$rc" postcheck_failed "paired smoke postcheck failed"
  exit $?
fi

CURRENT_PHASE="complete"
write_evidence 0 0 passed "paired 20-step C/D smoke and sealed postcheck passed; pilot was not started"
exit $?
