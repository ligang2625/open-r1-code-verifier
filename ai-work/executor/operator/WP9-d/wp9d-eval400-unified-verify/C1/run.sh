#!/usr/bin/env bash
set -uo pipefail

MODE="${1:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C1/run.sh"
EXPECTED_PARENT="8717f6032c27117facbd996b7bce3ba8ec328143"

VERIFIER="/home/dzy/wp9d-verifier-a-f17b4f6"
VERIFIER_COMMIT="f17b4f607daa3bb03b08682bbbd841118d36c4af"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEPENDENCY_LOCK_SHA="4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf"

DATASET_DIR="/home/dzy/wp6d-b-export/required/formal-data/prepared"
DATASET_SHA="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
ORDER_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
PISTON_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
WORKERS=64
SEED=42

RUN_NAME="wp9d-A-hidden-step300-eval400-b4-p1-seed42"
GENERATION_RUN="/home/dzy/wp9d-recipe-a-eval400-f17b4f6/generation/$RUN_NAME"
GENERATION_RUN_SHA="e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120"
GENERATION_RECORDS_SHA="8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c"

C0_OP="/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C0"
C0_RESULTS_ROOT="/home/dzy/wp9d-eval400-verified/evaluation"
C0_EVIDENCE_SHA="92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1"
C0_LOG_SHA="c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee"
C0_FAILED_RESULTS_SHA="a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f"

RETRY_TAG="${WP9D_VERIFY_REPAIR_TAG:-}"
if [[ -n "$RETRY_TAG" && ! "$RETRY_TAG" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$ ]]; then
  echo "WP9D_VERIFY_REPAIR_TAG must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$" >&2
  exit 64
fi
OUTPUT_ROOT="/home/dzy/wp9d-eval400-repair-c1${RETRY_TAG:+-$RETRY_TAG}"
REPAIR_RUN="$OUTPUT_ROOT/evaluation/$RUN_NAME"
FINAL_MANIFEST="$OUTPUT_ROOT/final-verification-manifest.json"

OP_ROOT="/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C1"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOCK_FILE="$OP_ROOT/run.lock"
RUNTIME_PY="/home/dzy/open-r1-code-verifier/.venv/bin/python"

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh preflight
  run.sh repair

required environment:
  WP9D_REPAIR_HANDOFF_COMMIT=<exact committed C1 operator checkpoint>
  WP9D_REPAIR_SCRIPT_SHA256=<sha256 of this tracked run.sh>

optional retry namespace after a failed completed C1 verification:
  WP9D_VERIFY_REPAIR_TAG=<safe short tag>

C1 preserves the failed C0 evidence/results, reruns the full 400-problem Hidden-step300
verification into a fresh external namespace, aggregates that repaired run, then combines it
with the eight byte-frozen clean C0 runs into one final 9-run manifest. It never generates
model output and never contacts an RTX 4090.
EOF
  exit 64
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"
}

fail_preflight() {
  local message="$1"
  printf 'preflight FAIL: %s\n' "$message" >&2
  return 125
}

check_control_identity() {
  local handoff="${WP9D_REPAIR_HANDOFF_COMMIT:-}"
  local expected_script_sha="${WP9D_REPAIR_SCRIPT_SHA256:-}"
  local head parent actual_sha dirty
  [[ "$handoff" =~ ^[0-9a-f]{40}$ ]] || fail_preflight "set WP9D_REPAIR_HANDOFF_COMMIT to the exact C1 checkpoint" || return $?
  [[ "$expected_script_sha" =~ ^[0-9a-f]{64}$ ]] || fail_preflight "set WP9D_REPAIR_SCRIPT_SHA256 to the exact tracked script SHA256" || return $?
  head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve control-plane HEAD" || return $?
  parent="$(git -C "$REPO_ROOT" rev-parse HEAD^ 2>/dev/null)" || fail_preflight "cannot resolve C1 parent" || return $?
  [[ "$head" == "$handoff" ]] || fail_preflight "control-plane HEAD does not equal WP9D_REPAIR_HANDOFF_COMMIT" || return $?
  [[ "$parent" == "$EXPECTED_PARENT" ]] || fail_preflight "C1 parent does not equal accepted failed C0 operator commit" || return $?
  actual_sha="$(sha256_file "$REPO_ROOT/$SCRIPT_REL")"
  [[ "$actual_sha" == "$expected_script_sha" ]] || fail_preflight "tracked C1 run.sh SHA256 mismatch" || return $?
  dirty="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal | grep -vE '^\?\? \.ai-bridge/' || true)"
  [[ -z "$dirty" ]] || fail_preflight "control-plane worktree must be clean outside .ai-bridge" || return $?
}

