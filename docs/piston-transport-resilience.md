# Piston transport resilience policy

## Scope and safety boundary

This document defines the WP7-c transport-reliability layer that is intentionally separate from the scientific Piston verifier definition. The implementation is developed and tested on the GTX 1660 Ti control plane only. It does not deploy or restart the live RTX 4090 tunnel, does not rebind `127.0.0.1:2000`, and does not modify the active C12 operator/report/history.

The canonical scientific endpoint remains:

```text
CodeVerifier -> http://127.0.0.1:2000
4090         -> SSH local forward -> 1660ti-wsl 127.0.0.1:2000
Piston       -> pinned Python 3.10.0
```

`configs/execution/piston-local.yaml` remains the scientific Piston definition. Transport recovery is defined independently by `configs/execution/piston-transport-resilience.yaml`.

## Scientific identity separation

Formal evidence must record two independent identities:

- `piston_definition_sha256`: SHA256 of the exact existing `configs/execution/piston-local.yaml` bytes.
- `piston_transport_policy_sha256`: SHA256 of the normalized transport-resilience policy **plus explicit retry/classifier/supervisor implementation-version identities**.

Changing retry/backoff/supervisor operations or their implementation semantics therefore changes the transport policy identity without pretending that the verifier scientific definition changed or remained equivalent for the wrong reason. Any semantic code change to classification, retry, or supervisor behavior must bump its implementation-version constant. The transport policy is excluded from the C/D paired scientific definition.

The policy binds all of the following operational facts:

- policy schema version;
- the exact safe-retry failure classes;
- maximum candidate-request attempts;
- candidate retry backoff sequence and cap;
- separate bounded recovery-health probe attempt/backoff policy;
- loopback listener, `/api/v2/runtimes`, and exact Python `3.10.0` health identity;
- canonical SSH target/forward;
- SSH connect/keepalive settings;
- reconnect sequence/cap/budget;
- mandatory exclusive locking;
- fail-closed behavior for an unknown port owner.

## Transport failure classification and retry decision

The first implementation retries only failures that prove the candidate POST did not reach Piston.

| Failure | Candidate execution state | Transparent retry |
|---|---|---|
| loopback connection refused / listener unavailable | proven not connected | allowed, bounded |
| explicit pre-connect host/network failure | proven not connected | allowed, bounded |
| connection reset | ambiguous | forbidden |
| read timeout | ambiguous | forbidden |
| HTTP application error | request may have reached service | forbidden |
| non-JSON / invalid JSON response | request reached a responder | forbidden |
| oversized response | request reached a responder | forbidden |
| local invalid request | no remote execution, but caller/config bug | forbidden |
| valid Piston `sandbox_error` | remote execution occurred | forbidden |
| syntax/runtime/wrong-answer/timeout/memory/output verdict | remote execution occurred | forbidden |

DNS retry classification is intentionally absent because project Piston endpoints must remain loopback-only.

For an allowed failure the sequence is bounded:

```text
candidate request
  -> proven pre-connect failure
  -> bounded candidate-retry backoff
  -> bounded endpoint/runtime health polling
  -> PistonExecutor.validate_runtime() == "3.10.0"
  -> resend the exact same request object/serialized semantics
  -> success, or bounded infrastructure failure
```

Candidate submission attempts and recovery-health polling have separate tracked budgets. The current health polling schedule can wait across an SSH `ConnectTimeout=10` recovery window instead of giving up after only the short candidate retry delay. An unsafe health-probe failure fails closed rather than authorizing a resend. There is no infinite retry path.

## GRPO failure ordering

The existing `_TrainingExecutorCircuitBreaker` remains authoritative and is not bypassed:

```text
safe transport recovery
  -> success: normal verifier/reward path
  -> unrecovered or ambiguous failure: SANDBOX_ERROR / infrastructure failure
  -> _TrainingExecutorCircuitBreaker trips
  -> reward callback raises GRPOTrainingError
  -> optimizer update is not reached
```

Candidate verdict and reward mathematics are unchanged. Transport telemetry is never inserted into reward-component records.

## Transport telemetry and resume semantics

For `train-grpo`, transport telemetry is stored outside the strict GRPO run directory at:

```text
<output_root>/transport-telemetry/<run_name>.json
```

The sidecar records only non-sensitive identities and aggregate counters:

- `piston_definition_sha256`;
- `piston_transport_policy_sha256`;
- `telemetry_semantics: cumulative_durable_snapshot_per_mutation_v1`;
- `transport_requests` (candidate `/execute` transport invocations that actually began; runtime probes are excluded);
- `transport_connect_failures`;
- `transport_safe_retries`;
- `transport_retry_successes`;
- `transport_retry_exhausted`;
- `transport_ambiguous_failures`;
- `tunnel_reconnect_count`;
- `tunnel_total_outage_seconds`;
- `tunnel_max_outage_seconds`.

Count fields are exact nonnegative integers; outage durations are finite nonnegative numbers. The sidecar contains no candidate code, completion text, tests, function names, SSH keys, credentials, or response payloads.

A fresh run checks that its GRPO run directory does not already exist, then atomically claims a new sidecar with exclusive creation. It never overwrites an existing same-run sidecar; an orphaned sidecar requires explicit operator review/cleanup. A resume requires both an existing run directory and sidecar, and the sidecar must match the run name plus both Piston identities before counters are restored. Counter mutations use atomic replacement with file and parent-directory fsync. Restored values are cumulative: subsequent mutations continue from the persisted totals rather than resetting them. These are physical transport-attempt totals across the run lineage, including work performed after an older Trainer checkpoint and before a crash; they are deliberately **not rolled back** when Trainer state resumes from that older checkpoint. This telemetry is operational evidence, not a reward component and not part of the C/D scientific pair hash.

