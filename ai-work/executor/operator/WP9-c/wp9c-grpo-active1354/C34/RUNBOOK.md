# WP9-c C34 — C29 active-1354 GRPO target runbook

This handoff prepares the frozen C29 reduced calibrated pool for target-side GRPO benchmark, pilot, and formal training. It does not authorize SFT work and it does not bypass the WP9 systems/pilot gates.

## Frozen scientific identity

- parent B: `B-sft-formal-seed42`
- base model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`
- model revision: `2e1fd397ee46e1388853d2af2c993145b0f1098a`
- C29 calibration manifest SHA256: `5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b`
- active problems: `1354`
- active order SHA256: `401f854032095cb638637dcf2d1ec000b770cd2d4c78619331f0b13746618c14`
- Public training SHA256: `558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c`
- Hidden training SHA256: `9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec`

The C34 prompt audit rebuilt the exact trainer conversational prompt for all 1354 Public rows with the frozen Qwen tokenizer/chat template. Results: min 116 tokens, p95 817, max 2019, 30 rows above 1024, and zero rows above 2048. Therefore the C29-specific benchmark/pilot/formal configs freeze `max_prompt_length=2048`; using the historical refresh configs with 1024 would truncate 30 frozen prompts.

## Target paths

The target machine pointer remains authoritative. On the current 4090 it resolves under `/root`:

- artifact root: `/root/sj-tmp/open-r1-code-verifier-outputs`
- HF home: `/root/huggingface`
- formal data root: `/root/open-r1-code-verifier-data-4090`
- C29 pool: `/root/open-r1-code-verifier-data-4090/wp9c/final-reduced-calibration-C29`
- parent B: `/root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42`
- C34 GRPO artifacts: `/root/sj-tmp/open-r1-code-verifier-outputs/wp9c/grpo-c29`

Do not restore or symlink active `/data` paths.

## Code/data transfer boundary

Code travels through Git. The 4090 must fetch the exact C34 handoff commit, detach/check out that commit, and have a clean worktree.

The C29 data bundle travels with rsync. Sync the directory byte-for-byte to:

`/root/open-r1-code-verifier-data-4090/wp9c/final-reduced-calibration-C29/`

The tracked C30 `target-sync-manifest.json` is the 11-file transfer inventory. C34 `run.sh audit` independently recomputes the production reduced-pool checks and the three frozen top-level SHA256 identities before any GPU job.

## Piston transport

GRPO reward execution requires the canonical reverse SSH forward owned by the 1660 Ti control plane:

`-R 127.0.0.1:2000:127.0.0.1:2000`

The 4090 must see only `http://127.0.0.1:2000`. Do not start the retired Tailscale/local-forward helper while the reverse forward is active.

## Target operator environment

Every target command must export:

```bash
export WP9C_HANDOFF_COMMIT=<exact-c34-handoff-commit>
export WP9C_SCRIPT_SHA256=<sha256-of-C34-run.sh>
export WP9C_CONCURRENT_SCRIPT_SHA256=<sha256-of-run_concurrent_benchmark.sh>
export WP9C_PAIR_SCRIPT_SHA256=<sha256-of-run_concurrent_pair.sh>
```

Use the tracked paths from the detached handoff checkout:

```bash
C34=ai-work/executor/operator/WP9-c/wp9c-grpo-active1354/C34
```

First run the read-only audit:

```bash
bash "$C34/run.sh" audit
```

## Formal systems benchmark prerequisites

The project specification requires one formal throughput report before k=8 pilot/formal GRPO. The report must include all of the following:

1. B evaluation generation batch sweep for batches 1, 2, 4, 8, 16 on the 4090.
2. Evaluation verification worker sweep for workers 1, 8, 16, 32, 64 using the same batch-1 frozen generation bundle; this verification is control-plane/Piston work and can be performed on the 1660 Ti, then the small verification run directories are rsynced to the 4090 for strict report rebuilding.
3. C29 GRPO k=8 Public worker sweep 8, 16, 32, 64.
4. C29 Public k=4/w8 diagnostic with the same bounded 20-step workset.
5. C29 Hidden k=8/w8 sequential source.
6. Same-GPU Public/Hidden k=8/w8 concurrent trial.

The tracked C34 GRPO benchmark commands are:

```bash
bash "$C34/run.sh" benchmark-k8 public 8 baseline
bash "$C34/run.sh" benchmark-k8 public 16 worker16
bash "$C34/run.sh" benchmark-k8 public 32 worker32
bash "$C34/run.sh" benchmark-k8 public 64 worker64
bash "$C34/run.sh" benchmark-k4 public 8 diagnostic
bash "$C34/run.sh" benchmark-k8 hidden 8 sequential
bash "$C34/run_concurrent_benchmark.sh"
```

Benchmark timing sources deliberately forbid resume. If one is interrupted, preserve it and rerun with a fresh tag rather than treating a resumed attempt as formal timing evidence.

After the evaluation sweep and all GRPO sources are present, freeze the report with `build_formal_benchmark.py`. It invokes the production benchmark summarizer/checker and requires the report to bind exactly to the C29 calibration/order/Public/Hidden hashes.

## Pilot gate

Read `freeze_summary.json` from the formal benchmark output and use its exact `selected_grpo_verification_workers` and `paired_grpo_mode`.

If `paired_grpo_mode=sequential`:

```bash
bash "$C34/run.sh" pilot public <workers> <absolute-refresh_benchmark_report.json>
bash "$C34/run.sh" pilot hidden <workers> <absolute-refresh_benchmark_report.json>
```

If `paired_grpo_mode=concurrent`:

```bash
bash "$C34/run_concurrent_pair.sh" pilot <workers> <absolute-refresh_benchmark_report.json>
```

Each completed pilot is then checked by `check_pilot.py`: >=100 groups, exactly 8 samples/group, exact C29/benchmark/worker identity, finite runtime/group telemetry, no reward-infrastructure retry instability, and the frozen zero-variance thresholds. Only `<0.20` is `green`; `0.20..0.25` is warning and `>0.25` is stop. Warning/stop exits nonzero and blocks formal training.

## Formal 300-step GRPO

C34 formal training refuses to start until both Public and Hidden pilot acceptance summaries are present, green, and bound to the same benchmark SHA/worker count.

If the benchmark selected sequential execution:

```bash
bash "$C34/run.sh" formal public <workers> <absolute-refresh_benchmark_report.json>
bash "$C34/run.sh" formal hidden <workers> <absolute-refresh_benchmark_report.json>
```

If the benchmark selected concurrent execution:

```bash
bash "$C34/run_concurrent_pair.sh" formal <workers> <absolute-refresh_benchmark_report.json>
```

Public and Hidden always initialize independently from the same frozen B. Public is never the parent of Hidden.

## Resume policy

Pilot/formal runs may resume only from a checkpoint belonging to the same run. Export, as applicable:

```bash
export WP9C_RESUME_CHECKPOINT=/absolute/path/to/the/run/checkpoints/checkpoint-N
export WP9C_RESUME_RUN_GIT_COMMIT=<40-hex-original-run-commit>
export WP9C_RESUME_CODE_MIGRATION=operational_reward_resilience_v1
```

Then invoke the same pilot/formal command. Do not set these variables for benchmark timing sources.

## Output/review

Each invocation writes an operator namespace under:

`$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/wp9c-grpo-active1354/C34/`

A passed target invocation has a final `status=passed` plus secret-free `operator-evidence.json`. Large model checkpoints remain on the 4090; sync small evidence/manifests/metrics/logs back to the 1660 Ti for review rather than copying checkpoints by default.
