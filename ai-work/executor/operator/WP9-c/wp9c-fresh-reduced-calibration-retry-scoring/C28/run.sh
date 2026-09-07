#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "repo .venv Python is unavailable" >&2; exit 125; }

exec "$PY" "$SCRIPT_DIR/run_retry_scoring.py" "$@"
