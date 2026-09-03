#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-c"
GATE_ID="wp9c-calibration-initial-generation"
CHECKPOINT_ID="C5"
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
SCRIPT_REL="ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C5/run.sh"
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
C2_EVIDENCE_FILE="$GATE_ROOT/C2/operator-evidence.json"
C2_EVIDENCE_SHA="9eb342bc24896ffd95f5d9a635ead3745c0f41e8bcc794c9469545ebb03de13c"
C3_EVIDENCE_FILE="$GATE_ROOT/C3/operator-evidence.json"
C3_EVIDENCE_SHA="950d605a5e46af424d11e7d94fa5a6511c61f2c711df592c68a289f298b0eb2e"

mkdir -p "$OP_ROOT" "$GATE_ROOT/C0" "$GATE_ROOT/C1" "$GATE_ROOT/C2" "$GATE_ROOT/C3"
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
[[ -f "$C2_EVIDENCE_FILE" ]] || { echo "superseded C2 operator evidence is missing: $C2_EVIDENCE_FILE" >&2; exit 125; }
C2_EVIDENCE_ACTUAL_SHA="$(sha256sum "$C2_EVIDENCE_FILE" | awk '{print $1}')"
[[ "$C2_EVIDENCE_ACTUAL_SHA" == "$C2_EVIDENCE_SHA" ]] || { echo "superseded C2 operator evidence SHA mismatch" >&2; exit 125; }
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
  [[ "$CURRENT_PHASE" == "preflight" || "$OUTPUT_ACTION" == reuse_completed* ]] || generation_started=true
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
    inventory(run_root / "samples" / "problem_origins.jsonl"),
    inventory(run_root / "reuse_manifest.json"),
    inventory(Path(artifact_root) / "wp9c" / "calibration" / "C5-new-generation" / "run.json"),
    inventory(Path(artifact_root) / "wp9c" / "calibration" / "C5-new-generation" / "samples" / "generations.jsonl"),
    inventory(Path(artifact_root) / "wp9c" / "calibration" / "C5-new-generation" / "samples" / "progress.json"),
    inventory(Path(artifact_root) / "wp9c" / "quarantine" / "calibration" / "initial" / "C3-reuse-source-for-C5" / "run.json"),
    inventory(Path(formal_data_root) / "wp9c" / "calibration-input-C5-missing-4781" / "input_manifest.json"),
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
    "checkpoint_id": "C5",
    "supersedes_checkpoint": "C4",
    "operator_gate_id": "wp9c-calibration-initial-generation",
    "operator_script": "ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C5/run.sh",
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
    "problem_batch_size_semantics": "applies only to the 4781 newly generated problems; C2/C3 reused groups retain source provenance",
    "expected_problem_count": 5000,
    "expected_record_count": 40000,
    "reuse_protocol": {
        "policy": "ordered_complete_problem_precedence_v1",
        "selection_timing": "problem_id_only_before_verifier_scoring",
        "C2_reused_problem_count": 8,
        "C3_reused_problem_count": 211,
        "generated_problem_count": 4781,
        "generated_record_count": 38248,
        "problem_origins_sha256": "74d882df1f29a6957ba9d43887531e8596b091f0f735629ea8da624737171b0f",
    },
    "superseded_c2_operator_evidence": inventory(Path(artifact_root) / "operator" / "WP9-c" / "5a1f083af6bfdf2e1333bd70e95e9257b4e66b48" / "wp9c-calibration-initial-generation" / "C2" / "operator-evidence.json"),
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
[[ "$EXPECTED_HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail_preflight "set WP9C_HANDOFF_COMMIT to the exact 40-hex C5 handoff commit before running"
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
        raise SystemExit(f"C5 handoff path is not tracked at target HEAD: {relative}")
mode_line = subprocess.run(
    ["git", "-C", str(repo), "ls-tree", head, "--", script],
    check=True, capture_output=True, text=True,
).stdout.strip()
if not mode_line.startswith("100755 "):
    raise SystemExit("tracked C5 operator script is not executable")
PY_SCOPE
then
  fail_preflight "C5 tracked handoff validation failed"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" <<'PY_META'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind("checkpoint_id: C5")
if pos < 0:
    raise SystemExit("C5 checkpoint block is missing")
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit("C5 checkpoint block is malformed")
block = text[start:end]
def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"C5 checkpoint field missing: {name}")
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
)" || fail_preflight "cannot parse C5 checkpoint metadata"
IFS="$TAB" read -r CHECKPOINT_STAGE CHECKPOINT_TASK CHECKPOINT_PLAN CHECKPOINT_REVIEW_ROUND CHECKPOINT_REVIEW_COMMIT CHECKPOINT_REPAIR_IDS CHECKPOINT_RESULT CHECKPOINT_GATE CHECKPOINT_MODE CHECKPOINT_RESTART CHECKPOINT_SUPERSEDES EXPECTED_SCRIPT_SHA CHECKPOINT_INPUT_MANIFEST CHECKPOINT_INPUT_RECORDS CHECKPOINT_INPUT_ORDER CHECKPOINT_EXCLUDED_SHA CHECKPOINT_WP9A CHECKPOINT_WP9A_ORDER CHECKPOINT_CONFIG_SHA CHECKPOINT_BATCH_SIZE CHECKPOINT_FILTER_POLICY CHECKPOINT_SOURCE_COUNT CHECKPOINT_ELIGIBLE_COUNT CHECKPOINT_EXCLUDED_COUNT CHECKPOINT_MAX_PROMPT CHECKPOINT_MAX_NEW CHECKPOINT_PROBLEM_COUNT CHECKPOINT_RECORD_COUNT CHECKPOINT_MODEL_WEIGHTS CHECKPOINT_MODEL_CONFIG CHECKPOINT_MODEL_GENERATION_CONFIG CHECKPOINT_MODEL_TOKENIZER CHECKPOINT_MODEL_TOKENIZER_CONFIG CHECKPOINT_MODEL_VOCAB CHECKPOINT_MODEL_MERGES CHECKPOINT_STATUS <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_STAGE" == "$STAGE_ID" && "$CHECKPOINT_TASK" == "repair" && "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" ]] || fail_preflight "C5 repair source provenance mismatch"
[[ "$CHECKPOINT_REVIEW_ROUND" == "null" && "$CHECKPOINT_REVIEW_COMMIT" == "null" && "$CHECKPOINT_REPAIR_IDS" == "[]" ]] || fail_preflight "C5 user-directed repair must not fabricate review provenance"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" && "$CHECKPOINT_GATE" == "$GATE_ID" && "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_RESTART" == "exact_missing_prefix_or_strict_completed_composite_reuse" && "$CHECKPOINT_SUPERSEDES" == "C4" ]] || fail_preflight "C5 gate/handoff/restart provenance mismatch"
[[ "$CHECKPOINT_INPUT_MANIFEST" == "$INPUT_MANIFEST_SHA" && "$CHECKPOINT_INPUT_RECORDS" == "$INPUT_RECORDS_SHA" && "$CHECKPOINT_INPUT_ORDER" == "$INPUT_ORDER_SHA" && "$CHECKPOINT_EXCLUDED_SHA" == "$EXCLUDED_CONTEXT_SHA" ]] || fail_preflight "C5 filtered input bundle identity mismatch"
[[ "$CHECKPOINT_WP9A" == "$WP9A_MANIFEST_SHA" && "$CHECKPOINT_WP9A_ORDER" == "$WP9A_SELECTED_ORDER_SHA" ]] || fail_preflight "C5 WP9-a authority mismatch"
[[ "$CHECKPOINT_CONFIG_SHA" == "$CALIBRATION_CONFIG_SHA" && "$CHECKPOINT_BATCH_SIZE" == "$PROBLEM_BATCH_SIZE" && "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "C5 config/batch/status metadata mismatch"
[[ "$CHECKPOINT_FILTER_POLICY" == "$CONTEXT_FILTER_POLICY" && "$CHECKPOINT_SOURCE_COUNT" == "$SOURCE_RECORD_COUNT" && "$CHECKPOINT_ELIGIBLE_COUNT" == "$ELIGIBLE_RECORD_COUNT" && "$CHECKPOINT_EXCLUDED_COUNT" == "$EXCLUDED_RECORD_COUNT" ]] || fail_preflight "C5 context-filter policy/count metadata mismatch"
[[ "$CHECKPOINT_MAX_PROMPT" == "$MAX_PROMPT_TOKENS" && "$CHECKPOINT_MAX_NEW" == "$MAX_NEW_TOKENS" && "$CHECKPOINT_PROBLEM_COUNT" == "$ELIGIBLE_RECORD_COUNT" && "$CHECKPOINT_RECORD_COUNT" == "$EXPECTED_RECORD_COUNT" ]] || fail_preflight "C5 context/output count metadata mismatch"
[[ "$CHECKPOINT_MODEL_WEIGHTS" == "$MODEL_WEIGHTS_SHA" && "$CHECKPOINT_MODEL_CONFIG" == "$MODEL_CONFIG_SHA" && "$CHECKPOINT_MODEL_GENERATION_CONFIG" == "$MODEL_GENERATION_CONFIG_SHA" ]] || fail_preflight "C5 base-model core snapshot metadata mismatch"
[[ "$CHECKPOINT_MODEL_TOKENIZER" == "$MODEL_TOKENIZER_SHA" && "$CHECKPOINT_MODEL_TOKENIZER_CONFIG" == "$MODEL_TOKENIZER_CONFIG_SHA" && "$CHECKPOINT_MODEL_VOCAB" == "$MODEL_VOCAB_SHA" && "$CHECKPOINT_MODEL_MERGES" == "$MODEL_MERGES_SHA" ]] || fail_preflight "C5 base-model tokenizer snapshot metadata mismatch"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked C5 operator script SHA differs from report"

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
[[ -d "$INPUT_DIR" ]] || fail_preflight "C5 calibration input is missing; sync it to $INPUT_DIR before running"
if ! "$PY" - "$INPUT_DIR" "$INPUT_MANIFEST_SHA" "$INPUT_RECORDS_SHA" "$INPUT_ORDER_SHA" "$EXCLUDED_CONTEXT_SHA" "$QUALITY_EXCLUDED_SHA" "$TRANCHE_RESERVE_SHA" "$WP9A_MANIFEST_SHA" "$WP9A_SELECTED_ORDER_SHA" "$CONTEXT_FILTER_POLICY" "$CANDIDATE_FILTER_POLICY" "$SOURCE_RECORD_COUNT" "$CONTEXT_ELIGIBLE_RECORD_COUNT" "$QUALITY_ELIGIBLE_RECORD_COUNT" "$QUALITY_EXCLUDED_RECORD_COUNT" "$TRANCHE_RESERVE_RECORD_COUNT" "$ELIGIBLE_RECORD_COUNT" "$EXCLUDED_RECORD_COUNT" "$MAX_PROMPT_TOKENS" "$MAX_NEW_TOKENS" "$B_MODEL_ID" "$B_MODEL_REVISION" >>"$LOG_FILE" <<'PY_INPUT'
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
        raise SystemExit(f"C5 calibration input SHA mismatch: {name}")
if manifest.get("records_sha256") != expected_records or manifest.get("problem_order_sha256") != expected_order:
    raise SystemExit("C5 calibration input records/order identity mismatch")
if manifest.get("wp9a_manifest_sha256") != expected_wp9a or manifest.get("wp9a_selected_order_sha256") != expected_wp9a_order:
    raise SystemExit("C5 calibration WP9-a authority mismatch")
if manifest.get("seed") != 42 or manifest.get("evidence_class") != "formal_input":
    raise SystemExit("C5 calibration input formal identity mismatch")
expected_context = {"policy": context_policy, "tokenizer_model_id": tokenizer_model_id, "tokenizer_model_revision": tokenizer_model_revision, "max_prompt_tokens": int(max_prompt_tokens), "max_new_tokens": int(max_new_tokens), "source_record_count": int(source_count), "eligible_record_count": int(context_eligible_count), "excluded_record_count": int(excluded_context_count), "excluded_records_sha256": expected_excluded_context}
expected_candidate = {"policy": candidate_policy, "exclude_quality_gate_required": True, "maximum_records": int(selected_count), "context_eligible_record_count": int(context_eligible_count), "quality_eligible_record_count": int(quality_eligible_count), "quality_excluded_record_count": int(quality_excluded_count), "quality_excluded_records_sha256": expected_excluded_quality, "selected_record_count": int(selected_count), "tranche_reserve_record_count": int(reserve_count), "tranche_reserve_records_sha256": expected_reserve}
if manifest.get("context_filter") != expected_context or manifest.get("candidate_filter") != expected_candidate:
    raise SystemExit("C5 calibration context/candidate filter metadata mismatch")
if manifest.get("record_count") != int(selected_count) or len(records) != int(selected_count):
    raise SystemExit("C5 calibration selected count mismatch")
if any(item.quality_gate_required or item.overlap_origin != "external_new" for item in records):
    raise SystemExit("C5 calibration selected tranche is not quality-safe external-new only")
print(f"calibration_input_source={source_count} context_eligible={context_eligible_count} quality_eligible={quality_eligible_count} selected={len(records)} reserve={reserve_count} excluded_context={excluded_context_count} excluded_quality={quality_excluded_count}")
PY_INPUT
then
  fail_preflight "formal C5 calibration input strict validation failed"
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

C2_INPUT_DIR="$FORMAL_DATA_ROOT/wp9c/calibration-input"
C3_INPUT_DIR="$FORMAL_DATA_ROOT/wp9c/calibration-input-context2048"
C2_SOURCE_DIR="$QUARANTINE_ROOT/before-C3-20260903T090220Z-24952"
C3_SOURCE_DIR="$QUARANTINE_ROOT/C3-reuse-source-for-C5"
MISSING_INPUT_DIR="$FORMAL_DATA_ROOT/wp9c/calibration-input-C5-missing-4781"
NEW_RUN_DIR="$ARTIFACT_ROOT/wp9c/calibration/C5-new-generation"
REUSE_ORIGIN_SHA="74d882df1f29a6957ba9d43887531e8596b091f0f735629ea8da624737171b0f"
REUSED_PROBLEM_COUNT="219"
C2_REUSED_PROBLEM_COUNT="8"
C3_REUSED_PROBLEM_COUNT="211"
GENERATED_PROBLEM_COUNT="4781"
GENERATED_RECORD_COUNT="38248"

OUTPUT_ACTION="$($PY - "$INPUT_DIR" "$C2_INPUT_DIR" "$C3_INPUT_DIR" "$C2_SOURCE_DIR" "$C3_SOURCE_DIR" "$OUTPUT_DIR" "$MISSING_INPUT_DIR" "$NEW_RUN_DIR" "$B_RUN" "$REUSE_ORIGIN_SHA" <<'PY_PREP'
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.training.calibration import (
    CALIBRATION_SCHEMA_VERSION,
    _json_bytes,
    _load_input_bundle,
    _load_json,
    _load_jsonl,
    _sft_identity,
    _write_json,
    _write_jsonl,
    calibration_problem_seed,
    load_completed_calibration_generation,
)
from code_verifier.training.sft import load_completed_sft_checkpoint

(
    input_dir, c2_input_dir, c3_input_dir, c2_source, c3_source, output_dir,
    missing_input_dir, new_run_dir, b_run,
) = map(Path, sys.argv[1:10])
expected_origin_sha = sys.argv[10]

EXPECTED = {
    "c2_input_manifest": "3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3",
    "c2_input_records": "86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682",
    "c2_input_order": "355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001",
    "c2_run": "823a8d6a738ddf3e905d43c2d390da3f9b449b07404f2d76cf60bb7b5db07b0f",
    "c2_records": "b218d3437ceb495c31a89cbaf36a5ee30224bb2ef00e55d0def6e8d9edb8cfad",
    "c2_progress": "a81f8e46efe27cde3fd00aea48bdb325cae45051b4620a0e8899c2aa19c98e5b",
    "c3_input_manifest": "0ac247e0eae6244148a117a350284dd7088c6822a2eab68382eb22cfd1a2b6c6",
    "c3_input_records": "22675dcbe31c663079c244175f6557d4b65b2206d96ef644c66677b97dd40140",
    "c3_input_order": "4de0fa55f04ee02bdd5c4668f97cca9eeb254273c25c354df3c66bc89be9b197",
    "c3_run": "25568d1d83286e79ee92749163a0415b949b9e2208749c398f73488a34fcc48c",
    "c3_records": "42fbe9e19da60723541bb4388e035b91aaeb597c775ec7fd4187542a0c1617a4",
    "c3_progress": "9ab25cce8f1552647de273db825d57bb5f23cfca31808b73db02e247ef30afb8",
}

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_committed(run_dir: Path, expected_run: str, expected_records: str, expected_progress: str, expected_count: int):
    for path, sha in (
        (run_dir / "run.json", expected_run),
        (run_dir / "samples/generations.jsonl", expected_records),
        (run_dir / "samples/progress.json", expected_progress),
    ):
        if not path.is_file() or digest(path) != sha:
            raise SystemExit(f"historical reuse source byte identity mismatch: {path}")
    run = _load_json(run_dir / "run.json")
    progress = _load_json(run_dir / "samples/progress.json")
    rows = _load_jsonl(run_dir / "samples/generations.jsonl")
    if run.get("status") != "running" or progress.get("record_count") != expected_count * 8 or len(rows) != expected_count * 8:
        raise SystemExit("historical reuse source committed prefix count/status mismatch")
    if progress.get("byte_count") != (run_dir / "samples/generations.jsonl").stat().st_size:
        raise SystemExit("historical reuse source progress byte marker mismatch")
    return run, rows

def validate_groups(rows, inputs, expected_batch):
    if len(rows) % 8:
        raise SystemExit("historical reuse source ends inside a problem group")
    input_by_id = {item.problem_id: item for item in inputs}
    run_ids = []
    for group_index in range(len(rows) // 8):
        group = rows[group_index * 8:(group_index + 1) * 8]
        pid = group[0].get("problem_id")
        if not isinstance(pid, str) or pid not in input_by_id:
            raise SystemExit("historical reuse source contains unknown problem")
        item = input_by_id[pid]
        seed = calibration_problem_seed(42, pid, 0)
        for offset, row in enumerate(group):
            if row.get("problem_id") != pid or row.get("block_index") != 0 or row.get("sample_index") != offset or row.get("sample_seed") != seed:
                raise SystemExit("historical reuse source group identity/seed mismatch")
            tokens = row.get("completion_tokens")
            latency = row.get("generation_latency_ms")
            hit = row.get("hit_max_new_tokens")
            if not isinstance(row.get("completion"), str) or isinstance(tokens, bool) or not isinstance(tokens, int) or not 0 <= tokens <= 512:
                raise SystemExit("historical reuse source completion/token telemetry invalid")
            if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or float(latency) < 0:
                raise SystemExit("historical reuse source latency telemetry invalid")
            if not isinstance(hit, bool) or hit != (tokens >= 512):
                raise SystemExit("historical reuse source truncation telemetry invalid")
        run_ids.append(pid)
    if len(run_ids) != len(set(run_ids)):
        raise SystemExit("historical reuse source contains duplicate groups")
    if run_ids != [item.problem_id for item in inputs[:len(run_ids)]]:
        raise SystemExit("historical reuse source is not the exact committed input prefix")
    return run_ids

for root, manifest_sha, records_sha, order_sha, count in (
    (c2_input_dir, EXPECTED["c2_input_manifest"], EXPECTED["c2_input_records"], EXPECTED["c2_input_order"], 10000),
    (c3_input_dir, EXPECTED["c3_input_manifest"], EXPECTED["c3_input_records"], EXPECTED["c3_input_order"], 9621),
):
    manifest, records = _load_input_bundle(root)
    if digest(root / "input_manifest.json") != manifest_sha or manifest.get("records_sha256") != records_sha or manifest.get("problem_order_sha256") != order_sha or len(records) != count:
        raise SystemExit(f"historical reuse input identity mismatch: {root}")

# Preserve the interrupted C3 source under one stable, read-only provenance path before reusing canonical output.
if not c3_source.exists():
    if not output_dir.is_dir():
        raise SystemExit("C3 canonical source is missing before C5 preservation")
    if digest(output_dir / "run.json") != EXPECTED["c3_run"] or digest(output_dir / "samples/generations.jsonl") != EXPECTED["c3_records"] or digest(output_dir / "samples/progress.json") != EXPECTED["c3_progress"]:
        raise SystemExit("canonical output is not the exact accepted C3 interrupted source")
    c3_source.parent.mkdir(parents=True, exist_ok=True)
    os.replace(output_dir, c3_source)
else:
    if not c3_source.is_dir():
        raise SystemExit("stable C3 reuse source path is not a directory")

c2_manifest, c2_inputs = _load_input_bundle(c2_input_dir)
c3_manifest, c3_inputs = _load_input_bundle(c3_input_dir)
c2_run, c2_rows = load_committed(c2_source, EXPECTED["c2_run"], EXPECTED["c2_records"], EXPECTED["c2_progress"], 12)
c3_run, c3_rows = load_committed(c3_source, EXPECTED["c3_run"], EXPECTED["c3_records"], EXPECTED["c3_progress"], 426)
if c2_run.get("problem_batch_size") != 4 or c3_run.get("problem_batch_size") != 1:
    raise SystemExit("historical C2/C3 batch identity mismatch")
if c2_run.get("input_manifest_sha256") != EXPECTED["c2_input_manifest"] or c3_run.get("input_manifest_sha256") != EXPECTED["c3_input_manifest"]:
    raise SystemExit("historical C2/C3 generation-to-input binding mismatch")
if c2_run.get("input_records_sha256") != EXPECTED["c2_input_records"] or c3_run.get("input_records_sha256") != EXPECTED["c3_input_records"]:
    raise SystemExit("historical C2/C3 generation input-record binding mismatch")
if c2_run.get("problem_order_sha256") != EXPECTED["c2_input_order"] or c3_run.get("problem_order_sha256") != EXPECTED["c3_input_order"]:
    raise SystemExit("historical C2/C3 generation source-order binding mismatch")

b = load_completed_sft_checkpoint(b_run)
expected_sft = _sft_identity(b)
if c2_run.get("sft_checkpoint") != expected_sft or c3_run.get("sft_checkpoint") != expected_sft:
    raise SystemExit("historical C2/C3 frozen-B identity mismatch")
c2_ids = validate_groups(c2_rows, c2_inputs, 4)
c3_ids = validate_groups(c3_rows, c3_inputs, 1)
if c2_ids != c3_ids[:12]:
    raise SystemExit("C2 is not the exact first-12 problem prefix of C3 authority")

target_manifest, target = _load_input_bundle(input_dir)
target_by_id = {item.problem_id: item for item in target}
c2_by_id = {c2_rows[i * 8]["problem_id"]: c2_rows[i * 8:(i + 1) * 8] for i in range(12)}
c3_by_id = {c3_rows[i * 8]["problem_id"]: c3_rows[i * 8:(i + 1) * 8] for i in range(426)}
c2_input_by_id = {item.problem_id: item for item in c2_inputs}
c3_input_by_id = {item.problem_id: item for item in c3_inputs}
origins = []
missing = []
c2_reused = c3_reused = 0
for item in target:
    pid = item.problem_id
    if pid in c2_by_id:
        if c2_input_by_id[pid] != item:
            raise SystemExit("C2 reusable problem prompt/metadata differs from C4 target")
        origin = "C2"
        c2_reused += 1
    elif pid in c3_by_id:
        if c3_input_by_id[pid] != item:
            raise SystemExit("C3 reusable problem prompt/metadata differs from C4 target")
        origin = "C3"
        c3_reused += 1
    else:
        origin = "generated"
        missing.append(item)
    origins.append({"problem_id": pid, "origin": origin})
origin_content = b"".join(_json_bytes(row) for row in origins)
origin_sha = hashlib.sha256(origin_content).hexdigest()
if (c2_reused, c3_reused, len(missing), origin_sha) != (8, 211, 4781, expected_origin_sha):
    raise SystemExit(f"frozen C5 reuse mapping mismatch: c2={c2_reused} c3={c3_reused} missing={len(missing)} origin_sha={origin_sha}")

# Materialize a deterministic missing-only staging input. It is generation-only; final scoring remains bound to the original C4 5000 input.
missing_rows = [asdict(item) for item in missing]
if missing_input_dir.exists():
    missing_manifest = _load_json(missing_input_dir / "input_manifest.json")
    missing_loaded = _load_jsonl(missing_input_dir / "inputs.jsonl")
    if missing_loaded != missing_rows:
        raise SystemExit("existing C5 missing-only input rows changed")
    if missing_manifest.get("record_count") != 4781 or missing_manifest.get("derived_from_input_manifest_sha256") != digest(input_dir / "input_manifest.json"):
        raise SystemExit("existing C5 missing-only input manifest identity mismatch")
else:
    missing_input_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{missing_input_dir.name}.", dir=missing_input_dir.parent))
    try:
        records_sha = _write_jsonl(temp / "inputs.jsonl", missing_rows)
        _write_json(temp / "input_manifest.json", {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "seed": 42,
            "record_count": len(missing_rows),
            "records_sha256": records_sha,
            "problem_order_sha256": stable_json_hash([item.problem_id for item in missing]),
            "evidence_class": "formal_intermediate",
            "generation_role": "C5_missing_only_after_predeclared_C2_C3_reuse",
            "derived_from_input_manifest_sha256": digest(input_dir / "input_manifest.json"),
            "reuse_problem_origins_sha256": origin_sha,
        })
        os.replace(temp, missing_input_dir)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
expected_missing_manifest_sha = "91cf290342111b493017e61d5be7b314fe96b79b3284b6bc0dce04682414e308"
expected_missing_records_sha = "79b38b57277579d9eaf5499ea219f062a5e7bebb603eb8a473c8f84d18d915f1"
expected_missing_order_sha = "4f5fdfbf8d2238638672b17d795d7d9cc4629dd3cae8860eef4cdb61d15d8acf"
missing_manifest = _load_json(missing_input_dir / "input_manifest.json")
if (
    digest(missing_input_dir / "input_manifest.json") != expected_missing_manifest_sha
    or digest(missing_input_dir / "inputs.jsonl") != expected_missing_records_sha
    or missing_manifest.get("records_sha256") != expected_missing_records_sha
    or missing_manifest.get("problem_order_sha256") != expected_missing_order_sha
):
    raise SystemExit("C5 missing-only staging input frozen byte/order identity mismatch")

if output_dir.exists():
    run = _load_json(output_dir / "run.json")
    if run.get("status") == "completed" and run.get("generation_mode") == "composite_reuse_v1" and run.get("problem_origins_sha256") == expected_origin_sha:
        print("reuse_completed_final")
        raise SystemExit(0)
    raise SystemExit("canonical output exists but is not the exact completed C5 composite artifact")
print(f"generate_missing:c2=8:c3=211:new=4781:new_run={new_run_dir}")
PY_PREP
)" || fail_preflight "C5 C2/C3 reuse preparation failed"
printf '[%s] generation action=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$OUTPUT_ACTION" >>"$LOG_FILE"

CURRENT_PHASE="generation"
if [[ "$OUTPUT_ACTION" == "reuse_completed_final" ]]; then
  COMMAND_RC=0
else
  if "$CV" generate-refresh-calibration \
    --config "$REPO_ROOT/$CONFIG_REL" \
    --input-bundle-dir "$MISSING_INPUT_DIR" \
    --sft-run-dir "$B_RUN" \
    --block initial \
    --problem-batch-size "$PROBLEM_BATCH_SIZE" \
    --output-dir "$NEW_RUN_DIR" >>"$LOG_FILE" 2>&1; then
    COMMAND_RC=0
  else
    COMMAND_RC=$?
  fi
  if (( COMMAND_RC != 0 )); then
    finalize_gate "$COMMAND_RC" 125 command_failed "C5 missing-only generate-refresh-calibration exited nonzero"
    exit $?
  fi

  CURRENT_PHASE="compose"
  if ! "$PY" - "$INPUT_DIR" "$C2_INPUT_DIR" "$C3_INPUT_DIR" "$C2_SOURCE_DIR" "$C3_SOURCE_DIR" "$MISSING_INPUT_DIR" "$NEW_RUN_DIR" "$OUTPUT_DIR" "$B_RUN" "$REUSE_ORIGIN_SHA" <<'PY_COMPOSE'
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from code_verifier.training.calibration import (
    CALIBRATION_SCHEMA_VERSION,
    _json_bytes,
    _load_input_bundle,
    _load_jsonl,
    _sft_identity,
    _write_json,
    _write_jsonl,
    calibration_problem_seed,
    load_completed_calibration_generation,
)
from code_verifier.training.sft import load_completed_sft_checkpoint
(
    input_dir, c2_input_dir, c3_input_dir, c2_source, c3_source, missing_input_dir,
    new_run_dir, output_dir, b_run,
) = map(Path, sys.argv[1:10])
expected_origin_sha = sys.argv[10]

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rows(path: Path):
    return _load_jsonl(path)

target_manifest, target = _load_input_bundle(input_dir)
c2_manifest, c2_inputs = _load_input_bundle(c2_input_dir)
c3_manifest, c3_inputs = _load_input_bundle(c3_input_dir)
missing_manifest, missing = _load_input_bundle(missing_input_dir)
new_run, new_rows = load_completed_calibration_generation(new_run_dir)
if len(missing) != 4781 or len(new_rows) != 38248 or new_run.get("problem_batch_size") != 4:
    raise SystemExit("C5 missing-only generation count/batch mismatch")
if new_run.get("input_manifest_sha256") != digest(missing_input_dir / "input_manifest.json") or new_run.get("input_records_sha256") != missing_manifest.get("records_sha256"):
    raise SystemExit("C5 missing-only generation input binding mismatch")
if new_run.get("problem_order_sha256") != missing_manifest.get("problem_order_sha256"):
    raise SystemExit("C5 missing-only generation order binding mismatch")
b = load_completed_sft_checkpoint(b_run)
if new_run.get("sft_checkpoint") != _sft_identity(b):
    raise SystemExit("C5 missing-only generation frozen-B binding mismatch")

c2_rows = rows(c2_source / "samples/generations.jsonl")
c3_rows = rows(c3_source / "samples/generations.jsonl")
c2_groups = {c2_rows[i * 8]["problem_id"]: c2_rows[i * 8:(i + 1) * 8] for i in range(12)}
c3_groups = {c3_rows[i * 8]["problem_id"]: c3_rows[i * 8:(i + 1) * 8] for i in range(426)}
new_groups = {new_rows[i * 8]["problem_id"]: new_rows[i * 8:(i + 1) * 8] for i in range(4781)}
c2_input = {item.problem_id: item for item in c2_inputs}
c3_input = {item.problem_id: item for item in c3_inputs}
new_input = {item.problem_id: item for item in missing}
final_rows = []
origins = []
c2_count = c3_count = new_count = 0
for item in target:
    pid = item.problem_id
    if pid in c2_groups:
        if c2_input[pid] != item:
            raise SystemExit("C2 reused problem identity drift during composition")
        group, origin = c2_groups[pid], "C2"
        c2_count += 1
    elif pid in c3_groups:
        if c3_input[pid] != item:
            raise SystemExit("C3 reused problem identity drift during composition")
        group, origin = c3_groups[pid], "C3"
        c3_count += 1
    else:
        if pid not in new_groups or new_input[pid] != item:
            raise SystemExit("C5 generated-new problem identity/order coverage mismatch")
        group, origin = new_groups[pid], "generated"
        new_count += 1
    seed = calibration_problem_seed(42, pid, 0)
    if len(group) != 8:
        raise SystemExit("C5 composition group is not k8")
    for offset, row in enumerate(group):
        if row.get("problem_id") != pid or row.get("block_index") != 0 or row.get("sample_index") != offset or row.get("sample_seed") != seed:
            raise SystemExit("C5 composition group seed/index mismatch")
    final_rows.extend(group)
    origins.append({"problem_id": pid, "origin": origin})
if (c2_count, c3_count, new_count, len(final_rows)) != (8, 211, 4781, 40000):
    raise SystemExit("C5 composition source counts mismatch")
origin_blob = b"".join(_json_bytes(row) for row in origins)
if hashlib.sha256(origin_blob).hexdigest() != expected_origin_sha:
    raise SystemExit("C5 composition problem-origin hash mismatch")
if output_dir.exists():
    raise SystemExit("C5 canonical output unexpectedly exists before atomic composition")
output_dir.parent.mkdir(parents=True, exist_ok=True)
temp = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.C5.", dir=output_dir.parent))
try:
    records_sha = _write_jsonl(temp / "samples/generations.jsonl", final_rows)
    origins_sha = _write_jsonl(temp / "samples/problem_origins.jsonl", origins)
    records_size = (temp / "samples/generations.jsonl").stat().st_size
    _write_json(temp / "samples/progress.json", {"version": 1, "record_count": 40000, "byte_count": records_size})
    reuse_manifest = {
        "version": 1,
        "policy": "ordered_complete_problem_precedence_v1",
        "selection_timing": "problem_id_only_before_verifier_scoring",
        "per_problem_initial_sample_count": 8,
        "source_precedence": ["C2", "C3", "generated"],
        "C2_reused_problem_count": 8,
        "C3_reused_problem_count": 211,
        "generated_problem_count": 4781,
        "problem_origins_sha256": origins_sha,
        "C2_input_manifest_sha256": digest(c2_input_dir / "input_manifest.json"),
        "C2_run_sha256": digest(c2_source / "run.json"),
        "C2_records_sha256": digest(c2_source / "samples/generations.jsonl"),
        "C2_progress_sha256": digest(c2_source / "samples/progress.json"),
        "C3_input_manifest_sha256": digest(c3_input_dir / "input_manifest.json"),
        "C3_run_sha256": digest(c3_source / "run.json"),
        "C3_records_sha256": digest(c3_source / "samples/generations.jsonl"),
        "C3_progress_sha256": digest(c3_source / "samples/progress.json"),
        "generated_input_manifest_sha256": digest(missing_input_dir / "input_manifest.json"),
        "generated_run_sha256": digest(new_run_dir / "run.json"),
        "generated_records_sha256": digest(new_run_dir / "samples/generations.jsonl"),
        "generated_progress_sha256": digest(new_run_dir / "samples/progress.json"),
    }
    _write_json(temp / "reuse_manifest.json", reuse_manifest)
    _write_json(temp / "run.json", {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "status": "completed",
        "block_index": 0,
        "samples_per_problem": 8,
        "problem_batch_size": 4,
        "problem_batch_size_semantics": "generated_missing_only; reused groups retain source batch provenance",
        "input_manifest_sha256": digest(input_dir / "input_manifest.json"),
        "input_records_sha256": target_manifest["records_sha256"],
        "problem_order_sha256": target_manifest["problem_order_sha256"],
        "retry_manifest_sha256": None,
        "sft_checkpoint": _sft_identity(b),
        "record_count": 40000,
        "records_sha256": records_sha,
        "generation_mode": "composite_reuse_v1",
        "reuse_policy": "ordered_complete_problem_precedence_v1",
        "reuse_manifest_sha256": digest(temp / "reuse_manifest.json"),
        "problem_origins_sha256": origins_sha,
        "reused_problem_count": 219,
        "C2_reused_problem_count": 8,
        "C3_reused_problem_count": 211,
        "generated_problem_count": 4781,
        "generated_record_count": 38248,
        "generated_problem_order_sha256": missing_manifest["problem_order_sha256"],
    })
    # Standard loader must accept the self-contained final composite artifact before publication.
    load_completed_calibration_generation(temp)
    os.replace(temp, output_dir)
except Exception:
    shutil.rmtree(temp, ignore_errors=True)
    raise
print("C5 composite publication completed")
PY_COMPOSE
  then
    finalize_gate 0 125 compose_failed "C5 composite publication failed"
    exit $?
  fi
fi

CURRENT_PHASE="postcheck"
if "$PY" - "$POSTCHECK_FILE.tmp" "$INPUT_DIR" "$C2_INPUT_DIR" "$C3_INPUT_DIR" "$C2_SOURCE_DIR" "$C3_SOURCE_DIR" "$MISSING_INPUT_DIR" "$NEW_RUN_DIR" "$OUTPUT_DIR" "$B_RUN" "$HEAD_COMMIT" "$REUSE_ORIGIN_SHA" <<'PY_POSTCHECK'
import hashlib
import json
import math
import sys
from pathlib import Path
from code_verifier.training.calibration import _load_input_bundle, _load_json, _load_jsonl, _sft_identity, calibration_problem_seed, load_completed_calibration_generation
from code_verifier.training.sft import load_completed_sft_checkpoint
(
    output, input_dir, c2_input_dir, c3_input_dir, c2_source, c3_source,
    missing_input_dir, new_run_dir, generation_dir, b_run,
) = map(Path, sys.argv[1:11])
checkpoint_commit = sys.argv[11]
expected_origin_sha = sys.argv[12]

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

expected_bytes = {
    c2_input_dir / "input_manifest.json": "3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3",
    c2_source / "run.json": "823a8d6a738ddf3e905d43c2d390da3f9b449b07404f2d76cf60bb7b5db07b0f",
    c2_source / "samples/generations.jsonl": "b218d3437ceb495c31a89cbaf36a5ee30224bb2ef00e55d0def6e8d9edb8cfad",
    c2_source / "samples/progress.json": "a81f8e46efe27cde3fd00aea48bdb325cae45051b4620a0e8899c2aa19c98e5b",
    c3_input_dir / "input_manifest.json": "0ac247e0eae6244148a117a350284dd7088c6822a2eab68382eb22cfd1a2b6c6",
    c3_source / "run.json": "25568d1d83286e79ee92749163a0415b949b9e2208749c398f73488a34fcc48c",
    c3_source / "samples/generations.jsonl": "42fbe9e19da60723541bb4388e035b91aaeb597c775ec7fd4187542a0c1617a4",
    c3_source / "samples/progress.json": "9ab25cce8f1552647de273db825d57bb5f23cfca31808b73db02e247ef30afb8",
    missing_input_dir / "input_manifest.json": "91cf290342111b493017e61d5be7b314fe96b79b3284b6bc0dce04682414e308",
    missing_input_dir / "inputs.jsonl": "79b38b57277579d9eaf5499ea219f062a5e7bebb603eb8a473c8f84d18d915f1",
}
for path, expected_sha in expected_bytes.items():
    if not path.is_file() or digest(path) != expected_sha:
        raise SystemExit(f"C5 Gate A frozen provenance byte mismatch: {path}")

target_manifest, target = _load_input_bundle(input_dir)
missing_manifest, missing = _load_input_bundle(missing_input_dir)
run, records = load_completed_calibration_generation(generation_dir)
new_run, new_rows = load_completed_calibration_generation(new_run_dir)
b = load_completed_sft_checkpoint(b_run)
if len(target) != 5000 or len(records) != 40000 or len(missing) != 4781 or len(new_rows) != 38248:
    raise SystemExit("C5 Gate A final/missing generation counts mismatch")
if run.get("generation_mode") != "composite_reuse_v1" or run.get("reuse_policy") != "ordered_complete_problem_precedence_v1":
    raise SystemExit("C5 Gate A composite reuse protocol identity mismatch")
if run.get("input_manifest_sha256") != digest(input_dir / "input_manifest.json") or run.get("input_records_sha256") != target_manifest.get("records_sha256") or run.get("problem_order_sha256") != target_manifest.get("problem_order_sha256"):
    raise SystemExit("C5 Gate A final artifact is not bound to the exact C4 5000 input")
if run.get("sft_checkpoint") != _sft_identity(b) or new_run.get("sft_checkpoint") != _sft_identity(b):
    raise SystemExit("C5 Gate A frozen-B binding mismatch")
if run.get("problem_batch_size") != 4 or new_run.get("problem_batch_size") != 4 or run.get("samples_per_problem") != 8 or new_run.get("samples_per_problem") != 8:
    raise SystemExit("C5 Gate A k8/batch4 identity mismatch")
if (
    new_run.get("input_manifest_sha256") != digest(missing_input_dir / "input_manifest.json")
    or new_run.get("input_records_sha256") != "79b38b57277579d9eaf5499ea219f062a5e7bebb603eb8a473c8f84d18d915f1"
    or new_run.get("problem_order_sha256") != "4f5fdfbf8d2238638672b17d795d7d9cc4629dd3cae8860eef4cdb61d15d8acf"
    or missing_manifest.get("problem_order_sha256") != "4f5fdfbf8d2238638672b17d795d7d9cc4629dd3cae8860eef4cdb61d15d8acf"
):
    raise SystemExit("C5 Gate A missing-only generation input/order binding mismatch")
origins_path = generation_dir / "samples/problem_origins.jsonl"
origins = _load_jsonl(origins_path)
if digest(origins_path) != expected_origin_sha or len(origins) != 5000:
    raise SystemExit("C5 Gate A problem-origin sidecar hash/count mismatch")
counts = {"C2": 0, "C3": 0, "generated": 0}
for row in origins:
    if set(row) != {"problem_id", "origin"} or row.get("origin") not in counts:
        raise SystemExit("C5 Gate A problem-origin sidecar schema invalid")
    counts[row["origin"]] += 1
if counts != {"C2": 8, "C3": 211, "generated": 4781}:
    raise SystemExit(f"C5 Gate A reuse counts mismatch: {counts}")
if [row["problem_id"] for row in origins] != [item.problem_id for item in target]:
    raise SystemExit("C5 Gate A problem-origin order differs from C4 target")

c2_rows = _load_jsonl(c2_source / "samples/generations.jsonl")
c3_rows = _load_jsonl(c3_source / "samples/generations.jsonl")
c2_groups = {c2_rows[i * 8]["problem_id"]: c2_rows[i * 8:(i + 1) * 8] for i in range(12)}
c3_groups = {c3_rows[i * 8]["problem_id"]: c3_rows[i * 8:(i + 1) * 8] for i in range(426)}
new_groups = {new_rows[i * 8]["problem_id"]: new_rows[i * 8:(i + 1) * 8] for i in range(4781)}
for index, (item, origin) in enumerate(zip(target, origins, strict=True)):
    pid = item.problem_id
    final_group = records[index * 8:(index + 1) * 8]
    expected_group = c2_groups[pid] if origin["origin"] == "C2" else c3_groups[pid] if origin["origin"] == "C3" else new_groups[pid]
    if final_group != expected_group:
        raise SystemExit("C5 Gate A final group differs byte-semantically from its declared source")
    seed = calibration_problem_seed(42, pid, 0)
    for offset, row in enumerate(final_group):
        if row.get("problem_id") != pid or row.get("block_index") != 0 or row.get("sample_index") != offset or row.get("sample_seed") != seed:
            raise SystemExit("C5 Gate A final group identity/seed mismatch")
        tokens, latency, hit = row.get("completion_tokens"), row.get("generation_latency_ms"), row.get("hit_max_new_tokens")
        if isinstance(tokens, bool) or not isinstance(tokens, int) or not 0 <= tokens <= 512:
            raise SystemExit("C5 Gate A final token telemetry invalid")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or float(latency) < 0:
            raise SystemExit("C5 Gate A final latency telemetry invalid")
        if not isinstance(hit, bool) or hit != (tokens >= 512) or not isinstance(row.get("completion"), str):
            raise SystemExit("C5 Gate A final completion/truncation telemetry invalid")
progress = _load_json(generation_dir / "samples/progress.json")
if progress != {"version": 1, "record_count": 40000, "byte_count": (generation_dir / "samples/generations.jsonl").stat().st_size}:
    raise SystemExit("C5 Gate A final committed progress mismatch")
reuse_manifest_path = generation_dir / "reuse_manifest.json"
reuse_manifest = _load_json(reuse_manifest_path)
if run.get("reuse_manifest_sha256") != digest(reuse_manifest_path) or reuse_manifest.get("problem_origins_sha256") != expected_origin_sha:
    raise SystemExit("C5 Gate A reuse manifest hash/binding mismatch")
if (run.get("reused_problem_count"), run.get("C2_reused_problem_count"), run.get("C3_reused_problem_count"), run.get("generated_problem_count"), run.get("generated_record_count")) != (219, 8, 211, 4781, 38248):
    raise SystemExit("C5 Gate A run-level reuse/generated counts mismatch")
payload = {
    "version": 1,
    "status": "passed",
    "stage_id": "WP9-c",
    "checkpoint_id": "C5",
    "operator_gate_id": "wp9c-calibration-initial-generation",
    "operator_checkpoint_commit": checkpoint_commit,
    "problem_count": 5000,
    "record_count": 40000,
    "samples_per_problem": 8,
    "new_generation_problem_batch_size": 4,
    "reuse_policy": "ordered_complete_problem_precedence_v1",
    "reuse_selection_timing": "problem_id_only_before_verifier_scoring",
    "reused_problem_count": 219,
    "C2_reused_problem_count": 8,
    "C3_reused_problem_count": 211,
    "generated_problem_count": 4781,
    "generated_record_count": 38248,
    "problem_origins_sha256": expected_origin_sha,
    "input_manifest_sha256": digest(input_dir / "input_manifest.json"),
    "input_records_sha256": target_manifest["records_sha256"],
    "problem_order_sha256": target_manifest["problem_order_sha256"],
    "C2_source": {
        "run_sha256": digest(c2_source / "run.json"),
        "records_sha256": digest(c2_source / "samples/generations.jsonl"),
        "progress_sha256": digest(c2_source / "samples/progress.json"),
    },
    "C3_source": {
        "run_sha256": digest(c3_source / "run.json"),
        "records_sha256": digest(c3_source / "samples/generations.jsonl"),
        "progress_sha256": digest(c3_source / "samples/progress.json"),
    },
    "generated_new": {
        "input_manifest_sha256": digest(missing_input_dir / "input_manifest.json"),
        "run_sha256": digest(new_run_dir / "run.json"),
        "records_sha256": digest(new_run_dir / "samples/generations.jsonl"),
        "progress_sha256": digest(new_run_dir / "samples/progress.json"),
    },
    "final": {
        "run_sha256": digest(generation_dir / "run.json"),
        "records_sha256": digest(generation_dir / "samples/generations.jsonl"),
        "progress_sha256": digest(generation_dir / "samples/progress.json"),
        "reuse_manifest_sha256": digest(reuse_manifest_path),
    },
    "formal_b": {key: value for key, value in _sft_identity(b).items()},
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
  finalize_gate 0 "$POSTCHECK_RC" postcheck_failed "strict C5 composite-reuse Gate A postcheck failed"
  exit $?
fi
mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"

CURRENT_PHASE="complete"
finalize_gate 0 0 passed "WP9-c C5 completed 5,000 x 8 calibration with predeclared C2/C3 problem-level reuse (8 + 211 reused; 4,781 newly generated) and strict provenance postcheck"
exit $?
