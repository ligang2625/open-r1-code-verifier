#!/usr/bin/env bash
set -Eeuo pipefail

echo "This control-plane-path runner is superseded. Use C25/run.sh from the portable-target handoff." >&2
exit 125

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
PY="$ROOT/.venv/bin/python"
CHECKPOINT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/checkpoint.json"
SCRIPT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/01-run-fresh-generation.sh"
RUNNER="$ROOT/ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/run_fresh_generation.py"
OUTPUT="/home/dzy/wp9c-fresh-calibration-generation-C25"
LOG="/home/dzy/wp9c-fresh-calibration-generation-C25.log"
LOCK="/home/dzy/wp9c-fresh-calibration-generation-C25.lock"

cd "$ROOT"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "C25 generation lock is already held: $LOCK" >&2
  exit 125
fi

"$PY" - "$CHECKPOINT" "$SCRIPT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

checkpoint = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if checkpoint.get("status") != "awaiting_operator":
    raise SystemExit("C25 checkpoint is not awaiting_operator")
expected = checkpoint.get("bindings", {}).get("shell_runner_sha256")
actual = hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
if expected != actual:
    raise SystemExit("C25 shell runner digest mismatch")
PY

GPU_INDEX="$($PY - <<'PY'
import subprocess

proc = subprocess.run(
    [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ],
    check=True,
    capture_output=True,
    text=True,
)
choices = []
for line in proc.stdout.splitlines():
    parts = [item.strip() for item in line.split(",")]
    if len(parts) != 4:
        continue
    index, name, total_text, free_text = parts
    try:
        total = int(total_text)
        free = int(free_text)
    except ValueError:
        continue
    if "RTX 4090" in name and total >= 22528 and free >= 20000:
        choices.append((index, free, name))
if not choices:
    raise SystemExit("no RTX 4090 with >=22528 MiB total and >=20000 MiB free")
choices.sort(key=lambda item: (-item[1], item[0]))
print(choices[0][0])
PY
)"
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"

printf '[%s] C25 fresh generation start gpu=%s output=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$GPU_INDEX" "$OUTPUT" | tee -a "$LOG"
"$PY" "$RUNNER" --output "$OUTPUT" --problem-batch-size 4 2>&1 | tee -a "$LOG"
printf '[%s] C25 fresh generation command completed\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
