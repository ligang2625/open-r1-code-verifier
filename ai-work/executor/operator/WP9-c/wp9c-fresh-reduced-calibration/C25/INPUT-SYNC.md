# WP9-c C25 — RTX 4090 input sync checklist

This checklist transfers only the frozen C25 fresh-calibration input bundle. It does not transfer historical calibration completions or reward outcomes.

## Frozen source

Control-plane source directory:

`/home/dzy/wp9c-fresh-calibration-input-C25`

Tracked transfer manifest:

`ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/input-sync-manifest.json`

Expected total bytes across the six files: `2574292`.

The target directory is resolved from the target-local validation-machine authority:

`$CODE_VERIFIER_DATA_ROOT/wp9c/fresh-calibration-input-C25`

All six files must be copied. The two zero-byte exclusion files are intentional and mandatory.

## Control-plane pre-copy check

Run from the WP9-c worktree:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
.venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path

repo = Path.cwd()
manifest_path = repo / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/input-sync-manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
source = Path(manifest["source_root_control_plane"])
seen_bytes = 0
for item in manifest["files"]:
    path = source / item["path"]
    if not path.is_file():
        raise SystemExit(f"missing C25 input file: {path}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != item["size_bytes"] or digest != item["sha256"]:
        raise SystemExit(f"C25 input mismatch: {item['path']}")
    seen_bytes += len(data)
if seen_bytes != manifest["expected_total_bytes"]:
    raise SystemExit("C25 input total-byte mismatch")
sidecar = (source / "report.sha256").read_text(encoding="utf-8").strip()
if sidecar != manifest["report_sidecar_value"]:
    raise SystemExit("C25 report sidecar mismatch")
print("C25_SOURCE_SYNC_MANIFEST_OK", seen_bytes)
PY
```

## Transfer

Use the provider's current SSH endpoint or other byte-preserving transfer mechanism. The provider hostname/port/authentication are machine-local and must not be committed.

A canonical `rsync` pattern from the control plane is:

```bash
GPU4090_SSH=<your-current-4090-ssh-destination>
TARGET_FORMAL_DATA_ROOT=<formal_data_root-from-target-validation-machine.json>
ssh "$GPU4090_SSH" "mkdir -p '$TARGET_FORMAL_DATA_ROOT/wp9c/fresh-calibration-input-C25'"
rsync -a --delete /home/dzy/wp9c-fresh-calibration-input-C25/ \
  "$GPU4090_SSH:$TARGET_FORMAL_DATA_ROOT/wp9c/fresh-calibration-input-C25/"
```

Do not use `/data`. Do not regenerate any input file on the target.

## Target verification

After the handoff commit is checked out on the RTX 4090, run from that checkout:

```bash
.venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path

repo = Path.cwd()
machine_candidates = [
    repo / ".ai-bridge/validation-machine.json",
]
common = Path((repo / ".git").resolve()) if (repo / ".git").exists() else None
if not machine_candidates[0].is_file():
    import subprocess
    git_common = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True,
    ).strip())
    machine_candidates.append(git_common.parent / ".ai-bridge/validation-machine.json")
machine_path = next((path for path in machine_candidates if path.is_file()), None)
if machine_path is None:
    raise SystemExit("validation-machine.json not found")
machine = json.loads(machine_path.read_text(encoding="utf-8"))
formal_root = Path(machine["formal_data_root"]).resolve()
target = formal_root / "wp9c/fresh-calibration-input-C25"
manifest = json.loads((repo / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/input-sync-manifest.json").read_text(encoding="utf-8"))
seen_bytes = 0
for item in manifest["files"]:
    path = target / item["path"]
    if not path.is_file():
        raise SystemExit(f"missing target C25 input file: {path}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != item["size_bytes"] or digest != item["sha256"]:
        raise SystemExit(f"target C25 input mismatch: {item['path']}")
    seen_bytes += len(data)
if seen_bytes != manifest["expected_total_bytes"]:
    raise SystemExit("target C25 input total-byte mismatch")
print("C25_TARGET_SYNC_MANIFEST_OK", target, seen_bytes)
PY
```

Only after this target verification succeeds should `C25/run.sh` be started.
