#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-preflight}"
case "$ACTION" in
  preflight|execute) ;;
  *)
    echo "usage: run_formal_training.sh <preflight|execute>" >&2
    exit 64
    ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
SELECTED_PAIR="$SCRIPT_DIR/run_selected_pair.sh"
RUN_SH="$SCRIPT_DIR/run.sh"
CONCURRENT_BENCHMARK="$SCRIPT_DIR/run_concurrent_benchmark.sh"
CONCURRENT_PAIR="$SCRIPT_DIR/run_concurrent_pair.sh"
[[ -x "$PY" ]] || { echo "target .venv Python is unavailable" >&2; exit 125; }

EXPECTED_SYSTEMS_EVIDENCE_COMMIT="6b49a50e552795ec35bf280fe59c5ff6a25182e8"
EXPECTED_EVAL_BATCH=4
EXPECTED_EVAL_PROBLEMS=200
EXPECTED_CALIBRATION_SHA="5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b"
EXPECTED_ACTIVE_ORDER_SHA="401f854032095cb638637dcf2d1ec000b770cd2d4c78619331f0b13746618c14"
EXPECTED_PUBLIC_SHA="558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c"
EXPECTED_HIDDEN_SHA="9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec"

HANDOFF="${WP9C_HANDOFF_COMMIT:-}"
[[ "$HANDOFF" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9C_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$HANDOFF" ]] || { echo "target HEAD differs from WP9C_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal)" ]] || {
  echo "target checkout must be clean" >&2
  exit 125
}

export WP9C_SCRIPT_SHA256="$(sha256sum "$RUN_SH" | awk '{print $1}')"
export WP9C_CONCURRENT_SCRIPT_SHA256="$(sha256sum "$CONCURRENT_BENCHMARK" | awk '{print $1}')"
export WP9C_PAIR_SCRIPT_SHA256="$(sha256sum "$CONCURRENT_PAIR" | awk '{print $1}')"

if [[ -n "${CODE_VERIFIER_VALIDATION_MACHINE:-}" ]]; then
  MACHINE_POINTER="$CODE_VERIFIER_VALIDATION_MACHINE"
else
  MACHINE_POINTER="$REPO_ROOT/.ai-bridge/validation-machine.json"
  if [[ ! -f "$MACHINE_POINTER" ]]; then
    COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"
    MACHINE_POINTER="$(dirname "$COMMON_DIR")/.ai-bridge/validation-machine.json"
  fi
fi
[[ -f "$MACHINE_POINTER" ]] || { echo "validation machine pointer not found" >&2; exit 125; }

read -r ARTIFACT_ROOT FORMAL_DATA_ROOT < <("$PY" - "$MACHINE_POINTER" <<'PY_MACHINE'
import json
import sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("machine_status") != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine is not READY_FOR_VALIDATION_PLANNER")
artifact_root = Path(value.get("artifact_root", ""))
formal_data_root = Path(value.get("formal_data_root", ""))
for label, path in (("artifact_root", artifact_root), ("formal_data_root", formal_data_root)):
    if not path.is_absolute() or not str(path).startswith("/root/") or "/data" in str(path):
        raise SystemExit(f"invalid validation-machine {label}")
print(artifact_root, formal_data_root)
PY_MACHINE
)

BASE_ROOT="$ARTIFACT_ROOT/wp9c/grpo-c29"
B1_RUN="$BASE_ROOT/eval200-generation/b1/generation/wp9c-c29-b-eval200-b1-seed42"
B4_RUN="$BASE_ROOT/eval200-generation/b4/generation/wp9c-c29-b-eval200-b4-seed42"
B8_RUN="$BASE_ROOT/eval200-generation/b8/generation/wp9c-c29-b-eval200-b8-seed42"
PASS1_ROOT="$BASE_ROOT/eval200-semantic-equivalence-v3"
B1_PASS1_RUN="$PASS1_ROOT/b1-v8/evaluation/wp9c-c29-b-eval200-b1-seed42"
B4_PASS1_RUN="$PASS1_ROOT/b4-v8/evaluation/wp9c-c29-b-eval200-b4-seed42"
B8_PASS1_RUN="$PASS1_ROOT/b8-v8/evaluation/wp9c-c29-b-eval200-b8-seed42"
REPORT="${WP9C_FORMAL_BENCHMARK_REPORT:-$BASE_ROOT/benchmark/report/refresh_benchmark_report.json}"
PUBLIC_PILOT="$BASE_ROOT/pilot-acceptance/public.json"
HIDDEN_PILOT="$BASE_ROOT/pilot-acceptance/hidden.json"
POOL_DIR="$FORMAL_DATA_ROOT/wp9c/final-reduced-calibration-C29"

