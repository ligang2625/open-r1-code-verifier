#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP7-c"
GATE_ID="grpo-cd-smoke"
CHECKPOINT_ID="C4"
PLAN_COMMIT="8464e69691c527c726a2e28e5a7ca81fa2001bbf"
RESULT_CODE_COMMIT="847f7c7f74b6d4d4af37762efe1da6a7370a8110"
B_RUN_NAME="B-sft-formal-seed42"
PUBLIC_RUN_NAME="C-public-grpo-smoke20-seed42"
HIDDEN_RUN_NAME="D-hidden-grpo-smoke20-seed42"
PUBLIC_CONFIG_REL="configs/grpo/validation-smoke-public.yaml"
HIDDEN_CONFIG_REL="configs/grpo/validation-smoke-hidden.yaml"
PISTON_CONFIG_REL="configs/execution/piston-local.yaml"
PLAN_REL="ai-work/planner/WP7-c-plan.md"
REPORT_REL="ai-work/executor/WP7-c-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP7-c/grpo-cd-smoke/C4/run.sh"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"

if [[ ! -x "$PY" || ! -x "$CV" ]]; then
  echo "target checkout .venv is unavailable; do not start GRPO" >&2
  exit 125
fi

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

pointer = Path(sys.argv[1])
value = json.loads(pointer.read_text(encoding="utf-8"))
required = (
    "version",
    "machine_status",
    "bootstrap_project_commit",
    "open_r1_commit",
    "artifact_root",
    "hf_home",
    "formal_data_root",
    "readiness_record",
    "piston_identity_record",
    "piston_endpoint",
    "piston_host_id",
)
if not isinstance(value, dict) or any(key not in value for key in required):
    raise SystemExit("validation machine pointer schema is invalid")
if value["version"] != 1 or value["machine_status"] != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine pointer is not READY_FOR_VALIDATION_PLANNER")
for key in ("artifact_root", "hf_home", "formal_data_root", "readiness_record", "piston_identity_record"):
    item = value[key]
    if not isinstance(item, str) or not Path(item).is_absolute():
        raise SystemExit(f"validation machine pointer {key} must be absolute")
for key in ("bootstrap_project_commit", "open_r1_commit", "piston_endpoint", "piston_host_id"):
    item = value[key]
    if not isinstance(item, str) or not item.strip():
        raise SystemExit(f"validation machine pointer {key} is invalid")
print("\t".join(str(value[key]) for key in required[2:]))
PY
)"
TAB="$(printf '\t')"
IFS="$TAB" read -r BOOTSTRAP_COMMIT MACHINE_OPEN_R1 ARTIFACT_ROOT TARGET_HF_HOME FORMAL_DATA_ROOT READINESS_RECORD PISTON_IDENTITY_RECORD PISTON_ENDPOINT PISTON_HOST_ID <<<"$MACHINE_FIELDS"

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$TARGET_HF_HOME"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"

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
C2_CHECKPOINT_COMMIT="b0d59cf0ccbdd5bd190f678ab1dc727a9112f98c"
C2_FAILED_PUBLIC_RUN_SHA="f642703ee635a4eafd02d8f905b34b85dcd1510b734d4288e7415e7047ce67cc"
C2_FAILED_STDERR_SHA="fc56b31a1f8c3bd2a166b0f815a68672b2631958f96a393be79049e62e9cd6b9"
C2_QUARANTINE_ROOT="$ARTIFACT_ROOT/grpo-validation/quarantine/$STAGE_ID/$GATE_ID/C2"
C2_QUARANTINE_DIR="$C2_QUARANTINE_ROOT/$PUBLIC_RUN_NAME-arrow-invalid-${C2_FAILED_PUBLIC_RUN_SHA:0:12}"
C2_QUARANTINE_MANIFEST="$C2_QUARANTINE_ROOT/quarantine-manifest.json"
C3_CHECKPOINT_COMMIT="500b3936dba6b0ef72a3e4a0ad8b703a35d93682"
C3_RESULT_CODE_COMMIT="7b47ee0ebb1b4c6ab494944155ff0fbd6ebaa0e0"
C3_FAILED_STDERR_SHA="cc0e697f76fe85b5ad6186baae92dcb29572e91a63ee09e1e687b25c1ffc21ea"
C3_OPERATOR_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$PLAN_COMMIT/$GATE_ID/C3"
C3_EVIDENCE_FILE="$C3_OPERATOR_ROOT/operator-evidence.json"
C3_STATUS_FILE="$C3_OPERATOR_ROOT/status"
C3_LOG_FILE="$C3_OPERATOR_ROOT/terminal.log"
C3_QUARANTINE_ROOT="$ARTIFACT_ROOT/grpo-validation/quarantine/$STAGE_ID/$GATE_ID/C3"
C3_QUARANTINE_DIR="$C3_QUARANTINE_ROOT/$PUBLIC_RUN_NAME-deepspeed-setuptools-${C3_CHECKPOINT_COMMIT:0:12}"
C3_QUARANTINE_MANIFEST="$C3_QUARANTINE_ROOT/quarantine-manifest.json"

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
MACHINE_SHA="$(sha256sum "$MACHINE_POINTER" | awk '{print $1}')"
READINESS_SHA=""
PISTON_IDENTITY_SHA=""
GPU_NAME=""
GPU_VRAM_MIB="0"
EXPECTED_PAIR_SHA=""
CURRENT_OPEN_R1=""
CURRENT_LOCK_SHA=""
CURRENT_TORCH=""
CURRENT_CUDA=""
PLAN_PUBLIC_SHA=""
PLAN_HIDDEN_SHA=""
PLAN_PISTON_SHA=""
CURRENT_PHASE="preflight"

write_evidence() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4" end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ -z "$HEAD_COMMIT" ]]; then
    HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
  fi
  if [[ -z "$SCRIPT_SHA" && -f "$REPO_ROOT/$SCRIPT_REL" ]]; then
    SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  fi
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$REPO_ROOT" "$MACHINE_POINTER" "$READINESS_RECORD" "$PISTON_IDENTITY_RECORD" \
    "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" "$HEAD_COMMIT" "$SCRIPT_SHA" "$MACHINE_SHA" "$READINESS_SHA" \
    "$PISTON_IDENTITY_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" "$PISTON_ENDPOINT" "$PISTON_HOST_ID" "$EXPECTED_PAIR_SHA" \
    "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$PLAN_PISTON_SHA" "$command_rc" "$postcheck_rc" \
    "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

