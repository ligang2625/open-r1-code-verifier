#!/usr/bin/env bash
set -Eeuo pipefail
PLAN_COMMIT="8464e69691c527c7""26a2e28e5a7ca81f""a2001bbf"
RESULT_CODE_COMMIT="ed3eaea93ba897c3""8e3b3ff7b95903d3""1f7e76d2"
C13_EVIDENCE_SHA="91647fa09354f1db""af486b7d94960934""3914674706654010""22493ad5fb87d50b"
WORKFLOW_TRANSPORT_COMMIT="b4ac6acb95530f53""59566e6f140f77ad""6a4da78f"
C13_CHECKPOINT_COMMIT="945764a99e3a1bed""53afbff830fddc84""181e215f"
C12_CHECKPOINT_COMMIT="355486ccccff3a13""25614e18e8f8d4a8""5b8789ba"
C13_STATUS_SHA="9a271f2a916b0b6e""e6cecb2426f0b320""6ef074578be55d9b""c94f6f3fe3ab86aa"
C13_LOG_SHA="98e5f0740b80d55b""ed544ae050394d1b""be23ef6154944c21""69224742d14359f8"
C13_POSTCHECK_SHA="91d4825b86a325a8""f9765bfb9d99ab51""345051c046c9847c""fe335aadad487b2f"
C13_PUBLIC_ADAPTER_SHA="55e1860b2cdd5a3e""6b497724f2519b5c""f0ee5825273545f8""042f039d916c19e9"
C13_HIDDEN_ADAPTER_SHA="29afca9c80537d71""2c2c388dfdcd8eef""822a91d772381367""389c5d18d57805d3"
EXPECTED_PILOT_PAIR_SHA="bb8a733b2f6b9519""d6e9c9de087461a9""75ba830f6c132a8f""06120881576b512f"
EXPECTED_FORMAL_PAIR_SHA="7924be4e115b20bc""3e40207256d67d2e""8591c973dbd9de7b""fcb0b4bf39b08df3"
EXPECTED_PUBLIC_PAIR_CONFIG_SHA="1ec25400fd1f6d6e""c46d636ac84db909""8de6559fa327fd63""d3e8f7364f650271"
EXPECTED_HIDDEN_PAIR_CONFIG_SHA="330ce6ce4a8ba374""3927bd3f38bd4692""a3616483bd8cd2fe""1727c455c55a9f71"
EXPECTED_TRANSPORT_POLICY_SHA="d7e7b3a3a2f6492c""f6040c08a64086fb""a3aa7a9c4f520975""2a0ba2917ef81c85"
EXPECTED_MACHINE_SHA="b2230476c3d76004""77108db5684ba2ef""bef95b89f746b8d8""a1bc83b88ba5cab7"
EXPECTED_READINESS_SHA="5e3a42ac4f99d831""2f876bd4f7ac70b3""5d5b3db27a7ca7c8""c96a7196b019e45d"
HISTORICAL_PISTON_IDENTITY_SHA="19e978bacadea8ff""1ac358b3e19efb68""f395740200faa460""b0f17b706c283d79"
PUBLIC_DATA_SHA="94ef48888d2b2eda""a0080b9b412c274a""da692c9546fe1355""72d48ab20fd49223"
HIDDEN_DATA_SHA="79af3c2a3742e0cd""a8d02901a07241af""ce12a54c0b6d334""e3012bcd0b69f77f7"
B_DATASET_SHA="4b90cf95de2d8f12""bdc98decbfb712b8""eacf5987b02b02b8""68075ed9ca69eb0c"
B_CONFIG_SHA="250fbc15ececb040""d2b90d3cb1606e41""2d1256e10ab9063c""073c4ad2b1fb5244"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7""f9d889d1969d8771""5c83ccb09ed95766""a50f81d9d762d560"
B_ADAPTER_MODEL_SHA="51042ea9c52d2d24""976c2ca4e777f1a5""f792e3943ff171d0""3e55b959463a7a67"
B_ADAPTER_CONFIG_SHA="3738f9ef0ac56f90""a48497ab4c0a1f17""2770864aa61dad56""e8d9751050f34344"
MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION="2e1fd397ee46e138""8853d2af2c993145""b0f1098a"
MODEL_WEIGHTS_SHA="c1b9b30e90795051""6ba3c646bdf570d8""084c25a6410a0cdc""a80cf04b11bc13a8"
OPEN_R1_COMMIT="1416fa0cf21595d2""083b399a2a0bbddd""7f6e9563"
PISTON_DEFINITION_SHA="f049f4ea344285e2""b732bb2a602e7c88""88ae3ac449320039""144c8a0dff62657e"

PLAN_REL="ai-work/planner/WP7-c-plan.md"
REPORT_REL="ai-work/executor/WP7-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP7-c/grpo-cd-formal/C15/run.sh"
PUBLIC_CONFIG_REL="configs/grpo/public.yaml"
HIDDEN_CONFIG_REL="configs/grpo/hidden.yaml"
PISTON_CONFIG_REL="configs/execution/piston-local.yaml"
TRANSPORT_POLICY_REL="configs/execution/piston-transport-resilience.yaml"
B_RUN_NAME="B-sft-formal-seed42"
PUBLIC_RUN_NAME="C-public-grpo-formal-seed42"
HIDDEN_RUN_NAME="D-hidden-grpo-formal-seed42"
PILOT_PUBLIC_RUN_NAME="C-public-grpo-pilot100-retry1-seed42"
PILOT_HIDDEN_RUN_NAME="D-hidden-grpo-pilot100-retry1-seed42"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
[[ -x "$PY" && -x "$CV" ]] || { echo "target checkout .venv is unavailable; do not start formal GRPO" >&2; exit 125; }

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
IFS="$TAB" read -r BOOTSTRAP_COMMIT MACHINE_OPEN_R1 ARTIFACT_ROOT TARGET_HF_HOME FORMAL_DATA_ROOT READINESS_RECORD HISTORICAL_PISTON_IDENTITY_RECORD PISTON_ENDPOINT PISTON_HOST_ID <<<"$MACHINE_FIELDS"

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
FORMAL_ROOT="$ARTIFACT_ROOT/grpo"
PUBLIC_RUN="$FORMAL_ROOT/$PUBLIC_RUN_NAME"
HIDDEN_RUN="$FORMAL_ROOT/$HIDDEN_RUN_NAME"
PUBLIC_TRANSPORT_SIDECAR="$FORMAL_ROOT/transport-telemetry/$PUBLIC_RUN_NAME.json"
HIDDEN_TRANSPORT_SIDECAR="$FORMAL_ROOT/transport-telemetry/$HIDDEN_RUN_NAME.json"
C13_OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/grpo-cd-pilot/C13"
C13_STATUS_FILE="$C13_OP_ROOT/status"
C13_LOG_FILE="$C13_OP_ROOT/terminal.log"
C13_EVIDENCE_FILE="$C13_OP_ROOT/operator-evidence.json"
C13_POSTCHECK_FILE="$C13_OP_ROOT/postcheck-summary.json"
PILOT_ROOT="$ARTIFACT_ROOT/grpo-validation/pilot"
PILOT_PUBLIC_RUN="$PILOT_ROOT/$PILOT_PUBLIC_RUN_NAME"
PILOT_HIDDEN_RUN="$PILOT_ROOT/$PILOT_HIDDEN_RUN_NAME"

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

