#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-c"
GATE_ID="wp9c-calibration-initial-generation"
CHECKPOINT_ID="C0"
PLAN_COMMIT="5a1f083af6bfdf2e1333bd70e95e9257b4e66b48"
RESULT_CODE_COMMIT="e929e515d25c43c15193058d24fc2a3d6670c3da"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560"
CALIBRATION_CONFIG_SHA="4f658443d0296fbc9da206e9f75ece07c4ceb544d66a3e93eacedf89722fab0e"
INPUT_MANIFEST_SHA="3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3"
INPUT_RECORDS_SHA="86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682"
INPUT_ORDER_SHA="355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001"
WP9A_MANIFEST_SHA="98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625"
WP9A_SELECTED_ORDER_SHA="355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001"
B_RUN_NAME="B-sft-formal-seed42"
B_MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
B_MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
B_DATASET_HASH="4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c"
B_CONFIG_HASH="250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244"
MODEL_WEIGHTS_SHA="c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"

PLAN_REL="ai-work/planner/WP9-c-plan.md"
REPORT_REL="ai-work/executor/WP9-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C0/run.sh"
CONFIG_REL="configs/grpo/refresh-calibration.yaml"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
[[ -x "$PY" && -x "$CV" ]] || { echo "target checkout .venv is unavailable; do not start calibration generation" >&2; exit 125; }

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
}
if not isinstance(value, dict) or not required.issubset(value):
    raise SystemExit("validation machine pointer schema is missing required fields")
if value["version"] != 1 or value["machine_status"] != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine pointer is not READY_FOR_VALIDATION_PLANNER")
for key in ("artifact_root", "hf_home", "formal_data_root", "readiness_record"):
    item = value[key]
    if not isinstance(item, str) or not Path(item).is_absolute():
        raise SystemExit(f"validation machine pointer {key} must be absolute")
print("\t".join(str(value[key]) for key in (
    "bootstrap_project_commit", "open_r1_commit", "artifact_root", "hf_home", "formal_data_root", "readiness_record",
)))
PY_MACHINE
)"
TAB="$(printf '\t')"
IFS="$TAB" read -r BOOTSTRAP_COMMIT MACHINE_OPEN_R1 ARTIFACT_ROOT TARGET_HF_HOME FORMAL_DATA_ROOT READINESS_RECORD <<<"$MACHINE_FIELDS"

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$TARGET_HF_HOME"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1

INPUT_DIR="$FORMAL_DATA_ROOT/wp9c/calibration-input"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
OUTPUT_DIR="$ARTIFACT_ROOT/wp9c/calibration/initial"
QUARANTINE_ROOT="$ARTIFACT_ROOT/wp9c/quarantine/calibration/initial"
OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/$GATE_ID/$CHECKPOINT_ID"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
POSTCHECK_FILE="$OP_ROOT/postcheck-summary.json"
LOCK_FILE="$OP_ROOT/run.lock"

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

HEAD_COMMIT=""
SCRIPT_SHA=""
READINESS_SHA=""
GPU_NAME=""
GPU_VRAM_MIB="0"
CURRENT_OPEN_R1=""
CURRENT_LOCK_SHA=""
CURRENT_TORCH=""
CURRENT_CUDA=""
OUTPUT_ACTION="unresolved"
CURRENT_PHASE="preflight"
FINALIZED=0

write_evidence() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time generation_started
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [[ -n "$HEAD_COMMIT" ]] || HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$SCRIPT_SHA" ]] || SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  generation_started=false
  [[ "$CURRENT_PHASE" == "preflight" ]] || generation_started=true
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$REPO_ROOT" "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" \
    "$MACHINE_POINTER" "$READINESS_RECORD" "$HEAD_COMMIT" "$SCRIPT_SHA" "$MACHINE_SHA" "$READINESS_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" \
    "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$INPUT_DIR" "$B_RUN" "$OUTPUT_DIR" "$OUTPUT_ACTION" \
    "$generation_started" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path
