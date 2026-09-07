#!/usr/bin/env bash
set -Eeuo pipefail

C25_HANDOFF_COMMIT="322db1e1649d8c87b51352f57c0884b0b9a24bfc"
EXPECTED_CONFIG_SHA="205fc26db8b1c932ac8ce3279998e6d31b5aad8de7607fd94a69c833a72ae3f1"
EXPECTED_RUNNER_SHA="e1e19fab82f62cf2a1d62a50425b1407344bcca065cb8ebbf4311b15b75b6cdf"
EXPECTED_SFT_RUNTIME_SHA="8ade6d543cab165b7e3c44ae902986f514c1f49d2a9cccea01285b364ba9c8e2"
EXPECTED_REPORT_SHA="fb8a6eb053cf76ab947caeeff68a7328e5b6fd10c4e6d06936c1d8b64cd73e99"
EXPECTED_PREVALIDATION_SHA="c40fc3fdf35faf98fa85bc4c021c31fa6b471718547cce81d8557cb4f160cc86"
EXPECTED_TRAIN_SHA="de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582"
EXPECTED_VALIDATION_SHA="7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2"
EXPECTED_PROVENANCE_SHA="802bf96d3df5c53e2f1238db56dc122ac52ed7fec13ac5cc65d99a99d3edd94f"
EXPECTED_ORDER_SHA="82a58dcb6283d85149d7715675639a7782c4ed9a7c3d17646287a390719dd986"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
DATASET_DIR="/root/open-r1-code-verifier-data-4090/wp9c/sft-only-active1354-C32"
PARENT_RUN="/root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42"
OUTPUT_ROOT="/root/sj-tmp/open-r1-code-verifier-outputs/sft"
RUN_DIR="$OUTPUT_ROOT/wp9c-sft-only-active1354-seed42"
EVIDENCE_DIR="/root/sj-tmp/open-r1-code-verifier-outputs/operator/WP9-c/wp9c-sft-only-active1354/C32"
CONFIG="$REPO_ROOT/configs/sft/wp9c-sft-only-active1354.yaml"
RUNNER="$SCRIPT_DIR/run_sft_continuation.py"
SFT_RUNTIME="$REPO_ROOT/src/code_verifier/training/sft.py"

[[ -x "$PY" ]] || { echo "missing target .venv Python: $PY" >&2; exit 125; }
[[ "$HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "set WP9C_HANDOFF_COMMIT to the exact C32 handoff commit" >&2; exit 64; }
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$HANDOFF_COMMIT" ]] || { echo "target HEAD differs from WP9C_HANDOFF_COMMIT" >&2; exit 65; }
git -C "$REPO_ROOT" merge-base --is-ancestor "$C25_HANDOFF_COMMIT" "$HANDOFF_COMMIT" || { echo "C32 handoff is not descended from accepted C25" >&2; exit 65; }
DIRTY="$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all | grep -vE '^\?\? \.ai-bridge/' || true)"
[[ -z "$DIRTY" ]] || { echo "target checkout has non-.ai-bridge changes" >&2; printf '%s\n' "$DIRTY" >&2; exit 65; }

printf '%s  %s\n' "$EXPECTED_CONFIG_SHA" "$CONFIG" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_RUNNER_SHA" "$RUNNER" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_SFT_RUNTIME_SHA" "$SFT_RUNTIME" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_REPORT_SHA" "$DATASET_DIR/report.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_PREVALIDATION_SHA" "$DATASET_DIR/prevalidation.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_TRAIN_SHA" "$DATASET_DIR/training/sft.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_VALIDATION_SHA" "$DATASET_DIR/training/sft_validation.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_PROVENANCE_SHA" "$DATASET_DIR/manifest/target_provenance.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_ORDER_SHA" "$DATASET_DIR/manifest/problem_order.jsonl" | sha256sum -c -
[[ -d "$PARENT_RUN/checkpoints" ]] || { echo "frozen parent B is missing" >&2; exit 66; }
mkdir -p "$OUTPUT_ROOT" "$EVIDENCE_DIR"

export HF_HOME="${HF_HOME:-/root/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"
export TMPDIR="${TMPDIR:-/root/tmp}"
mkdir -p "$TMPDIR"

GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits | head -n 1)"
[[ -n "$GPU_LINE" ]] || { echo "nvidia-smi did not return a GPU" >&2; exit 125; }
IFS=',' read -r GPU_NAME GPU_TOTAL GPU_FREE <<<"$GPU_LINE"
GPU_TOTAL="${GPU_TOTAL//[[:space:]]/}"
GPU_FREE="${GPU_FREE//[[:space:]]/}"
(( GPU_TOTAL >= 22528 )) || { echo "C32 requires a 24GB-class GPU; total MiB=$GPU_TOTAL" >&2; exit 125; }

RESUME_ARGS=()
ACTION="fresh"
if [[ -d "$RUN_DIR" ]]; then
  [[ -f "$RUN_DIR/run.json" ]] || { echo "existing C32 run lacks run.json" >&2; exit 67; }
  STATUS="$($PY - "$RUN_DIR/run.json" <<'PY_STATUS'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(value.get('status',''))
PY_STATUS
)"
  if [[ "$STATUS" == "completed" ]]; then
    ACTION="completed_reuse"
  elif [[ "$STATUS" == "running" || "$STATUS" == "failed" ]]; then
    LATEST="$(find "$RUN_DIR/checkpoints" -mindepth 1 -maxdepth 1 -type d -name 'checkpoint-[0-9]*' -printf '%f\n' | sort -V | tail -n 1)"
    [[ -n "$LATEST" ]] || { echo "interrupted C32 run has no resumable checkpoint; refusing destructive restart" >&2; exit 68; }
    RESUME_ARGS=(--resume-from-checkpoint "$RUN_DIR/checkpoints/$LATEST")
    ACTION="resume:$LATEST"
  else
    echo "existing C32 run has invalid status: $STATUS" >&2
    exit 67
  fi
