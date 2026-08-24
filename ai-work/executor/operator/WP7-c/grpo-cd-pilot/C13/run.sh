#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP7-c"
GATE_ID="grpo-cd-pilot"
CHECKPOINT_ID="C13"
PLAN_COMMIT="8464e69691c527c726a2e28e5a7ca81fa2001bbf"
C12_CHECKPOINT_COMMIT="355486ccccff3a1325614e18e8f8d4a85b8789ba"
C12_SCRIPT_SHA="ba838037596a3e0ba9a0d1102075174de36998156d0b3766df62c3b7550afd44"
EXPECTED_PILOT_PAIR_SHA="bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f"
EXPECTED_PUBLIC_PAIR_CONFIG_SHA="da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac"
EXPECTED_HIDDEN_PAIR_CONFIG_SHA="5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658"
EXPECTED_MACHINE_SHA="b2230476c3d7600477108db5684ba2efbef95b89f746b8d8a1bc83b88ba5cab7"
EXPECTED_READINESS_SHA="5e3a42ac4f99d8312f876bd4f7ac70b35d5b3db27a7ca7c8c96a7196b019e45d"
EXPECTED_PISTON_IDENTITY_SHA="19e978bacadea8ff1ac358b3e19efb68f395740200faa460b0f17b706c283d79"
PUBLIC_DATA_SHA="94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223"
HIDDEN_DATA_SHA="79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7"
B_DATASET_SHA="4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c"
B_CONFIG_SHA="250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560"
B_ADAPTER_MODEL_SHA="51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67"
B_ADAPTER_CONFIG_SHA="3738f9ef0ac56f90a48497ab4c0a1f172770864aa61dad56e8d9751050f34344"
MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
MODEL_WEIGHTS_SHA="c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
PISTON_DEFINITION_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"

PLAN_REL="ai-work/planner/WP7-c-plan.md"
REPORT_REL="ai-work/executor/WP7-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP7-c/grpo-cd-pilot/C13/run.sh"
PUBLIC_CONFIG_REL="configs/grpo/validation-pilot-public.yaml"
HIDDEN_CONFIG_REL="configs/grpo/validation-pilot-hidden.yaml"
PISTON_CONFIG_REL="configs/execution/piston-local.yaml"
B_RUN_NAME="B-sft-formal-seed42"
PUBLIC_RUN_NAME="C-public-grpo-pilot100-retry1-seed42"
HIDDEN_RUN_NAME="D-hidden-grpo-pilot100-retry1-seed42"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
[[ -x "$PY" && -x "$CV" ]] || { echo "target checkout .venv is unavailable; do not start GRPO recovery" >&2; exit 125; }

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
MACHINE_SHA="$(sha256sum "$MACHINE_POINTER" | awk '{print $1}')"

MACHINE_FIELDS="$($PY - "$MACHINE_POINTER" <<'PY_MACHINE'
import json
import sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "version", "machine_status", "bootstrap_project_commit", "open_r1_commit",
    "artifact_root", "hf_home", "formal_data_root", "readiness_record",
    "piston_identity_record", "piston_endpoint", "piston_host_id",
}
if not isinstance(value, dict) or set(value) != required:
    raise SystemExit("validation machine pointer schema is not exact")
if value["version"] != 1 or value["machine_status"] != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine pointer is not READY_FOR_VALIDATION_PLANNER")
for key in ("artifact_root", "hf_home", "formal_data_root", "readiness_record", "piston_identity_record"):
    item = value[key]
    if not isinstance(item, str) or not Path(item).is_absolute():
        raise SystemExit(f"validation machine pointer {key} must be absolute")
print("\t".join(str(value[key]) for key in (
    "bootstrap_project_commit", "open_r1_commit", "artifact_root", "hf_home", "formal_data_root",
    "readiness_record", "piston_identity_record", "piston_endpoint", "piston_host_id",
)))
PY_MACHINE
)"
TAB="$(printf '\t')"
IFS="$TAB" read -r BOOTSTRAP_COMMIT MACHINE_OPEN_R1 ARTIFACT_ROOT TARGET_HF_HOME FORMAL_DATA_ROOT READINESS_RECORD PISTON_IDENTITY_RECORD PISTON_ENDPOINT PISTON_HOST_ID <<<"$MACHINE_FIELDS"

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$TARGET_HF_HOME"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"

OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/$GATE_ID/$CHECKPOINT_ID"
C12_OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/$GATE_ID/C12"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
POSTCHECK_FILE="$OP_ROOT/postcheck-summary.json"
LOCK_FILE="$OP_ROOT/run.lock"
C12_EVIDENCE_FILE="$C12_OP_ROOT/operator-evidence.json"
C12_STATUS_FILE="$C12_OP_ROOT/status"
C12_LOG_FILE="$C12_OP_ROOT/terminal.log"
C12_POSTCHECK_FILE="$C12_OP_ROOT/postcheck-summary.json"
DATA_DIR="$FORMAL_DATA_ROOT/prepared"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
PILOT_ROOT="$ARTIFACT_ROOT/grpo-validation/pilot"
PUBLIC_RUN="$PILOT_ROOT/$PUBLIC_RUN_NAME"
HIDDEN_RUN="$PILOT_ROOT/$HIDDEN_RUN_NAME"
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
[[ ! -f "$POSTCHECK_FILE" ]] || cp -a "$POSTCHECK_FILE" "$OP_ROOT/postcheck-summary.before-$ATTEMPT_ID.json"
rm -f "$STATUS_FILE.tmp" "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"
printf '[%s] attempt=%s start checkpoint=%s gate=%s\n' "$START_TIME" "$ATTEMPT_ID" "$CHECKPOINT_ID" "$GATE_ID" >>"$LOG_FILE"

HEAD_COMMIT="" RESULT_CODE_COMMIT="" SCRIPT_SHA="" C12_EVIDENCE_SHA=""
READINESS_SHA="" PISTON_IDENTITY_SHA="" GPU_NAME="" GPU_VRAM_MIB="0" PAIR_SHA=""
CURRENT_OPEN_R1="" CURRENT_LOCK_SHA="" CURRENT_TORCH="" CURRENT_CUDA=""
RESUME_CHECKPOINT="" CURRENT_PHASE="preflight"

write_evidence() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [[ -n "$HEAD_COMMIT" ]] || HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$RESULT_CODE_COMMIT" ]] || RESULT_CODE_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null || true)"
  [[ -n "$SCRIPT_SHA" ]] || SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  [[ -n "$C12_EVIDENCE_SHA" ]] || C12_EVIDENCE_SHA="$(sha256sum "$C12_EVIDENCE_FILE" 2>/dev/null | awk '{print $1}' || true)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$ARTIFACT_ROOT" "$HEAD_COMMIT" "$RESULT_CODE_COMMIT" "$SCRIPT_SHA" \
    "$C12_EVIDENCE_SHA" "$MACHINE_POINTER" "$MACHINE_SHA" "$READINESS_RECORD" "$READINESS_SHA" "$PISTON_IDENTITY_RECORD" \
    "$PISTON_IDENTITY_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" "$PISTON_ENDPOINT" "$PISTON_HOST_ID" "$PAIR_SHA" "$CURRENT_OPEN_R1" \
    "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$RESUME_CHECKPOINT" "$command_rc" "$postcheck_rc" "$gate_status" \
    "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path
(
    output, postcheck_path, artifact_root, checkpoint_commit, result_code_commit, script_sha, c12_evidence_sha,
    machine_pointer, machine_sha, readiness_record, readiness_sha, piston_record, piston_sha, gpu_name, gpu_vram_mib,
    piston_endpoint, piston_host_id, pair_sha, open_r1_commit, dependency_lock_sha, torch_version, cuda_version,
    resume_checkpoint, command_rc, postcheck_rc, gate_status, note, start_time, end_time, attempt_id,
) = sys.argv[1:]

