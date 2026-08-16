# RTX 4090 remote-Piston handoff amendment

> Status: authoritative migration-infrastructure amendment after the WP8 Development Complete Record.
>
> This document changes only the 1660 Ti → 4090 deployment topology. It does not reopen WP3–WP8 product development and does not change formal dataset/model/training/evaluation identities.

## 1. Why the original migration package is stale

The original 4090 handoff package assumed that the RTX 4090 node was a full Linux host with a usable Docker daemon and could start the pinned Piston image locally with `--privileged`.

The actual GPU rental environment is an ordinary non-privileged Ubuntu 22.04 Docker container (`PID 1 = docker-init`) with no host Docker socket and no usable nested privileged Docker. Therefore the original `bootstrap-4090.sh` Docker/Piston steps cannot be used as-is.

After this amendment is committed, any existing migration control package that still pins the pre-amendment project commit, old bootstrap SHA, or GPU-local Docker topology is no longer authoritative. Do not run the old full bootstrap and do not accept its old readiness definition as proof for validation.

## 2. New authoritative topology

```text
Dedicated CPU Linux host / VM
  Docker daemon
  cgroup v2
  pinned Piston image
  --privileged Piston API container
  named piston_wp3b volume
  Python runtime 3.10.0
  API bound only to 127.0.0.1:2000
              |
              | SSH local forward
              v
Ordinary RTX 4090 GPU container
  no systemd requirement
  no Docker daemon requirement
  no Docker socket requirement
  no privileged-container requirement
  127.0.0.1:2000 -> SSH tunnel -> Piston host loopback
  open-r1-code-verifier + PyTorch/CUDA + SFT/GRPO/evaluation
```

The project configuration remains `configs/execution/piston-local.yaml` with `base_url: http://127.0.0.1:2000`. Direct LAN/public Piston endpoints remain forbidden.

## 3. Piston host responsibilities

The CPU Piston host owns all infrastructure that previously lived in the 4090 bootstrap:

- Docker daemon and cgroup v2;
- exact Piston image `ghcr.io/engineer-man/piston@sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a`;
- exact Piston source provenance `de2b365ac759670a3a0d13ea208a0869a92c7e64`;
- `piston_wp3b` named volume/container;
- `--privileged` Piston API container;
- host publish restricted to `127.0.0.1:2000:2000`;
- exact Piston Python runtime `3.10.0`;
- Docker/Piston logs and lifecycle operations.

The Piston host does not need an NVIDIA GPU.

## 4. RTX 4090 container responsibilities

The GPU container owns:

- RTX 4090 / >=22 GiB GPU validation;
- Python 3.10 + `uv` + pinned training environment;
- exact project and Open-R1 commits;
- formal data/model restore;
- persistent `DATA_ROOT`, `CODE_VERIFIER_ARTIFACT_ROOT`, and `HF_HOME`;
- a bootstrap-generated, gitignored primary-checkout machine pointer `.ai-bridge/validation-machine.json` so Web/Local workflow does not depend on shell exports surviving across sessions;
- SSH client connectivity to the Piston host;
- SSH local forward to `127.0.0.1:2000`;
- project runtime probe against tunneled Piston;
- `make lint`, `make test`, `make test-gpu`, and real `make test-piston` through the tunnel;
- SFT/GRPO/evaluation and final validation artifacts.

The GPU container must not attempt to install/start `dockerd`, use `systemctl` for Docker, or execute candidate code directly on the GPU-container Python host.

## 5. SSH tunnel gate

From the 4090 container:

```bash
ssh -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:2000:127.0.0.1:2000 \
  <PISTON_SSH_TARGET>
```

Use `-p <PORT>` when the Piston host SSH service is not on port 22.

