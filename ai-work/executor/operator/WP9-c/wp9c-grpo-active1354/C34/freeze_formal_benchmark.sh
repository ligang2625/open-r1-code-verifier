#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"
HANDOFF="${WP9C_HANDOFF_COMMIT:-}"
[[ "$HANDOFF" =~ ^[0-9a-f]{40}$ && "$(git rev-parse HEAD)" == "$HANDOFF" ]] || { echo "checkout exact WP9C_HANDOFF_COMMIT first" >&2; exit 125; }
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
import json
import sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("machine_status") != "READY_FOR_VALIDATION_PLANNER":
    raise SystemExit("validation machine not ready")
for key in ("artifact_root", "formal_data_root"):
    path = Path(value.get(key, ""))
    if not path.is_absolute() or not str(path).startswith("/root/"):
        raise SystemExit(f"invalid {key}")
    print(path)
PY_MACHINE
)
ARTIFACT_ROOT="${ROOTS[0]}"
FORMAL_DATA_ROOT="${ROOTS[1]}"
BASE="$ARTIFACT_ROOT/wp9c/grpo-c29"
POOL="$FORMAL_DATA_ROOT/wp9c/final-reduced-calibration-C29"
OUT="$BASE/benchmark"
REPORT="$OUT/report/refresh_benchmark_report.json"
SUMMARY="$OUT/freeze_summary.json"
mkdir -p "$OUT/report"

"$PY" - "$POOL" "$REPORT" "$SUMMARY" <<'PY_FREEZE'
import hashlib
import json
import sys
from pathlib import Path

pool, report_path, summary_path = map(Path, sys.argv[1:])
manifest_path = pool / "calibration_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if manifest.get("status") != "completed" or manifest.get("schema_version") != "wp9c-reduced-calibration-v1":
    raise SystemExit("C29 calibration manifest is not completed/frozen")
if manifest.get("evidence_class") != "formal_calibration":
    raise SystemExit("C29 calibration is not formal")
artifacts = manifest.get("artifacts")
if not isinstance(artifacts, dict):
    raise SystemExit("C29 calibration artifact inventory is invalid")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

public_path = pool / "training" / "public_grpo.jsonl"
hidden_path = pool / "training" / "hidden_grpo.jsonl"
public_sha = sha(public_path)
hidden_sha = sha(hidden_path)
if artifacts.get("training/public_grpo.jsonl") != public_sha:
    raise SystemExit("C29 Public training hash mismatch")
if artifacts.get("training/hidden_grpo.jsonl") != hidden_sha:
    raise SystemExit("C29 Hidden training hash mismatch")
active_order = manifest.get("active_order_sha256")
if not isinstance(active_order, str) or len(active_order) != 64:
    raise SystemExit("C29 active order hash is invalid")

report = {
    "version": "wp9c-fixed-execution-v1",
    "evidence_class": "formal",
    "selection_source": "operator_fixed_reuse",
    "selected_eval_generation_batch_size": 4,
    "selected_eval_verification_workers": 64,
    "selected_grpo_verification_workers": 8,
    "paired_grpo_mode": "sequential",
    "calibration_identity": {
        "calibration_manifest_sha256": sha(manifest_path),
        "active_order_sha256": active_order,
        "active_public_training_sha256": public_sha,
        "active_hidden_training_sha256": hidden_sha,
    },
    "note": (
        "C34 fixed execution contract: reuse the previously validated single-4090 sequential GRPO path; "
        "use one verifier worker per k=8 completion; eval batch=4 has exact per-problem Pass@1 parity with b1; "
        "batch=8 is rejected because it changes Pass@1. Full worker/concurrent sweeps are intentionally skipped."
    ),
}
encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
if report_path.exists():
    existing = report_path.read_text(encoding="utf-8")
    if existing != encoded:
        raise SystemExit("existing fixed execution contract differs; preserve/archive it before changing the contract")
else:
    report_path.write_text(encoded, encoding="utf-8")

from code_verifier.throughput import check_refresh_benchmark_report
checked = check_refresh_benchmark_report(report_path)
summary = {
    "schema_version": "wp9c-c29-fixed-execution-freeze-v1",
    "status": "completed",
    "report": str(report_path),
    "report_sha256": sha(report_path),
    "selected_eval_generation_batch_size": checked.selected_eval_generation_batch_size,
    "selected_eval_verification_workers": checked.selected_eval_verification_workers,
    "selected_grpo_verification_workers": checked.selected_grpo_verification_workers,
    "paired_grpo_mode": checked.paired_grpo_mode,
    "calibration_manifest_sha256": checked.calibration_manifest_sha256,
    "active_order_sha256": checked.active_order_sha256,
    "active_public_training_sha256": checked.active_public_training_sha256,
    "active_hidden_training_sha256": checked.active_hidden_training_sha256,
}
summary_path.write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, allow_nan=False))
PY_FREEZE

echo "fixed execution contract PASS: $REPORT"
