#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ID="WP9-d"
GATE_ID="wp9d-eval400-parallel-benchmark"
CHECKPOINT_ID="C0"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-eval400-parallel-benchmark/C0/run.sh"
RESULT_CODE_COMMIT="7a92bb587fe34e6ae80a5d703e85a0659f05f43a"
P2_OPERATOR_COMMIT="07ccc71968bedc25b1a8fd15aa0ee35a75e05389"
P1_REPORT_SHA="5a6801024c70177e5f4f777bf524e8b263f93782f4e262ad03bbe886955d231d"
EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
EVAL_DATASET_SHA="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
EVAL_ORDER_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh preflight
  run.sh p2
  run.sh p4
  run.sh compare

Required target bindings:
  WP9D_HANDOFF_COMMIT=<exact 40-hex operator handoff commit>
  WP9D_PPAR_SCRIPT_SHA256=<sha256 of this tracked run.sh>

This benchmark NEVER runs b4/p1. It reuses the completed P2 B-refresh b4/p1
bundle as the baseline, generates only b4/p2 and b4/p4, and can then compare
all three generation bundles. It does not contact Piston, verify, aggregate, or
run GRPO training. Benchmark outputs are isolated from the formal P2 B-refresh.
EOF
  exit 64
}

PHASE="${1:-}"
case "$PHASE" in
  preflight|p2|p4|compare) [[ $# -eq 1 ]] || usage ;;
  *) usage ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
[[ "$REPO_ROOT" == "/root/open-r1-code-verifier" ]] || { echo "target repo must be /root/open-r1-code-verifier" >&2; exit 125; }
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "target .venv Python is unavailable" >&2; exit 125; }
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"

EXPECTED_COMMIT="${WP9D_HANDOFF_COMMIT:-}"
EXPECTED_SCRIPT_SHA="${WP9D_PPAR_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9D_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_SCRIPT_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9D_PPAR_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from WP9D_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean; inspect without reset/clean" >&2; exit 125; }
SCRIPT_SHA="$(sha256sum "$REPO_ROOT/$SCRIPT_REL" | awk '{print $1}')"
[[ "$SCRIPT_SHA" == "$EXPECTED_SCRIPT_SHA" ]] || { echo "tracked benchmark run.sh SHA256 drift" >&2; exit 125; }
git merge-base --is-ancestor "$RESULT_CODE_COMMIT" HEAD || { echo "handoff is not a descendant of frozen result-code commit" >&2; exit 125; }
git merge-base --is-ancestor "$P2_OPERATOR_COMMIT" HEAD || { echo "handoff is not a descendant of the P2 operator commit" >&2; exit 125; }
[[ -z "$(git ls-files .ai-bridge)" ]] || { echo ".ai-bridge must have zero tracked paths" >&2; exit 125; }

if [[ -n "${CODE_VERIFIER_VALIDATION_MACHINE:-}" ]]; then
  MACHINE_POINTER="$CODE_VERIFIER_VALIDATION_MACHINE"
else
  MACHINE_POINTER="$REPO_ROOT/.ai-bridge/validation-machine.json"
fi
[[ -f "$MACHINE_POINTER" ]] || { echo "validation machine pointer not found" >&2; exit 125; }
readarray -t MACHINE_FIELDS < <("$PY" - "$MACHINE_POINTER" <<'PY_MACHINE'
import json, sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "machine_status": "READY_FOR_VALIDATION_PLANNER",
    "artifact_root": "/root/sj-tmp/open-r1-code-verifier-outputs",
    "hf_home": "/root/huggingface",
    "formal_data_root": "/root/open-r1-code-verifier-data-4090",
    "piston_endpoint": "http://127.0.0.1:2000",
}
for key, wanted in expected.items():
    if value.get(key) != wanted:
        raise SystemExit(f"validation machine {key} drift")
for key in ("artifact_root", "hf_home", "formal_data_root"):
    print(value[key])
PY_MACHINE
)
ARTIFACT_ROOT="${MACHINE_FIELDS[0]}"
HF_HOME_TARGET="${MACHINE_FIELDS[1]}"
DATA_ROOT="${MACHINE_FIELDS[2]}"
export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$DATA_ROOT"
export HF_HOME="$HF_HOME_TARGET"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export TMPDIR="/root/tmp"
mkdir -p "$TMPDIR"

