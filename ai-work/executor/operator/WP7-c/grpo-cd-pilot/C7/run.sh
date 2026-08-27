#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP7-c"
GATE_ID="grpo-cd-pilot"
CHECKPOINT_ID="C7"
PLAN_COMMIT="8464e69691c527c726a2e28e5a7ca81fa2001bbf"
RESULT_CODE_COMMIT="8f8e3e0f5040574e6fcca9401a71281e1e9660ad"
SUPERSEDED_CHECKPOINT_ID="C6"
SUPERSEDED_CHECKPOINT_COMMIT="db42c382a6499ca771ae95a7d8b2472c3960a8b8"
PRIOR_CHECKPOINT_COMMIT="ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d"
PRIOR_RESULT_CODE_COMMIT="e1592bfc89c5e3f276c4b42d089597a23ccfe4c2"
PRIOR_EVIDENCE_SHA="f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e"
PRIOR_POSTCHECK_SHA="94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a"
PRIOR_PAIR_SHA="b0aa34f56a3453687301edfc327fd26e5f1318839d77c8f4a5a8e508b435f49d"
PRIOR_PUBLIC_ADAPTER_SHA="0d7eebadb82932450533aa1ce28f79e651aa033f4a7d44bf19c39c8d033ac22e"
PRIOR_HIDDEN_ADAPTER_SHA="20becdf150b81e1f26283b030bfde93ed8ba85353d80675f73bf3dec968eed6d"
EXPECTED_PILOT_PAIR_SHA="a82c7521551d8a4520a0126783c3c4c4dd3f36f57a5b3dd43484e59dda7a34b5"
EXPECTED_MACHINE_SHA="b2230476c3d7600477108db5684ba2efbef95b89f746b8d8a1bc83b88ba5cab7"
EXPECTED_READINESS_SHA="5e3a42ac4f99d8312f876bd4f7ac70b35d5b3db27a7ca7c8c96a7196b019e45d"
EXPECTED_PISTON_IDENTITY_SHA="19e978bacadea8ff1ac358b3e19efb68f395740200faa460b0f17b706c283d79"
PUBLIC_DATA_SHA="94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223"
HIDDEN_DATA_SHA="79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7"
MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
MODEL_WEIGHTS_SHA="c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
B_DATASET_SHA="4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c"
B_CONFIG_SHA="250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560"
B_ADAPTER_MODEL_SHA="51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67"
B_ADAPTER_CONFIG_SHA="3738f9ef0ac56f90a48497ab4c0a1f172770864aa61dad56e8d9751050f34344"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
PISTON_DEFINITION_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
SMOKE_MAX_CHECKPOINT_BYTES=42184437
SMOKE_MAX_CHECKPOINT_INODES=15

PLAN_REL="ai-work/planner/WP7-c-plan.md"
REPORT_REL="ai-work/executor/WP7-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP7-c/grpo-cd-pilot/C7/run.sh"
PUBLIC_CONFIG_REL="configs/grpo/validation-pilot-public.yaml"
HIDDEN_CONFIG_REL="configs/grpo/validation-pilot-hidden.yaml"
PISTON_CONFIG_REL="configs/execution/piston-local.yaml"
B_RUN_NAME="B-sft-formal-seed42"
PUBLIC_RUN_NAME="C-public-grpo-pilot100-seed42"
HIDDEN_RUN_NAME="D-hidden-grpo-pilot100-seed42"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
[[ -x "$PY" && -x "$CV" ]] || { echo "target checkout .venv is unavailable; do not start GRPO pilot" >&2; exit 125; }

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
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
POSTCHECK_FILE="$OP_ROOT/postcheck-summary.json"
LOCK_FILE="$OP_ROOT/run.lock"
DATA_DIR="$FORMAL_DATA_ROOT/prepared"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
PILOT_ROOT="$ARTIFACT_ROOT/grpo-validation/pilot"
PUBLIC_RUN="$PILOT_ROOT/$PUBLIC_RUN_NAME"
HIDDEN_RUN="$PILOT_ROOT/$HIDDEN_RUN_NAME"
TUNNEL_HELPER="$ARTIFACT_ROOT/machine/ensure-piston-1660ti-tunnel.sh"
PRIOR_OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/grpo-cd-smoke/C5"
PRIOR_EVIDENCE_FILE="$PRIOR_OP_ROOT/operator-evidence.json"
PRIOR_STATUS_FILE="$PRIOR_OP_ROOT/status"
PRIOR_POSTCHECK_FILE="$PRIOR_OP_ROOT/postcheck-summary.json"
PRIOR_SMOKE_ROOT="$ARTIFACT_ROOT/grpo-validation/smoke"
PRIOR_PUBLIC_RUN="$PRIOR_SMOKE_ROOT/C-public-grpo-smoke20-seed42"
PRIOR_HIDDEN_RUN="$PRIOR_SMOKE_ROOT/D-hidden-grpo-smoke20-seed42"

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

HEAD_COMMIT="" SCRIPT_SHA="" READINESS_SHA="" PISTON_IDENTITY_SHA=""
GPU_NAME="" GPU_VRAM_MIB="0" PAIR_SHA=""
CURRENT_OPEN_R1="" CURRENT_LOCK_SHA="" CURRENT_TORCH="" CURRENT_CUDA=""
REQUIRED_STORAGE_BYTES="0" REQUIRED_STORAGE_INODES="0" CURRENT_PHASE="preflight"

write_evidence() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [[ -n "$HEAD_COMMIT" ]] || HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$SCRIPT_SHA" ]] || SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$REPO_ROOT" "$MACHINE_POINTER" "$READINESS_RECORD" "$PISTON_IDENTITY_RECORD" \
    "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" "$HEAD_COMMIT" "$SCRIPT_SHA" "$MACHINE_SHA" "$READINESS_SHA" \
    "$PISTON_IDENTITY_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" "$PISTON_ENDPOINT" "$PISTON_HOST_ID" "$PAIR_SHA" "$CURRENT_OPEN_R1" \
    "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" \
    "$end_time" "$ATTEMPT_ID" "$REQUIRED_STORAGE_BYTES" "$REQUIRED_STORAGE_INODES" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path