(
    output,
    postcheck_path,
    repo_root,
    machine_pointer,
    readiness_record,
    piston_identity_record,
    artifact_root,
    hf_home,
    formal_data_root,
    checkpoint_commit,
    script_sha,
    machine_sha,
    readiness_sha,
    piston_identity_sha,
    gpu_name,
    gpu_vram_mib,
    piston_endpoint,
    piston_host_id,
    pair_sha,
    open_r1_commit,
    dependency_lock_sha,
    torch_version,
    cuda_version,
    piston_definition_sha,
    command_rc,
    postcheck_rc,
    gate_status,
    note,
    start_time,
    end_time,
    attempt_id,
) = sys.argv[1:]


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inventory(path: Path, *, include_digest: bool) -> dict[str, object]:
    row: dict[str, object] = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        row["size_bytes"] = path.stat().st_size
        if include_digest:
            row["sha256"] = digest(path)
    return row


postcheck = None
postcheck_file = Path(postcheck_path)
if postcheck_file.is_file():
    value = json.loads(postcheck_file.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        postcheck = value
smoke_root = Path(artifact_root) / "grpo-validation" / "smoke"
files = []
for run_name in ("C-public-grpo-smoke20-seed42", "D-hidden-grpo-smoke20-seed42"):
    run = smoke_root / run_name
    for relative, include_digest in (
        ("run.json", True),
        ("resolved_config.yaml", True),
        ("environment.json", True),
        ("metrics.jsonl", True),
        ("rollouts.jsonl", False),
        ("rewards.jsonl", True),
        ("group_metrics.jsonl", True),
        ("checkpoints/adapter_config.json", True),
        ("checkpoints/adapter_model.safetensors", False),
    ):
        files.append(inventory(run / relative, include_digest=include_digest))
if postcheck_file.is_file():
    files.append(inventory(postcheck_file, include_digest=True))
c2_recovery_manifest = Path(artifact_root) / "grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C2/quarantine-manifest.json"
c3_recovery_manifest = Path(artifact_root) / "grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C3/quarantine-manifest.json"
payload = {
    "version": 1,
    "operator_handoff_mode": "portable_target",
    "stage_id": "WP7-c",
    "source_plan_commit": "8464e69691c527c726a2e28e5a7ca81fa2001bbf",
    "operator_checkpoint_commit": checkpoint_commit or None,
    "result_code_commit": "847f7c7f74b6d4d4af37762efe1da6a7370a8110",
    "checkpoint_id": "C4",
    "operator_gate_id": "grpo-cd-smoke",
    "operator_script": "ai-work/executor/operator/WP7-c/grpo-cd-smoke/C4/run.sh",
    "operator_script_sha256": script_sha or None,
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
        "definition_sha256": piston_definition_sha or None,
        "python_runtime": "3.10.0",
    },
    "formal_pair": {
        "public_run_name": "C-public-grpo-smoke20-seed42",
        "hidden_run_name": "D-hidden-grpo-smoke20-seed42",
        "seed": 42,
        "paired_definition_sha256": pair_sha or None,
        "parent_b_run_name": "B-sft-formal-seed42",
    },
    "attempt_id": attempt_id,
    "start_time": start_time,
    "end_time": end_time,
    "command_rc": int(command_rc),
    "postcheck_rc": int(postcheck_rc),
    "gate_status": gate_status,
    "note": note,
    "postcheck": postcheck,
    "recovery": {
        "c2_quarantine_manifest": inventory(c2_recovery_manifest, include_digest=True),
        "c3_quarantine_manifest": inventory(c3_recovery_manifest, include_digest=True),
    },
    "expected_artifact_inventory": files,
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY
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
printf '%s\n' "${CHECKPOINT_DIFF[@]}" | grep -Fxq "$SCRIPT_REL" || fail_preflight "checkpoint commit does not contain tracked C4 script"

CHECKPOINT_META="$($PY - "$REPO_ROOT/$REPORT_REL" "$CHECKPOINT_ID" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
marker = f"checkpoint_id: {sys.argv[2]}"
pos = text.rfind(marker)
if pos < 0:
    raise SystemExit(2)
start = text.rfind("execution_checkpoint:", 0, pos)
end = text.find("```", pos)
if start < 0 or end < 0:
    raise SystemExit(2)
block = text[start:end]


def field(name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if not match:
        raise SystemExit(2)
    return match.group(1).strip().strip('"').strip("'")


print(
    "\t".join(
        [
            field("operator_script_sha256"),
            field("operator_handoff_mode"),
            field("operator_gate_id"),
            field("operator_restart_policy"),
            field("result_code_commit"),
            field("source_plan_commit"),
            field("status"),
        ]
    )
)
PY
)" || fail_preflight "cannot parse C4 checkpoint provenance"
IFS="$TAB" read -r EXPECTED_SCRIPT_SHA CHECKPOINT_MODE CHECKPOINT_GATE CHECKPOINT_RESTART CHECKPOINT_RESULT CHECKPOINT_PLAN CHECKPOINT_STATUS <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_MODE" == "portable_target" && "$CHECKPOINT_GATE" == "$GATE_ID" ]] || fail_preflight "checkpoint handoff/gate mismatch"
[[ "$CHECKPOINT_RESTART" == "trainer_checkpoint" && "$CHECKPOINT_STATUS" == "awaiting_operator" ]] || fail_preflight "checkpoint restart/status mismatch"
[[ "$CHECKPOINT_RESULT" == "$RESULT_CODE_COMMIT" && "$CHECKPOINT_PLAN" == "$PLAN_COMMIT" ]] || fail_preflight "checkpoint source provenance mismatch"
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked operator script SHA mismatch"

PLAN_FIELDS="$($PY - "$REPO_ROOT/$PLAN_REL" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")


def one(pattern: str, name: str) -> str:
    match = re.search(pattern, text)
    if not match:
        raise SystemExit(f"cannot parse sealed plan field: {name}")
    return match.group(1)


public_sha = one(r"formal `public_grpo\.jsonl`[^\n]*SHA256 `([0-9a-f]{64})`", "public data SHA")
hidden_sha = one(r"formal `hidden_grpo\.jsonl`[^\n]*SHA256 `([0-9a-f]{64})`", "hidden data SHA")
b_identity = re.search(
    r"run `B-sft-formal-seed42`[^\n]*model `([^`]+)@([0-9a-f]{40})`[^\n]*dataset hash `([0-9a-f]{64})`[^\n]*config hash `([0-9a-f]{64})`[^\n]*dependency lock hash `([0-9a-f]{64})`",
    text,
)
if not b_identity:
    raise SystemExit("cannot parse sealed formal B identity")
