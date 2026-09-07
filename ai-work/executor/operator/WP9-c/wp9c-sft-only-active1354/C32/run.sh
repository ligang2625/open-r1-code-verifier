#!/usr/bin/env bash
set -Eeuo pipefail

BASE_HANDOFF_COMMIT="322db1e1649d8c87b51352f57c0884b0b9a24bfc"
EXPECTED_CONFIG_SHA="f1994feee9a7f70576c22beb13b2e0a8a383de200a8ba8574a8b9077128774b8"
EXPECTED_RUNNER_SHA="e1e19fab82f62cf2a1d62a50425b1407344bcca065cb8ebbf4311b15b75b6cdf"
EXPECTED_SFT_RUNTIME_SHA="4d020000fb7a89757472084c3d0fba71b5c1e0149351a81c93e725c7c214c23a"
EXPECTED_REPORT_SHA="fb8a6eb053cf76ab947caeeff68a7328e5b6fd10c4e6d06936c1d8b64cd73e99"
EXPECTED_PREVALIDATION_SHA="c40fc3fdf35faf98fa85bc4c021c31fa6b471718547cce81d8557cb4f160cc86"
EXPECTED_TRAIN_SHA="de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582"
EXPECTED_VALIDATION_SHA="7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2"
EXPECTED_PROVENANCE_SHA="802bf96d3df5c53e2f1238db56dc122ac52ed7fec13ac5cc65d99a99d3edd94f"
EXPECTED_ORDER_SHA="82a58dcb6283d85149d7715675639a7782c4ed9a7c3d17646287a390719dd986"
MIN_FREE_GIB=20
MIN_FREE_INODES=100000
MIN_FREE_VRAM_MIB=20000

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
ARTIFACT_ROOT="${CODE_VERIFIER_ARTIFACT_ROOT:-/root/sj-tmp/open-r1-code-verifier-outputs}"
FORMAL_DATA_ROOT="${CODE_VERIFIER_DATA_ROOT:-/root/open-r1-code-verifier-data-4090}"
HF_HOME_TARGET="${HF_HOME:-/root/huggingface}"
DATASET_DIR="$FORMAL_DATA_ROOT/wp9c/sft-only-active1354-C32"
PARENT_RUN="$ARTIFACT_ROOT/sft/B-sft-formal-seed42"
OUTPUT_ROOT="$ARTIFACT_ROOT/sft"
RUN_DIR="$OUTPUT_ROOT/wp9c-sft-only-active1354-seed42"
EVIDENCE_DIR="$ARTIFACT_ROOT/operator/WP9-c/wp9c-sft-only-active1354/C32"
CONFIG="$REPO_ROOT/configs/sft/wp9c-sft-only-active1354.yaml"
RUNNER="$SCRIPT_DIR/run_sft_continuation.py"
FAILED_ARCHIVE_ROOT="$EVIDENCE_DIR/precheckpoint-failures"
SFT_RUNTIME="$REPO_ROOT/src/code_verifier/training/sft.py"
LOCK_FILE="$EVIDENCE_DIR/run.lock"

fail() {
  echo "ERROR: $*" >&2
  exit 125
}

