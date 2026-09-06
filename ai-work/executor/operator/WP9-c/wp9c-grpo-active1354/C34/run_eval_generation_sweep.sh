#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"
[[ -x "$PY" ]] || { echo "target .venv Python is unavailable" >&2; exit 125; }

HANDOFF="${WP9C_HANDOFF_COMMIT:-}"
[[ "$HANDOFF" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9C_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$(git rev-parse HEAD)" == "$HANDOFF" ]] || { echo "target HEAD differs from WP9C_HANDOFF_COMMIT" >&2; exit 125; }
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean" >&2; exit 125; }

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
readarray -t ROOTS < <("$PY" - "$MACHINE_POINTER" <<'PY_MACHINE'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("machine_status") != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine is not READY_FOR_VALIDATION_PLANNER")
for key in ("artifact_root", "hf_home", "formal_data_root"):
    path=Path(value.get(key, ""))
    if not path.is_absolute() or not str(path).startswith("/root/") or "/data" in str(path):
        raise SystemExit(f"invalid validation-machine {key}")
    print(path)
PY_MACHINE
)
ARTIFACT_ROOT="${ROOTS[0]}"; HF_HOME_TARGET="${ROOTS[1]}"; FORMAL_DATA_ROOT="${ROOTS[2]}"
export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$HF_HOME_TARGET"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export TMPDIR="/root/tmp"
mkdir -p "$TMPDIR"

DATASET_DIR="$FORMAL_DATA_ROOT/wp9c/heldout-eval200-C34"
B_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
OUT_BASE="$ARTIFACT_ROOT/wp9c/grpo-c29/eval200-generation"
CONFIG="$REPO_ROOT/configs/eval/base.yaml"
[[ -d "$DATASET_DIR" ]] || { echo "heldout-eval200-C34 is missing; rsync it first" >&2; exit 125; }
[[ -d "$B_RUN" ]] || { echo "formal B run is missing" >&2; exit 125; }

EXPECTED=(
  "6d90392983a8605773b1f83acb2811f666290598fec8eec4f2225d2eb95d64d3 canonical/problems.jsonl"
  "0713020cf3c0c5cf8ede7883be4dda2dabdc9e763b88ffeb94df538120ed11c6 hf_dataset/data-00000-of-00001.arrow"
  "92bbb50ce5825d6c8ee4a675a9199f0ebae50535909313d1e442ed28d68895f9 hf_dataset/dataset_info.json"
  "cd9375ded43d13e712090ddf5dbaadcd682e4d8a0e22b70904f9aa3ad216fcb0 hf_dataset/state.json"
  "79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7 training/hidden_grpo.jsonl"
  "94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223 training/public_grpo.jsonl"
  "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c training/sft.jsonl"
  "7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2 training/sft_validation.jsonl"
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
if value.get("schema_version") != "wp9c-c34-eval200-subset-v1": raise SystemExit("eval200 manifest schema drift")
if value.get("selection") != "first_200_in_frozen_order" or value.get("problem_count") != 200:
    raise SystemExit("eval200 deterministic selection drift")
if value.get("ordered_problem_ids_sha256") != "8a723184e8c3787cf8c18f2d9f6ddd59f6928ca4711b31dc196e4daffb91a422":
    raise SystemExit("eval200 ordered problem IDs drift")
source=value.get("source_eval400", {})
if source.get("test_problem_count") != 400:
    raise SystemExit("eval200 source eval400 count drift")
if source.get("artifact_sha256", {}).get("canonical/problems.jsonl") != "d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6":
    raise SystemExit("eval200 source eval400 identity drift")
contract=value.get("scientific_evaluation_contract", {})
if contract.get("heldout_eval400_remains_authoritative") is not True:
    raise SystemExit("eval400 scientific authority contract drift")
PY_EVAL200

"$PY" - "$B_RUN" <<'PY_B'
import sys
from pathlib import Path
from code_verifier.training.sft import load_completed_sft_checkpoint
identity=load_completed_sft_checkpoint(Path(sys.argv[1]))
if identity.run_id != "B-sft-formal-seed42" or identity.model_id != "Qwen/Qwen2.5-Coder-1.5B-Instruct":
    raise SystemExit("formal B identity drift")
if identity.model_revision != "2e1fd397ee46e1388853d2af2c993145b0f1098a" or identity.seed != 42:
    raise SystemExit("formal B revision/seed drift")
PY_B

command -v nvidia-smi >/dev/null 2>&1 || { echo "nvidia-smi unavailable" >&2; exit 125; }
GPU_TOTAL="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n 1 | tr -d ' ')"
[[ "$GPU_TOTAL" =~ ^[0-9]+$ && "$GPU_TOTAL" -ge 22528 ]] || { echo "evaluation generation requires >=22528 MiB target GPU" >&2; exit 125; }

mkdir -p "$OUT_BASE"
for BATCH in 1 2 4 8 16; do
  RUN_NAME="wp9c-c29-b-eval200-b${BATCH}-seed42"
  OUT_ROOT="$OUT_BASE/b${BATCH}"
  RUN_DIR="$OUT_ROOT/generation/$RUN_NAME"
  if [[ -d "$RUN_DIR" ]]; then
    if "$PY" - "$RUN_DIR" "$BATCH" <<'PY_DONE'
import json, sys
from pathlib import Path
run=Path(sys.argv[1]); batch=int(sys.argv[2])
value=json.loads((run/"run.json").read_text(encoding="utf-8"))
if value.get("status") != "completed" or value.get("total_problems") != 200 or value.get("completed_records") != 200:
    raise SystemExit(1)
if value.get("batch_size") != batch or value.get("seed") != 42:
    raise SystemExit(1)
PY_DONE
    then
      echo "reuse completed generation: $RUN_DIR"
      continue
    fi
    echo "incomplete/nonmatching generation exists: $RUN_DIR" >&2
    exit 125
  fi
  "$PY" -m code_verifier.cli generate-eval \
    --config "$CONFIG" \
    --dataset-dir "$DATASET_DIR" \
    --sft-run-dir "$B_RUN" \
    --run-name "$RUN_NAME" \
    --batch-size "$BATCH" \
    --seed 42 \
    --output-dir "$OUT_ROOT"
done

"$PY" - "$OUT_BASE" <<'PY_PARITY'
import json, sys
from pathlib import Path
from code_verifier.throughput import compare_generation_bundle_parity
root=Path(sys.argv[1])
base=root/"b1"/"generation"/"wp9c-c29-b-eval200-b1-seed42"
result={"baseline": str(base), "candidates": {}}
for batch in (2,4,8,16):
    run=root/f"b{batch}"/"generation"/f"wp9c-c29-b-eval200-b{batch}-seed42"
    parity=compare_generation_bundle_parity(base, run)
    result["candidates"][str(batch)]={"exact": parity.exact, "reason": parity.reason, "problem_count": parity.problem_count}
    if not parity.exact or parity.problem_count != 200:
        raise SystemExit(f"batch {batch} generation parity failed: {parity}")
print(json.dumps(result, sort_keys=True))
PY_PARITY

echo "C34 evaluation generation sweep PASS: $OUT_BASE"