(
    output, postcheck_path, repo_root, machine_pointer, readiness_record, piston_identity_record,
    artifact_root, hf_home, formal_data_root, checkpoint_commit, script_sha, machine_sha, readiness_sha,
    piston_identity_sha, gpu_name, gpu_vram_mib, piston_endpoint, piston_host_id, pair_sha, open_r1_commit,
    dependency_lock_sha, torch_version, cuda_version, command_rc, postcheck_rc, gate_status, note,
    start_time, end_time, attempt_id, required_storage_bytes, required_storage_inodes,
) = sys.argv[1:]


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(path: Path) -> dict[str, object]:
    row: dict[str, object] = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        row["size_bytes"] = path.stat().st_size
        row["sha256"] = digest(path)
    return row


postcheck = None
postcheck_file = Path(postcheck_path)
if postcheck_file.is_file():
    value = json.loads(postcheck_file.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        postcheck = value
pilot_root = Path(artifact_root) / "grpo-validation" / "pilot"
files = []
for run_name in ("C-public-grpo-pilot100-seed42", "D-hidden-grpo-pilot100-seed42"):
    run = pilot_root / run_name
    for relative in (
        "run.json", "resolved_config.yaml", "environment.json", "metrics.jsonl", "rollouts.jsonl",
        "rewards.jsonl", "group_metrics.jsonl", "checkpoints/adapter_config.json", "checkpoints/adapter_model.safetensors",
    ):
        files.append(inventory(run / relative))
if postcheck_file.is_file():
    files.append(inventory(postcheck_file))
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP7-c",
    "source_plan_commit": "8464e69691c527c726a2e28e5a7ca81fa2001bbf",
    "operator_checkpoint_commit": checkpoint_commit or None,
    "result_code_commit": "8f8e3e0f5040574e6fcca9401a71281e1e9660ad",
    "checkpoint_id": "C7",
    "operator_gate_id": "grpo-cd-pilot",
    "operator_script": "ai-work/executor/operator/WP7-c/grpo-cd-pilot/C7/run.sh",
    "operator_script_sha256": script_sha or None,
    "prior_gate": {
        "operator_gate_id": "grpo-cd-smoke",
        "checkpoint_id": "C5",
        "operator_checkpoint_commit": "ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d",
        "accepted_operator_evidence_sha256": "f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e",
        "accepted_postcheck_sha256": "94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a",
    },
    "target_machine_pointer": machine_pointer,
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record": readiness_record,
    "target_readiness_record_sha256": readiness_sha or None,
    "piston_identity_record": piston_identity_record,
    "piston_identity_record_sha256": piston_identity_sha or None,
    "gpu_name": gpu_name or None,
    "gpu_vram_mib": int(gpu_vram_mib or 0),
    "resolved_roots": {
        "repo_root": repo_root,
        "artifact_root": artifact_root,
        "hf_home": hf_home,
        "formal_data_root": formal_data_root,
    },
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
        "public_run_name": "C-public-grpo-pilot100-seed42",
        "hidden_run_name": "D-hidden-grpo-pilot100-seed42",
        "seed": 42,
        "paired_definition_sha256": pair_sha or None,
        "parent_b_run_name": "B-sft-formal-seed42",
    },
    "storage_gate": {
        "smoke_max_complete_checkpoint_bytes": 42184437,
        "smoke_max_complete_checkpoint_inodes": 15,
        "required_free_bytes": int(required_storage_bytes or 0),
        "required_free_inodes": int(required_storage_inodes or 0),
    },
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