"$PY" - "$B1_RUN" "$B4_RUN" "$B8_RUN" "$EXPECTED_SYSTEMS_EVIDENCE_COMMIT" "$EXPECTED_EVAL_PROBLEMS" <<'PY_SYSTEMS'
import json
import sys
from pathlib import Path

b1_path, b4_path, b8_path = map(Path, sys.argv[1:4])
expected_commit = sys.argv[4]
expected_count = int(sys.argv[5])

def load(path: Path, batch: int) -> tuple[dict[str, object], float]:
    if not path.is_dir():
        raise SystemExit(f"selected systems run is missing: {path}")
    value = json.loads((path / "run.json").read_text(encoding="utf-8"))
    expected_id = f"wp9c-c29-b-eval200-b{batch}-seed42"
    if value.get("run_id") != expected_id:
        raise SystemExit(f"systems run_id drift for batch={batch}")
    if value.get("status") != "completed" or value.get("batch_size") != batch or value.get("seed") != 42:
        raise SystemExit(f"systems run is not completed/frozen for batch={batch}")
    if value.get("total_problems") != expected_count or value.get("completed_records") != expected_count:
        raise SystemExit(f"systems problem count drift for batch={batch}")
    if value.get("project_commit") != expected_commit:
        raise SystemExit(f"systems evidence commit drift for batch={batch}")
    gpu_hours = value.get("gpu_hours")
    if not isinstance(gpu_hours, (int, float)) or gpu_hours <= 0:
        raise SystemExit(f"systems gpu_hours missing for batch={batch}")
    return value, float(gpu_hours)

_, b1_hours = load(b1_path, 1)
_, b4_hours = load(b4_path, 4)
_, b8_hours = load(b8_path, 8)
if not (b8_hours < b4_hours < b1_hours):
    raise SystemExit("measured eval generation ordering is not b8 < b4 < b1")
print(f"systems_timing=b1:{b1_hours * 3600:.3f}s b4:{b4_hours * 3600:.3f}s b8:{b8_hours * 3600:.3f}s")
PY_SYSTEMS

"$PY" - "$B1_RUN" "$B4_RUN" "$B8_RUN" "$B1_PASS1_RUN" "$B4_PASS1_RUN" "$B8_PASS1_RUN" "$EXPECTED_SYSTEMS_EVIDENCE_COMMIT" "$EXPECTED_EVAL_PROBLEMS" <<'PY_PASS1'
import json
import sys
from pathlib import Path

b1_gen, b4_gen, b8_gen, b1_eval, b4_eval, b8_eval = map(Path, sys.argv[1:7])
expected_commit = sys.argv[7]
expected_count = int(sys.argv[8])