piston_sha = one(r"Piston definition SHA256 `([0-9a-f]{64})`", "Piston SHA")
print("\t".join([public_sha, hidden_sha, *b_identity.groups(), piston_sha]))
PY
)" || fail_preflight "cannot parse sealed plan identities"
IFS="$TAB" read -r PLAN_PUBLIC_SHA PLAN_HIDDEN_SHA PLAN_MODEL_ID PLAN_MODEL_REVISION PLAN_B_DATASET_SHA PLAN_B_CONFIG_SHA PLAN_B_LOCK_SHA PLAN_PISTON_SHA <<<"$PLAN_FIELDS"

[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" && -d "$TARGET_HF_HOME" && -d "$DATA_DIR" ]] || fail_preflight "target persistent roots are unavailable"
[[ "$ARTIFACT_ROOT" != "$REPO_ROOT" && "$ARTIFACT_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "artifact_root must remain outside the target checkout"
[[ "$FORMAL_DATA_ROOT" != "$REPO_ROOT" && "$FORMAL_DATA_ROOT" != "$REPO_ROOT/"* ]] || fail_preflight "formal_data_root must remain outside the target checkout"
[[ "$TARGET_HF_HOME" != "$REPO_ROOT" && "$TARGET_HF_HOME" != "$REPO_ROOT/"* ]] || fail_preflight "hf_home must remain outside the target checkout"
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


def contains_ready(value: object) -> bool:
    if isinstance(value, str):
        return value == "READY_FOR_VALIDATION_PLANNER"
    if isinstance(value, dict):
        return any(contains_ready(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_ready(item) for item in value)
    return False


if not contains_ready(readiness):
    raise SystemExit("readiness record is not READY_FOR_VALIDATION_PLANNER")
expected = {
    "deployment_mode": "ssh_tunneled_remote",
    "endpoint": endpoint,
    "python_runtime": "3.10.0",
    "piston_host_id": host_id,
}
if not isinstance(piston, dict) or any(piston.get(key) != value for key, value in expected.items()):
    raise SystemExit("Piston identity record mismatch")
acceptance = piston.get("real_piston_acceptance")
if acceptance not in {"PASS", "PASS_9_OF_9_TUNNELED"}:
    raise SystemExit("Piston identity record has invalid tunneled acceptance")
if acceptance == "PASS_9_OF_9_TUNNELED" and piston.get("local_piston_acceptance") != "PASS_9_OF_9":
    raise SystemExit("Piston identity record has inconsistent detailed acceptance")
if endpoint != "http://127.0.0.1:2000" or host_id != "1660ti-wsl":
    raise SystemExit("canonical Piston topology mismatch")
PY
then
  fail_preflight "target readiness/Piston identity validation failed"
fi

if ! GPU_LIST="$(nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits 2>>"$LOG_FILE")"; then
  fail_preflight "nvidia-smi GPU inventory failed"
fi
GPU_INDEX="$(printf '%s\n' "$GPU_LIST" | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$1); gsub(/ /,"",$3); if ($3+0 >= 22528) {print $1; exit}}')"
[[ -n "$GPU_INDEX" ]] || fail_preflight "no RTX 4090 with at least 22528 MiB VRAM detected"
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
GPU_FIELDS="$($PY - <<'PY'
import torch

if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise SystemExit("operator requires exactly one visible CUDA device")
properties = torch.cuda.get_device_properties(0)
name = properties.name
vram_mib = int(properties.total_memory // (1024 * 1024))
if "RTX 4090" not in name or vram_mib < 22528:
    raise SystemExit("visible GPU is not RTX 4090 class")
if not bool(torch.cuda.is_bf16_supported(including_emulation=False)):
    raise SystemExit("native BF16 is unavailable")
print(f"{name}\t{vram_mib}")
PY
)" || fail_preflight "CUDA/BF16 target validation failed"
IFS="$TAB" read -r GPU_NAME GPU_VRAM_MIB <<<"$GPU_FIELDS"

RUNTIME_OUTPUT="$($PY - "$REPO_ROOT" "$B_RUN" "$MACHINE_OPEN_R1" "$PLAN_B_LOCK_SHA" "$HEAD_COMMIT" <<'PY'
import inspect
import json
import sys
from pathlib import Path

import code_verifier
import open_r1
from code_verifier.environment import collect_environment
from code_verifier.training.grpo import _load_grpo_runtime

repo = Path(sys.argv[1]).resolve()
b_run = Path(sys.argv[2]).resolve()
machine_open_r1, expected_lock, expected_head = sys.argv[3:]
for module, name in ((code_verifier, "code_verifier"), (open_r1, "open_r1")):
    module_file = getattr(module, "__file__", None)
    if module_file is None or repo not in Path(module_file).resolve().parents:
        raise SystemExit(f"{name} does not resolve inside target checkout")
frozen_b = json.loads((b_run / "environment.json").read_text(encoding="utf-8"))
current = collect_environment()
for name, value in (("formal B environment", frozen_b), ("current environment", current)):
    if not isinstance(value, dict) or not isinstance(value.get("packages"), dict):
        raise SystemExit(f"{name} package identity is invalid")
if current.get("project_commit") != expected_head:
    raise SystemExit("current project commit does not equal operator checkpoint HEAD")
if current.get("open_r1_commit") != machine_open_r1 or frozen_b.get("open_r1_commit") != machine_open_r1:
    raise SystemExit("Open-R1 commit differs from machine/formal B identity")
if current.get("dependency_lock_hash") != expected_lock or frozen_b.get("dependency_lock_hash") != expected_lock:
    raise SystemExit("dependency lock differs from sealed/formal B identity")
if current["packages"] != frozen_b["packages"]:
    raise SystemExit("installed package versions differ from formal B frozen runtime")
torch_version = current["packages"].get("torch")
if not isinstance(torch_version, str) or not torch_version:
    raise SystemExit("installed torch identity is unavailable")
cuda_version = current.get("cuda_version")
if cuda_version != frozen_b.get("cuda_version") or not isinstance(cuda_version, str):
    raise SystemExit("current CUDA runtime differs from formal B frozen runtime")
if sys.version_info[:2] != (3, 10):
    raise SystemExit("target Python must be 3.10.x")
runtime = _load_grpo_runtime()
parameters = inspect.signature(runtime.training_config_type.__init__).parameters
for name in ("skip_memory_metrics", "logging_nan_inf_filter", "save_total_limit", "save_only_model"):
    if name not in parameters:
        raise SystemExit(f"GRPOConfig missing telemetry field: {name}")
print(f"WP7C_RUNTIME\t{current['open_r1_commit']}\t{current['dependency_lock_hash']}\t{torch_version}\t{cuda_version}")
PY
)" || fail_preflight "target runtime/package identity validation failed"
RUNTIME_FIELDS="$(printf '%s\n' "$RUNTIME_OUTPUT" | awk '/^WP7C_RUNTIME\t/ {count += 1; sub(/^WP7C_RUNTIME\t/, ""); value = $0} END {if (count != 1) exit 2; print value}')" || fail_preflight "target runtime output is ambiguous"
IFS="$TAB" read -r CURRENT_OPEN_R1 CURRENT_LOCK_SHA CURRENT_TORCH CURRENT_CUDA <<<"$RUNTIME_FIELDS"
[[ -n "$CURRENT_OPEN_R1" && -n "$CURRENT_LOCK_SHA" && -n "$CURRENT_TORCH" && -n "$CURRENT_CUDA" ]] || fail_preflight "target runtime identity fields are incomplete"

if ! "$PY" - "$PLAN_MODEL_ID" "$PLAN_MODEL_REVISION" >>"$LOG_FILE" <<'PY'
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

snapshot = Path(snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_files_only=True)).resolve()
if not snapshot.is_dir():
    raise SystemExit("exact model snapshot is not available local-only")
print(f"model_snapshot={snapshot}")
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
from code_verifier.training.grpo import (
    _paired_definition,
    load_grpo_training_config,
    load_training_artifact,
    validate_grpo_artifact_pair,
    validate_grpo_config_pair,
)

repo, data_dir, b_run = map(Path, sys.argv[1:4])
public_sha, hidden_sha, model_id, revision, b_dataset, b_config, b_lock = sys.argv[4:]
public_path = data_dir / "training" / "public_grpo.jsonl"
hidden_path = data_dir / "training" / "hidden_grpo.jsonl"
if hashlib.sha256(public_path.read_bytes()).hexdigest() != public_sha:
    raise SystemExit("formal Public GRPO dataset SHA mismatch")
if hashlib.sha256(hidden_path.read_bytes()).hexdigest() != hidden_sha:
    raise SystemExit("formal Hidden GRPO dataset SHA mismatch")
public_rows = load_training_artifact(public_path, kind=TrainingArtifactKind.PUBLIC_GRPO)
hidden_rows = load_training_artifact(hidden_path, kind=TrainingArtifactKind.HIDDEN_GRPO)
if len(public_rows) != 2500 or len(hidden_rows) != 2500:
    raise SystemExit("formal GRPO row count mismatch")
validate_grpo_artifact_pair(public_rows, hidden_rows)
parent = load_completed_sft_checkpoint(b_run)
expected_parent = {
    "run_id": "B-sft-formal-seed42",
    "model_id": model_id,
    "model_revision": revision,
    "dataset_hash": b_dataset,
    "config_hash": b_config,
    "dependency_lock_hash": b_lock,
    "seed": 42,
}
for key, value in expected_parent.items():
    if getattr(parent, key) != value:
        raise SystemExit(f"formal B identity mismatch: {key}")
public = replace(
    load_grpo_training_config(repo / "configs/grpo/validation-smoke-public.yaml"),
    dataset_path=public_path,
    run_name="C-public-grpo-smoke20-seed42",
)
hidden = replace(
    load_grpo_training_config(repo / "configs/grpo/validation-smoke-hidden.yaml"),
    dataset_path=hidden_path,
    run_name="D-hidden-grpo-smoke20-seed42",
)
validate_grpo_config_pair(public, hidden)
if (public.max_steps, hidden.max_steps, public.save_steps, hidden.save_steps) != (20, 20, 10, 10):
    raise SystemExit("smoke phase contract mismatch")
pair_sha, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
print(f"{pair_sha}\t{json.dumps(components, sort_keys=True, separators=(',', ':'))}")
PY
)" || fail_preflight "formal C/D pair or B identity validation failed"
IFS="$TAB" read -r EXPECTED_PAIR_SHA PAIR_COMPONENTS_JSON <<<"$PAIR_FIELDS"
[[ "$EXPECTED_PAIR_SHA" =~ ^[0-9a-f]{64}$ ]] || fail_preflight "computed paired definition SHA is invalid"

if ! "$PY" - "$DATA_DIR" >>"$LOG_FILE" <<'PY'
import sys
from pathlib import Path

from code_verifier.data.leakage_checks import TrainingArtifactKind
from code_verifier.training.grpo import load_training_artifact
from code_verifier.training.grpo_data import build_grpo_dataset

root = Path(sys.argv[1]) / "training"
public_records = load_training_artifact(root / "public_grpo.jsonl", kind=TrainingArtifactKind.PUBLIC_GRPO)
hidden_records = load_training_artifact(root / "hidden_grpo.jsonl", kind=TrainingArtifactKind.HIDDEN_GRPO)
public = build_grpo_dataset(public_records, reward_mode="public")
hidden = build_grpo_dataset(hidden_records, reward_mode="hidden")
if len(public) != 2500 or len(hidden) != 2500:
    raise SystemExit("formal GRPO trainer Dataset row count mismatch")
public_tests = public.features["visible_tests"]
hidden_visible = hidden.features["visible_tests"]
hidden_tests = hidden.features["train_hidden_tests"]
for name, feature in (
    ("public visible_tests", public_tests),
    ("hidden visible_tests", hidden_visible),
    ("hidden train_hidden_tests", hidden_tests),
):
    item = getattr(feature, "feature", None)
    if getattr(item, "dtype", None) != "string":
        raise SystemExit(f"{name} is not Arrow-stable string payload")
print("formal_dataset_materialization=PASS public=2500 hidden=2500 test_payload=list<string>")
PY
then
  fail_preflight "formal GRPO trainer Dataset materialization failed"
fi

if ! "$PY" - >>"$LOG_FILE" <<'PY_RUNTIME'
from importlib import metadata

from accelerate.utils.modeling import is_peft_model

from code_verifier.training.grpo import _without_unconfigured_deepspeed_backend

try:
    deepspeed_version = metadata.version("deepspeed")
except metadata.PackageNotFoundError:
    raise SystemExit("pinned DeepSpeed runtime is missing") from None
if deepspeed_version != "0.16.8":
    raise SystemExit(f"pinned DeepSpeed runtime mismatch: {deepspeed_version}")
try:
    setuptools_version = metadata.version("setuptools")
except metadata.PackageNotFoundError:
    setuptools_version = None
with _without_unconfigured_deepspeed_backend():
    if is_peft_model(object()) is not False:
        raise SystemExit("guarded Accelerate PEFT probe returned an unexpected value")
print(f"guarded_accelerate_peft_probe=PASS deepspeed={deepspeed_version} setuptools={setuptools_version}")
PY_RUNTIME
then
  fail_preflight "guarded Accelerate/DeepSpeed compatibility probe failed"
fi

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

if ! "$PY" - "$ARTIFACT_ROOT" >>"$LOG_FILE" <<'PY'
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
printf '[%s] preflight PASS: provenance/machine/GPU/frozen-runtime/offline-model/data/B/pair/Piston/storage\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"

recover_c2_failure() {
  "$PY" - "$PUBLIC_RUN" "$HIDDEN_RUN" "$C2_QUARANTINE_DIR" "$C2_QUARANTINE_MANIFEST" "$C2_FAILED_PUBLIC_RUN_SHA" "$C2_FAILED_STDERR_SHA" "$C2_CHECKPOINT_COMMIT" <<'PY'
import hashlib
import json
import math
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
hidden = Path(sys.argv[2])
destination = Path(sys.argv[3])
manifest = Path(sys.argv[4])
expected_run_sha, expected_stderr_sha, expected_commit = sys.argv[5:8]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_failed_run(path: Path) -> list[dict[str, object]]:
    if not path.is_dir() or path.is_symlink():
        raise SystemExit("known C2 failed Public run path is not a plain directory")
    expected_entries = {
        "checkpoints",
        "environment.json",
        "group_metrics.jsonl",
        "metrics.jsonl",
        "resolved_config.yaml",
        "rewards.jsonl",
        "rollouts.jsonl",
        "run.json",
        "stderr.log",
        "stdout.log",
    }
    if {item.name for item in path.iterdir()} != expected_entries:
        raise SystemExit("known C2 failed Public run inventory changed")
    if any(item.is_symlink() for item in path.iterdir()):
        raise SystemExit("known C2 failed Public run contains a symlink")
    run_json = path / "run.json"
    if digest(run_json) != expected_run_sha:
        raise SystemExit("known C2 failed Public run.json SHA changed")
    metadata = json.loads(run_json.read_text(encoding="utf-8"))
    expected_metadata = {
        "status": "failed",
        "run_id": "C-public-grpo-smoke20-seed42",
        "reward_mode": "public",
        "git_commit": expected_commit,
        "global_step": None,
        "peak_cuda_memory_allocated_bytes": 0,
        "peak_cuda_memory_reserved_bytes": 0,
    }
    if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise SystemExit("known C2 failed Public run metadata changed")
    attempts = metadata.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 1 or not isinstance(attempts[0], dict):
        raise SystemExit("known C2 failed Public attempt history changed")
    attempt = attempts[0]
    if attempt.get("attempt") != 1 or attempt.get("status") != "failed" or attempt.get("resume_from_checkpoint") is not None:
        raise SystemExit("known C2 failed Public attempt identity changed")
    hours = attempt.get("gpu_hours")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(float(hours)) or float(hours) < 0:
        raise SystemExit("known C2 failed Public attempt gpu_hours invalid")
    checkpoints = path / "checkpoints"
    if not checkpoints.is_dir() or checkpoints.is_symlink() or any(checkpoints.iterdir()):
        raise SystemExit("known C2 failure unexpectedly contains a Trainer checkpoint")
    for name in ("metrics.jsonl", "rollouts.jsonl", "rewards.jsonl", "group_metrics.jsonl", "stdout.log"):
        item = path / name
        if not item.is_file() or item.is_symlink() or item.stat().st_size != 0:
            raise SystemExit(f"known C2 failure {name} is no longer empty")
    stderr = path / "stderr.log"
    if not stderr.is_file() or stderr.is_symlink() or digest(stderr) != expected_stderr_sha:
        raise SystemExit("known C2 failure stderr identity changed")
    if hidden.exists():
        raise SystemExit("C2 unexpectedly created a Hidden run; automatic quarantine is unsafe")
    inventory: list[dict[str, object]] = []
    files = sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: str(item.relative_to(path)))
    for item in files:
        if item.is_symlink():
            raise SystemExit("known C2 failed Public run contains a nested symlink")
        inventory.append(
            {
                "path": str(item.relative_to(path)),
                "size_bytes": item.stat().st_size,
                "sha256": digest(item),
            }
        )
    return inventory


def manifest_payload(inventory: list[dict[str, object]]) -> dict[str, object]:
    return {
        "version": 1,
        "stage_id": "WP7-c",
        "source_checkpoint_id": "C2",
        "source_checkpoint_commit": expected_commit,
        "source_run_json_sha256": expected_run_sha,
        "reason": "ArrowInvalid during GRPO Dataset.from_list before Trainer/model initialization",
        "quarantined_run": str(destination),
        "inventory": inventory,
    }


def write_manifest(inventory: list[dict[str, object]]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest_payload(inventory)
    temp = manifest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, manifest)


def validate_manifest(inventory: list[dict[str, object]]) -> None:
    if not manifest.is_file() or manifest.is_symlink():
        raise SystemExit("C2 quarantine manifest is unavailable or invalid")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("C2 quarantine manifest is unreadable") from None
    if value != manifest_payload(inventory):
        raise SystemExit("C2 quarantine manifest does not match quarantined run inventory")


if source.exists():
    run_json = source / "run.json"
    if not run_json.is_file() or digest(run_json) != expected_run_sha:
        print("unrelated-existing-run")
        raise SystemExit(0)
    if destination.exists() or manifest.exists():
        raise SystemExit("canonical C2 failure conflicts with existing quarantine state")
    inventory = validate_failed_run(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    write_manifest(inventory)
    validate_manifest(inventory)
    print("quarantined-c2-arrow-failure")
elif destination.exists():
    inventory = validate_failed_run(destination)
    if not manifest.exists():
        write_manifest(inventory)
    validate_manifest(inventory)
    print("already-quarantined-c2-arrow-failure")
elif manifest.exists():
    raise SystemExit("C2 quarantine manifest exists without quarantined run")
else:
    print("no-c2-failure-present")
PY
}

CURRENT_PHASE="recover-c2"
if ! RECOVERY_ACTION="$(recover_c2_failure)"; then
  fail_preflight "C2 failed Public run cannot be safely quarantined"
fi
printf '[%s] recovery action=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RECOVERY_ACTION" >>"$LOG_FILE"
CURRENT_PHASE="preflight"

recover_c3_failure() {
  "$PY" - "$PUBLIC_RUN" "$HIDDEN_RUN" "$C3_QUARANTINE_DIR" "$C3_QUARANTINE_MANIFEST" \
    "$C3_FAILED_STDERR_SHA" "$C3_CHECKPOINT_COMMIT" "$C3_RESULT_CODE_COMMIT" "$EXPECTED_PAIR_SHA" \
    "$C3_EVIDENCE_FILE" "$C3_STATUS_FILE" "$C3_LOG_FILE" <<'PY_C3'
import hashlib
import json
import math
import os
import sys
from pathlib import Path

(
    source_text,
    hidden_text,
    destination_text,
    manifest_text,
    expected_stderr_sha,
    expected_checkpoint_commit,
    expected_result_code_commit,
    expected_pair_sha,
    evidence_text,
    status_text,
    log_text,
) = sys.argv[1:]
source = Path(source_text)
hidden = Path(hidden_text)
destination = Path(destination_text)
manifest = Path(manifest_text)
evidence_path = Path(evidence_text)
status_path = Path(status_text)
log_path = Path(log_text)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_operator_evidence() -> dict[str, str]:
    for path, label in ((evidence_path, "evidence"), (status_path, "status"), (log_path, "terminal log")):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"C3 operator {label} is unavailable or invalid")
    if status_path.read_text(encoding="utf-8").strip() != "1":
        raise SystemExit("C3 operator status is not the expected command failure rc=1")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("C3 operator evidence is unreadable") from None
    expected = {
        "version": 1,
        "checkpoint_id": "C3",
        "operator_checkpoint_commit": expected_checkpoint_commit,
        "result_code_commit": expected_result_code_commit,
        "operator_gate_id": "grpo-cd-smoke",
        "source_plan_commit": "8464e69691c527c726a2e28e5a7ca81fa2001bbf",
        "command_rc": 1,
        "postcheck_rc": 125,
        "gate_status": "command_failed",
        "note": "public smoke train-grpo exited nonzero",
    }
    if not isinstance(evidence, dict) or any(evidence.get(key) != value for key, value in expected.items()):
        raise SystemExit("C3 operator evidence identity changed")
    formal_pair = evidence.get("formal_pair")
    if not isinstance(formal_pair, dict) or formal_pair.get("paired_definition_sha256") != expected_pair_sha:
        raise SystemExit("C3 operator evidence paired definition changed")
    terminal = log_path.read_text(encoding="utf-8")
    required_fragments = (
        "preflight PASS: provenance/machine/GPU/frozen-runtime/offline-model/data/B/pair/Piston/storage",
        "public smoke fresh run=C-public-grpo-smoke20-seed42",
        "ModuleNotFoundError: No module named 'setuptools'",
        "end phase=train-public command_rc=1 postcheck_rc=125 gate_status=command_failed",
    )
    if any(fragment not in terminal for fragment in required_fragments):
        raise SystemExit("C3 terminal log does not prove the expected setuptools/DeepSpeed failure")
    return {
        "operator_evidence_sha256": digest(evidence_path),
        "operator_status_sha256": digest(status_path),
        "operator_terminal_log_sha256": digest(log_path),
    }


def validate_failed_run(path: Path) -> tuple[list[dict[str, object]], str]:
    if not path.is_dir() or path.is_symlink():
        raise SystemExit("known C3 failed Public run path is not a plain directory")
    expected_entries = {
        "checkpoints",
        "environment.json",
        "group_metrics.jsonl",
        "metrics.jsonl",
        "resolved_config.yaml",
        "rewards.jsonl",
        "rollouts.jsonl",
        "run.json",
        "stderr.log",
        "stdout.log",
    }
    entries = list(path.iterdir())
    if {item.name for item in entries} != expected_entries:
        raise SystemExit("known C3 failed Public run inventory changed")
    if any(item.is_symlink() for item in entries):
        raise SystemExit("known C3 failed Public run contains a symlink")
    run_json = path / "run.json"
    try:
        metadata = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("known C3 failed Public run.json is unreadable") from None
    expected_metadata = {
        "status": "failed",
        "run_id": "C-public-grpo-smoke20-seed42",
        "reward_mode": "public",
        "git_commit": expected_checkpoint_commit,
        "global_step": None,
        "dataset_hash": "94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223",
        "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
        "parent_sft_run_id": "B-sft-formal-seed42",
        "parent_sft_dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
        "paired_definition_sha256": expected_pair_sha,
    }
    if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise SystemExit("known C3 failed Public run metadata changed")
    attempts = metadata.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 1 or not isinstance(attempts[0], dict):
        raise SystemExit("known C3 failed Public attempt history changed")
    attempt = attempts[0]
    if attempt.get("attempt") != 1 or attempt.get("status") != "failed" or attempt.get("resume_from_checkpoint") is not None:
        raise SystemExit("known C3 failed Public attempt identity changed")
    hours = attempt.get("gpu_hours")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(float(hours)) or float(hours) < 0:
        raise SystemExit("known C3 failed Public attempt gpu_hours invalid")
    for field in ("peak_cuda_memory_allocated_bytes", "peak_cuda_memory_reserved_bytes"):
        value = metadata.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SystemExit(f"known C3 failure {field} must prove post-model CUDA allocation")
    checkpoints = path / "checkpoints"
    if not checkpoints.is_dir() or checkpoints.is_symlink() or any(checkpoints.iterdir()):
        raise SystemExit("known C3 failure unexpectedly contains a Trainer checkpoint")
    for name in ("metrics.jsonl", "rollouts.jsonl", "rewards.jsonl", "group_metrics.jsonl", "stdout.log"):
        item = path / name
        if not item.is_file() or item.is_symlink() or item.stat().st_size != 0:
            raise SystemExit(f"known C3 failure {name} is no longer empty")
    stderr = path / "stderr.log"
    if not stderr.is_file() or stderr.is_symlink() or digest(stderr) != expected_stderr_sha:
        raise SystemExit("known C3 failure stderr identity changed")
    if hidden.exists():
        raise SystemExit("C3 unexpectedly created a Hidden run; automatic quarantine is unsafe")
    inventory: list[dict[str, object]] = []
    files = sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: str(item.relative_to(path)))
    for item in files:
        if item.is_symlink():
            raise SystemExit("known C3 failed Public run contains a nested symlink")
        inventory.append(
            {
                "path": str(item.relative_to(path)),
                "size_bytes": item.stat().st_size,
                "sha256": digest(item),
            }
        )
    return inventory, digest(run_json)