def digest(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inventory(path: Path) -> dict[str, object]:
    row: dict[str, object] = {"path": str(path), "exists": path.is_file() and not path.is_symlink()}
    if row["exists"]:
        row["size_bytes"] = path.stat().st_size
        row["sha256"] = digest(path)
    return row
pilot = Path(artifact_root) / "grpo-validation" / "pilot"
files = []
for name in ("C-public-grpo-pilot100-retry1-seed42", "D-hidden-grpo-pilot100-retry1-seed42"):
    run = pilot / name
    for relative in (
        "run.json", "resolved_config.yaml", "environment.json", "metrics.jsonl", "rollouts.jsonl", "rewards.jsonl",
        "group_metrics.jsonl", "checkpoints/checkpoint-90/code_verifier_log_state.json",
        "checkpoints/checkpoint-100/code_verifier_log_state.json", "checkpoints/adapter_config.json",
        "checkpoints/adapter_model.safetensors",
    ):
        files.append(inventory(run / relative))
postcheck_file = Path(postcheck_path)
postcheck = None
if postcheck_file.is_file() and not postcheck_file.is_symlink():
    postcheck = json.loads(postcheck_file.read_text(encoding="utf-8"))
    files.append(inventory(postcheck_file))
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP7-c",
    "source_plan_commit": "8464e69691c527c726a2e28e5a7ca81fa2001bbf",
    "operator_checkpoint_commit": checkpoint_commit or None,
    "result_code_commit": result_code_commit or None,
    "checkpoint_id": "C13",
    "operator_gate_id": "grpo-cd-pilot",
    "operator_script": "ai-work/executor/operator/WP7-c/grpo-cd-pilot/C13/run.sh",
    "operator_script_sha256": script_sha or None,
    "recovery_from": {
        "checkpoint_id": "C12",
        "operator_checkpoint_commit": "355486ccccff3a1325614e18e8f8d4a85b8789ba",
        "operator_script_sha256": "ba838037596a3e0ba9a0d1102075174de36998156d0b3766df62c3b7550afd44",
        "accepted_operator_evidence_sha256": c12_evidence_sha or None,
        "public_state": "completed_100",
        "hidden_state": "failed_after_checkpoint_90",
    },
    "target_machine_pointer": machine_pointer,
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record": readiness_record,
    "target_readiness_record_sha256": readiness_sha or None,
    "piston_identity_record": piston_record,
    "piston_identity_record_sha256": piston_sha or None,
    "gpu_name": gpu_name or None,
    "gpu_vram_mib": int(gpu_vram_mib or 0),
    "runtime_identity": {
        "open_r1_commit": open_r1_commit or None,
        "dependency_lock_sha256": dependency_lock_sha or None,
        "torch_version": torch_version or None,
        "cuda_version": cuda_version or None,
        "offline_model_loading": True,
    },
    "piston": {
        "endpoint": piston_endpoint,
        "host_id": piston_host_id,
        "definition_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
        "python_runtime": "3.10.0",
    },
    "formal_pair": {
        "public_run_name": "C-public-grpo-pilot100-retry1-seed42",
        "hidden_run_name": "D-hidden-grpo-pilot100-retry1-seed42",
        "seed": 42,
        "paired_definition_sha256": pair_sha or None,
        "parent_b_run_name": "B-sft-formal-seed42",
    },
    "resume_checkpoint": resume_checkpoint or None,
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
PY_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  local final_rc=1
  if [[ "$gate_status" == "passed" && "$command_rc" == "0" && "$postcheck_rc" == "0" ]]; then
    final_rc=0
  elif [[ "$command_rc" =~ ^[0-9]+$ ]] && (( command_rc > 0 && command_rc <= 255 )); then
    final_rc="$command_rc"
  elif [[ "$postcheck_rc" =~ ^[0-9]+$ ]] && (( postcheck_rc > 0 && postcheck_rc <= 255 )); then
    final_rc="$postcheck_rc"
  fi
  printf '%s\n' "$final_rc" >"$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  printf '[%s] attempt=%s end phase=%s command_rc=%s postcheck_rc=%s gate_status=%s note=%s\n' \
    "$end_time" "$ATTEMPT_ID" "$CURRENT_PHASE" "$command_rc" "$postcheck_rc" "$gate_status" "$note" >>"$LOG_FILE"
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

[[ "$MACHINE_SHA" == "$EXPECTED_MACHINE_SHA" ]] || fail_preflight "validation machine pointer SHA differs from C12"
[[ "$MACHINE_OPEN_R1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "validation machine Open-R1 identity changed"
[[ "$PISTON_ENDPOINT" == "http://127.0.0.1:2000" && "$PISTON_HOST_ID" == "1660ti-wsl" ]] || fail_preflight "canonical Piston topology changed"

HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve checkpoint HEAD"
RESULT_CODE_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve recovery result-code commit"
RESULT_PARENT="$(git -C "$REPO_ROOT" rev-parse "$RESULT_CODE_COMMIT^" 2>/dev/null)" || fail_preflight "cannot resolve recovery result-code parent"
[[ "$RESULT_PARENT" == "$C12_CHECKPOINT_COMMIT" ]] || fail_preflight "C13 recovery result-code commit is not directly parented by C12"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge contains tracked paths"
git -C "$REPO_ROOT" diff --quiet "$PLAN_COMMIT" HEAD -- "$PLAN_REL" || fail_preflight "sealed plan differs from source_plan_commit"
git -C "$REPO_ROOT" merge-base --is-ancestor "$BOOTSTRAP_COMMIT" HEAD || fail_preflight "bootstrap project commit is not an ancestor of C13"

if ! "$PY" - "$REPO_ROOT" "$C12_CHECKPOINT_COMMIT" "$RESULT_CODE_COMMIT" "$HEAD_COMMIT" "$REPORT_REL" "$SCRIPT_REL" <<'PY_SCOPE'
import hashlib
import subprocess
import sys
from pathlib import Path
repo = Path(sys.argv[1])
c12, result, head, report, script = sys.argv[2:]

def status(a: str, b: str) -> list[str]:
    return subprocess.run(["git", "-C", str(repo), "diff", "--name-status", a, b], check=True, capture_output=True, text=True).stdout.splitlines()
expected_business = [
    "M\tsrc/code_verifier/cli.py",
    "M\tsrc/code_verifier/training/grpo.py",
    "M\ttests/unit/test_cli.py",
    "A\ttests/unit/training/test_grpo_resume_lineage.py",
]
if status(c12, result) != expected_business:
    raise SystemExit(f"C13 recovery business scope changed: {status(c12, result)}")
if status(result, head) != [f"M\t{report}", f"A\t{script}"]:
    raise SystemExit(f"C13 checkpoint scope is not exactly report+script: {status(result, head)}")
mode = subprocess.run(["git", "-C", str(repo), "ls-tree", head, "--", script], check=True, capture_output=True, text=True).stdout.strip()
if not mode.startswith("100755 "):
    raise SystemExit("tracked C13 operator script is not executable")
previous = subprocess.run(["git", "-C", str(repo), "show", f"{result}:{report}"], check=True, capture_output=True).stdout
current = (repo / report).read_bytes()
if len(current) <= len(previous) or not current.startswith(previous):
    raise SystemExit("execution report is not byte-for-byte append-only")
c12_script = "ai-work/executor/operator/WP7-c/grpo-cd-pilot/C12/run.sh"
content = subprocess.run(["git", "-C", str(repo), "show", f"{c12}:{c12_script}"], check=True, capture_output=True).stdout
if hashlib.sha256(content).hexdigest() != "ba838037596a3e0ba9a0d1102075174de36998156d0b3766df62c3b7550afd44":
    raise SystemExit("C12 operator script bytes changed")
PY_SCOPE
then
  fail_preflight "C13 business/checkpoint scope provenance failed"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" <<'PY_META'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind("checkpoint_id: C13")
if pos < 0:
    raise SystemExit("C13 checkpoint block is missing")
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit("C13 checkpoint block is malformed")
block = text[start:end]
def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"C13 checkpoint field missing: {name}")
    return match.group(1).strip().strip('"').strip("'")
print("\t".join([
    field("result_code_commit"), field("operator_script_sha256"), field("operator_handoff_mode"),
    field("operator_gate_id"), field("operator_restart_policy"), field("status"),
]))
PY_META
)" || fail_preflight "cannot parse C13 checkpoint metadata"
IFS="$TAB" read -r CHECKPOINT_RESULT EXPECTED_SCRIPT_SHA CHECKPOINT_MODE CHECKPOINT_GATE CHECKPOINT_RESTART CHECKPOINT_STATUS <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "C13 report result-code commit does not match checkpoint parent"
[[ "$EXPECTED_SCRIPT_SHA" == "$SCRIPT_SHA" ]] || fail_preflight "tracked C13 operator script SHA differs from report"
[[ "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_GATE" == "$GATE_ID" ]] || fail_preflight "C13 checkpoint handoff/gate mismatch"
[[ "$CHECKPOINT_RESTART" == "trainer_checkpoint" && "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "C13 checkpoint restart/status mismatch"

[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -d "$DATA_DIR" ]] || fail_preflight "target persistent roots are unavailable"
[[ "$ARTIFACT_ROOT" != "$REPO_ROOT" && "$ARTIFACT_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "artifact_root must remain outside target checkout"
[[ -f "$READINESS_RECORD" && -f "$PISTON_IDENTITY_RECORD" ]] || fail_preflight "target readiness/Piston records are unavailable"
READINESS_SHA="$(sha256sum "$READINESS_RECORD" | awk '{print $1}')"
PISTON_IDENTITY_SHA="$(sha256sum "$PISTON_IDENTITY_RECORD" | awk '{print $1}')"
[[ "$READINESS_SHA" == "$EXPECTED_READINESS_SHA" ]] || fail_preflight "readiness record SHA differs from C12"
[[ "$PISTON_IDENTITY_SHA" == "$EXPECTED_PISTON_IDENTITY_SHA" ]] || fail_preflight "Piston identity SHA differs from C12"

if ! GPU_LIST="$(nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits 2>>"$LOG_FILE")"; then
  fail_preflight "nvidia-smi GPU inventory failed"
fi
GPU_INDEX="$(printf '%s\n' "$GPU_LIST" | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$1); gsub(/ /,"",$3); if ($3+0 >= 22528) {print $1; exit}}')"
[[ -n "$GPU_INDEX" ]] || fail_preflight "no RTX 4090 with at least 22528 MiB VRAM detected"
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
GPU_FIELDS="$($PY - <<'PY_GPU'
import torch
if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise SystemExit("operator requires exactly one visible CUDA device")
p = torch.cuda.get_device_properties(0)
if p.name != "NVIDIA GeForce RTX 4090" or int(p.total_memory // (1024 * 1024)) < 22528:
    raise SystemExit("visible GPU is not the certified RTX 4090")
if torch.cuda.get_device_capability(0) != (8, 9) or not bool(torch.cuda.is_bf16_supported(including_emulation=False)):
    raise SystemExit("RTX 4090 BF16/compute capability mismatch")
print(f"{p.name}\t{int(p.total_memory // (1024 * 1024))}")
PY_GPU
)" || fail_preflight "CUDA/BF16 target validation failed"
IFS="$TAB" read -r GPU_NAME GPU_VRAM_MIB <<<"$GPU_FIELDS"

RUNTIME_FIELDS="$($PY - "$REPO_ROOT" "$B_RUN" "$HEAD_COMMIT" <<'PY_RUNTIME'
import json
import sys
from pathlib import Path
import code_verifier
import open_r1
from code_verifier.environment import collect_environment
repo = Path(sys.argv[1]).resolve()
b_run = Path(sys.argv[2]).resolve()
head = sys.argv[3]
for module, name in ((code_verifier, "code_verifier"), (open_r1, "open_r1")):
    module_file = getattr(module, "__file__", None)
    if module_file is None or repo not in Path(module_file).resolve().parents:
        raise SystemExit(f"{name} does not resolve inside target checkout")
current = collect_environment()
frozen = json.loads((b_run / "environment.json").read_text(encoding="utf-8"))
expected_packages = {
    "accelerate": "1.4.0", "datasets": "3.2.0", "open-r1": "0.1.0.dev0", "peft": "0.14.0",
    "torch": "2.6.0+cu124", "transformers": "4.52.3", "trl": "0.18.0",
}
for value, label in ((current, "current"), (frozen, "formal B")):
    if value.get("packages") != expected_packages:
        raise SystemExit(f"{label} package map mismatch")
    if value.get("open_r1_commit") != "1416fa0cf21595d2083b399a2a0bbddd7f6e9563":
        raise SystemExit(f"{label} Open-R1 mismatch")
    if value.get("dependency_lock_hash") != "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560":
        raise SystemExit(f"{label} dependency lock mismatch")
    if value.get("python_version") != "3.10.21" or value.get("cuda_version") != "12.4":
        raise SystemExit(f"{label} Python/CUDA identity mismatch")
    if value.get("gpu_name") != "NVIDIA GeForce RTX 4090" or value.get("gpu_count") != 1:
        raise SystemExit(f"{label} GPU identity mismatch")
if current.get("project_commit") != head:
    raise SystemExit("current project commit does not equal C13 checkpoint HEAD")
print("\t".join([current["open_r1_commit"], current["dependency_lock_hash"], current["packages"]["torch"], current["cuda_version"]]))
PY_RUNTIME
)" || fail_preflight "target runtime/package identity validation failed"
IFS="$TAB" read -r CURRENT_OPEN_R1 CURRENT_LOCK_SHA CURRENT_TORCH CURRENT_CUDA <<<"$RUNTIME_FIELDS"

if ! "$PY" - "$MODEL_ID" "$MODEL_REVISION" "$MODEL_WEIGHTS_SHA" >>"$LOG_FILE" <<'PY_MODEL'
import hashlib
import sys
from pathlib import Path
from huggingface_hub import snapshot_download
snapshot = Path(snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_files_only=True)).resolve()
weights = snapshot / "model.safetensors"
if not snapshot.is_dir() or not weights.is_file():
    raise SystemExit("exact model snapshot is not available local-only")
h = hashlib.sha256()
with weights.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        h.update(chunk)
if h.hexdigest() != sys.argv[3]:
    raise SystemExit("cached base-model weights SHA256 mismatch")
print(f"model_snapshot={snapshot} model_safetensors_sha256={h.hexdigest()}")
PY_MODEL
then
  fail_preflight "exact 1.5B model revision/weights are unavailable local-only"
fi

[[ -f "$B_RUN/checkpoints/adapter_model.safetensors" && -f "$B_RUN/checkpoints/adapter_config.json" ]] || fail_preflight "formal B adapter is unavailable"
[[ "$(sha256sum "$B_RUN/checkpoints/adapter_model.safetensors" | awk '{print $1}')" == "$B_ADAPTER_MODEL_SHA" ]] || fail_preflight "formal B adapter_model SHA mismatch"
[[ "$(sha256sum "$B_RUN/checkpoints/adapter_config.json" | awk '{print $1}')" == "$B_ADAPTER_CONFIG_SHA" ]] || fail_preflight "formal B adapter_config SHA mismatch"
[[ "$(sha256sum "$REPO_ROOT/$PISTON_CONFIG_REL" | awk '{print $1}')" == "$PISTON_DEFINITION_SHA" ]] || fail_preflight "tracked Piston definition SHA changed"

PAIR_SHA="$($PY - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" <<'PY_PAIR'
import hashlib
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.data.leakage_checks import TrainingArtifactKind
from code_verifier.training import load_completed_sft_checkpoint
from code_verifier.training.grpo import _paired_definition, load_grpo_training_config, load_training_artifact, validate_grpo_artifact_pair, validate_grpo_config_pair
repo, data_dir, b_run = map(Path, sys.argv[1:4])
public_path = data_dir / "training/public_grpo.jsonl"
hidden_path = data_dir / "training/hidden_grpo.jsonl"
if hashlib.sha256(public_path.read_bytes()).hexdigest() != "94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223":
    raise SystemExit("formal Public dataset SHA mismatch")
if hashlib.sha256(hidden_path.read_bytes()).hexdigest() != "79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7":
    raise SystemExit("formal Hidden dataset SHA mismatch")
public_rows = load_training_artifact(public_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
hidden_rows = load_training_artifact(hidden_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
if len(public_rows) != 2500 or len(hidden_rows) != 2500:
    raise SystemExit("formal GRPO row count mismatch")
validate_grpo_artifact_pair(public_rows, hidden_rows)
parent = load_completed_sft_checkpoint(b_run)
if parent.run_id != "B-sft-formal-seed42" or parent.model_id != "Qwen/Qwen2.5-Coder-1.5B-Instruct":
    raise SystemExit("formal B identity mismatch")
if parent.model_revision != "2e1fd397ee46e1388853d2af2c993145b0f1098a" or parent.dataset_hash != "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c":
    raise SystemExit("formal B model/data identity mismatch")
if parent.config_hash != "250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244" or parent.dependency_lock_hash != "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560" or parent.seed != 42:
    raise SystemExit("formal B config/lock/seed identity mismatch")
public = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-public.yaml"), dataset_path=public_path, run_name="C-public-grpo-pilot100-retry1-seed42")
hidden = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-hidden.yaml"), dataset_path=hidden_path, run_name="D-hidden-grpo-pilot100-retry1-seed42")
validate_grpo_config_pair(public, hidden)
if (public.max_steps, hidden.max_steps, public.save_steps, hidden.save_steps) != (100, 100, 10, 10):
    raise SystemExit("pilot cadence changed")
pair_sha, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
if components.get("paired_public_config_hash") != "da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac" or components.get("paired_hidden_config_hash") != "5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658":
    raise SystemExit("portable pilot config identity changed")
if pair_sha != "bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f":
    raise SystemExit("portable pilot pair SHA changed")
print(pair_sha)
PY_PAIR
)" || fail_preflight "formal pilot pair/B identity validation failed"

C12_EVIDENCE_SHA="$($PY - "$C12_EVIDENCE_FILE" "$C12_STATUS_FILE" "$C12_LOG_FILE" "$C12_POSTCHECK_FILE" <<'PY_C12'
import hashlib
import json
import sys
from pathlib import Path
evidence_path, status_path, log_path, postcheck_path = map(Path, sys.argv[1:5])
for path in (evidence_path, status_path, log_path):
    if not path.is_file() or path.is_symlink():
        raise SystemExit("C12 terminal evidence is unavailable")
if status_path.read_text(encoding="utf-8").strip() != "2":
    raise SystemExit("C12 status is not the expected command failure rc=2")
if postcheck_path.exists():
    raise SystemExit("C12 unexpectedly produced postcheck evidence")
e = json.loads(evidence_path.read_text(encoding="utf-8"))
expected = {
    "version": 1,
    "stage_id": "WP7-c",
    "checkpoint_id": "C12",
    "operator_gate_id": "grpo-cd-pilot",
    "operator_checkpoint_commit": "355486ccccff3a1325614e18e8f8d4a85b8789ba",
    "result_code_commit": "dfbeafaf5b449b0884c065495db8059815cfd80f",
    "operator_script_sha256": "ba838037596a3e0ba9a0d1102075174de36998156d0b3766df62c3b7550afd44",
    "command_rc": 2,
    "postcheck_rc": 125,
    "gate_status": "command_failed",
    "note": "hidden pilot train-grpo exited nonzero",
}
if not isinstance(e, dict) or any(e.get(key) != value for key, value in expected.items()):
    raise SystemExit("C12 failure provenance changed")
h = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
print(h)
PY_C12
)" || fail_preflight "C12 failure evidence validation failed"

ACTION="$($PY - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" "$PUBLIC_RUN" "$HIDDEN_RUN" "$C12_CHECKPOINT_COMMIT" "$HEAD_COMMIT" "$PAIR_SHA" <<'PY_STATE'
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.environment import collect_environment
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint
from code_verifier.training.grpo import (
    _config_hash, _file_hash, _latest_valid_resume_checkpoint, _paired_definition,
    _resolve_resume_checkpoint, _validate_resume_run, load_grpo_training_config,
)
repo, data_dir, b_run, public_run, hidden_run = map(Path, sys.argv[1:6])
c12, head, pair_sha = sys.argv[6:9]
public = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-public.yaml"), dataset_path=data_dir / "training/public_grpo.jsonl", run_name="C-public-grpo-pilot100-retry1-seed42")
hidden = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-hidden.yaml"), dataset_path=data_dir / "training/hidden_grpo.jsonl", run_name="D-hidden-grpo-pilot100-retry1-seed42")
parent = load_completed_sft_checkpoint(b_run)
computed_pair, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
if computed_pair != pair_sha:
    raise SystemExit("pilot pair SHA changed during run-state validation")
public_identity = load_completed_grpo_checkpoint(public_run)
if public_identity.run_id != public.run_name or public_identity.reward_mode != "public" or public_identity.parent_sft != parent or public_identity.paired_definition_sha256 != pair_sha:
    raise SystemExit("C12 Public completed identity mismatch")
public_meta = json.loads((public_run / "run.json").read_text(encoding="utf-8"))
if public_meta.get("git_commit") != c12 or public_meta.get("status") != "completed" or public_meta.get("global_step") != 100:
    raise SystemExit("C12 Public is not the exact completed 100-step run")
if not hidden_run.is_dir() or hidden_run.is_symlink():
    raise SystemExit("C12 Hidden run directory is missing or unsafe")
hidden_meta = json.loads((hidden_run / "run.json").read_text(encoding="utf-8"))
if not isinstance(hidden_meta, dict) or hidden_meta.get("git_commit") != c12:
    raise SystemExit("Hidden run is not owned by C12")
attempts = hidden_meta.get("attempts")
if not isinstance(attempts, list) or not attempts:
    raise SystemExit("Hidden attempt history is missing")
if attempts[0].get("attempt") != 1 or attempts[0].get("status") != "failed" or attempts[0].get("code_commit") is not None:
    raise SystemExit("C12 Hidden attempt-1 history changed")
for index, attempt in enumerate(attempts[1:], 2):
    if not isinstance(attempt, dict) or attempt.get("attempt") != index or attempt.get("code_commit") != head:
        raise SystemExit("post-C12 Hidden attempt lineage is invalid")
status = hidden_meta.get("status")
if status == "completed":
    identity = load_completed_grpo_checkpoint(hidden_run)
    if identity.run_id != hidden.run_name or identity.reward_mode != "hidden" or identity.parent_sft != parent or identity.paired_definition_sha256 != pair_sha or hidden_meta.get("global_step") != 100:
        raise SystemExit("completed Hidden recovery identity mismatch")
    print("completed")
    raise SystemExit(0)
if status not in {"failed", "running"} or attempts[-1].get("status") != status:
    raise SystemExit("Hidden run is not in a coherent resumable state")
selected = _latest_valid_resume_checkpoint(hidden_run, hidden)
if selected is None:
    raise SystemExit("Hidden recovery has no valid Trainer+sidecar checkpoint")
match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", selected.name)
step = int(match.group(1)) if match else -1
if step < 90 or step > 100 or step % 10 != 0:
    raise SystemExit(f"Hidden recovery selected unsafe step {step}")
if len(attempts) == 1 and step != 90:
    raise SystemExit(f"first C13 recovery must start exactly from checkpoint-90, found checkpoint-{step}")
resolved, source = _resolve_resume_checkpoint(hidden_run, selected)
before = (hidden_run / "run.json").read_bytes()
_validate_resume_run(
    run_dir=hidden_run, config=hidden, seed=42, parent_sft=parent,
    dataset_hash=_file_hash(hidden.dataset_path, description="GRPO dataset"),
    config_hash=_config_hash(hidden, seed=42), paired_definition_sha256=pair_sha,
    paired_components=components, environment=collect_environment(), resume_source=source,
    resume_run_git_commit=c12,
)
if before != (hidden_run / "run.json").read_bytes():
    raise SystemExit("resume validation mutated Hidden run before attempt begin")
print(f"resume:{resolved}")
PY_STATE
)" || fail_preflight "C12 Public/Hidden recovery-state validation failed"

[[ -x "$TUNNEL_HELPER" ]] || fail_preflight "1660ti-wsl Piston tunnel helper is unavailable"
if ! "$TUNNEL_HELPER" >>"$LOG_FILE" 2>&1; then
  fail_preflight "1660ti-wsl Piston tunnel helper failed"
fi
if ! "$PY" - "$REPO_ROOT/$PISTON_CONFIG_REL" <<'PY_PISTON'
import sys
from pathlib import Path
from code_verifier.execution import PistonExecutor, load_piston_executor_config
executor = PistonExecutor(load_piston_executor_config(Path(sys.argv[1])))
if executor.validate_runtime() != "3.10.0":
    raise SystemExit("Piston Python runtime mismatch")
PY_PISTON
then
  fail_preflight "loopback Piston runtime validation failed"
fi

printf '[%s] preflight PASS: C12 Public complete; Hidden recovery action=%s; C12 evidence sha=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ACTION" "$C12_EVIDENCE_SHA" >>"$LOG_FILE"

if [[ "$ACTION" == "completed" ]]; then
  printf '[%s] Hidden already completed by an earlier C13 attempt; training command skipped\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
elif [[ "$ACTION" == resume:* ]]; then
  RESUME_CHECKPOINT="${ACTION#resume:}"
  CURRENT_PHASE="train-hidden"
  printf '[%s] Hidden recovery resume=%s origin_commit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RESUME_CHECKPOINT" "$C12_CHECKPOINT_COMMIT" >>"$LOG_FILE"
  if "$CV" train-grpo \
      --public-config "$REPO_ROOT/$PUBLIC_CONFIG_REL" \
      --hidden-config "$REPO_ROOT/$HIDDEN_CONFIG_REL" \
      --dataset-dir "$DATA_DIR" \
      --public-run-name "$PUBLIC_RUN_NAME" \
      --hidden-run-name "$HIDDEN_RUN_NAME" \
      --public-sft-run-dir "$B_RUN" \
      --hidden-sft-run-dir "$B_RUN" \
      --reward-mode hidden \
      --resume-from-checkpoint "$RESUME_CHECKPOINT" \
      --resume-run-git-commit "$C12_CHECKPOINT_COMMIT" \
      --seed 42 \
      --output-dir "$PILOT_ROOT" > >(tee -a "$LOG_FILE") 2>&1; then
    printf '[%s] Hidden recovery train-grpo rc=0\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
  else
    rc=$?
    write_evidence "$rc" 125 command_failed "Hidden C13 checkpoint recovery train-grpo exited nonzero"
    exit $?
  fi
else
  fail_preflight "C13 action is neither completed nor resume"
fi

CURRENT_PHASE="postcheck"
if "$PY" - "$PUBLIC_RUN" "$HIDDEN_RUN" "$B_RUN" "$C12_CHECKPOINT_COMMIT" "$HEAD_COMMIT" "$PAIR_SHA" "$POSTCHECK_FILE.tmp" <<'PY_POSTCHECK'
import json
import math
import re
import sys
from pathlib import Path
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint
from code_verifier.training.grpo import _GRPO_STREAM_LOG_NAMES, _stream_log_file_state, _validate_resume_log_checkpoint
public_run, hidden_run, b_run = map(Path, sys.argv[1:4])
c12, head, pair_sha, output = sys.argv[4:8]
parent = load_completed_sft_checkpoint(b_run)

def validate_completed(run: Path, mode: str, run_id: str) -> dict[str, object]:
    identity = load_completed_grpo_checkpoint(run)
    if identity.run_id != run_id or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != pair_sha:
        raise SystemExit(f"{mode} strict completed identity mismatch")
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    if meta.get("git_commit") != c12 or meta.get("status") != "completed" or meta.get("global_step") != 100:
        raise SystemExit(f"{mode} final metadata mismatch")
    attempts = meta.get("attempts")
    if not isinstance(attempts, list) or not attempts or attempts[-1].get("status") != "completed":
        raise SystemExit(f"{mode} final attempt history invalid")
    total = 0.0
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict) or attempt.get("attempt") != index:
            raise SystemExit(f"{mode} attempt numbering invalid")
        hours = attempt.get("gpu_hours")
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(float(hours)) or float(hours) < 0:
            raise SystemExit(f"{mode} attempt gpu_hours invalid")
        total += float(hours)
        if index > 1 and attempt.get("code_commit") != head:
            raise SystemExit(f"{mode} resumed attempt code_commit mismatch")
    gpu_hours = meta.get("gpu_hours")
    if isinstance(gpu_hours, bool) or not isinstance(gpu_hours, (int, float)) or not math.isclose(float(gpu_hours), total, rel_tol=0.0, abs_tol=1e-12):
        raise SystemExit(f"{mode} cumulative gpu_hours invalid")
    for step in range(10, 101, 10):
        checkpoint = run / "checkpoints" / f"checkpoint-{step}"
        state = _validate_resume_log_checkpoint(run, checkpoint)
        if state.get("global_step") != step:
            raise SystemExit(f"{mode} checkpoint-{step} sidecar mismatch")
    final_state = _validate_resume_log_checkpoint(run, run / "checkpoints/checkpoint-100")
    for name in _GRPO_STREAM_LOG_NAMES:
        if _stream_log_file_state(run / name) != final_state["logs"][name]:
            raise SystemExit(f"{mode} checkpoint-100 is not the complete canonical {name}")
    return {"run_id": run_id, "attempt_count": len(attempts), "gpu_hours": float(gpu_hours)}

