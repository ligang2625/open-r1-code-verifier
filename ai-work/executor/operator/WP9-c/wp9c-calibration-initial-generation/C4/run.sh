#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-c"
GATE_ID="wp9c-calibration-initial-generation"
CHECKPOINT_ID="C4"
PLAN_COMMIT="5a1f083af6bfdf2e1333bd70e95e9257b4e66b48"
RESULT_CODE_COMMIT="643bba54b5f92c74796922f51ea9eb4c1aae655b"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560"
CALIBRATION_CONFIG_SHA="97b2706808e1d4d2fa9088be018617c3e1459633767d3505de138fc5f48c68b0"
INPUT_MANIFEST_SHA="f53cd897530756df5e8ae78903bf52225dc988d636051a4030323b71726506d5"
INPUT_RECORDS_SHA="18c77583dc0695747fd5d6a46a3439730f4e3abc0b8e32a7f79aafa4e1b46361"
INPUT_ORDER_SHA="e48e3803be5a7a6d497f677e0bc2da2233840b56cade7a7f4305579d770687de"
EXCLUDED_CONTEXT_SHA="83219a69b08ffe5348f15e3078389dece3f94e28a8964ac9604ee9d80cf21e1f"
WP9A_MANIFEST_SHA="98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625"
WP9A_SELECTED_ORDER_SHA="355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001"
CONTEXT_FILTER_POLICY="chat_template_prompt_cap_v1"
SOURCE_RECORD_COUNT="10000"
CONTEXT_ELIGIBLE_RECORD_COUNT="9621"
QUALITY_ELIGIBLE_RECORD_COUNT="8549"
QUALITY_EXCLUDED_RECORD_COUNT="1072"
QUALITY_EXCLUDED_SHA="ac6559ae28f59808797462d235b5c8fc8ba0c8eddf16298cb157764767519b3b"
TRANCHE_RESERVE_RECORD_COUNT="3549"
TRANCHE_RESERVE_SHA="3fac92dc70e725fefb86899fe600885380ef0bcdbb07a6de28f6c7dbf2a78df2"
CANDIDATE_FILTER_POLICY="quality_safe_stratified_tranche_v1"
ELIGIBLE_RECORD_COUNT="5000"
EXCLUDED_RECORD_COUNT="379"
MAX_PROMPT_TOKENS="2048"
MAX_NEW_TOKENS="512"
EXPECTED_RECORD_COUNT="40000"
B_RUN_NAME="B-sft-formal-seed42"
B_MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
B_MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
B_DATASET_HASH="4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c"
B_CONFIG_HASH="250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244"
B_ADAPTER_MODEL_SHA="51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67"
B_ADAPTER_CONFIG_SHA="3738f9ef0ac56f90a48497ab4c0a1f172770864aa61dad56e8d9751050f34344"
MODEL_WEIGHTS_SHA="c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
MODEL_CONFIG_SHA="88f9a17863c05fb313515d2ff74b1098e0c35579f99068e32beda00618508ae0"
MODEL_GENERATION_CONFIG_SHA="1a628a5775bc69cde01c6749a531150ca4d3189652c618a174f7077923acf3b1"
MODEL_TOKENIZER_SHA="c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"
MODEL_TOKENIZER_CONFIG_SHA="959e7f1d9a1b7641a6d6ce05ca97b75c7894fcb66cbe5a040406458fb1128ee4"
MODEL_VOCAB_SHA="ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"
MODEL_MERGES_SHA="599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3"
PROBLEM_BATCH_SIZE="4"

PLAN_REL="ai-work/planner/WP9-c-plan.md"
REPORT_REL="ai-work/executor/WP9-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C4/run.sh"
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
import re
import sys
from pathlib import Path

def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
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
    if not isinstance(item, str) or any(char in item for char in "\t\r\n") or not Path(item).is_absolute():
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

INPUT_DIR="$FORMAL_DATA_ROOT/wp9c/calibration-input-C4-qualitysafe-5000"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
OUTPUT_DIR="$ARTIFACT_ROOT/wp9c/calibration/initial"
QUARANTINE_ROOT="$ARTIFACT_ROOT/wp9c/quarantine/calibration/initial"
GATE_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/$GATE_ID"
OP_ROOT="$GATE_ROOT/$CHECKPOINT_ID"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
POSTCHECK_FILE="$OP_ROOT/postcheck-summary.json"
LOCK_FILE="$GATE_ROOT/run.lock"
LEGACY_C0_LOCK_FILE="$GATE_ROOT/C0/run.lock"
LEGACY_C1_LOCK_FILE="$GATE_ROOT/C1/run.lock"
LEGACY_C3_LOCK_FILE="$GATE_ROOT/C3/run.lock"
C3_EVIDENCE_FILE="$GATE_ROOT/C3/operator-evidence.json"
C3_EVIDENCE_SHA="950d605a5e46af424d11e7d94fa5a6511c61f2c711df592c68a289f298b0eb2e"

mkdir -p "$OP_ROOT" "$GATE_ROOT/C0" "$GATE_ROOT/C1" "$GATE_ROOT/C3"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Gate A operator lock is already held: $LOCK_FILE" >&2
  exit 73
fi
exec 8>"$LEGACY_C3_LOCK_FILE"
if ! flock -n 8; then
  echo "superseded C3 operator lock is active: $LEGACY_C3_LOCK_FILE" >&2
  exit 73
fi
exec 7>"$LEGACY_C1_LOCK_FILE"
if ! flock -n 7; then
  echo "superseded C1 operator lock is active: $LEGACY_C1_LOCK_FILE" >&2
  exit 73
fi
exec 6>"$LEGACY_C0_LOCK_FILE"
if ! flock -n 6; then
  echo "superseded C0 operator lock is active: $LEGACY_C0_LOCK_FILE" >&2
  exit 73
