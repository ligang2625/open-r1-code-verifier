#!/usr/bin/env bash
set -Eeuo pipefail

# WP9-c C36: final frozen eval400 generation for the SFT-only active1354 arm.
# Scientific contract: same eval400 as B/C/D, deterministic pass@1, seed=42, batch=4.
# Policy reconstruction: Base A -> safe-merge frozen B -> attach completed C32 SFT adapter.

BASE_EVAL_COMMIT="cc8c6c63a6ff45f42d1257305864809d6ba6007e"
EXPECTED_EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
EXPECTED_CANONICAL_SHA="d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6"
EXPECTED_RUNNER_SHA="51208be1c85851716164ac4ee5c7925657326df24ce477e779d2d5a0b083d51f"
EXPECTED_PARENT_RUN_JSON_SHA="6d059ae271e176aaa2becfa131937e64c8e38bb883f358149010f367a5a62a73"
EXPECTED_CHILD_RUN_JSON_SHA="bee4b0121a0ef7e730c4fcff4423bbecfbc2febed6f248a46ca0759c8b2fdeae"
EXPECTED_CHILD_METRICS_SHA="9a1bc4421a81cdb4453abc883e8ef493a26be8e54a231c8e07055da068a5c631"
EXPECTED_CHILD_ADAPTER_CONFIG_SHA="1ed8f60015a1df78d0dbe3f973bf5faf35adc7dcb6fce844e81bc04ea368bbdb"
EXPECTED_CHILD_ADAPTER_MODEL_SHA="fac1742fce977bbcdc713fba35e307397a696b7ee961768deb3c94bccc0d17e8"
MIN_FREE_VRAM_MIB=20000

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${WP9C_REPO_ROOT:-/root/open-r1-code-verifier}"
ARTIFACT_ROOT="${CODE_VERIFIER_ARTIFACT_ROOT:-/root/sj-tmp/open-r1-code-verifier-outputs}"
FORMAL_DATA_ROOT="${CODE_VERIFIER_DATA_ROOT:-/root/open-r1-code-verifier-data-4090}"
HF_HOME_TARGET="${HF_HOME:-/root/huggingface}"
HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"

PY="$REPO_ROOT/.venv/bin/python"
CONFIG="$REPO_ROOT/configs/eval/base.yaml"
RUNNER="$SCRIPT_DIR/run_continuation_generation.py"
DATASET_DIR="$FORMAL_DATA_ROOT/wp9c/heldout-eval400-C34"
PARENT_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
CHILD_RUN="$ARTIFACT_ROOT/sft/wp9c-sft-only-active1354-seed42"
GEN_RUN="$ARTIFACT_ROOT/generation/wp9c-sft-only-active1354-eval400-b4-seed42"

die() {
  echo "ERROR: $*" >&2
  exit 125
}