def manifest_payload(
    inventory: list[dict[str, object]],
    run_json_sha: str,
    operator_identity: dict[str, str],
) -> dict[str, object]:
    return {
        "version": 1,
        "stage_id": "WP7-c",
        "source_checkpoint_id": "C3",
        "source_checkpoint_commit": expected_checkpoint_commit,
        "source_result_code_commit": expected_result_code_commit,
        "source_run_json_sha256": run_json_sha,
        "source_paired_definition_sha256": expected_pair_sha,
        "reason": "ModuleNotFoundError for setuptools during unused DeepSpeed probe in GRPOTrainer.__init__",
        "quarantined_run": str(destination),
        **operator_identity,
        "inventory": inventory,
    }


def write_manifest(
    inventory: list[dict[str, object]],
    run_json_sha: str,
    operator_identity: dict[str, str],
) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest_payload(inventory, run_json_sha, operator_identity)
    temp = manifest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, manifest)


def validate_manifest(
    inventory: list[dict[str, object]],
    run_json_sha: str,
    operator_identity: dict[str, str],
) -> None:
    if not manifest.is_file() or manifest.is_symlink():
        raise SystemExit("C3 quarantine manifest is unavailable or invalid")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("C3 quarantine manifest is unreadable") from None
    if value != manifest_payload(inventory, run_json_sha, operator_identity):
        raise SystemExit("C3 quarantine manifest does not match quarantined run/evidence inventory")