[[ -x "$PY" ]] || fail "missing target .venv Python: $PY"
[[ "$HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "set WP9C_HANDOFF_COMMIT to the exact C32 handoff commit" >&2; exit 64; }
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$HANDOFF_COMMIT" ]] || { echo "target HEAD differs from WP9C_HANDOFF_COMMIT" >&2; exit 65; }
git -C "$REPO_ROOT" merge-base --is-ancestor "$BASE_HANDOFF_COMMIT" "$HANDOFF_COMMIT" || { echo "C32 handoff is not descended from accepted C25" >&2; exit 65; }
DIRTY="$(git -C "$REPO_ROOT" status --porcelain --ignore-submodules=none | grep -vE '^\?\? \.ai-bridge/' || true)"
[[ -z "$DIRTY" ]] || { echo "target checkout has non-.ai-bridge changes" >&2; printf '%s\n' "$DIRTY" >&2; exit 65; }

for root in "$ARTIFACT_ROOT" "$FORMAL_DATA_ROOT" "$HF_HOME_TARGET"; do
  [[ "$root" == /root || "$root" == /root/* ]] || fail "active target root must be under /root: $root"
  [[ "$root" != /data && "$root" != /data/* ]] || fail "retired /data root must not be active: $root"
done

printf '%s  %s\n' "$EXPECTED_CONFIG_SHA" "$CONFIG" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_RUNNER_SHA" "$RUNNER" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_SFT_RUNTIME_SHA" "$SFT_RUNTIME" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_REPORT_SHA" "$DATASET_DIR/report.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_PREVALIDATION_SHA" "$DATASET_DIR/prevalidation.json" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_TRAIN_SHA" "$DATASET_DIR/training/sft.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_VALIDATION_SHA" "$DATASET_DIR/training/sft_validation.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_PROVENANCE_SHA" "$DATASET_DIR/manifest/target_provenance.jsonl" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_ORDER_SHA" "$DATASET_DIR/manifest/problem_order.jsonl" | sha256sum -c -
[[ -d "$PARENT_RUN" ]] || fail "frozen parent B is missing: $PARENT_RUN"
[[ -d "$HF_HOME_TARGET" && -r "$HF_HOME_TARGET" ]] || fail "HF_HOME is missing or unreadable: $HF_HOME_TARGET"

export CODE_VERIFIER_ARTIFACT_ROOT="$ARTIFACT_ROOT"
export CODE_VERIFIER_DATA_ROOT="$FORMAL_DATA_ROOT"
export HF_HOME="$HF_HOME_TARGET"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"
export TMPDIR="${TMPDIR:-/root/tmp}"
mkdir -p "$TMPDIR" "$OUTPUT_ROOT" "$EVIDENCE_DIR"

exec 9>"$LOCK_FILE"
flock -n 9 || fail "C32 training lock is already held: $LOCK_FILE"

"$PY" - "$PARENT_RUN" "$CONFIG" "$DATASET_DIR" <<'PY_PREFLIGHT'
import sys
from dataclasses import replace
from pathlib import Path

from code_verifier.training.sft import _config_hash, load_completed_sft_checkpoint, load_sft_training_config

parent_dir = Path(sys.argv[1])
config_path = Path(sys.argv[2])
dataset_dir = Path(sys.argv[3])
parent = load_completed_sft_checkpoint(parent_dir)
expected_parent = {
    "run_id": "B-sft-formal-seed42",
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "dataset_hash": "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c",
    "config_hash": "250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244",
    "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
    "seed": 42,
}
actual_parent = {
    "run_id": parent.run_id,
    "model_id": parent.model_id,
    "model_revision": parent.model_revision,
    "dataset_hash": parent.dataset_hash,
    "config_hash": parent.config_hash,
    "dependency_lock_hash": parent.dependency_lock_hash,
    "seed": parent.seed,
}
if actual_parent != expected_parent:
    raise SystemExit("frozen parent B identity drift")
config = load_sft_training_config(config_path)
config = replace(
    config,
    dataset_path=dataset_dir / "training/sft.jsonl",
    validation_dataset_path=dataset_dir / "training/sft_validation.jsonl",
    piston_config=Path.cwd() / "configs/execution/piston-local.yaml",
)
expected_recipe = {
    "learning_rate": 2e-4,
    "num_train_epochs": 2.0,
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 16,
    "save_steps": 30,
    "lora_r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "max_seq_length": 2304,
    "seed": 42,
}
for key, expected in expected_recipe.items():
    if getattr(config, key) != expected:
        raise SystemExit(f"C32 training recipe drift: {key}")
print(f"C32_CONFIG_HASH={_config_hash(config, seed=42)}")
PY_PREFLIGHT

ACTION="fresh"
RESUME_ARGS=()
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
    if [[ -n "$LATEST" ]]; then
      RESUME_ARGS=(--resume-from-checkpoint "$RUN_DIR/checkpoints/$LATEST")
      ACTION="resume:$LATEST"
    else
      "$PY" - "$RUN_DIR/run.json" <<'PY_FAILED_IDENTITY'
import json
import sys
from pathlib import Path

run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "run_id": "wp9c-sft-only-active1354-seed42",
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "dataset_hash": "de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582",
    "validation_dataset_hash": "7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2",
    "seed": 42,
}
for key, value in expected.items():
    if run.get(key) != value:
        raise SystemExit(f"pre-checkpoint failed run identity mismatch: {key}")
if run.get("status") not in {"running", "failed"}:
    raise SystemExit("pre-checkpoint run is not resumable/failed")
parent = run.get("parent_sft")
if not isinstance(parent, dict) or parent.get("run_id") != "B-sft-formal-seed42":
    raise SystemExit("pre-checkpoint failed run parent identity mismatch")
PY_FAILED_IDENTITY
      mkdir -p "$FAILED_ARCHIVE_ROOT"
      RUN_JSON_PREFIX="$(sha256sum "$RUN_DIR/run.json" | awk '{print substr($1,1,12)}')"
      ARCHIVE_DIR="$FAILED_ARCHIVE_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$RUN_JSON_PREFIX"
      [[ ! -e "$ARCHIVE_DIR" ]] || { echo "pre-checkpoint archive already exists: $ARCHIVE_DIR" >&2; exit 68; }
      mv "$RUN_DIR" "$ARCHIVE_DIR"
      ACTION="restart_after_precheckpoint_failure:$ARCHIVE_DIR"
      echo "archived non-resumable pre-checkpoint C32 run: $ARCHIVE_DIR"
    fi
  else
    echo "existing C32 run has invalid status: $STATUS" >&2
    exit 67
  fi
fi

if [[ "$ACTION" != "completed_reuse" ]]; then
  "$PY" - "$ARTIFACT_ROOT" "$MIN_FREE_GIB" "$MIN_FREE_INODES" <<'PY_STORAGE'
import os, shutil, sys
from pathlib import Path
root = Path(sys.argv[1])
minimum_bytes = int(sys.argv[2]) * 1024**3
minimum_inodes = int(sys.argv[3])
usage = shutil.disk_usage(root)
stat = os.statvfs(root)
if usage.free < minimum_bytes:
    raise SystemExit(f"C32 requires at least {minimum_bytes} free bytes; found {usage.free}")
if stat.f_favail < minimum_inodes:
    raise SystemExit(f"C32 requires at least {minimum_inodes} free inodes; found {stat.f_favail}")
print(f"storage_free_bytes={usage.free} storage_free_inodes={stat.f_favail}")
PY_STORAGE

  GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits | head -n 1)"
  [[ -n "$GPU_LINE" ]] || fail "nvidia-smi did not return a GPU"
  IFS=',' read -r GPU_NAME GPU_TOTAL GPU_FREE <<<"$GPU_LINE"
  GPU_TOTAL="${GPU_TOTAL//[[:space:]]/}"
  GPU_FREE="${GPU_FREE//[[:space:]]/}"
  (( GPU_TOTAL >= 22528 )) || fail "C32 requires a 24GB-class GPU; total MiB=$GPU_TOTAL"
  (( GPU_FREE >= MIN_FREE_VRAM_MIB )) || fail "C32 requires at least $MIN_FREE_VRAM_MIB MiB free VRAM; free MiB=$GPU_FREE"
  ACTIVE_GPU_PIDS="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | tr -d '[:space:]')"
  [[ -z "$ACTIVE_GPU_PIDS" ]] || fail "another GPU compute process is active: $ACTIVE_GPU_PIDS"

  "$PY" "$RUNNER" \
    --dataset-dir "$DATASET_DIR" \
    --parent-sft-run-dir "$PARENT_RUN" \
    --output-root "$OUTPUT_ROOT" \
    "${RESUME_ARGS[@]}"
fi

"$PY" - "$RUN_DIR" "$EVIDENCE_DIR/postcheck.json" "$HANDOFF_COMMIT" "$ACTION" "$CONFIG" "$DATASET_DIR" <<'PY_POST'
import hashlib
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

from code_verifier.training.sft import _config_hash, load_completed_sft_checkpoint, load_sft_training_config

run_dir = Path(sys.argv[1])
out = Path(sys.argv[2])
handoff = sys.argv[3]
action = sys.argv[4]
config_path = Path(sys.argv[5])
dataset_dir = Path(sys.argv[6])
identity = load_completed_sft_checkpoint(run_dir)
run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
config = load_sft_training_config(config_path)
config = replace(
    config,
    dataset_path=dataset_dir / "training/sft.jsonl",
    validation_dataset_path=dataset_dir / "training/sft_validation.jsonl",
    piston_config=Path.cwd() / "configs/execution/piston-local.yaml",
)
expected_parent = {
    "run_id": "B-sft-formal-seed42",
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "dataset_hash": "4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c",
    "config_hash": "250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244",
    "dependency_lock_hash": "59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560",
    "seed": 42,
}
expected = {
    "status": "completed",
    "run_id": "wp9c-sft-only-active1354-seed42",
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "model_revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
    "dataset_hash": "de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582",
    "validation_dataset_hash": "7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2",
    "prevalidation_manifest_sha256": "c40fc3fdf35faf98fa85bc4c021c31fa6b471718547cce81d8557cb4f160cc86",
    "config_hash": _config_hash(config, seed=42),
    "git_commit": handoff,
    "seed": 42,
}
for key, value in expected.items():
    if run.get(key) != value:
        raise SystemExit(f"C32 completed run identity mismatch: {key}: {run.get(key)!r} != {value!r}")
if run.get("parent_sft") != expected_parent:
    raise SystemExit("C32 completed run parent B identity mismatch")
if identity.run_id != expected["run_id"] or identity.dataset_hash != expected["dataset_hash"] or identity.config_hash != expected["config_hash"]:
    raise SystemExit("C32 strict checkpoint identity mismatch")
summary_rows = []
for line in (run_dir / "metrics.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    value = json.loads(line)
    if value.get("record_type") == "summary":
        summary_rows.append(value)
if len(summary_rows) != 1:
    raise SystemExit("C32 metrics must contain exactly one summary row")
summary_row = summary_rows[0]
for key, expected_value in {"global_step": 170, "train_samples": 1354, "eval_samples": 300}.items():
    if summary_row.get(key) != expected_value:
        raise SystemExit(f"C32 training summary mismatch: {key}")
loss = summary_row.get("train_loss")
if isinstance(loss, bool) or not isinstance(loss, (int, float)) or not math.isfinite(float(loss)):
    raise SystemExit("C32 train_loss is not finite")

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

checkpoint_dir = run_dir / "checkpoints"
result = {
    "schema_version": 2,
    "status": "completed_verified",
    "handoff_commit": handoff,
    "action": action,
    "run_dir": str(run_dir),
    "run_json_sha256": digest(run_dir / "run.json"),
    "metrics_sha256": digest(run_dir / "metrics.jsonl"),
    "adapter_config_sha256": digest(checkpoint_dir / "adapter_config.json"),
    "adapter_model_sha256": digest(checkpoint_dir / "adapter_model.safetensors"),
    "train_problem_count": 1354,
    "validation_problem_count": 300,
    "global_step": 170,
    "parent_run_id": expected_parent["run_id"],
    "config_hash": expected["config_hash"],
}
out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
PY_POST

echo "C32_SFT_ONLY_TRAINING_OK action=$ACTION run=$RUN_DIR"