fi

if [[ "$ACTION" != "completed_reuse" ]]; then
  "$PY" "$RUNNER" \
    --dataset-dir "$DATASET_DIR" \
    --parent-sft-run-dir "$PARENT_RUN" \
    --output-root "$OUTPUT_ROOT" \
    "${RESUME_ARGS[@]}"
fi

"$PY" - "$RUN_DIR" "$EVIDENCE_DIR/postcheck.json" "$HANDOFF_COMMIT" "$ACTION" "$GPU_NAME" "$GPU_TOTAL" "$GPU_FREE" <<'PY_POST'
import hashlib
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
out = Path(sys.argv[2])
handoff, action, gpu_name, gpu_total, gpu_free = sys.argv[3:]
run = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
expected_parent = {
    'run_id': 'B-sft-formal-seed42',
    'model_id': 'Qwen/Qwen2.5-Coder-1.5B-Instruct',
    'model_revision': '2e1fd397ee46e1388853d2af2c993145b0f1098a',
    'dataset_hash': '4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c',
    'config_hash': '250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244',
    'dependency_lock_hash': '59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560',
    'seed': 42,
}
expected = {
    'status': 'completed',
    'run_id': 'wp9c-sft-only-active1354-seed42',
    'model_id': 'Qwen/Qwen2.5-Coder-1.5B-Instruct',
    'model_revision': '2e1fd397ee46e1388853d2af2c993145b0f1098a',
    'dataset_hash': 'de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582',
    'validation_dataset_hash': '7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2',
    'prevalidation_manifest_sha256': 'c40fc3fdf35faf98fa85bc4c021c31fa6b471718547cce81d8557cb4f160cc86',
    'seed': 42,
}
for key, value in expected.items():
    if run.get(key) != value:
        raise SystemExit(f'C32 completed run identity mismatch: {key}')
if run.get('parent_sft') != expected_parent:
    raise SystemExit('C32 completed run parent B identity mismatch')
checkpoint_dir = run_dir / 'checkpoints'
for name in ('adapter_config.json', 'adapter_model.safetensors'):
    if not (checkpoint_dir / name).is_file():
        raise SystemExit(f'C32 completed adapter missing: {name}')

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

summary = {
    'schema_version': 1,
    'status': 'completed_verified',
    'handoff_commit': handoff,
    'action': action,
    'gpu': {'name': gpu_name.strip(), 'total_mib': int(gpu_total), 'free_mib_at_preflight': int(gpu_free)},
    'run_dir': str(run_dir),
    'run_json_sha256': digest(run_dir / 'run.json'),
    'metrics_sha256': digest(run_dir / 'metrics.jsonl'),
    'adapter_config_sha256': digest(checkpoint_dir / 'adapter_config.json'),
    'adapter_model_sha256': digest(checkpoint_dir / 'adapter_model.safetensors'),
    'train_problem_count': 1354,
    'parent_run_id': expected_parent['run_id'],
}
out.write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, sort_keys=True))
PY_POST

echo "C32_SFT_ONLY_TRAINING_OK action=$ACTION run=$RUN_DIR"
