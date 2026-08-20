#!/usr/bin/env bash
set -uo pipefail

STAGE_WORKTREE="/home/dzy/open-r1-code-verifier-wp6d-verify/.worktrees/wp6-d"
PRIMARY_ROOT="/home/dzy/open-r1-code-verifier-wp6d-verify"
WORKFLOW_RUNTIME="/home/dzy/open-r1-code-verifier-wp6d-verify/.worktrees/workflow-runtime-1660ti"
VERIFY_REPO="/home/dzy/wp6d-r1-verifier-41abf"
RUNTIME_PY="/home/dzy/open-r1-code-verifier/.venv/bin/python"
EXPORT_ROOT="/home/dzy/wp6d-b-export"
CANONICAL_B="/home/dzy/wp6d-b-verified/evaluation/B-sft-formal-seed42"
OP_ROOT="/home/dzy/wp6d-r1-operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C8"
OUTPUT_ROOT="$OP_ROOT/output"
OUTPUT_RUN="$OUTPUT_ROOT/evaluation/B-sft-formal-seed42"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOCK_FILE="$OP_ROOT/run.lock"
REPORT_REL="ai-work/executor/WP6-d-executor.md"
SCRIPT_REL="ai-work/executor/operator/WP6-d/sft-b-evaluation/C8/run.sh"
CHECKPOINT_ID="C8"
GATE_ID="sft-b-evaluation"
PLAN_COMMIT="eb523bc749e9aa4362790c45bbcf4d604ad7e478"
REVIEW_COMMIT="6f80d545374809693d8a47defe791ee1f881489e"
RESULT_CODE_COMMIT="280cfb0da3f5d988b60484c712d511b25d87f433"
PLANNING_BASE_COMMIT="a683602f22de7f7b0ba24f01d12a183eea7ddca7"
WORKFLOW_RUNTIME_COMMIT="734549fe3282edad76456c69f085e53d9ce39844"
VERIFIER_COMMIT="41abf31618372445ba2233f386c08417b4407436"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEPENDENCY_LOCK_SHA="59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560"
GENERATION_RECORDS_SHA="24cdd44976e7c8ff50934cb636ff7128497799c84f7b3739be89314fe477adfc"
GENERATION_CONTRACT_SHA="119fe22ee3983394ecae036b9ddc6a741766b07f3f09244765aa510679322a72"
DATASET_SHA="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
PISTON_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
CANONICAL_RESULTS_SHA="b53cb533b17ce7ca30e508a01cc484272470c64c1532d5a68810dfa66cd6291f"
RUN_NAME="B-sft-formal-seed42"

mkdir -p "$OP_ROOT"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "operator lock is already held: $LOCK_FILE" >&2
  exit 73
fi

ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ -f "$STATUS_FILE" ]]; then
  cp -a "$STATUS_FILE" "$OP_ROOT/status.before-$ATTEMPT_ID"
fi
if [[ -f "$EVIDENCE_FILE" ]]; then
  cp -a "$EVIDENCE_FILE" "$OP_ROOT/operator-evidence.before-$ATTEMPT_ID.json"
fi
rm -f "$STATUS_FILE.tmp" "$EVIDENCE_FILE.tmp"
printf '[%s] attempt=%s start checkpoint=%s gate=%s\n' "$START_TIME" "$ATTEMPT_ID" "$CHECKPOINT_ID" "$GATE_ID" >>"$LOG_FILE"