B_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
EVAL400_DIR="$DATA_ROOT/wp9c/heldout-eval400-C34"
P1_REPORT="$ARTIFACT_ROOT/wp9d/p1-runtime-validation/report/p1-runtime-report.json"
EVAL_CONFIG="$REPO_ROOT/configs/eval/base.yaml"
BASELINE_ROOT="$ARTIFACT_ROOT/wp9d/b-refresh-eval400"
BASELINE_RUN="$BASELINE_ROOT/generation/wp9d-B-eval400-b4-p1-seed42"
BENCH_ROOT="$ARTIFACT_ROOT/wp9d/eval400-parallel-benchmark"
P2_RUN="$BENCH_ROOT/generation/wp9d-B-eval400-b4-p2-seed42"
P4_RUN="$BENCH_ROOT/generation/wp9d-B-eval400-b4-p4-seed42"
OP_ROOT="$ARTIFACT_ROOT/operator/$STAGE_ID/$GATE_ID/$CHECKPOINT_ID/$PHASE"
STATUS_FILE="$OP_ROOT/status"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOG_FILE="$OP_ROOT/terminal.log"
LOCK_FILE="$OP_ROOT/run.lock"
mkdir -p "$OP_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "operator lock is already held: $LOCK_FILE" >&2; exit 73; }
START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'running\n' >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
printf '[%s] start phase=%s commit=%s script_sha=%s\n' "$START_TIME" "$PHASE" "$EXPECTED_COMMIT" "$SCRIPT_SHA" >>"$LOG_FILE"

COMMAND_RC="null"
POSTCHECK_RC="null"
RUN_DIR=""
PARALLEL_GENERATORS=""

write_evidence() {
  local gate_status="$1" note="$2"
  local ended run_json_sha records_sha report_sha
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  run_json_sha=""; records_sha=""; report_sha=""
  [[ -z "$RUN_DIR" || ! -f "$RUN_DIR/run.json" ]] || run_json_sha="$(sha256sum "$RUN_DIR/run.json" | awk '{print $1}')"
  [[ -z "$RUN_DIR" || ! -f "$RUN_DIR/samples/generations.jsonl" ]] || records_sha="$(sha256sum "$RUN_DIR/samples/generations.jsonl" | awk '{print $1}')"
  [[ ! -f "$BENCH_ROOT/report/parallel-benchmark-report.json" ]] || report_sha="$(sha256sum "$BENCH_ROOT/report/parallel-benchmark-report.json" | awk '{print $1}')"
  "$PY" - "$EVIDENCE_FILE.tmp" "$EXPECTED_COMMIT" "$SCRIPT_SHA" "$PHASE" "$gate_status" "$COMMAND_RC" "$POSTCHECK_RC" "$START_TIME" "$ended" "$note" "$RUN_DIR" "$PARALLEL_GENERATORS" "$run_json_sha" "$records_sha" "$report_sha" <<'PY_EVIDENCE'
import json, sys
from pathlib import Path
(out, handoff, script_sha, phase, gate_status, command_rc, postcheck_rc, started, ended,
 note, run_dir, parallel, run_json_sha, records_sha, report_sha) = sys.argv[1:]
def rc(value):
    return None if value == "null" else int(value)
payload = {
    "schema_version": "wp9d-eval400-parallel-benchmark-evidence-v1",
    "stage_id": "WP9-d",
    "gate_id": "wp9d-eval400-parallel-benchmark",
    "checkpoint_id": "C0",
    "phase": phase,
    "handoff_commit": handoff,
    "operator_script": "ai-work/executor/operator/WP9-d/wp9d-eval400-parallel-benchmark/C0/run.sh",
    "operator_script_sha256": script_sha,
    "baseline_b4_p1_run": "/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/b-refresh-eval400/generation/wp9d-B-eval400-b4-p1-seed42",
    "benchmark_root": "/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/eval400-parallel-benchmark",
    "batch_size": 4,
    "parallel_generators": int(parallel) if parallel else None,
    "seed": 42,
    "run_dir": run_dir or None,
    "run_json_sha256": run_json_sha or None,
    "generation_records_sha256": records_sha or None,
    "comparison_report_sha256": report_sha or None,
    "command_rc": rc(command_rc),
    "postcheck_rc": rc(postcheck_rc),
    "gate_status": gate_status,
    "note": note,
    "started_at": started,
    "ended_at": ended,
}
Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  printf '%s\n' "$gate_status" >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
}

