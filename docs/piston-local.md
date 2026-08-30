# Loopback Piston deployment

Piston is an external sandbox service. It is not a Git submodule or vendored dependency of this repository. The CodeVerifier process sends untrusted source text only to a loopback HTTP endpoint and must never execute model-generated code directly in the training/evaluation process.

**Current project topology:** the only Piston host is `1660ti-wsl`. `home-piston-01` is retired and must not be reintroduced. The pinned service runs on the GTX 1660 Ti WSL host. The 1660 Ti control plane uses its loopback endpoint directly; for Piston-dependent work on the 4090, the 1660 Ti initiates an outbound SSH connection to the current provider public SSH endpoint and creates `-R 127.0.0.1:2000:127.0.0.1:2000`. CodeVerifier on the 4090 therefore still sees only `http://127.0.0.1:2000`. Provider SSH hostname/port/authentication are machine-local operator state and are not committed.

The loopback endpoint may be backed by either:

1. a Piston service running on the same Linux host/VM; or
2. the recommended cloud-GPU topology: a dedicated CPU Linux host/VM running Piston, connected to the GPU container through loopback-only SSH forwarding.

In both cases CodeVerifier still connects only to `http://127.0.0.1:2000`. Do not put a LAN/public Piston address in project configuration.

## Validated baseline

The WP3 single-request and batch acceptance suites were validated with the following environment:

| Component | Validated value |
|---|---|
| Piston source reference | `de2b365ac759670a3a0d13ea208a0869a92c7e64` |
| Piston API image | `ghcr.io/engineer-man/piston@sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a` |
| Piston API package version | `3.1.1` |
| Python runtime | `3.10.0` |
| Docker Engine | `29.6.2` |
| Docker Compose | `5.3.1` |
| Linux cgroup mode | cgroup v2 |

The source reference and container digest are recorded independently because the published image does not contain Git metadata. Do not assume that a source checkout and a published image correspond unless build provenance explicitly proves it. The execution artifact used for acceptance is the exact image digest above.

## Recommended RTX 4090 cloud topology

Many GPU rental platforms expose Ubuntu as an ordinary non-privileged container. Such a GPU container may have no `systemd`, no Docker daemon/socket, and no capability to start a nested privileged container. That is a supported 4090 deployment for this project when Piston is separated from the GPU node.

```text
Dedicated CPU Linux host / VM
  Docker + cgroup v2
  pinned privileged Piston container
  Piston API: 127.0.0.1:2000 only
              |
              | outbound SSH + reverse forward
              v
Ordinary RTX 4090 GPU container
  127.0.0.1:2000  <- SSH reverse tunnel
  open-r1-code-verifier
  PyTorch / CUDA / SFT / GRPO / evaluation
  no Docker daemon required
```

Docker, `--privileged`, and Piston cgroup requirements belong to the dedicated Piston host in this topology. The 4090 container only needs the pinned training environment, GPU access, persistent storage, its existing provider SSH service, and the loopback reverse tunnel.

Do not replace this topology with direct host execution of candidate code merely because the GPU container cannot run Docker.

## Security boundary

The service and tunnel must satisfy all of these requirements:

- Piston publishes port 2000 only on `127.0.0.1` or another loopback address on the Piston host;
- the GPU container reaches Piston only through loopback-only SSH forwarding that binds `127.0.0.1` on the GPU side;
- never expose Piston directly to a LAN or the public internet;
- use a dedicated Piston Linux host/VM because the Piston API container requires elevated privileges;
- do not mount the Docker socket, repository, home directory, credentials, or unrelated host paths into execution jobs;
- keep networking disabled for sandbox jobs;
- use an exact runtime version matching `configs/execution/piston-local.yaml`;
- pin both the Piston source reference and the container image digest used for validation;
- treat any failed or skipped real safety probe as a release/validation blocker.

The public Piston endpoint is not supported by this project. Do not add API tokens or remote endpoint addresses to project configuration.

