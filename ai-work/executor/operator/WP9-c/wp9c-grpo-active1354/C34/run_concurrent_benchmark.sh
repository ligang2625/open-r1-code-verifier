#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
RUN_SH="$SCRIPT_DIR/run.sh"
WRAPPER_REL="ai-work/executor/operator/WP9-c/wp9c-grpo-active1354/C34/run_concurrent_benchmark.sh"

EXPECTED_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
EXPECTED_RUN_SHA="${WP9C_SCRIPT_SHA256:-}"
EXPECTED_WRAPPER_SHA="${WP9C_CONCURRENT_SCRIPT_SHA256:-}"
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "WP9C_HANDOFF_COMMIT must be exact 40-hex commit" >&2; exit 125; }
[[ "$EXPECTED_RUN_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9C_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$EXPECTED_WRAPPER_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "WP9C_CONCURRENT_SCRIPT_SHA256 must be exact lowercase SHA256" >&2; exit 125; }
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { echo "target HEAD differs from handoff commit" >&2; exit 125; }
[[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal)" ]] || { echo "target checkout must be clean" >&2; exit 125; }
[[ "$(sha256sum "$RUN_SH" | awk '{print $1}')" == "$EXPECTED_RUN_SHA" ]] || { echo "run.sh SHA256 drift" >&2; exit 125; }
[[ "$(sha256sum "$REPO_ROOT/$WRAPPER_REL" | awk '{print $1}')" == "$EXPECTED_WRAPPER_SHA" ]] || { echo "concurrent wrapper SHA256 drift" >&2; exit 125; }

command -v nvidia-smi >/dev/null 2>&1 || { echo "nvidia-smi unavailable" >&2; exit 125; }
GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits | head -n 1)"
IFS=',' read -r GPU_NAME GPU_TOTAL_MIB GPU_FREE_MIB <<<"$GPU_LINE"
GPU_NAME="${GPU_NAME# }"; GPU_TOTAL_MIB="${GPU_TOTAL_MIB// /}"; GPU_FREE_MIB="${GPU_FREE_MIB// /}"
[[ "$GPU_TOTAL_MIB" =~ ^[0-9]+$ && "$GPU_TOTAL_MIB" -ge 22528 ]] || { echo "target GPU total VRAM is below 22528 MiB" >&2; exit 125; }
[[ "$GPU_FREE_MIB" =~ ^[0-9]+$ && "$GPU_FREE_MIB" -ge 20000 ]] || { echo "concurrent trial requires at least 20000 MiB free VRAM before launching either arm" >&2; exit 125; }

printf '[%s] launching frozen same-GPU concurrent benchmark trial on %s total=%sMiB free=%sMiB\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$GPU_NAME" "$GPU_TOTAL_MIB" "$GPU_FREE_MIB"

set +e
WP9C_CONCURRENT_CHILD=1 bash "$RUN_SH" benchmark-k8 public 8 concurrent &
PUBLIC_PID=$!
WP9C_CONCURRENT_CHILD=1 bash "$RUN_SH" benchmark-k8 hidden 8 concurrent &
HIDDEN_PID=$!
wait "$PUBLIC_PID"
PUBLIC_RC=$?
wait "$HIDDEN_PID"
HIDDEN_RC=$?
set -e

if [[ "$PUBLIC_RC" -ne 0 || "$HIDDEN_RC" -ne 0 ]]; then
  printf 'concurrent benchmark failed: public_rc=%s hidden_rc=%s\n' "$PUBLIC_RC" "$HIDDEN_RC" >&2
  exit 2
fi

printf 'concurrent benchmark PASS: public_rc=0 hidden_rc=0\n'