common_preflight() {
  [[ -f "$P1_REPORT" ]] || { echo "P1 report missing" >&2; return 125; }
  [[ "$(sha256sum "$P1_REPORT" | awk '{print $1}')" == "$P1_REPORT_SHA" ]] || { echo "P1 report SHA drift" >&2; return 125; }
  [[ "$(sha256sum "$EVAL_CONFIG" | awk '{print $1}')" == "$EVAL_CONFIG_SHA" ]] || { echo "eval config SHA drift" >&2; return 125; }
  [[ -d "$EVAL400_DIR" && -d "$B_RUN" ]] || { echo "eval400 or frozen B missing" >&2; return 125; }
  "$PY" - "$P1_REPORT" "$B_RUN" "$BASELINE_RUN" <<'PY_PREFLIGHT'
import json, sys
from pathlib import Path
from code_verifier.cli import build_parser
from code_verifier.training.sft import load_completed_sft_checkpoint
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
freeze = report.get("runtime_freeze_candidate", {})
if freeze.get("Eval") != {"batch_size": 4, "dedicated_cuda_streams": False, "parallel_generators": 1, "verification_workers": 64}:
    raise SystemExit("P1 eval runtime freeze drift")
identity = load_completed_sft_checkpoint(Path(sys.argv[2]))
if (identity.run_id, identity.model_id, identity.model_revision, identity.seed) != (
    "B-sft-formal-seed42", "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "2e1fd397ee46e1388853d2af2c993145b0f1098a", 42,
):
    raise SystemExit("frozen B identity drift")
baseline = json.loads((Path(sys.argv[3]) / "run.json").read_text(encoding="utf-8"))
for key, wanted in {
    "status": "completed", "artifact_type": "evaluation_generation_bundle",
    "run_id": "wp9d-B-eval400-b4-p1-seed42", "batch_size": 4, "parallel_generators": 1,
    "seed": 42, "completed_records": 400, "total_problems": 400,
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
}.items():
    if baseline.get(key) != wanted:
        raise SystemExit(f"b4/p1 baseline is not completed/frozen: {key}")
parser = build_parser()
sub = next(a for a in parser._actions if getattr(a, "dest", None) == "command")
gen = sub.choices["generate-eval"]
parallel = next(a for a in gen._actions if getattr(a, "dest", None) == "parallel_generators")
if tuple(parallel.choices or ()) != (1, 2, 4):
    raise SystemExit("generate-eval p4 CLI support missing")
PY_PREFLIGHT
  if [[ "$PHASE" != "compare" ]]; then
    local gpu_row free_mib
    gpu_row="$(nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits | awk -F',' '$2 ~ /RTX 4090/ {gsub(/ /,"",$3); gsub(/ /,"",$4); if ($3+0 >= 22528 && $4+0 >= 20000) {print $2"|"$3"|"$4; exit}}')"
    [[ -n "$gpu_row" ]] || { echo "benchmark generation requires RTX 4090 with >=20000 MiB free VRAM" >&2; return 125; }
    IFS='|' read -r _ _ free_mib <<<"$gpu_row"
  fi
}

set +e
common_preflight >>"$LOG_FILE" 2>&1
PREFLIGHT_RC=$?
set -e
if [[ "$PREFLIGHT_RC" -ne 0 ]]; then
  COMMAND_RC="$PREFLIGHT_RC"; POSTCHECK_RC="$PREFLIGHT_RC"
  write_evidence failed "preflight failed"
  exit "$PREFLIGHT_RC"
fi

if [[ "$PHASE" == "preflight" ]]; then
  COMMAND_RC=0; POSTCHECK_RC=0
  write_evidence passed "benchmark preflight passed; no generation was started"
  echo "WP9-d eval400 parallel benchmark preflight PASS"
  exit 0
