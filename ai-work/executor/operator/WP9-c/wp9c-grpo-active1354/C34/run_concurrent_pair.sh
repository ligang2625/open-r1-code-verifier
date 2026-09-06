#!/usr/bin/env bash
set -Eeuo pipefail

PHASE="${1:-}"
WORKERS="${2:-}"
BENCHMARK_REPORT="${3:-}"
[[ "$PHASE" == "pilot" || "$PHASE" == "formal" ]] || { echo "usage: run_concurrent_pair.sh <pilot|formal> <workers> <benchmark-report>" >&2; exit 64; }
[[ "$WORKERS" =~ ^[0-9]+$ ]] || { echo "workers must be an integer" >&2; exit 64; }
[[ "$BENCHMARK_REPORT" = /* && -f "$BENCHMARK_REPORT" ]] || { echo "benchmark report must be an existing absolute path" >&2; exit 64; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
RUN_SH="$SCRIPT_DIR/run.sh"
WRAPPER_REL="ai-work/executor/operator/WP9-c/wp9c-grpo-active1354/C34/run_concurrent_pair.sh"
PY="$REPO_ROOT/.venv/bin/python"

EXPECTED_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
EXPECTED_RUN_SHA="${WP9C_SCRIPT_SHA256:-}"
EXPECTED_WRAPPER_SHA="${WP9C_PAIR_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9C_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_RUN_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9C_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$EXPECTED_WRAPPER_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9C_PAIR_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from handoff commit" >&2; exit 125; }
[[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean" >&2; exit 125; }
[[ "$(sha256sum "$RUN_SH" | awk '{print $1}')" == "$EXPECTED_RUN_SHA" ]] || { echo "run.sh SHA256 drift" >&2; exit 125; }
[[ "$(sha256sum "$REPO_ROOT/$WRAPPER_REL" | awk '{print $1}')" == "$EXPECTED_WRAPPER_SHA" ]] || { echo "concurrent pair wrapper SHA256 drift" >&2; exit 125; }

if ! "$PY" - "$BENCHMARK_REPORT" "$WORKERS" <<'PY_BENCH'
import sys
from pathlib import Path
from code_verifier.throughput import check_refresh_benchmark_report
summary = check_refresh_benchmark_report(Path(sys.argv[1]))
if summary.evidence_class != "formal":
    raise SystemExit("benchmark is not formal")
if summary.paired_grpo_mode != "concurrent":
    raise SystemExit("benchmark did not select concurrent Public/Hidden execution")
if summary.selected_grpo_verification_workers != int(sys.argv[2]):
    raise SystemExit("workers differ from benchmark selection")
if summary.calibration_manifest_sha256 != "5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b":
    raise SystemExit("benchmark is not bound to C29")
print("concurrent benchmark decision verified")
PY_BENCH
then
  exit 125
fi

command -v nvidia-smi >/dev/null 2>&1 || { echo "nvidia-smi unavailable" >&2; exit 125; }
GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits | head -n 1)"
IFS=',' read -r GPU_NAME GPU_TOTAL_MIB GPU_FREE_MIB <<<"$GPU_LINE"
GPU_NAME="${GPU_NAME# }"; GPU_TOTAL_MIB="${GPU_TOTAL_MIB// /}"; GPU_FREE_MIB="${GPU_FREE_MIB// /}"
[[ "$GPU_TOTAL_MIB" =~ ^[0-9]+$ && "$GPU_TOTAL_MIB" -ge 22528 ]] || { echo "target GPU total VRAM is below 22528 MiB" >&2; exit 125; }
[[ "$GPU_FREE_MIB" =~ ^[0-9]+$ && "$GPU_FREE_MIB" -ge 20000 ]] || { echo "concurrent pair requires at least 20000 MiB free VRAM before launch" >&2; exit 125; }

printf '[%s] launching concurrent %s pair workers=%s on %s total=%sMiB free=%sMiB\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PHASE" "$WORKERS" "$GPU_NAME" "$GPU_TOTAL_MIB" "$GPU_FREE_MIB"

set +e
WP9C_CONCURRENT_CHILD=1 bash "$RUN_SH" "$PHASE" public "$WORKERS" "$BENCHMARK_REPORT" &
PUBLIC_PID=$!
WP9C_CONCURRENT_CHILD=1 bash "$RUN_SH" "$PHASE" hidden "$WORKERS" "$BENCHMARK_REPORT" &
HIDDEN_PID=$!
wait "$PUBLIC_PID"
PUBLIC_RC=$?
wait "$HIDDEN_PID"
HIDDEN_RC=$?
set -e

if [[ "$PUBLIC_RC" -ne 0 || "$HIDDEN_RC" -ne 0 ]]; then
  printf 'concurrent %s pair failed: public_rc=%s hidden_rc=%s\n' "$PHASE" "$PUBLIC_RC" "$HIDDEN_RC" >&2
  exit 2
fi
printf 'concurrent %s pair PASS\n' "$PHASE"
