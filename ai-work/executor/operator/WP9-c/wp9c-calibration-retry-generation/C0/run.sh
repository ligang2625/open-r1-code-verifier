#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-c"
GATE_ID="wp9c-calibration-retry-generation"
CHECKPOINT_ID="C0"
PLAN_COMMIT="5a1f083af6bfdf2e1333bd70e95e9257b4e66b48"
INITIAL_HANDOFF_COMMIT="c3cf0d66befe99be38c83925ba8b8980a71b1dce"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560"
CALIBRATION_CONFIG_SHA="97b2706808e1d4d2fa9088be018617c3e1459633767d3505de138fc5f48c68b0"
CHECKPOINT_METADATA_SHA="341e59d37802e19a907c88f413347ba140930b6e9d48d742d9ee5e8048858a12"

INPUT_MANIFEST_SHA="f53cd897530756df5e8ae78903bf52225dc988d636051a4030323b71726506d5"
INPUT_RECORDS_SHA="18c77583dc0695747fd5d6a46a3439730f4e3abc0b8e32a7f79aafa4e1b46361"
INPUT_ORDER_SHA="e48e3803be5a7a6d497f677e0bc2da2233840b56cade7a7f4305579d770687de"
RETRY_MANIFEST_SHA="251e7eac7aba350925734aa024e95165f1358195d4e0811a3e48f3757c54edab"
RETRY_ORDER_SHA="337c9b85a6744f308dec1a699ce71421a2d5a6c94e2e73748b429fbe2932e111"
INITIAL_SCORE_MANIFEST_SHA="2147d72603001ee2fdc951470f3981d6f373a5c3e4e21dc20b4736a5b3fda771"
INITIAL_SCORE_RECORDS_SHA="9bb39a67e3c97ca3a84c1e1393bf5e17824e4d9eacb93410c35a865aaac04621"
INITIAL_GENERATION_MANIFEST_SHA="7ab6d5a2bff51cc1871cc06d59b3ccb37080e309f3c82abb9ccfd31e58a58cb8"
INITIAL_GENERATION_RECORDS_SHA="c90a46254d05bb9abe043c6ca6c82696ab4ab2b2cfd58b21e6817f50e726e622"
WP9A_MANIFEST_SHA="98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625"
WP9A_PUBLIC_SHA="cc2d033ae580d26bb346f5a1e1058645b365c2f5d76cd6b1d6662f8f294126ad"
WP9A_HIDDEN_SHA="e4d72704841095bf057ccbf6318db138429caab11f02886ad892a950ac73a65d"

B_RUN_NAME="B-sft-formal-seed42"
B_MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
B_MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
B_DATASET_HASH="4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c"
B_CONFIG_HASH="250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244"
B_CHECKPOINT_SHA="0fe4ff5d18b980bf6109007b0f0a0a229c716cbcd713d687d642e852e280dbba"

RETRY_PROBLEM_COUNT="4386"
EXPECTED_RECORD_COUNT="35088"
PROBLEM_BATCH_SIZE="4"

PLAN_REL="ai-work/planner/WP9-c-plan.md"
SCRIPT_REL="ai-work/executor/operator/WP9-c/wp9c-calibration-retry-generation/C0/run.sh"
CHECKPOINT_REL="ai-work/executor/operator/WP9-c/wp9c-calibration-retry-generation/C0/checkpoint.json"
CONFIG_REL="configs/grpo/refresh-calibration.yaml"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
[[ -x "$PY" && -x "$CV" ]] || { echo "target checkout .venv is unavailable; do not start retry generation" >&2; exit 125; }

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
import re
import sys
from pathlib import Path

def reject_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value

try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
    raise SystemExit(f"validation machine pointer is not strict JSON: {type(error).__name__}") from None
required = {
    "version", "machine_status", "bootstrap_project_commit", "open_r1_commit",
    "artifact_root", "hf_home", "formal_data_root", "readiness_record",
}
if not isinstance(value, dict) or not required.issubset(value):
    raise SystemExit("validation machine pointer schema is missing required fields")
