# Piston transport resilience policy

## Scope and safety boundary

This document defines the WP7-c transport-reliability layer that is intentionally separate from the scientific Piston verifier definition. The implementation is developed and tested on the GTX 1660 Ti control plane and accepted against the 4090 only through the already-established loopback transport. It never restarts or perturbs an SSH transport while a formal target-GPU run is active and does not rewrite historical operator scripts/evidence.

The canonical scientific endpoint remains loopback-only while the transport direction is now:

```text
1660ti-wsl Piston 127.0.0.1:2000
        -> outbound provider SSH connection
        -> -R 127.0.0.1:2000:127.0.0.1:2000
        -> 4090 CodeVerifier http://127.0.0.1:2000
Piston runtime -> pinned Python 3.10.0
```

`configs/execution/piston-local.yaml` remains the scientific Piston definition. Transport recovery is defined independently by `configs/execution/piston-transport-resilience.yaml`.

## Scientific identity separation

Formal evidence must record two independent identities:

- `piston_definition_sha256`: SHA256 of the exact existing `configs/execution/piston-local.yaml` bytes.
- `piston_transport_policy_sha256`: SHA256 of the normalized transport-resilience policy **plus explicit retry/classifier/connection/supervisor implementation-version identities**.

Changing retry/backoff, failure classification, persistent-connection behavior, or supervisor operations therefore changes the transport policy identity without pretending that the verifier scientific definition changed. Any semantic code change to classification, retry, keep-alive connection handling, or supervisor behavior must bump its implementation-version constant. The transport policy is excluded from the C/D paired scientific definition.

The policy binds all current retry/health semantics plus the legacy supervisor fields required to keep historical evidence interpretable:

- policy schema version;
- the exact safe-retry failure classes;
- maximum candidate-request attempts;
- candidate retry backoff sequence and cap;
- separate bounded recovery-health probe attempt/backoff policy;
- loopback listener, `/api/v2/runtimes`, and exact Python `3.10.0` health identity;
- persistent HTTP connection/classifier implementation identities;
- the legacy local-forward supervisor target/forward, SSH keepalive, reconnect, locking, and unknown-owner fields retained only for provenance compatibility.

The legacy supervisor fields do not authorize new operators to start the retired 4090-side local forward; the current reverse SSH endpoint ownership remains machine-local operator state.

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

Candidate submission attempts and recovery-health polling have separate tracked budgets. The current health polling schedule can wait across a bounded transport-recovery window instead of giving up after only the short candidate retry delay. An unsafe health-probe failure fails closed rather than authorizing a resend. There is no infinite retry path.

## Phase 2 persistent HTTP keep-alive contract

The default Piston transport now uses one lazy `http.client.HTTPConnection` per `PistonExecutor` transport instance. HTTP/1.1 requests are sequential and protected by one lock; there is no connection pool and no bounded-concurrency change. A healthy connection is reused across `/api/v2/runtimes` and `/api/v2/execute`, eliminating repeated TCP/SSH setup while preserving one isolated Piston job per test.

The connection lifecycle is deliberately fail closed:

- a new connection is explicitly established before request bytes are sent, so only the existing proven pre-connect failure kinds retain safe-retry eligibility;
- once a connection exists, reset, broken pipe, read timeout, EOF/incomplete response, or another HTTP stream failure discards that connection and fails the current request without replay;
- an ambiguous candidate `POST /api/v2/execute` is never automatically resent by the persistent transport;
- the next independent request may lazily create a new connection after the failed connection was discarded;
- non-2xx responses remain sanitized `HTTP_ERROR` failures and are not replayed;
- bounded response, content-type, UTF-8, and JSON validation remain unchanged;
- `response.will_close` and `Connection: close` are honored: the successful response is returned, the connection is discarded, and only the next independent request reconnects;
- before reusing an idle real socket, the client performs a zero-time readiness/error check; readable EOF, exceptional state, or unexpected pending peer bytes cause the old connection to be discarded **before** new request bytes are sent, so a server-side keep-alive timeout reconnects safely without replaying a candidate POST;
- per-request socket timeouts are refreshed when a persistent connection is reused.

The transport implementation identity includes `httpclient-single-keepalive-v2`; changing these reuse/discard semantics requires an identity bump. Successful verifier/reward mathematics, test selection, one-job-per-test isolation, timeout/memory/output limits, and Python `3.10.0` runtime identity are unchanged.

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

## Legacy local-forward supervisor provenance

`piston_tunnel.py` and the `tunnel_supervisor` block remain in the transport-policy schema only to preserve the already-reviewed Phase 1 resilience provenance and historical operator evidence. They describe the former 4090-initiated `-L ... 1660ti-wsl` transport and are **not** the canonical transport after the 2026-08-27 reverse-SSH amendment.

New WP7-c operator/runtime code must not start that legacy supervisor or `ensure-piston-1660ti-tunnel.sh` while the control-plane-initiated reverse forward is in use. Current target-side recovery is intentionally limited to fail-closed loopback health/runtime validation plus the safe pre-connect retry policy; ownership/restart of the reverse SSH session remains operator/control-plane infrastructure state. Historical supervisor tests and implementation identities remain readable and hash-bound so old evidence is not silently reinterpreted.

## Deferred exactly-once relay design

A future relay may make an otherwise ambiguous response-path interruption retryable, but it must provide a stronger exactly-once boundary than the current direct Piston transport.

The proposed request identity is a cryptographically random `request_id` paired with `payload_sha256 = SHA256(exact canonical request body bytes)`. The relay persists a mapping from `request_id` to the exact payload hash and execution state. A first request may execute Piston once. A repeated `request_id` with the same payload hash returns the cached exact response bytes. A repeated `request_id` with a different payload hash is a hard conflict and fails closed.

The cache must be bounded by entry count, byte size, and retention time, stored with restrictive permissions, and updated atomically. Completed entries retain the exact response bytes needed for byte-identical replay. Process restart must preserve completed entries. If the relay crashes while an execution is in flight and cannot prove whether Piston executed it, the recovered entry remains an ambiguous tombstone and must not re-execute the candidate automatically.

The relay must not log candidate/test payloads, must validate all cache records before use, must reject malformed/conflicting records, and must prevent untrusted request identifiers from escaping the bounded cache namespace. Cache poisoning or identity mismatch is an infrastructure failure. Candidate execution is permitted at most once for a successfully committed request identity.

This relay is deliberately deferred: the current phase uses only the single persistent HTTP connection, provably safe pre-connect retry, and fail-closed reconnect on the next independent request.

## Real-machine acceptance

The transport change is accepted only when all applicable gates are green without fault-injecting an active formal target-GPU run:

- real `make test-piston` with 0 failed / 0 skipped;
- exact `PistonExecutor.validate_runtime() == "3.10.0"`;
- representative fresh versus persistent latency benchmark through the canonical reverse SSH tunnel;
- complete lint and CPU test suite;
- no change to reward math, GRPO batch/test selection, one-job-per-test isolation, runtime pin, or resource/output limits.

Destructive tunnel restart/fault-injection experiments remain deferred unless no formal target-GPU run is active and an operator explicitly chooses to perform them. The legacy local-forward supervisor is not a required acceptance gate for the reverse-SSH transport.