Before validation bootstrap can pass, a separate shell on the 4090 container must verify:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:2000/api/v2/runtimes
```

and:

```bash
.venv/bin/python -c "from pathlib import Path; from code_verifier.execution import PistonExecutor, load_piston_executor_config; executor = PistonExecutor(load_piston_executor_config(Path('configs/execution/piston-local.yaml'))); print(executor.validate_runtime())"
```

The exact project runtime result must be `3.10.0`.

## 6. Required changes to `bootstrap-4090.sh`

The next authoritative bootstrap must remove these GPU-node gates/actions:

- local Docker daemon availability;
- GPU-node Docker socket access;
- GPU-node Docker/cgroup topology as a Piston prerequisite;
- `docker load` of the Piston archive on the 4090 node;
- creation/removal of the `piston_wp3b` Docker volume/container on the 4090 node;
- `docker run --privileged` on the 4090 node;
- Piston Python package installation from the 4090 node;
- Docker inspect checks that assume Piston is locally hosted on the GPU node.

Replace them with fail-closed gates:

1. `ssh` client exists on the 4090 node;
2. `http://127.0.0.1:2000` is reachable after the operator-established tunnel;
3. project `PistonExecutor.validate_runtime()` returns exact Python `3.10.0`;
4. full real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` runs from the 4090 container through the tunnel with 0 failed / 0 skipped;
5. a machine-level Piston deployment identity record is written only after those gates pass;
6. after all GPU/data/model/test gates pass, an ignored `<REPO_DIR>/.ai-bridge/validation-machine.json` is written atomically and points to the persistent machine records/roots used by lifecycle/router.

The bootstrap must continue to perform the existing project/data/model/GPU/dependency/lint/test/test-gpu/check-data/readiness gates that are unrelated to local Docker.

## 7. Required machine provenance

Under the persistent machine artifact directory, add:

```text
piston-runtime-identity.json
```

Minimum non-secret content:

```json
{
  "deployment_mode": "ssh_tunneled_remote",
  "endpoint": "http://127.0.0.1:2000",
  "piston_source_ref": "de2b365ac759670a3a0d13ea208a0869a92c7e64",
  "piston_image_digest": "sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a",
  "python_runtime": "3.10.0",
  "piston_host_id": "<operator-defined-stable-non-secret-id>",
  "real_piston_acceptance": "PASS"
}
```

Never record SSH private keys, passwords, tokens, or other credentials.

`bootstrap-4090-readiness.json = READY_FOR_VALIDATION_PLANNER` is valid only if this Piston identity record exists and the tunneled real-Piston acceptance passed.

The bootstrap must also write the following **ignored local machine pointer** under the restored primary repository:

```text
.ai-bridge/validation-machine.json
```

Minimum non-secret fields are `version: 1`, `machine_status: READY_FOR_VALIDATION_PLANNER`, `bootstrap_project_commit`, `open_r1_commit`, absolute `artifact_root`, `hf_home`, `formal_data_root`, `readiness_record`, `piston_identity_record`, `piston_endpoint`, and `piston_host_id`. The bootstrap must first confirm `.ai-bridge/validation-machine.json` is ignored/untracked. This file is deliberately not committed: it carries machine-local absolute paths so `stage-lifecycle`/`execution-router` can recover them even when a new shell or an already-running Web/CodexPro connector does not inherit operator `export` commands.

## 8. Required migration-package regeneration

Before the next transfer/bootstrap, regenerate or update the external `~/migration` package so that its authoritative control files match the new committed project state and topology.

At minimum revisit:

- `MIGRATION-MANIFEST.json` and its SHA256;
- expected exact project/handoff commit;
- `verify-migration.py` if the transport inventory or Piston archive destination changes;
- `bootstrap-4090.sh` and its SHA256;
- `bootstrap-4090.env.example` and its SHA256;
- `README-MIGRATION.md` and its SHA256;
- `README-BOOTSTRAP-4090.md` and its SHA256;
- `BOOTSTRAP-4090-REVIEW.md` and its SHA256;
- the human handoff runbook.

Two valid transport layouts are possible:

### Layout A — smallest change to the old verifier

Keep the Piston image archive in the 4090 migration payload only so the existing top-level migration verifier can still validate the complete package, but do not load it on the GPU node. Separately copy the same verified Piston archive to the CPU Piston host for `docker load`.

### Layout B — cleaner long-term split

Split the transport inventories into GPU payload and Piston-host payload, and update `MIGRATION-MANIFEST.json`/`verify-migration.py` accordingly. The GPU payload no longer carries an unused Piston image archive; the Piston-host payload owns the image/manifest checks.

Prefer Layout A for the immediate migration because it changes fewer control-plane components. A later cleanup may adopt Layout B if there is a concrete need.

## 9. Revised 4090 preflight

The 4090 preflight should require:

```text
Linux x86_64
RTX 4090
VRAM >= 22528 MiB
persistent disk >= required capacity
Git remote/exact commit recoverable
uv
Python 3.10.x >= 3.10.9
SSH client
Piston loopback tunnel reachable
Piston runtime = 3.10.0
formal data/model archive SHA256 PASS
```

It must not require on the GPU node:

```text
systemd
Docker daemon
Docker socket
nested privileged Docker
local Piston container
GPU-node cgroup-v2 as a nested-Docker prerequisite
```

The Piston host has its own Docker/cgroup preflight.

## 10. Revised READY definition

`READY_FOR_VALIDATION_PLANNER` now requires all existing non-Docker 4090 gates plus:

```text
Piston deployment mode = ssh_tunneled_remote
Piston exact source/image identity recorded
Piston Python runtime = 3.10.0
Piston endpoint visible to project only as 127.0.0.1:2000
real make test-piston through tunnel = PASS, 0 skipped
piston-runtime-identity.json exists
```

The formal SFT/GRPO/evaluation definitions, dataset identity, Qwen model identity, Open-R1 submodule identity, artifact-root rules, and validation lifecycle remain unchanged.