## Piston host: start the pinned service

Run these steps on the dedicated CPU Piston host (or on a same-host development VM when using the original local topology).

Use a repository-external directory for an optional source checkout:

```bash
git clone https://github.com/engineer-man/piston.git "$PISTON_HOME"
git -C "$PISTON_HOME" checkout de2b365ac759670a3a0d13ea208a0869a92c7e64
```

The validated runtime can be started directly from the pinned image. A named Docker volume persists installed language packages without mounting user directories:

```bash
docker run \
  --privileged \
  --detach \
  --publish 127.0.0.1:2000:2000 \
  --volume piston_wp3b:/piston \
  --name piston_wp3b \
  ghcr.io/engineer-man/piston@sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a
```

Confirm that the published address is loopback-only:

```bash
docker inspect --format '{{json .NetworkSettings.Ports}}' piston_wp3b
```

The output for `2000/tcp` must show `HostIp` as `127.0.0.1`. Stop immediately if Docker publishes the port on `0.0.0.0`, `::`, a LAN address, or a public address.

## Piston host: install the exact Python runtime

The service starts without language runtimes. Install Python `3.10.0` through the host-local package API:

```bash
curl --fail --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"language":"python","version":"3.10.0"}' \
  http://127.0.0.1:2000/api/v2/packages
```

Verify the installed runtime on the Piston host:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:2000/api/v2/runtimes
```

The response must contain exactly the configured Python version before the GPU node is allowed to use this service.

## GTX 1660 Ti control plane: establish the 4090 loopback reverse tunnel

From the 1660 Ti WSL control plane, establish a long-lived outbound SSH session to the current provider public SSH endpoint and bind the 4090 side only on loopback:

```bash
ssh -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R 127.0.0.1:2000:127.0.0.1:2000 \
  -p <CURRENT_PROVIDER_SSH_PORT> \
  root@<CURRENT_PROVIDER_SSH_HOST>
```

The current provider host/port and authentication are machine-local operator state. Do not commit them to the repository. The former 4090-side Tailscale/local-forward helper is not part of the canonical transport after this change.

Keep this SSH session alive for the entire training/evaluation command that needs Piston. If the SSH process exits, CodeVerifier must fail closed on Piston transport errors rather than running candidate code locally. If a formal target-GPU run is already active, do not restart or perturb the tunnel; only perform read-only health checks.

The project YAML remains unchanged:

```yaml
piston:
  base_url: http://127.0.0.1:2000
```

Do not replace `base_url` with the Piston host's real IP/hostname.

Before starting validation, check the tunneled endpoint from the 4090 container:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:2000/api/v2/runtimes
```

Then validate it through the project API:

```bash
.venv/bin/python -c "from pathlib import Path; from code_verifier.execution import PistonExecutor, load_piston_executor_config; executor = PistonExecutor(load_piston_executor_config(Path('configs/execution/piston-local.yaml'))); print(executor.validate_runtime())"
```

The project API must report exactly `3.10.0`.

## Run health checks and acceptance tests

Run the standard project checks first:

```bash
make lint
make test
```

Default `make test` does not contact Piston. The real sandbox suite must be enabled explicitly:

```bash
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
```

The real suite verifies correct, wrong-answer, syntax-error, runtime-error, timeout, memory-limit, and output-limit outcomes. It also probes disabled outbound networking, non-root execution, protected base filesystem writes, host-file invisibility, per-job temporary-state cleanup, PID containment, batch ordering, cache reuse, non-caching of sandbox failures, and service recovery after malicious workloads.

For the SSH-tunneled 4090 topology this exact suite must run from the 4090 container through the tunnel. A failed or skipped real test means the Piston boundary is not accepted. Do not weaken assertions, switch to direct GPU-container execution, or bypass the sandbox/cache contracts until the behavior is understood and corrected.