write_evidence() {
  local command_rc="$1"
  local postcheck_rc="$2"
  local gate_status="$3"
  local note="$4"
  local end_time head script_sha results_sha run_sha
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  head="$(git -C "$STAGE_WORKTREE" rev-parse HEAD 2>/dev/null || printf 'unknown')"
  script_sha="$(sha256sum "$STAGE_WORKTREE/$SCRIPT_REL" 2>/dev/null | awk '{print $1}' || true)"
  results_sha=""
  run_sha=""
  if [[ -f "$OUTPUT_RUN/samples/results.jsonl" ]]; then
    results_sha="$(sha256sum "$OUTPUT_RUN/samples/results.jsonl" | awk '{print $1}')"
  fi
  if [[ -f "$OUTPUT_RUN/run.json" ]]; then
    run_sha="$(sha256sum "$OUTPUT_RUN/run.json" | awk '{print $1}')"
  fi
  "$RUNTIME_PY" - "$EVIDENCE_FILE.tmp" "$head" "$script_sha" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" "$results_sha" "$run_sha" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

(
    output,
    checkpoint_commit,
    script_sha,
    command_rc,
    postcheck_rc,
    gate_status,
    note,
    start_time,
    end_time,
    attempt_id,
    results_sha,
    run_sha,
) = sys.argv[1:]


def semantic_results_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise SystemExit("evaluation row is not an object")
        rows.append({key: value for key, value in row.items() if key not in {"runtime_ms", "config_hash"}})
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


canonical_results = Path("/home/dzy/wp6d-b-verified/evaluation/B-sft-formal-seed42/samples/results.jsonl")
repair_results = Path(
    "/home/dzy/wp6d-r1-operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/"
    "sft-b-evaluation/C8/output/evaluation/B-sft-formal-seed42/samples/results.jsonl"
)
canonical_semantic_sha = semantic_results_sha(canonical_results)
repair_semantic_sha = semantic_results_sha(repair_results)
payload = {
    "version": 1,
    "operator_handoff_mode": "control_plane_manual",
    "stage_id": "WP6-d",
    "source_plan_commit": "eb523bc749e9aa4362790c45bbcf4d604ad7e478",
    "source_review_round": 1,
    "source_review_commit": "6f80d545374809693d8a47defe791ee1f881489e",
    "repair_issue_ids": ["R1-M1"],
    "workflow_runtime_commit": "734549fe3282edad76456c69f085e53d9ce39844",
    "legacy_control_plane_default": True,
    "operator_checkpoint_commit": checkpoint_commit,
    "result_code_commit": "280cfb0da3f5d988b60484c712d511b25d87f433",
    "checkpoint_id": "C8",
    "operator_gate_id": "sft-b-evaluation",
    "operator_script": "ai-work/executor/operator/WP6-d/sft-b-evaluation/C8/run.sh",
    "operator_script_sha256": script_sha,
    "control_plane_hardware": "GTX 1660 Ti (6GB)",
    "verifier_project_commit": "41abf31618372445ba2233f386c08417b4407436",
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "dependency_lock_sha256": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
    "generation_records_sha256": "24cdd44976e7c8ff50934cb636ff7128497799c84f7b3739be89314fe477adfc",
    "generation_contract_sha256": "119fe22ee3983394ecae036b9ddc6a741766b07f3f09244765aa510679322a72",
    "dataset_sha256": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "formal_run_name": "B-sft-formal-seed42",
    "generation_run_dir": "/home/dzy/wp6d-b-export/required/generation/B-sft-formal-seed42",
    "formal_data_dir": "/home/dzy/wp6d-b-export/required/formal-data/prepared",
    "canonical_b_dir": "/home/dzy/wp6d-b-verified/evaluation/B-sft-formal-seed42",
    "repair_output_run_dir": "/home/dzy/wp6d-r1-operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C8/output/evaluation/B-sft-formal-seed42",
    "canonical_results_sha256": "b53cb533b17ce7ca30e508a01cc484272470c64c1532d5a68810dfa66cd6291f",
    "repair_results_sha256": results_sha or None,
    "volatile_result_fields": ["config_hash", "runtime_ms"],
    "canonical_semantic_results_sha256": canonical_semantic_sha,
    "repair_semantic_results_sha256": repair_semantic_sha,
    "semantic_results_equal": canonical_semantic_sha is not None and canonical_semantic_sha == repair_semantic_sha,
    "repair_run_json_sha256": run_sha or None,
    "attempt_id": attempt_id,
    "start_time": start_time,
    "end_time": end_time,
    "command_rc": int(command_rc),
    "postcheck_rc": int(postcheck_rc),
    "gate_status": gate_status,
    "note": note,
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  local final_rc=1
  if [[ "$gate_status" == "passed" && "$command_rc" == "0" && "$postcheck_rc" == "0" ]]; then
    final_rc=0
  elif [[ "$command_rc" =~ ^[0-9]+$ ]] && (( command_rc > 0 && command_rc < 126 )); then
    final_rc="$command_rc"
  fi
  printf '%s\n' "$final_rc" >"$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  printf '[%s] attempt=%s end command_rc=%s postcheck_rc=%s gate_status=%s note=%s\n' "$end_time" "$ATTEMPT_ID" "$command_rc" "$postcheck_rc" "$gate_status" "$note" >>"$LOG_FILE"
  return "$final_rc"
}

fail_preflight() {
  local message="$1"
  printf '[%s] preflight FAIL: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$message" >>"$LOG_FILE"
  write_evidence 125 125 preflight_failed "$message"
  exit $?
}

[[ -x "$RUNTIME_PY" ]] || fail_preflight "runtime python unavailable"
[[ -d "$VERIFY_REPO/.git" ]] || fail_preflight "isolated verifier clone unavailable"
[[ -d "$EXPORT_ROOT" ]] || fail_preflight "export root unavailable"
[[ -d "$CANONICAL_B" ]] || fail_preflight "canonical B evidence unavailable"

HEAD_COMMIT="$(git -C "$STAGE_WORKTREE" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve stage HEAD"
PARENT_COMMIT="$(git -C "$STAGE_WORKTREE" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve checkpoint parent"
[[ "$PARENT_COMMIT" == "$RESULT_CODE_COMMIT" ]] || fail_preflight "checkpoint parent does not equal result_code_commit"
[[ "$(git -C "$STAGE_WORKTREE" symbolic-ref --short HEAD 2>/dev/null)" == "feat/wp6-d" ]] || fail_preflight "stage branch mismatch"
[[ -z "$(git -C "$STAGE_WORKTREE" status --porcelain)" ]] || fail_preflight "stage worktree is not clean"
[[ "$(git -C "$PRIMARY_ROOT" rev-parse main 2>/dev/null)" == "$PLANNING_BASE_COMMIT" ]] || fail_preflight "primary main advanced from sealed planning base"
[[ "$(git -C "$WORKFLOW_RUNTIME" rev-parse HEAD 2>/dev/null)" == "$WORKFLOW_RUNTIME_COMMIT" ]] || fail_preflight "workflow runtime commit mismatch"
[[ -z "$(git -C "$WORKFLOW_RUNTIME" status --porcelain)" ]] || fail_preflight "workflow runtime worktree is not clean"
[[ "$(git -C "$VERIFY_REPO" rev-parse HEAD 2>/dev/null)" == "$VERIFIER_COMMIT" ]] || fail_preflight "isolated verifier commit mismatch"
[[ "$(git -C "$VERIFY_REPO/third_party/open-r1" rev-parse HEAD 2>/dev/null)" == "$OPEN_R1_COMMIT" ]] || fail_preflight "isolated Open-R1 commit mismatch"
[[ -z "$(git -C "$VERIFY_REPO" status --porcelain --ignore-submodules=none)" ]] || fail_preflight "isolated verifier checkout is not clean"
LOCK_HASH="$(env PYTHONPATH="$VERIFY_REPO/src:$VERIFY_REPO/third_party/open-r1/src" "$RUNTIME_PY" -c 'import sys; from pathlib import Path; from code_verifier.environment import _dependency_lock_hash; print(_dependency_lock_hash(Path(sys.argv[1]), {}))' "$VERIFY_REPO")" || fail_preflight "cannot compute dependency lock identity"
[[ "$LOCK_HASH" == "$DEPENDENCY_LOCK_SHA" ]] || fail_preflight "dependency lock SHA mismatch"
[[ "$(sha256sum "$VERIFY_REPO/configs/execution/piston-local.yaml" | awk '{print $1}')" == "$PISTON_SHA" ]] || fail_preflight "Piston config SHA mismatch"
if ! env PYTHONPATH="$VERIFY_REPO/src:$VERIFY_REPO/third_party/open-r1/src" "$RUNTIME_PY" - "$EXPORT_ROOT/required/generation/$RUN_NAME/environment.json" <<'PY'
import json
import sys
from pathlib import Path

from code_verifier.environment import collect_environment

frozen = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
current = collect_environment()
for key in ("project_commit", "open_r1_commit", "dependency_lock_hash"):
    if current.get(key) != frozen.get(key):
        raise SystemExit(f"current verifier environment mismatch: {key}")
if current.get("packages") != frozen.get("packages"):
    raise SystemExit("current tracked package versions do not match frozen generation environment")
PY
then
  fail_preflight "isolated verifier runtime/package identity mismatch"
fi

CHECKPOINT_META="$($RUNTIME_PY - "$STAGE_WORKTREE/$REPORT_REL" "$CHECKPOINT_ID" <<'PY'
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
print("\t".join([
    field("operator_script_sha256"),
    field("operator_handoff_mode"),
    field("workflow_runtime_commit"),
    field("source_review_commit"),
]))
PY
)" || fail_preflight "cannot parse latest C8 checkpoint provenance"
IFS=$'\t' read -r EXPECTED_SCRIPT_SHA CHECKPOINT_MODE CHECKPOINT_RUNTIME CHECKPOINT_REVIEW <<<"$CHECKPOINT_META"
[[ "$CHECKPOINT_MODE" == "control_plane_manual" ]] || fail_preflight "checkpoint handoff mode mismatch"
[[ "$CHECKPOINT_RUNTIME" == "$WORKFLOW_RUNTIME_COMMIT" ]] || fail_preflight "checkpoint workflow runtime mismatch"
[[ "$CHECKPOINT_REVIEW" == "$REVIEW_COMMIT" ]] || fail_preflight "checkpoint review provenance mismatch"
ACTUAL_SCRIPT_SHA="$(sha256sum "$STAGE_WORKTREE/$SCRIPT_REL" | awk '{print $1}')"
[[ "$ACTUAL_SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || fail_preflight "tracked operator script SHA mismatch"

mapfile -t CHECKPOINT_DIFF < <(git -C "$STAGE_WORKTREE" diff --name-only "$PARENT_COMMIT" "$HEAD_COMMIT")
[[ "${#CHECKPOINT_DIFF[@]}" -eq 2 ]] || fail_preflight "checkpoint commit must contain exactly report plus one script"
printf '%s\n' "${CHECKPOINT_DIFF[@]}" | grep -Fxq "$REPORT_REL" || fail_preflight "checkpoint commit does not contain execution report"
printf '%s\n' "${CHECKPOINT_DIFF[@]}" | grep -Fxq "$SCRIPT_REL" || fail_preflight "checkpoint commit does not contain tracked C8 script"

if ! (cd "$EXPORT_ROOT" && sha256sum -c MANIFEST.sha256 --quiet); then
  fail_preflight "export manifest verification failed"
fi
if ! (cd "$CANONICAL_B" && sha256sum -c MANIFEST.sha256 --quiet); then
  fail_preflight "canonical B manifest verification failed"
fi

if ! "$RUNTIME_PY" - "$EXPORT_ROOT/required/generation/$RUN_NAME/run.json" "$CANONICAL_B/run.json" <<'PY'
import json
import sys
from pathlib import Path

generation = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
canonical = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
expected_generation = {
    "status": "completed",
    "completed_records": 400,
    "total_problems": 400,
    "records_sha256": "24cdd44976e7c8ff50934cb636ff7128497799c84f7b3739be89314fe477adfc",
    "evaluation_contract_sha256": "119fe22ee3983394ecae036b9ddc6a741766b07f3f09244765aa510679322a72",
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "project_commit": "41abf31618372445ba2233f386c08417b4407436",
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
    "run_id": "B-sft-formal-seed42",
    "seed": 42,
}
for key, value in expected_generation.items():
    if generation.get(key) != value:
        raise SystemExit(f"generation identity mismatch: {key}")
expected_canonical = {
    "status": "completed",
    "project_commit": "41abf31618372445ba2233f386c08417b4407436",
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
    "generation_bundle_records_sha256": "24cdd44976e7c8ff50934cb636ff7128497799c84f7b3739be89314fe477adfc",
    "generation_bundle_contract_sha256": "119fe22ee3983394ecae036b9ddc6a741766b07f3f09244765aa510679322a72",
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "run_id": "B-sft-formal-seed42",
    "seed": 42,
    "verification_workers": 4,
}
for key, value in expected_canonical.items():
    if canonical.get(key) != value:
        raise SystemExit(f"canonical B identity mismatch: {key}")
PY
then
  fail_preflight "generation/canonical B identity preflight failed"
fi

if ! "$RUNTIME_PY" - "$OP_ROOT" <<'PY'
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
usage = shutil.disk_usage(root)
if usage.free < 1024**3:
    raise SystemExit("less than 1 GiB free for repair verification evidence")
PY
then
  fail_preflight "repair output storage preflight failed"
fi

printf '[%s] preflight: running local Piston acceptance\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
make -C "$STAGE_WORKTREE" test-piston >>"$LOG_FILE" 2>&1
PISTON_RC=$?
if [[ "$PISTON_RC" -ne 0 ]]; then
  fail_preflight "local Piston acceptance failed rc=$PISTON_RC"
fi
printf '[%s] preflight PASS: exact identities, manifests, storage, Piston 9/9\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"

export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
export PYTHONPATH="$VERIFY_REPO/src:$VERIFY_REPO/third_party/open-r1/src"
cd "$VERIFY_REPO" || fail_preflight "cannot enter isolated verifier checkout"

printf '[%s] command start: verify-eval frozen 400-row generation bundle -> fresh repair namespace\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
"$RUNTIME_PY" -m code_verifier.cli verify-eval \
  --config "$VERIFY_REPO/configs/eval/base.yaml" \
  --dataset-dir "$EXPORT_ROOT/required/formal-data/prepared" \
  --generation-run-dir "$EXPORT_ROOT/required/generation/$RUN_NAME" \
  --run-name "$RUN_NAME" \
  --seed 42 \
  --workers 4 \
  --output-dir "$OUTPUT_ROOT" 2>&1 | tee -a "$LOG_FILE"
COMMAND_RC=${PIPESTATUS[0]}
printf '[%s] command end rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$COMMAND_RC" >>"$LOG_FILE"
if [[ "$COMMAND_RC" -ne 0 ]]; then
  write_evidence "$COMMAND_RC" 125 command_failed "verify-eval exited nonzero"
  exit $?
fi

printf '[%s] postcheck start\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
"$RUNTIME_PY" - "$OUTPUT_RUN" "$CANONICAL_B" <<'PY'
import hashlib
import json
import math
import re
import sys
from pathlib import Path

from code_verifier.analysis.experiment import _load_evaluation_run

run_dir = Path(sys.argv[1])
canonical_dir = Path(sys.argv[2])
run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
expected = {
    "status": "completed",
    "project_commit": "41abf31618372445ba2233f386c08417b4407436",
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
    "generation_bundle_records_sha256": "24cdd44976e7c8ff50934cb636ff7128497799c84f7b3739be89314fe477adfc",
    "generation_bundle_contract_sha256": "119fe22ee3983394ecae036b9ddc6a741766b07f3f09244765aa510679322a72",
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "run_id": "B-sft-formal-seed42",
    "seed": 42,
    "verification_workers": 4,
}
for key, value in expected.items():
    if run.get(key) != value:
        raise SystemExit(f"repair run identity mismatch: {key}")
strict_records, strict_metadata, _ = _load_evaluation_run(run_dir, method="B-repair")
if len(strict_records) != 400 or strict_metadata.get("status") != "completed":
    raise SystemExit("strict repair evaluation loader did not accept one completed 400-row run")


def load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SystemExit("evaluation result row is not an object")
        rows.append(value)
    return rows


repair_results = run_dir / "samples" / "results.jsonl"
canonical_results = canonical_dir / "samples" / "results.jsonl"
canonical_raw_sha = hashlib.sha256(canonical_results.read_bytes()).hexdigest()
if canonical_raw_sha != "b53cb533b17ce7ca30e508a01cc484272470c64c1532d5a68810dfa66cd6291f":
    raise SystemExit("canonical B results SHA drifted before repair comparison")
repair_rows = load_rows(repair_results)
canonical_rows = load_rows(canonical_results)
if len(repair_rows) != 400 or len(canonical_rows) != 400:
    raise SystemExit("repair/canonical comparison requires exactly 400 rows")
repair_ids = [row.get("problem_id") for row in repair_rows]
canonical_ids = [row.get("problem_id") for row in canonical_rows]
if repair_ids != canonical_ids or len(set(repair_ids)) != 400:
    raise SystemExit("repair results do not preserve the canonical 400-problem order")

volatile_fields = {"runtime_ms", "config_hash"}
for index, (repair_row, canonical_row) in enumerate(zip(repair_rows, canonical_rows, strict=True), start=1):
    if set(repair_row) != set(canonical_row):
        raise SystemExit(f"repair result row {index} field set drifted")
    runtime_ms = repair_row.get("runtime_ms")
    if isinstance(runtime_ms, bool) or not isinstance(runtime_ms, (int, float)) or not math.isfinite(runtime_ms) or runtime_ms < 0:
        raise SystemExit(f"repair result row {index} has invalid runtime_ms")
    config_hash = repair_row.get("config_hash")
    if not isinstance(config_hash, str) or re.fullmatch(r"[0-9a-f]{64}", config_hash) is None:
        raise SystemExit(f"repair result row {index} has invalid config_hash")
    repair_semantic = {key: value for key, value in repair_row.items() if key not in volatile_fields}
    canonical_semantic = {key: value for key, value in canonical_row.items() if key not in volatile_fields}
    if repair_semantic != canonical_semantic:
        raise SystemExit(f"repair result row {index} semantic verdict/generated payload drifted")

repair_semantic_rows = [
    {key: value for key, value in row.items() if key not in volatile_fields}
    for row in repair_rows
]
canonical_semantic_rows = [
    {key: value for key, value in row.items() if key not in volatile_fields}
    for row in canonical_rows
]
def semantic_sha(rows: list[dict[str, object]]) -> str:
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
if semantic_sha(repair_semantic_rows) != semantic_sha(canonical_semantic_rows):
    raise SystemExit("repair semantic results SHA mismatch")
PY
POSTCHECK_RC=$?
if [[ "$POSTCHECK_RC" -ne 0 ]]; then
  write_evidence 0 "$POSTCHECK_RC" postcheck_failed "strict repair output semantic/provenance postcheck failed"
  exit $?
fi
printf '[%s] postcheck PASS: 400 canonical rows, exact generated/verdict semantics; runtime_ms/config_hash recorded as fresh attempt-local fields\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
write_evidence 0 0 passed "manual 1660 Ti Piston verification reproduced canonical generated payload and verdict semantics; fresh runtime_ms/config_hash remain independently recorded"
exit $?