(
    output, postcheck_path, repo_root, artifact_root, hf_home, formal_data_root,
    machine_pointer, readiness_record, checkpoint_commit, script_sha, machine_sha,
    readiness_sha, gpu_name, gpu_vram_mib, open_r1_commit, dependency_lock_sha,
    torch_version, cuda_version, input_dir, b_run, output_dir, output_action,
    generation_started, command_rc, postcheck_rc, gate_status, note, start_time,
    end_time, attempt_id,
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
postcheck_file = Path(postcheck_path)
postcheck = None
if postcheck_file.is_file():
    value = json.loads(postcheck_file.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        postcheck = value
run_root = Path(output_dir)
files = [
    inventory(run_root / "run.json"),
    inventory(run_root / "samples" / "generations.jsonl"),
    inventory(postcheck_file),
]
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP9-c",
    "source_plan_commit": "5a1f083af6bfdf2e1333bd70e95e9257b4e66b48",
    "operator_checkpoint_commit": checkpoint_commit,
    "result_code_commit": "e929e515d25c43c15193058d24fc2a3d6670c3da",
    "checkpoint_id": "C0",
    "operator_gate_id": "wp9c-calibration-initial-generation",
    "operator_script": "ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C0/run.sh",
    "operator_script_sha256": script_sha,
    "target_machine_pointer": machine_pointer,
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record": readiness_record,
    "target_readiness_record_sha256": readiness_sha or None,
    "gpu_name": gpu_name or None,
    "gpu_vram_mib": int(gpu_vram_mib) if gpu_vram_mib.isdigit() else None,
    "resolved_roots": {
        "repo_root": repo_root,
        "artifact_root": artifact_root,
        "hf_home": hf_home,
        "formal_data_root": formal_data_root,
    },
    "runtime_identity": {
        "open_r1_commit": open_r1_commit or None,
        "dependency_lock_hash": dependency_lock_sha or None,
        "torch_version": torch_version or None,
        "cuda_version": cuda_version or None,
    },
    "input_bundle": {
        "path": input_dir,
        "input_manifest_sha256": "3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3",
        "records_sha256": "86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682",
        "problem_order_sha256": "355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001",
    },
    "formal_b_run": b_run,
    "generation_output": output_dir,
    "generation_action": output_action,
    "generation_started": generation_started == "true",
    "postcheck": postcheck,
    "expected_artifact_inventory": files,
    "attempt_id": attempt_id,
    "start_time": start_time,
    "end_time": end_time,
    "command_rc": int(command_rc),
    "postcheck_rc": int(postcheck_rc),
    "gate_status": gate_status,
    "note": note,
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
}

finalize_gate() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time final_rc
  trap - ERR INT TERM
  write_evidence "$command_rc" "$postcheck_rc" "$gate_status" "$note"
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  final_rc=1
  if [[ "$gate_status" == "passed" && "$command_rc" == "0" && "$postcheck_rc" == "0" ]]; then
    final_rc=0
  elif [[ "$command_rc" =~ ^[0-9]+$ ]] && (( command_rc > 0 && command_rc < 126 )); then
    final_rc="$command_rc"
  fi
  printf '%s\n' "$final_rc" >"$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  printf '[%s] attempt=%s end phase=%s command_rc=%s postcheck_rc=%s gate_status=%s note=%s\n' \
    "$end_time" "$ATTEMPT_ID" "$CURRENT_PHASE" "$command_rc" "$postcheck_rc" "$gate_status" "$note" >>"$LOG_FILE"
  FINALIZED=1
  return "$final_rc"
}

fail_preflight() {
  local message="$1"
  printf '[%s] preflight FAIL: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$message" >>"$LOG_FILE"
  finalize_gate 125 125 preflight_failed "$message"
  exit $?
}

on_err() {
  local line="$1" rc="$2"
  [[ "$FINALIZED" == "0" ]] || exit "$rc"
  printf '[%s] unexpected ERR line=%s rc=%s phase=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$line" "$rc" "$CURRENT_PHASE" >>"$LOG_FILE" || true
  finalize_gate "$rc" 125 internal_error "unexpected shell error at line $line" || true
  exit "$rc"
}

on_signal() {
  local rc="$1" name="$2"
  [[ "$FINALIZED" == "0" ]] || exit "$rc"
  printf '[%s] signal=%s phase=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$CURRENT_PHASE" >>"$LOG_FILE" || true
  finalize_gate "$rc" 125 interrupted "received $name during $CURRENT_PHASE" || true
  exit "$rc"
}
trap 'on_err "$LINENO" "$?"' ERR
trap 'on_signal 130 INT' INT
trap 'on_signal 143 TERM' TERM

HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve target HEAD"
PARENT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve target checkpoint parent"
[[ "$PARENT_COMMIT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "C0 checkpoint parent does not equal result_code_commit"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --ignore-submodules=none)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge must remain untracked"
if ! git -C "$REPO_ROOT" diff --quiet "$PLAN_COMMIT" -- "$PLAN_REL"; then
  fail_preflight "sealed WP9-c plan changed after plan commit"
fi
if ! "$PY" - "$REPO_ROOT" "$HEAD_COMMIT" "$REPORT_REL" "$SCRIPT_REL" <<'PY_SCOPE'
import subprocess
import sys
from pathlib import Path
repo = Path(sys.argv[1])
head, report, script = sys.argv[2:]
rows = subprocess.run(
    ["git", "-C", str(repo), "diff-tree", "--no-commit-id", "--name-status", "-r", head],
    check=True, capture_output=True, text=True,
).stdout.splitlines()
if sorted(rows) != sorted([f"A\t{report}", f"A\t{script}"]):
    raise SystemExit("C0 checkpoint commit must contain exactly the new report and operator script")
mode_line = subprocess.run(
    ["git", "-C", str(repo), "ls-tree", head, "--", script],
    check=True, capture_output=True, text=True,
).stdout.strip()
if not mode_line.startswith("100755 "):
    raise SystemExit("tracked C0 operator script is not executable")
PY_SCOPE
then
  fail_preflight "C0 checkpoint commit scope validation failed"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" <<'PY_META'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind("checkpoint_id: C0")
if pos < 0:
    raise SystemExit("C0 checkpoint block is missing")
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit("C0 checkpoint block is malformed")
block = text[start:end]
def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"C0 checkpoint field missing: {name}")
    return match.group(1).strip().strip('"').strip("'")
print("\t".join([
    field("stage_id"), field("task_kind"), field("source_plan_commit"), field("source_review_round"),
    field("source_review_commit"), field("repair_issue_ids"), field("result_code_commit"), field("operator_gate_id"),
    field("operator_handoff_mode"), field("operator_restart_policy"), field("operator_script_sha256"), field("input_manifest_sha256"),
    field("input_records_sha256"), field("input_problem_order_sha256"), field("wp9a_manifest_sha256"),
    field("wp9a_selected_order_sha256"), field("calibration_config_sha256"), field("status"),
]))
PY_META
)" || fail_preflight "cannot parse C0 checkpoint metadata"
IFS="$TAB" read -r CHECKPOINT_STAGE CHECKPOINT_TASK CHECKPOINT_PLAN CHECKPOINT_REVIEW_ROUND CHECKPOINT_REVIEW_COMMIT CHECKPOINT_REPAIR_IDS CHECKPOINT_RESULT CHECKPOINT_GATE CHECKPOINT_MODE CHECKPOINT_RESTART EXPECTED_SCRIPT_SHA CHECKPOINT_INPUT_MANIFEST CHECKPOINT_INPUT_RECORDS CHECKPOINT_INPUT_ORDER CHECKPOINT_WP9A CHECKPOINT_WP9A_ORDER CHECKPOINT_CONFIG_SHA CHECKPOINT_STATUS <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_STAGE" == "$STAGE_ID" && "$CHECKPOINT_TASK" == "implementation" && "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" ]] || fail_preflight "C0 implementation source provenance mismatch"
[[ "$CHECKPOINT_REVIEW_ROUND" == "null" && "$CHECKPOINT_REVIEW_COMMIT" == "null" && "$CHECKPOINT_REPAIR_IDS" == "[]" ]] || fail_preflight "C0 must not fabricate review provenance"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" && "$CHECKPOINT_GATE" == "$GATE_ID" && "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_RESTART" == "exact_rerun" ]] || fail_preflight "C0 gate/handoff/restart provenance mismatch"
[[ "$CHECKPOINT_INPUT_MANIFEST" == "$INPUT_MANIFEST_SHA" && "$CHECKPOINT_INPUT_RECORDS" == "$INPUT_RECORDS_SHA" && "$CHECKPOINT_INPUT_ORDER" == "$INPUT_ORDER_SHA" ]] || fail_preflight "C0 input bundle identity mismatch"
[[ "$CHECKPOINT_WP9A" == "$WP9A_MANIFEST_SHA" && "$CHECKPOINT_WP9A_ORDER" == "$WP9A_SELECTED_ORDER_SHA" ]] || fail_preflight "C0 WP9-a identity mismatch"
[[ "$CHECKPOINT_CONFIG_SHA" == "$CALIBRATION_CONFIG_SHA" && "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "C0 config/status metadata mismatch"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked C0 operator script SHA differs from report"

[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -d "$FORMAL_DATA_ROOT" ]] || fail_preflight "target persistent roots are unavailable"
[[ "$ARTIFACT_ROOT" != "$REPO_ROOT" && "$ARTIFACT_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "artifact_root must remain outside target checkout"
[[ "$FORMAL_DATA_ROOT" != "$REPO_ROOT" && "$FORMAL_DATA_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "formal_data_root must remain outside target checkout"
[[ "$TARGET_HF_HOME" != "$REPO_ROOT" && "$TARGET_HF_HOME" != "$REPO_ROOT/"* ]] || fail_preflight "hf_home must remain outside target checkout"
[[ -f "$READINESS_RECORD" ]] || fail_preflight "target readiness record is unavailable"
READINESS_SHA="$(sha256sum "$READINESS_RECORD" | awk '{print $1}')"

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
if "RTX 4090" not in name or vram_mib < 22528:
    raise SystemExit("visible GPU is not the certified RTX 4090 class target")
if not torch.cuda.is_bf16_supported():
    raise SystemExit("target GPU must support BF16")
print(f"{name}\t{vram_mib}")
PY_GPU
)" || fail_preflight "CUDA/BF16 target validation failed"
IFS="$TAB" read -r GPU_NAME GPU_VRAM_MIB <<<"$GPU_FIELDS"

RUNTIME_FIELDS="$($PY - "$REPO_ROOT" "$HEAD_COMMIT" "$OPEN_R1_COMMIT" "$DEPENDENCY_LOCK_SHA" <<'PY_RUNTIME'
import sys
from pathlib import Path
import code_verifier
import open_r1
from code_verifier.environment import collect_environment
repo = Path(sys.argv[1]).resolve()
head, expected_open_r1, expected_lock = sys.argv[2:5]
for module, name in ((code_verifier, "code_verifier"), (open_r1, "open_r1")):
    module_file = getattr(module, "__file__", None)
    if module_file is None or repo not in Path(module_file).resolve().parents:
        raise SystemExit(f"{name} does not resolve inside target checkout")
current = collect_environment()
if current.get("project_commit") != head or current.get("open_r1_commit") != expected_open_r1 or current.get("dependency_lock_hash") != expected_lock:
    raise SystemExit("current project/Open-R1/dependency identity mismatch")
if current.get("gpu_count") != 1 or not isinstance(current.get("cuda_version"), str):
    raise SystemExit("target CUDA environment identity is invalid")
print("\t".join([current["open_r1_commit"], current["dependency_lock_hash"], current["packages"]["torch"], current["cuda_version"]]))
PY_RUNTIME
)" || fail_preflight "target runtime identity validation failed"
IFS="$TAB" read -r CURRENT_OPEN_R1 CURRENT_LOCK_SHA CURRENT_TORCH CURRENT_CUDA <<<"$RUNTIME_FIELDS"

[[ "$(sha256sum "$REPO_ROOT/$CONFIG_REL" | awk '{print $1}')" == "$CALIBRATION_CONFIG_SHA" ]] || fail_preflight "tracked calibration config SHA changed"
[[ -d "$INPUT_DIR" ]] || fail_preflight "calibration input is missing; sync it to $INPUT_DIR before running"
if ! "$PY" - "$INPUT_DIR" "$INPUT_MANIFEST_SHA" "$INPUT_RECORDS_SHA" "$INPUT_ORDER_SHA" "$WP9A_MANIFEST_SHA" "$WP9A_SELECTED_ORDER_SHA" >>"$LOG_FILE" <<'PY_INPUT'
import hashlib
import sys
from pathlib import Path
from code_verifier.training.calibration import _load_input_bundle
root = Path(sys.argv[1])
expected_manifest, expected_records, expected_order, expected_wp9a, expected_wp9a_order = sys.argv[2:]
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
manifest, records = _load_input_bundle(root)
if digest(root / "input_manifest.json") != expected_manifest:
    raise SystemExit("calibration input manifest SHA mismatch")
if manifest.get("records_sha256") != expected_records or manifest.get("problem_order_sha256") != expected_order:
    raise SystemExit("calibration input records/order identity mismatch")
if manifest.get("wp9a_manifest_sha256") != expected_wp9a or manifest.get("wp9a_selected_order_sha256") != expected_wp9a_order:
    raise SystemExit("calibration input WP9-a provenance mismatch")
if manifest.get("record_count") != 10000 or manifest.get("seed") != 42 or manifest.get("evidence_class") != "formal_input" or len(records) != 10000:
    raise SystemExit("calibration input formal shape mismatch")
print(f"calibration_input_records={len(records)} input_manifest_sha256={expected_manifest}")
PY_INPUT
then
  fail_preflight "formal calibration input strict validation failed"
fi

if ! B_FIELDS="$($PY - "$B_RUN" "$B_RUN_NAME" "$B_MODEL_ID" "$B_MODEL_REVISION" "$B_DATASET_HASH" "$B_CONFIG_HASH" "$DEPENDENCY_LOCK_SHA" <<'PY_B'
import sys
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
run = load_completed_sft_checkpoint(Path(sys.argv[1]))
expected = sys.argv[2:]
actual = [run.run_id, run.model_id, run.model_revision, run.dataset_hash, run.config_hash, run.dependency_lock_hash]
if actual != expected:
    raise SystemExit("formal B checkpoint identity mismatch")
if run.seed != 42:
    raise SystemExit("formal B seed mismatch")
print("\t".join(actual))
PY_B
)"; then
  fail_preflight "formal B strict load failed"
fi
printf '[%s] formal B identity=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$B_FIELDS" >>"$LOG_FILE"

if ! "$PY" - "$B_MODEL_ID" "$B_MODEL_REVISION" "$MODEL_WEIGHTS_SHA" >>"$LOG_FILE" <<'PY_MODEL'
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
  fail_preflight "exact formal B base-model revision/weights are unavailable local-only"
fi

if ! "$PY" - "$ARTIFACT_ROOT" <<'PY_STORAGE'
import os
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1])
usage = shutil.disk_usage(root)
stat = os.statvfs(root)
if usage.free < 30 * 1024**3:
    raise SystemExit("Gate A requires at least 30 GiB free")
