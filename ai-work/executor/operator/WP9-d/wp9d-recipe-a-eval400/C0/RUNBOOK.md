# WP9-d C0 — Recipe A eval400 checkpoint generation

This formal target-GPU gate generates canonical eval400 completions for the completed Recipe A Public/Hidden runs at steps `300/600/900/1200`. It is generation-only: it never contacts Piston and never verifies, scores, or aggregates results.

## Frozen contract

- formal Recipe A training commit: `7b5e097b448b6c42fb9faf1f27711a65e00d2075`
- completed runs:
  - `wp9d-A-public-vllm-qkvo-active1354-seed42`
  - `wp9d-A-hidden-vllm-qkvo-active1354-seed42`
- checkpoints per arm: `300/600/900/1200`
- parent B: `B-sft-formal-seed42`
- model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`
- revision: `2e1fd397ee46e1388853d2af2c993145b0f1098a`
- seed: `42`
- canonical eval400 dataset SHA256: `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`
- ordered problem IDs SHA256: `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`
- eval config SHA256: `3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3`
- P1 eval topology: `batch_size=4`, `parallel_generators=1`, dedicated streams disabled.
- user-directed scheduling amendment: `checkpoint_parallelism=2`. This does not change the P1-frozen per-checkpoint topology; each checkpoint still runs `batch_size=4`, `parallel_generators=1`, with no dedicated CUDA stream.

The helper validates each selected checkpoint before model loading: direct ownership by the completed GRPO run, exact `trainer_state.global_step`, formal training commit in checkpoint log state, parent B identity, and q/k/v/o LoRA `r=16/alpha=32/dropout=0.05`.

## Target roots

- repo: `/root/open-r1-code-verifier`
- artifacts: `/root/sj-tmp/open-r1-code-verifier-outputs`
- formal data: `/root/open-r1-code-verifier-data-4090`
- HF home: `/root/huggingface`
- Recipe A training: `/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/recipe-a`
- generation output: `/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/recipe-a-eval400`

## Execution

After this checkpoint is committed on the 1660 Ti control plane, make the exact commit reachable on the first RTX 4090 without pushing from this workflow. Detach/check out the exact handoff commit, verify a clean checkout, recompute the script SHA256, and export:

```bash
export WP9D_HANDOFF_COMMIT=<exact C0 handoff commit>
export WP9D_RECIPE_A_EVAL_SCRIPT_SHA256=<exact run.sh SHA256>
C0=ai-work/executor/operator/WP9-d/wp9d-recipe-a-eval400/C0
```

Run:

```bash
bash "$C0/run.sh" preflight
bash "$C0/run.sh" generate
```

`generate` runs four two-checkpoint waves, with both jobs in a wave launched concurrently and both awaited before the next wave starts:

1. Public `300 + 600`
2. Public `900 + 1200`
3. Hidden `300 + 600`
4. Hidden `900 + 1200`

Each job gets its own terminal log and persisted return-code evidence. If either job in a wave fails, the operator still waits for the sibling job, preserves both outputs/logs, records the failing wave, and fails closed. `SIGINT`/`SIGTERM` terminates and awaits any active checkpoint children before writing failed evidence. The strict postcheck requires all eight `run.json` files to be completed, all eight per-job RCs to equal zero, non-empty per-job logs, 400 unique problem IDs per bundle, exact checkpoint identity, exact dataset/order/runtime/seed bindings, and available GPU utilization telemetry.

If a generation fails, preserve the failed bundle and operator evidence. Diagnose first, then use `WP9D_RECIPE_A_EVAL_RETRY_TAG` for a retry; never delete or overwrite failed evidence.

## After generation PASS

Do not score on the RTX 4090. Sync the eight completed generation bundles plus operator evidence to the 1660 Ti control plane together with the already-completed WP9-d B-refresh generation bundle. Then run local-Piston verification and aggregation for B plus all eight Recipe A bundles under one scoring protocol. Only after that unified scoring pass should checkpoint ranking or B deltas be reported.