operator_identity = validate_operator_evidence()
existing_quarantine: tuple[list[dict[str, object]], str] | None = None
if destination.exists():
    existing_quarantine = validate_failed_run(destination)
    validate_manifest(existing_quarantine[0], existing_quarantine[1], operator_identity)
elif manifest.exists():
    raise SystemExit("C3 quarantine manifest exists without quarantined run")

if source.exists():
    run_json = source / "run.json"
    if not run_json.is_file():
        print("unrelated-existing-run")
        raise SystemExit(0)
    try:
        source_metadata = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("unrelated-existing-run")
        raise SystemExit(0)
    if not isinstance(source_metadata, dict) or source_metadata.get("git_commit") != expected_checkpoint_commit:
        print("unrelated-existing-run")
        raise SystemExit(0)
    if existing_quarantine is not None or manifest.exists():
        raise SystemExit("canonical C3 failure conflicts with existing quarantine state")
    inventory, run_json_sha = validate_failed_run(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    write_manifest(inventory, run_json_sha, operator_identity)
    validate_manifest(inventory, run_json_sha, operator_identity)
    print("quarantined-c3-deepspeed-setuptools-failure")
elif existing_quarantine is not None:
    print("already-quarantined-c3-deepspeed-setuptools-failure")
else:
    print("no-c3-failure-present")
PY_C3
}