if stat.f_favail < 100000:
    raise SystemExit("Gate A requires at least 100000 free inodes")
print(f"storage_free_bytes={usage.free} storage_free_inodes={stat.f_favail}")
PY_STORAGE
then
  fail_preflight "Gate A storage gate failed"
fi

OUTPUT_ACTION="$($PY - "$OUTPUT_DIR" "$QUARANTINE_ROOT" "$INPUT_MANIFEST_SHA" "$INPUT_RECORDS_SHA" "$ATTEMPT_ID" "$B_RUN" <<'PY_PREP'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
output = Path(sys.argv[1])
quarantine = Path(sys.argv[2])
expected_input_manifest = sys.argv[3]
expected_input_records = sys.argv[4]
attempt = sys.argv[5]
b_run = Path(sys.argv[6])
if not output.exists():
    print("fresh")
    raise SystemExit(0)
try:
    value = json.loads((output / "run.json").read_text(encoding="utf-8"))
    b = load_completed_sft_checkpoint(b_run)
    expected_b = {
        "run_id": b.run_id,
        "model_id": b.model_id,
        "model_revision": b.model_revision,
        "dataset_hash": b.dataset_hash,
        "config_hash": b.config_hash,
        "dependency_lock_hash": b.dependency_lock_hash,
        "seed": b.seed,
    }
    if value.get("block_index") != 0 or value.get("input_manifest_sha256") != expected_input_manifest or value.get("input_records_sha256") != expected_input_records:
        raise ValueError("input identity mismatch")
    observed_b = value.get("sft_checkpoint")
    if not isinstance(observed_b, dict) or any(observed_b.get(k) != v for k, v in expected_b.items()):
        raise ValueError("B identity mismatch")