fi

if [[ "$PHASE" == "compare" ]]; then
  mkdir -p "$BENCH_ROOT/report"
  REPORT="$BENCH_ROOT/report/parallel-benchmark-report.json"
  [[ ! -e "$REPORT" ]] || { COMMAND_RC=125; POSTCHECK_RC=125; write_evidence failed "comparison report already exists"; exit 125; }
  set +e
  "$PY" - "$REPORT.tmp" "$BASELINE_RUN" "$P2_RUN" "$P4_RUN" <<'PY_COMPARE' >>"$LOG_FILE" 2>&1
import hashlib, json, math, sys
from pathlib import Path
out = Path(sys.argv[1])
runs = {"b4_p1": Path(sys.argv[2]), "b4_p2": Path(sys.argv[3]), "b4_p4": Path(sys.argv[4])}
expected_parallel = {"b4_p1": 1, "b4_p2": 2, "b4_p4": 4}

def semantic_hash(rows):
    payload = [
        [r.get("problem_id"), r.get("prompt_hash"), r.get("completion"), r.get("completion_tokens"), r.get("hit_max_new_tokens")]
        for r in rows
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

def load(name, path):
    meta = json.loads((path / "run.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (path / "samples" / "generations.jsonl").read_text(encoding="utf-8").splitlines() if line]
    for key, wanted in {
        "status": "completed", "artifact_type": "evaluation_generation_bundle",
        "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
        "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
        "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
        "batch_size": 4, "parallel_generators": expected_parallel[name], "seed": 42,
        "completed_records": 400, "total_problems": 400,
    }.items():
        if meta.get(key) != wanted:
            raise SystemExit(f"{name} drift: {key}={meta.get(key)!r}, expected={wanted!r}")
    if len(rows) != 400 or len({r.get("problem_id") for r in rows}) != 400:
        raise SystemExit(f"{name} records invalid")
    wall = meta.get("invocation_generation_wall_seconds")
    if isinstance(wall, bool) or not isinstance(wall, (int, float)) or not math.isfinite(float(wall)) or wall <= 0:
        raise SystemExit(f"{name} generation wall invalid")
    util = meta.get("runtime_utilization", {})
    if util.get("status") != "available":
        raise SystemExit(f"{name} runtime utilization unavailable")
    return {
        "run_dir": str(path),
        "project_commit": meta.get("project_commit"),
        "generation_wall_seconds": float(wall),
        "gpu_utilization_mean_percent": util.get("gpu_utilization_mean_percent"),
        "gpu_utilization_p95_percent": util.get("gpu_utilization_p95_percent"),
        "gpu_memory_used_mean_mib": util.get("gpu_memory_used_mean_mib"),
        "gpu_memory_used_p95_mib": util.get("gpu_memory_used_p95_mib"),
        "gpu_memory_used_max_mib": util.get("gpu_memory_used_max_mib"),
        "sample_count": util.get("sample_count"),
        "semantic_generation_sha256": semantic_hash(rows),
        "records_file_sha256": hashlib.sha256((path / "samples" / "generations.jsonl").read_bytes()).hexdigest(),
    }

result = {name: load(name, path) for name, path in runs.items()}
p1 = result["b4_p1"]
for name in ("b4_p2", "b4_p4"):
    result[name]["speedup_vs_b4_p1"] = p1["generation_wall_seconds"] / result[name]["generation_wall_seconds"]
result["b4_p4"]["speedup_vs_b4_p2"] = result["b4_p2"]["generation_wall_seconds"] / result["b4_p4"]["generation_wall_seconds"]
parity = {
    "p1_eq_p2": p1["semantic_generation_sha256"] == result["b4_p2"]["semantic_generation_sha256"],
    "p1_eq_p4": p1["semantic_generation_sha256"] == result["b4_p4"]["semantic_generation_sha256"],
    "p2_eq_p4": result["b4_p2"]["semantic_generation_sha256"] == result["b4_p4"]["semantic_generation_sha256"],
}
payload = {
    "schema_version": "wp9d-eval400-parallel-benchmark-report-v1",
    "evidence_class": "benchmark_only_not_runtime_freeze",
    "batch_size": 4,
    "seed": 42,
    "runs": result,
    "semantic_parity": parity,
    "all_semantically_equal": all(parity.values()),
    "note": "b4/p1 is reused from the formal P2 B-refresh; this benchmark starts only p2 and p4. No runtime freeze is changed by this report alone.",
}
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_COMPARE
  COMMAND_RC=$?
  set -e
  if [[ "$COMMAND_RC" -ne 0 ]]; then
    POSTCHECK_RC="$COMMAND_RC"; write_evidence failed "comparison failed"; exit "$COMMAND_RC"
  fi
  mv "$REPORT.tmp" "$REPORT"
  POSTCHECK_RC=0
  write_evidence passed "b4/p1 baseline compared with newly generated b4/p2 and b4/p4"
  echo "parallel benchmark comparison PASS: $REPORT"
  exit 0
fi

case "$PHASE" in
  p2) PARALLEL_GENERATORS=2; RUN_DIR="$P2_RUN" ;;
  p4) PARALLEL_GENERATORS=4; RUN_DIR="$P4_RUN" ;;
esac
RUN_NAME="$(basename "$RUN_DIR")"
[[ ! -e "$RUN_DIR" ]] || { COMMAND_RC=125; POSTCHECK_RC=125; write_evidence failed "benchmark run already exists; preserve it"; exit 125; }
mkdir -p "$BENCH_ROOT"
set +e
"$PY" -m code_verifier.cli generate-eval \
  --config "$EVAL_CONFIG" \
  --dataset-dir "$EVAL400_DIR" \
  --sft-run-dir "$B_RUN" \
  --run-name "$RUN_NAME" \
  --batch-size 4 \
  --parallel-generators "$PARALLEL_GENERATORS" \
  --seed 42 \
  --output-dir "$BENCH_ROOT" >>"$LOG_FILE" 2>&1
COMMAND_RC=$?
set -e
if [[ "$COMMAND_RC" -ne 0 ]]; then
  POSTCHECK_RC="null"; write_evidence failed "generate-eval exited nonzero"; exit "$COMMAND_RC"
fi

set +e
"$PY" - "$RUN_DIR" "$EXPECTED_COMMIT" "$PARALLEL_GENERATORS" <<'PY_POST' >>"$LOG_FILE" 2>&1
import json, math, sys
from pathlib import Path
run_dir = Path(sys.argv[1]); handoff = sys.argv[2]; parallel = int(sys.argv[3])
meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
expected = {
    "status": "completed", "artifact_type": "evaluation_generation_bundle", "run_id": run_dir.name,
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "dataset_hash": "770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae",
    "ordered_problem_ids_sha256": "2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9",
    "batch_size": 4, "parallel_generators": parallel, "seed": 42,
    "completed_records": 400, "total_problems": 400, "project_commit": handoff,
}
for key, wanted in expected.items():
    if meta.get(key) != wanted:
        raise SystemExit(f"benchmark generation drift: {key}={meta.get(key)!r}, expected={wanted!r}")
rows = [json.loads(line) for line in (run_dir / "samples" / "generations.jsonl").read_text(encoding="utf-8").splitlines() if line]
if len(rows) != 400 or len({row.get("problem_id") for row in rows}) != 400:
    raise SystemExit("benchmark generation rows invalid")
wall = meta.get("invocation_generation_wall_seconds")
if isinstance(wall, bool) or not isinstance(wall, (int, float)) or not math.isfinite(float(wall)) or wall <= 0:
    raise SystemExit("benchmark generation wall invalid")
util = meta.get("runtime_utilization", {})
if util.get("status") != "available" or not util.get("sample_count"):
    raise SystemExit("benchmark runtime utilization unavailable")
PY_POST
POSTCHECK_RC=$?
set -e
if [[ "$POSTCHECK_RC" -ne 0 ]]; then
  write_evidence failed "benchmark generation postcheck failed"; exit 3
fi
write_evidence passed "b4/p${PARALLEL_GENERATORS} eval400 generation completed; formal b4/p1 output was not modified"
echo "benchmark b4/p${PARALLEL_GENERATORS} PASS: $RUN_DIR"
