#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
CONFIG="$ROOT/configs/data/wp9c-fixed-2505-candidate-freeze.yaml"
AUDIT="$ROOT/ai-work/executor/operator/WP9-c/wp9c-fixed-2505-candidate-freeze/C12/audit_fixed_2505.py"
OUTPUT="/home/dzy/wp9c-fixed-2505-candidate-freeze-C12-r1"

cd "$ROOT"
exec .venv/bin/python "$AUDIT" --config "$CONFIG" --output-dir "$OUTPUT"