fi
[[ -f "$C3_EVIDENCE_FILE" ]] || { echo "superseded C3 operator evidence is missing: $C3_EVIDENCE_FILE" >&2; exit 125; }
C3_EVIDENCE_ACTUAL_SHA="$(sha256sum "$C3_EVIDENCE_FILE" | awk '{print $1}')"
[[ "$C3_EVIDENCE_ACTUAL_SHA" == "$C3_EVIDENCE_SHA" ]] || { echo "superseded C3 operator evidence SHA mismatch" >&2; exit 125; }
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
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time generation_started
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [[ -n "$HEAD_COMMIT" ]] || HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$SCRIPT_SHA" ]] || SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  generation_started=false
  [[ "$CURRENT_PHASE" == "preflight" || "$OUTPUT_ACTION" == reuse_completed:* ]] || generation_started=true
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$REPO_ROOT" "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" \
    "$MACHINE_POINTER" "$READINESS_RECORD" "$HEAD_COMMIT" "$SCRIPT_SHA" "$MACHINE_SHA" "$READINESS_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" \
    "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$INPUT_DIR" "$B_RUN" "$OUTPUT_DIR" "$OUTPUT_ACTION" "$PROBLEM_BATCH_SIZE" \
    "$generation_started" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path
(
    output, postcheck_path, repo_root, artifact_root, hf_home, formal_data_root,
    machine_pointer, readiness_record, checkpoint_commit, script_sha, machine_sha,
    readiness_sha, gpu_name, gpu_vram_mib, open_r1_commit, dependency_lock_sha,
    torch_version, cuda_version, input_dir, b_run, output_dir, output_action, problem_batch_size,
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
    inventory(run_root / "samples" / "progress.json"),
    inventory(Path(b_run) / "checkpoints" / "adapter_config.json"),
    inventory(Path(b_run) / "checkpoints" / "adapter_model.safetensors"),
    inventory(postcheck_file),
]
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP9-c",
    "source_plan_commit": "5a1f083af6bfdf2e1333bd70e95e9257b4e66b48",
    "operator_checkpoint_commit": checkpoint_commit,
    "result_code_commit": "643bba54b5f92c74796922f51ea9eb4c1aae655b",
    "checkpoint_id": "C4",
    "supersedes_checkpoint": "C3",
    "operator_gate_id": "wp9c-calibration-initial-generation",
    "operator_script": "ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C4/run.sh",
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
        "input_manifest_sha256": "f53cd897530756df5e8ae78903bf52225dc988d636051a4030323b71726506d5",
        "records_sha256": "18c77583dc0695747fd5d6a46a3439730f4e3abc0b8e32a7f79aafa4e1b46361",
        "problem_order_sha256": "e48e3803be5a7a6d497f677e0bc2da2233840b56cade7a7f4305579d770687de",
        "excluded_context_sha256": "83219a69b08ffe5348f15e3078389dece3f94e28a8964ac9604ee9d80cf21e1f",
        "context_filter_policy": "chat_template_prompt_cap_v1",
        "source_record_count": 10000,
        "context_eligible_record_count": 9621,
        "quality_eligible_record_count": 8549,
        "quality_excluded_record_count": 1072,
        "selected_record_count": 5000,
        "tranche_reserve_record_count": 3549,
        "excluded_quality_sha256": "ac6559ae28f59808797462d235b5c8fc8ba0c8eddf16298cb157764767519b3b",
        "tranche_reserve_sha256": "3fac92dc70e725fefb86899fe600885380ef0bcdbb07a6de28f6c7dbf2a78df2",
        "excluded_record_count": 379,
        "max_prompt_tokens": 2048,
        "max_new_tokens": 512,
        "tokenizer_model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "tokenizer_model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    },
    "formal_b_run": b_run,
    "base_model_snapshot": {
        "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
        "files_sha256": {
            "model.safetensors": "c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8",
            "config.json": "88f9a17863c05fb313515d2ff74b1098e0c35579f99068e32beda00618508ae0",
            "generation_config.json": "1a628a5775bc69cde01c6749a531150ca4d3189652c618a174f7077923acf3b1",
            "tokenizer.json": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
            "tokenizer_config.json": "959e7f1d9a1b7641a6d6ce05ca97b75c7894fcb66cbe5a040406458fb1128ee4",
            "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
            "merges.txt": "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3",
        },
    },
    "generation_output": output_dir,
    "problem_batch_size": int(problem_batch_size),
    "expected_problem_count": 5000,
    "expected_record_count": 40000,
    "superseded_c3_operator_evidence": inventory(Path(artifact_root) / "operator" / "WP9-c" / "5a1f083af6bfdf2e1333bd70e95e9257b4e66b48" / "wp9c-calibration-initial-generation" / "C3" / "operator-evidence.json"),
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