HEAD_COMMIT="" SCRIPT_SHA="" READINESS_SHA="" HISTORICAL_PISTON_IDENTITY_RECORD_SHA=""
GPU_NAME="" GPU_VRAM_MIB="0" PAIR_SHA="" PAIR_COMPONENTS_JSON="{}"
TRANSPORT_POLICY_SHA="" TRANSPORT_POLICY_FILE_SHA="" CURRENT_OPEN_R1="" CURRENT_LOCK_SHA="" CURRENT_TORCH="" CURRENT_CUDA=""
PILOT_MAX_CHECKPOINT_BYTES="0" PILOT_MAX_CHECKPOINT_INODES="0" REQUIRED_STORAGE_BYTES="0" REQUIRED_STORAGE_INODES="0"
PUBLIC_ACTION="unresolved" HIDDEN_ACTION="unresolved" CURRENT_PHASE="preflight"

write_evidence() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [[ -n "$HEAD_COMMIT" ]] || HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$SCRIPT_SHA" ]] || SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$REPO_ROOT" "$MACHINE_POINTER" "$READINESS_RECORD" "$HISTORICAL_PISTON_IDENTITY_RECORD" \
    "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" "$HEAD_COMMIT" "$PLAN_COMMIT" "$RESULT_CODE_COMMIT" "$WORKFLOW_TRANSPORT_COMMIT" "$SCRIPT_SHA" \
    "$MACHINE_SHA" "$READINESS_SHA" "$HISTORICAL_PISTON_IDENTITY_RECORD_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" "$PISTON_ENDPOINT" "$PISTON_HOST_ID" \
    "$PAIR_SHA" "$TRANSPORT_POLICY_SHA" "$TRANSPORT_POLICY_FILE_SHA" "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" \
    "$PUBLIC_ACTION" "$HIDDEN_ACTION" "$PILOT_MAX_CHECKPOINT_BYTES" "$PILOT_MAX_CHECKPOINT_INODES" "$REQUIRED_STORAGE_BYTES" \
    "$REQUIRED_STORAGE_INODES" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" "$PISTON_DEFINITION_SHA" \
    "$C13_CHECKPOINT_COMMIT" "$C13_EVIDENCE_SHA" "$C13_POSTCHECK_SHA" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path
