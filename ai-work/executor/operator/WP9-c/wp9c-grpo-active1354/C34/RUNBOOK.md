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
- held-out eval400 data: `/root/open-r1-code-verifier-data-4090/wp9c/heldout-eval400-C34` (authoritative final model evaluation suite; unchanged)
- held-out systems benchmark eval200 data: `/root/open-r1-code-verifier-data-4090/wp9c/heldout-eval200-C34`
- synced eval200 verification sources: `/root/open-r1-code-verifier-data-4090/wp9c/eval200-verification-C34`
- parent B: `/root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42`
- C34 GRPO artifacts: `/root/sj-tmp/open-r1-code-verifier-outputs/wp9c/grpo-c29`
- formal benchmark report: `/root/sj-tmp/open-r1-code-verifier-outputs/wp9c/grpo-c29/benchmark/report/refresh_benchmark_report.json`

Do not restore or symlink active `/data` paths.

## Code/data transfer boundary

Code travels through Git. The 4090 must fetch the exact C34 handoff commit, detach/check out that commit, and have a clean worktree.

Data and generated benchmark artifacts travel with rsync; project source code does not. Sync these two immutable input bundles before the C34 systems benchmark:

- `/home/dzy/wp9c-final-reduced-calibration-C29/` -> `/root/open-r1-code-verifier-data-4090/wp9c/final-reduced-calibration-C29/`
- `/home/dzy/wp9c-heldout-eval200-C34/` -> `/root/open-r1-code-verifier-data-4090/wp9c/heldout-eval200-C34/`

Build or byte-verify the deterministic eval200 bundle on the control plane from the frozen eval400 authority before rsync:

```bash
.venv/bin/python "$C34/build_eval200_subset.py" \
  --source /home/dzy/wp8-formal-sync/data/prepared \
  --output /home/dzy/wp9c-heldout-eval200-C34
```

The selection is exactly the first 200 `test` problems in frozen eval400 order. The frozen `/home/dzy/wp8-formal-sync/data/prepared/` eval400 artifact remains authoritative for final model evaluation and must not be deleted, overwritten, or redefined as a 200-problem scientific suite. The tracked C30 `target-sync-manifest.json` remains the 11-file C29 transfer inventory. C34 `run.sh audit` independently recomputes the production reduced-pool checks and frozen C29 SHA256 identities before any GPU job.

Frozen eval200 identity:

- ordered problem IDs SHA256 (`sha256_utf8_lf_lines_v1`): `8a723184e8c3787cf8c18f2d9f6ddd59f6928ca4711b31dc196e4daffb91a422`
- `canonical/problems.jsonl`: `6d90392983a8605773b1f83acb2811f666290598fec8eec4f2225d2eb95d64d3`
- `hf_dataset/data-00000-of-00001.arrow`: `0713020cf3c0c5cf8ede7883be4dda2dabdc9e763b88ffeb94df538120ed11c6`
- `hf_dataset/dataset_info.json`: `92bbb50ce5825d6c8ee4a675a9199f0ebae50535909313d1e442ed28d68895f9`
- `hf_dataset/state.json`: `cd9375ded43d13e712090ddf5dbaadcd682e4d8a0e22b70904f9aa3ad216fcb0`
- `eval200_manifest.json`: `c3ee992f59faa70e1bc6a3d60546921f1862db56b79135f98a561cecae1951cf`

The training sidecars are byte-identical to eval400 because train/validation are intentionally unchanged; their hashes remain the frozen eval400 values.

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

1. C34 systems benchmark evaluation generation batch sweep for batches 1, 2, 4, 8, 16 on the 4090 using deterministic held-out eval200. The frozen held-out eval400 suite remains authoritative for final model evaluation.
2. Evaluation verification worker sweep for workers 1, 8, 16, 32, 64 using the same batch-1 frozen generation bundle; this verification is control-plane/Piston work and can be performed on the 1660 Ti, then the small verification run directories are rsynced to the 4090 for strict report rebuilding.
3. C29 GRPO k=8 Public worker sweep 8, 16, 32, 64.
4. C29 Public k=4/w8 diagnostic with the same bounded 20-step workset.
5. C29 Hidden k=8/w8 sequential source.
6. Same-GPU Public/Hidden k=8/w8 concurrent trial.

First generate the five exact-parity evaluation bundles on the 4090:

```bash
bash "$C34/run_eval_generation_sweep.sh"
```

Expected generation output is `eval200`, with `b1 -> b2 -> b4 -> b8 -> b16`, exactly 200 problems each. All b2/b4/b8/b16 bundles must have exact generation parity with the fresh eval200 b1 bundle.

Rsync only the fresh eval200 batch-1 generation run back to the 1660 Ti, then run the tracked control-plane verification sweep against the same deterministic eval200 dataset:

```bash
bash "$C34/run_eval_verification_sweep.sh" \
  <absolute-local-eval200-b1-generation-run> \
  /home/dzy/wp9c-heldout-eval200-C34 \
  /home/dzy/wp9c-grpo-c29-eval200-verification
```

Rsync `/home/dzy/wp9c-grpo-c29-eval200-verification/` back to target `/root/open-r1-code-verifier-data-4090/wp9c/eval200-verification-C34/`. Then run the GRPO timing sources on the 4090:

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

The legacy 400-problem batch-1 run `wp9c-c29-b-eval-b1-seed42` was interrupted after at least 245 generation records. Preserve that artifact for debugging/order comparison only. It is not a formal eval200 throughput source because its run identity, `total_problems`, timing interval, and unfinished records hash belong to the interrupted 400-problem attempt. C34 therefore requires a fresh eval200 b1 run, followed by fresh b2/b4/b8/b16 runs. If the legacy artifact is available, compare its first 200 problem IDs with the deterministic eval200 ordered IDs and record the result; do not rewrite or truncate the legacy manifest.

After all sources are present, freeze the report with the path-bound wrapper:

```bash
bash "$C34/freeze_formal_benchmark.sh"
```

It calls `build_formal_benchmark.py`, which invokes the production benchmark summarizer/checker and requires the report to bind exactly to the C29 calibration/order/Public/Hidden hashes.

## Pilot gate

Read `freeze_summary.json` from the formal benchmark output and use its exact `selected_grpo_verification_workers` and `paired_grpo_mode`.

The tracked selector reads the strict formal benchmark and executes the selected worker count/topology automatically:

```bash
bash "$C34/run_selected_pair.sh" pilot
```

Each completed pilot is then checked by `check_pilot.py`: >=100 groups, exactly 8 samples/group, exact C29/benchmark/worker identity, finite runtime/group telemetry, no reward-infrastructure retry instability, and the frozen zero-variance thresholds. Only `<0.20` is `green`; `0.20..0.25` is warning and `>0.25` is stop. Warning/stop exits nonzero and blocks formal training.

## Formal 300-step GRPO

C34 formal training refuses to start until both Public and Hidden pilot acceptance summaries are present, green, and bound to the same benchmark SHA/worker count.

Use the same strict selector for the 300-step pair:

```bash
bash "$C34/run_selected_pair.sh" formal
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
