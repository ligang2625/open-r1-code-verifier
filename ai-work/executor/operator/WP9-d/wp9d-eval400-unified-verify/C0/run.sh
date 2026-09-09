#!/usr/bin/env bash
set -uo pipefail

MODE="${1:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C0/run.sh"
EXPECTED_PARENT="f17b4f607daa3bb03b08682bbbd841118d36c4af"

A_VERIFIER="/home/dzy/wp9d-verifier-a-f17b4f6"
B_VERIFIER="/home/dzy/wp9d-verifier-b-07ccc719"
A_COMMIT="f17b4f607daa3bb03b08682bbbd841118d36c4af"
B_COMMIT="07ccc71968bedc25b1a8fd15aa0ee35a75e05389"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEPENDENCY_LOCK_SHA="4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf"

DATASET_DIR="/home/dzy/wp6d-b-export/required/formal-data/prepared"
DATASET_SHA="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
ORDER_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
PISTON_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
WORKERS=64
SEED=42

A_SOURCE_ROOT="/home/dzy/wp9d-recipe-a-eval400-f17b4f6/generation"
A_EVIDENCE="/home/dzy/wp9d-recipe-a-eval400-f17b4f6/operator-evidence/operator-evidence.json"
B_SOURCE_ROOT="/home/dzy/wp9d-b-refresh-eval400/generation"
B_EVIDENCE="/home/dzy/wp9d-b-refresh-eval400/operator-evidence/operator-evidence.json"
OUTPUT_ROOT="/home/dzy/wp9d-eval400-verified"
OP_ROOT="/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C0"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOCK_FILE="$OP_ROOT/run.lock"
MANIFEST_FILE="$OUTPUT_ROOT/verification-manifest.json"
RUNTIME_PY="/home/dzy/open-r1-code-verifier/.venv/bin/python"

B_RUN="wp9d-B-eval400-b4-p1-seed42"
A_RUNS=(
  "wp9d-A-public-step300-eval400-b4-p1-seed42"
  "wp9d-A-public-step600-eval400-b4-p1-seed42"
  "wp9d-A-public-step900-eval400-b4-p1-seed42"
  "wp9d-A-public-step1200-eval400-b4-p1-seed42"
  "wp9d-A-hidden-step300-eval400-b4-p1-seed42"
  "wp9d-A-hidden-step600-eval400-b4-p1-seed42"
  "wp9d-A-hidden-step900-eval400-b4-p1-seed42"
  "wp9d-A-hidden-step1200-eval400-b4-p1-seed42"
)

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh preflight
  run.sh verify

required environment:
  WP9D_VERIFY_HANDOFF_COMMIT=<exact committed operator checkpoint>
  WP9D_VERIFY_SCRIPT_SHA256=<sha256 of this tracked run.sh>

The verify mode is control-plane manual execution only. It consumes the already-synced
B + Recipe A frozen generation bundles, runs local-Piston verify-eval sequentially
with workers=64, then aggregate-eval, and performs a strict 9-run/3600-row postcheck.
It never loads a model and never contacts an RTX 4090.
EOF
  exit 64
}

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

fail_preflight() {
  local message="$1"
  printf 'preflight FAIL: %s\n' "$message" >&2
  return 125
}

check_control_identity() {
  local handoff="${WP9D_VERIFY_HANDOFF_COMMIT:-}"
  local expected_script_sha="${WP9D_VERIFY_SCRIPT_SHA256:-}"
  local head parent actual_sha dirty

  [[ "$handoff" =~ ^[0-9a-f]{40}$ ]] || fail_preflight "set WP9D_VERIFY_HANDOFF_COMMIT to the exact operator checkpoint" || return $?
  [[ "$expected_script_sha" =~ ^[0-9a-f]{64}$ ]] || fail_preflight "set WP9D_VERIFY_SCRIPT_SHA256 to the exact tracked script SHA256" || return $?
  head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve control-plane HEAD" || return $?
  parent="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve operator checkpoint parent" || return $?
  [[ "$head" == "$handoff" ]] || fail_preflight "control-plane HEAD does not equal WP9D_VERIFY_HANDOFF_COMMIT" || return $?
  [[ "$parent" == "$EXPECTED_PARENT" ]] || fail_preflight "operator checkpoint parent is not the accepted Recipe A eval handoff" || return $?
  actual_sha="$(sha256_file "$REPO_ROOT/$SCRIPT_REL")"
  [[ "$actual_sha" == "$expected_script_sha" ]] || fail_preflight "tracked run.sh SHA256 mismatch" || return $?
  dirty="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal | grep -vE '^\?\? \.ai-bridge/' || true)"
  [[ -z "$dirty" ]] || fail_preflight "control-plane worktree must be clean outside .ai-bridge" || return $?
}