(
    output, postcheck_path, repo_root, machine_pointer, readiness_record, historical_piston_record,
    artifact_root, hf_home, formal_data_root, checkpoint_commit, source_plan_commit, result_code_commit,
    workflow_transport_commit, script_sha, machine_sha, readiness_sha, historical_piston_sha, gpu_name,
    gpu_vram_mib, piston_endpoint, piston_host_id, pair_sha, transport_policy_sha, transport_policy_file_sha,
    open_r1_commit, dependency_lock_sha, torch_version, cuda_version, public_action, hidden_action,
    pilot_checkpoint_bytes, pilot_checkpoint_inodes, required_storage_bytes, required_storage_inodes,
    command_rc, postcheck_rc, gate_status, note, start_time, end_time, attempt_id, piston_definition_sha,
    c13_checkpoint_commit, c13_evidence_sha, c13_postcheck_sha,
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
formal_root = Path(artifact_root) / "grpo"
files = []
for run_name in ("C-public-grpo-formal-seed42", "D-hidden-grpo-formal-seed42"):
    run = formal_root / run_name
    for relative in (
        "run.json", "resolved_config.yaml", "environment.json", "metrics.jsonl", "rollouts.jsonl",
        "rewards.jsonl", "group_metrics.jsonl", "checkpoints/checkpoint-300/code_verifier_log_state.json",
        "checkpoints/adapter_config.json", "checkpoints/adapter_model.safetensors",
    ):
        files.append(inventory(run / relative))
    files.append(inventory(formal_root / "transport-telemetry" / f"{run_name}.json"))
if postcheck_file.is_file():
    files.append(inventory(postcheck_file))
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP7-c",
    "source_plan_commit": source_plan_commit,
    "result_code_commit": result_code_commit,
    "workflow_transport_commit": workflow_transport_commit,
    "operator_checkpoint_commit": checkpoint_commit or None,
    "checkpoint_id": "C15",
    "operator_gate_id": "grpo-cd-formal",
    "operator_script": "ai-work/executor/operator/WP7-c/grpo-cd-formal/C15/run.sh",
    "operator_script_sha256": script_sha or None,
    "accepted_prior_gate": {
        "checkpoint_id": "C13",
        "operator_checkpoint_commit": c13_checkpoint_commit,
        "operator_evidence_sha256": c13_evidence_sha,
        "postcheck_sha256": c13_postcheck_sha,
        "pilot_review_conclusion": "no_spec_defined_hard_stop_signal",
    },
    "target_machine_pointer": machine_pointer,
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record": readiness_record,
    "target_readiness_record_sha256": readiness_sha or None,
    "historical_piston_identity_record": historical_piston_record,
    "historical_piston_identity_record_sha256": historical_piston_sha or None,
    "historical_piston_identity_note": "preserved provenance only; current reverse-SSH transport is validated live",
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
        "definition_sha256": piston_definition_sha,
        "python_runtime": "3.10.0",
        "transport_topology": "control_plane_reverse_ssh_loopback_forward",
        "transport_policy_sha256": transport_policy_sha or None,
        "transport_policy_file_sha256": transport_policy_file_sha or None,
        "transport_policy_path": "configs/execution/piston-transport-resilience.yaml",
        "retry_implementation_version": "piston-transport-retry-v2",
        "classifier_implementation_version": "httpclient-loopback-classifier-v3",
        "connection_implementation_version": "httpclient-single-keepalive-v1",
        "legacy_supervisor_implementation_version": "piston-tunnel-supervisor-v3",
        "operator_starts_tunnel": False,
    },
    "formal_pair": {
        "public_run_name": "C-public-grpo-formal-seed42",
        "hidden_run_name": "D-hidden-grpo-formal-seed42",
        "seed": 42,
        "paired_definition_sha256": pair_sha or None,
        "parent_b_run_name": "B-sft-formal-seed42",
        "public_reward_source": "visible_tests",
        "hidden_reward_source": "train_hidden_tests",
        "fresh_parent_policy": "both members independently initialize from completed B",
    },
    "run_actions": {"public": public_action, "hidden": hidden_action},
    "storage_gate": {
        "pilot_max_complete_checkpoint_bytes": int(pilot_checkpoint_bytes or 0),
        "pilot_max_complete_checkpoint_inodes": int(pilot_checkpoint_inodes or 0),
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

[[ "$MACHINE_SHA" == "$EXPECTED_MACHINE_SHA" ]] || fail_preflight "validation machine pointer SHA changed"
[[ "$MACHINE_OPEN_R1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "validation machine Open-R1 identity changed"
[[ "$PISTON_ENDPOINT" == "http://127.0.0.1:2000" && "$PISTON_HOST_ID" == "1660ti-wsl" ]] || fail_preflight "canonical loopback Piston endpoint/host changed"

HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve checkpoint HEAD"
PARENT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve checkpoint parent"
[[ "$PARENT_COMMIT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "formal operator checkpoint parent is not the accepted Phase-2 result-code commit"
git -C "$REPO_ROOT" merge-base --is-ancestor "$C13_CHECKPOINT_COMMIT" "$RESULT_CODE_COMMIT" || fail_preflight "C13 is not an ancestor of the Phase-2 result-code commit"
git -C "$REPO_ROOT" merge-base --is-ancestor "$WORKFLOW_TRANSPORT_COMMIT" "$RESULT_CODE_COMMIT" || fail_preflight "reverse-SSH workflow transport amendment is not in the result-code lineage"
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
expected_status = [f"M\t{report}", f"A\t{script}"]
if sorted(status) != sorted(expected_status):
    raise SystemExit(f"C15 checkpoint scope is not exactly append-only report + new script: {status}")
mode_line = subprocess.run(
    ["git", "-C", str(repo), "ls-tree", head, "--", script],
    check=True, capture_output=True, text=True,
).stdout.strip()
if not mode_line.startswith("100755 "):
    raise SystemExit("tracked C15 operator script is not executable")
previous = subprocess.run(
    ["git", "-C", str(repo), "show", f"{parent}:{report}"],
    check=True, capture_output=True,
).stdout
current = (repo / report).read_bytes()
if len(current) <= len(previous) or not current.startswith(previous):
    raise SystemExit("execution report is not byte-for-byte append-only")
PY_SCOPE
then
  fail_preflight "formal checkpoint scope/append-only provenance failed"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" <<'PY_META'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind("checkpoint_id: C15")
if pos < 0:
    raise SystemExit("C15 checkpoint block is missing")
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit("C15 checkpoint block is malformed")
block = text[start:end]
def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"C15 checkpoint field missing: {name}")
    return match.group(1).strip().strip('"').strip("'")
print("\t".join([
    field("source_plan_commit"), field("result_code_commit"), field("workflow_transport_commit"),
    field("operator_gate_id"), field("operator_handoff_mode"), field("operator_restart_policy"),
    field("operator_script_sha256"), field("formal_pair_sha256"), field("transport_policy_sha256"),
    field("accepted_c13_operator_evidence_sha256"), field("status"),
]))
PY_META
)" || fail_preflight "cannot parse C15 checkpoint metadata"
IFS="$TAB" read -r CHECKPOINT_PLAN CHECKPOINT_RESULT CHECKPOINT_WORKFLOW CHECKPOINT_GATE CHECKPOINT_MODE CHECKPOINT_RESTART EXPECTED_SCRIPT_SHA CHECKPOINT_PAIR CHECKPOINT_TRANSPORT CHECKPOINT_C13_EVIDENCE CHECKPOINT_STATUS <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" && "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "C15 source/result provenance mismatch"
[[ "$CHECKPOINT_WORKFLOW" == "$WORKFLOW_TRANSPORT_COMMIT" ]] || fail_preflight "C15 workflow transport provenance mismatch"
[[ "$CHECKPOINT_GATE" == "$GATE_ID" && "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_RESTART" == "trainer_checkpoint" ]] || fail_preflight "C15 handoff/gate/restart mismatch"
[[ "$CHECKPOINT_PAIR" == "$EXPECTED_FORMAL_PAIR_SHA" && "$CHECKPOINT_TRANSPORT" == "$EXPECTED_TRANSPORT_POLICY_SHA" ]] || fail_preflight "C15 formal pair/transport policy metadata mismatch"
[[ "$CHECKPOINT_C13_EVIDENCE" == "$C13_EVIDENCE_SHA" && "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "C15 accepted C13/status metadata mismatch"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked C15 operator script SHA differs from report"

[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -d "$DATA_DIR" ]] || fail_preflight "target persistent roots are unavailable"
[[ "$ARTIFACT_ROOT" != "$REPO_ROOT" && "$ARTIFACT_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "artifact_root must remain outside target checkout"
[[ "$FORMAL_DATA_ROOT" != "$REPO_ROOT" && "$FORMAL_DATA_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "formal_data_root must remain outside target checkout"
[[ "$TARGET_HF_HOME" != "$REPO_ROOT" && "$TARGET_HF_HOME" != "$REPO_ROOT/"* ]] || fail_preflight "hf_home must remain outside target checkout"
[[ -f "$READINESS_RECORD" && -f "$HISTORICAL_PISTON_IDENTITY_RECORD" ]] || fail_preflight "target readiness/historical Piston records are unavailable"
READINESS_SHA="$(sha256sum "$READINESS_RECORD" | awk '{print $1}')"
HISTORICAL_PISTON_IDENTITY_RECORD_SHA="$(sha256sum "$HISTORICAL_PISTON_IDENTITY_RECORD" | awk '{print $1}')"
[[ "$READINESS_SHA" == "$EXPECTED_READINESS_SHA" ]] || fail_preflight "readiness record SHA changed"
[[ "$HISTORICAL_PISTON_IDENTITY_RECORD_SHA" == "$HISTORICAL_PISTON_IDENTITY_SHA" ]] || fail_preflight "historical Piston identity record changed; preserve and review rather than rewrite"

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

RUNTIME_FIELDS="$($PY - "$REPO_ROOT" "$B_RUN" "$HEAD_COMMIT" "$OPEN_R1_COMMIT" "$DEPENDENCY_LOCK_SHA" <<'PY_RUNTIME'
import json
import sys
from pathlib import Path
import code_verifier
import open_r1
from code_verifier.environment import collect_environment
repo = Path(sys.argv[1]).resolve()
b_run = Path(sys.argv[2]).resolve()
head, expected_open_r1, expected_lock = sys.argv[3:6]
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
    if value.get("open_r1_commit") != expected_open_r1:
        raise SystemExit(f"{label} Open-R1 mismatch")
    if value.get("dependency_lock_hash") != expected_lock:
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
[[ "$(sha256sum "$REPO_ROOT/$PISTON_CONFIG_REL" | awk '{print $1}')" == "$PISTON_DEFINITION_SHA" ]] || fail_preflight "tracked scientific Piston definition SHA changed"

PAIR_FIELDS="$($PY - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" "$PUBLIC_DATA_SHA" "$HIDDEN_DATA_SHA" "$B_DATASET_SHA" "$B_CONFIG_SHA" "$DEPENDENCY_LOCK_SHA" "$MODEL_ID" "$MODEL_REVISION" "$EXPECTED_PUBLIC_PAIR_CONFIG_SHA" "$EXPECTED_HIDDEN_PAIR_CONFIG_SHA" "$EXPECTED_FORMAL_PAIR_SHA" <<'PY_PAIR'
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.data.leakage_checks import TrainingArtifactKind
from code_verifier.training import load_completed_sft_checkpoint
from code_verifier.training.grpo import _paired_definition, load_grpo_training_config, load_training_artifact, validate_grpo_artifact_pair, validate_grpo_config_pair
repo, data_dir, b_run = map(Path, sys.argv[1:4])
(public_data_sha, hidden_data_sha, b_data_sha, b_config_sha, lock_sha, model_id, model_revision,
 expected_public_config, expected_hidden_config, expected_pair) = sys.argv[4:14]
public_path = data_dir / "training/public_grpo.jsonl"
hidden_path = data_dir / "training/hidden_grpo.jsonl"
if hashlib.sha256(public_path.read_bytes()).hexdigest() != public_data_sha:
    raise SystemExit("formal Public dataset SHA mismatch")
if hashlib.sha256(hidden_path.read_bytes()).hexdigest() != hidden_data_sha:
    raise SystemExit("formal Hidden dataset SHA mismatch")
public_rows = load_training_artifact(public_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
hidden_rows = load_training_artifact(hidden_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
if len(public_rows) != 2500 or len(hidden_rows) != 2500:
    raise SystemExit("formal GRPO row count mismatch")
validate_grpo_artifact_pair(public_rows, hidden_rows)
parent = load_completed_sft_checkpoint(b_run)
expected_parent = {
    "run_id": "B-sft-formal-seed42", "model_id": model_id, "model_revision": model_revision,
    "dataset_hash": b_data_sha, "config_hash": b_config_sha, "dependency_lock_hash": lock_sha, "seed": 42,
}
for key, value in expected_parent.items():
    if getattr(parent, key) != value:
        raise SystemExit(f"formal B identity mismatch: {key}")
public = replace(load_grpo_training_config(repo / "configs/grpo/public.yaml"), dataset_path=public_path, run_name="C-public-grpo-formal-seed42")
hidden = replace(load_grpo_training_config(repo / "configs/grpo/hidden.yaml"), dataset_path=hidden_path, run_name="D-hidden-grpo-formal-seed42")
validate_grpo_config_pair(public, hidden)
if (public.max_steps, hidden.max_steps, public.save_steps, hidden.save_steps) != (300, 300, 50, 50):
    raise SystemExit("formal cadence is not exactly 300 steps / save 50")
pair_sha, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
expected_components = {
    "paired_definition_version": 2,
    "paired_public_config_hash": expected_public_config,
    "paired_hidden_config_hash": expected_hidden_config,
    "paired_public_dataset_hash": public_data_sha,
    "paired_hidden_dataset_hash": hidden_data_sha,
}
if components != expected_components:
    raise SystemExit("formal pair components differ from control-plane certification")
if pair_sha != expected_pair:
    raise SystemExit("formal pair SHA differs from control-plane certification")
print(f"{pair_sha}\t{json.dumps(components, sort_keys=True, separators=(',', ':'))}")
PY_PAIR
)" || fail_preflight "formal pair/B/data identity validation failed"
IFS="$TAB" read -r PAIR_SHA PAIR_COMPONENTS_JSON <<<"$PAIR_FIELDS"

TRANSPORT_FIELDS="$($PY - "$REPO_ROOT/$TRANSPORT_POLICY_REL" "$EXPECTED_TRANSPORT_POLICY_SHA" <<'PY_TRANSPORT'
import hashlib
import sys
from pathlib import Path
from code_verifier.execution.piston_resilience import (
    PISTON_TRANSPORT_CLASSIFIER_IMPLEMENTATION_VERSION,
    PISTON_TRANSPORT_CONNECTION_IMPLEMENTATION_VERSION,
    PISTON_TRANSPORT_RETRY_IMPLEMENTATION_VERSION,
    PISTON_TUNNEL_SUPERVISOR_IMPLEMENTATION_VERSION,
    load_piston_transport_policy,
    piston_transport_policy_sha256,
)
path = Path(sys.argv[1])
expected_identity = sys.argv[2]
policy = load_piston_transport_policy(path)
identity = piston_transport_policy_sha256(path)
if identity != expected_identity:
    raise SystemExit("transport policy identity differs from control-plane certification")
if policy.safe_retry_kinds != ("connection_refused", "preconnect_failure") or policy.max_attempts != 3:
    raise SystemExit("transport safe retry policy changed")
versions = (
    PISTON_TRANSPORT_RETRY_IMPLEMENTATION_VERSION,
    PISTON_TRANSPORT_CLASSIFIER_IMPLEMENTATION_VERSION,
    PISTON_TRANSPORT_CONNECTION_IMPLEMENTATION_VERSION,
    PISTON_TUNNEL_SUPERVISOR_IMPLEMENTATION_VERSION,
)
expected = (
    "piston-transport-retry-v2",
    "httpclient-loopback-classifier-v3",
    "httpclient-single-keepalive-v1",
    "piston-tunnel-supervisor-v3",
)
if versions != expected:
    raise SystemExit("transport implementation identity changed")
print(f"{identity}\t{hashlib.sha256(path.read_bytes()).hexdigest()}")
PY_TRANSPORT
)" || fail_preflight "transport resilience policy validation failed"
IFS="$TAB" read -r TRANSPORT_POLICY_SHA TRANSPORT_POLICY_FILE_SHA <<<"$TRANSPORT_FIELDS"

probe_piston() {
  "$PY" - "$REPO_ROOT/$PISTON_CONFIG_REL" "$REPO_ROOT/$TRANSPORT_POLICY_REL" <<'PY_PROBE'
import sys
from pathlib import Path
from code_verifier.execution import PistonExecutor, load_piston_executor_config
from code_verifier.execution.piston_resilience import load_piston_transport_policy
executor = PistonExecutor(
    load_piston_executor_config(Path(sys.argv[1])),
    transport_policy=load_piston_transport_policy(Path(sys.argv[2])),
)
if executor.validate_runtime() != "3.10.0":
    raise SystemExit("Piston Python runtime mismatch")
PY_PROBE
}
if ! probe_piston >>"$LOG_FILE" 2>&1; then
  fail_preflight "reverse-SSH loopback Piston health/runtime probe failed; operator does not start or repair the tunnel"
fi

if ! "$PY" - "$C13_STATUS_FILE" "$C13_LOG_FILE" "$C13_EVIDENCE_FILE" "$C13_POSTCHECK_FILE" "$PILOT_PUBLIC_RUN" "$PILOT_HIDDEN_RUN" "$B_RUN" "$C13_STATUS_SHA" "$C13_LOG_SHA" "$C13_EVIDENCE_SHA" "$C13_POSTCHECK_SHA" "$C13_CHECKPOINT_COMMIT" "$C12_CHECKPOINT_COMMIT" "$EXPECTED_PILOT_PAIR_SHA" "$C13_PUBLIC_ADAPTER_SHA" "$C13_HIDDEN_ADAPTER_SHA" <<'PY_C13'
import hashlib
import json
import sys
from pathlib import Path
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint
from code_verifier.training.grpo import _stream_log_file_state, _validate_resume_log_checkpoint
status_path, log_path, evidence_path, postcheck_path, public_run, hidden_run, b_run = map(Path, sys.argv[1:8])
(status_sha, log_sha, evidence_sha, postcheck_sha, c13_commit, c12_commit, pilot_pair,
 public_adapter_sha, hidden_adapter_sha) = sys.argv[8:17]
expected_sha = {status_path: status_sha, log_path: log_sha, evidence_path: evidence_sha, postcheck_path: postcheck_sha}
for path, expected in expected_sha.items():
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"accepted C13 artifact changed: {path.name}")
if status_path.read_text(encoding="utf-8").strip() != "0":
    raise SystemExit("accepted C13 status is not zero")
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
expected_evidence = {
    "version": 1, "stage_id": "WP7-c", "checkpoint_id": "C13", "operator_gate_id": "grpo-cd-pilot",
    "operator_checkpoint_commit": c13_commit, "command_rc": 0, "postcheck_rc": 0, "gate_status": "passed",
}
if not isinstance(evidence, dict) or any(evidence.get(key) != value for key, value in expected_evidence.items()):
    raise SystemExit("accepted C13 evidence provenance changed")
post = json.loads(postcheck_path.read_text(encoding="utf-8"))
if post.get("status") != "passed" or post.get("paired_definition_sha256") != pilot_pair:
    raise SystemExit("accepted C13 postcheck identity changed")
parent = load_completed_sft_checkpoint(b_run)
for run, mode, run_id, adapter_sha in (
    (public_run, "public", "C-public-grpo-pilot100-retry1-seed42", public_adapter_sha),
    (hidden_run, "hidden", "D-hidden-grpo-pilot100-retry1-seed42", hidden_adapter_sha),
):
    identity = load_completed_grpo_checkpoint(run)
    if identity.run_id != run_id or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != pilot_pair:
        raise SystemExit(f"accepted C13 {mode} strict identity changed")
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    if meta.get("status") != "completed" or meta.get("global_step") != 100 or meta.get("git_commit") != c12_commit:
        raise SystemExit(f"accepted C13 {mode} metadata changed")
    if hashlib.sha256((run / "checkpoints/adapter_model.safetensors").read_bytes()).hexdigest() != adapter_sha:
        raise SystemExit(f"accepted C13 {mode} final adapter changed")
    final_state = _validate_resume_log_checkpoint(run, run / "checkpoints/checkpoint-100")
    for name, expected in final_state["logs"].items():
        if _stream_log_file_state(run / name) != expected:
            raise SystemExit(f"accepted C13 {mode} canonical final stream changed: {name}")
    rewards = [json.loads(line) for line in (run / "rewards.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if len(rewards) != 800 or any(row.get("infrastructure_failure") is not False or row.get("status") == "sandbox_error" for row in rewards):
        raise SystemExit(f"accepted C13 {mode} canonical reward state changed")
public_meta = json.loads((public_run / "run.json").read_text(encoding="utf-8"))
hidden_meta = json.loads((hidden_run / "run.json").read_text(encoding="utf-8"))
if len(public_meta.get("attempts", [])) != 1 or len(hidden_meta.get("attempts", [])) != 2:
    raise SystemExit("accepted C13 attempt lineage changed")
second = hidden_meta["attempts"][1]
if second.get("code_commit") != c13_commit or second.get("resume_from_checkpoint") != "checkpoints/checkpoint-90":
    raise SystemExit("accepted C13 Hidden recovery lineage changed")
print("accepted_c13_pilot=PASS")
PY_C13
then
  fail_preflight "accepted C13 pilot evidence/artifacts changed"
fi

STORAGE_FIELDS="$($PY - "$ARTIFACT_ROOT" "$PILOT_PUBLIC_RUN" "$PILOT_HIDDEN_RUN" <<'PY_STORAGE'
import os
import re
import shutil
import sys
from pathlib import Path
root, public_run, hidden_run = map(Path, sys.argv[1:4])
max_bytes = 0
max_inodes = 0
for run in (public_run, hidden_run):
    checkpoints = run / "checkpoints"
    seen = []
    for path in checkpoints.iterdir():
        match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", path.name)
        if match is None:
            continue
        step = int(match.group(1))
        if step > 100 or path.is_symlink() or not path.is_dir():
            raise SystemExit("pilot checkpoint inventory is unsafe")
        files = [item for item in path.rglob("*") if item.is_file() and not item.is_symlink()]
        if not files:
            raise SystemExit("pilot checkpoint inventory contains an empty checkpoint")
        max_bytes = max(max_bytes, sum(item.stat().st_size for item in files))
        max_inodes = max(max_inodes, len(files))
        seen.append(step)
    if 100 not in seen:
        raise SystemExit("pilot checkpoint-100 is missing")
required_bytes = max(40 * 1024**3, 14 * max_bytes + 10 * 1024**3)
required_inodes = max(100000, 14 * max_inodes + 20000)
usage = shutil.disk_usage(root)
free_inodes = os.statvfs(root).f_favail
if usage.free < required_bytes:
    raise SystemExit(f"formal requires {required_bytes} free bytes; found {usage.free}")
if free_inodes < required_inodes:
    raise SystemExit(f"formal requires {required_inodes} free inodes; found {free_inodes}")
print(f"{max_bytes}\t{max_inodes}\t{required_bytes}\t{required_inodes}\t{usage.free}\t{free_inodes}")
PY_STORAGE
)" || fail_preflight "formal operator-start storage gate failed"
IFS="$TAB" read -r PILOT_MAX_CHECKPOINT_BYTES PILOT_MAX_CHECKPOINT_INODES REQUIRED_STORAGE_BYTES REQUIRED_STORAGE_INODES FREE_STORAGE_BYTES FREE_STORAGE_INODES <<<"$STORAGE_FIELDS"

resolve_run_action() {
  local mode="$1" run_dir="$2" sidecar="$3"
  "$PY" - "$REPO_ROOT" "$DATA_DIR" "$B_RUN" "$run_dir" "$sidecar" "$mode" "$HEAD_COMMIT" "$PAIR_SHA" "$TRANSPORT_POLICY_SHA" "$PISTON_DEFINITION_SHA" <<'PY_RESUME'
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
repo, data_dir, b_run, run_dir, sidecar = map(Path, sys.argv[1:6])
mode, head, expected_pair, expected_transport, expected_piston = sys.argv[6:11]
public = replace(load_grpo_training_config(repo / "configs/grpo/public.yaml"), dataset_path=data_dir / "training/public_grpo.jsonl", run_name="C-public-grpo-formal-seed42")
hidden = replace(load_grpo_training_config(repo / "configs/grpo/hidden.yaml"), dataset_path=data_dir / "training/hidden_grpo.jsonl", run_name="D-hidden-grpo-formal-seed42")
config = public if mode == "public" else hidden
parent = load_completed_sft_checkpoint(b_run)
pair_sha, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
if pair_sha != expected_pair:
    raise SystemExit("formal pair SHA changed after preflight")
if not run_dir.exists():
    if sidecar.exists():
        raise SystemExit("formal run is absent but transport sidecar already exists")
    print("fresh")
    raise SystemExit(0)
if not run_dir.is_dir() or run_dir.is_symlink() or not (run_dir / "run.json").is_file():
    raise SystemExit("existing formal run path is invalid")
metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
if not isinstance(metadata, dict) or metadata.get("git_commit") != head:
    raise SystemExit("existing formal run belongs to a different operator checkpoint; preserve it for control-plane review")
if not sidecar.is_file() or sidecar.is_symlink():
    raise SystemExit("existing formal run transport sidecar is missing or unsafe")
sidecar_value = json.loads(sidecar.read_text(encoding="utf-8"))
sidecar_fields = {
    "version", "run_name", "piston_definition_sha256", "piston_transport_policy_sha256",
    "telemetry_semantics", "telemetry",
}
if not isinstance(sidecar_value, dict) or set(sidecar_value) != sidecar_fields:
    raise SystemExit("existing formal transport sidecar schema mismatch")
if (
    sidecar_value.get("version") != 1
    or sidecar_value.get("run_name") != config.run_name
    or sidecar_value.get("piston_definition_sha256") != expected_piston
    or sidecar_value.get("piston_transport_policy_sha256") != expected_transport
    or sidecar_value.get("telemetry_semantics") != "cumulative_durable_snapshot_per_mutation_v1"
):
    raise SystemExit("existing formal transport sidecar identity mismatch")
if metadata.get("status") == "completed":
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.run_id != config.run_name or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != expected_pair:
        raise SystemExit("completed formal run identity mismatch")
    print("completed")
    raise SystemExit(0)
if metadata.get("status") not in {"running", "failed"}:
    raise SystemExit("existing formal run status is not resumable")
selected = _latest_valid_resume_checkpoint(run_dir, config)
if selected is None:
    raise SystemExit("incomplete formal run has no valid Trainer+canonical-sidecar checkpoint; preserve it for control-plane recovery")
match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", selected.name)
step = int(match.group(1)) if match else -1
if step < 50 or step > 300 or step % 50 != 0:
    raise SystemExit(f"formal resume selected unsafe checkpoint step {step}")
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

if ! PUBLIC_ACTION="$(resolve_run_action public "$PUBLIC_RUN" "$PUBLIC_TRANSPORT_SIDECAR")"; then
  fail_preflight "Public formal run is not safely fresh/resumable/completed"
fi
if ! HIDDEN_ACTION="$(resolve_run_action hidden "$HIDDEN_RUN" "$HIDDEN_TRANSPORT_SIDECAR")"; then
  fail_preflight "Hidden formal run is not safely fresh/resumable/completed"
fi
printf '[%s] preflight PASS: accepted-C13/formal-pair/Piston-policy/reverse-SSH-runtime/storage actions public=%s hidden=%s required_bytes=%s required_inodes=%s free_bytes=%s free_inodes=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PUBLIC_ACTION" "$HIDDEN_ACTION" "$REQUIRED_STORAGE_BYTES" "$REQUIRED_STORAGE_INODES" "$FREE_STORAGE_BYTES" "$FREE_STORAGE_INODES" >>"$LOG_FILE"

run_one() {
  local mode="$1" run_name="$2" action="$3"
  if [[ "$action" == "completed" ]]; then
    printf '[%s] %s formal already completed; command skipped\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
    return 0
  fi
  local resume_args=()
  if [[ "$action" == resume:* ]]; then
    resume_args=(--resume-from-checkpoint "${action#resume:}")
    printf '[%s] %s formal resume=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "${action#resume:}" >>"$LOG_FILE"
  elif [[ "$action" == "fresh" ]]; then
    printf '[%s] %s formal fresh from formal B run=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "$run_name" >>"$LOG_FILE"
  else
    write_evidence 125 125 identity_failed "$mode formal action is invalid"
    exit $?
  fi
  CURRENT_PHASE="piston-$mode"
  if ! probe_piston >>"$LOG_FILE" 2>&1; then
    write_evidence 2 125 infrastructure_failed "$mode formal reverse-SSH loopback Piston is unavailable immediately before train-grpo"
    exit $?
  fi
  printf '[%s] %s formal Piston health/runtime probe PASS immediately before train-grpo; operator did not start or restart tunnel\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
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
      --piston-transport-policy "$REPO_ROOT/$TRANSPORT_POLICY_REL" \
      --seed 42 \
      --output-dir "$FORMAL_ROOT" \
      "${resume_args[@]}" > >(tee -a "$LOG_FILE") 2>&1; then
    printf '[%s] %s formal command rc=0\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
  else
    local rc=$?
    write_evidence "$rc" 125 command_failed "$mode formal train-grpo exited nonzero"
    exit $?
  fi
}

mkdir -p "$FORMAL_ROOT"
run_one public "$PUBLIC_RUN_NAME" "$PUBLIC_ACTION"
run_one hidden "$HIDDEN_RUN_NAME" "$HIDDEN_ACTION"

CURRENT_PHASE="postcheck"
if "$PY" - "$PUBLIC_RUN" "$HIDDEN_RUN" "$PUBLIC_TRANSPORT_SIDECAR" "$HIDDEN_TRANSPORT_SIDECAR" "$B_RUN" "$HEAD_COMMIT" "$PAIR_SHA" "$PAIR_COMPONENTS_JSON" "$TRANSPORT_POLICY_SHA" "$PISTON_DEFINITION_SHA" "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$GPU_NAME" "$POSTCHECK_FILE.tmp" <<'PY_POSTCHECK'
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from code_verifier.analysis import build_cost_row, load_training_curve_rows
from code_verifier.analysis.report import _REWARD_FIELDS, _ROLLOUT_FIELDS
from code_verifier.execution.piston_resilience import PistonTransportTelemetry
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint
from code_verifier.training.grpo import (
    GRPOTrainingError,
    _GRPO_LOG_STATE_FILENAME,
    _GRPO_STREAM_LOG_NAMES,
    _GRPO_TRAINER_RESUME_FILES,
    _stream_log_file_state,
    _validate_resume_log_checkpoint,
)
public_run, hidden_run, public_transport, hidden_transport, b_run = map(Path, sys.argv[1:6])
head, pair_sha, pair_components_json, transport_sha, piston_sha, open_r1, lock_sha, torch_version, cuda_version, gpu_name, output = sys.argv[6:17]
pair_components = json.loads(pair_components_json)
if not isinstance(pair_components, dict):
    raise SystemExit("formal paired component identity is invalid")
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
    value = sum(values) / len(values)
    if not math.isfinite(value):
        raise SystemExit("numeric series mean is nonfinite")
    return value

def p95(values: list[float]) -> float:
    if not values:
        raise SystemExit("cannot summarize empty numeric series")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]

def checkpoint_inventory(run_dir: Path) -> dict[str, object]:
    required = {*_GRPO_TRAINER_RESUME_FILES, _GRPO_LOG_STATE_FILENAME}
    inventory = []
    final_log_state = None
    for step in range(50, 301, 50):
        path = run_dir / "checkpoints" / f"checkpoint-{step}"
        if not path.is_dir() or path.is_symlink():
            raise SystemExit(f"missing complete checkpoint-{step}")
        required_paths = [path / name for name in required]
        if any(not item.is_file() or item.is_symlink() or item.stat().st_size <= 0 for item in required_paths):
            raise SystemExit(f"incomplete checkpoint-{step}")
        state = json.loads((path / "trainer_state.json").read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("global_step") != step:
            raise SystemExit(f"checkpoint-{step} global_step mismatch")
        try:
            log_state = _validate_resume_log_checkpoint(run_dir, path)
        except GRPOTrainingError as error:
            raise SystemExit(f"checkpoint-{step} canonical log boundary invalid: {type(error).__name__}") from None
        if step == 300:
            final_log_state = log_state
        files = [item for item in path.rglob("*") if item.is_file() and not item.is_symlink()]
        inventory.append({"step": step, "bytes": sum(item.stat().st_size for item in files), "inodes": len(files)})
    if final_log_state is None:
        raise SystemExit("checkpoint-300 log state is missing")
    for name in _GRPO_STREAM_LOG_NAMES:
        if _stream_log_file_state(run_dir / name) != final_log_state["logs"][name]:
            raise SystemExit(f"checkpoint-300 log boundary is not the complete canonical {name}")
    return {
        "checkpoints": inventory,
        "max_checkpoint_bytes": max(item["bytes"] for item in inventory),
        "max_checkpoint_inodes": max(item["inodes"] for item in inventory),
    }

def recovery_history_inventory(run_dir: Path, attempt_count: int) -> list[str]:
    history_root = run_dir / "checkpoints" / "recovery-history"
    if not history_root.exists():
        return []
    if not history_root.is_dir() or history_root.is_symlink():
        raise SystemExit("recovery-history is unsafe")
    entries = []
    stream_names = {"rollouts.jsonl", "rewards.jsonl", "group_metrics.jsonl"}
    pattern = re.compile(r"before-attempt-([1-9][0-9]*)-resume-checkpoint-([1-9][0-9]*)")
    for entry in sorted(history_root.iterdir()):
        if entry.is_symlink() or not entry.is_dir():
            raise SystemExit("formal recovery-history contains an unsafe entry")
        match = pattern.fullmatch(entry.name)
        if match is None:
            raise SystemExit("formal recovery-history entry name is invalid")
        attempt = int(match.group(1))
        step = int(match.group(2))
        if attempt < 2 or attempt > attempt_count or step < 50 or step > 300 or step % 50 != 0:
            raise SystemExit("formal recovery-history identity is out of range")
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise SystemExit("formal recovery-history manifest is missing or unsafe")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required_fields = {"version", "attempt", "resume_checkpoint", "global_step", "before_logs", "restored_checkpoint_logs", "superseded_future_checkpoints"}
        if not isinstance(manifest, dict) or set(manifest) != required_fields:
            raise SystemExit("formal recovery-history manifest schema is invalid")
        if manifest.get("version") != 1 or manifest.get("attempt") != attempt or manifest.get("resume_checkpoint") != f"checkpoint-{step}" or manifest.get("global_step") != step:
            raise SystemExit("formal recovery-history manifest identity is invalid")
        before = manifest.get("before_logs")
        restored = manifest.get("restored_checkpoint_logs")
        future = manifest.get("superseded_future_checkpoints")
        if not isinstance(before, dict) or set(before) != stream_names or not isinstance(restored, dict) or set(restored) != stream_names:
            raise SystemExit("formal recovery-history stream state is invalid")
        if not isinstance(future, list) or not all(isinstance(item, str) for item in future):
            raise SystemExit("formal recovery-history future-checkpoint inventory is invalid")
        selected = run_dir / "checkpoints" / f"checkpoint-{step}"
        try:
            selected_state = _validate_resume_log_checkpoint(run_dir, selected)
        except GRPOTrainingError as error:
            raise SystemExit(f"formal recovery selected checkpoint is invalid: {type(error).__name__}") from None
        if selected_state.get("logs") != restored:
            raise SystemExit("formal recovery restored state differs from selected checkpoint sidecar")
        for name in stream_names:
            archived = entry / name
            if _stream_log_file_state(archived) != before[name]:
                raise SystemExit(f"formal recovery-history archived {name} differs from manifest")
        future_root = entry / "superseded-future-checkpoints"
        allowed = {*stream_names, "manifest.json"}
        if future:
            if not future_root.is_dir() or future_root.is_symlink():
                raise SystemExit("formal recovery-history future-checkpoint directory is missing or unsafe")
            allowed.add("superseded-future-checkpoints")
            actual = sorted(path.name for path in future_root.iterdir())
            if actual != sorted(future):
                raise SystemExit("formal recovery-history future-checkpoint inventory differs from manifest")
            for path in future_root.iterdir():
                match_future = re.fullmatch(r"checkpoint-([1-9][0-9]*)", path.name)
                if match_future is None or path.is_symlink() or not path.is_dir():
                    raise SystemExit("formal recovery-history contains an unsafe future checkpoint")
                future_step = int(match_future.group(1))
                if future_step <= step or future_step > 300:
                    raise SystemExit("formal recovery-history future checkpoint is out of range")
        elif future_root.exists():
            raise SystemExit("formal recovery-history has an unrecorded future-checkpoint directory")
        if {path.name for path in entry.iterdir()} != allowed:
            raise SystemExit("formal recovery-history archive contains unexpected files")
        entries.append(entry.name)
    return entries

def validate_transport(path: Path, run_name: str) -> dict[str, int | float]:
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"{run_name} transport sidecar missing or unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    expected_fields = {
        "version", "run_name", "piston_definition_sha256", "piston_transport_policy_sha256",
        "telemetry_semantics", "telemetry",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise SystemExit(f"{run_name} transport sidecar schema invalid")
    expected = {
        "version": 1,
        "run_name": run_name,
        "piston_definition_sha256": piston_sha,
        "piston_transport_policy_sha256": transport_sha,
        "telemetry_semantics": "cumulative_durable_snapshot_per_mutation_v1",
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise SystemExit(f"{run_name} transport sidecar identity invalid")
    telemetry = PistonTransportTelemetry()
    try:
        telemetry.restore(value.get("telemetry"))
    except ValueError as error:
        raise SystemExit(f"{run_name} transport telemetry invalid: {error}") from None
    counters = telemetry.to_mapping()
    if counters["transport_requests"] <= 0:
        raise SystemExit(f"{run_name} transport telemetry recorded no real request")
    if counters["transport_retry_successes"] > counters["transport_safe_retries"]:
        raise SystemExit(f"{run_name} transport retry-success counter exceeds safe retries")
    if counters["transport_safe_retries"] > counters["transport_connect_failures"]:
        raise SystemExit(f"{run_name} safe retry counter exceeds connect failures")
    return counters

def check_run(run_dir: Path, transport_path: Path, mode: str, run_id: str) -> dict[str, object]:
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.run_id != run_id or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != pair_sha:
        raise SystemExit(f"{mode} strict formal identity mismatch")
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    expected = {
        "status": "completed", "run_id": run_id, "reward_mode": mode,
        "paired_definition_sha256": pair_sha, "seed": 42, "git_commit": head,
        "open_r1_commit": open_r1, "dependency_lock_hash": lock_sha,
        "torch_version": torch_version, "cuda_version": cuda_version, "gpu_name": gpu_name,
        "gpu_count_used": 1, "global_step": 300,
    }
    for key, expected_value in expected.items():
        if metadata.get(key) != expected_value:
            raise SystemExit(f"{mode} formal metadata mismatch: {key}")
    for key, expected_value in pair_components.items():
        if metadata.get(key) != expected_value:
            raise SystemExit(f"{mode} formal paired component mismatch: {key}")
    attempts = metadata.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise SystemExit(f"{mode} formal attempts missing")
    attempt_total = 0.0
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict) or attempt.get("attempt") != index or attempt.get("status") not in {"running", "failed", "completed"}:
            raise SystemExit(f"{mode} formal attempt history invalid")
        hours = finite_number(attempt.get("gpu_hours"), f"{mode} attempt gpu_hours")
        if hours < 0 or (attempt.get("status") == "running" and hours != 0.0):
            raise SystemExit(f"{mode} formal attempt gpu_hours invalid")
        attempt_total += hours
        if attempt.get("code_commit") != head:
            raise SystemExit(f"{mode} formal attempt code_commit mismatch")
        resume_value = attempt.get("resume_from_checkpoint")
        if index == 1 and resume_value is not None:
            raise SystemExit(f"{mode} formal first attempt must initialize fresh from B")
        if index > 1:
            match = re.fullmatch(r"checkpoints/checkpoint-([1-9][0-9]*)", str(resume_value))
            if match is None or int(match.group(1)) % 50 != 0 or not (50 <= int(match.group(1)) <= 300):
                raise SystemExit(f"{mode} formal resumed attempt is not same-run 50-step cadence")
    gpu_hours = finite_number(metadata.get("gpu_hours"), f"{mode} cumulative gpu_hours")
    if attempts[-1].get("status") != "completed" or gpu_hours <= 0 or not math.isclose(gpu_hours, attempt_total, rel_tol=0.0, abs_tol=1e-12):
        raise SystemExit(f"{mode} cumulative gpu_hours invalid")
    for key in ("peak_cuda_memory_allocated_bytes", "peak_cuda_memory_reserved_bytes"):
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SystemExit(f"{mode} {key} invalid")
    recovery_archives = recovery_history_inventory(run_dir, len(attempts))

    metrics = load_rows(run_dir / "metrics.jsonl")
    require_finite(metrics, f"{mode} formal metrics")
    trainer_rows = [row for row in metrics if row.get("record_type") == "trainer"]
    step_rows = {}
    for row in trainer_rows:
        step_value = row.get("step")
        if isinstance(step_value, bool) or not isinstance(step_value, (int, float)) or not float(step_value).is_integer():
            continue
        step = int(step_value)
        if 1 <= step <= 300 and "reward" in row:
            if step in step_rows:
                raise SystemExit(f"{mode} duplicate formal trainer step telemetry")
            step_rows[step] = row
    if set(step_rows) != set(range(1, 301)):
        raise SystemExit(f"{mode} formal trainer telemetry does not cover steps 1..300 exactly once")
    if not metrics or metrics[-1].get("record_type") != "summary" or metrics[-1].get("global_step") != 300:
        raise SystemExit(f"{mode} formal metrics summary incomplete")

    def series(name: str) -> list[float]:
        return [finite_number(step_rows[i].get(name), f"{mode} {name} step {i}") for i in range(1, 301)]

    reward_series = series("reward")
    reward_std_series = series("reward_std")
    kl_series = series("kl")
    loss_series = series("loss")
    generation_seconds = series("generation_runtime_seconds")
    rollout_seconds = series("rollout_runtime_seconds")
    no_grad_seconds = series("no_grad_logps_runtime_seconds")
    no_grad_calls = series("no_grad_logps_calls")
    step_seconds = series("step_runtime_seconds")
    completion_mean_series = series("completions/mean_length")
    clipped_series = series("completions/clipped_ratio")
    for index, (generation, rollout, no_grad, calls, step) in enumerate(
        zip(generation_seconds, rollout_seconds, no_grad_seconds, no_grad_calls, step_seconds), 1
    ):
        if generation < 0 or rollout < generation or no_grad < 0 or step < rollout + no_grad:
            raise SystemExit(f"{mode} formal timing decomposition invalid at step {index}")
        if calls != 8.0:
            raise SystemExit(f"{mode} formal no-grad call count changed at step {index}: {calls}")

    rollouts = load_rows(run_dir / "rollouts.jsonl")
    rewards = load_rows(run_dir / "rewards.jsonl")
    groups = load_rows(run_dir / "group_metrics.jsonl")
    if (len(rollouts), len(rewards), len(groups)) != (2400, 2400, 600):
        raise SystemExit(f"{mode} formal canonical row counts are not 2400/2400/600")
    if any(set(row) != _ROLLOUT_FIELDS or row.get("reward_mode") != mode for row in rollouts):
        raise SystemExit(f"{mode} formal rollout schema/source mismatch")
    if any(set(row) != _REWARD_FIELDS or row.get("mode") != mode for row in rewards):
        raise SystemExit(f"{mode} formal reward schema/source mismatch")
    group_fields = {"group_index", "problem_id", "reward_mode", "sample_count", "mean", "std", "all_equal"}
    if any(set(row) != group_fields or row.get("reward_mode") != mode or row.get("sample_count") != 4 for row in groups):
        raise SystemExit(f"{mode} formal group schema/source mismatch")
    if any(row.get("infrastructure_failure") is not False or row.get("status") == "sandbox_error" for row in rewards):
        raise SystemExit(f"{mode} formal canonical reward path contains infrastructure/sandbox failure")
    if not any(row.get("executed") is True for row in rewards):
        raise SystemExit(f"{mode} formal reward path contains no real executed completion")
    require_finite(rollouts, f"{mode} formal rollouts")
    require_finite(rewards, f"{mode} formal rewards")
    require_finite(groups, f"{mode} formal groups")
    if any(any(key in row for key in ("prompt", "visible_tests", "train_hidden_tests", "eval_hidden_tests")) for row in rollouts):
        raise SystemExit(f"{mode} formal rollout contains forbidden test payload")

    curve = load_training_curve_rows(run_dir, method=f"{mode}-formal")
    cost = build_cost_row(run_dir, method=f"{mode}-formal", gpu_hour_cost_usd=None)
    generated_count = getattr(cost, "generated_" + "tokens")
    if (
        not curve
        or not math.isfinite(cost.gpu_hours)
        or cost.gpu_hours <= 0
        or not isinstance(generated_count, int)
        or generated_count <= 0
    ):
        raise SystemExit(f"{mode} formal curve/cost loader failed")
    executor_ms = [finite_number(row.get("executor_runtime_ms"), f"{mode} executor runtime") for row in rewards]
    group_std = [finite_number(row.get("std"), f"{mode} group std") for row in groups]
    completion_lengths = [finite_number(row.get("completion_token_count"), f"{mode} completion length") for row in rollouts]
    statuses = Counter(str(row.get("status")) for row in rewards)
    failures = Counter()
    for row in rewards:
        value = row.get("failure_counts")
        if not isinstance(value, dict):
            raise SystemExit(f"{mode} failure_counts invalid")
        for key, count in value.items():
            if not isinstance(key, str) or isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise SystemExit(f"{mode} failure_counts entry invalid")
            failures[key] += count
    test_rows = [
        row for row in rewards
        if isinstance(row.get("total_tests"), int)
        and not isinstance(row.get("total_tests"), bool)
        and row.get("total_tests", 0) > 0
    ]
    pass_rows = [row for row in test_rows if row.get("passed_tests") == row.get("total_tests")]
    transport = validate_transport(transport_path, run_id)
    inventory = checkpoint_inventory(run_dir)
    telemetry = {
        "reward_mean": mean(reward_series),
        "reward_std_mean": mean(reward_std_series),
        "group_std_mean": mean(group_std),
        "group_all_equal_rate": sum(1 for row in groups if row.get("all_equal") is True) / len(groups),
        "kl_mean": mean(kl_series),
        "kl_max": max(kl_series),
        "loss_mean": mean(loss_series),
        "completion_mean_length": mean(completion_lengths),
        "trainer_completion_mean_length_mean": mean(completion_mean_series),
        "trainer_completion_clipped_ratio_mean": mean(clipped_series),
        "completion_truncation_rate": sum(1 for row in rollouts if row.get("truncated") is True) / len(rollouts),
        "parsed_rate": sum(1 for row in rewards if row.get("parsed") is True) / len(rewards),
        "executed_rate": sum(1 for row in rewards if row.get("executed") is True) / len(rewards),
        "timeout_rate": sum(1 for row in rewards if row.get("status") == "timeout") / len(rewards),
        "pass_rate": len(pass_rows) / len(test_rows) if test_rows else 0.0,
        "generation_runtime_mean_seconds": mean(generation_seconds),
        "generation_runtime_p95_seconds": p95(generation_seconds),
        "generation_runtime_max_seconds": max(generation_seconds),
        "rollout_runtime_mean_seconds": mean(rollout_seconds),
        "rollout_runtime_p95_seconds": p95(rollout_seconds),
        "rollout_runtime_max_seconds": max(rollout_seconds),
        "no_grad_runtime_mean_seconds": mean(no_grad_seconds),
        "step_runtime_mean_seconds": mean(step_seconds),
        "step_runtime_p95_seconds": p95(step_seconds),
        "step_runtime_max_seconds": max(step_seconds),
        "executor_runtime_mean_ms": mean(executor_ms),
        "executor_runtime_total_ms": sum(executor_ms),
        "status_counts": dict(sorted(statuses.items())),
        "failure_counts": dict(sorted(failures.items())),
        "reward_source": "visible_tests" if mode == "public" else "train_hidden_tests",
    }
    require_finite(telemetry, f"{mode} formal telemetry summary")
    return {
        "run_id": run_id,
        "reward_mode": mode,
        "paired_definition_sha256": pair_sha,
        "parent_sft_run_id": identity.parent_sft.run_id,
        "global_step": 300,
        "gpu_hours": gpu_hours,
        "attempt_count": len(attempts),
        "recovery_history_archives": recovery_archives,
        "peak_cuda_memory_allocated_bytes": metadata["peak_cuda_memory_allocated_bytes"],
        "peak_cuda_memory_reserved_bytes": metadata["peak_cuda_memory_reserved_bytes"],
        "trainer_metric_rows": len(trainer_rows),
        "curve_rows": len(curve),
        "rollout_rows": len(rollouts),
        "reward_rows": len(rewards),
        "group_rows": len(groups),
        "executor_hours": cost.executor_hours,
        "completion_output_units": generated_count,
        "telemetry": telemetry,
        "transport_telemetry": transport,
        **inventory,
    }

public = check_run(public_run, public_transport, "public", "C-public-grpo-formal-seed42")
hidden = check_run(hidden_run, hidden_transport, "hidden", "D-hidden-grpo-formal-seed42")
if public["telemetry"]["reward_source"] == hidden["telemetry"]["reward_source"]:
    raise SystemExit("Public/Hidden formal reward sources unexpectedly match")
summary = {
    "version": 1,
    "status": "passed",
    "paired_definition_sha256": pair_sha,
    "piston_definition_sha256": piston_sha,
    "piston_transport_policy_sha256": transport_sha,
    "public": public,
    "hidden": hidden,
    "formal_training_completed": True,
    "generation_started": False,
}
Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY_POSTCHECK
then
  mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"
else
  rc=$?
  rm -f "$POSTCHECK_FILE.tmp"
  write_evidence 0 "$rc" postcheck_failed "paired formal C/D postcheck failed"
  exit $?
fi

CURRENT_PHASE="complete"
write_evidence 0 0 passed "paired 300-step formal C/D training completed and postchecked; generation was not started"
exit $?
