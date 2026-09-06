#!/usr/bin/env bash
set -Eeuo pipefail

GENERATION_RUN="${1:-}"
DATASET_DIR="${2:-}"
OUTPUT_BASE="${3:-}"
[[ "$GENERATION_RUN" = /* && -d "$GENERATION_RUN" ]] || { echo "usage: run_eval_verification_sweep.sh <absolute-eval200-b1-generation-run> <absolute-eval200-dataset> <absolute-output-base>" >&2; exit 64; }
[[ "$DATASET_DIR" = /* && -d "$DATASET_DIR" ]] || { echo "evaluation dataset must be an existing absolute directory" >&2; exit 64; }
[[ "$OUTPUT_BASE" = /* ]] || { echo "output base must be absolute" >&2; exit 64; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"
[[ -x "$PY" ]] || { echo ".venv Python is unavailable" >&2; exit 125; }
HANDOFF="${WP9C_HANDOFF_COMMIT:-}"
[[ "$HANDOFF" =~ ^[0-9a-f]{40}$ && "$(git rev-parse HEAD)" == "$HANDOFF" ]] || { echo "checkout exact WP9C_HANDOFF_COMMIT first" >&2; exit 125; }
# .ai-bridge is local machine state; no tracked/untracked project changes are allowed.
DIRTY="$(git status --porcelain=v1 --untracked-files=normal | grep -vE '^\?\? \.ai-bridge/' || true)"
[[ -z "$DIRTY" ]] || { echo "control-plane checkout must be clean outside .ai-bridge" >&2; exit 125; }

EXPECTED=(
  "6d90392983a8605773b1f83acb2811f666290598fec8eec4f2225d2eb95d64d3 canonical/problems.jsonl"
  "0713020cf3c0c5cf8ede7883be4dda2dabdc9e763b88ffeb94df538120ed11c6 hf_dataset/data-00000-of-00001.arrow"
  "92bbb50ce5825d6c8ee4a675a9199f0ebae50535909313d1e442ed28d68895f9 hf_dataset/dataset_info.json"
  "cd9375ded43d13e712090ddf5dbaadcd682e4d8a0e22b70904f9aa3ad216fcb0 hf_dataset/state.json"
)
for item in "${EXPECTED[@]}"; do
  sha="${item%% *}"; rel="${item#* }"
  [[ -f "$DATASET_DIR/$rel" && "$(sha256sum "$DATASET_DIR/$rel" | awk '{print $1}')" == "$sha" ]] || {
    echo "heldout eval200 dataset hash mismatch: $rel" >&2; exit 125;
  }
done

"$PY" - "$DATASET_DIR/eval200_manifest.json" <<'PY_EVAL200'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("selection") != "first_200_in_frozen_order" or value.get("problem_count") != 200:
    raise SystemExit("eval200 deterministic selection drift")
if value.get("ordered_problem_ids_sha256") != "8a723184e8c3787cf8c18f2d9f6ddd59f6928ca4711b31dc196e4daffb91a422":
    raise SystemExit("eval200 ordered problem IDs drift")
PY_EVAL200

CONFIG="$REPO_ROOT/configs/eval/base.yaml"
PISTON_CONFIG="$REPO_ROOT/configs/execution/piston-local.yaml"
"$PY" - "$GENERATION_RUN" <<'PY_GEN'
import json, sys
from pathlib import Path
from code_verifier.evaluation.staged import load_generation_bundle_source
run=Path(sys.argv[1])
source=load_generation_bundle_source(run)
value=json.loads((run/"run.json").read_text(encoding="utf-8"))
if source.run_id != "wp9c-c29-b-eval200-b1-seed42" or source.seed != 42:
    raise SystemExit("batch-1 generation source identity drift")
if value.get("batch_size") != 1 or value.get("total_problems") != 200 or value.get("completed_records") != 200:
    raise SystemExit("batch-1 generation source is not complete formal eval200")
PY_GEN

"$PY" - "$PISTON_CONFIG" <<'PY_PISTON'
import sys
from pathlib import Path
from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config
PistonExecutor(load_piston_executor_config(Path(sys.argv[1]))).validate_runtime()
PY_PISTON

RUN_NAME="wp9c-c29-b-eval200-b1-seed42"
mkdir -p "$OUTPUT_BASE"
for WORKERS in 1 8 16 32 64; do
  OUT_ROOT="$OUTPUT_BASE/v${WORKERS}"
  RUN_DIR="$OUT_ROOT/evaluation/$RUN_NAME"
  if [[ -d "$RUN_DIR" ]]; then
    if "$PY" - "$RUN_DIR" "$WORKERS" <<'PY_DONE'
import json, sys
from pathlib import Path
value=json.loads((Path(sys.argv[1])/"run.json").read_text(encoding="utf-8"))
if value.get("status") != "completed" or value.get("completed_records") != 200 or value.get("verification_workers") != int(sys.argv[2]):
    raise SystemExit(1)
PY_DONE
    then
      echo "reuse completed verification: $RUN_DIR"
      continue
    fi
    echo "incomplete/nonmatching verification exists: $RUN_DIR" >&2
    exit 125
  fi
  "$PY" -m code_verifier.cli verify-eval \
    --config "$CONFIG" \
    --dataset-dir "$DATASET_DIR" \
    --generation-run-dir "$GENERATION_RUN" \
    --run-name "$RUN_NAME" \
    --workers "$WORKERS" \
    --seed 42 \
    --output-dir "$OUT_ROOT"
done

echo "C34 evaluation verification sweep PASS: $OUTPUT_BASE"