check_verifier_checkout() {
  local root="$1"
  local expected_commit="$2"
  local head open_r1 dirty
  [[ -d "$root" ]] || fail_preflight "missing verifier checkout: $root" || return $?
  head="$(git -C "$root" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve verifier HEAD: $root" || return $?
  [[ "$head" == "$expected_commit" ]] || fail_preflight "verifier commit mismatch: $root" || return $?
  open_r1="$(git -C "$root/third_party/open-r1" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve Open-R1 checkout: $root" || return $?
  [[ "$open_r1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "Open-R1 commit mismatch: $root" || return $?
  dirty="$(git -C "$root" status --porcelain=v1 --untracked-files=normal --ignore-submodules=none)"
  [[ -z "$dirty" ]] || fail_preflight "verifier checkout is not clean: $root" || return $?
  [[ "$(sha256_file "$root/configs/eval/base.yaml")" == "$EVAL_CONFIG_SHA" ]] || fail_preflight "eval config SHA mismatch: $root" || return $?
  [[ "$(sha256_file "$root/configs/execution/piston-local.yaml")" == "$PISTON_SHA" ]] || fail_preflight "Piston definition SHA mismatch: $root" || return $?
}

check_synced_source_hashes() {
  "$RUNTIME_PY" - "$A_EVIDENCE" "$B_EVIDENCE" "$A_SOURCE_ROOT" "$B_SOURCE_ROOT" <<'PY_SOURCE_HASHES'
import hashlib
import json
import sys
from pathlib import Path

A_EVIDENCE, B_EVIDENCE, A_ROOT, B_ROOT = map(Path, sys.argv[1:])
A_COMMIT = "f17b4f607daa3bb03b08682bbbd841118d36c4af"
B_COMMIT = "07ccc71968bedc25b1a8fd15aa0ee35a75e05389"
EXPECTED = {
    "wp9d-B-eval400-b4-p1-seed42": (
        "99d715b40384c6d98aff8640cc5346f5ce0b3e613031564bfaf1481a30f57756",
        "9bd47fff5c36216ede0e33c087ea98946198f6d131ff780794135aa655eb9c02",
        B_COMMIT,
    ),
    "wp9d-A-public-step300-eval400-b4-p1-seed42": (
        "7becf09cdd6d559a1dfe9b4504886aea9688b57e8bd2f5dc613f6a8606333a7b",
        "6536ee10e4cc9ad3bf84e39bc8223a366d49b059fad921fcdd9d03f7d95133db",
        A_COMMIT,
    ),
    "wp9d-A-public-step600-eval400-b4-p1-seed42": (
        "d57c8f36328e88c76420bbae8bb06d9a01272a204ed108a36f0d8208cd36510b",
        "39967983a63cb4f22de2f0f9f21172ebd169a7e89f910977a05d465e8e455119",
        A_COMMIT,
    ),
    "wp9d-A-public-step900-eval400-b4-p1-seed42": (
        "3082ce8588b568e8c519122b8504188ea39632d74926e4d3c1cadf3e27940e73",
        "33ad1c81a9f3ee63e46d6b300753c6c63157cdd44b52a6d8e4abff989f55a85f",
        A_COMMIT,
    ),
    "wp9d-A-public-step1200-eval400-b4-p1-seed42": (
        "bdcd70ac2ee6eba919aed4498a8a1bd9f08d1fa2ad8bb0a982ae8ca879e00ff6",
        "957beb9f6ff56a7ba3459127f319c506ccafaddbe066684941782b66c0c40af1",
        A_COMMIT,
    ),
    "wp9d-A-hidden-step300-eval400-b4-p1-seed42": (
        "e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120",
        "8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c",
        A_COMMIT,
    ),
    "wp9d-A-hidden-step600-eval400-b4-p1-seed42": (
        "ed65576ac5551390accb63ba8a3547b607388501e4c3be790d4e61e2d2d239f9",
        "93a5d0bf1811d226328661c193bd3498ad99c36e37d659e23da947294c920fa4",
        A_COMMIT,
    ),
    "wp9d-A-hidden-step900-eval400-b4-p1-seed42": (
        "0b3dcf46601666cd165a442191f37292dd3872869b496dc031fcf79b424e591d",
        "79046932a512f083383ab01a7f6c4b8c0d11531470f12aa45f1001c9fbdb76f3",
        A_COMMIT,
    ),
    "wp9d-A-hidden-step1200-eval400-b4-p1-seed42": (
        "64655c5f78c48d13527be709ae723991e77d2f25582a31a0a6ef0ced1406c3ad",
        "07d27f5ddc3fd4e64979acd4b875db5191ab7f485da66d6054a053cc8ed528d5",
        A_COMMIT,
    ),
}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

for evidence_path, expected_commit, expected_gate in (
    (A_EVIDENCE, A_COMMIT, "wp9d-recipe-a-eval400"),
    (B_EVIDENCE, B_COMMIT, "wp9d-b-refresh-eval400"),
):
    value = load_json(evidence_path)
    if value.get("gate_status") != "passed" or value.get("handoff_commit") != expected_commit:
        raise SystemExit(f"synced operator evidence identity mismatch: {evidence_path}")
    if value.get("gate_id") != expected_gate:
        raise SystemExit(f"synced operator evidence gate mismatch: {evidence_path}")

for name, (run_sha, records_sha, project_commit) in EXPECTED.items():
    root = B_ROOT if name.startswith("wp9d-B-") else A_ROOT
    run = root / name
    run_json = run / "run.json"
    records = run / "samples" / "generations.jsonl"
    if sha(run_json) != run_sha or sha(records) != records_sha:
        raise SystemExit(f"synced generation SHA mismatch: {name}")
    metadata = load_json(run_json)
    expected = {
        "status": "completed",
        "completed_records": 400,
        "total_problems": 400,
        "batch_size": 4,
        "parallel_generators": 1,
        "seed": 42,
        "project_commit": project_commit,
        "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
        "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
        "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    }
    for key, wanted in expected.items():
        if metadata.get(key) != wanted:
            raise SystemExit(f"synced generation identity mismatch: {name}: {key}")
print("source_hash_postcheck=PASS bundles=9 records=3600")
PY_SOURCE_HASHES
}

strict_bundle_preflight() {
  local verifier="$1"
  shift
  env PYTHONPATH="$verifier/src:$verifier/third_party/open-r1/src" \
    "$RUNTIME_PY" - "$verifier" "$DATASET_DIR" "$@" <<'PY_BUNDLE'
import os
import sys
from dataclasses import replace
from pathlib import Path

from code_verifier.environment import collect_environment
from code_verifier.evaluation.evaluate import load_evaluation_config, load_evaluation_problems
from code_verifier.evaluation.staged import load_completed_generation_bundle, load_generation_bundle_source

root = Path(sys.argv[1])
dataset = Path(sys.argv[2])
runs = [Path(value) for value in sys.argv[3:]]
os.chdir(root)
current = collect_environment()
expected_project = "07ccc71968bedc25b1a8fd15aa0ee35a75e05389" if "verifier-b" in root.name else "f17b4f607daa3bb03b08682bbbd841118d36c4af"
expected_env = {
    "project_commit": expected_project,
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "dependency_lock_hash": "4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf",
}
for key, wanted in expected_env.items():
    if current.get(key) != wanted:
        raise SystemExit(f"verifier environment mismatch: {root}: {key}")
base = load_evaluation_config(root / "configs/eval/base.yaml")
base = replace(base, dataset_dir=dataset)
problems = load_evaluation_problems(base)
if len(problems) != 400:
    raise SystemExit("canonical eval dataset is not 400 problems")
for run in runs:
    source = load_generation_bundle_source(run)
    config = replace(base, model_revision=source.model_revision, checkpoint=source.checkpoint)
    identity, records = load_completed_generation_bundle(
        run,
        config=config,
        problems=problems,
        seed=42,
        require_current_code_identity=False,
    )
    if identity.run_id != run.name or len(records) != 400 or identity.batch_size != 4:
        raise SystemExit(f"strict generation bundle preflight failed: {run.name}")
    print(f"bundle_preflight=PASS run={run.name} rows={len(records)}")
PY_BUNDLE
}

check_dataset_identity() {
  env PYTHONPATH="$A_VERIFIER/src:$A_VERIFIER/third_party/open-r1/src" \
    "$RUNTIME_PY" - "$A_VERIFIER" "$DATASET_DIR" <<'PY_DATASET'
import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.evaluation.evaluate import dataset_hash, load_evaluation_config, load_evaluation_problems

root = Path(sys.argv[1])
dataset = Path(sys.argv[2])
os.chdir(root)
config = replace(load_evaluation_config(root / "configs/eval/base.yaml"), dataset_dir=dataset)
problems = load_evaluation_problems(config)
ids = [problem.problem_id for problem in problems]
order_sha = hashlib.sha256(json.dumps(ids, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
if len(problems) != 400:
    raise SystemExit("eval400 problem count mismatch")
if dataset_hash(problems) != "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae":
    raise SystemExit("eval400 dataset hash mismatch")
if order_sha != "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9":
    raise SystemExit("eval400 ordered problem IDs hash mismatch")
print("dataset_preflight=PASS rows=400")
PY_DATASET
}

check_piston_runtime() {
  env NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
    PYTHONPATH="$A_VERIFIER/src:$A_VERIFIER/third_party/open-r1/src" \
    "$RUNTIME_PY" - "$A_VERIFIER" <<'PY_PISTON'
import os
import sys
from pathlib import Path
from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config

root = Path(sys.argv[1])
os.chdir(root)
config = load_piston_executor_config(root / "configs/execution/piston-local.yaml")
PistonExecutor(config).validate_runtime()
print("piston_preflight=PASS endpoint=127.0.0.1:2000")
PY_PISTON
}

run_preflight() {
  mkdir -p "$OP_ROOT"
  [[ -x "$RUNTIME_PY" ]] || fail_preflight "runtime Python unavailable" || return $?
  [[ -d "$DATASET_DIR" ]] || fail_preflight "canonical eval400 dataset directory unavailable" || return $?
  [[ -f "$A_EVIDENCE" && -f "$B_EVIDENCE" ]] || fail_preflight "synced operator evidence missing" || return $?
  check_control_identity || return $?
  check_verifier_checkout "$A_VERIFIER" "$A_COMMIT" || return $?
  check_verifier_checkout "$B_VERIFIER" "$B_COMMIT" || return $?
  check_dataset_identity || return $?
  check_synced_source_hashes || fail_preflight "synced source SHA/identity postcheck failed" || return $?
  strict_bundle_preflight "$B_VERIFIER" "$B_SOURCE_ROOT/$B_RUN" || fail_preflight "strict B bundle load failed" || return $?
  local a_paths=()
  local name
  for name in "${A_RUNS[@]}"; do
    a_paths+=("$A_SOURCE_ROOT/$name")
  done
  strict_bundle_preflight "$A_VERIFIER" "${a_paths[@]}" || fail_preflight "strict Recipe A bundle load failed" || return $?
  check_piston_runtime || fail_preflight "local Piston runtime acceptance failed" || return $?
  "$RUNTIME_PY" - "$OUTPUT_ROOT" <<'PY_STORAGE'
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
if shutil.disk_usage(root).free < 1024**3:
    raise SystemExit("less than 1 GiB free for WP9-d eval400 verification")
print("storage_preflight=PASS")
PY_STORAGE
  [[ $? -eq 0 ]] || fail_preflight "verification output storage preflight failed" || return $?
  printf 'WP9-d unified eval400 preflight PASS: bundles=9 rows=3600 workers=%s\n' "$WORKERS"
}

write_evidence() {
  local command_rc="$1"
  local postcheck_rc="$2"
  local gate_status="$3"
  local note="$4"
  local end_time head script_sha manifest_sha
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown')"
  script_sha="$(sha256_file "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null || true)"
  manifest_sha=""
  if [[ -f "$MANIFEST_FILE" ]]; then
    manifest_sha="$(sha256_file "$MANIFEST_FILE")"
  fi
  "$RUNTIME_PY" - "$EVIDENCE_FILE.tmp" "$head" "$script_sha" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" "$manifest_sha" <<'PY_EVIDENCE'
import json
import socket
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
    manifest_sha,
) = sys.argv[1:]
payload = {
    "schema_version": "wp9d-eval400-unified-verification-operator-evidence-v1",
    "operator_handoff_mode": "control_plane_manual",
    "stage_id": "WP9-d",
    "gate_id": "wp9d-eval400-unified-verify",
    "checkpoint_id": "C0",
    "operator_checkpoint_commit": checkpoint_commit,
    "operator_script": "ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C0/run.sh",
    "operator_script_sha256": script_sha,
    "control_plane_hardware": "GTX 1660 Ti (6GB)",
    "hostname": socket.gethostname(),
    "attempt_id": attempt_id,
    "started_at": start_time,
    "ended_at": end_time,
    "command_rc": int(command_rc),
    "postcheck_rc": int(postcheck_rc),
    "gate_status": gate_status,
    "note": note,
    "verification_workers": 64,
    "seed": 42,
    "dataset_sha256": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "eval_config_sha256": "3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "dependency_lock_sha256": "4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf",
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "b_verifier_commit": "07ccc71968bedc25b1a8fd15aa0ee35a75e05389",
    "a_verifier_commit": "f17b4f607daa3bb03b08682bbbd841118d36c4af",
    "b_generation_root": "/home/dzy/wp9d-b-refresh-eval400/generation",
    "a_generation_root": "/home/dzy/wp9d-recipe-a-eval400-f17b4f6/generation",
    "verification_output_root": "/home/dzy/wp9d-eval400-verified",
    "verification_manifest_sha256": manifest_sha or None,
    "expected_bundles": 9,
    "expected_results": 3600,
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  local final_rc=1
  if [[ "$gate_status" == "passed" && "$command_rc" == "0" && "$postcheck_rc" == "0" ]]; then
    final_rc=0
  elif [[ "$command_rc" =~ ^[0-9]+$ ]] && (( command_rc > 0 && command_rc < 126 )); then
    final_rc="$command_rc"
  fi
  printf '%s\n' "$final_rc" >"$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  log "attempt=$ATTEMPT_ID end command_rc=$command_rc postcheck_rc=$postcheck_rc gate_status=$gate_status note=$note"
  return "$final_rc"
}

verify_one() {
  local verifier="$1"
  local generation_run="$2"
  local run_name="$3"
  local run_dir="$OUTPUT_ROOT/evaluation/$run_name"
  local rc

  log "verify start run=$run_name workers=$WORKERS verifier=$(basename "$verifier")"
  (
    cd "$verifier" || exit 125
    env NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
      PYTHONPATH="$verifier/src:$verifier/third_party/open-r1/src" \
      "$RUNTIME_PY" -m code_verifier.cli verify-eval \
        --config "$verifier/configs/eval/base.yaml" \
        --dataset-dir "$DATASET_DIR" \
        --generation-run-dir "$generation_run" \
        --run-name "$run_name" \
        --seed "$SEED" \
        --workers "$WORKERS" \
        --output-dir "$OUTPUT_ROOT"
  ) 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}
  log "verify end run=$run_name rc=$rc"
  [[ "$rc" -eq 0 ]] || return "$rc"

  if [[ -f "$run_dir/summary.json" && -f "$run_dir/main_results.csv" ]]; then
    log "aggregate reuse run=$run_name existing summary/main_results"
    return 0
  fi
  if [[ -e "$run_dir/summary.json" || -e "$run_dir/main_results.csv" ]]; then
    log "aggregate FAIL run=$run_name partial derived artifacts already exist"
    return 125
  fi

  log "aggregate start run=$run_name"
  (
    cd "$verifier" || exit 125
    env PYTHONPATH="$verifier/src:$verifier/third_party/open-r1/src" \
      "$RUNTIME_PY" -m code_verifier.cli aggregate-eval \
        --run-dir "$run_dir" \
        --seed "$SEED"
  ) 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}
  log "aggregate end run=$run_name rc=$rc"
  return "$rc"
}

strict_postcheck() {
  "$RUNTIME_PY" - "$OUTPUT_ROOT" "$A_SOURCE_ROOT" "$B_SOURCE_ROOT" "$MANIFEST_FILE" <<'PY_POST'
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path

OUTPUT, A_ROOT, B_ROOT, MANIFEST = map(Path, sys.argv[1:])
DATASET_SHA = "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
ORDER_SHA = "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
PISTON_SHA = "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
OPEN_R1 = "1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEP = "4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf"
A_COMMIT = "f17b4f607daa3bb03b08682bbbd841118d36c4af"
B_COMMIT = "07ccc71968bedc25b1a8fd15aa0ee35a75e05389"
EXPECTED = [
    ("wp9d-B-eval400-b4-p1-seed42", B_ROOT, B_COMMIT, "9bd47fff5c36216ede0e33c087ea98946198f6d131ff780794135aa655eb9c02"),
    ("wp9d-A-public-step300-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "6536ee10e4cc9ad3bf84e39bc8223a366d49b059fad921fcdd9d03f7d95133db"),
    ("wp9d-A-public-step600-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "39967983a63cb4f22de2f0f9f21172ebd169a7e89f910977a05d465e8e455119"),
    ("wp9d-A-public-step900-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "33ad1c81a9f3ee63e46d6b300753c6c63157cdd44b52a6d8e4abff989f55a85f"),
    ("wp9d-A-public-step1200-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "957beb9f6ff56a7ba3459127f319c506ccafaddbe066684941782b66c0c40af1"),
    ("wp9d-A-hidden-step300-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c"),
    ("wp9d-A-hidden-step600-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "93a5d0bf1811d226328661c193bd3498ad99c36e37d659e23da947294c920fa4"),
    ("wp9d-A-hidden-step900-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "79046932a512f083383ab01a7f6c4b8c0d11531470f12aa45f1001c9fbdb76f3"),
    ("wp9d-A-hidden-step1200-eval400-b4-p1-seed42", A_ROOT, A_COMMIT, "07d27f5ddc3fd4e64979acd4b875db5191ab7f485da66d6054a053cc8ed528d5"),
]

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_jsonl(path: Path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise SystemExit(f"JSONL row is not an object: {path}")
                rows.append(value)
    return rows

def finite_tree(value):
    if isinstance(value, bool) or value is None or isinstance(value, str) or isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_tree(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_tree(item) for key, item in value.items())
    return False

manifest_runs = []
for name, source_root, project_commit, generation_records_sha in EXPECTED:
    source = source_root / name
    run_dir = OUTPUT / "evaluation" / name
    run_json = run_dir / "run.json"
    results_path = run_dir / "samples" / "results.jsonl"
    summary_path = run_dir / "summary.json"
    csv_path = run_dir / "main_results.csv"
    for required in (run_json, results_path, summary_path, csv_path):
        if not required.is_file() or required.stat().st_size == 0:
            raise SystemExit(f"missing/empty verification artifact: {required}")

    metadata = json.loads(run_json.read_text(encoding="utf-8"))
    expected_meta = {
        "status": "completed",
        "run_id": name,
        "command": "code-verifier verify-eval",
        "seed": 42,
        "verification_workers": 64,
        "project_commit": project_commit,
        "open_r1_commit": OPEN_R1,
        "dependency_lock_hash": DEP,
        "dataset_hash": DATASET_SHA,
        "piston_config_sha256": PISTON_SHA,
        "generation_bundle_records_sha256": generation_records_sha,
        "generation_bundle_ordered_problem_ids_sha256": ORDER_SHA,
        "generation_batch_size": 4,
    }
    for key, wanted in expected_meta.items():
        if metadata.get(key) != wanted:
            raise SystemExit(f"verification run identity mismatch: {name}: {key}")

    generations = load_jsonl(source / "samples" / "generations.jsonl")
    results = load_jsonl(results_path)
    if len(generations) != 400 or len(results) != 400:
        raise SystemExit(f"verification row count mismatch: {name}")
    generation_ids = [row.get("problem_id") for row in generations]
    result_ids = [row.get("problem_id") for row in results]
    if result_ids != generation_ids or len(set(result_ids)) != 400:
        raise SystemExit(f"verification problem order/uniqueness mismatch: {name}")
    for index, (generation, result) in enumerate(zip(generations, results, strict=True), start=1):
        for key in ("problem_id", "prompt_hash", "completion", "completion_tokens", "generation_latency_ms", "hit_max_new_tokens"):
            if result.get(key) != generation.get(key):
                raise SystemExit(f"frozen generation payload drift: {name}: row={index}: field={key}")
        for key in ("execution_status", "visible_execution_status", "train_hidden_execution_status", "eval_hidden_execution_status"):
            if result.get(key) == "sandbox_error":
                raise SystemExit(f"Piston sandbox/infrastructure failure: {name}: row={index}: field={key}")
        for key in ("visible_failure_counts", "train_hidden_failure_counts", "eval_hidden_failure_counts"):
            counts = result.get(key)
            if isinstance(counts, dict) and counts.get("sandbox_error", 0):
                raise SystemExit(f"Piston sandbox/infrastructure failure count: {name}: row={index}: field={key}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not finite_tree(summary):
        raise SystemExit(f"non-finite aggregate summary: {name}")
    if summary.get("schema_version") != 1 or summary.get("run_id") != name:
        raise SystemExit(f"aggregate summary identity mismatch: {name}")
    if summary.get("dataset_hash") != DATASET_SHA or summary.get("seed") != 42 or summary.get("project_commit") != project_commit:
        raise SystemExit(f"aggregate summary provenance mismatch: {name}")
    bootstrap = summary.get("bootstrap", {})
    if bootstrap != {"seed": 42, "resamples": 10000, "confidence_level": 0.95}:
        raise SystemExit(f"aggregate bootstrap contract mismatch: {name}")
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("total_problems") != 400:
        raise SystemExit(f"aggregate metrics count mismatch: {name}")
    for key in ("visible_pass@1", "train_hidden_pass@1", "eval_hidden_pass@1", "eval_hidden_average_test_pass_rate", "runtime_error_rate", "parse_success_rate"):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise SystemExit(f"aggregate metric invalid: {name}: {key}")

    with csv_path.open(newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    if len(csv_rows) != 1 or csv_rows[0].get("run_id") != name:
        raise SystemExit(f"main_results.csv identity mismatch: {name}")

    manifest_runs.append({
        "run_name": name,
        "verifier_project_commit": project_commit,
        "generation_records_sha256": generation_records_sha,
        "evaluation_run_json_sha256": sha(run_json),
        "evaluation_results_sha256": sha(results_path),
        "summary_sha256": sha(summary_path),
        "main_results_sha256": sha(csv_path),
        "metrics": {
            "visible_pass@1": metrics["visible_pass@1"],
            "train_hidden_pass@1": metrics["train_hidden_pass@1"],
            "eval_hidden_pass@1": metrics["eval_hidden_pass@1"],
            "eval_hidden_average_test_pass_rate": metrics["eval_hidden_average_test_pass_rate"],
            "runtime_error_rate": metrics["runtime_error_rate"],
            "parse_success_rate": metrics["parse_success_rate"],
        },
    })

payload = {
    "schema_version": "wp9d-eval400-unified-verification-manifest-v1",
    "dataset_sha256": DATASET_SHA,
    "ordered_problem_ids_sha256": ORDER_SHA,
    "piston_config_sha256": PISTON_SHA,
    "verification_workers": 64,
    "seed": 42,
    "bundle_count": 9,
    "result_count": 3600,
    "runs": manifest_runs,
}
content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
if MANIFEST.exists():
    if MANIFEST.read_text(encoding="utf-8") != content:
        raise SystemExit("existing verification manifest does not match strict recomputation")
else:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".verification-manifest.", suffix=".tmp", dir=MANIFEST.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, MANIFEST)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
print("formal_postcheck=PASS bundles=9 records=3600 workers=64 sandbox_errors=0 aggregation=PASS")
PY_POST
}

run_verify() {
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
  log "attempt=$ATTEMPT_ID start gate=wp9d-eval400-unified-verify bundles=9 workers=$WORKERS"

  run_preflight >>"$LOG_FILE" 2>&1
  local rc=$?
  if [[ "$rc" -ne 0 ]]; then
    write_evidence 125 125 preflight_failed "unified eval400 verification preflight failed"
    exit $?
  fi
  log "preflight PASS"

  verify_one "$B_VERIFIER" "$B_SOURCE_ROOT/$B_RUN" "$B_RUN"
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    write_evidence "$rc" 125 command_failed "B verify-eval/aggregate-eval failed"
    exit $?
  fi

  local name
  for name in "${A_RUNS[@]}"; do
    verify_one "$A_VERIFIER" "$A_SOURCE_ROOT/$name" "$name"
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
      write_evidence "$rc" 125 command_failed "Recipe A verify-eval/aggregate-eval failed at $name"
      exit $?
    fi
  done

  log "strict postcheck start"
  strict_postcheck 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}
  if [[ "$rc" -ne 0 ]]; then
    write_evidence 0 "$rc" postcheck_failed "strict 9-run verification/aggregation postcheck failed"
    exit $?
  fi
  log "strict postcheck PASS"
  write_evidence 0 0 passed "B + Recipe A 8 eval400 bundles verified and aggregated on local Piston; 3600 ordered results; zero sandbox errors"
  exit $?
}

case "$MODE" in
  preflight)
    mkdir -p "$OP_ROOT"
    run_preflight
    ;;
  verify)
    run_verify
    ;;
  *)
    usage
    ;;
esac