check_verifier() {
  local head open_r1 dirty
  [[ -d "$VERIFIER" ]] || fail_preflight "missing detached Recipe A verifier worktree" || return $?
  head="$(git -C "$VERIFIER" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve verifier HEAD" || return $?
  [[ "$head" == "$VERIFIER_COMMIT" ]] || fail_preflight "Recipe A verifier commit mismatch" || return $?
  open_r1="$(git -C "$VERIFIER/third_party/open-r1" rev-parse HEAD 2>/dev/null)" || fail_preflight "cannot resolve verifier Open-R1 HEAD" || return $?
  [[ "$open_r1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "verifier Open-R1 commit mismatch" || return $?
  dirty="$(git -C "$VERIFIER" status --porcelain=v1 --untracked-files=normal --ignore-submodules=none)"
  [[ -z "$dirty" ]] || fail_preflight "Recipe A verifier worktree is not clean" || return $?
  [[ "$(sha256_file "$VERIFIER/configs/eval/base.yaml")" == "$EVAL_CONFIG_SHA" ]] || fail_preflight "eval config SHA mismatch" || return $?
  [[ "$(sha256_file "$VERIFIER/configs/execution/piston-local.yaml")" == "$PISTON_SHA" ]] || fail_preflight "Piston definition SHA mismatch" || return $?
}

check_frozen_c0_and_generation() {
  "$RUNTIME_PY" - "$C0_OP" "$C0_RESULTS_ROOT" "$GENERATION_RUN" <<'PY_C0'
import hashlib
import json
import sys
from pathlib import Path

op, c0_root, generation = map(Path, sys.argv[1:])
EXPECTED_C0_EVIDENCE_SHA = "92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1"
EXPECTED_C0_LOG_SHA = "c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee"
EXPECTED_GENERATION_RUN_SHA = "e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120"
EXPECTED_GENERATION_RECORDS_SHA = "8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c"
FAILED = "wp9d-A-hidden-step300-eval400-b4-p1-seed42"
CLEAN = {
    "wp9d-B-eval400-b4-p1-seed42": (
        "a7816b606504e0c45d19c1a684533cfc9dc28c1f01f6e1b0fd13886090eed232",
        "adad4e09f79e92d74c8438db66bb77e8b6a688d1aa91f7e6b03927fcc851fd3a",
        "e2284c2f30dd691c0abdd6f752d8ab0c9f0f60eed394ab7c399c733e60816327",
        "5c7471bb5a4e1d0e81ce8a8c0a1918fbd6659d14df52f8c01bce05bb95419487",
    ),
    "wp9d-A-public-step300-eval400-b4-p1-seed42": (
        "2f78060d3d7d6e08bb455d9dd7d0306edfeeeb9c0d5d67aebb122f0a44718968",
        "671a1fc6a2691b3c9e22baa94d284865bc8ccbce027f5e4e8161b11dc6b201d9",
        "0e544be88e1fce9778a0645ef2944f7bf8f771be1be4715dcbd6bda59a98b8c1",
        "31ead1304714d9271c0505bf37009991656543fe3c9c3c18a147f129fc807fc8",
    ),
    "wp9d-A-public-step600-eval400-b4-p1-seed42": (
        "d6a57674530a3021d1cdba5eabcf72e2873ad1855af7b005ecb23645b02eefda",
        "e4fea29ab783c59c251f4d642e74269cbbf065b8c08155afbe39e82c65800e38",
        "6e41c45d8204286c48a082cc7e2a9d0daaf2dbb1d1ddd3d4816cc2c6c56883cb",
        "d48a3df5cf5a3d1d9ddc0f15e178f331f8f6d3cb047e224af87bdb41e05d16d8",
    ),
    "wp9d-A-public-step900-eval400-b4-p1-seed42": (
        "6048d4025a6474597710a79c8a3bbb41acd41de412f729b8f764745b9be9679b",
        "eb4e30828eec4d658b0f38222a55149e8e8bd78405ded189f6b2d0beff8815fa",
        "0e7bf455f2e226cfd1b78a4b2c535bf724a66d8539a61eb486f7a4481b0ee076",
        "8ee1a9c45a180aa5052c3367b5b26d30b344c5a33475c4a831429ae5c197afda",
    ),
    "wp9d-A-public-step1200-eval400-b4-p1-seed42": (
        "2e53cfb3a30b17db45fe0f5ce6449d153a3f750ee656c095f61afb7e917ac6fb",
        "56dea4eb7b338febd87ea4575c136e3cc7ee5dacae792796bcee19fa548369fc",
        "9541d0a44119efa142d453c18abb13a030bf1adf20d16af77659e04f81fe23ce",
        "f5f7e5d2563d6bef0630bc2150f2ab80169d2c280c7bb07e93369072874ff975",
    ),
    "wp9d-A-hidden-step600-eval400-b4-p1-seed42": (
        "312ca538dac43120ad150a27d38a390d99134ffe06625f2adf99a9ec1d0ecd27",
        "72625da6e7bd11e314fa202d77b421cae764eab06347d23ad2209fa28cb307de",
        "5ef4a60ee05bc331febc3917cebef4d07558962d0bc6c184302c79e3fa6f2810",
        "2770c0e2f8c2ccb4e678c0bc5bc1bbdd85df08c63c215b5bc3ad88d7498a4a41",
    ),
    "wp9d-A-hidden-step900-eval400-b4-p1-seed42": (
        "6c168ff63d7d47423e0644efe8a63f05f91c82b24d2f1b1f2665e477466d2003",
        "274abdb79b2ad155ec8c81c4c81605299862e0f4a1ee38e247d6cc7730b35b75",
        "17a5bc175a7ecb113e782130930191ae27641c76620899e1d8b4618baadd5cb7",
        "81bc72937f988c9b212fbff30c7f57ebc3433771d933b5b07ea4b8f16c2d9fe6",
    ),
    "wp9d-A-hidden-step1200-eval400-b4-p1-seed42": (
        "80ace33594992ef73c7522c8a1dc0c924fbeb2b23e8d1277bb1e9804c3c78b49",
        "fc06ddd7aa58b883a11bf044069440d3341b6ddd2ba34e08514eb3db0910c397",
        "844bd4d0d4e687c3176ee228e83b23e6c69364005947535693c48fb0e21aa482",
        "dcbf954491bfb8fd87e6fb198fb1b7e64b49ba09a2964eb7347ee3c44b4f8c44",
    ),
}
FAILED_HASHES = (
    "7df662c199dbf9a92ecebc6f44f807cb97a5f2951abc1af6671bed782034dcb6",
    "a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f",
    "b3ac5a91a17f9da923cf9daee6c5178aa0a1bda6e030f4bcc174fdc71e2b4332",
    "475d0dac2b1f3d183a54659dd27838d3e70de70ee14a48d0e91ed0925562b04d",
)

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def sandbox(row: dict) -> bool:
    status_keys = ("execution_status", "visible_execution_status", "train_hidden_execution_status", "eval_hidden_execution_status")
    count_keys = ("visible_failure_counts", "train_hidden_failure_counts", "eval_hidden_failure_counts")
    return any(row.get(k) == "sandbox_error" for k in status_keys) or any(
        isinstance(row.get(k), dict) and row[k].get("sandbox_error", 0) for k in count_keys
    )

if (op / "status").read_text(encoding="utf-8").strip() != "1":
    raise SystemExit("C0 terminal status is no longer the frozen failure status 1")
if sha(op / "operator-evidence.json") != EXPECTED_C0_EVIDENCE_SHA:
    raise SystemExit("C0 operator evidence SHA drifted")
if sha(op / "terminal.log") != EXPECTED_C0_LOG_SHA:
    raise SystemExit("C0 terminal log SHA drifted")
evidence = json.loads((op / "operator-evidence.json").read_text(encoding="utf-8"))
if evidence.get("gate_status") != "postcheck_failed" or evidence.get("command_rc") != 0 or evidence.get("postcheck_rc") != 1:
    raise SystemExit("C0 failure identity drifted")

if sha(generation / "run.json") != EXPECTED_GENERATION_RUN_SHA or sha(generation / "samples" / "generations.jsonl") != EXPECTED_GENERATION_RECORDS_SHA:
    raise SystemExit("frozen Hidden300 generation bundle SHA drifted")
generation_meta = json.loads((generation / "run.json").read_text(encoding="utf-8"))
for key, expected in {
    "status": "completed",
    "completed_records": 400,
    "total_problems": 400,
    "batch_size": 4,
    "parallel_generators": 1,
    "project_commit": "f17b4f607daa3bb03b08682bbbd841118d36c4af",
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "seed": 42,
}.items():
    if generation_meta.get(key) != expected:
        raise SystemExit(f"frozen Hidden300 generation identity drifted: {key}")

for name, expected_hashes in CLEAN.items():
    run = c0_root / name
    paths = (run / "run.json", run / "samples" / "results.jsonl", run / "summary.json", run / "main_results.csv")
    if tuple(sha(path) for path in paths) != expected_hashes:
        raise SystemExit(f"clean C0 artifact SHA drifted: {name}")
    result_rows = rows(paths[1])
    if len(result_rows) != 400 or any(sandbox(row) for row in result_rows):
        raise SystemExit(f"clean C0 run is no longer clean 400-row evidence: {name}")

failed = c0_root / FAILED
failed_paths = (failed / "run.json", failed / "samples" / "results.jsonl", failed / "summary.json", failed / "main_results.csv")
if tuple(sha(path) for path in failed_paths) != FAILED_HASHES:
    raise SystemExit("failed Hidden300 C0 artifact SHA drifted")
failed_rows = rows(failed_paths[1])
issues = [(index, row.get("problem_id")) for index, row in enumerate(failed_rows, start=1) if sandbox(row)]
if issues != [
    (55, "leetcode-earliest-possible-day-of-full-bloom"),
    (59, "leetcode-expressive-words"),
]:
    raise SystemExit(f"C0 Hidden300 failure fingerprint drifted: {issues!r}")
print("frozen_c0_preflight=PASS clean_runs=8 failed_run=1 failed_sandbox_rows=2")
PY_C0
}

check_bundle_identity() {
  env PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" \
    "$RUNTIME_PY" - "$VERIFIER" "$DATASET_DIR" "$GENERATION_RUN" <<'PY_BUNDLE'
import os
import sys
from dataclasses import replace
from pathlib import Path
from code_verifier.environment import collect_environment
from code_verifier.evaluation.evaluate import dataset_hash, load_evaluation_config, load_evaluation_problems
from code_verifier.evaluation.staged import load_completed_generation_bundle, load_generation_bundle_source

root, dataset, run = map(Path, sys.argv[1:])
os.chdir(root)
env = collect_environment()
for key, expected in {
    "project_commit": "f17b4f607daa3bb03b08682bbbd841118d36c4af",
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "dependency_lock_hash": "4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf",
}.items():
    if env.get(key) != expected:
        raise SystemExit(f"verifier environment mismatch: {key}")
source = load_generation_bundle_source(run)
config = replace(
    load_evaluation_config(root / "configs/eval/base.yaml"),
    dataset_dir=dataset,
    model_revision=source.model_revision,
    checkpoint=source.checkpoint,
)
problems = load_evaluation_problems(config)
if len(problems) != 400 or dataset_hash(problems) != "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae":
    raise SystemExit("canonical eval400 dataset identity mismatch")
identity, records = load_completed_generation_bundle(run, config=config, problems=problems, seed=42)
if identity.run_id != run.name or len(records) != 400 or identity.records_sha256 != "8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c":
    raise SystemExit("strict Hidden300 generation bundle identity mismatch")
print("bundle_preflight=PASS rows=400")
PY_BUNDLE
}

check_piston() {
  env NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
    PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" \
    "$RUNTIME_PY" - "$VERIFIER" <<'PY_PISTON'
import os
import sys
from pathlib import Path
from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config
root = Path(sys.argv[1])
os.chdir(root)
PistonExecutor(load_piston_executor_config(root / "configs/execution/piston-local.yaml")).validate_runtime()
print("piston_preflight=PASS endpoint=127.0.0.1:2000")
PY_PISTON
}

run_preflight() {
  mkdir -p "$OP_ROOT"
  [[ -x "$RUNTIME_PY" ]] || fail_preflight "runtime Python unavailable" || return $?
  [[ -d "$DATASET_DIR" ]] || fail_preflight "canonical eval400 dataset unavailable" || return $?
  check_control_identity || return $?
  check_verifier || return $?
  check_frozen_c0_and_generation || fail_preflight "frozen C0/generation evidence validation failed" || return $?
  check_bundle_identity || fail_preflight "strict Hidden300 bundle validation failed" || return $?
  check_piston || fail_preflight "local Piston runtime acceptance failed" || return $?
  "$RUNTIME_PY" - "$OUTPUT_ROOT" <<'PY_STORAGE'
import shutil
import sys
from pathlib import Path
root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
if shutil.disk_usage(root).free < 1024**3:
    raise SystemExit("less than 1 GiB free for C1 repair output")
print("storage_preflight=PASS")
PY_STORAGE
  [[ $? -eq 0 ]] || fail_preflight "repair output storage preflight failed" || return $?
  printf 'WP9-d C1 repair preflight PASS: run=%s rows=400 workers=%s output=%s\n' "$RUN_NAME" "$WORKERS" "$OUTPUT_ROOT"
}

write_evidence() {
  local command_rc="$1"
  local postcheck_rc="$2"
  local gate_status="$3"
  local note="$4"
  local end_time head script_sha manifest_sha run_sha results_sha summary_sha csv_sha
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown')"
  script_sha="$(sha256_file "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null || true)"
  manifest_sha=""; run_sha=""; results_sha=""; summary_sha=""; csv_sha=""
  [[ -f "$FINAL_MANIFEST" ]] && manifest_sha="$(sha256_file "$FINAL_MANIFEST")"
  [[ -f "$REPAIR_RUN/run.json" ]] && run_sha="$(sha256_file "$REPAIR_RUN/run.json")"
  [[ -f "$REPAIR_RUN/samples/results.jsonl" ]] && results_sha="$(sha256_file "$REPAIR_RUN/samples/results.jsonl")"
  [[ -f "$REPAIR_RUN/summary.json" ]] && summary_sha="$(sha256_file "$REPAIR_RUN/summary.json")"
  [[ -f "$REPAIR_RUN/main_results.csv" ]] && csv_sha="$(sha256_file "$REPAIR_RUN/main_results.csv")"
  "$RUNTIME_PY" - "$EVIDENCE_FILE.tmp" "$head" "$script_sha" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" "$RETRY_TAG" "$OUTPUT_ROOT" "$manifest_sha" "$run_sha" "$results_sha" "$summary_sha" "$csv_sha" <<'PY_EVIDENCE'
import json
import socket
import sys
from pathlib import Path
(
    output, checkpoint_commit, script_sha, command_rc, postcheck_rc, gate_status, note,
    start_time, end_time, attempt_id, retry_tag, output_root, manifest_sha,
    run_sha, results_sha, summary_sha, csv_sha,
) = sys.argv[1:]
payload = {
    "schema_version": "wp9d-eval400-hidden300-repair-operator-evidence-v1",
    "operator_handoff_mode": "control_plane_manual",
    "stage_id": "WP9-d",
    "gate_id": "wp9d-eval400-unified-verify",
    "checkpoint_id": "C1",
    "operator_checkpoint_commit": checkpoint_commit,
    "operator_script": "ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C1/run.sh",
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
    "retry_tag": retry_tag or None,
    "verification_workers": 64,
    "seed": 42,
    "repair_run_name": "wp9d-A-hidden-step300-eval400-b4-p1-seed42",
    "repair_output_root": output_root,
    "repair_run_json_sha256": run_sha or None,
    "repair_results_sha256": results_sha or None,
    "repair_summary_sha256": summary_sha or None,
    "repair_main_results_sha256": csv_sha or None,
    "final_manifest_sha256": manifest_sha or None,
    "source_c0_operator_commit": "8717f6032c27117facbd996b7bce3ba8ec328143",
    "source_c0_operator_evidence_sha256": "92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1",
    "source_c0_terminal_log_sha256": "c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee",
    "source_c0_failed_results_sha256": "a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f",
    "generation_run_json_sha256": "e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120",
    "generation_records_sha256": "8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c",
    "dataset_sha256": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "eval_config_sha256": "3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3",
    "piston_config_sha256": "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e",
    "verifier_project_commit": "f17b4f607daa3bb03b08682bbbd841118d36c4af",
    "open_r1_commit": "1416fa0cf21595d2083b399a2a0bbddd7f6e9563",
    "dependency_lock_sha256": "4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf",
    "final_bundle_count": 9,
    "final_result_count": 3600,
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

run_verification() {
  local rc
  log "repair verify start run=$RUN_NAME workers=$WORKERS output=$OUTPUT_ROOT"
  (
    cd "$VERIFIER" || exit 125
    env NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
      PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" \
      "$RUNTIME_PY" -m code_verifier.cli verify-eval \
        --config "$VERIFIER/configs/eval/base.yaml" \
        --dataset-dir "$DATASET_DIR" \
        --generation-run-dir "$GENERATION_RUN" \
        --run-name "$RUN_NAME" \
        --seed "$SEED" \
        --workers "$WORKERS" \
        --output-dir "$OUTPUT_ROOT"
  ) 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}
  log "repair verify end run=$RUN_NAME rc=$rc"
  [[ "$rc" -eq 0 ]] || return "$rc"

  if [[ -f "$REPAIR_RUN/summary.json" && -f "$REPAIR_RUN/main_results.csv" ]]; then
    log "repair aggregate reuse run=$RUN_NAME existing summary/main_results"
    return 0
  fi
  if [[ -e "$REPAIR_RUN/summary.json" || -e "$REPAIR_RUN/main_results.csv" ]]; then
    log "repair aggregate FAIL partial derived artifact pair exists"
    return 125
  fi
  log "repair aggregate start run=$RUN_NAME"
  (
    cd "$VERIFIER" || exit 125
    env PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" \
      "$RUNTIME_PY" -m code_verifier.cli aggregate-eval \
        --run-dir "$REPAIR_RUN" \
        --seed "$SEED"
  ) 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}
  log "repair aggregate end run=$RUN_NAME rc=$rc"
  return "$rc"
}

strict_postcheck() {
  local checkpoint_commit
  checkpoint_commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  "$RUNTIME_PY" - "$C0_OP" "$C0_RESULTS_ROOT" "$GENERATION_RUN" "$REPAIR_RUN" "$FINAL_MANIFEST" "$checkpoint_commit" <<'PY_POST'
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path

c0_op, c0_root, generation, repair, manifest = map(Path, sys.argv[1:6])
checkpoint_commit = sys.argv[6]
RUN_NAME = "wp9d-A-hidden-step300-eval400-b4-p1-seed42"
DATASET_SHA = "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
ORDER_SHA = "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
PISTON_SHA = "f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
A_COMMIT = "f17b4f607daa3bb03b08682bbbd841118d36c4af"
B_COMMIT = "07ccc71968bedc25b1a8fd15aa0ee35a75e05389"
OPEN_R1 = "1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEP = "4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf"
C0_EVIDENCE_SHA = "92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1"
C0_LOG_SHA = "c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee"
C0_FAILED_RESULTS_SHA = "a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f"
GENERATION_RUN_SHA = "e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120"
GENERATION_RECORDS_SHA = "8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c"
CLEAN = {
    "wp9d-B-eval400-b4-p1-seed42": (
        B_COMMIT,
        "a7816b606504e0c45d19c1a684533cfc9dc28c1f01f6e1b0fd13886090eed232",
        "adad4e09f79e92d74c8438db66bb77e8b6a688d1aa91f7e6b03927fcc851fd3a",
        "e2284c2f30dd691c0abdd6f752d8ab0c9f0f60eed394ab7c399c733e60816327",
        "5c7471bb5a4e1d0e81ce8a8c0a1918fbd6659d14df52f8c01bce05bb95419487",
    ),
    "wp9d-A-public-step300-eval400-b4-p1-seed42": (
        A_COMMIT,
        "2f78060d3d7d6e08bb455d9dd7d0306edfeeeb9c0d5d67aebb122f0a44718968",
        "671a1fc6a2691b3c9e22baa94d284865bc8ccbce027f5e4e8161b11dc6b201d9",
        "0e544be88e1fce9778a0645ef2944f7bf8f771be1be4715dcbd6bda59a98b8c1",
        "31ead1304714d9271c0505bf37009991656543fe3c9c3c18a147f129fc807fc8",
    ),
    "wp9d-A-public-step600-eval400-b4-p1-seed42": (
        A_COMMIT,
        "d6a57674530a3021d1cdba5eabcf72e2873ad1855af7b005ecb23645b02eefda",
        "e4fea29ab783c59c251f4d642e74269cbbf065b8c08155afbe39e82c65800e38",
        "6e41c45d8204286c48a082cc7e2a9d0daaf2dbb1d1ddd3d4816cc2c6c56883cb",
        "d48a3df5cf5a3d1d9ddc0f15e178f331f8f6d3cb047e224af87bdb41e05d16d8",
    ),
    "wp9d-A-public-step900-eval400-b4-p1-seed42": (
        A_COMMIT,
        "6048d4025a6474597710a79c8a3bbb41acd41de412f729b8f764745b9be9679b",
        "eb4e30828eec4d658b0f38222a55149e8e8bd78405ded189f6b2d0beff8815fa",
        "0e7bf455f2e226cfd1b78a4b2c535bf724a66d8539a61eb486f7a4481b0ee076",
        "8ee1a9c45a180aa5052c3367b5b26d30b344c5a33475c4a831429ae5c197afda",
    ),
    "wp9d-A-public-step1200-eval400-b4-p1-seed42": (
        A_COMMIT,
        "2e53cfb3a30b17db45fe0f5ce6449d153a3f750ee656c095f61afb7e917ac6fb",
        "56dea4eb7b338febd87ea4575c136e3cc7ee5dacae792796bcee19fa548369fc",
        "9541d0a44119efa142d453c18abb13a030bf1adf20d16af77659e04f81fe23ce",
        "f5f7e5d2563d6bef0630bc2150f2ab80169d2c280c7bb07e93369072874ff975",
    ),
    "wp9d-A-hidden-step600-eval400-b4-p1-seed42": (
        A_COMMIT,
        "312ca538dac43120ad150a27d38a390d99134ffe06625f2adf99a9ec1d0ecd27",
        "72625da6e7bd11e314fa202d77b421cae764eab06347d23ad2209fa28cb307de",
        "5ef4a60ee05bc331febc3917cebef4d07558962d0bc6c184302c79e3fa6f2810",
        "2770c0e2f8c2ccb4e678c0bc5bc1bbdd85df08c63c215b5bc3ad88d7498a4a41",
    ),
    "wp9d-A-hidden-step900-eval400-b4-p1-seed42": (
        A_COMMIT,
        "6c168ff63d7d47423e0644efe8a63f05f91c82b24d2f1b1f2665e477466d2003",
        "274abdb79b2ad155ec8c81c4c81605299862e0f4a1ee38e247d6cc7730b35b75",
        "17a5bc175a7ecb113e782130930191ae27641c76620899e1d8b4618baadd5cb7",
        "81bc72937f988c9b212fbff30c7f57ebc3433771d933b5b07ea4b8f16c2d9fe6",
    ),
    "wp9d-A-hidden-step1200-eval400-b4-p1-seed42": (
        A_COMMIT,
        "80ace33594992ef73c7522c8a1dc0c924fbeb2b23e8d1277bb1e9804c3c78b49",
        "fc06ddd7aa58b883a11bf044069440d3341b6ddd2ba34e08514eb3db0910c397",
        "844bd4d0d4e687c3176ee228e83b23e6c69364005947535693c48fb0e21aa482",
        "dcbf954491bfb8fd87e6fb198fb1b7e64b49ba09a2964eb7347ee3c44b4f8c44",
    ),
}
GEN_PAYLOAD_FIELDS = ("problem_id", "prompt_hash", "completion", "completion_tokens", "generation_latency_ms", "hit_max_new_tokens")
STATUS_FIELDS = ("execution_status", "visible_execution_status", "train_hidden_execution_status", "eval_hidden_execution_status")
COUNT_FIELDS = ("visible_failure_counts", "train_hidden_failure_counts", "eval_hidden_failure_counts")

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def sandbox(row: dict) -> bool:
    return any(row.get(k) == "sandbox_error" for k in STATUS_FIELDS) or any(
        isinstance(row.get(k), dict) and row[k].get("sandbox_error", 0) for k in COUNT_FIELDS
    )

def finite_tree(value):
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_tree(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and finite_tree(v) for k, v in value.items())
    return False

def validate_aggregate(run_dir: Path, project_commit: str):
    summary_path = run_dir / "summary.json"
    csv_path = run_dir / "main_results.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not finite_tree(summary):
        raise SystemExit(f"non-finite aggregate summary: {run_dir.name}")
    if summary.get("schema_version") != 1 or summary.get("run_id") != run_dir.name:
        raise SystemExit(f"aggregate summary identity mismatch: {run_dir.name}")
    if summary.get("dataset_hash") != DATASET_SHA or summary.get("seed") != 42 or summary.get("project_commit") != project_commit:
        raise SystemExit(f"aggregate provenance mismatch: {run_dir.name}")
    if summary.get("bootstrap") != {"seed": 42, "resamples": 10000, "confidence_level": 0.95}:
        raise SystemExit(f"aggregate bootstrap contract mismatch: {run_dir.name}")
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("total_problems") != 400:
        raise SystemExit(f"aggregate problem count mismatch: {run_dir.name}")
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 1 or rows[0].get("run_id") != run_dir.name:
        raise SystemExit(f"main_results.csv identity mismatch: {run_dir.name}")
    return summary, metrics

if sha(c0_op / "operator-evidence.json") != C0_EVIDENCE_SHA or sha(c0_op / "terminal.log") != C0_LOG_SHA:
    raise SystemExit("C0 operator evidence/log drifted during C1 repair")
if (c0_op / "status").read_text(encoding="utf-8").strip() != "1":
    raise SystemExit("C0 operator status drifted during C1 repair")
if sha(generation / "run.json") != GENERATION_RUN_SHA or sha(generation / "samples" / "generations.jsonl") != GENERATION_RECORDS_SHA:
    raise SystemExit("Hidden300 generation bundle drifted during C1 repair")
if sha(c0_root / RUN_NAME / "samples" / "results.jsonl") != C0_FAILED_RESULTS_SHA:
    raise SystemExit("C0 failed Hidden300 results drifted during C1 repair")

# Validate the repaired run itself.
for required in (repair / "run.json", repair / "samples" / "results.jsonl", repair / "summary.json", repair / "main_results.csv"):
    if not required.is_file() or required.stat().st_size == 0:
        raise SystemExit(f"missing/empty repaired artifact: {required}")
meta = json.loads((repair / "run.json").read_text(encoding="utf-8"))
for key, expected in {
    "status": "completed",
    "run_id": RUN_NAME,
    "command": "code-verifier verify-eval",
    "seed": 42,
    "verification_workers": 64,
    "project_commit": A_COMMIT,
    "open_r1_commit": OPEN_R1,
    "dependency_lock_hash": DEP,
    "dataset_hash": DATASET_SHA,
    "piston_config_sha256": PISTON_SHA,
    "generation_bundle_records_sha256": GENERATION_RECORDS_SHA,
    "generation_bundle_ordered_problem_ids_sha256": ORDER_SHA,
    "generation_batch_size": 4,
}.items():
    if meta.get(key) != expected:
        raise SystemExit(f"repaired run identity mismatch: {key}")

gen_rows = load_jsonl(generation / "samples" / "generations.jsonl")
repair_rows = load_jsonl(repair / "samples" / "results.jsonl")
old_rows = load_jsonl(c0_root / RUN_NAME / "samples" / "results.jsonl")
if len(gen_rows) != 400 or len(repair_rows) != 400 or len(old_rows) != 400:
    raise SystemExit("repair comparison requires 400 generation/old/new rows")
if [r.get("problem_id") for r in repair_rows] != [r.get("problem_id") for r in gen_rows] or len({r.get("problem_id") for r in repair_rows}) != 400:
    raise SystemExit("repaired results do not preserve frozen problem order/uniqueness")
for index, (gen, new) in enumerate(zip(gen_rows, repair_rows, strict=True), start=1):
    for key in GEN_PAYLOAD_FIELDS:
        if new.get(key) != gen.get(key):
            raise SystemExit(f"repaired frozen generation payload drift: row={index} field={key}")
    if sandbox(new):
        raise SystemExit(f"repaired run still has sandbox/infrastructure failure: row={index} problem={new.get('problem_id')}")

# On the 398 rows that were not infrastructure failures in C0, verdict semantics must reproduce.
old_bad = {i for i, row in enumerate(old_rows, start=1) if sandbox(row)}
if old_bad != {55, 59}:
    raise SystemExit(f"unexpected frozen C0 sandbox rows: {sorted(old_bad)}")
for index, (old, new) in enumerate(zip(old_rows, repair_rows, strict=True), start=1):
    if index in old_bad:
        continue
    old_sem = {k: v for k, v in old.items() if k != "runtime_ms"}
    new_sem = {k: v for k, v in new.items() if k != "runtime_ms"}
    if old_sem != new_sem:
        raise SystemExit(f"non-infrastructure C0 verdict semantic drift on repair: row={index}")
repair_summary, repair_metrics = validate_aggregate(repair, A_COMMIT)

# Assemble the final accepted set: eight byte-frozen clean C0 runs + C1 repaired Hidden300.
manifest_runs = []
for name, (project_commit, expected_run_sha, expected_results_sha, expected_summary_sha, expected_csv_sha) in CLEAN.items():
    run = c0_root / name
    results = load_jsonl(run / "samples" / "results.jsonl")
    if len(results) != 400 or any(sandbox(row) for row in results):
        raise SystemExit(f"final clean C0 run failed readback: {name}")
    actual_hashes = (
        sha(run / "run.json"),
        sha(run / "samples" / "results.jsonl"),
        sha(run / "summary.json"),
        sha(run / "main_results.csv"),
    )
    expected_hashes = (expected_run_sha, expected_results_sha, expected_summary_sha, expected_csv_sha)
    if actual_hashes != expected_hashes:
        raise SystemExit(f"final clean C0 artifact SHA drift: {name}")
    summary, metrics = validate_aggregate(run, project_commit)
    manifest_runs.append({
        "run_name": name,
        "source": "C0_clean",
        "verifier_project_commit": project_commit,
        "results_sha256": sha(run / "samples" / "results.jsonl"),
        "run_json_sha256": sha(run / "run.json"),
        "summary_sha256": sha(run / "summary.json"),
        "main_results_sha256": sha(run / "main_results.csv"),
        "metrics": {
            "visible_pass@1": metrics["visible_pass@1"],
            "train_hidden_pass@1": metrics["train_hidden_pass@1"],
            "eval_hidden_pass@1": metrics["eval_hidden_pass@1"],
            "eval_hidden_average_test_pass_rate": metrics["eval_hidden_average_test_pass_rate"],
            "runtime_error_rate": metrics["runtime_error_rate"],
            "parse_success_rate": metrics["parse_success_rate"],
        },
    })
manifest_runs.append({
    "run_name": RUN_NAME,
    "source": "C1_full_400_repair",
    "verifier_project_commit": A_COMMIT,
    "results_sha256": sha(repair / "samples" / "results.jsonl"),
    "run_json_sha256": sha(repair / "run.json"),
    "summary_sha256": sha(repair / "summary.json"),
    "main_results_sha256": sha(repair / "main_results.csv"),
    "metrics": {
        "visible_pass@1": repair_metrics["visible_pass@1"],
        "train_hidden_pass@1": repair_metrics["train_hidden_pass@1"],
        "eval_hidden_pass@1": repair_metrics["eval_hidden_pass@1"],
        "eval_hidden_average_test_pass_rate": repair_metrics["eval_hidden_average_test_pass_rate"],
        "runtime_error_rate": repair_metrics["runtime_error_rate"],
        "parse_success_rate": repair_metrics["parse_success_rate"],
    },
})
manifest_runs.sort(key=lambda item: item["run_name"])
payload = {
    "schema_version": "wp9d-eval400-final-verification-manifest-v1",
    "repair_checkpoint_commit": checkpoint_commit,
    "source_c0_operator_commit": "8717f6032c27117facbd996b7bce3ba8ec328143",
    "source_c0_operator_evidence_sha256": C0_EVIDENCE_SHA,
    "source_c0_failed_hidden300_results_sha256": C0_FAILED_RESULTS_SHA,
    "repair_policy": "full_400_rerun_no_row_patch",
    "dataset_sha256": DATASET_SHA,
    "ordered_problem_ids_sha256": ORDER_SHA,
    "piston_config_sha256": PISTON_SHA,
    "verification_workers": 64,
    "seed": 42,
    "bundle_count": 9,
    "result_count": 3600,
    "sandbox_error_rows": 0,
    "runs": manifest_runs,
}
content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
if manifest.exists():
    if manifest.read_text(encoding="utf-8") != content:
        raise SystemExit("existing final repair manifest differs from strict recomputation")
else:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".final-verification-manifest.", suffix=".tmp", dir=manifest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, manifest)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
print("formal_repair_postcheck=PASS bundles=9 records=3600 repaired_run=hidden-step300 repaired_rows=400 sandbox_errors=0 aggregation=PASS")
PY_POST
}