EXPECTED_HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
[[ "$EXPECTED_HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail_preflight "set WP9C_HANDOFF_COMMIT to the exact 40-hex C4 handoff commit before running"
HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve target HEAD"
[[ "$HEAD_COMMIT" == "$EXPECTED_HANDOFF_COMMIT" ]] || fail_preflight "target HEAD does not equal WP9C_HANDOFF_COMMIT"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --ignore-submodules=none)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge must remain untracked"
if ! git -C "$REPO_ROOT" diff --quiet "$PLAN_COMMIT" "$HEAD_COMMIT" -- "$PLAN_REL"; then
  fail_preflight "sealed WP9-c plan changed after plan commit"
fi
[[ "$MACHINE_OPEN_R1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "validation machine Open-R1 identity changed"
git -C "$REPO_ROOT" merge-base --is-ancestor "$RESULT_CODE_COMMIT" "$HEAD_COMMIT" || fail_preflight "C4 repair result-code commit is not an ancestor of target HEAD"
git -C "$REPO_ROOT" merge-base --is-ancestor "$BOOTSTRAP_COMMIT" "$HEAD_COMMIT" || fail_preflight "validation-machine bootstrap commit is not an ancestor of target HEAD"
if ! "$PY" - "$REPO_ROOT" "$HEAD_COMMIT" "$REPORT_REL" "$SCRIPT_REL" <<'PY_SCOPE'
import subprocess
import sys
from pathlib import Path
repo = Path(sys.argv[1])
head, report, script = sys.argv[2:]
for relative in (report, script):
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", head, "--", relative],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if not tracked:
        raise SystemExit(f"C4 handoff path is not tracked at target HEAD: {relative}")
mode_line = subprocess.run(
    ["git", "-C", str(repo), "ls-tree", head, "--", script],
    check=True, capture_output=True, text=True,
).stdout.strip()
if not mode_line.startswith("100755 "):
    raise SystemExit("tracked C4 operator script is not executable")
PY_SCOPE
then
  fail_preflight "C4 tracked handoff validation failed"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" <<'PY_META'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind("checkpoint_id: C4")
if pos < 0:
    raise SystemExit("C4 checkpoint block is missing")
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit("C4 checkpoint block is malformed")
block = text[start:end]
def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"C4 checkpoint field missing: {name}")
    return match.group(1).strip().strip('"').strip("'")
print("\t".join([
    field("stage_id"), field("task_kind"), field("source_plan_commit"), field("source_review_round"),
    field("source_review_commit"), field("repair_issue_ids"), field("result_code_commit"), field("operator_gate_id"),
    field("operator_handoff_mode"), field("operator_restart_policy"), field("supersedes_checkpoint"), field("operator_script_sha256"), field("input_manifest_sha256"),
    field("input_records_sha256"), field("input_problem_order_sha256"), field("excluded_context_sha256"), field("wp9a_manifest_sha256"),
    field("wp9a_selected_order_sha256"), field("calibration_config_sha256"), field("problem_batch_size"),
    field("context_filter_policy"), field("source_record_count"), field("eligible_record_count"), field("excluded_record_count"),
    field("max_prompt_tokens"), field("max_new_tokens"), field("expected_problem_count"), field("expected_record_count"),
    field("base_model_weights_sha256"), field("base_model_config_sha256"), field("base_model_generation_config_sha256"),
    field("base_model_tokenizer_sha256"), field("base_model_tokenizer_config_sha256"), field("base_model_vocab_sha256"),
    field("base_model_merges_sha256"), field("status"),
]))
PY_META
)" || fail_preflight "cannot parse C4 checkpoint metadata"
IFS="$TAB" read -r CHECKPOINT_STAGE CHECKPOINT_TASK CHECKPOINT_PLAN CHECKPOINT_REVIEW_ROUND CHECKPOINT_REVIEW_COMMIT CHECKPOINT_REPAIR_IDS CHECKPOINT_RESULT CHECKPOINT_GATE CHECKPOINT_MODE CHECKPOINT_RESTART CHECKPOINT_SUPERSEDES EXPECTED_SCRIPT_SHA CHECKPOINT_INPUT_MANIFEST CHECKPOINT_INPUT_RECORDS CHECKPOINT_INPUT_ORDER CHECKPOINT_EXCLUDED_SHA CHECKPOINT_WP9A CHECKPOINT_WP9A_ORDER CHECKPOINT_CONFIG_SHA CHECKPOINT_BATCH_SIZE CHECKPOINT_FILTER_POLICY CHECKPOINT_SOURCE_COUNT CHECKPOINT_ELIGIBLE_COUNT CHECKPOINT_EXCLUDED_COUNT CHECKPOINT_MAX_PROMPT CHECKPOINT_MAX_NEW CHECKPOINT_PROBLEM_COUNT CHECKPOINT_RECORD_COUNT CHECKPOINT_MODEL_WEIGHTS CHECKPOINT_MODEL_CONFIG CHECKPOINT_MODEL_GENERATION_CONFIG CHECKPOINT_MODEL_TOKENIZER CHECKPOINT_MODEL_TOKENIZER_CONFIG CHECKPOINT_MODEL_VOCAB CHECKPOINT_MODEL_MERGES CHECKPOINT_STATUS <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_STAGE" == "$STAGE_ID" && "$CHECKPOINT_TASK" == "repair" && "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" ]] || fail_preflight "C4 repair source provenance mismatch"
[[ "$CHECKPOINT_REVIEW_ROUND" == "null" && "$CHECKPOINT_REVIEW_COMMIT" == "null" && "$CHECKPOINT_REPAIR_IDS" == "[]" ]] || fail_preflight "C4 user-directed repair must not fabricate review provenance"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" && "$CHECKPOINT_GATE" == "$GATE_ID" && "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_RESTART" == "exact_prefix_or_strict_completed_reuse_after_identity_quarantine" && "$CHECKPOINT_SUPERSEDES" == "C3" ]] || fail_preflight "C4 gate/handoff/restart provenance mismatch"
[[ "$CHECKPOINT_INPUT_MANIFEST" == "$INPUT_MANIFEST_SHA" && "$CHECKPOINT_INPUT_RECORDS" == "$INPUT_RECORDS_SHA" && "$CHECKPOINT_INPUT_ORDER" == "$INPUT_ORDER_SHA" && "$CHECKPOINT_EXCLUDED_SHA" == "$EXCLUDED_CONTEXT_SHA" ]] || fail_preflight "C4 filtered input bundle identity mismatch"
[[ "$CHECKPOINT_WP9A" == "$WP9A_MANIFEST_SHA" && "$CHECKPOINT_WP9A_ORDER" == "$WP9A_SELECTED_ORDER_SHA" ]] || fail_preflight "C4 WP9-a authority mismatch"
[[ "$CHECKPOINT_CONFIG_SHA" == "$CALIBRATION_CONFIG_SHA" && "$CHECKPOINT_BATCH_SIZE" == "$PROBLEM_BATCH_SIZE" && "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "C4 config/batch/status metadata mismatch"
[[ "$CHECKPOINT_FILTER_POLICY" == "$CONTEXT_FILTER_POLICY" && "$CHECKPOINT_SOURCE_COUNT" == "$SOURCE_RECORD_COUNT" && "$CHECKPOINT_ELIGIBLE_COUNT" == "$ELIGIBLE_RECORD_COUNT" && "$CHECKPOINT_EXCLUDED_COUNT" == "$EXCLUDED_RECORD_COUNT" ]] || fail_preflight "C4 context-filter policy/count metadata mismatch"
[[ "$CHECKPOINT_MAX_PROMPT" == "$MAX_PROMPT_TOKENS" && "$CHECKPOINT_MAX_NEW" == "$MAX_NEW_TOKENS" && "$CHECKPOINT_PROBLEM_COUNT" == "$ELIGIBLE_RECORD_COUNT" && "$CHECKPOINT_RECORD_COUNT" == "$EXPECTED_RECORD_COUNT" ]] || fail_preflight "C4 context/output count metadata mismatch"
[[ "$CHECKPOINT_MODEL_WEIGHTS" == "$MODEL_WEIGHTS_SHA" && "$CHECKPOINT_MODEL_CONFIG" == "$MODEL_CONFIG_SHA" && "$CHECKPOINT_MODEL_GENERATION_CONFIG" == "$MODEL_GENERATION_CONFIG_SHA" ]] || fail_preflight "C4 base-model core snapshot metadata mismatch"
[[ "$CHECKPOINT_MODEL_TOKENIZER" == "$MODEL_TOKENIZER_SHA" && "$CHECKPOINT_MODEL_TOKENIZER_CONFIG" == "$MODEL_TOKENIZER_CONFIG_SHA" && "$CHECKPOINT_MODEL_VOCAB" == "$MODEL_VOCAB_SHA" && "$CHECKPOINT_MODEL_MERGES" == "$MODEL_MERGES_SHA" ]] || fail_preflight "C4 base-model tokenizer snapshot metadata mismatch"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked C4 operator script SHA differs from report"

[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -r "$TARGET_HF_HOME" && -d "$FORMAL_DATA_ROOT" && -r "$FORMAL_DATA_ROOT" && -w "$FORMAL_DATA_ROOT" ]] || fail_preflight "target persistent roots are unavailable or lack required access"
[[ "$ARTIFACT_ROOT" != "$REPO_ROOT" && "$ARTIFACT_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "artifact_root must remain outside target checkout"
[[ "$FORMAL_DATA_ROOT" != "$REPO_ROOT" && "$FORMAL_DATA_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "formal_data_root must remain outside target checkout"
[[ "$TARGET_HF_HOME" != "$REPO_ROOT" && "$TARGET_HF_HOME" != "$REPO_ROOT/"* ]] || fail_preflight "hf_home must remain outside target checkout"
[[ -f "$READINESS_RECORD" ]] || fail_preflight "target readiness record is unavailable"
if ! "$PY" - "$READINESS_RECORD" <<'PY_READINESS'
import json
import sys
from pathlib import Path

def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value

def contains_ready(value: object) -> bool:
    if isinstance(value, str):
        return value == "READY_FOR_VALIDATION_PLANNER"
    if isinstance(value, dict):
        return any(contains_ready(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_ready(item) for item in value)
    return False

try:
    readiness = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
    raise SystemExit(f"readiness record is not strict JSON: {type(error).__name__}") from None
if not contains_ready(readiness):
    raise SystemExit("readiness record is not READY_FOR_VALIDATION_PLANNER")
PY_READINESS
then
  fail_preflight "target readiness record semantic validation failed"
fi
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
if current.get("gpu_count") != 1 or not isinstance(current.get("cuda_version"), str) or current.get("bf16_supported") is not True:
    raise SystemExit("target CUDA/BF16 environment identity is invalid")
print("\t".join([current["open_r1_commit"], current["dependency_lock_hash"], current["packages"]["torch"], current["cuda_version"]]))
PY_RUNTIME
)" || fail_preflight "target runtime identity validation failed"
IFS="$TAB" read -r CURRENT_OPEN_R1 CURRENT_LOCK_SHA CURRENT_TORCH CURRENT_CUDA <<<"$RUNTIME_FIELDS"

[[ "$(sha256sum "$REPO_ROOT/$CONFIG_REL" | awk '{print $1}')" == "$CALIBRATION_CONFIG_SHA" ]] || fail_preflight "tracked calibration config SHA changed"
if ! "$PY" - "$REPO_ROOT/$CONFIG_REL" >>"$LOG_FILE" <<'PY_CONFIG'
import sys
from pathlib import Path
from code_verifier.training.calibration import load_calibration_config
config = load_calibration_config(Path(sys.argv[1]))
if (
    config.initial_generations != 8
    or config.temperature != 0.8
    or config.top_p != 0.95
    or config.max_new_tokens != 512
    or config.max_prompt_tokens != 2048
    or config.active_pool_size != 3000
):
    raise SystemExit("tracked calibration config protocol mismatch")
print("calibration_config_protocol=k8 temperature=0.8 top_p=0.95 max_new_tokens=512 max_prompt_tokens=2048 active_pool=3000")
PY_CONFIG
then
  fail_preflight "tracked calibration config strict protocol validation failed"
fi
[[ -d "" ]] || fail_preflight "C4 calibration input is missing; sync it to  before running"
if ! "" - "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" >>"" <<'PY_INPUT'
import hashlib
import sys
from pathlib import Path
from code_verifier.training.calibration import _load_input_bundle
root = Path(sys.argv[1])
(expected_manifest, expected_records, expected_order, expected_excluded_context, expected_excluded_quality, expected_reserve, expected_wp9a, expected_wp9a_order, context_policy, candidate_policy, source_count, context_eligible_count, quality_eligible_count, quality_excluded_count, reserve_count, selected_count, excluded_context_count, max_prompt_tokens, max_new_tokens, tokenizer_model_id, tokenizer_model_revision) = sys.argv[2:]
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
manifest, records = _load_input_bundle(root)
for name, expected in {"input_manifest.json": expected_manifest, "inputs.jsonl": expected_records, "excluded_context.jsonl": expected_excluded_context, "excluded_quality.jsonl": expected_excluded_quality, "tranche_reserve.jsonl": expected_reserve}.items():
    if digest(root / name) != expected:
        raise SystemExit(f"C4 calibration input SHA mismatch: {name}")
if manifest.get("records_sha256") != expected_records or manifest.get("problem_order_sha256") != expected_order:
    raise SystemExit("C4 calibration input records/order identity mismatch")
if manifest.get("wp9a_manifest_sha256") != expected_wp9a or manifest.get("wp9a_selected_order_sha256") != expected_wp9a_order:
    raise SystemExit("C4 calibration WP9-a authority mismatch")
if manifest.get("seed") != 42 or manifest.get("evidence_class") != "formal_input":
    raise SystemExit("C4 calibration input formal identity mismatch")
expected_context = {"policy": context_policy, "tokenizer_model_id": tokenizer_model_id, "tokenizer_model_revision": tokenizer_model_revision, "max_prompt_tokens": int(max_prompt_tokens), "max_new_tokens": int(max_new_tokens), "source_record_count": int(source_count), "eligible_record_count": int(context_eligible_count), "excluded_record_count": int(excluded_context_count), "excluded_records_sha256": expected_excluded_context}
expected_candidate = {"policy": candidate_policy, "exclude_quality_gate_required": True, "maximum_records": int(selected_count), "context_eligible_record_count": int(context_eligible_count), "quality_eligible_record_count": int(quality_eligible_count), "quality_excluded_record_count": int(quality_excluded_count), "quality_excluded_records_sha256": expected_excluded_quality, "selected_record_count": int(selected_count), "tranche_reserve_record_count": int(reserve_count), "tranche_reserve_records_sha256": expected_reserve}
if manifest.get("context_filter") != expected_context or manifest.get("candidate_filter") != expected_candidate:
    raise SystemExit("C4 calibration context/candidate filter metadata mismatch")
if manifest.get("record_count") != int(selected_count) or len(records) != int(selected_count):
    raise SystemExit("C4 calibration selected count mismatch")
if any(item.quality_gate_required or item.overlap_origin != "external_new" for item in records):
    raise SystemExit("C4 calibration selected tranche is not quality-safe external-new only")
print(f"calibration_input_source={source_count} context_eligible={context_eligible_count} quality_eligible={quality_eligible_count} selected={len(records)} reserve={reserve_count} excluded_context={excluded_context_count} excluded_quality={quality_excluded_count}")
PY_INPUT
then
  fail_preflight "formal C4 calibration input strict validation failed"
fi

if ! B_FIELDS="$($PY - "$B_RUN" "$B_RUN_NAME" "$B_MODEL_ID" "$B_MODEL_REVISION" "$B_DATASET_HASH" "$B_CONFIG_HASH" "$DEPENDENCY_LOCK_SHA" "$B_ADAPTER_MODEL_SHA" "$B_ADAPTER_CONFIG_SHA" <<'PY_B'
import hashlib
import sys
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
run = load_completed_sft_checkpoint(Path(sys.argv[1]))
expected = sys.argv[2:8]
actual = [run.run_id, run.model_id, run.model_revision, run.dataset_hash, run.config_hash, run.dependency_lock_hash]
if actual != expected:
    raise SystemExit("formal B checkpoint identity mismatch")
if run.seed != 42:
    raise SystemExit("formal B seed mismatch")
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
if digest(run.checkpoint_dir / "adapter_model.safetensors") != sys.argv[8]:
    raise SystemExit("formal B adapter model SHA256 mismatch")
if digest(run.checkpoint_dir / "adapter_config.json") != sys.argv[9]:
    raise SystemExit("formal B adapter config SHA256 mismatch")
print("\t".join(actual))
PY_B
)"; then
  fail_preflight "formal B strict identity/byte validation failed"
fi
printf '[%s] formal B identity=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$B_FIELDS" >>"$LOG_FILE"

if ! "$PY" - "$B_MODEL_ID" "$B_MODEL_REVISION" \
  "$MODEL_WEIGHTS_SHA" "$MODEL_CONFIG_SHA" "$MODEL_GENERATION_CONFIG_SHA" "$MODEL_TOKENIZER_SHA" \
  "$MODEL_TOKENIZER_CONFIG_SHA" "$MODEL_VOCAB_SHA" "$MODEL_MERGES_SHA" >>"$LOG_FILE" <<'PY_MODEL'
import hashlib
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

snapshot = Path(snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_files_only=True)).resolve()
expected = {
    "model.safetensors": sys.argv[3],
    "config.json": sys.argv[4],
    "generation_config.json": sys.argv[5],
    "tokenizer.json": sys.argv[6],
    "tokenizer_config.json": sys.argv[7],
    "vocab.json": sys.argv[8],
    "merges.txt": sys.argv[9],
}
if not snapshot.is_dir():
    raise SystemExit("exact model snapshot is not available local-only")
observed: dict[str, str] = {}
for name, expected_sha in expected.items():
    path = snapshot / name
    if not path.is_file():
        raise SystemExit(f"exact model snapshot file is missing: {name}")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    observed[name] = h.hexdigest()
    if observed[name] != expected_sha:
        raise SystemExit(f"cached base-model snapshot SHA256 mismatch: {name}")
print("model_snapshot=" + str(snapshot))
for name in sorted(observed):
    print(f"model_snapshot_sha256[{name}]={observed[name]}")
PY_MODEL
then
  fail_preflight "exact formal B base-model revision/snapshot bytes are unavailable local-only"
fi

if ! "$PY" - "$INPUT_DIR" "$B_MODEL_ID" "$B_MODEL_REVISION" "$MAX_PROMPT_TOKENS" >>"$LOG_FILE" <<'PY_CONTEXT_RECHECK'
import sys
from pathlib import Path
from transformers import AutoTokenizer
from code_verifier.training.calibration import _load_input_bundle
root = Path(sys.argv[1])
model_id, revision = sys.argv[2:4]
cap = int(sys.argv[4])
manifest, records = _load_input_bundle(root)
context = manifest.get("context_filter")
if not isinstance(context, dict) or context.get("tokenizer_model_id") != model_id or context.get("tokenizer_model_revision") != revision:
    raise SystemExit("filtered calibration tokenizer identity mismatch before context recheck")
tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, local_files_only=True)
max_observed = 0
for index, item in enumerate(records, start=1):
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": item.prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )
    encoded = tokenizer(rendered, add_special_tokens=False)
    count = len(encoded["input_ids"])
    if count <= 0 or count > cap:
        raise SystemExit(f"survivor prompt token cap violation at record {index}: {item.problem_id} tokens={count}")
    max_observed = max(max_observed, count)
print(f"context_recheck_records={len(records)} max_observed_prompt_tokens={max_observed} cap={cap}")
PY_CONTEXT_RECHECK
then
  fail_preflight "exact tokenizer/chat-template survivor context revalidation failed"
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

OUTPUT_ACTION="$($PY - "$OUTPUT_DIR" "$QUARANTINE_ROOT" "$INPUT_DIR" "$ATTEMPT_ID" "$B_RUN" "$PROBLEM_BATCH_SIZE" "$C3_EVIDENCE_FILE" <<'PY_PREP'
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from code_verifier.training.calibration import (
    CALIBRATION_SCHEMA_VERSION,
    _load_input_bundle,
    _load_json,
    _load_running_calibration_generation_prefix,
    _sft_identity,
    calibration_problem_seed,
    load_completed_calibration_generation,
)
from code_verifier.training.sft import load_completed_sft_checkpoint
output = Path(sys.argv[1])
quarantine = Path(sys.argv[2])
input_dir = Path(sys.argv[3])
attempt = sys.argv[4]
b_run = Path(sys.argv[5])
problem_batch_size = int(sys.argv[6])
c3_evidence = Path(sys.argv[7])
def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
if not output.exists():
    print("fresh")
    raise SystemExit(0)
try:
    input_manifest, inputs = _load_input_bundle(input_dir)
    b = load_completed_sft_checkpoint(b_run)
    expected_identity = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "status": "running",
        "block_index": 0,
        "samples_per_problem": 8,
        "problem_batch_size": problem_batch_size,
        "input_manifest_sha256": __import__("hashlib").sha256((input_dir / "input_manifest.json").read_bytes()).hexdigest(),
        "input_records_sha256": input_manifest["records_sha256"],
        "problem_order_sha256": input_manifest["problem_order_sha256"],
        "retry_manifest_sha256": None,
        "sft_checkpoint": _sft_identity(b),
    }
    value = _load_json(output / "run.json")
    status = value.get("status")
    if status not in {"running", "completed"}:
        raise ValueError("invalid generation status")
    comparable = dict(value)
    comparable.pop("status", None)
    comparable.pop("record_count", None)
    comparable.pop("records_sha256", None)
    expected = dict(expected_identity)
    expected.pop("status")
    if comparable != expected:
        raise ValueError("generation identity mismatch")
    if status == "completed":
        _, records = load_completed_calibration_generation(output)
        if len(records) != len(inputs) * 8:
            raise ValueError("completed generation count mismatch")
        print(f"reuse_completed:{len(records)}")
        raise SystemExit(0)
    records, _ = _load_running_calibration_generation_prefix(output)
    if len(records) > len(inputs) * 8 or len(records) % 8:
        raise ValueError("running generation is not a complete k8 prefix")
    expected_fields = {
        "problem_id", "block_index", "sample_index", "sample_seed", "completion",
        "completion_tokens", "generation_latency_ms", "hit_max_new_tokens",
    }
    base_seed = input_manifest.get("seed")
    if isinstance(base_seed, bool) or not isinstance(base_seed, int):
        raise ValueError("input seed is invalid")
    for index, row in enumerate(records):
        item = inputs[index // 8]
        sample_index = index % 8
        if set(row) != expected_fields:
            raise ValueError("running generation fields are invalid")
        if row.get("problem_id") != item.problem_id or row.get("block_index") != 0 or row.get("sample_index") != sample_index:
            raise ValueError("running generation is not the exact ordered prefix")
        if row.get("sample_seed") != calibration_problem_seed(base_seed, item.problem_id, 0):
            raise ValueError("running generation sample seed mismatch")
        completion = row.get("completion")
        tokens = row.get("completion_tokens")
        latency = row.get("generation_latency_ms")
        hit_max = row.get("hit_max_new_tokens")
        if not isinstance(completion, str):
            raise ValueError("running generation completion type mismatch")
        if isinstance(tokens, bool) or not isinstance(tokens, int) or not 0 <= tokens <= 512:
            raise ValueError("running generation token telemetry invalid")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or float(latency) < 0:
            raise ValueError("running generation latency telemetry invalid")
        if not isinstance(hit_max, bool) or hit_max != (tokens >= 512):
            raise ValueError("running generation truncation telemetry invalid")
    print(f"resume_running:{len(records)}")
except SystemExit:
    raise
except Exception as error:
    quarantine.mkdir(parents=True, exist_ok=True)
    destination = quarantine / f"before-C4-{attempt}"
    if destination.exists():
        raise SystemExit("quarantine destination already exists")
    old_run = None
    old_progress = None
    try:
        old_run = _load_json(output / "run.json")
    except Exception:
        pass
    try:
        old_progress = _load_json(output / "samples" / "progress.json")
    except Exception:
        pass
    inventory = {
        "run_json_sha256": digest(output / "run.json"),
        "generation_records_sha256": digest(output / "samples" / "generations.jsonl"),
        "generation_progress_sha256": digest(output / "samples" / "progress.json"),
        "generation_records_size_bytes": (output / "samples" / "generations.jsonl").stat().st_size if (output / "samples" / "generations.jsonl").is_file() else None,
        "c3_operator_evidence_path": str(c3_evidence),
        "c3_operator_evidence_sha256": digest(c3_evidence),
    }
    recognized_c3 = bool(
        isinstance(old_run, dict)
        and old_run.get("input_manifest_sha256") == "0ac247e0eae6244148a117a350284dd7088c6822a2eab68382eb22cfd1a2b6c6"
        and old_run.get("input_records_sha256") == "22675dcbe31c663079c244175f6557d4b65b2206d96ef644c66677b97dd40140"
        and old_run.get("problem_order_sha256") == "4de0fa55f04ee02bdd5c4668f97cca9eeb254273c25c354df3c66bc89be9b197"
        and old_run.get("problem_batch_size") == 1
    )
    os.replace(output, destination)
    manifest = quarantine / f"before-C4-{attempt}.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "stage_id": "WP9-c",
        "gate_id": "wp9c-calibration-initial-generation",
        "checkpoint_id": "C4",
        "supersedes_checkpoint": "C3",
        "quarantined_path": str(destination),
        "reason": f"incompatible_or_malformed_existing_output:{type(error).__name__}",
        "recognized_superseded_c3_identity": recognized_c3,
        "observed_run_identity": old_run,
        "observed_progress": old_progress,
        "inventory": inventory,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"quarantined:{destination}:{manifest}")
PY_PREP
)" || fail_preflight "existing calibration generation preparation failed"
printf '[%s] generation action=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$OUTPUT_ACTION" >>"$LOG_FILE"

CURRENT_PHASE="generation"
if [[ "$OUTPUT_ACTION" == reuse_completed:* ]]; then
  COMMAND_RC=0
  printf '[%s] strict completed generation already present; skipping model generation\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
else
  if "$CV" generate-refresh-calibration \
    --config "$REPO_ROOT/$CONFIG_REL" \
    --input-bundle-dir "$INPUT_DIR" \
    --sft-run-dir "$B_RUN" \
    --block initial \
    --problem-batch-size "$PROBLEM_BATCH_SIZE" \
    --output-dir "$OUTPUT_DIR" >>"$LOG_FILE" 2>&1; then
    COMMAND_RC=0
  else
    COMMAND_RC=$?
  fi
  if (( COMMAND_RC != 0 )); then
    finalize_gate "$COMMAND_RC" 125 command_failed "generate-refresh-calibration exited nonzero"
    exit $?
  fi
fi

CURRENT_PHASE="postcheck"
if "$PY" - "$POSTCHECK_FILE.tmp" "$INPUT_DIR" "$B_RUN" "$OUTPUT_DIR" "$HEAD_COMMIT" "$PROBLEM_BATCH_SIZE" "$ELIGIBLE_RECORD_COUNT" "$EXPECTED_RECORD_COUNT" "$EXCLUDED_CONTEXT_SHA" "$QUALITY_EXCLUDED_SHA" "$TRANCHE_RESERVE_SHA" "$CONTEXT_ELIGIBLE_RECORD_COUNT" "$QUALITY_ELIGIBLE_RECORD_COUNT" "$QUALITY_EXCLUDED_RECORD_COUNT" "$TRANCHE_RESERVE_RECORD_COUNT" <<'PY_POSTCHECK'
import hashlib
import json
import math
import sys
from pathlib import Path
from code_verifier.training.calibration import (
    _load_input_bundle,
    calibration_problem_seed,
    load_completed_calibration_generation,
)
from code_verifier.training.sft import load_completed_sft_checkpoint
output, input_dir, b_run, generation_dir = map(Path, sys.argv[1:5])
checkpoint_commit = sys.argv[5]
problem_batch_size = int(sys.argv[6])
expected_problem_count = int(sys.argv[7])
expected_record_count = int(sys.argv[8])
expected_excluded_sha = sys.argv[9]
expected_quality_excluded_sha = sys.argv[10]
expected_reserve_sha = sys.argv[11]
context_eligible_count = int(sys.argv[12])
quality_eligible_count = int(sys.argv[13])
quality_excluded_count = int(sys.argv[14])
reserve_count = int(sys.argv[15])
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
input_manifest, inputs = _load_input_bundle(input_dir)
run, records = load_completed_calibration_generation(generation_dir)
b = load_completed_sft_checkpoint(b_run)
if len(inputs) != expected_problem_count or len(records) != expected_record_count or run.get("record_count") != expected_record_count or run.get("block_index") != 0:
    raise SystemExit("C4 Gate A generation count/block mismatch")
if expected_record_count != expected_problem_count * 8:
    raise SystemExit("C4 Gate A expected count arithmetic mismatch")
context = input_manifest.get("context_filter")
if not isinstance(context, dict) or context != {
    "policy": "chat_template_prompt_cap_v1",
    "tokenizer_model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "tokenizer_model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "max_prompt_tokens": 2048,
    "max_new_tokens": 512,
    "source_record_count": 10000,
    "eligible_record_count": context_eligible_count,
    "excluded_record_count": 379,
    "excluded_records_sha256": expected_excluded_sha,
}:
    raise SystemExit("C4 Gate A context-filter binding mismatch")
candidate = input_manifest.get("candidate_filter")
if not isinstance(candidate, dict):
    raise SystemExit("C4 Gate A candidate-filter metadata is missing")
if (
    candidate.get("policy") != "quality_safe_stratified_tranche_v1"
    or candidate.get("exclude_quality_gate_required") is not True
    or candidate.get("maximum_records") != expected_problem_count
    or candidate.get("context_eligible_record_count") != context_eligible_count
    or candidate.get("quality_eligible_record_count") != quality_eligible_count
    or candidate.get("quality_excluded_record_count") != quality_excluded_count
    or candidate.get("quality_excluded_records_sha256") != expected_quality_excluded_sha
    or candidate.get("selected_record_count") != expected_problem_count
    or candidate.get("tranche_reserve_record_count") != reserve_count
    or candidate.get("tranche_reserve_records_sha256") != expected_reserve_sha
):
    raise SystemExit("C4 Gate A candidate-filter binding mismatch")
for name, expected_sha in (
    ("excluded_context.jsonl", expected_excluded_sha),
    ("excluded_quality.jsonl", expected_quality_excluded_sha),
    ("tranche_reserve.jsonl", expected_reserve_sha),
):
    if digest(input_dir / name) != expected_sha:
        raise SystemExit(f"C4 Gate A input sidecar bytes mismatch: {name}")
if any(item.quality_gate_required or item.overlap_origin != "external_new" for item in inputs):
    raise SystemExit("C4 Gate A selected tranche is not quality-safe external-new only")
if run.get("input_manifest_sha256") != digest(input_dir / "input_manifest.json") or run.get("input_records_sha256") != input_manifest.get("records_sha256"):
    raise SystemExit("Gate A generation input binding mismatch")
if (
    run.get("samples_per_problem") != 8
    or run.get("problem_batch_size") != problem_batch_size
    or run.get("retry_manifest_sha256") is not None
    or run.get("problem_order_sha256") != input_manifest.get("problem_order_sha256")
):
    raise SystemExit("Gate A generation protocol/order/batch binding mismatch")
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
expected_fields = {
    "problem_id", "block_index", "sample_index", "sample_seed", "completion",
    "completion_tokens", "generation_latency_ms", "hit_max_new_tokens",
}
expected_ids = [item.problem_id for item in inputs]
base_seed = input_manifest.get("seed")
if isinstance(base_seed, bool) or not isinstance(base_seed, int):
    raise SystemExit("Gate A input seed is invalid")
for index, row in enumerate(records):
    item = inputs[index // 8]
    sample_index = index % 8
    if set(row) != expected_fields:
        raise SystemExit("Gate A generation record fields mismatch")
    if row.get("problem_id") != item.problem_id or row.get("block_index") != 0 or row.get("sample_index") != sample_index:
        raise SystemExit("Gate A generation is not the exact ordered k8 stream")
    if row.get("sample_seed") != calibration_problem_seed(base_seed, item.problem_id, 0):
        raise SystemExit("Gate A sample seed mismatch")
    tokens = row.get("completion_tokens")
    latency = row.get("generation_latency_ms")
    hit_max = row.get("hit_max_new_tokens")
    completion = row.get("completion")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or not 0 <= tokens <= 512:
        raise SystemExit("Gate A completion token telemetry invalid")
    if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or float(latency) < 0:
        raise SystemExit("Gate A generation latency telemetry invalid")
    if not isinstance(hit_max, bool) or hit_max != (tokens >= 512) or not isinstance(completion, str):
        raise SystemExit("Gate A completion fields/truncation telemetry invalid")
progress_path = generation_dir / "samples" / "progress.json"
progress = json.loads(progress_path.read_text(encoding="utf-8"))
if progress != {"version": 1, "record_count": expected_record_count, "byte_count": (generation_dir / "samples" / "generations.jsonl").stat().st_size}:
    raise SystemExit("Gate A committed progress marker mismatch")
payload = {
    "version": 1,
    "status": "passed",
    "stage_id": "WP9-c",
    "checkpoint_id": "C4",
    "operator_gate_id": "wp9c-calibration-initial-generation",
    "operator_checkpoint_commit": checkpoint_commit,
    "problem_count": len(expected_ids),
    "record_count": len(records),
    "samples_per_problem": 8,
    "problem_batch_size": problem_batch_size,
    "context_filter": context,
    "candidate_filter": candidate,
    "input_manifest_sha256": digest(input_dir / "input_manifest.json"),
    "input_records_sha256": input_manifest["records_sha256"],
    "excluded_context_sha256": expected_excluded_sha,
    "excluded_quality_sha256": expected_quality_excluded_sha,
    "tranche_reserve_sha256": expected_reserve_sha,
    "problem_order_sha256": input_manifest["problem_order_sha256"],
    "generation_run_sha256": digest(generation_dir / "run.json"),
    "generation_records_sha256": digest(generation_dir / "samples" / "generations.jsonl"),
    "generation_progress_sha256": digest(progress_path),
    "formal_b": expected_b,
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_POSTCHECK
then
  POSTCHECK_RC=0
else
  POSTCHECK_RC=$?
fi
if (( POSTCHECK_RC != 0 )); then
  rm -f "$POSTCHECK_FILE.tmp"
  finalize_gate 0 "$POSTCHECK_RC" postcheck_failed "strict C4 Gate A postcheck failed"
  exit $?
fi
mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"

CURRENT_PHASE="complete"
finalize_gate 0 0 passed "WP9-c Gate A initial 5,000 x 8 quality-safe context-filtered frozen-B calibration tranche completed and strict postcheck passed"
exit $?
