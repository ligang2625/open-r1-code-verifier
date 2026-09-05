#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-c"
GATE_ID="wp9c-fresh-reduced-calibration-generation"
CHECKPOINT_ID="C25"
EXPECTED_PROBLEMS=1602
EXPECTED_RECORDS=12816
PROBLEM_BATCH_SIZE=4
MIN_FREE_GIB=20
MIN_FREE_INODES=100000
B_RUN_NAME="B-sft-formal-seed42"

SCRIPT_REL="ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/run.sh"
CHECKPOINT_REL="ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/checkpoint.json"
RUNNER_REL="ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/run_fresh_generation.py"
PREP_REL="ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/prepare_input_bundle.py"
CONFIG_REL="configs/grpo/wp9c-reduced-fresh-calibration.yaml"
C24_REL="ai-work/executor/operator/WP9-c/wp9c-final-reduced-pool/C24/checkpoint.json"
SYNC_MANIFEST_REL="ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/input-sync-manifest.json"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "target checkout .venv Python is unavailable" >&2; exit 125; }

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

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

path = Path(sys.argv[1])
try:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
    raise SystemExit(f"validation machine pointer is not strict JSON: {type(error).__name__}") from None
required = {
    "version", "machine_status", "bootstrap_project_commit", "open_r1_commit",
    "artifact_root", "hf_home", "formal_data_root", "readiness_record",
}
if not isinstance(value, dict) or not required.issubset(value):
    raise SystemExit("validation machine pointer schema is incomplete")
if value["version"] != 1 or value["machine_status"] != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine is not READY_FOR_VALIDATION_PLANNER")
for key in ("artifact_root", "hf_home", "formal_data_root", "readiness_record"):
    item = value[key]
    if not isinstance(item, str) or not Path(item).is_absolute() or any(ch in item for ch in "\t\r\n"):
        raise SystemExit(f"validation machine {key} must be an absolute control-free path")
for key in ("artifact_root", "hf_home", "formal_data_root"):
    resolved = Path(value[key]).resolve()
    if resolved != Path("/root") and Path("/root") not in resolved.parents:
        raise SystemExit(f"validation machine {key} resolves outside /root: {resolved}")
    if resolved == Path("/data") or Path("/data") in resolved.parents:
        raise SystemExit(f"validation machine {key} resolves under retired /data: {resolved}")
    value[key] = str(resolved)
for key in ("bootstrap_project_commit", "open_r1_commit"):
    item = value[key]
    if not isinstance(item, str) or len(item) != 40 or any(ch not in "0123456789abcdef" for ch in item):
        raise SystemExit(f"validation machine {key} must be exact lowercase 40-hex")
print("\t".join(str(value[key]) for key in (
    "bootstrap_project_commit", "open_r1_commit", "artifact_root", "hf_home", "formal_data_root", "readiness_record",
)))
PY_MACHINE
)" || { echo "validation machine pointer validation failed" >&2; exit 125; }
TAB="$(printf '\t')"
IFS="$TAB" read -r BOOTSTRAP_COMMIT MACHINE_OPEN_R1 ARTIFACT_ROOT TARGET_HF_HOME FORMAL_DATA_ROOT READINESS_RECORD <<<"$MACHINE_FIELDS"

