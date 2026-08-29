#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP7-c"
GATE_ID="grpo-cd-generate-eval"
CHECKPOINT_ID="C27"
PLAN_COMMIT="8464e69691c527c726a2e28e5a7ca81fa2001bbf"
RESULT_CODE_COMMIT="d53a18cd951a3cab7e5571f95b3b508b61878b2d"
WORKFLOW_RUNTIME_COMMIT="657030c47a29411e343049926de10730858104a8"
RECONCILED_CHECKPOINT_ID="C25"
RECONCILED_CHECKPOINT_COMMIT="e0ec354790d42753c8170625adea4d5e28fe4325"
RECONCILED_RESULT_CODE_COMMIT="31b997279ff4e908165b93187fc898922a059de4"
C25_SCRIPT_SHA="cb68ff0c5dfc852810c6e6aff620093f0dd1ea7f4d759e9c5902607126551fae"
C25_STATUS_SHA="9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa"
C25_LOG_SHA="b08930b7c7a984816cb9ccb69fbfb031aa88d07768852f5fd9914297e5aa4234"
C25_EVIDENCE_SHA="0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e"
C25_POSTCHECK_SHA="c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63"
C26_CHECKPOINT_COMMIT="d53a18cd951a3cab7e5571f95b3b508b61878b2d"
C26_SCRIPT_SHA="f1fb281c0aef9ca237584b99374033a58a68fa75adc26ffbf1cdc111ae3f1565"
C26_LOG_SHA="28b31446fee864dab14ed9dd73d83831b1679d86c8117b93e01a3570bdab0c80"
EXPECTED_MACHINE_SHA="b2230476c3d7600477108db5684ba2efbef95b89f746b8d8a1bc83b88ba5cab7"
EXPECTED_READINESS_SHA="5e3a42ac4f99d8312f876bd4f7ac70b35d5b3db27a7ca7c8c96a7196b019e45d"
HISTORICAL_PISTON_IDENTITY_SHA="19e978bacadea8ff1ac358b3e19efb68f395740200faa460b0f17b706c283d79"
FORMAL_PAIR_SHA="31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9"
EVAL_DATASET_SHA="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
ORDERED_IDS_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
PISTON_DEFINITION_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
BASE_EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
MODEL_WEIGHTS_SHA="c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
B_RUN_NAME="B-sft-formal-seed42"
PUBLIC_RUN_NAME="C-public-grpo-formal-seed42"
HIDDEN_RUN_NAME="D-hidden-grpo-formal-seed42"

PLAN_REL="ai-work/planner/WP7-c-plan.md"
REPORT_REL="ai-work/executor/WP7-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP7-c/grpo-cd-generate-eval/C27/run.sh"
EVAL_CONFIG_REL="configs/eval/base.yaml"
PISTON_CONFIG_REL="configs/execution/piston-local.yaml"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
[[ -x "$PY" && -x "$CV" ]] || { echo "target checkout .venv is unavailable; do not start generation" >&2; exit 125; }

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
PUBLIC_GRPO_RUN="$ARTIFACT_ROOT/grpo/$PUBLIC_RUN_NAME"
HIDDEN_GRPO_RUN="$ARTIFACT_ROOT/grpo/$HIDDEN_RUN_NAME"
PUBLIC_GENERATION_RUN="$ARTIFACT_ROOT/generation/$PUBLIC_RUN_NAME"
HIDDEN_GENERATION_RUN="$ARTIFACT_ROOT/generation/$HIDDEN_RUN_NAME"
QUARANTINE_ROOT="$ARTIFACT_ROOT/generation-quarantine/$STAGE_ID/$GATE_ID/$CHECKPOINT_ID"
C25_OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/grpo-cd-formal/C25"
C25_STATUS_FILE="$C25_OP_ROOT/status"
C25_LOG_FILE="$C25_OP_ROOT/terminal.log"
C25_EVIDENCE_FILE="$C25_OP_ROOT/operator-evidence.json"
C25_POSTCHECK_FILE="$C25_OP_ROOT/postcheck-summary.json"
C26_OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/grpo-cd-generate-eval/C26"
C26_STATUS_FILE="$C26_OP_ROOT/status"
C26_LOG_FILE="$C26_OP_ROOT/terminal.log"
C26_EVIDENCE_FILE="$C26_OP_ROOT/operator-evidence.json"
C26_POSTCHECK_FILE="$C26_OP_ROOT/postcheck-summary.json"

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
HISTORICAL_PISTON_SHA=""
GPU_NAME=""
GPU_VRAM_MIB="0"
CURRENT_OPEN_R1=""
CURRENT_LOCK_SHA=""
CURRENT_TORCH=""
CURRENT_CUDA=""
PUBLIC_ACTION="unresolved"
HIDDEN_ACTION="unresolved"
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
    "$MACHINE_POINTER" "$READINESS_RECORD" "$HISTORICAL_PISTON_IDENTITY_RECORD" "$HEAD_COMMIT" "$SCRIPT_SHA" "$MACHINE_SHA" \
    "$READINESS_SHA" "$HISTORICAL_PISTON_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" \
    "$CURRENT_TORCH" "$CURRENT_CUDA" "$PUBLIC_ACTION" "$HIDDEN_ACTION" "$generation_started" "$command_rc" "$postcheck_rc" \
    "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path
