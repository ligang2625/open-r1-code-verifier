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
readarray -t ROOTS < <("$PY" - "$MACHINE_POINTER" <<'PY_MACHINE'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("machine_status") != "READY_FOR_VALIDATION_PLANNER": raise SystemExit("validation machine not ready")
for key in ("artifact_root", "formal_data_root"):
    path=Path(value.get(key, ""))
    if not path.is_absolute(): raise SystemExit(f"invalid {key}")
    print(path)
PY_MACHINE
)
ARTIFACT_ROOT="${ROOTS[0]}"; FORMAL_DATA_ROOT="${ROOTS[1]}"
BASE="$ARTIFACT_ROOT/wp9c/grpo-c29"
EVAL="$BASE/eval200-generation"
VERIFY="$FORMAL_DATA_ROOT/wp9c/eval200-verification-C34"
GRPO="$BASE/benchmark-sources"
OUT="$BASE/benchmark"
RUN="wp9c-c29-b-eval200-b1-seed42"

"$PY" "$SCRIPT_DIR/build_formal_benchmark.py" \
  --eval-b1 "$EVAL/b1/generation/wp9c-c29-b-eval200-b1-seed42" \
  --eval-b2 "$EVAL/b2/generation/wp9c-c29-b-eval200-b2-seed42" \
  --eval-b4 "$EVAL/b4/generation/wp9c-c29-b-eval200-b4-seed42" \
  --eval-b8 "$EVAL/b8/generation/wp9c-c29-b-eval200-b8-seed42" \
  --eval-b16 "$EVAL/b16/generation/wp9c-c29-b-eval200-b16-seed42" \
  --eval-v1 "$VERIFY/v1/evaluation/$RUN" \
  --eval-v8 "$VERIFY/v8/evaluation/$RUN" \
  --eval-v16 "$VERIFY/v16/evaluation/$RUN" \
  --eval-v32 "$VERIFY/v32/evaluation/$RUN" \
  --eval-v64 "$VERIFY/v64/evaluation/$RUN" \
  --grpo-k8-w8 "$GRPO/k8-public-w8-baseline/wp9c-c29-public-benchmark20-seed42" \
  --grpo-k8-w16 "$GRPO/k8-public-w16-worker16/wp9c-c29-public-benchmark20-seed42" \
  --grpo-k8-w32 "$GRPO/k8-public-w32-worker32/wp9c-c29-public-benchmark20-seed42" \
  --grpo-k8-w64 "$GRPO/k8-public-w64-worker64/wp9c-c29-public-benchmark20-seed42" \
  --grpo-k4-w8 "$GRPO/k4-public-w8-diagnostic/wp9c-c29-public-k4-diagnostic20-seed42" \
  --grpo-hidden-sequential "$GRPO/k8-hidden-w8-sequential/wp9c-c29-hidden-benchmark20-seed42" \
  --grpo-public-concurrent "$GRPO/k8-public-w8-concurrent/wp9c-c29-public-benchmark20-seed42" \
  --grpo-hidden-concurrent "$GRPO/k8-hidden-w8-concurrent/wp9c-c29-hidden-benchmark20-seed42" \
  --output-root "$OUT"

echo "formal benchmark PASS: $OUT/report/refresh_benchmark_report.json"