## Validation provenance for a tunneled deployment

The formal 4090 bootstrap/handoff artifacts must record that the loopback endpoint is backed by a remote Piston host. At minimum keep a `piston-runtime-identity.json` (outside the Git worktree, under the persistent machine/artifact records) with the following non-secret facts:

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

Do not store SSH private keys, passwords, tokens, or other credentials in this record. The formal migration bootstrap should write this record only after the exact runtime probe and full `make test-piston` acceptance pass.

The existing experiment-level Piston config hash still represents the result-affecting executor configuration because CodeVerifier sees the same loopback endpoint and executor semantics. The separate machine record captures where that endpoint terminates operationally.

## Batch concurrency operations

`max_concurrency` controls how many independent Piston executors can submit work at once. Each request can create multiple Piston jobs because every test remains isolated, so increasing the batch worker count increases pressure on Piston, Docker, cgroups, memory, file descriptors, host scheduling, and—when tunneled—SSH/network latency.

Start with `max_concurrency: 1`, run the real acceptance suite and a representative workload, then increase gradually. After each change, check Piston logs, Piston-host resource pressure, tunnel stability, timeout frequency, memory-limit behavior, and service recovery. Never remove the configured upper bound or share one `PistonExecutor`/transport instance across worker threads.

The implementation remains a bounded single-machine thread pool on the CodeVerifier side. A remote Piston host does not turn it into a distributed scheduler and does not imply linear speedup. Prefer a Piston host with low network latency to the GPU rental region.

## Execution cache operations

The optional SQLite cache is independent of Piston and never replaces sandbox execution. It stores only cache-key hashes/metadata and validated execution results; raw candidate code and tests are not stored. Results may contain bounded model stdout/stderr, so the file must remain a sensitive experiment artifact.

Operational rules:

- the cache file is created with mode `0600`; refuse wider permissions rather than silently correcting an existing insecure file;
- keep the cache outside atomic CLI output directories;
- back up or delete the entire SQLite file only while no CodeVerifier process is using it;
- do not commit cache files to Git or copy them into shared locations without equivalent access controls;
- schema mismatch, version mismatch, malformed rows, symlinks, and corruption are hard failures;
- on a hard cache failure, stop the run and repair, archive, or delete the cache; do not reinterpret corruption as a miss or fall back to unbounded/host execution;
- executor, harness, comparator, status-mapping, stop-policy, runtime, or result-affecting config changes must invalidate old entries through the deterministic executor version;
- training workloads keep caching disabled unless the experiment explicitly opts in and records the resolved policy.

## Stop and remove the service

On the Piston host, stop the API container without deleting installed runtimes:

```bash
docker stop piston_wp3b
```

Start it again with:

```bash
docker start piston_wp3b
```

Remove the container and its persisted runtime volume only when the environment is no longer needed:

```bash
docker rm --force piston_wp3b
docker volume rm piston_wp3b
```

On the GTX 1660 Ti control plane, stop the tunnel by terminating the foreground `ssh -N -T ... -R 127.0.0.1:2000:127.0.0.1:2000 ...` process. Stopping the tunnel must not modify the Piston service, its container, or its volume. Never terminate or restart this transport while a formal target-GPU run is active.

## Known MVP limitation

Each test still uses one Piston job, but the trusted verifier and candidate no longer share a Python interpreter. The trusted parent closes the original stdin, disables process dumping, retains the expected value and final marker, and launches a child interpreter that receives only the function name and input. Candidate stdout/stderr are drained and bounded by the parent, and the child result channel is parsed only as an untrusted claimed return value before parent-side comparison.

This closes ordinary `__main__`, JSON serializer, output-stream, and stack-frame verdict tampering. It still relies on the Linux process boundary and Piston sandbox rather than a separately deployed verifier service. Any future change that exposes expected values or the final marker to the child, reuses one interpreter, or accepts a child-supplied outcome must be treated as a security regression.