[[ -x "$PY" ]] || die "target .venv Python unavailable: $PY"
[[ "$HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "set WP9C_HANDOFF_COMMIT to the exact C36 handoff commit" >&2; exit 64; }
[[ "$REPO_ROOT" == /root || "$REPO_ROOT" == /root/* ]] || die "repo must be under /root"
[[ "$ARTIFACT_ROOT" == /root/* ]] || die "artifact root must be under /root"
[[ "$FORMAL_DATA_ROOT" == /root/* ]] || die "data root must be under /root"
[[ "$HF_HOME_TARGET" == /root/* ]] || die "HF_HOME must be under /root"

cd "$REPO_ROOT"
[[ "$(git rev-parse HEAD)" == "$HANDOFF_COMMIT" ]] || die "target HEAD differs from WP9C_HANDOFF_COMMIT"
git merge-base --is-ancestor "$BASE_EVAL_COMMIT" "$HANDOFF_COMMIT" || die "C36 handoff is not descended from frozen eval code $BASE_EVAL_COMMIT"
DIRTY="$(git status --porcelain --untracked-files=all | grep -vE '^\?\? \.ai-bridge/' || true)"
[[ -z "$DIRTY" ]] || { echo "target checkout has non-.ai-bridge changes" >&2; printf '%s\n' "$DIRTY" >&2; exit 65; }

[[ -f "$CONFIG" ]] || die "eval config missing: $CONFIG"
[[ -f "$RUNNER" ]] || die "C36 generation runner missing: $RUNNER"
[[ -d "$DATASET_DIR" ]] || die "frozen eval400 missing: $DATASET_DIR"
[[ -d "$PARENT_RUN" ]] || die "frozen parent B missing: $PARENT_RUN"
[[ -d "$CHILD_RUN" ]] || die "completed C32 SFT run missing: $CHILD_RUN"
[[ -d "$HF_HOME_TARGET" ]] || die "HF cache missing: $HF_HOME_TARGET"

printf '%s  %s\n' "$EXPECTED_EVAL_CONFIG_SHA" "$CONFIG" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_CANONICAL_SHA" "$DATASET_DIR/canonical/problems.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_RUNNER_SHA" "$RUNNER" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_PARENT_RUN_JSON_SHA" "$PARENT_RUN/run.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_CHILD_RUN_JSON_SHA" "$CHILD_RUN/run.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_CHILD_METRICS_SHA" "$CHILD_RUN/metrics.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_CHILD_ADAPTER_CONFIG_SHA" "$CHILD_RUN/checkpoints/adapter_config.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_CHILD_ADAPTER_MODEL_SHA" "$CHILD_RUN/checkpoints/adapter_model.safetensors" | sha256sum -c -

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$HF_HOME_TARGET"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"
export TMPDIR="${TMPDIR:-/root/tmp}"
mkdir -p "$TMPDIR" "$ARTIFACT_ROOT/generation"

COMMON_ARGS=(
  --config "$CONFIG"
  --dataset-dir "$DATASET_DIR"
  --parent-sft-run-dir "$PARENT_RUN"
  --child-sft-run-dir "$CHILD_RUN"
  --output-root "$ARTIFACT_ROOT"
  --project-commit "$HANDOFF_COMMIT"
)

if [[ -f "$GEN_RUN/run.json" ]]; then
  if "$PY" "$RUNNER" "${COMMON_ARGS[@]}" --postcheck-only >/dev/null 2>&1; then
    echo "reuse strict-completed C36 generation: $GEN_RUN"
    "$PY" "$RUNNER" "${COMMON_ARGS[@]}" --postcheck-only
    exit 0
  fi
  echo "existing C36 generation is not strict-completed; exact-prefix resume will be attempted" >&2
fi

command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi unavailable"
GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits | head -n 1)"
[[ -n "$GPU_LINE" ]] || die "nvidia-smi did not return a GPU"
IFS=',' read -r GPU_NAME GPU_TOTAL GPU_FREE <<<"$GPU_LINE"
GPU_TOTAL="${GPU_TOTAL//[[:space:]]/}"
GPU_FREE="${GPU_FREE//[[:space:]]/}"
(( GPU_TOTAL >= 22528 )) || die "C36 generation requires a 24GB-class GPU; total MiB=$GPU_TOTAL"
(( GPU_FREE >= MIN_FREE_VRAM_MIB )) || die "C36 generation requires at least $MIN_FREE_VRAM_MIB MiB free VRAM; free MiB=$GPU_FREE"
ACTIVE_GPU_PIDS="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | tr -d '[:space:]')"
[[ -z "$ACTIVE_GPU_PIDS" ]] || die "another GPU compute process is active: $ACTIVE_GPU_PIDS"

echo "=== WP9-c C36 SFT-continuation frozen eval400 generation: batch=4 seed=42 ==="
"$PY" "$RUNNER" "${COMMON_ARGS[@]}"
"$PY" "$RUNNER" "${COMMON_ARGS[@]}" --postcheck-only

echo "=== PASS: C36 SFT-continuation eval400 b4 generation strict-completed ==="
echo "generation: $GEN_RUN"
