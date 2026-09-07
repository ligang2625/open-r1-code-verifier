#!/usr/bin/env bash
set -Eeuo pipefail

RUN_NAME="wp9c-sft-only-active1354-seed42"
C25_HANDOFF_COMMIT="322db1e1649d8c87b51352f57c0884b0b9a24bfc"
EXPECTED_EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
EXPECTED_CANONICAL_SHA="d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6"
EXPECTED_HF_ARROW_SHA="474edfd8731dea9f4938630f4f4903b6a016124c9ee5d4d4eed2a322015c47af"
EXPECTED_HF_INFO_SHA="92bbb50ce5825d6c8ee4a675a9199f0ebae50535909313d1e442ed28d68895f9"
EXPECTED_HF_STATE_SHA="ea62279de3ce3df8f6908e3a9dd1901734f12fc6cc0569cda75527e2d7841ca1"
EXPECTED_HIDDEN_GRPO_SHA="79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7"
EXPECTED_PUBLIC_GRPO_SHA="94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223"
EXPECTED_SFT_SHA="4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c"
EXPECTED_SFT_VALIDATION_SHA="7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2"
EXPECTED_EVAL_DATASET_HASH="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
EXPECTED_ORDER_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
DATASET_DIR="/root/open-r1-code-verifier-data-4090/wp9c/heldout-eval400-C33"
SFT_RUN="/root/sj-tmp/open-r1-code-verifier-outputs/sft/$RUN_NAME"
OUTPUT_ROOT="/root/sj-tmp/open-r1-code-verifier-outputs/evaluation"
GEN_RUN="$OUTPUT_ROOT/generation/$RUN_NAME"
CONFIG="$REPO_ROOT/configs/eval/base.yaml"

[[ -x "$PY" ]] || { echo "missing target .venv Python" >&2; exit 125; }
[[ "$HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "set WP9C_HANDOFF_COMMIT" >&2; exit 64; }
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$HANDOFF_COMMIT" ]] || { echo "target HEAD differs from handoff" >&2; exit 65; }
git -C "$REPO_ROOT" merge-base --is-ancestor "$C25_HANDOFF_COMMIT" "$HANDOFF_COMMIT" || { echo "handoff is not descended from C25" >&2; exit 65; }
DIRTY="$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all | grep -vE '^\?\? \.ai-bridge/' || true)"
[[ -z "$DIRTY" ]] || { echo "target checkout has non-.ai-bridge changes" >&2; exit 65; }

printf '%s  %s\n' "$EXPECTED_EVAL_CONFIG_SHA" "$CONFIG" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_CANONICAL_SHA" "$DATASET_DIR/canonical/problems.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_HF_ARROW_SHA" "$DATASET_DIR/hf_dataset/data-00000-of-00001.arrow" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_HF_INFO_SHA" "$DATASET_DIR/hf_dataset/dataset_info.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_HF_STATE_SHA" "$DATASET_DIR/hf_dataset/state.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_HIDDEN_GRPO_SHA" "$DATASET_DIR/training/hidden_grpo.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_PUBLIC_GRPO_SHA" "$DATASET_DIR/training/public_grpo.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_SFT_SHA" "$DATASET_DIR/training/sft.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_SFT_VALIDATION_SHA" "$DATASET_DIR/training/sft_validation.jsonl" | sha256sum -c -
[[ -f "$SFT_RUN/run.json" ]] || { echo "completed C32 SFT run is missing" >&2; exit 66; }

export HF_HOME="${HF_HOME:-/root/huggingface}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"
export TMPDIR="${TMPDIR:-/root/tmp}"
mkdir -p "$TMPDIR" "$OUTPUT_ROOT"

"$PY" - "$SFT_RUN" <<'PY_SFT'
import json, sys
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
run_dir=Path(sys.argv[1])
identity=load_completed_sft_checkpoint(run_dir)
run=json.loads((run_dir/'run.json').read_text(encoding='utf-8'))
if identity.run_id != 'wp9c-sft-only-active1354-seed42':
    raise SystemExit('C32 SFT run id mismatch')
if identity.dataset_hash != 'de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582':
    raise SystemExit('C32 SFT dataset identity mismatch')
if run.get('parent_sft',{}).get('run_id') != 'B-sft-formal-seed42':
    raise SystemExit('C32 SFT parent identity mismatch')
PY_SFT

GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits | head -n 1)"
[[ -n "$GPU_LINE" ]] || { echo "nvidia-smi did not return a GPU" >&2; exit 125; }
IFS=',' read -r GPU_NAME GPU_TOTAL <<<"$GPU_LINE"
GPU_TOTAL="${GPU_TOTAL//[[:space:]]/}"
(( GPU_TOTAL >= 22528 )) || { echo "C33 generation requires the 24GB target" >&2; exit 125; }

"$PY" -m code_verifier.cli generate-eval \
  --config "$CONFIG" \
  --dataset-dir "$DATASET_DIR" \
  --sft-run-dir "$SFT_RUN" \
  --run-name "$RUN_NAME" \
  --batch-size 1 \
  --seed 42 \
  --output-dir "$OUTPUT_ROOT"

"$PY" - "$GEN_RUN" <<'PY_POST'
import json, sys
from pathlib import Path
run_dir=Path(sys.argv[1])
run=json.loads((run_dir/'run.json').read_text(encoding='utf-8'))
expected={
    'status':'completed',
    'run_id':'wp9c-sft-only-active1354-seed42',
    'total_problems':400,
    'completed_records':400,
    'dataset_hash':'770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae',
    'ordered_problem_ids_sha256':'2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9',
    'seed':42,
}
for key,value in expected.items():
    if run.get(key) != value:
        raise SystemExit(f'C33 generation identity mismatch: {key}')
print(json.dumps({'status':'C33_GENERATION_OK','records_sha256':run.get('records_sha256'),'gpu_name':run.get('gpu_name')},sort_keys=True))
PY_POST