(
    output, postcheck_path, repo_root, artifact_root, hf_home, formal_data_root,
    machine_pointer, readiness_record, historical_piston_record, checkpoint_commit, script_sha, machine_sha,
    readiness_sha, historical_piston_sha, gpu_name, gpu_vram_mib, open_r1_commit, dependency_lock_sha,
    torch_version, cuda_version, public_action, hidden_action, generation_started, command_rc, postcheck_rc,
    gate_status, note, start_time, end_time, attempt_id,
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

root = Path(artifact_root)
postcheck = None
postcheck_file = Path(postcheck_path)
if postcheck_file.is_file():
    value = json.loads(postcheck_file.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        postcheck = value
files = []
for run_name in ("C-public-grpo-formal-seed42", "D-hidden-grpo-formal-seed42"):
    run = root / "generation" / run_name
    for relative in (
        "run.json", "resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log",
        "samples/generations.jsonl",
    ):
        files.append(inventory(run / relative))
files.append(inventory(postcheck_file))
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP7-c",
    "source_plan_commit": "8464e69691c527c726a2e28e5a7ca81fa2001bbf",
    "operator_checkpoint_commit": checkpoint_commit,
    "result_code_commit": "d53a18cd951a3cab7e5571f95b3b508b61878b2d",
    "checkpoint_id": "C27",
    "operator_gate_id": "grpo-cd-generate-eval",
    "operator_script": "ai-work/executor/operator/WP7-c/grpo-cd-generate-eval/C27/run.sh",
    "operator_script_sha256": script_sha,
    "workflow_runtime_commit": "657030c47a29411e343049926de10730858104a8",
    "operator_checkpoint_reconciliation": {
        "version": 1,
        "reconciled_checkpoint_id": "C25",
        "reconciled_checkpoint_commit": "e0ec354790d42753c8170625adea4d5e28fe4325",
        "reconciled_checkpoint_task_kind_raw": "repair",
        "reconciled_checkpoint_task_kind_effective": "implementation",
        "accepted_c25_operator_evidence_sha256": "0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e",
    },
    "supersession": {
        "checkpoint_id": "C26",
        "operator_checkpoint_commit": "d53a18cd951a3cab7e5571f95b3b508b61878b2d",
        "operator_script_sha256": "f1fb281c0aef9ca237584b99374033a58a68fa75adc26ffbf1cdc111ae3f1565",
        "terminal_log_sha256": "28b31446fee864dab14ed9dd73d83831b1679d86c8117b93e01a3570bdab0c80",
        "failure_kind": "shell_unbound_local_label_before_generation",
        "generation_started": False,
    },
    "target_machine_pointer": machine_pointer,
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record": readiness_record,
    "target_readiness_record_sha256": readiness_sha or None,
    "historical_piston_identity_record": historical_piston_record,
    "historical_piston_identity_record_sha256": historical_piston_sha or None,
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
    "piston": {
        "definition_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
        "live_runtime_required": False,
        "live_runtime_contacted": False,
    },
    "formal_pair_sha256": "31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9",
    "evaluation_dataset_sha256": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "generation_actions": {"public": public_action, "hidden": hidden_action},
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
[[ "$PARENT_COMMIT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "C27 checkpoint parent does not equal result_code_commit"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --ignore-submodules=none)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge must remain untracked"
if ! git -C "$REPO_ROOT" diff --quiet "$PLAN_COMMIT" -- "$PLAN_REL"; then
  fail_preflight "sealed WP7-c plan changed after plan commit"
fi

if ! "$PY" - "$REPO_ROOT" "$HEAD_COMMIT" "$PARENT_COMMIT" "$REPORT_REL" "$SCRIPT_REL" <<'PY_SCOPE'
import subprocess
import sys
from pathlib import Path
repo = Path(sys.argv[1])
head, parent, report, script = sys.argv[2:]
rows = subprocess.run(
    ["git", "-C", str(repo), "diff-tree", "--no-commit-id", "--name-status", "-r", head],
    check=True, capture_output=True, text=True,
).stdout.splitlines()
if sorted(rows) != sorted([f"M\t{report}", f"A\t{script}"]):
    raise SystemExit("C27 checkpoint commit must contain exactly report modification plus new script")
mode_line = subprocess.run(
    ["git", "-C", str(repo), "ls-tree", head, "--", script],
    check=True, capture_output=True, text=True,
).stdout.strip()
if not mode_line.startswith("100755 "):
    raise SystemExit("tracked C27 operator script is not executable")
previous = subprocess.run(
    ["git", "-C", str(repo), "show", f"{parent}:{report}"],
    check=True, capture_output=True,
).stdout
current = (repo / report).read_bytes()
if len(current) <= len(previous) or not current.startswith(previous):
    raise SystemExit("execution report is not byte-for-byte append-only")
PY_SCOPE
then
  fail_preflight "C27 checkpoint scope/append-only provenance failed"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" <<'PY_META'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
pos = text.rfind("checkpoint_id: C27")
if pos < 0:
    raise SystemExit("C27 checkpoint block is missing")
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit("C27 checkpoint block is malformed")
block = text[start:end]
def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"C27 checkpoint field missing: {name}")
    return match.group(1).strip().strip('"').strip("'")
print("\t".join([
    field("stage_id"), field("task_kind"), field("source_plan_commit"), field("source_review_round"),
    field("source_review_commit"), field("repair_issue_ids"), field("result_code_commit"), field("operator_gate_id"),
    field("operator_handoff_mode"), field("operator_restart_policy"), field("operator_script_sha256"), field("workflow_runtime_commit"),
    field("operator_checkpoint_reconciliation_version"), field("reconciled_checkpoint_id"), field("reconciled_checkpoint_commit"),
    field("reconciled_checkpoint_task_kind_raw"), field("reconciled_checkpoint_task_kind_effective"),
    field("accepted_c25_operator_evidence_sha256"), field("accepted_c25_postcheck_sha256"), field("formal_pair_sha256"),
    field("evaluation_dataset_sha256"), field("ordered_problem_ids_sha256"), field("piston_definition_sha256"), field("status"),
]))
PY_META
)" || fail_preflight "cannot parse C27 checkpoint metadata"
IFS="$TAB" read -r CHECKPOINT_STAGE CHECKPOINT_TASK CHECKPOINT_PLAN CHECKPOINT_REVIEW_ROUND CHECKPOINT_REVIEW_COMMIT CHECKPOINT_REPAIR_IDS CHECKPOINT_RESULT CHECKPOINT_GATE CHECKPOINT_MODE CHECKPOINT_RESTART EXPECTED_SCRIPT_SHA CHECKPOINT_RUNTIME CHECKPOINT_RECON_VERSION CHECKPOINT_RECON_ID CHECKPOINT_RECON_COMMIT CHECKPOINT_RECON_RAW CHECKPOINT_RECON_EFFECTIVE CHECKPOINT_C25_EVIDENCE CHECKPOINT_C25_POSTCHECK CHECKPOINT_PAIR CHECKPOINT_DATASET CHECKPOINT_ORDER CHECKPOINT_PISTON CHECKPOINT_STATUS <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_STAGE" == "$STAGE_ID" && "$CHECKPOINT_TASK" == "implementation" && "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" ]] || fail_preflight "C27 implementation source provenance mismatch"
[[ "$CHECKPOINT_REVIEW_ROUND" == "null" && "$CHECKPOINT_REVIEW_COMMIT" == "null" && "$CHECKPOINT_REPAIR_IDS" == "[]" ]] || fail_preflight "C27 must not fabricate review provenance"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" && "$CHECKPOINT_GATE" == "$GATE_ID" && "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_RESTART" == "exact_rerun" ]] || fail_preflight "C27 gate/handoff/restart provenance mismatch"
[[ "$CHECKPOINT_RUNTIME" == "$WORKFLOW_RUNTIME_COMMIT" && "$CHECKPOINT_RECON_VERSION" == "1" && "$CHECKPOINT_RECON_ID" == "$RECONCILED_CHECKPOINT_ID" && "$CHECKPOINT_RECON_COMMIT" == "$RECONCILED_CHECKPOINT_COMMIT" ]] || fail_preflight "C27 reconciliation runtime/checkpoint provenance mismatch"
[[ "$CHECKPOINT_RECON_RAW" == "repair" && "$CHECKPOINT_RECON_EFFECTIVE" == "implementation" ]] || fail_preflight "C27 reconciliation raw/effective task provenance mismatch"
[[ "$CHECKPOINT_C25_EVIDENCE" == "$C25_EVIDENCE_SHA" && "$CHECKPOINT_C25_POSTCHECK" == "$C25_POSTCHECK_SHA" ]] || fail_preflight "C27 accepted C25 evidence metadata mismatch"
[[ "$CHECKPOINT_PAIR" == "$FORMAL_PAIR_SHA" && "$CHECKPOINT_DATASET" == "$EVAL_DATASET_SHA" && "$CHECKPOINT_ORDER" == "$ORDERED_IDS_SHA" && "$CHECKPOINT_PISTON" == "$PISTON_DEFINITION_SHA" ]] || fail_preflight "C27 scientific identity metadata mismatch"
[[ "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "C27 checkpoint status is not awaiting_operator"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked C27 operator script SHA differs from report"

[[ "$MACHINE_SHA" == "$EXPECTED_MACHINE_SHA" ]] || fail_preflight "validation machine pointer SHA changed from accepted C25 machine"
[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -d "$DATA_DIR" ]] || fail_preflight "target persistent roots are unavailable"
[[ "$ARTIFACT_ROOT" != "$REPO_ROOT" && "$ARTIFACT_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "artifact_root must remain outside target checkout"
[[ "$FORMAL_DATA_ROOT" != "$REPO_ROOT" && "$FORMAL_DATA_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "formal_data_root must remain outside target checkout"
[[ "$TARGET_HF_HOME" != "$REPO_ROOT" && "$TARGET_HF_HOME" != "$REPO_ROOT/"* ]] || fail_preflight "hf_home must remain outside target checkout"
[[ -f "$READINESS_RECORD" && -f "$HISTORICAL_PISTON_IDENTITY_RECORD" ]] || fail_preflight "target readiness/historical Piston records are unavailable"
READINESS_SHA="$(sha256sum "$READINESS_RECORD" | awk '{print $1}')"
HISTORICAL_PISTON_SHA="$(sha256sum "$HISTORICAL_PISTON_IDENTITY_RECORD" | awk '{print $1}')"
[[ "$READINESS_SHA" == "$EXPECTED_READINESS_SHA" ]] || fail_preflight "readiness record SHA changed from accepted C25 machine"
[[ "$HISTORICAL_PISTON_SHA" == "$HISTORICAL_PISTON_IDENTITY_SHA" ]] || fail_preflight "historical Piston identity record changed"

[[ -f "$C25_STATUS_FILE" && -f "$C25_LOG_FILE" && -f "$C25_EVIDENCE_FILE" && -f "$C25_POSTCHECK_FILE" ]] || fail_preflight "accepted C25 target evidence is incomplete"
[[ "$(sha256sum "$C25_STATUS_FILE" | awk '{print $1}')" == "$C25_STATUS_SHA" ]] || fail_preflight "C25 status evidence changed"
[[ "$(sha256sum "$C25_LOG_FILE" | awk '{print $1}')" == "$C25_LOG_SHA" ]] || fail_preflight "C25 terminal log evidence changed"
[[ "$(sha256sum "$C25_EVIDENCE_FILE" | awk '{print $1}')" == "$C25_EVIDENCE_SHA" ]] || fail_preflight "C25 operator evidence changed"
[[ "$(sha256sum "$C25_POSTCHECK_FILE" | awk '{print $1}')" == "$C25_POSTCHECK_SHA" ]] || fail_preflight "C25 postcheck evidence changed"
[[ "$(tr -d '\r\n' < "$C25_STATUS_FILE")" == "0" ]] || fail_preflight "C25 target status is not successful"
if ! "$PY" - "$C25_EVIDENCE_FILE" "$C25_POSTCHECK_FILE" "$ARTIFACT_ROOT" "$RECONCILED_CHECKPOINT_COMMIT" "$RECONCILED_RESULT_CODE_COMMIT" "$C25_SCRIPT_SHA" "$FORMAL_PAIR_SHA" "$EXPECTED_MACHINE_SHA" <<'PY_C25'
import hashlib
import json
import sys
from pathlib import Path
(
    evidence_path, postcheck_path, artifact_root, checkpoint_commit, result_commit, script_sha,
    formal_pair_sha, machine_sha,
) = sys.argv[1:]
root = Path(artifact_root)
evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
postcheck = json.loads(Path(postcheck_path).read_text(encoding="utf-8"))
expected = {
    "version": 1,
    "stage_id": "WP7-c",
    "source_plan_commit": "8464e69691c527c726a2e28e5a7ca81fa2001bbf",
    "operator_checkpoint_commit": checkpoint_commit,
    "result_code_commit": result_commit,
    "training_code_commit": result_commit,
    "checkpoint_id": "C25",
    "operator_gate_id": "grpo-cd-formal",
    "operator_handoff_mode": "portable_target",
    "operator_script": "ai-work/executor/operator/WP7-c/grpo-cd-formal/C25/run.sh",
    "operator_script_sha256": script_sha,
    "command_rc": 0,
    "postcheck_rc": 0,
    "gate_status": "passed",
    "target_machine_record_sha256": machine_sha,
}
if not isinstance(evidence, dict) or any(evidence.get(k) != v for k, v in expected.items()):
    raise SystemExit("C25 operator evidence identity changed")
public_verify = evidence.get("public_verify_only")
if not isinstance(public_verify, dict) or public_verify.get("train_grpo_invoked") is not False or public_verify.get("unchanged") is not True or public_verify.get("before_snapshot_sha256") != public_verify.get("after_snapshot_sha256"):
    raise SystemExit("C25 Public verify-only evidence changed")
actions = evidence.get("run_actions")
if not isinstance(actions, dict) or actions.get("public") != "verify-only" or not str(actions.get("hidden", "")).endswith("/checkpoints/checkpoint-125"):
    raise SystemExit("C25 run action evidence changed")
if evidence.get("gpu_name") != "NVIDIA GeForce RTX 4090" or int(evidence.get("gpu_vram_mib", 0)) < 22528:
    raise SystemExit("C25 GPU identity changed")
if postcheck.get("version") != 1 or postcheck.get("status") != "passed" or postcheck.get("formal_training_completed") is not True or postcheck.get("generation_started") is not False:
    raise SystemExit("C25 formal postcheck status changed")
for member, mode in (("public", "public"), ("hidden", "hidden")):
    row = postcheck.get(member)
    if not isinstance(row, dict) or row.get("global_step") != 300 or row.get("reward_mode") != mode or row.get("paired_definition_sha256") != formal_pair_sha:
        raise SystemExit(f"C25 {member} completed formal identity changed")
for item in evidence.get("expected_artifact_inventory", []):
    if not isinstance(item, dict) or item.get("exists") is not True:
        raise SystemExit("C25 artifact inventory is malformed")
    path = Path(str(item.get("path", "")))
    try:
        path.relative_to(root)
    except ValueError:
        raise SystemExit("C25 inventory escaped artifact root")
    if not path.is_file():
        raise SystemExit(f"C25 inventoried artifact disappeared: {path}")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != item.get("sha256") or path.stat().st_size != item.get("size_bytes"):
        raise SystemExit(f"C25 inventoried artifact changed: {path}")
PY_C25
then
  fail_preflight "accepted C25 target evidence validation failed"
fi

[[ "$RESULT_CODE_COMMIT" == "$C26_CHECKPOINT_COMMIT" ]] || fail_preflight "C27 result_code_commit must be the superseded C26 checkpoint commit"
[[ -f "$C26_LOG_FILE" ]] || fail_preflight "superseded C26 terminal log is unavailable"
[[ "$(sha256sum "$C26_LOG_FILE" | awk '{print $1}')" == "$C26_LOG_SHA" ]] || fail_preflight "superseded C26 terminal log changed"
[[ "$(sha256sum "$REPO_ROOT/ai-work/executor/operator/WP7-c/grpo-cd-generate-eval/C26/run.sh" | awk '{print $1}')" == "$C26_SCRIPT_SHA" ]] || fail_preflight "superseded C26 tracked script changed"
[[ ! -e "$C26_STATUS_FILE" && ! -e "$C26_EVIDENCE_FILE" && ! -e "$C26_POSTCHECK_FILE" ]] || fail_preflight "C26 unexpectedly gained terminal status/evidence after the pre-generation shell failure"
if ! "$PY" - "$C26_LOG_FILE" <<'PY_C26_FAILURE'
import sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
if not lines or "checkpoint=C26 gate=grpo-cd-generate-eval" not in lines[0]:
    raise SystemExit("C26 terminal log start identity changed")
if not any("source identities public_checkpoint=" in line and "hidden_checkpoint=" in line for line in lines):
    raise SystemExit("C26 source identity preflight did not complete")
if not any("generation actions public=fresh hidden=fresh" in line for line in lines):
    raise SystemExit("C26 failure no longer proves both generation targets were fresh before dispatch")
if any("generated 400 evaluation prompts" in line for line in lines):
    raise SystemExit("C26 log unexpectedly contains generation completion output")
PY_C26_FAILURE
then
  fail_preflight "superseded C26 pre-generation failure evidence validation failed"
fi

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
print(f"{name}\t{vram_mib}")
PY_GPU
)" || fail_preflight "CUDA target validation failed"
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
expected_packages = {
    "accelerate": "1.4.0", "datasets": "3.2.0", "open-r1": "0.1.0.dev0", "peft": "0.14.0",
    "torch": "2.6.0+cu124", "transformers": "4.52.3", "trl": "0.18.0",
}
if current.get("packages") != expected_packages:
    raise SystemExit("current package map mismatch")
if current.get("project_commit") != head or current.get("open_r1_commit") != expected_open_r1 or current.get("dependency_lock_hash") != expected_lock:
    raise SystemExit("current project/Open-R1/dependency identity mismatch")
if current.get("python_version") != "3.10.21" or current.get("cuda_version") != "12.4":
    raise SystemExit("current Python/CUDA identity mismatch")
if current.get("gpu_name") != "NVIDIA GeForce RTX 4090" or current.get("gpu_count") != 1 or current.get("compute_capability") != "8.9":
    raise SystemExit("current GPU runtime identity mismatch")
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

[[ "$(sha256sum "$REPO_ROOT/$EVAL_CONFIG_REL" | awk '{print $1}')" == "$BASE_EVAL_CONFIG_SHA" ]] || fail_preflight "base evaluation config SHA changed"
[[ "$(sha256sum "$REPO_ROOT/$PISTON_CONFIG_REL" | awk '{print $1}')" == "$PISTON_DEFINITION_SHA" ]] || fail_preflight "tracked Piston definition SHA changed"
if ! "$CV" check-data --dataset "$DATA_DIR" >>"$LOG_FILE" 2>&1; then
  fail_preflight "formal data check-data failed"
fi

SOURCE_FIELDS="$($PY - "$REPO_ROOT" "$DATA_DIR" "$PUBLIC_GRPO_RUN" "$HIDDEN_GRPO_RUN" "$EVAL_DATASET_SHA" "$ORDERED_IDS_SHA" "$FORMAL_PAIR_SHA" "$DEPENDENCY_LOCK_SHA" "$MODEL_ID" "$MODEL_REVISION" "$PISTON_DEFINITION_SHA" <<'PY_SOURCE'
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.evaluation.evaluate import dataset_hash, load_evaluation_config, load_evaluation_problems
from code_verifier.training import grpo_evaluation_checkpoint_id, load_completed_grpo_checkpoint
repo, data_dir, public_run, hidden_run = map(Path, sys.argv[1:5])
expected_dataset, expected_order, expected_pair, expected_lock, model_id, model_revision, piston_sha = sys.argv[5:12]
config = load_evaluation_config(repo / "configs/eval/base.yaml")
config = replace(config, dataset_dir=data_dir)
if config.split != "test" or config.device != "cuda" or config.model_revision != model_revision:
    raise SystemExit("evaluation split/device/model revision changed")
if config.generation.do_sample is not False or config.generation.temperature is not None or config.generation.top_p is not None or config.generation.max_new_tokens != 512 or config.generation.dtype != "float16":
    raise SystemExit("deterministic evaluation generation contract changed")
problems = load_evaluation_problems(config)
if len(problems) != 400 or dataset_hash(problems) != expected_dataset:
    raise SystemExit("formal evaluation dataset identity changed")
ordered = hashlib.sha256(json.dumps([p.problem_id for p in problems], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
if ordered != expected_order:
    raise SystemExit("formal evaluation problem order changed")
if hashlib.sha256((repo / "configs/execution/piston-local.yaml").read_bytes()).hexdigest() != piston_sha:
    raise SystemExit("Piston definition changed")
public = load_completed_grpo_checkpoint(public_run)
hidden = load_completed_grpo_checkpoint(hidden_run)
for identity, run_name, mode in ((public, "C-public-grpo-formal-seed42", "public"), (hidden, "D-hidden-grpo-formal-seed42", "hidden")):
    if identity.run_id != run_name or identity.reward_mode != mode or identity.seed != 42:
        raise SystemExit(f"formal GRPO source identity changed: {run_name}")
    if identity.paired_definition_sha256 != expected_pair or identity.dependency_lock_hash != expected_lock:
        raise SystemExit(f"formal GRPO pair/dependency identity changed: {run_name}")
    parent = identity.parent_sft
    if parent.run_id != "B-sft-formal-seed42" or parent.model_id != model_id or parent.model_revision != model_revision or parent.seed != 42 or parent.dependency_lock_hash != expected_lock:
        raise SystemExit(f"formal GRPO parent B identity changed: {run_name}")
if public.parent_sft.run_dir != hidden.parent_sft.run_dir or public.parent_sft.checkpoint_dir != hidden.parent_sft.checkpoint_dir:
    raise SystemExit("C/D no longer share the same formal B parent")
print("\t".join([grpo_evaluation_checkpoint_id(public), grpo_evaluation_checkpoint_id(hidden)]))
PY_SOURCE
)" || fail_preflight "formal C/D source + evaluation identity validation failed"
IFS="$TAB" read -r PUBLIC_CHECKPOINT_ID HIDDEN_CHECKPOINT_ID <<<"$SOURCE_FIELDS"
printf '[%s] source identities public_checkpoint=%s hidden_checkpoint=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PUBLIC_CHECKPOINT_ID" "$HIDDEN_CHECKPOINT_ID" >>"$LOG_FILE"

if ! "$PY" - "$ARTIFACT_ROOT" <<'PY_STORAGE'
import os
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1])
usage = shutil.disk_usage(root)
stat = os.statvfs(root)
free_inodes = stat.f_favail
if usage.free < 15 * 1024**3:
    raise SystemExit("generation operator requires at least 15 GiB free")
if free_inodes < 100000:
    raise SystemExit("generation operator requires at least 100000 free inodes")
print(f"storage_free_bytes={usage.free} storage_free_inodes={free_inodes}")
PY_STORAGE
then
  fail_preflight "generation storage gate failed"
fi

prepare_generation() {
  local run_name="$1" grpo_run="$2"
  "$PY" - "$REPO_ROOT" "$DATA_DIR" "$ARTIFACT_ROOT" "$QUARANTINE_ROOT" "$run_name" "$grpo_run" "$ATTEMPT_ID" <<'PY_PREP'
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from code_verifier.evaluation.evaluate import load_evaluation_config, load_evaluation_problems
from code_verifier.evaluation.staged import _resume_bundle
from code_verifier.training import grpo_evaluation_checkpoint_id, load_completed_grpo_checkpoint
repo, data_dir, artifact_root, quarantine_root = map(Path, sys.argv[1:5])
run_name, grpo_run, attempt_id = sys.argv[5:8]
grpo = load_completed_grpo_checkpoint(Path(grpo_run))
config = load_evaluation_config(repo / "configs/eval/base.yaml")
config = replace(
    config,
    dataset_dir=data_dir,
    model_revision=grpo.parent_sft.model_revision,
    checkpoint=grpo_evaluation_checkpoint_id(grpo),
)
problems = load_evaluation_problems(config)
run_dir = artifact_root / "generation" / run_name
if not run_dir.exists():
    print("fresh")
    raise SystemExit(0)
status = None
try:
    value = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if isinstance(value, dict):
        status = value.get("status")
except Exception:
    status = None
try:
    _, records = _resume_bundle(
        output_root=artifact_root,
        run_id=run_name,
        config=config,
        model_id=grpo.parent_sft.model_id,
        seed=42,
        problems=problems,
    )
except Exception as error:
    if status == "completed":
        raise SystemExit(f"completed generation bundle failed strict identity validation: {type(error).__name__}: {error}")
    quarantine_root.mkdir(parents=True, exist_ok=True)
    destination = quarantine_root / f"{run_name}.before-{attempt_id}"
    manifest = quarantine_root / f"{run_name}.before-{attempt_id}.manifest.json"
    if destination.exists() or manifest.exists():
        raise SystemExit("generation quarantine destination already exists")
    os.replace(run_dir, destination)
    payload = {
        "version": 1,
        "stage_id": "WP7-c",
        "gate_id": "grpo-cd-generate-eval",
        "checkpoint_id": "C27",
        "run_name": run_name,
        "original_path": str(run_dir),
        "quarantined_path": str(destination),
        "observed_status": status,
        "reason": "incompatible_or_malformed_incomplete_generation_bundle",
        "error_type": type(error).__name__,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"quarantined:{destination}")
    raise SystemExit(0)
print(f"completed:{len(records)}" if status == "completed" else f"resume:{len(records)}")
PY_PREP
}

PUBLIC_ACTION="$(prepare_generation "$PUBLIC_RUN_NAME" "$PUBLIC_GRPO_RUN")" || fail_preflight "Public generation prefix preparation failed"
HIDDEN_ACTION="$(prepare_generation "$HIDDEN_RUN_NAME" "$HIDDEN_GRPO_RUN")" || fail_preflight "Hidden generation prefix preparation failed"
printf '[%s] generation actions public=%s hidden=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PUBLIC_ACTION" "$HIDDEN_ACTION" >>"$LOG_FILE"

CURRENT_PHASE="generation"
run_generate() {
  local run_name="$1" grpo_run="$2" label="$3"
  local out_file="$OP_ROOT/$label.generate.stdout"
  : >"$out_file"
  "$CV" generate-eval \
    --config "$REPO_ROOT/$EVAL_CONFIG_REL" \
    --dataset-dir "$DATA_DIR" \
    --grpo-run-dir "$grpo_run" \
    --run-name "$run_name" --seed 42 \
    --output-dir "$ARTIFACT_ROOT" >"$out_file" 2>>"$LOG_FILE"
  local rc=$?
  cat "$out_file" >>"$LOG_FILE"
  return "$rc"
}

set +e
run_generate "$PUBLIC_RUN_NAME" "$PUBLIC_GRPO_RUN" public
PUBLIC_RC=$?
set -e
if (( PUBLIC_RC != 0 )); then
  finalize_gate "$PUBLIC_RC" 125 command_failed "Public generate-eval exited nonzero"
  exit $?
fi
set +e
run_generate "$HIDDEN_RUN_NAME" "$HIDDEN_GRPO_RUN" hidden
HIDDEN_RC=$?
set -e
if (( HIDDEN_RC != 0 )); then
  finalize_gate "$HIDDEN_RC" 125 command_failed "Hidden generate-eval exited nonzero after Public bundle completed/resumed"
  exit $?
fi

CURRENT_PHASE="postcheck"
set +e
"$PY" - "$POSTCHECK_FILE.tmp" "$REPO_ROOT" "$DATA_DIR" "$PUBLIC_GRPO_RUN" "$HIDDEN_GRPO_RUN" "$PUBLIC_GENERATION_RUN" "$HIDDEN_GENERATION_RUN" "$HEAD_COMMIT" "$EVAL_DATASET_SHA" "$ORDERED_IDS_SHA" "$FORMAL_PAIR_SHA" "$PISTON_DEFINITION_SHA" "$DEPENDENCY_LOCK_SHA" "$OPEN_R1_COMMIT" <<'PY_POSTCHECK'
import hashlib
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.evaluation.evaluate import load_evaluation_config, load_evaluation_problems
from code_verifier.evaluation.staged import load_completed_generation_bundle
from code_verifier.training import grpo_evaluation_checkpoint_id, load_completed_grpo_checkpoint
(
    output, repo, data_dir, public_grpo_path, hidden_grpo_path, public_gen_path, hidden_gen_path,
    checkpoint_commit, expected_dataset, expected_order, expected_pair, expected_piston, expected_lock, expected_open_r1,
) = sys.argv[1:]
repo = Path(repo)
data_dir = Path(data_dir)

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inspect(grpo_path: str, generation_path: str, run_name: str, mode: str) -> dict[str, object]:
    grpo = load_completed_grpo_checkpoint(Path(grpo_path))
    if grpo.run_id != run_name or grpo.reward_mode != mode or grpo.seed != 42:
        raise SystemExit(f"{run_name}: formal GRPO source identity changed")
    if grpo.paired_definition_sha256 != expected_pair or grpo.dependency_lock_hash != expected_lock:
        raise SystemExit(f"{run_name}: formal pair/dependency identity changed")
    config = load_evaluation_config(repo / "configs/eval/base.yaml")
    config = replace(
        config,
        dataset_dir=data_dir,
        model_revision=grpo.parent_sft.model_revision,
        checkpoint=grpo_evaluation_checkpoint_id(grpo),
    )
    problems = load_evaluation_problems(config)
    identity, records = load_completed_generation_bundle(
        Path(generation_path), config=config, problems=problems, seed=42, require_current_code_identity=True
    )
    if identity.run_id != run_name or identity.model_id != grpo.parent_sft.model_id or identity.model_revision != grpo.parent_sft.model_revision:
        raise SystemExit(f"{run_name}: generation model identity mismatch")
    if identity.checkpoint != grpo_evaluation_checkpoint_id(grpo):
        raise SystemExit(f"{run_name}: generation checkpoint identity mismatch")
    if identity.dataset_hash != expected_dataset or identity.ordered_problem_ids_sha256 != expected_order or identity.piston_config_sha256 != expected_piston:
        raise SystemExit(f"{run_name}: generation evaluation identity mismatch")
    if identity.seed != 42 or identity.total_problems != 400 or len(records) != 400:
        raise SystemExit(f"{run_name}: generation row count/seed mismatch")
    problem_ids = [record.problem_id for record in records]
    if len(set(problem_ids)) != 400:
        raise SystemExit(f"{run_name}: problem IDs are not unique")
    if identity.gpu_count_used != 1 or not math.isfinite(identity.gpu_hours) or identity.gpu_hours < 0:
        raise SystemExit(f"{run_name}: generation GPU accounting invalid")
    run_dir = Path(generation_path)
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    environment = json.loads((run_dir / "environment.json").read_text(encoding="utf-8"))
    for value, label in ((run_json, "run"), (environment, "environment")):
        if value.get("project_commit") != checkpoint_commit or value.get("open_r1_commit") != expected_open_r1 or value.get("dependency_lock_hash") != expected_lock:
            raise SystemExit(f"{run_name}: {label} code identity mismatch")
    expected_packages = {
        "accelerate": "1.4.0", "datasets": "3.2.0", "open-r1": "0.1.0.dev0", "peft": "0.14.0",
        "torch": "2.6.0+cu124", "transformers": "4.52.3", "trl": "0.18.0",
    }
    if environment.get("packages") != expected_packages or environment.get("gpu_name") != "NVIDIA GeForce RTX 4090" or environment.get("gpu_count") != 1:
        raise SystemExit(f"{run_name}: frozen generation runtime identity mismatch")
    inventory = []
    for relative in (
        "run.json", "resolved_config.yaml", "environment.json", "metrics.jsonl", "stdout.log", "stderr.log",
        "samples/generations.jsonl",
    ):
        path = run_dir / relative
        if not path.is_file():
            raise SystemExit(f"{run_name}: missing generation artifact {relative}")
        inventory.append({"path": str(path), "size_bytes": path.stat().st_size, "sha256": digest(path)})
    return {
        "run_id": run_name,
        "reward_mode": mode,
        "formal_grpo_checkpoint": grpo_evaluation_checkpoint_id(grpo),
        "paired_definition_sha256": grpo.paired_definition_sha256,
        "parent_sft_run_id": grpo.parent_sft.run_id,
        "model_id": identity.model_id,
        "model_revision": identity.model_revision,
        "dataset_hash": identity.dataset_hash,
        "ordered_problem_ids_sha256": identity.ordered_problem_ids_sha256,
        "piston_config_sha256": identity.piston_config_sha256,
        "evaluation_contract_sha256": identity.evaluation_contract_sha256,
        "records_sha256": identity.records_sha256,
        "environment_sha256": identity.environment_sha256,
        "seed": identity.seed,
        "total_problems": identity.total_problems,
        "gpu_count_used": identity.gpu_count_used,
        "gpu_hours": identity.gpu_hours,
        "start_time": identity.start_time,
        "end_time": identity.end_time,
        "inventory": inventory,
    }

public = inspect(public_grpo_path, public_gen_path, "C-public-grpo-formal-seed42", "public")
hidden = inspect(hidden_grpo_path, hidden_gen_path, "D-hidden-grpo-formal-seed42", "hidden")
if public["paired_definition_sha256"] != hidden["paired_definition_sha256"] or public["parent_sft_run_id"] != hidden["parent_sft_run_id"]:
    raise SystemExit("C/D generation sources do not share the same pair/B identity")
payload = {
    "version": 1,
    "status": "passed",
    "stage_id": "WP7-c",
    "checkpoint_id": "C27",
    "operator_gate_id": "grpo-cd-generate-eval",
    "operator_checkpoint_commit": checkpoint_commit,
    "generation_only": True,
    "piston_verification_started": False,
    "evaluation_dataset_sha256": expected_dataset,
    "ordered_problem_ids_sha256": expected_order,
    "formal_pair_sha256": expected_pair,
    "piston_definition_sha256": expected_piston,
    "public": public,
    "hidden": hidden,
    "quick_readback": None,
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_POSTCHECK
POSTCHECK_RC=$?
set -e
if (( POSTCHECK_RC != 0 )); then
  rm -f "$POSTCHECK_FILE.tmp"
  finalize_gate 0 "$POSTCHECK_RC" postcheck_failed "strict generation bundle postcheck failed"
  exit $?
fi

CURRENT_PHASE="readback"
readback_one() {
  local run_name="$1" grpo_run="$2" label="$3"
  local out_file="$OP_ROOT/$label.readback.stdout"
  : >"$out_file"
  "$CV" generate-eval \
    --config "$REPO_ROOT/$EVAL_CONFIG_REL" \
    --dataset-dir "$DATA_DIR" \
    --grpo-run-dir "$grpo_run" \
    --run-name "$run_name" --seed 42 \
    --output-dir "$ARTIFACT_ROOT" >"$out_file" 2>>"$LOG_FILE"
  local rc=$?
  cat "$out_file" >>"$LOG_FILE"
  return "$rc"
}

set +e
readback_one "$PUBLIC_RUN_NAME" "$PUBLIC_GRPO_RUN" public
PUBLIC_READBACK_RC=$?
set -e
if (( PUBLIC_READBACK_RC != 0 )); then
  rm -f "$POSTCHECK_FILE.tmp"
  finalize_gate 0 "$PUBLIC_READBACK_RC" postcheck_failed "Public 400/0 generation readback failed"
  exit $?
fi
set +e
readback_one "$HIDDEN_RUN_NAME" "$HIDDEN_GRPO_RUN" hidden
HIDDEN_READBACK_RC=$?
set -e
if (( HIDDEN_READBACK_RC != 0 )); then
  rm -f "$POSTCHECK_FILE.tmp"
  finalize_gate 0 "$HIDDEN_READBACK_RC" postcheck_failed "Hidden 400/0 generation readback failed"
  exit $?
fi

if ! "$PY" - "$POSTCHECK_FILE.tmp" "$OP_ROOT/public.readback.stdout" "$OP_ROOT/hidden.readback.stdout" <<'PY_READBACK'
import hashlib
import json
import sys
from pathlib import Path
postcheck_path, public_out, hidden_out = map(Path, sys.argv[1:4])
value = json.loads(postcheck_path.read_text(encoding="utf-8"))
expected_line = "generated 400 evaluation prompts (resumed=400, generated=0)"
readbacks = {}
for label, path in (("public", public_out), ("hidden", hidden_out)):
    text = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if expected_line not in lines:
        raise SystemExit(f"{label}: quick readback did not report resumed=400/generated=0")
    readbacks[label] = {"resumed": 400, "generated": 0, "stdout_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    member = value[label]
    for item in member["inventory"]:
        artifact = Path(item["path"])
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != item["sha256"] or artifact.stat().st_size != item["size_bytes"]:
            raise SystemExit(f"{label}: generation bundle changed during 400/0 readback")
value["quick_readback"] = readbacks
postcheck_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_READBACK
then
  rm -f "$POSTCHECK_FILE.tmp"
  finalize_gate 0 1 postcheck_failed "generation 400/0 readback identity validation failed"
  exit $?
fi
mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"

CURRENT_PHASE="complete"
finalize_gate 0 0 passed "C/D deterministic 400-row generation bundles completed and strict 400/0 readback passed; Piston verification was not started"
exit $?