except Exception as error:
    quarantine.mkdir(parents=True, exist_ok=True)
    destination = quarantine / f"before-{attempt}"
    if destination.exists():
        raise SystemExit("quarantine destination already exists")
    os.replace(output, destination)
    manifest = quarantine / f"before-{attempt}.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "stage_id": "WP9-c",
        "gate_id": "wp9c-calibration-initial-generation",
        "checkpoint_id": "C0",
        "quarantined_path": str(destination),
        "reason": f"incompatible_or_malformed_existing_output:{type(error).__name__}",
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"quarantined:{destination}")
    raise SystemExit(0)
status = value.get("status")
record_count = value.get("record_count")
print(f"resume:{status}:{record_count}")
PY_PREP
)" || fail_preflight "existing calibration generation preparation failed"
printf '[%s] generation action=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$OUTPUT_ACTION" >>"$LOG_FILE"

CURRENT_PHASE="generation"
set +e
"$CV" generate-refresh-calibration \
  --config "$REPO_ROOT/$CONFIG_REL" \
  --input-bundle-dir "$INPUT_DIR" \
  --sft-run-dir "$B_RUN" \
  --block initial \
  --output-dir "$OUTPUT_DIR" >>"$LOG_FILE" 2>&1
COMMAND_RC=$?
set -e
if (( COMMAND_RC != 0 )); then
  finalize_gate "$COMMAND_RC" 125 command_failed "generate-refresh-calibration exited nonzero"
  exit $?
