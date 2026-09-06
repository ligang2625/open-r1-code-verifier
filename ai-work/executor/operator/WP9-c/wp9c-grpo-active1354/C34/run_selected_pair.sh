#!/usr/bin/env bash
set -Eeuo pipefail
PHASE="${1:-}"
[[ "$PHASE" == "pilot" || "$PHASE" == "formal" ]] || { echo "usage: run_selected_pair.sh <pilot|formal>" >&2; exit 64; }
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/third_party/open-r1/src"

if [[ -n "${CODE_VERIFIER_VALIDATION_MACHINE:-}" ]]; then
  MACHINE_POINTER="$CODE_VERIFIER_VALIDATION_MACHINE"
else
  MACHINE_POINTER="$REPO_ROOT/.ai-bridge/validation-machine.json"
  if [[ ! -f "$MACHINE_POINTER" ]]; then
    COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"
    MACHINE_POINTER="$(dirname "$COMMON_DIR")/.ai-bridge/validation-machine.json"
  fi
fi
ARTIFACT_ROOT="$($PY - "$MACHINE_POINTER" <<'PY_ROOT'
import json,sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["artifact_root"])
PY_ROOT
)"
REPORT="$ARTIFACT_ROOT/wp9c/grpo-c29/benchmark/report/refresh_benchmark_report.json"
[[ -f "$REPORT" ]] || { echo "formal benchmark report missing: $REPORT" >&2; exit 125; }
read -r WORKERS MODE < <("$PY" - "$REPORT" <<'PY_REPORT'
import sys
from pathlib import Path
from code_verifier.throughput import check_refresh_benchmark_report
summary=check_refresh_benchmark_report(Path(sys.argv[1]))
if summary.evidence_class != "formal" or summary.selected_grpo_verification_workers is None:
    raise SystemExit("formal benchmark selection incomplete")
print(summary.selected_grpo_verification_workers, summary.paired_grpo_mode)
PY_REPORT
)
echo "selected GRPO execution: phase=$PHASE workers=$WORKERS paired_mode=$MODE"
if [[ "$MODE" == "sequential" ]]; then
  bash "$SCRIPT_DIR/run.sh" "$PHASE" public "$WORKERS" "$REPORT"
  bash "$SCRIPT_DIR/run.sh" "$PHASE" hidden "$WORKERS" "$REPORT"
elif [[ "$MODE" == "concurrent" ]]; then
  bash "$SCRIPT_DIR/run_concurrent_pair.sh" "$PHASE" "$WORKERS" "$REPORT"
else
  echo "unsupported paired mode: $MODE" >&2
  exit 125
fi