CURRENT_PHASE="recover-c3"
if ! C3_RECOVERY_ACTION="$(recover_c3_failure)"; then
  fail_preflight "C3 failed Public run cannot be safely quarantined"
fi
printf '[%s] C3 recovery action=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$C3_RECOVERY_ACTION" >>"$LOG_FILE"
CURRENT_PHASE="preflight"

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
from code_verifier.training.grpo import (
    _config_hash,
    _file_hash,
    _paired_definition,
    _resolve_resume_checkpoint,
    _validate_resume_run,
    load_grpo_training_config,
)

repo, data_dir, b_run, run_dir = map(Path, sys.argv[1:5])
mode, head, expected_pair = sys.argv[5:8]
public = replace(
    load_grpo_training_config(repo / "configs/grpo/validation-smoke-public.yaml"),
    dataset_path=data_dir / "training/public_grpo.jsonl",
    run_name="C-public-grpo-smoke20-seed42",
)
hidden = replace(
    load_grpo_training_config(repo / "configs/grpo/validation-smoke-hidden.yaml"),
    dataset_path=data_dir / "training/hidden_grpo.jsonl",
    run_name="D-hidden-grpo-smoke20-seed42",
)
config = public if mode == "public" else hidden
parent = load_completed_sft_checkpoint(b_run)
pair_sha, components = _paired_definition(public, hidden, seed=42, parent_sft=parent)
if pair_sha != expected_pair:
    raise SystemExit("pair SHA changed after preflight")