fi

CURRENT_PHASE="postcheck"
set +e
"$PY" - "$POSTCHECK_FILE.tmp" "$INPUT_DIR" "$B_RUN" "$OUTPUT_DIR" "$HEAD_COMMIT" <<'PY_POSTCHECK'
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from code_verifier.training.calibration import _load_input_bundle, load_completed_calibration_generation
from code_verifier.training.sft import load_completed_sft_checkpoint
output, input_dir, b_run, generation_dir = map(Path, sys.argv[1:5])
checkpoint_commit = sys.argv[5]
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
input_manifest, inputs = _load_input_bundle(input_dir)
run, records = load_completed_calibration_generation(generation_dir)
b = load_completed_sft_checkpoint(b_run)
if len(inputs) != 10000 or len(records) != 80000 or run.get("record_count") != 80000 or run.get("block_index") != 0:
    raise SystemExit("Gate A generation count/block mismatch")
if run.get("input_manifest_sha256") != digest(input_dir / "input_manifest.json") or run.get("input_records_sha256") != input_manifest.get("records_sha256"):
    raise SystemExit("Gate A generation input binding mismatch")
expected_b = {
    "run_id": b.run_id,
    "model_id": b.model_id,
    "model_revision": b.model_revision,
    "dataset_hash": b.dataset_hash,
    "config_hash": b.config_hash,
    "dependency_lock_hash": b.dependency_lock_hash,
    "seed": b.seed,
}
observed_b = run.get("sft_checkpoint")
if not isinstance(observed_b, dict) or any(observed_b.get(k) != v for k, v in expected_b.items()):
    raise SystemExit("Gate A generation B binding mismatch")
by_problem: dict[str, list[dict[str, object]]] = defaultdict(list)
for row in records:
    pid = row.get("problem_id")
    if not isinstance(pid, str):
        raise SystemExit("Gate A generation problem_id type mismatch")
    by_problem[pid].append(row)
expected_ids = [item.problem_id for item in inputs]
if list(by_problem) != expected_ids or len(by_problem) != 10000:
    raise SystemExit("Gate A generation problem order mismatch")
for pid in expected_ids:
    rows = by_problem[pid]
    indices = [row.get("sample_index") for row in rows]
    if len(rows) != 8 or indices != list(range(8)):
        raise SystemExit(f"Gate A sample index mismatch for {pid}")
    for row in rows:
        tokens = row.get("completion_tokens")
        latency = row.get("generation_latency_ms")
        hit_max = row.get("hit_max_new_tokens")
        completion = row.get("completion")
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise SystemExit("Gate A completion token telemetry invalid")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or float(latency) < 0:
            raise SystemExit("Gate A generation latency telemetry invalid")
        if not isinstance(hit_max, bool) or not isinstance(completion, str):
            raise SystemExit("Gate A completion fields invalid")
payload = {
    "version": 1,
    "status": "passed",
    "stage_id": "WP9-c",
    "checkpoint_id": "C0",
    "operator_gate_id": "wp9c-calibration-initial-generation",
    "operator_checkpoint_commit": checkpoint_commit,
    "problem_count": len(by_problem),
    "record_count": len(records),
    "samples_per_problem": 8,
    "input_manifest_sha256": digest(input_dir / "input_manifest.json"),
    "input_records_sha256": input_manifest["records_sha256"],
    "problem_order_sha256": input_manifest["problem_order_sha256"],
    "generation_run_sha256": digest(generation_dir / "run.json"),
    "generation_records_sha256": digest(generation_dir / "samples" / "generations.jsonl"),
    "formal_b": expected_b,
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_POSTCHECK
POSTCHECK_RC=$?
set -e
if (( POSTCHECK_RC != 0 )); then
  rm -f "$POSTCHECK_FILE.tmp"
  finalize_gate 0 "$POSTCHECK_RC" postcheck_failed "strict Gate A postcheck failed"
  exit $?
fi
mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"

CURRENT_PHASE="complete"
finalize_gate 0 0 passed "WP9-c Gate A initial 10,000 x 8 frozen-B calibration generation completed and strict postcheck passed"
exit $?