[[ "$MACHINE_SHA" == "$EXPECTED_MACHINE_SHA" ]] || fail_preflight "validation machine pointer SHA differs from accepted C5 identity"
[[ "$MACHINE_OPEN_R1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "validation machine Open-R1 identity changed"
[[ "$PISTON_ENDPOINT" == "http://127.0.0.1:2000" && "$PISTON_HOST_ID" == "1660ti-wsl" ]] || fail_preflight "canonical Piston topology changed"

HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve checkpoint HEAD"
PARENT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve checkpoint parent"
[[ "$PARENT_COMMIT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "C7 checkpoint parent is not optimized result-code commit"
RESULT_CODE_PARENT="$(git -C "$REPO_ROOT" rev-parse "$RESULT_CODE_COMMIT^" 2>/dev/null)" || fail_preflight "cannot resolve optimized result-code parent"
[[ "$RESULT_CODE_PARENT" == "$SUPERSEDED_CHECKPOINT_COMMIT" ]] || fail_preflight "optimized result-code parent is not superseded C6 checkpoint"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge contains tracked paths"
git -C "$REPO_ROOT" diff --quiet "$PLAN_COMMIT" HEAD -- "$PLAN_REL" || fail_preflight "sealed plan differs from source_plan_commit"
git -C "$REPO_ROOT" merge-base --is-ancestor "$BOOTSTRAP_COMMIT" HEAD || fail_preflight "bootstrap project commit is not an ancestor of checkpoint HEAD"

if ! "$PY" - "$REPO_ROOT" "$PARENT_COMMIT" "$HEAD_COMMIT" "$REPORT_REL" "$SCRIPT_REL" <<'PY_SCOPE'
import subprocess
import sys
from pathlib import Path
repo = Path(sys.argv[1])
parent, head, report, script = sys.argv[2:]
status = subprocess.run(
    ["git", "-C", str(repo), "diff", "--name-status", parent, head],
    check=True, capture_output=True, text=True,
).stdout.splitlines()
if status != [f"M\t{report}", f"A\t{script}"]:
    raise SystemExit(f"C7 checkpoint scope is not exactly report+script: {status}")
mode_line = subprocess.run(
    ["git", "-C", str(repo), "ls-tree", head, "--", script],
    check=True, capture_output=True, text=True,
).stdout.strip()
if not mode_line.startswith("100755 "):
    raise SystemExit("tracked C7 operator script is not executable")
previous = subprocess.run(
    ["git", "-C", str(repo), "show", f"{parent}:{report}"],
    check=True, capture_output=True,
).stdout
current = (repo / report).read_bytes()
if len(current) <= len(previous) or not current.startswith(previous):
    raise SystemExit("execution report is not byte-for-byte append-only")
PY_SCOPE
then
  fail_preflight "C7 checkpoint scope/append-only provenance failed"
fi

CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" <<'PY_META'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind("checkpoint_id: C7")
if pos < 0:
    raise SystemExit("C7 checkpoint block is missing")
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit("C7 checkpoint block is malformed")
block = text[start:end]
def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"C7 checkpoint field missing: {name}")
    return match.group(1).strip().strip('"').strip("'")
print("\t".join([
    field("operator_script_sha256"), field("operator_handoff_mode"), field("operator_gate_id"),
    field("operator_restart_policy"), field("result_code_commit"), field("source_plan_commit"), field("status"),
    field("accepted_prior_operator_evidence_sha256"), field("prior_operator_checkpoint_commit"),
    field("supersedes_checkpoint_id"), field("supersedes_checkpoint_commit"),
]))
PY_META
)" || fail_preflight "cannot parse C7 checkpoint metadata"
IFS="$TAB" read -r EXPECTED_SCRIPT_SHA CHECKPOINT_MODE CHECKPOINT_GATE CHECKPOINT_RESTART CHECKPOINT_RESULT CHECKPOINT_PLAN CHECKPOINT_STATUS ACCEPTED_PRIOR_EVIDENCE CHECKPOINT_PRIOR_COMMIT CHECKPOINT_SUPERSEDES_ID CHECKPOINT_SUPERSEDES_COMMIT <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_GATE" == "$GATE_ID" ]] || fail_preflight "C7 checkpoint handoff/gate mismatch"
[[ "$CHECKPOINT_RESTART" == "trainer_checkpoint" && "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "C7 checkpoint restart/status mismatch"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" && "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" ]] || fail_preflight "C7 checkpoint source provenance mismatch"
[[ "$ACCEPTED_PRIOR_EVIDENCE" == "$PRIOR_EVIDENCE_SHA" && "$CHECKPOINT_PRIOR_COMMIT" == "$PRIOR_CHECKPOINT_COMMIT" ]] || fail_preflight "C7 accepted-C5 provenance mismatch"
[[ "$CHECKPOINT_SUPERSEDES_ID" == "$SUPERSEDED_CHECKPOINT_ID" && "$CHECKPOINT_SUPERSEDES_COMMIT" == "$SUPERSEDED_CHECKPOINT_COMMIT" ]] || fail_preflight "C7 supersession provenance mismatch"
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked C7 operator script SHA mismatch"

[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -d "$DATA_DIR" ]] || fail_preflight "target persistent roots are unavailable"
[[ "$ARTIFACT_ROOT" != "$REPO_ROOT" && "$ARTIFACT_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "artifact_root must remain outside target checkout"
[[ "$FORMAL_DATA_ROOT" != "$REPO_ROOT" && "$FORMAL_DATA_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "formal_data_root must remain outside target checkout"
[[ "$TARGET_HF_HOME" != "$REPO_ROOT" && "$TARGET_HF_HOME" != "$REPO_ROOT/"* ]] || fail_preflight "hf_home must remain outside target checkout"
[[ -f "$READINESS_RECORD" && -f "$PISTON_IDENTITY_RECORD" ]] || fail_preflight "target readiness/Piston records are unavailable"
READINESS_SHA="$(sha256sum "$READINESS_RECORD" | awk '{print $1}')"
PISTON_IDENTITY_SHA="$(sha256sum "$PISTON_IDENTITY_RECORD" | awk '{print $1}')"
[[ "$READINESS_SHA" == "$EXPECTED_READINESS_SHA" ]] || fail_preflight "readiness record SHA differs from accepted C5 identity"
[[ "$PISTON_IDENTITY_SHA" == "$EXPECTED_PISTON_IDENTITY_SHA" ]] || fail_preflight "Piston identity SHA differs from accepted C5 identity"

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
name = p.name
vram_mib = int(p.total_memory // (1024 * 1024))
if name != "NVIDIA GeForce RTX 4090" or vram_mib < 22528:
    raise SystemExit("visible GPU is not the certified RTX 4090")
if torch.cuda.get_device_capability(0) != (8, 9):
    raise SystemExit("RTX 4090 compute capability mismatch")
if not bool(torch.cuda.is_bf16_supported(including_emulation=False)):
    raise SystemExit("native BF16 is unavailable")
print(f"{name}\t{vram_mib}")
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
    if value.get("compute_capability") != "8.9" or value.get("bf16_supported") is not True:
        raise SystemExit(f"{label} BF16/compute capability mismatch")
if current.get("project_commit") != head:
    raise SystemExit("current project commit does not equal operator checkpoint HEAD")
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

[[ -f "$B_RUN/checkpoints/adapter_model.safetensors" && -f "$B_RUN/checkpoints/adapter_config.json" ]] || fail_preflight "formal B core adapter files are unavailable"
[[ "$(sha256sum "$B_RUN/checkpoints/adapter_model.safetensors" | awk '{print $1}')" == "$B_ADAPTER_MODEL_SHA" ]] || fail_preflight "formal B adapter_model SHA mismatch"
[[ "$(sha256sum "$B_RUN/checkpoints/adapter_config.json" | awk '{print $1}')" == "$B_ADAPTER_CONFIG_SHA" ]] || fail_preflight "formal B adapter_config SHA mismatch"
if ! "$CV" check-data --dataset "$DATA_DIR" >>"$LOG_FILE" 2>&1; then
  fail_preflight "formal data check-data failed"
fi

PAIR_FIELDS="$($PY - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" <<'PY_PAIR'
import hashlib
import json
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
expected_parent = {
    "run_id": "B-sft-formal-seed42", "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a", "dataset_hash": "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c",
    "config_hash": "250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244", "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560", "seed": 42,
}
for key, value in expected_parent.items():
    if getattr(parent, key) != value:
        raise SystemExit(f"formal B identity mismatch: {key}")
public = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-public.yaml"), dataset_path=public_path, run_name="C-public-grpo-pilot100-seed42")
hidden = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-hidden.yaml"), dataset_path=hidden_path, run_name="D-hidden-grpo-pilot100-seed42")
validate_grpo_config_pair(public, hidden)
if (public.max_steps, hidden.max_steps, public.save_steps, hidden.save_steps) != (100, 100, 50, 50):
    raise SystemExit("pilot cadence is not 100 steps / save 50")
pair_sha, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
if pair_sha != "a82c7521551d8a4520a0126783c3c4c4dd3f36f57a5b3dd43484e59dda7a34b5":
    raise SystemExit("pilot pair SHA differs from control-plane certification")
print(f"{pair_sha}\t{json.dumps(components, sort_keys=True, separators=(',', ':'))}")
PY_PAIR
)" || fail_preflight "formal pilot pair/B identity validation failed"
IFS="$TAB" read -r PAIR_SHA PAIR_COMPONENTS_JSON <<<"$PAIR_FIELDS"

if ! "$PY" - "$PRIOR_EVIDENCE_FILE" "$PRIOR_STATUS_FILE" "$PRIOR_POSTCHECK_FILE" "$PRIOR_PUBLIC_RUN" "$PRIOR_HIDDEN_RUN" <<'PY_PRIOR'
import hashlib
import json
import sys
from pathlib import Path
from code_verifier.training import load_completed_grpo_checkpoint
evidence_path, status_path, postcheck_path, public_run, hidden_run = map(Path, sys.argv[1:6])
def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
for path in (evidence_path, status_path, postcheck_path):
    if not path.is_file() or path.is_symlink():
        raise SystemExit("accepted C5 operator artifact is unavailable")
if sha(evidence_path) != "f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e" or sha(postcheck_path) != "94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a":
    raise SystemExit("accepted C5 evidence/postcheck bytes changed")
if status_path.read_text(encoding="utf-8").strip() != "0":
    raise SystemExit("accepted C5 status is not zero")
e = json.loads(evidence_path.read_text(encoding="utf-8"))
expected = {
    "version": 1, "stage_id": "WP7-c", "checkpoint_id": "C5", "operator_gate_id": "grpo-cd-smoke",
    "operator_checkpoint_commit": "ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d", "result_code_commit": "e1592bfc89c5e3f276c4b42d089597a23ccfe4c2",
    "command_rc": 0, "postcheck_rc": 0, "gate_status": "passed",
}
if not isinstance(e, dict) or any(e.get(key) != value for key, value in expected.items()):
    raise SystemExit("accepted C5 evidence provenance changed")
formal_pair = e.get("formal_pair")
if not isinstance(formal_pair, dict) or formal_pair.get("paired_definition_sha256") != "b0aa34f56a3453687301edfc327fd26e5f1318839d77c8f4a5a8e508b435f49d":
    raise SystemExit("accepted C5 pair identity changed")
post = json.loads(postcheck_path.read_text(encoding="utf-8"))
if post.get("status") != "passed" or post.get("max_complete_trainer_checkpoint_bytes") != 42184437 or post.get("max_complete_trainer_checkpoint_inodes") != 15:
    raise SystemExit("accepted C5 checkpoint inventory changed")
for run, mode, run_id, adapter_sha in (
    (public_run, "public", "C-public-grpo-smoke20-seed42", "0d7eebadb82932450533aa1ce28f79e651aa033f4a7d44bf19c39c8d033ac22e"),
    (hidden_run, "hidden", "D-hidden-grpo-smoke20-seed42", "20becdf150b81e1f26283b030bfde93ed8ba85353d80675f73bf3dec968eed6d"),
):
    identity = load_completed_grpo_checkpoint(run)
    if identity.run_id != run_id or identity.reward_mode != mode or identity.paired_definition_sha256 != "b0aa34f56a3453687301edfc327fd26e5f1318839d77c8f4a5a8e508b435f49d":
        raise SystemExit(f"accepted C5 {mode} run identity changed")
    metadata = json.loads((run / "run.json").read_text(encoding="utf-8"))
    if metadata.get("git_commit") != "ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d" or metadata.get("global_step") != 20 or metadata.get("status") != "completed":
        raise SystemExit(f"accepted C5 {mode} metadata changed")
    if sha(run / "checkpoints/adapter_model.safetensors") != adapter_sha:
        raise SystemExit(f"accepted C5 {mode} final adapter changed")
    for step in (10, 20):
        checkpoint = run / "checkpoints" / f"checkpoint-{step}"
        required = [checkpoint / name for name in (
            "adapter_config.json", "adapter_model.safetensors", "optimizer.pt", "scheduler.pt",
            "rng_state.pth", "trainer_state.json", "training_args.bin",
        )]
        if any(not item.is_file() or item.is_symlink() or item.stat().st_size <= 0 for item in required):
            raise SystemExit(f"accepted C5 {mode} checkpoint-{step} is incomplete")
        state = json.loads((checkpoint / "trainer_state.json").read_text(encoding="utf-8"))
        if state.get("global_step") != step:
            raise SystemExit(f"accepted C5 {mode} checkpoint-{step} state mismatch")
print("accepted_c5_smoke=PASS")
PY_PRIOR
then
  fail_preflight "accepted C5 smoke evidence or target artifacts changed"
fi

[[ "$(sha256sum "$REPO_ROOT/$PISTON_CONFIG_REL" | awk '{print $1}')" == "$PISTON_DEFINITION_SHA" ]] || fail_preflight "tracked Piston definition SHA changed"
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

STORAGE_FIELDS="$($PY - "$ARTIFACT_ROOT" "$SMOKE_MAX_CHECKPOINT_BYTES" "$SMOKE_MAX_CHECKPOINT_INODES" <<'PY_STORAGE'
import os
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1])
smoke_bytes = int(sys.argv[2])
smoke_inodes = int(sys.argv[3])
required_bytes = max(30 * 1024**3, 6 * smoke_bytes + 10 * 1024**3)
required_inodes = max(100000, 6 * smoke_inodes + 20000)
usage = shutil.disk_usage(root)
free_inodes = os.statvfs(root).f_favail
if usage.free < required_bytes:
    raise SystemExit(f"pilot requires {required_bytes} free bytes; found {usage.free}")
if free_inodes < required_inodes:
    raise SystemExit(f"pilot requires {required_inodes} free inodes; found {free_inodes}")
print(f"{required_bytes}\t{required_inodes}\t{usage.free}\t{free_inodes}")
PY_STORAGE
)" || fail_preflight "pilot operator-start storage gate failed"
IFS="$TAB" read -r REQUIRED_STORAGE_BYTES REQUIRED_STORAGE_INODES FREE_STORAGE_BYTES FREE_STORAGE_INODES <<<"$STORAGE_FIELDS"
printf '[%s] preflight PASS: provenance/accepted-C5/machine/GPU/runtime/model/data/B/pilot-pair/Piston/storage required_bytes=%s required_inodes=%s free_bytes=%s free_inodes=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$REQUIRED_STORAGE_BYTES" "$REQUIRED_STORAGE_INODES" "$FREE_STORAGE_BYTES" "$FREE_STORAGE_INODES" >>"$LOG_FILE"

resolve_run_action() {
  local mode="$1" run_dir="$2"
  "$PY" - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" "$run_dir" "$mode" "$HEAD_COMMIT" "$PAIR_SHA" <<'PY_RESUME'
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
public = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-public.yaml"), dataset_path=data_dir / "training/public_grpo.jsonl", run_name="C-public-grpo-pilot100-seed42")
hidden = replace(load_grpo_training_config(repo / "configs/grpo/validation-pilot-hidden.yaml"), dataset_path=data_dir / "training/hidden_grpo.jsonl", run_name="D-hidden-grpo-pilot100-seed42")
config = public if mode == "public" else hidden
parent = load_completed_sft_checkpoint(b_run)
pair_sha, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
if pair_sha != expected_pair:
    raise SystemExit("pilot pair SHA changed after preflight")
if not run_dir.exists():
    print("fresh")
    raise SystemExit(0)
if not run_dir.is_dir() or run_dir.is_symlink() or not (run_dir / "run.json").is_file():
    raise SystemExit("existing pilot run path is invalid")
metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
if not isinstance(metadata, dict) or metadata.get("git_commit") != head:
    raise SystemExit("existing pilot run belongs to a different checkpoint commit")
if metadata.get("status") == "completed":
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.run_id != config.run_name or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != expected_pair:
        raise SystemExit("completed pilot run identity mismatch")
    print("completed")
    raise SystemExit(0)
if metadata.get("status") not in {"running", "failed"}:
    raise SystemExit("existing pilot run status is not resumable")
checkpoint_root = run_dir / "checkpoints"
if not checkpoint_root.is_dir() or checkpoint_root.is_symlink():
    raise SystemExit("existing pilot checkpoint root is invalid")
required = {"adapter_config.json", "adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth", "trainer_state.json", "training_args.bin"}
valid = []
for path in checkpoint_root.glob("checkpoint-*"):
    match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", path.name)
    if not match or not path.is_dir() or path.is_symlink():
        continue
    step = int(match.group(1))
    if step > config.max_steps or step % config.save_steps != 0:
        continue
    files = [path / name for name in required]
    if any(not item.is_file() or item.is_symlink() or item.stat().st_size <= 0 for item in files):
        continue
    try:
        state = json.loads((path / "trainer_state.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        continue
    if isinstance(state, dict) and state.get("global_step") == step:
        valid.append((step, path))
if not valid:
    raise SystemExit("incomplete pilot has no valid Trainer checkpoint; preserve it and return to control-plane recovery")
_, selected = max(valid)
resolved, source = _resolve_resume_checkpoint(run_dir, selected)
before = (run_dir / "run.json").read_bytes()
_validate_resume_run(
    run_dir=run_dir, config=config, seed=42, parent_sft=parent,
    dataset_hash=_file_hash(config.dataset_path, description="GRPO dataset"),
    config_hash=_config_hash(config, seed=42), paired_definition_sha256=expected_pair,
    paired_components=components, environment=collect_environment(), resume_source=source,
)
if before != (run_dir / "run.json").read_bytes():
    raise SystemExit("resume identity validation must be read-only before attempt begin")
print(f"resume:{resolved}")
PY_RESUME
}

run_one() {
  local mode="$1" run_name="$2" run_dir="$3" action
  if ! action="$(resolve_run_action "$mode" "$run_dir")"; then
    write_evidence 125 125 identity_failed "$mode pilot is not safely fresh/resumable/completed"
    exit $?
  fi
  if [[ "$action" == "completed" ]]; then
    printf '[%s] %s pilot already completed; command skipped\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
    return 0
  fi
  local resume_args=()
  if [[ "$action" == resume:* ]]; then
    resume_args=(--resume-from-checkpoint "${action#resume:}")
    printf '[%s] %s pilot resume=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "${action#resume:}" >>"$LOG_FILE"
  elif [[ "$action" == "fresh" ]]; then
    printf '[%s] %s pilot fresh from formal B run=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "$run_name" >>"$LOG_FILE"
  else
    write_evidence 125 125 identity_failed "$mode pilot action is invalid"
    exit $?
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
      --output-dir "$PILOT_ROOT" \
      "${resume_args[@]}" > >(tee -a "$LOG_FILE") 2>&1; then
    printf '[%s] %s pilot command rc=0\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
  else
    local rc=$?
    write_evidence "$rc" 125 command_failed "$mode pilot train-grpo exited nonzero"
    exit $?
  fi
}

mkdir -p "$PILOT_ROOT"
run_one public "$PUBLIC_RUN_NAME" "$PUBLIC_RUN"
run_one hidden "$HIDDEN_RUN_NAME" "$HIDDEN_RUN"

CURRENT_PHASE="postcheck"
if "$PY" - "$PUBLIC_RUN" "$HIDDEN_RUN" "$B_RUN" "$HEAD_COMMIT" "$PAIR_SHA" "$PAIR_COMPONENTS_JSON" "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$GPU_NAME" "$POSTCHECK_FILE.tmp" <<'PY_POSTCHECK'
import json
import math
import sys
from collections import Counter
from pathlib import Path
from code_verifier.analysis import build_cost_row, load_training_curve_rows
from code_verifier.analysis.report import _REWARD_FIELDS, _ROLLOUT_FIELDS
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint

public_run, hidden_run, b_run = map(Path, sys.argv[1:4])
head, pair_sha, pair_components_json, open_r1, lock_sha, torch_version, cuda_version, gpu_name, output = sys.argv[4:13]
pair_components = json.loads(pair_components_json)
if not isinstance(pair_components, dict):
    raise SystemExit("paired component identity is invalid")
parent = load_completed_sft_checkpoint(b_run)

def load_rows(path: Path) -> list[dict[str, object]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise SystemExit(f"blank JSONL row: {path.name}")
        value = json.loads(line, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
        if not isinstance(value, dict):
            raise SystemExit(f"non-object JSONL row: {path.name}")
        rows.append(value)
    return rows


def finite_number(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SystemExit(f"nonfinite/nonnumeric value: {context}")
    return float(value)


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


def mean(values: list[float]) -> float:
    if not values:
        raise SystemExit("cannot summarize empty numeric series")
    result = sum(values) / len(values)
    if not math.isfinite(result):
        raise SystemExit("numeric series mean is nonfinite")
    return result


def p95(values: list[float]) -> float:
    if not values:
        raise SystemExit("cannot summarize empty numeric series")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def checkpoint_inventory(run_dir: Path) -> dict[str, object]:
    required = {
        "adapter_config.json", "adapter_model.safetensors", "optimizer.pt", "scheduler.pt",
        "rng_state.pth", "trainer_state.json", "training_args.bin",
    }
    inventory = []
    for step in (50, 100):
        path = run_dir / "checkpoints" / f"checkpoint-{step}"
        if not path.is_dir() or path.is_symlink():
            raise SystemExit(f"missing complete checkpoint-{step}")
        required_paths = [path / name for name in required]
        if any(not item.is_file() or item.is_symlink() or item.stat().st_size <= 0 for item in required_paths):
            raise SystemExit(f"incomplete checkpoint-{step}")
        state = json.loads((path / "trainer_state.json").read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("global_step") != step:
            raise SystemExit(f"checkpoint-{step} global_step mismatch")
        files = [item for item in path.rglob("*") if item.is_file() and not item.is_symlink()]
        inventory.append({"step": step, "bytes": sum(item.stat().st_size for item in files), "inodes": len(files)})
    return {
        "checkpoints": inventory,
        "max_checkpoint_bytes": max(item["bytes"] for item in inventory),
        "max_checkpoint_inodes": max(item["inodes"] for item in inventory),
    }


def check_run(run_dir: Path, mode: str, run_id: str) -> dict[str, object]:
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.run_id != run_id or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != pair_sha:
        raise SystemExit(f"{mode} strict identity mismatch")
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    expected = {
        "status": "completed", "run_id": run_id, "reward_mode": mode, "paired_definition_sha256": pair_sha,
        "seed": 42, "git_commit": head, "open_r1_commit": open_r1, "dependency_lock_hash": lock_sha,
        "torch_version": torch_version, "cuda_version": cuda_version, "gpu_name": gpu_name,
        "gpu_count_used": 1, "global_step": 100,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise SystemExit(f"{mode} metadata mismatch: {key}")
    for key, value in pair_components.items():
        if metadata.get(key) != value:
            raise SystemExit(f"{mode} paired component mismatch: {key}")
    attempts = metadata.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise SystemExit(f"{mode} attempts missing")
    attempt_total = 0.0
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict) or attempt.get("attempt") != index or attempt.get("status") not in {"running", "failed", "completed"}:
            raise SystemExit(f"{mode} attempt history invalid")
        hours = finite_number(attempt.get("gpu_hours"), f"{mode} attempt gpu_hours")
        if hours < 0 or (attempt.get("status") == "running" and hours != 0.0):
            raise SystemExit(f"{mode} attempt gpu_hours invalid")
        attempt_total += hours
    gpu_hours = finite_number(metadata.get("gpu_hours"), f"{mode} cumulative gpu_hours")
    if attempts[-1].get("status") != "completed" or gpu_hours <= 0 or not math.isclose(gpu_hours, attempt_total, rel_tol=0.0, abs_tol=1e-12):
        raise SystemExit(f"{mode} cumulative gpu_hours invalid")
    for key in ("peak_cuda_memory_allocated_bytes", "peak_cuda_memory_reserved_bytes"):
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SystemExit(f"{mode} {key} invalid")

    metrics = load_rows(run_dir / "metrics.jsonl")
    require_finite(metrics, f"{mode} metrics")
    trainer_rows = [row for row in metrics if row.get("record_type") == "trainer"]
    step_rows = {}
    for row in trainer_rows:
        step_value = row.get("step")
        if isinstance(step_value, bool) or not isinstance(step_value, (int, float)) or not float(step_value).is_integer():
            continue
        step = int(step_value)
        if 1 <= step <= 100 and "reward" in row:
            if step in step_rows:
                raise SystemExit(f"{mode} duplicate trainer step telemetry")
            step_rows[step] = row
    if set(step_rows) != set(range(1, 101)):
        raise SystemExit(f"{mode} trainer telemetry does not cover steps 1..100")
    if not metrics or metrics[-1].get("record_type") != "summary" or metrics[-1].get("global_step") != 100:
        raise SystemExit(f"{mode} metrics summary incomplete")
    def series(name: str) -> list[float]:
        return [finite_number(step_rows[i].get(name), f"{mode} {name} step {i}") for i in range(1, 101)]

    reward_series = series("reward")
    reward_std_series = series("reward_std")
    kl_series = series("kl")
    loss_series = series("loss")
    completion_mean_series = series("completions/mean_length")
    clipped_series = series("completions/clipped_ratio")
    zero_std_series = series("frac_reward_zero_std")
    generation_seconds = series("generation_runtime_seconds")
    rollout_seconds = series("rollout_runtime_seconds")
    no_grad_logps_seconds = series("no_grad_logps_runtime_seconds")
    no_grad_logps_calls = series("no_grad_logps_calls")
    step_seconds = series("step_runtime_seconds")
    for index, (generation, rollout, no_grad, calls, step) in enumerate(
        zip(generation_seconds, rollout_seconds, no_grad_logps_seconds, no_grad_logps_calls, step_seconds), 1
    ):
        if generation < 0 or rollout < generation or no_grad < 0 or step < rollout + no_grad:
            raise SystemExit(f"{mode} timing decomposition invalid at step {index}")
        if calls != 8.0:
            raise SystemExit(f"{mode} no-grad reference log-prob call count changed at step {index}: {calls}")

    rollouts = load_rows(run_dir / "rollouts.jsonl")
    rewards = load_rows(run_dir / "rewards.jsonl")
    groups = load_rows(run_dir / "group_metrics.jsonl")
    if not rollouts or not rewards or not groups or len(rollouts) != len(rewards):
        raise SystemExit(f"{mode} reward evidence incomplete")
    if any(set(row) != _ROLLOUT_FIELDS or row.get("reward_mode") != mode for row in rollouts):
        raise SystemExit(f"{mode} rollout schema/source mismatch")
    if any(set(row) != _REWARD_FIELDS or row.get("mode") != mode for row in rewards):
        raise SystemExit(f"{mode} reward schema/source mismatch")
    group_fields = {"group_index", "problem_id", "reward_mode", "sample_count", "mean", "std", "all_equal"}
    if any(set(row) != group_fields or row.get("reward_mode") != mode or row.get("sample_count") != 4 for row in groups):
        raise SystemExit(f"{mode} group schema/source mismatch")
    if any(row.get("infrastructure_failure") is not False for row in rewards):
        raise SystemExit(f"{mode} reward path contains infrastructure failures")
    if not any(row.get("executed") is True for row in rewards):
        raise SystemExit(f"{mode} reward path contains no real executed completion")
    require_finite(rewards, f"{mode} rewards")
    require_finite(groups, f"{mode} groups")
    if any(any(key in row for key in ("prompt", "visible_tests", "train_hidden_tests", "eval_hidden_tests")) for row in rollouts):
        raise SystemExit(f"{mode} rollout contains forbidden test payload")

    curve = load_training_curve_rows(run_dir, method=f"{mode}-pilot")
    cost = build_cost_row(run_dir, method=f"{mode}-pilot", gpu_hour_cost_usd=None)
    if not curve or not math.isfinite(cost.gpu_hours) or cost.gpu_hours <= 0 or not isinstance(cost.generated_tokens, int) or cost.generated_tokens <= 0:
        raise SystemExit(f"{mode} curve/cost loader failed")
    token_counts = [finite_number(row.get("completion_token_count"), f"{mode} completion token count") for row in rollouts]
    group_std = [finite_number(row.get("std"), f"{mode} group std") for row in groups]
    group_mean = [finite_number(row.get("mean"), f"{mode} group mean") for row in groups]
    executor_ms = [finite_number(row.get("executor_runtime_ms"), f"{mode} executor runtime") for row in rewards]
    if any(value < 0 for value in executor_ms):
        raise SystemExit(f"{mode} executor runtime negative")
    component_names = ("test_reward", "executable_reward", "timeout_penalty", "invalid_format_penalty", "total_reward")
    component_means = {name: mean([finite_number(row.get(name), f"{mode} {name}") for row in rewards]) for name in component_names}
    statuses = Counter(str(row.get("status")) for row in rewards)
    failure_counts = Counter()
    for row in rewards:
        value = row.get("failure_counts")
        if not isinstance(value, dict):
            raise SystemExit(f"{mode} failure_counts invalid")
        for key, count in value.items():
            if not isinstance(key, str) or isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise SystemExit(f"{mode} failure_counts entry invalid")
            failure_counts[key] += count
    test_rows = [row for row in rewards if isinstance(row.get("total_tests"), int) and not isinstance(row.get("total_tests"), bool) and row.get("total_tests", 0) > 0]
    pass_rows = [row for row in test_rows if row.get("passed_tests") == row.get("total_tests")]
    train_runtime = finite_number(metrics[-1].get("train_runtime"), f"{mode} train_runtime")
    if train_runtime <= 0:
        raise SystemExit(f"{mode} train_runtime is not positive")
    total_executor_seconds = sum(executor_ms) / 1000.0
    total_generation_seconds = sum(generation_seconds)
    total_rollout_seconds = sum(rollout_seconds)
    total_no_grad_logps_seconds = sum(no_grad_logps_seconds)
    total_step_seconds = sum(step_seconds)
    if min(total_generation_seconds, total_rollout_seconds, total_step_seconds) <= 0:
        raise SystemExit(f"{mode} timing totals are not positive")

    stop = {
        "trainer_reward_series": reward_series,
        "trainer_reward_std_series": reward_std_series,
        "trainer_kl_series": kl_series,
        "trainer_loss_series": loss_series,
        "trainer_completion_mean_length_series": completion_mean_series,
        "trainer_completion_clipped_ratio_series": clipped_series,
        "trainer_frac_reward_zero_std_series": zero_std_series,
        "generation_runtime_seconds_series": generation_seconds,
        "rollout_runtime_seconds_series": rollout_seconds,
        "no_grad_logps_runtime_seconds_series": no_grad_logps_seconds,
        "no_grad_logps_calls_series": no_grad_logps_calls,
        "step_runtime_seconds_series": step_seconds,
        "group_reward_std_series": group_std,
        "group_reward_mean_series": group_mean,
        "reward_mean": mean(reward_series),
        "reward_std_mean": mean(reward_std_series),
        "kl_mean": mean(kl_series),
        "kl_max": max(kl_series),
        "loss_mean": mean(loss_series),
        "completion_mean_tokens": mean(token_counts),
        "completion_truncation_rate": sum(1 for row in rollouts if row.get("truncated") is True) / len(rollouts),
        "parsed_rate": sum(1 for row in rewards if row.get("parsed") is True) / len(rewards),
        "executed_rate": sum(1 for row in rewards if row.get("executed") is True) / len(rewards),
        "timeout_rate": sum(1 for row in rewards if row.get("status") == "timeout") / len(rewards),
        "pass_rate": len(pass_rows) / len(test_rows) if test_rows else 0.0,
        "sandbox_infrastructure_failure_rate": sum(1 for row in rewards if row.get("infrastructure_failure") is True) / len(rewards),
        "mean_executor_runtime_ms": mean(executor_ms),
        "total_executor_runtime_ms": sum(executor_ms),
        "executor_runtime_fraction_of_train": total_executor_seconds / train_runtime,
        "executor_runtime_fraction_of_rollout": total_executor_seconds / total_rollout_seconds,
        "generation_runtime_mean_seconds": mean(generation_seconds),
        "generation_runtime_p95_seconds": p95(generation_seconds),
        "generation_runtime_max_seconds": max(generation_seconds),
        "rollout_runtime_mean_seconds": mean(rollout_seconds),
        "rollout_runtime_p95_seconds": p95(rollout_seconds),
        "rollout_runtime_max_seconds": max(rollout_seconds),
        "no_grad_logps_runtime_mean_seconds": mean(no_grad_logps_seconds),
        "no_grad_logps_runtime_p95_seconds": p95(no_grad_logps_seconds),
        "no_grad_logps_runtime_max_seconds": max(no_grad_logps_seconds),
        "step_runtime_mean_seconds": mean(step_seconds),
        "step_runtime_p95_seconds": p95(step_seconds),
        "step_runtime_max_seconds": max(step_seconds),
        "generation_fraction_of_step": total_generation_seconds / total_step_seconds,
        "rollout_fraction_of_step": total_rollout_seconds / total_step_seconds,
        "no_grad_logps_fraction_of_step": total_no_grad_logps_seconds / total_step_seconds,
        "generated_tokens_per_generation_second": cost.generated_tokens / total_generation_seconds,
        "group_all_equal_rate": sum(1 for row in groups if row.get("all_equal") is True) / len(groups),
        "group_std_mean": mean(group_std),
        "reward_component_means": component_means,
        "status_counts": dict(sorted(statuses.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
        "train_runtime_seconds": train_runtime,
        "mean_step_seconds": mean(step_seconds),
        "reward_source": "visible_tests" if mode == "public" else "train_hidden_tests",
        "rollout_runtime_seconds_recorded": True,
        "threshold_decision": "raw_metrics_only_no_unsealed_thresholds",
    }
    require_finite(stop, f"{mode} stop-condition telemetry")
    inventory = checkpoint_inventory(run_dir)
    return {
        "run_id": run_id,
        "reward_mode": mode,
        "paired_definition_sha256": pair_sha,
        "parent_sft_run_id": identity.parent_sft.run_id,
        "global_step": 100,
        "gpu_hours": gpu_hours,
        "attempt_count": len(attempts),
        "peak_cuda_memory_allocated_bytes": metadata["peak_cuda_memory_allocated_bytes"],
        "peak_cuda_memory_reserved_bytes": metadata["peak_cuda_memory_reserved_bytes"],
        "trainer_metric_rows": len(trainer_rows),
        "curve_rows": len(curve),
        "rollout_rows": len(rollouts),
        "reward_rows": len(rewards),
        "group_rows": len(groups),
        "executor_hours": cost.executor_hours,
        "generated_tokens": cost.generated_tokens,
        "stop_condition_telemetry": stop,
        **inventory,
    }


public = check_run(public_run, "public", "C-public-grpo-pilot100-seed42")
hidden = check_run(hidden_run, "hidden", "D-hidden-grpo-pilot100-seed42")
if public["stop_condition_telemetry"]["reward_source"] == hidden["stop_condition_telemetry"]["reward_source"]:
    raise SystemExit("Public/Hidden reward sources unexpectedly match")
summary = {
    "version": 1,
    "status": "passed",
    "decision_policy": "record raw spec-12.4 metrics only; operator script invents no numerical stopping threshold",
    "paired_definition_sha256": pair_sha,
    "public": public,
    "hidden": hidden,
    "max_complete_trainer_checkpoint_bytes": max(public["max_checkpoint_bytes"], hidden["max_checkpoint_bytes"]),
    "max_complete_trainer_checkpoint_inodes": max(public["max_checkpoint_inodes"], hidden["max_checkpoint_inodes"]),
}
Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY_POSTCHECK
then
  mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"
else
  rc=$?
  rm -f "$POSTCHECK_FILE.tmp"
  write_evidence 0 "$rc" postcheck_failed "paired pilot postcheck failed"
  exit $?
fi

CURRENT_PHASE="complete"
write_evidence 0 0 passed "paired 100-step C/D pilot and raw spec-12.4 telemetry passed; formal training was not started"
exit $?

