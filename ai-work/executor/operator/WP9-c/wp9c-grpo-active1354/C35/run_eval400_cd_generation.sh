#!/usr/bin/env bash
set -Eeuo pipefail

# WP9-c C35: final eval400 generation for C/Public and D/Hidden.
# Scientific contract: deterministic pass@1, frozen eval400, seed=42, operational batch=4.
# This script intentionally keeps the target repository at the C34 code identity used by B generation.

EXPECTED_HEAD="cc8c6c63a6ff45f42d1257305864809d6ba6007e"
EXPECTED_MODEL_ID="Qwen/Qwen2.5-Coder-1.5B-Instruct"
EXPECTED_MODEL_REVISION="2e1fd397ee46e1388853d2af2c993145b0f1098a"
EXPECTED_DATASET_HASH="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
EXPECTED_ORDER_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
EXPECTED_PISTON_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
EXPECTED_CANONICAL_SHA="d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6"
BATCH=4
SEED=42

REPO_ROOT="${WP9C_REPO_ROOT:-/root/open-r1-code-verifier}"
ARTIFACT_ROOT="${CODE_VERIFIER_ARTIFACT_ROOT:-/root/sj-tmp/open-r1-code-verifier-outputs}"
FORMAL_DATA_ROOT="${CODE_VERIFIER_DATA_ROOT:-/root/open-r1-code-verifier-data-4090}"
HF_HOME_TARGET="${HF_HOME:-/root/huggingface}"

PY="$REPO_ROOT/.venv/bin/python"
CV="$REPO_ROOT/.venv/bin/code-verifier"
CONFIG="$REPO_ROOT/configs/eval/base.yaml"
DATASET_DIR="$FORMAL_DATA_ROOT/wp9c/heldout-eval400-C34"

B_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
C_RUN="$ARTIFACT_ROOT/wp9c/grpo-c29/formal/C-public-grpo-c29-active1354-seed42"
D_RUN="$ARTIFACT_ROOT/wp9c/grpo-c29/formal/D-hidden-grpo-c29-active1354-seed42"

B_GEN_NAME="wp9c-B-sft-eval400-b4-seed42"
C_GEN_NAME="wp9c-C-public-eval400-b4-seed42"
D_GEN_NAME="wp9c-D-hidden-eval400-b4-seed42"
B_GEN="$ARTIFACT_ROOT/generation/$B_GEN_NAME"

fail() {
  echo "ERROR: $*" >&2
  exit 125
}

[[ -d "$REPO_ROOT/.git" || -f "$REPO_ROOT/.git" ]] || fail "repo missing: $REPO_ROOT"
[[ -x "$PY" && -x "$CV" ]] || fail "target .venv/code-verifier unavailable"
[[ -f "$CONFIG" ]] || fail "eval config missing: $CONFIG"
[[ -d "$DATASET_DIR" ]] || fail "frozen eval400 missing: $DATASET_DIR"
[[ -d "$B_RUN" && -d "$C_RUN" && -d "$D_RUN" ]] || fail "B/C/D run directory missing"

cd "$REPO_ROOT"
[[ "$(git rev-parse HEAD)" == "$EXPECTED_HEAD" ]] || fail "target HEAD must remain $EXPECTED_HEAD"
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || fail "target repo must be clean"
[[ "$(sha256sum "$DATASET_DIR/canonical/problems.jsonl" | awk '{print $1}')" == "$EXPECTED_CANONICAL_SHA" ]] || fail "eval400 canonical hash drift"

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$HF_HOME_TARGET"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export TMPDIR="/root/tmp"
mkdir -p "$TMPDIR"

if pgrep -af 'code-verifier train-grpo|python.*train-grpo' >/dev/null 2>&1; then
  fail "GRPO training process is still present; do not overlap formal generation"
fi

command -v nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi unavailable"
GPU_TOTAL="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n 1 | tr -d ' ')"
[[ "$GPU_TOTAL" =~ ^[0-9]+$ && "$GPU_TOTAL" -ge 22528 ]] || fail "eval generation requires >=22528 MiB GPU"

"$PY" - "$B_RUN" "$C_RUN" "$D_RUN" <<'PY_IDENTITIES'
import json
import sys
from pathlib import Path
from code_verifier.training import load_completed_grpo_checkpoint, load_completed_sft_checkpoint

expected_model = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
expected_revision = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
expected_public_hash = "558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c"
expected_hidden_hash = "9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec"

b = load_completed_sft_checkpoint(Path(sys.argv[1]))
if b.run_id != "B-sft-formal-seed42" or b.model_id != expected_model or b.model_revision != expected_revision or b.seed != 42:
    raise SystemExit("B identity drift")

for path, mode, expected_hash in (
    (Path(sys.argv[2]), "public", expected_public_hash),
    (Path(sys.argv[3]), "hidden", expected_hidden_hash),
):
    ident = load_completed_grpo_checkpoint(path)
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    if ident.reward_mode != mode:
        raise SystemExit(f"{mode} reward_mode drift")
    if ident.parent_sft != b:
        raise SystemExit(f"{mode} parent B drift")
    if ident.dataset_hash != expected_hash:
        raise SystemExit(f"{mode} dataset hash drift")
    if run.get("status") != "completed" or run.get("global_step") != 300:
        raise SystemExit(f"{mode} formal run is not completed at step 300")