public = validate_completed(public_run, "public", "C-public-grpo-pilot100-retry1-seed42")
if public["attempt_count"] != 1:
    raise SystemExit("Public must remain the untouched C12 completed run")
hidden = validate_completed(hidden_run, "hidden", "D-hidden-grpo-pilot100-retry1-seed42")
if hidden["attempt_count"] < 2:
    raise SystemExit("Hidden recovery did not append a C13 attempt")
history = hidden_run / "checkpoints/recovery-history"
if not history.is_dir() or history.is_symlink():
    raise SystemExit("Hidden recovery-history is missing or unsafe")
archives = sorted(path.name for path in history.iterdir() if path.is_dir() and not path.is_symlink() and re.fullmatch(r"before-attempt-[1-9][0-9]*-resume-checkpoint-(90|100)", path.name))
if not any(name.endswith("-resume-checkpoint-90") for name in archives):
    raise SystemExit("Hidden C13 has no completed checkpoint-90 recovery archive")
summary = {
    "version": 1,
    "status": "passed",
    "paired_definition_sha256": pair_sha,
    "origin_run_git_commit": c12,
    "recovery_code_commit": head,
    "public": public,
    "hidden": hidden,
    "hidden_recovery_archives": archives,
    "recovery_scope": "Public untouched; Hidden resumed from checkpoint-90 or a later C13-created valid checkpoint and completed step 100",
}
Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY_POSTCHECK
then
  mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"
else
  rc=$?
  rm -f "$POSTCHECK_FILE.tmp"
  write_evidence 0 "$rc" postcheck_failed "C13 paired completion postcheck failed"
  exit $?
fi

CURRENT_PHASE="complete"
write_evidence 0 0 passed "C12 Public preserved; Hidden recovered from checkpoint-90 lineage and completed step 100"
exit $?