if value["version"] != 1 or value["machine_status"] != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine pointer is not READY_FOR_VALIDATION_PLANNER")
for key in ("bootstrap_project_commit", "open_r1_commit"):
    item = value[key]
    if not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{40}", item) is None:
        raise SystemExit(f"validation machine pointer {key} must be exact lowercase 40-hex")
for key in ("artifact_root", "hf_home", "formal_data_root", "readiness_record"):
    item = value[key]
    if not isinstance(item, str) or not Path(item).is_absolute() or any(char in item for char in "\t\r\n"):
        raise SystemExit(f"validation machine pointer {key} must be an absolute control-free path")
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
export TMPDIR="/root/tmp"

INPUT_DIR="$FORMAL_DATA_ROOT/wp9c/calibration-input-C4-qualitysafe-5000"
RETRY_MANIFEST="$FORMAL_DATA_ROOT/wp9c/retry_problem_ids.jsonl"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
OUTPUT_DIR="$ARTIFACT_ROOT/wp9c/calibration/retry"
GATE_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/$GATE_ID"
OP_ROOT="$GATE_ROOT/$CHECKPOINT_ID"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
POSTCHECK_FILE="$OP_ROOT/postcheck-summary.json"
LOCK_FILE="$GATE_ROOT/run.lock"

mkdir -p "$OP_ROOT" /root/tmp
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Gate B operator lock is already held: $LOCK_FILE" >&2
  exit 73
fi

ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-${BASHPID}"
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
[[ ! -f "$STATUS_FILE" ]] || mv "$STATUS_FILE" "$OP_ROOT/status.before-$ATTEMPT_ID"
[[ ! -f "$EVIDENCE_FILE" ]] || mv "$EVIDENCE_FILE" "$OP_ROOT/operator-evidence.before-$ATTEMPT_ID.json"
[[ ! -f "$POSTCHECK_FILE" ]] || mv "$POSTCHECK_FILE" "$OP_ROOT/postcheck-summary.before-$ATTEMPT_ID.json"
rm -f "$STATUS_FILE.tmp" "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE.tmp"
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
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [[ -n "$HEAD_COMMIT" ]] || HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$SCRIPT_SHA" ]] || SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$HEAD_COMMIT" "$SCRIPT_SHA" "$MACHINE_SHA" "$READINESS_SHA" \
    "$GPU_NAME" "$GPU_VRAM_MIB" "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" \
    "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" "$INPUT_DIR" "$RETRY_MANIFEST" "$B_RUN" "$OUTPUT_DIR" \
    "$OUTPUT_ACTION" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path

(
    output, postcheck_path, head, script_sha, machine_sha, readiness_sha, gpu_name, gpu_vram,
    open_r1, lock_sha, torch_version, cuda_version, artifact_root, hf_home, formal_data_root,
    input_dir, retry_manifest, b_run, output_dir, output_action, command_rc, postcheck_rc,
    gate_status, note, start_time, end_time, attempt_id,
) = sys.argv[1:]

def digest(path: Path):
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inventory(path: Path):
    item = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        item.update(size_bytes=path.stat().st_size, sha256=digest(path))
    return item