PY_IDENTITIES

"$PY" - "$B_GEN" "$EXPECTED_HEAD" "$EXPECTED_DATASET_HASH" "$EXPECTED_ORDER_SHA" "$EXPECTED_PISTON_SHA" <<'PY_BGEN'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
expected_head, dataset_hash, order_sha, piston_sha = sys.argv[2:]
run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
checks = {
    "status": "completed",
    "completed_records": 400,
    "total_problems": 400,
    "batch_size": 4,
    "seed": 42,
    "dataset_hash": dataset_hash,
    "ordered_problem_ids_sha256": order_sha,
    "piston_config_sha256": piston_sha,
    "project_commit": expected_head,
}
for key, expected in checks.items():
    if run.get(key) != expected:
        raise SystemExit(f"B b4 eval400 anchor drift: {key}: {run.get(key)!r} != {expected!r}")
PY_BGEN

postcheck() {
  local run_name="$1"
  local source_run="$2"
  local mode="$3"
  local run_dir="$ARTIFACT_ROOT/generation/$run_name"
  "$PY" - "$run_dir" "$source_run" "$mode" "$EXPECTED_HEAD" "$EXPECTED_DATASET_HASH" "$EXPECTED_ORDER_SHA" "$EXPECTED_PISTON_SHA" "$EXPECTED_MODEL_ID" "$EXPECTED_MODEL_REVISION" <<'PY_POST'
import json
import sys
from pathlib import Path
from code_verifier.training import load_completed_grpo_checkpoint

run_dir = Path(sys.argv[1])
source_run = Path(sys.argv[2])
mode = sys.argv[3]
expected_head, dataset_hash, order_sha, piston_sha, model_id, revision = sys.argv[4:]
identity = load_completed_grpo_checkpoint(source_run)
if identity.reward_mode != mode:
    raise SystemExit(f"source reward mode drift: {identity.reward_mode} != {mode}")
run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
checks = {
    "status": "completed",
    "completed_records": 400,
    "total_problems": 400,
    "batch_size": 4,
    "seed": 42,
    "dataset_hash": dataset_hash,
    "ordered_problem_ids_sha256": order_sha,
    "piston_config_sha256": piston_sha,
    "project_commit": expected_head,
    "model_id": model_id,
    "model_revision": revision,
    "checkpoint": str(identity.checkpoint_dir),
}
for key, expected in checks.items():
    if run.get(key) != expected:
        raise SystemExit(f"{mode} generation postcheck failed: {key}: {run.get(key)!r} != {expected!r}")
samples = run_dir / "samples" / "generations.jsonl"
if not samples.is_file():
    raise SystemExit(f"{mode} generations.jsonl missing")
with samples.open("r", encoding="utf-8") as handle:
    rows = sum(1 for line in handle if line.strip())
if rows != 400:
    raise SystemExit(f"{mode} generations row count {rows} != 400")
print(json.dumps({
    "run": str(run_dir),
    "reward_mode": mode,
    "status": run["status"],
    "completed_records": run["completed_records"],
    "batch_size": run["batch_size"],
    "dataset_hash": run["dataset_hash"],
    "ordered_problem_ids_sha256": run["ordered_problem_ids_sha256"],
    "records_sha256": run.get("records_sha256"),
    "gpu_hours": run.get("gpu_hours"),
}, sort_keys=True))
PY_POST
}

run_one() {
  local run_name="$1"
  local source_run="$2"
  local mode="$3"
  local run_dir="$ARTIFACT_ROOT/generation/$run_name"

  if [[ -f "$run_dir/run.json" ]]; then
    if postcheck "$run_name" "$source_run" "$mode" >/dev/null 2>&1; then
      echo "reuse strict-completed $mode generation: $run_dir"
      postcheck "$run_name" "$source_run" "$mode"
      return 0
    fi
    echo "existing $mode generation is not strict-completed; invoking exact-prefix resume: $run_dir" >&2
  fi

  "$CV" generate-eval \
    --config "$CONFIG" \
    --dataset-dir "$DATASET_DIR" \
    --grpo-run-dir "$source_run" \
    --run-name "$run_name" \
    --batch-size "$BATCH" \
    --seed "$SEED" \
    --output-dir "$ARTIFACT_ROOT"

  postcheck "$run_name" "$source_run" "$mode"
}

echo "=== WP9-c final eval400 generation: C/Public, batch=$BATCH ==="
run_one "$C_GEN_NAME" "$C_RUN" public

echo "=== WP9-c final eval400 generation: D/Hidden, batch=$BATCH ==="
run_one "$D_GEN_NAME" "$D_RUN" hidden

echo "=== PASS: C and D final eval400 b4 generation strict-completed ==="
echo "C: $ARTIFACT_ROOT/generation/$C_GEN_NAME"
echo "D: $ARTIFACT_ROOT/generation/$D_GEN_NAME"
