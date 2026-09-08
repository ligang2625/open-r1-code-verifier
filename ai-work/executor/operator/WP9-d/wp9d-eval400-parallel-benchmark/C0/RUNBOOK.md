# WP9-d eval400 parallel-generation benchmark C0

Purpose: benchmark `b4/p2` and `b4/p4` against the already-running/formal P2 `b4/p1` B-refresh generation without rerunning `b4/p1` and without changing the frozen GRPO recipe.

## Safety / ordering

- Do **not** run this handoff while the current P2 `b4/p1` generation is still running.
- The operator preflight requires the canonical `b4/p1` bundle to be completed with 400/400 records before it allows either benchmark arm. This prevents accidental overlap with the current generation.
- The benchmark starts only `b4/p2` and `b4/p4`, sequentially as separate operator phases.
- It never contacts Piston, never verifies/aggregates, and never starts GRPO training.
- Benchmark outputs are isolated under `$ARTIFACT_ROOT/wp9d/eval400-parallel-benchmark`; the formal P2 `b4/p1` bundle under `$ARTIFACT_ROOT/wp9d/b-refresh-eval400` is read-only baseline evidence.
- `b4/p4` is experimental. An OOM or nonzero exit is a benchmark result to diagnose; do not lower batch size, alter seed, or overwrite its artifacts silently.

## Exact evaluation identity

All three compared runs use the same:

- parent: `B-sft-formal-seed42`
- model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`
- revision: `2e1fd397ee46e1388853d2af2c993145b0f1098a`
- canonical eval400 dataset/order
- deterministic Pass@1 config
- `batch_size=4`
- `seed=42`

The only benchmark variable is `parallel_generators`: baseline `p1`, new arms `p2` and `p4`. For `p2/p4`, the existing `generate-eval` implementation enables dedicated CUDA streams for each independent generator instance.

## Target execution sequence

After the current formal P2 `b4/p1` generation has completed and its strict P2 postcheck has passed, sync/check out the tracked handoff commit on the RTX4090, confirm a clean checkout, and recompute the tracked script SHA256.

Export the exact handoff bindings supplied with the committed operator:

```bash
export WP9D_HANDOFF_COMMIT=<handoff-commit>
export WP9D_PPAR_SCRIPT_SHA256=<run.sh-sha256>
C0=ai-work/executor/operator/WP9-d/wp9d-eval400-parallel-benchmark/C0
```

Run only in this order:

```bash
bash "$C0/run.sh" preflight
bash "$C0/run.sh" p2
bash "$C0/run.sh" p4
bash "$C0/run.sh" compare
```

Use tmux for `p2` and `p4` if desired. Never run the two phases concurrently. The `compare` phase is read-only with respect to all three generation bundles and does not require an idle GPU once the bundles are present.

## Comparison report

`compare` reads the completed formal baseline plus the two benchmark bundles and writes:

`$ARTIFACT_ROOT/wp9d/eval400-parallel-benchmark/report/parallel-benchmark-report.json`

It reports for each topology:

- generation-only wall time from `run.json`
- GPU utilization mean/p95
- GPU memory mean/p95/max
- utilization sample count
- semantic generation SHA256 excluding latency telemetry
- raw records-file SHA256
- speedup of p2/p4 versus p1 and p4 versus p2

It also records semantic parity across p1/p2/p4. The report is explicitly benchmark-only and does **not** change the existing P1 runtime freeze by itself.

## Acceptance for considering a runtime revision

A topology is only eligible for a later explicit WP9-d runtime-freeze amendment if:

1. its generation phase passes the strict 400/400 postcheck;
2. semantic generation parity with the formal `b4/p1` baseline holds;
3. no OOM/runtime failure occurs; and
4. the measured throughput gain is material enough to justify revising the frozen runtime.

Do not interpret a faster p4 run as authorization to change GRPO vLLM utilization, Public/Hidden sequencing, Recipe A parameters, or verification worker count.