def generation_records_sha(path: Path, batch: int) -> str:
    value = json.loads((path / "run.json").read_text(encoding="utf-8"))
    if value.get("status") != "completed" or value.get("batch_size") != batch:
        raise SystemExit(f"generation evidence is not completed batch={batch}")
    sha = value.get("records_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise SystemExit(f"generation records hash missing for batch={batch}")
    return sha


def verification(path: Path, batch: int, generation_sha: str) -> list[dict[str, object]]:
    if not path.is_dir():
        raise SystemExit(f"Pass@1 verification evidence is missing for batch={batch}: {path}")
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    if run.get("status") != "completed" or run.get("seed") != 42 or run.get("verification_workers") != 8:
        raise SystemExit(f"Pass@1 verification evidence is not completed/frozen for batch={batch}")
    if run.get("project_commit") != expected_commit or run.get("generation_batch_size") != batch:
        raise SystemExit(f"Pass@1 verification provenance drift for batch={batch}")
    if run.get("generation_bundle_records_sha256") != generation_sha:
        raise SystemExit(f"Pass@1 verification generation hash drift for batch={batch}")
    rows = [
        json.loads(line)
        for line in (path / "samples" / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != expected_count:
        raise SystemExit(f"Pass@1 verification record count drift for batch={batch}")
    return rows


def pass1_signature(row: dict[str, object]) -> tuple[bool, bool, bool]:
    return (
        row.get("visible_pass_rate") == 1.0,
        row.get("train_hidden_pass_rate") == 1.0,
        row.get("eval_hidden_pass_rate") == 1.0,
    )


b1 = verification(b1_eval, 1, generation_records_sha(b1_gen, 1))
b4 = verification(b4_eval, 4, generation_records_sha(b4_gen, 4))
b8 = verification(b8_eval, 8, generation_records_sha(b8_gen, 8))


def mismatch_count(candidate: list[dict[str, object]]) -> int:
    mismatches = 0
    for baseline_row, candidate_row in zip(b1, candidate, strict=True):
        if baseline_row.get("problem_id") != candidate_row.get("problem_id") or baseline_row.get("prompt_hash") != candidate_row.get("prompt_hash"):
            raise SystemExit("Pass@1 evidence problem/order drift")
        if pass1_signature(baseline_row) != pass1_signature(candidate_row):
            mismatches += 1
    return mismatches


b4_mismatches = mismatch_count(b4)
b8_mismatches = mismatch_count(b8)
if b4_mismatches != 0:
    raise SystemExit(f"batch=4 changes per-problem Pass@1 on {b4_mismatches} problems")
if b8_mismatches == 0:
    raise SystemExit("batch=8 rejection evidence unexpectedly has exact per-problem Pass@1 parity")
print(
    "systems_selection=batch4 equivalence=per_problem_pass1_exact "
    f"b4_mismatches={b4_mismatches} b8_rejected_pass1_mismatches={b8_mismatches}"
)
PY_PASS1

"$PY" - "$REPO_ROOT/configs/grpo/wp9c-c29-active1354-public.yaml" "$REPO_ROOT/configs/grpo/wp9c-c29-active1354-hidden.yaml" <<'PY_CONFIG'
import sys
from pathlib import Path
import yaml

expected_common = {
    "num_generations": 8,
    "max_prompt_length": 2048,
    "max_completion_length": 512,
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 8,
    "learning_rate": 0.000005,
    "max_steps": 300,
    "warmup_ratio": 0.05,
    "lr_scheduler_type": "cosine",
    "temperature": 0.8,
    "top_p": 0.95,
    "beta": 0.01,
    "bf16": True,
    "fp16": False,
    "gradient_checkpointing": True,
    "lora_r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "seed": 42,
    "min_cuda_memory_gb": 20.0,
}
expected_modes = (
    ("public", "C-public-grpo-c29-active1354-seed42", "wp9c/final-reduced-calibration-C29/training/public_grpo.jsonl"),
    ("hidden", "D-hidden-grpo-c29-active1354-seed42", "wp9c/final-reduced-calibration-C29/training/hidden_grpo.jsonl"),
)
for path_text, (mode, run_name, dataset_path) in zip(sys.argv[1:], expected_modes, strict=True):
    value = yaml.safe_load(Path(path_text).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"formal {mode} config is invalid")
    if value.get("reward_mode") != mode or value.get("run_name") != run_name or value.get("dataset_path") != dataset_path:
        raise SystemExit(f"formal {mode} identity drift")
    for key, expected in expected_common.items():
        if value.get(key) != expected:
            raise SystemExit(f"formal {mode} config drift: {key}={value.get(key)!r}, expected={expected!r}")
print("formal_config_identity=passed max_steps=300 num_generations=8 seed=42")
PY_CONFIG

[[ -f "$POOL_DIR/calibration_manifest.json" ]] || { echo "C29 calibration manifest is missing" >&2; exit 125; }
[[ "$(sha256sum "$POOL_DIR/calibration_manifest.json" | awk '{print $1}')" == "$EXPECTED_CALIBRATION_SHA" ]] || {
  echo "C29 calibration manifest hash mismatch" >&2; exit 125;
}
[[ "$(sha256sum "$POOL_DIR/training/public_grpo.jsonl" | awk '{print $1}')" == "$EXPECTED_PUBLIC_SHA" ]] || {
  echo "C29 Public training hash mismatch" >&2; exit 125;
}
[[ "$(sha256sum "$POOL_DIR/training/hidden_grpo.jsonl" | awk '{print $1}')" == "$EXPECTED_HIDDEN_SHA" ]] || {
  echo "C29 Hidden training hash mismatch" >&2; exit 125;
}

[[ -f "$REPORT" ]] || {
  echo "formal benchmark report missing: $REPORT" >&2
  echo "formal training remains blocked until the benchmark/worker selection report is frozen" >&2
  exit 125
}

read -r SELECTED_EVAL_BATCH SELECTED_WORKERS PAIRED_MODE BENCHMARK_SHA < <("$PY" - "$REPORT" "$EXPECTED_CALIBRATION_SHA" "$EXPECTED_ACTIVE_ORDER_SHA" "$EXPECTED_PUBLIC_SHA" "$EXPECTED_HIDDEN_SHA" <<'PY_REPORT'
import hashlib
import sys
from pathlib import Path
from code_verifier.throughput import check_refresh_benchmark_report

path = Path(sys.argv[1])
expected_calibration, expected_order, expected_public, expected_hidden = sys.argv[2:]
summary = check_refresh_benchmark_report(path)
if summary.evidence_class != "formal":
    raise SystemExit("benchmark report is not formal")
if summary.selected_grpo_verification_workers is None:
    raise SystemExit("benchmark report has no GRPO worker selection")
if summary.calibration_manifest_sha256 != expected_calibration:
    raise SystemExit("benchmark calibration identity drift")
if summary.active_order_sha256 != expected_order:
    raise SystemExit("benchmark active order drift")
if summary.active_public_training_sha256 != expected_public or summary.active_hidden_training_sha256 != expected_hidden:
    raise SystemExit("benchmark training dataset identity drift")
sha = hashlib.sha256(path.read_bytes()).hexdigest()
print(summary.selected_eval_generation_batch_size, summary.selected_grpo_verification_workers, summary.paired_grpo_mode, sha)
PY_REPORT
)

echo "formal benchmark exact-text eval batch=$SELECTED_EVAL_BATCH; C34 effective eval batch=$EXPECTED_EVAL_BATCH uses per-problem Pass@1 exact parity"

"$PY" - "$PUBLIC_PILOT" "$HIDDEN_PILOT" "$BENCHMARK_SHA" "$SELECTED_WORKERS" <<'PY_PILOT'
import json
import sys
from pathlib import Path

public_path, hidden_path = map(Path, sys.argv[1:3])
benchmark_sha = sys.argv[3]
workers = int(sys.argv[4])
for mode, path in (("public", public_path), ("hidden", hidden_path)):
    if not path.is_file():
        raise SystemExit(f"{mode} pilot acceptance summary is missing")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "wp9c-c29-grpo-pilot-acceptance-v1":
        raise SystemExit(f"{mode} pilot acceptance schema drift")
    if value.get("status") != "completed" or value.get("decision") != "green" or value.get("reward_mode") != mode:
        raise SystemExit(f"{mode} pilot is not green")
    if value.get("benchmark_report_sha256") != benchmark_sha:
        raise SystemExit(f"{mode} pilot benchmark identity drift")
    if value.get("verification_workers") != workers:
        raise SystemExit(f"{mode} pilot worker selection drift")
print("pilot_gate=green public=green hidden=green")
PY_PILOT

printf 'formal_preflight=PASS handoff=%s eval_batch=%s strict_report_eval_batch=%s grpo_workers=%s paired_mode=%s\n' \
  "$HANDOFF" "$EXPECTED_EVAL_BATCH" "$SELECTED_EVAL_BATCH" "$SELECTED_WORKERS" "$PAIRED_MODE"

if [[ "$ACTION" == "preflight" ]]; then
  echo "preflight only: no GRPO training was started"
  exit 0
fi

[[ "${WP9C_FORMAL_EXECUTION_ACK:-}" == "RUN_300_STEP_PUBLIC_HIDDEN" ]] || {
  echo "formal execution requires WP9C_FORMAL_EXECUTION_ACK=RUN_300_STEP_PUBLIC_HIDDEN" >&2
  exit 125
}

exec bash "$SELECTED_PAIR" formal