if not run_dir.exists():
    print("fresh")
    raise SystemExit(0)
if not run_dir.is_dir() or run_dir.is_symlink() or not (run_dir / "run.json").is_file():
    raise SystemExit("existing run path is invalid")
metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
if not isinstance(metadata, dict) or metadata.get("git_commit") != head:
    raise SystemExit("existing run belongs to a different checkpoint commit")
if metadata.get("status") == "completed":
    identity = load_completed_grpo_checkpoint(run_dir)
    if identity.run_id != config.run_name or identity.reward_mode != mode or identity.parent_sft != parent or identity.paired_definition_sha256 != expected_pair:
        raise SystemExit("completed run identity mismatch")
    print("completed")
    raise SystemExit(0)
if metadata.get("status") not in {"running", "failed"}:
    raise SystemExit("existing run status is not resumable")
checkpoint_root = run_dir / "checkpoints"
if not checkpoint_root.is_dir() or checkpoint_root.is_symlink():
    raise SystemExit("existing run checkpoint root is invalid")
required = {
    "adapter_config.json", "adapter_model.safetensors", "optimizer.pt", "scheduler.pt",
    "rng_state.pth", "trainer_state.json", "training_args.bin",
}
valid = []
for path in checkpoint_root.glob("checkpoint-*"):
    match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", path.name)
    if not match or not path.is_dir() or path.is_symlink():
        continue
    files = [path / name for name in required]
    if any(not item.is_file() or item.is_symlink() or item.stat().st_size <= 0 for item in files):
        continue
    step = int(match.group(1))
    if step > config.max_steps or step % config.save_steps != 0:
        continue
    try:
        state = json.loads((path / "trainer_state.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        continue
    if isinstance(state, dict) and state.get("global_step") == step:
        valid.append((step, path))
if not valid:
    raise SystemExit("incomplete run has no valid Trainer checkpoint; quarantine is required")
_, selected = max(valid)
resolved, source = _resolve_resume_checkpoint(run_dir, selected)
before = (run_dir / "run.json").read_bytes()
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
if before != (run_dir / "run.json").read_bytes():
    raise SystemExit("resume identity validation must be read-only before attempt begin")
print(f"resume:{resolved}")
PY
}

run_one() {
  local mode="$1" run_name="$2" run_dir="$3" action
  if ! action="$(resolve_run_action "$mode" "$run_dir")"; then
    write_evidence 125 125 identity_failed "$mode run is not safely fresh/resumable/completed"
    exit $?
  fi
  if [[ "$action" == "completed" ]]; then
    printf '[%s] %s smoke already completed; command skipped\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" >>"$LOG_FILE"
    return 0
  fi
  local resume_args=()
  if [[ "$action" == resume:* ]]; then
    resume_args=(--resume-from-checkpoint "${action#resume:}")
    printf '[%s] %s smoke resume=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "${action#resume:}" >>"$LOG_FILE"
  elif [[ "$action" == "fresh" ]]; then
    printf '[%s] %s smoke fresh run=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" "$run_name" >>"$LOG_FILE"
  else
    write_evidence 125 125 identity_failed "$mode run action is invalid"
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
if "$PY" - "$PUBLIC_RUN" "$HIDDEN_RUN" "$B_RUN" "$HEAD_COMMIT" "$EXPECTED_PAIR_SHA" "$PAIR_COMPONENTS_JSON" "$CURRENT_OPEN_R1" "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$GPU_NAME" "$POSTCHECK_FILE.tmp" <<'PY'
import json
import math
import sys
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
forbidden = (
    '"prompt"', '"visible_tests"', '"train_hidden_tests"', '"eval_hidden_tests"',
    '"reference_solution"', '"starter_code"', '"sft_response"',
)


def load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise SystemExit(f"blank JSONL row: {path.name}")
        value = json.loads(line, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
        if not isinstance(value, dict):
            raise SystemExit(f"non-object JSONL row: {path.name}")
        rows.append(value)
    return rows


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
    required = {
        "adapter_config.json", "adapter_model.safetensors", "optimizer.pt", "scheduler.pt",
        "rng_state.pth", "trainer_state.json", "training_args.bin",
    }
    inventory = []
    for step in (10, 20):
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
        "status": "completed",
        "run_id": run_id,
        "reward_mode": mode,
        "paired_definition_sha256": pair_sha,
        "seed": 42,
        "git_commit": head,
        "open_r1_commit": open_r1,
        "dependency_lock_hash": lock_sha,
        "torch_version": torch_version,
        "cuda_version": cuda_version,
        "gpu_name": gpu_name,
        "gpu_count_used": 1,
        "global_step": 20,
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
        if not isinstance(attempt, dict) or attempt.get("attempt") != index:
            raise SystemExit(f"{mode} attempt schema invalid")
        status = attempt.get("status")
        if status not in {"running", "failed", "completed"}:
            raise SystemExit(f"{mode} attempt status invalid")
        hours = attempt.get("gpu_hours")
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(float(hours)) or hours < 0:
            raise SystemExit(f"{mode} attempt gpu_hours invalid")
        if status == "running" and float(hours) != 0.0:
            raise SystemExit(f"{mode} interrupted running attempt must retain zero recorded gpu_hours")
        attempt_total += float(hours)
    gpu_hours = metadata.get("gpu_hours")
    if attempts[-1].get("status") != "completed" or isinstance(gpu_hours, bool) or not isinstance(gpu_hours, (int, float)):
        raise SystemExit(f"{mode} cumulative gpu_hours invalid")
    if not math.isfinite(float(gpu_hours)) or float(gpu_hours) <= 0 or not math.isclose(float(gpu_hours), attempt_total, rel_tol=0.0, abs_tol=1e-12):
        raise SystemExit(f"{mode} cumulative gpu_hours is not recomputable")
    for key in ("peak_cuda_memory_allocated_bytes", "peak_cuda_memory_reserved_bytes"):
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
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
    group_fields = {"group_index", "problem_id", "reward_mode", "sample_count", "mean", "std", "all_equal"}
    if any(set(row) != group_fields or row.get("reward_mode") != mode or row.get("sample_count") != 4 for row in groups):
        raise SystemExit(f"{mode} group schema/source mismatch")
    if len(rollouts) != len(rewards):
        raise SystemExit(f"{mode} rollout/reward row count mismatch")
    if any(row.get("infrastructure_failure") is not False for row in rewards):
        raise SystemExit(f"{mode} reward path contains infrastructure failures")
    if not any(row.get("executed") is True for row in rewards):
        raise SystemExit(f"{mode} reward path contains no real executed completion")
    require_finite(rewards, f"{mode} rewards")
    require_finite(groups, f"{mode} groups")

    for name in (
        "run.json", "resolved_config.yaml", "environment.json", "metrics.jsonl",
        "rewards.jsonl", "group_metrics.jsonl", "stdout.log", "stderr.log",
    ):
        text = (run_dir / name).read_text(encoding="utf-8")
        if any(marker in text for marker in forbidden):
            raise SystemExit(f"{mode} forbidden payload marker in {name}")
    if any(any(key in row for key in ("prompt", "visible_tests", "train_hidden_tests", "eval_hidden_tests")) for row in rollouts):
        raise SystemExit(f"{mode} rollout contains forbidden payload")

    curve = load_training_curve_rows(run_dir, method=f"{mode}-smoke")
    cost = build_cost_row(run_dir, method=f"{mode}-smoke", gpu_hour_cost_usd=None)
    if not curve or not math.isfinite(cost.gpu_hours) or cost.gpu_hours <= 0:
        raise SystemExit(f"{mode} curve/cost loader failed")
    if not isinstance(cost.generated_tokens, int) or cost.generated_tokens <= 0:
        raise SystemExit(f"{mode} generated token count is empty")
    inventory = checkpoint_inventory(run_dir)
    return {
        "run_id": run_id,
        "reward_mode": mode,
        "paired_definition_sha256": pair_sha,
        "parent_sft_run_id": identity.parent_sft.run_id,
        "global_step": 20,
        "gpu_hours": float(gpu_hours),
        "attempt_count": len(attempts),
        "peak_cuda_memory_allocated_bytes": metadata["peak_cuda_memory_allocated_bytes"],
        "peak_cuda_memory_reserved_bytes": metadata["peak_cuda_memory_reserved_bytes"],
        "trainer_metric_rows": len(trainer_rows),
        "curve_rows": len(curve),
        "rollout_rows": len(rollouts),
        "reward_rows": len(rewards),
        "group_rows": len(groups),
        "executor_hours": cost.executor_hours,
        **inventory,
    }


public = check_run(public_run, "public", "C-public-grpo-smoke20-seed42")
hidden = check_run(hidden_run, "hidden", "D-hidden-grpo-smoke20-seed42")
summary = {
    "version": 1,
    "status": "passed",
    "paired_definition_sha256": pair_sha,
    "public": public,
    "hidden": hidden,
    "max_complete_trainer_checkpoint_bytes": max(public["max_checkpoint_bytes"], hidden["max_checkpoint_bytes"]),
    "max_complete_trainer_checkpoint_inodes": max(public["max_checkpoint_inodes"], hidden["max_checkpoint_inodes"]),
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