## Tunnel supervisor contract

The supervisor code is a non-deployed template during active C12 execution. Its canonical SSH command semantics include:

```text
BatchMode=yes
ExitOnForwardFailure=yes
ConnectTimeout=10
ServerAliveInterval=30
ServerAliveCountMax=3
-L 127.0.0.1:2000:127.0.0.1:2000
1660ti-wsl
```

Operational invariants:

- the supervisor owns an exclusive nonblocking lock for its entire lifetime and keeps it until every SSH child it created has exited;
- SIGTERM/SIGINT are handled by the supervisor; the spawn/handle-binding window temporarily blocks those signals so an SSH child cannot be orphaned before its handle is recorded;
- on supervisor exception/shutdown, an owned SSH child is terminated, then killed after a bounded graceful-stop timeout if necessary;
- it checks the port before every SSH process start, including reconnects;
- if a listener exists and ownership is not proven, it never kills or replaces that process and fails closed;
- reconnect budget/backoff is bounded **per outage**; successful exact health closes the outage and resets that outage's reconnect budget, while cumulative reconnect telemetry never resets;
- health evaluation is structurally performed by `tunnel_is_healthy`: listener presence plus the project runtime HTTP probe validating exact Python `3.10.0`;
- telemetry schemas accept only fixed numeric/boolean fields and cannot carry candidate/test/secret strings.

Required supervisor events are `supervisor_start`, `ssh_process_start`, `ssh_process_exit`, `reconnect`, `outage_begin`, `outage_end` with duration, successful `health_transition`, and `final_failure`. `DurableTunnelEventSink` is the deployment template for append-only, fsynced, secret-free JSONL supervisor telemetry. It validates every event against the fixed schema before persistence; supervisor JSONL remains operational evidence separate from GRPO reward logs.

A future deployment wrapper should be thin and mechanically derive both runtime health and supervisor settings from tracked project definitions. The intended wiring is equivalent to the following **template only; do not execute during an active formal GRPO run**:

```python
from pathlib import Path

from code_verifier.execution import PistonExecutor, load_piston_executor_config, load_piston_transport_policy
from code_verifier.execution.piston_tunnel import DurableTunnelEventSink, TunnelSupervisor, TunnelSupervisorConfig

policy = load_piston_transport_policy(Path("configs/execution/piston-transport-resilience.yaml"))
executor = PistonExecutor(load_piston_executor_config(Path("configs/execution/piston-local.yaml")))
supervisor = TunnelSupervisor(
    TunnelSupervisorConfig.from_definition(policy.tunnel_supervisor),
    lock_path=Path("/absolute/operator-owned/piston-tunnel-supervisor.lock"),
    runtime_validator=executor,
    emit=DurableTunnelEventSink(Path("/absolute/operator-owned/piston-tunnel-events.jsonl")),
)
supervisor.run()
```

The deployment wrapper must not substitute an arbitrary `health_check` callback, must not infer SSH ownership from a listener alone, and must keep the lock/event paths outside Git and outside C/D reward artifacts.

## Phase 2 design: idempotency relay (not implemented by default)

A future relay may make an otherwise ambiguous response-path interruption retryable, but it must provide a stronger exactly-once boundary than the current direct Piston transport.

The proposed request identity is a cryptographically random `request_id` paired with `payload_sha256 = SHA256(exact canonical request body bytes)`. The relay persists a mapping from `request_id` to the exact payload hash and execution state. A first request may execute Piston once. A repeated `request_id` with the same payload hash returns the cached exact response bytes. A repeated `request_id` with a different payload hash is a hard conflict and fails closed.

The cache must be bounded by entry count, byte size, and retention time, stored with restrictive permissions, and updated atomically. Completed entries retain the exact response bytes needed for byte-identical replay. Process restart must preserve completed entries. If the relay crashes while an execution is in flight and cannot prove whether Piston executed it, the recovered entry remains an ambiguous tombstone and must not re-execute the candidate automatically.

The relay must not log candidate/test payloads, must validate all cache records before use, must reject malformed/conflicting records, and must prevent untrusted request identifiers from escaping the bounded cache namespace. Cache poisoning or identity mismatch is an infrastructure failure. Candidate execution is permitted at most once for a successfully committed request identity.

This relay is deliberately deferred: the current phase uses only self-healing tunnel supervision plus provably safe pre-connect retry.

## Deferred real-machine gates

These gates are intentionally deferred until C12 and its review are complete:

- deploy the tracked tunnel supervisor on the 4090;
- kill the SSH process and verify automatic recovery;
- make the listener unavailable and verify recovery;
- run real `make test-piston` with all expected probes passing;
- compare direct 1660 Ti and 4090-tunneled semantic-equivalence corpora;
- soak at least twice the expected formal Piston request count;
- perform multiple tunnel restarts;
- run a short real GRPO smoke with controlled tunnel interruption;
- prove no duplicate canonical reward rows and no erroneous optimizer update;
- prove Trainer+sidecar checkpoint/resume after interruption;
- run the complete lint/test/test-gpu/test-piston acceptance set;
- complete review before generating any new formal GRPO operator checkpoint.