postcheck_file = Path(postcheck_path)
postcheck = json.loads(postcheck_file.read_text(encoding="utf-8")) if postcheck_file.is_file() else None
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP9-c",
    "source_plan_commit": "5a1f083af6bfdf2e1333bd70e95e9257b4e66b48",
    "source_initial_generation_handoff_commit": "c3cf0d66befe99be38c83925ba8b8980a71b1dce",
    "operator_checkpoint_commit": head,
    "checkpoint_id": "C0",
    "operator_gate_id": "wp9c-calibration-retry-generation",
    "operator_script": "ai-work/executor/operator/WP9-c/wp9c-calibration-retry-generation/C0/run.sh",
    "operator_script_sha256": script_sha,
    "checkpoint_metadata_sha256": "341e59d37802e19a907c88f413347ba140930b6e9d48d742d9ee5e8048858a12",
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record_sha256": readiness_sha or None,
    "gpu_name": gpu_name or None,
    "gpu_vram_mib": int(gpu_vram) if gpu_vram.isdigit() else None,
    "resolved_roots": {"artifact_root": artifact_root, "hf_home": hf_home, "formal_data_root": formal_data_root},
    "runtime_identity": {
        "open_r1_commit": open_r1 or None,
        "dependency_lock_hash": lock_sha or None,
        "torch_version": torch_version or None,
        "cuda_version": cuda_version or None,
    },
    "input_bundle": {"path": input_dir, "input_manifest_sha256": "f53cd897530756df5e8ae78903bf52225dc988d636051a4030323b71726506d5"},
    "retry_manifest": {"path": retry_manifest, "sha256": "251e7eac7aba350925734aa024e95165f1358195d4e0811a3e48f3757c54edab", "problem_count": 4386},
    "formal_b_run": b_run,
    "generation_output": output_dir,
    "problem_batch_size": 4,
    "expected_problem_count": 4386,
    "expected_record_count": 35088,
    "generation_action": output_action,
    "postcheck": postcheck,
    "expected_artifact_inventory": [
        inventory(Path(output_dir) / "run.json"),
        inventory(Path(output_dir) / "samples" / "generations.jsonl"),
        inventory(Path(output_dir) / "samples" / "progress.json"),
        inventory(Path(retry_manifest)),
        inventory(postcheck_file),
    ],
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
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" final_rc
  trap - ERR INT TERM
  write_evidence "$command_rc" "$postcheck_rc" "$gate_status" "$note"
  final_rc=1
  if [[ "$gate_status" == "passed" && "$command_rc" == "0" && "$postcheck_rc" == "0" ]]; then
    final_rc=0
  elif [[ "$command_rc" =~ ^[0-9]+$ ]] && (( command_rc > 0 && command_rc < 126 )); then
    final_rc="$command_rc"
  fi
  printf '%s\n' "$final_rc" >"$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  printf '[%s] attempt=%s end phase=%s command_rc=%s postcheck_rc=%s gate_status=%s note=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ATTEMPT_ID" "$CURRENT_PHASE" "$command_rc" "$postcheck_rc" "$gate_status" "$note" >>"$LOG_FILE"
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
  finalize_gate "$rc" 125 internal_error "unexpected shell error at line $line" || true
  exit "$rc"
}
on_signal() {
  local rc="$1" name="$2"
  [[ "$FINALIZED" == "0" ]] || exit "$rc"
  finalize_gate "$rc" 125 interrupted "received $name during $CURRENT_PHASE" || true
  exit "$rc"
}
trap 'on_err "$LINENO" "$?"' ERR
trap 'on_signal 130 INT' INT
trap 'on_signal 143 TERM' TERM