for root in "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT"; do
  [[ "$root" == /root || "$root" == /root/* ]] || { echo "active WP9 target root must be under /root: $root" >&2; exit 125; }
  [[ "$root" != /data && "$root" != /data/* ]] || { echo "retired /data root must not be active: $root" >&2; exit 125; }
done
[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" ]] || { echo "artifact_root is unavailable or not writable" >&2; exit 125; }
[[ -d "$TARGET_HF_HOME" && -r "$TARGET_HF_HOME" ]] || { echo "hf_home is unavailable or not readable" >&2; exit 125; }
[[ -d "$FORMAL_DATA_ROOT" && -r "$FORMAL_DATA_ROOT" ]] || { echo "formal_data_root is unavailable or not readable" >&2; exit 125; }
[[ -f "$READINESS_RECORD" ]] || { echo "target readiness record is unavailable" >&2; exit 125; }
[[ -d /root/tmp && -w /root/tmp ]] || { echo "/root/tmp is unavailable or not writable" >&2; exit 125; }

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$TARGET_HF_HOME"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export TMPDIR="/root/tmp"

INPUT_DIR="$FORMAL_DATA_ROOT/wp9c/fresh-calibration-input-C25"
B_RUN="$ARTIFACT_ROOT/sft/$B_RUN_NAME"
OUTPUT_DIR="$ARTIFACT_ROOT/wp9c/calibration/fresh-reduced-C25"
GATE_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$GATE_ID"
OP_ROOT="$GATE_ROOT/$CHECKPOINT_ID"
LOCK_FILE="$GATE_ROOT/run.lock"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
POSTCHECK_FILE="$OP_ROOT/postcheck-summary.json"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"

mkdir -p "$OP_ROOT"
[[ -d /root/tmp && -w /root/tmp ]] || { echo "/root/tmp is unavailable or not writable" >&2; exit 125; }
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "C25 operator lock is already held: $LOCK_FILE" >&2
  exit 73
fi

ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-${BASHPID}"
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
[[ ! -f "$STATUS_FILE" ]] || mv "$STATUS_FILE" "$OP_ROOT/status.before-$ATTEMPT_ID"
[[ ! -f "$POSTCHECK_FILE" ]] || mv "$POSTCHECK_FILE" "$OP_ROOT/postcheck-summary.before-$ATTEMPT_ID.json"
[[ ! -f "$EVIDENCE_FILE" ]] || mv "$EVIDENCE_FILE" "$OP_ROOT/operator-evidence.before-$ATTEMPT_ID.json"
rm -f "$STATUS_FILE.tmp" "$POSTCHECK_FILE.tmp" "$EVIDENCE_FILE.tmp"
printf '[%s] attempt=%s start gate=%s checkpoint=%s\n' "$START_TIME" "$ATTEMPT_ID" "$GATE_ID" "$CHECKPOINT_ID" >>"$LOG_FILE"

HEAD_COMMIT=""
SCRIPT_SHA=""
CHECKPOINT_SHA=""
READINESS_SHA=""
GPU_NAME=""
GPU_VRAM_MIB="0"
GPU_FREE_MIB="0"
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
  [[ -n "$CHECKPOINT_SHA" ]] || CHECKPOINT_SHA="$(sha256sum "$REPO_ROOT/$CHECKPOINT_REL" 2>/dev/null | awk '{print $1}' || true)"
  "$PY" - "$EVIDENCE_FILE.tmp" "$POSTCHECK_FILE" "$HEAD_COMMIT" "$SCRIPT_SHA" "$CHECKPOINT_SHA" \
    "$MACHINE_SHA" "$READINESS_SHA" "$GPU_NAME" "$GPU_VRAM_MIB" "$GPU_FREE_MIB" "$CURRENT_OPEN_R1" \
    "$CURRENT_LOCK_SHA" "$CURRENT_TORCH" "$CURRENT_CUDA" "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT" \
    "$INPUT_DIR" "$B_RUN" "$OUTPUT_DIR" "$OUTPUT_ACTION" "$command_rc" "$postcheck_rc" "$gate_status" "$note" \
    "$START_TIME" "$end_time" "$ATTEMPT_ID" <<'PY_EVIDENCE'
import hashlib
import json
import sys
from pathlib import Path
(
    out, postcheck_path, head, script_sha, checkpoint_sha, machine_sha, readiness_sha,
    gpu_name, gpu_vram, gpu_free, open_r1, lock_sha, torch_version, cuda_version,
    artifact_root, hf_home, formal_data_root, input_dir, b_run, output_dir, action,
    command_rc, postcheck_rc, gate_status, note, start_time, end_time, attempt_id,
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
    "checkpoint_id": "C25",
    "operator_gate_id": "wp9c-fresh-reduced-calibration-generation",
    "operator_checkpoint_commit": head or None,
    "operator_script": "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/run.sh",
    "operator_script_sha256": script_sha or None,
    "checkpoint_metadata_sha256": checkpoint_sha or None,
    "target_machine_record_sha256": machine_sha or None,
    "target_readiness_record_sha256": readiness_sha or None,
    "gpu_name": gpu_name or None,
    "gpu_vram_mib": int(gpu_vram) if gpu_vram.isdigit() else None,
    "gpu_free_mib_at_preflight": int(gpu_free) if gpu_free.isdigit() else None,
    "resolved_roots": {"artifact_root": artifact_root, "hf_home": hf_home, "formal_data_root": formal_data_root},
    "runtime_identity": {
        "open_r1_commit": open_r1 or None,
        "dependency_lock_hash": lock_sha or None,
        "torch_version": torch_version or None,
        "cuda_version": cuda_version or None,
    },
    "input_bundle": input_dir,
    "formal_b_run": b_run,
    "generation_output": output_dir,
    "generation_action": action,
    "problem_batch_size": 4,
    "expected_problem_count": 1602,
    "expected_record_count": 12816,
    "postcheck": postcheck,
    "artifact_inventory": [
        inventory(Path(input_dir) / "input_manifest.json"),
        inventory(Path(input_dir) / "inputs.jsonl"),
        inventory(Path(output_dir) / "run.json"),
        inventory(Path(output_dir) / "samples" / "generations.jsonl"),
        inventory(Path(output_dir) / "samples" / "progress.json"),
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
Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
  printf '[%s] attempt=%s end phase=%s command_rc=%s postcheck_rc=%s status=%s note=%s\n' \
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
[[ "$EXPECTED_HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail_preflight "set WP9C_HANDOFF_COMMIT to the exact 40-hex C25 handoff commit"
HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve target HEAD"
[[ "$HEAD_COMMIT" == "$EXPECTED_HANDOFF_COMMIT" ]] || fail_preflight "target HEAD does not equal WP9C_HANDOFF_COMMIT"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --ignore-submodules=none)" ]] || fail_preflight "target checkout is not clean"
[[ -z "$(git -C "$REPO_ROOT" ls-files .ai-bridge)" ]] || fail_preflight ".ai-bridge must remain untracked"
git -C "$REPO_ROOT" merge-base --is-ancestor "$BOOTSTRAP_COMMIT" "$HEAD_COMMIT" || fail_preflight "validation-machine bootstrap commit is not an ancestor of target HEAD"

if ! "$PY" - "$REPO_ROOT" "$HEAD_COMMIT" "$SCRIPT_REL" "$CHECKPOINT_REL" "$RUNNER_REL" "$CONFIG_REL" "$SYNC_MANIFEST_REL" <<'PY_TRACKED'
import subprocess
import sys
from pathlib import Path
repo = Path(sys.argv[1])
head = sys.argv[2]
items = sys.argv[3:]
for index, relative in enumerate(items):
    line = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", head, "--", relative],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    required_mode = "100755 " if index == 0 else "100644 "
    if not line.startswith(required_mode):
        raise SystemExit(f"tracked handoff file has wrong mode or is missing: {relative}")
PY_TRACKED
then
  fail_preflight "tracked C25 handoff files are missing or have invalid modes"
fi

SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
CHECKPOINT_SHA="$(sha256sum "$REPO_ROOT/$CHECKPOINT_REL" | awk '{print $1}')"
if ! "$PY" - "$REPO_ROOT/$CHECKPOINT_REL" "$SCRIPT_SHA" "$REPO_ROOT" <<'PY_CHECKPOINT'
import hashlib
import json
import sys
from pathlib import Path
checkpoint_path = Path(sys.argv[1])
script_sha = sys.argv[2]
root = Path(sys.argv[3])
value = json.loads(checkpoint_path.read_text(encoding="utf-8"))
expected = {
    "version": 1,
    "stage_id": "WP9-c",
    "checkpoint_id": "C25",
    "operator_gate_id": "wp9c-fresh-reduced-calibration-generation",
    "operator_handoff_mode": "portable_target",
    "operator_restart_policy": "exact_prefix_resume_or_strict_completed",
    "status": "awaiting_operator",
    "expected_problem_count": 1602,
    "expected_record_count": 12816,
    "problem_batch_size": 4,
}
for key, item in expected.items():
    if value.get(key) != item:
        raise SystemExit(f"C25 checkpoint metadata mismatch: {key}")
bindings = value.get("bindings")
paths = value.get("paths")
if not isinstance(bindings, dict) or not isinstance(paths, dict):
    raise SystemExit("C25 checkpoint paths/bindings are invalid")
if bindings.get("shell_runner_sha256") != script_sha:
    raise SystemExit("C25 tracked run.sh SHA does not match checkpoint")
def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
checks = (
    (root / paths["config"], "config_sha256"),
    (root / paths["preparation_script"], "preparation_script_sha256"),
    (root / paths["runner"], "runner_sha256"),
    (root / paths["c24_checkpoint"], "c24_checkpoint_sha256"),
    (root / paths["input_sync_manifest"], "input_sync_manifest_sha256"),
)
for path, key in checks:
    if not path.is_file() or digest(path) != bindings.get(key):
        raise SystemExit(f"C25 tracked binding mismatch: {key}")
PY_CHECKPOINT
then
  fail_preflight "C25 checkpoint/tracked binding validation failed"
fi

for root in "$ARTIFACT_ROOT" "$TARGET_HF_HOME" "$FORMAL_DATA_ROOT"; do
  [[ "$root" == /root || "$root" == /root/* ]] || fail_preflight "active WP9 target root must be under /root: $root"
  [[ "$root" != /data && "$root" != /data/* ]] || fail_preflight "retired /data root must not be active: $root"
done
[[ -d "$ARTIFACT_ROOT" && -w "$ARTIFACT_ROOT" ]] || fail_preflight "artifact_root is unavailable or not writable"
[[ -d "$TARGET_HF_HOME" && -r "$TARGET_HF_HOME" ]] || fail_preflight "hf_home is unavailable or not readable"
[[ -d "$FORMAL_DATA_ROOT" && -r "$FORMAL_DATA_ROOT" ]] || fail_preflight "formal_data_root is unavailable or not readable"
[[ -f "$READINESS_RECORD" ]] || fail_preflight "target readiness record is unavailable"
READINESS_SHA="$(sha256sum "$READINESS_RECORD" | awk '{print $1}')"

if ! "$PY" - "$ARTIFACT_ROOT" "$MIN_FREE_GIB" "$MIN_FREE_INODES" <<'PY_STORAGE'
import os
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1])
minimum_bytes = int(sys.argv[2]) * 1024**3
minimum_inodes = int(sys.argv[3])
usage = shutil.disk_usage(root)
stat = os.statvfs(root)
if usage.free < minimum_bytes:
    raise SystemExit(f"C25 requires at least {minimum_bytes} free bytes; found {usage.free}")
if stat.f_favail < minimum_inodes:
    raise SystemExit(f"C25 requires at least {minimum_inodes} free inodes; found {stat.f_favail}")
print(f"storage_free_bytes={usage.free} storage_free_inodes={stat.f_favail}")
PY_STORAGE
then
  fail_preflight "C25 storage gate failed"
fi

[[ -d "$INPUT_DIR" ]] || fail_preflight "C25 target input bundle is missing: $INPUT_DIR"
[[ -d "$B_RUN" ]] || fail_preflight "frozen B run is missing: $B_RUN"
if ! "$PY" - "$REPO_ROOT/$CHECKPOINT_REL" "$REPO_ROOT/$SYNC_MANIFEST_REL" "$INPUT_DIR" "$B_RUN" <<'PY_INPUT_B'
import hashlib
import json
import sys
from pathlib import Path
from code_verifier.training.calibration import _load_input_bundle, _sft_identity
from code_verifier.training.sft import load_completed_sft_checkpoint
checkpoint = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sync_manifest = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
input_dir = Path(sys.argv[3])
b_run = Path(sys.argv[4])
bindings = checkpoint["bindings"]
def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
if sync_manifest.get("version") != 1 or sync_manifest.get("stage_id") != "WP9-c" or sync_manifest.get("checkpoint_id") != "C25":
    raise SystemExit("C25 input sync manifest identity mismatch")
if sync_manifest.get("problem_count") != 1602 or sync_manifest.get("expected_total_bytes") != 2574292:
    raise SystemExit("C25 input sync manifest count/size mismatch")
files = sync_manifest.get("files")
if not isinstance(files, list) or len(files) != 6:
    raise SystemExit("C25 input sync manifest file list mismatch")
seen_bytes = 0
for item in files:
    if not isinstance(item, dict):
        raise SystemExit("C25 input sync manifest row is invalid")
    relative = item.get("path")
    expected_size = item.get("size_bytes")
    expected_sha = item.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected_size, int) or not isinstance(expected_sha, str):
        raise SystemExit("C25 input sync manifest row fields are invalid")
    path = input_dir / relative
    if not path.is_file() or path.stat().st_size != expected_size or digest(path) != expected_sha:
        raise SystemExit(f"C25 target input transfer mismatch: {relative}")
    seen_bytes += expected_size
if seen_bytes != sync_manifest["expected_total_bytes"]:
    raise SystemExit("C25 target input transfer total-byte mismatch")
if (input_dir / "report.sha256").read_text(encoding="utf-8").strip() != sync_manifest.get("report_sidecar_value"):
    raise SystemExit("C25 target input report sidecar mismatch")
if digest(input_dir / "input_manifest.json") != bindings["input_manifest_sha256"]:
    raise SystemExit("C25 target input manifest SHA mismatch")
if digest(input_dir / "inputs.jsonl") != bindings["inputs_sha256"]:
    raise SystemExit("C25 target input records SHA mismatch")
manifest, records = _load_input_bundle(input_dir)
if len(records) != 1602 or manifest.get("seed") != 42:
    raise SystemExit("C25 target input count/seed mismatch")
if any(item.quality_gate_required or item.overlap_origin != "external_new" for item in records):
    raise SystemExit("C25 target input is not external-new-only and quality-safe")
if manifest.get("context_filter", {}).get("max_prompt_tokens") != 2048:
    raise SystemExit("C25 target input context contract mismatch")
identity = _sft_identity(load_completed_sft_checkpoint(b_run))
if identity != checkpoint.get("sft_identity"):
    raise SystemExit("C25 frozen B identity mismatch")
print(f"input_records={len(records)} problem_order_sha256={manifest.get('problem_order_sha256')} sync_bytes={seen_bytes}")
PY_INPUT_B
then
  fail_preflight "C25 input/B strict validation failed"
fi

OUTPUT_ACTION="$($PY - "$REPO_ROOT/$CHECKPOINT_REL" "$OUTPUT_DIR" "$INPUT_DIR" <<'PY_RESUME'
import json
import sys
from pathlib import Path
from code_verifier.training.calibration import (
    _load_input_bundle,
    _load_running_calibration_generation_prefix,
    load_completed_calibration_generation,
)
checkpoint = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
output = Path(sys.argv[2])
input_dir = Path(sys.argv[3])
input_manifest, inputs = _load_input_bundle(input_dir)
if not output.exists():
    print("fresh")
    raise SystemExit(0)
run_path = output / "run.json"
if not run_path.is_file():
    raise SystemExit("existing C25 output lacks run.json")
run = json.loads(run_path.read_text(encoding="utf-8"))
expected = {
    "schema_version": "wp9b-calibration-v1",
    "block_index": 0,
    "samples_per_problem": 8,
    "problem_batch_size": 4,
    "input_manifest_sha256": checkpoint["bindings"]["input_manifest_sha256"],
    "input_records_sha256": checkpoint["bindings"]["inputs_sha256"],
    "problem_order_sha256": input_manifest["problem_order_sha256"],
    "retry_manifest_sha256": None,
    "sft_checkpoint": checkpoint["sft_identity"],
}
for key, value in expected.items():
    if run.get(key) != value:
        raise SystemExit(f"existing C25 output identity mismatch: {key}")
status = run.get("status")
if status == "completed":
    manifest, rows = load_completed_calibration_generation(output)
    if len(rows) != 1602 * 8 or manifest.get("record_count") != 1602 * 8:
        raise SystemExit("completed C25 output count mismatch")
    print("completed_reuse")
    raise SystemExit(0)
if status != "running":
    raise SystemExit("existing C25 output has invalid status")
rows, _ = _load_running_calibration_generation_prefix(output)
if len(rows) > 1602 * 8 or len(rows) % 8:
    raise SystemExit("running C25 prefix has invalid record count")
print(f"resume_{len(rows)//8}_of_1602")
PY_RESUME
)" || fail_preflight "C25 resume-state validation failed"
printf '[%s] generation_action=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$OUTPUT_ACTION" >>"$LOG_FILE"

RUNTIME_FIELDS="$($PY - "$REPO_ROOT" "$HEAD_COMMIT" "$MACHINE_OPEN_R1" <<'PY_RUNTIME'
import sys
from pathlib import Path
import code_verifier
from code_verifier.environment import collect_environment
repo = Path(sys.argv[1]).resolve()
head, expected_open_r1 = sys.argv[2:4]
module_file = getattr(code_verifier, "__file__", None)
if module_file is None or repo not in Path(module_file).resolve().parents:
    raise SystemExit("code_verifier does not resolve inside target checkout")
current = collect_environment(repo)
if current.get("project_commit") != head:
    raise SystemExit("project commit/runtime mismatch")
if current.get("open_r1_commit") != expected_open_r1:
    raise SystemExit("Open-R1/runtime mismatch")
print("\t".join([
    str(current.get("open_r1_commit") or ""),
    str(current.get("dependency_lock_hash") or ""),
    str(current.get("packages", {}).get("torch") or ""),
    str(current.get("cuda_version") or ""),
]))
PY_RUNTIME
)" || fail_preflight "C25 target runtime identity validation failed"
IFS="$TAB" read -r CURRENT_OPEN_R1 CURRENT_LOCK_SHA CURRENT_TORCH CURRENT_CUDA <<<"$RUNTIME_FIELDS"
EXPECTED_LOCK_SHA="$($PY - "$REPO_ROOT/$CHECKPOINT_REL" <<'PY_LOCK'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["sft_identity"]["dependency_lock_hash"])
PY_LOCK
)"
[[ "$CURRENT_LOCK_SHA" == "$EXPECTED_LOCK_SHA" ]] || fail_preflight "dependency lock differs from frozen B identity"

if ! GPU_LIST="$(nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits 2>>"$LOG_FILE")"; then
  fail_preflight "nvidia-smi GPU inventory failed"
fi
if [[ "$OUTPUT_ACTION" == "completed_reuse" ]]; then
  GPU_ROW="$(printf '%s\n' "$GPU_LIST" | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$1); gsub(/ /,"",$3); gsub(/ /,"",$4); if ($3+0 >= 22528) {print $1"\t"$2"\t"$3"\t"$4; exit}}')"
  [[ -n "$GPU_ROW" ]] || fail_preflight "completed C25 reuse still requires the certified RTX 4090 machine identity"
else
  GPU_ROW="$(printf '%s\n' "$GPU_LIST" | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$1); gsub(/ /,"",$3); gsub(/ /,"",$4); if ($3+0 >= 22528 && $4+0 >= 20000) {print $1"\t"$2"\t"$3"\t"$4; exit}}')"
  [[ -n "$GPU_ROW" ]] || fail_preflight "fresh/resumed C25 generation requires RTX 4090 with >=22528 MiB total and >=20000 MiB free VRAM"
fi
IFS="$TAB" read -r GPU_INDEX GPU_NAME GPU_VRAM_MIB GPU_FREE_MIB <<<"$GPU_ROW"
GPU_NAME="$(printf '%s' "$GPU_NAME" | sed 's/^ *//;s/ *$//')"
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
if ! "$PY" - <<'PY_GPU'
import torch
if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise SystemExit("C25 requires exactly one visible CUDA device")
p = torch.cuda.get_device_properties(0)
if "RTX 4090" not in p.name or p.total_memory // (1024 * 1024) < 22528:
    raise SystemExit("visible CUDA device is not the certified RTX 4090 target")
if not torch.cuda.is_bf16_supported():
    raise SystemExit("visible RTX 4090 lacks required bf16 support")
PY_GPU
then
  fail_preflight "C25 CUDA/BF16 validation failed"
fi

CURRENT_PHASE="generation"
set +e
"$PY" "$REPO_ROOT/$RUNNER_REL" \
  --input-bundle "$INPUT_DIR" \
  --sft-run "$B_RUN" \
  --output "$OUTPUT_DIR" \
  --problem-batch-size "$PROBLEM_BATCH_SIZE" 2>&1 | tee -a "$LOG_FILE"
COMMAND_RC="${PIPESTATUS[0]}"
set -e
if (( COMMAND_RC != 0 )); then
  finalize_gate "$COMMAND_RC" 125 command_failed "C25 generation command exited nonzero"
  exit $?
fi

CURRENT_PHASE="postcheck"
set +e
"$PY" - "$REPO_ROOT/$CHECKPOINT_REL" "$INPUT_DIR" "$OUTPUT_DIR" "$POSTCHECK_FILE.tmp" <<'PY_POSTCHECK'
import hashlib
import json
import sys
from pathlib import Path
from code_verifier.training.calibration import (
    _load_input_bundle,
    calibration_problem_seed,
    load_completed_calibration_generation,
)
checkpoint = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
input_dir = Path(sys.argv[2])
output = Path(sys.argv[3])
summary_path = Path(sys.argv[4])
input_manifest, inputs = _load_input_bundle(input_dir)
run, rows = load_completed_calibration_generation(output)
if len(inputs) != 1602 or len(rows) != 12816:
    raise SystemExit("C25 postcheck count mismatch")
if run.get("record_count") != 12816 or run.get("block_index") != 0 or run.get("samples_per_problem") != 8:
    raise SystemExit("C25 completed run manifest count/block mismatch")
if run.get("input_manifest_sha256") != checkpoint["bindings"]["input_manifest_sha256"]:
    raise SystemExit("C25 completed run input manifest binding mismatch")
if run.get("input_records_sha256") != checkpoint["bindings"]["inputs_sha256"]:
    raise SystemExit("C25 completed run input records binding mismatch")
if run.get("sft_checkpoint") != checkpoint["sft_identity"]:
    raise SystemExit("C25 completed run frozen B identity mismatch")
expected = []
for item in inputs:
    seed = calibration_problem_seed(42, item.problem_id, 0)
    for sample_index in range(8):
        expected.append((item.problem_id, sample_index, seed))
actual = [(row.get("problem_id"), row.get("sample_index"), row.get("sample_seed")) for row in rows]
if actual != expected:
    raise SystemExit("C25 generation rows are not the exact input-order k=8 sequence")
records_path = output / "samples" / "generations.jsonl"
def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
if digest(records_path) != run.get("records_sha256"):
    raise SystemExit("C25 completed generation records SHA mismatch")
progress = json.loads((output / "samples" / "progress.json").read_text(encoding="utf-8"))
if progress.get("record_count") != 12816 or progress.get("byte_count") != records_path.stat().st_size:
    raise SystemExit("C25 progress marker does not cover the completed records file")
summary = {
    "version": 1,
    "status": "passed",
    "problem_count": 1602,
    "record_count": 12816,
    "samples_per_problem": 8,
    "sample_index_start": 0,
    "sample_index_end": 7,
    "problem_batch_size": 4,
    "problem_order_sha256": input_manifest["problem_order_sha256"],
    "generation_records_sha256": run["records_sha256"],
    "run_manifest_sha256": digest(output / "run.json"),
    "progress_sha256": digest(output / "samples" / "progress.json"),
    "input_manifest_sha256": checkpoint["bindings"]["input_manifest_sha256"],
    "inputs_sha256": checkpoint["bindings"]["inputs_sha256"],
    "sft_checkpoint": checkpoint["sft_identity"],
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_POSTCHECK
POSTCHECK_RC=$?
set -e
if (( POSTCHECK_RC != 0 )); then
  finalize_gate 0 "$POSTCHECK_RC" postcheck_failed "C25 mandatory postcheck failed"
  exit $?
fi
mv "$POSTCHECK_FILE.tmp" "$POSTCHECK_FILE"
finalize_gate 0 0 passed "C25 fresh 1602x8 generation completed and postchecked"
exit $?