run_repair() {
  mkdir -p "$OP_ROOT"
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    echo "operator lock is already held: $LOCK_FILE" >&2
    exit 73
  fi
  ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ -f "$STATUS_FILE" ]]; then cp -a "$STATUS_FILE" "$OP_ROOT/status.before-$ATTEMPT_ID"; fi
  if [[ -f "$EVIDENCE_FILE" ]]; then cp -a "$EVIDENCE_FILE" "$OP_ROOT/operator-evidence.before-$ATTEMPT_ID.json"; fi
  rm -f "$STATUS_FILE.tmp" "$EVIDENCE_FILE.tmp"
  log "attempt=$ATTEMPT_ID start checkpoint=C1 repair_run=$RUN_NAME workers=$WORKERS output=$OUTPUT_ROOT"

  run_preflight >>"$LOG_FILE" 2>&1
  local rc=$?
  if [[ "$rc" -ne 0 ]]; then
    write_evidence 125 125 preflight_failed "C1 Hidden300 full-rerun repair preflight failed"
    exit $?
  fi
  log "preflight PASS"

  run_verification
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    write_evidence "$rc" 125 command_failed "C1 Hidden300 verify-eval/aggregate-eval failed"
    exit $?
  fi

  log "strict repair postcheck start"
  strict_postcheck 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}
  if [[ "$rc" -ne 0 ]]; then
    write_evidence 0 "$rc" postcheck_failed "C1 repaired Hidden300 or final 9-run strict postcheck failed; preserve output and use a fresh retry tag if needed"
    exit $?
  fi
  log "strict repair postcheck PASS"
  write_evidence 0 0 passed "full 400-row Hidden300 repair verified cleanly; final accepted set is eight immutable C0 clean runs plus C1 repaired Hidden300; 3600 results and zero sandbox errors"
  exit $?
}

case "$MODE" in
  preflight)
    mkdir -p "$OP_ROOT"
    run_preflight
    ;;
  repair)
    run_repair
    ;;
  *)
    usage
    ;;
esac