EXPECTED_HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
[[ "$EXPECTED_HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail_preflight "set WP9C_HANDOFF_COMMIT to the exact 40-hex retry handoff commit before running"
HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve target HEAD"
[[ "$HEAD_COMMIT" == "$EXPECTED_HANDOFF_COMMIT" ]] || fail_preflight "target HEAD does not equal WP9C_HANDOFF_COMMIT"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --ignore-submodules=none)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge must remain untracked"
git -C "$REPO_ROOT" merge-base --is-ancestor "$INITIAL_HANDOFF_COMMIT" "$HEAD_COMMIT" || fail_preflight "C5 initial-generation handoff commit is not an ancestor of target HEAD"
git -C "$REPO_ROOT" merge-base --is-ancestor "$BOOTSTRAP_COMMIT" "$HEAD_COMMIT" || fail_preflight "validation-machine bootstrap commit is not an ancestor of target HEAD"
if ! git -C "$REPO_ROOT" diff --quiet "$PLAN_COMMIT" "$HEAD_COMMIT" -- "$PLAN_REL"; then
  fail_preflight "sealed WP9-c plan changed after plan commit"
fi
[[ "$MACHINE_OPEN_R1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "validation machine Open-R1 identity changed"

if ! "$PY" - "$REPO_ROOT" "$HEAD_COMMIT" "$SCRIPT_REL" "$CHECKPOINT_REL" <<'PY_TRACKED'
import subprocess
import sys
from pathlib import Path
repo = Path(sys.argv[1])
head, script, checkpoint = sys.argv[2:]
script_line = subprocess.run(["git", "-C", str(repo), "ls-tree", head, "--", script], check=True, capture_output=True, text=True).stdout.strip()
checkpoint_line = subprocess.run(["git", "-C", str(repo), "ls-tree", head, "--", checkpoint], check=True, capture_output=True, text=True).stdout.strip()
if not script_line.startswith("100755 "):
    raise SystemExit("tracked retry operator script must be executable")
if not checkpoint_line.startswith("100644 "):
    raise SystemExit("tracked retry checkpoint metadata must be a regular file")
PY_TRACKED
then
  fail_preflight "tracked retry handoff files are missing or have invalid modes"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$(sha256sum "$REPO_ROOT/$CHECKPOINT_REL" | awk '{print $1}')" == "$CHECKPOINT_METADATA_SHA" ]] || fail_preflight "retry checkpoint metadata SHA mismatch"

if ! "$PY" - "$REPO_ROOT/$CHECKPOINT_REL" <<'PY_CHECKPOINT'
import json
import sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "version": 1,
    "stage_id": "WP9-c",
    "checkpoint_id": "C0",
    "source_plan_commit": "5a1f083af6bfdf2e1333bd70e95e9257b4e66b48",
    "source_initial_generation_handoff_commit": "c3cf0d66befe99be38c83925ba8b8980a71b1dce",
    "operator_gate_id": "wp9c-calibration-retry-generation",
    "operator_handoff_mode": "portable_target",
    "operator_restart_policy": "exact_prefix_resume_or_strict_completed",
    "calibration_config_sha256": "97b2706808e1d4d2fa9088be018617c3e1459633767d3505de138fc5f48c68b0",
    "problem_batch_size": 4,
    "retry_problem_count": 4386,
    "expected_record_count": 35088,
    "expected_sample_index_start": 8,
    "expected_sample_index_end": 15,
    "retry_problem_order_sha256": "337c9b85a6744f308dec1a699ce71421a2d5a6c94e2e73748b429fbe2932e111",
    "retry_manifest_sha256": "251e7eac7aba350925734aa024e95165f1358195d4e0811a3e48f3757c54edab",
    "status": "awaiting_operator",
}
for key, item in expected.items():
    if value.get(key) != item:
        raise SystemExit(f"retry checkpoint metadata mismatch: {key}")
if value.get("retry_manifest", {}).get("byte_identity_required") is not True:
    raise SystemExit("retry checkpoint must require byte-identical retry manifest")
PY_CHECKPOINT
then
  fail_preflight "retry checkpoint metadata validation failed"
fi

for root in "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT"; do
  [[ "$root" == /root || "$root" == /root/* ]] || fail_preflight "active WP9 target root must be under /root: $root"
  [[ "$root" != /data && "$root" != /data/* ]] || fail_preflight "retired /data root must not be active: $root"
done
[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -r "$TARGET_HF_HOME" && -d "$FORMAL_DATA_ROOT" && -r "$FORMAL_DATA_ROOT" ]] || fail_preflight "target persistent roots are unavailable"
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
vram_mib = int(p.total_memory // (1024 * 1024))
if "RTX 4090" not in p.name or vram_mib < 22528 or not torch.cuda.is_bf16_supported():
    raise SystemExit("visible GPU is not the certified RTX 4090 BF16 target")
print(f"{p.name}\t{vram_mib}")
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
print("\t".join([current["open_r1_commit"], current["dependency_lock_hash"], current["packages"]["torch"], current["cuda_version"]]))
PY_RUNTIME
)" || fail_preflight "target runtime identity validation failed"
IFS="$TAB" read -r CURRENT_OPEN_R1 CURRENT_LOCK_SHA CURRENT_TORCH CURRENT_CUDA <<<"$RUNTIME_FIELDS"

[[ "$(sha256sum "$REPO_ROOT/$CONFIG_REL" | awk '{print $1}')" == "$CALIBRATION_CONFIG_SHA" ]] || fail_preflight "tracked calibration config SHA changed"
if ! "$PY" - "$REPO_ROOT/$CONFIG_REL" <<'PY_CONFIG'
import sys
from pathlib import Path
from code_verifier.training.calibration import load_calibration_config
config = load_calibration_config(Path(sys.argv[1]))
if (config.initial_generations, config.retry_generations, config.temperature, config.top_p, config.max_new_tokens, config.max_prompt_tokens, config.active_pool_size) != (8, 8, 0.8, 0.95, 512, 2048, 3000):
    raise SystemExit("tracked calibration config protocol mismatch")
PY_CONFIG
then
  fail_preflight "tracked calibration config strict protocol validation failed"
fi

[[ -d "$INPUT_DIR" ]] || fail_preflight "formal C4 quality-safe calibration input is missing: $INPUT_DIR"
[[ -f "$RETRY_MANIFEST" ]] || fail_preflight "canonical retry manifest is missing: $RETRY_MANIFEST"
if ! "$PY" - "$INPUT_DIR" "$RETRY_MANIFEST" <<'PY_INPUT_RETRY'
import hashlib
import json
import sys
from pathlib import Path
from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.training.calibration import _load_input_bundle

input_root = Path(sys.argv[1])
retry_path = Path(sys.argv[2])
def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
manifest, records = _load_input_bundle(input_root)
if digest(input_root / "input_manifest.json") != "f53cd897530756df5e8ae78903bf52225dc988d636051a4030323b71726506d5":
    raise SystemExit("formal calibration input manifest SHA mismatch")
if manifest.get("records_sha256") != "18c77583dc0695747fd5d6a46a3439730f4e3abc0b8e32a7f79aafa4e1b46361" or manifest.get("problem_order_sha256") != "e48e3803be5a7a6d497f677e0bc2da2233840b56cade7a7f4305579d770687de":
    raise SystemExit("formal calibration input records/order mismatch")
if len(records) != 5000 or any(item.quality_gate_required or item.overlap_origin != "external_new" for item in records):
    raise SystemExit("formal calibration input population mismatch")
if digest(retry_path) != "251e7eac7aba350925734aa024e95165f1358195d4e0811a3e48f3757c54edab":
    raise SystemExit("retry manifest is not byte-identical to initial scoring output")
rows = [json.loads(line) for line in retry_path.read_text(encoding="utf-8").splitlines() if line]
if any(set(row) != {"problem_id"} or not isinstance(row.get("problem_id"), str) for row in rows):
    raise SystemExit("retry manifest schema mismatch")
ids = [row["problem_id"] for row in rows]
if len(ids) != 4386 or ids != sorted(ids) or len(ids) != len(set(ids)):
    raise SystemExit("retry manifest count/order/uniqueness mismatch")
if stable_json_hash(ids) != "337c9b85a6744f308dec1a699ce71421a2d5a6c94e2e73748b429fbe2932e111":
    raise SystemExit("retry problem-order hash mismatch")
input_ids = {item.problem_id for item in records}
if any(problem_id not in input_ids for problem_id in ids):
    raise SystemExit("retry manifest is not a subset of formal calibration input")
PY_INPUT_RETRY
then
  fail_preflight "formal input/retry-manifest strict validation failed"
fi

if ! "$PY" - "$B_RUN" <<'PY_B'
import sys
from pathlib import Path
from code_verifier.training.calibration import _sft_identity
from code_verifier.training.sft import load_completed_sft_checkpoint
run = load_completed_sft_checkpoint(Path(sys.argv[1]))
identity = _sft_identity(run)
expected = {
    "run_id": "B-sft-formal-seed42",
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "dataset_hash": "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c",
    "config_hash": "250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244",
    "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
    "seed": 42,
    "checkpoint_sha256": "0fe4ff5d18b980bf6109007b0f0a0a229c716cbcd713d687d642e852e280dbba",
}
if identity != expected:
    raise SystemExit("formal B checkpoint identity mismatch")
PY_B
then
  fail_preflight "formal B strict identity validation failed"
fi
