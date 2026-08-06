# Local Piston deployment

Piston is an external local service. It is not a Git submodule or vendored dependency of this repository. The CodeVerifier process sends untrusted source text to Piston over a loopback-only HTTP boundary and must never execute model-generated code directly on the host.

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

The source reference and container digest are recorded independently because the published image does not contain Git metadata. Do not assume that a source checkout and a published image correspond unless the build provenance explicitly proves it. The execution artifact used for acceptance is the exact image digest above.

## Security boundary

The service must satisfy all of these requirements:

- publish port 2000 only on `127.0.0.1` or another loopback address;
- never expose Piston to a LAN or the public internet;
- use a dedicated development machine or VM because the Piston API container requires elevated privileges;
- do not mount the Docker socket, repository, home directory, credentials, or unrelated host paths into execution jobs;
- keep networking disabled for sandbox jobs;
- use an exact runtime version matching `configs/execution/piston-local.yaml`;
- pin both the Piston source reference and the container image digest used for validation;
- treat any failed safety probe as a release blocker.

The public Piston endpoint is not supported by this project. Do not add API tokens or remote endpoints to project configuration.

## Start a pinned loopback-only service

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

## Install the exact Python runtime

The service starts without language runtimes. Install Python `3.10.0` through the local package API:

```bash
curl --fail --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"language":"python","version":"3.10.0"}' \
  http://127.0.0.1:2000/api/v2/packages
```

Verify the installed runtime:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:2000/api/v2/runtimes
```

The response must contain exactly the configured Python version before running CodeVerifier acceptance tests.

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

A failed or skipped real test means WP3 is not accepted. Do not weaken assertions, switch to host execution, or bypass the sandbox/cache contracts until the behavior is understood and corrected.

## Batch concurrency operations

`max_concurrency` controls how many independent Piston executors can submit work at once. Each request can create multiple Piston jobs because every test remains isolated, so increasing the batch worker count increases pressure on Piston, Docker, cgroups, memory, file descriptors, and host scheduling.

Start with `max_concurrency: 1`, run the real acceptance suite and a representative workload, then increase gradually. After each change, check Piston logs, host resource pressure, timeout frequency, memory-limit behavior, and service recovery. Never remove the configured upper bound or share one `PistonExecutor`/transport instance across worker threads.

The local implementation is a bounded single-machine thread pool. It is not a distributed scheduler and does not imply linear speedup.

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

Stop the API container without deleting installed runtimes:

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

## Known MVP limitation

Each test still uses one Piston job, but the trusted verifier and candidate no longer share a Python interpreter. The trusted parent closes the original stdin, disables process dumping, retains the expected value and final marker, and launches a child interpreter that receives only the function name and input. Candidate stdout/stderr are drained and bounded by the parent, and the child result channel is parsed only as an untrusted claimed return value before parent-side comparison.

This closes ordinary `__main__`, JSON serializer, output-stream, and stack-frame verdict tampering. It still relies on the Linux process boundary and Piston sandbox rather than a separately deployed verifier service. Any future change that exposes expected values or the final marker to the child, reuses one interpreter, or accepts a child-supplied outcome must be treated as a security regression.
