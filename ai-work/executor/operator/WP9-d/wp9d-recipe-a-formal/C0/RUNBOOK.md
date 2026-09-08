# WP9-d Recipe A formal GRPO C0

Purpose: launch the two formal 1200-step Recipe A arms on one RTX4090 in strict sequence, with Public first and Hidden starting immediately after Public strict postcheck. Both arms independently start from the same immutable `B-sft-formal-seed42` parent.

## User-directed checkpoint cadence amendment

The previously frozen Recipe A configs use `save_steps: 100`. This handoff adds two tracked derived configs:

- `configs/grpo/wp9d-recipe-a-public-save50.yaml`
- `configs/grpo/wp9d-recipe-a-hidden-save50.yaml`

They are byte-for-byte semantic derivatives of the frozen configs with exactly one field changed: `save_steps: 100 -> 50`. All other Recipe A scientific parameters remain unchanged. The operator preflight verifies this derivation and the exact config SHA256 values before training.

Expected checkpoints for each arm are exactly `checkpoint-50, checkpoint-100, ... checkpoint-1200` (24 checkpoints). Formal evaluation checkpoints at steps 300/600/900/1200 remain included in that cadence.

## Precondition accepted for this execution order

The B eval400 generation gate has completed and strict-postchecked 400/400 records. Its formal scoring/verification is intentionally deferred to the separate validation GPU per the user's execution order. Training may proceed, but Recipe A checkpoint deltas must not be interpreted as final evaluation results until the B baseline and corresponding Recipe A checkpoints are verified/aggregated under the frozen evaluation protocol.

## Runtime contract

- Public then Hidden, sequential only.
- No concurrent Public/Hidden GRPO.
- `use_vllm=true`, colocate mode, `vllm_gpu_memory_utilization=0.40`.
- reward verification workers: 8.
- `num_generations=8`, prompt cap 2048, completion cap 512.
- train batch 1, gradient accumulation 8.
- learning rate `5e-6`, 1200 steps, one epoch cap, warmup ratio 0.05, constant-with-warmup scheduler.
- temperature 0.8, top_p 0.95, beta 0.01.
- bf16 true, fp16 false, gradient checkpointing true; runtime remains non-reentrant as previously repaired/validated.
- fresh GRPO LoRA q/k/v/o, r=16, alpha=32, dropout=0.05.
- seed 42.

## Safety behavior

`run.sh execute` runs both arms inside one shell invocation:

1. full preflight;
2. Public training to step 1200;
3. strict Public artifact/checkpoint postcheck;
4. immediately launch Hidden from the original B parent, with no prompt/sleep/manual pause;
5. strict Hidden artifact/checkpoint postcheck;
6. final combined operator evidence.

If Public training or Public postcheck fails, Hidden is not started. This is failure containment, not an intentional pause. The initial C0 operator refuses implicit resume and refuses to overwrite an existing formal run directory.

## Target invocation

After transferring/checking out the tracked handoff commit on the target RTX4090 and confirming a clean checkout, recompute the script SHA256 and export the exact bindings supplied with the committed handoff:

```bash
export WP9D_HANDOFF_COMMIT=<handoff-commit>
export WP9D_P3_SCRIPT_SHA256=<run.sh-sha256>
export WP9D_FORMAL_EXECUTION_ACK=RUN_RECIPE_A_PUBLIC_THEN_HIDDEN_1200_SAVE50
C0=ai-work/executor/operator/WP9-d/wp9d-recipe-a-formal/C0
```

Run the no-GRPO preflight first:

```bash
bash "$C0/run.sh" preflight
```

Then start one tmux session and run exactly one formal command inside it:

```bash
tmux new-session -s wp9d-recipe-a
bash "$C0/run.sh" execute
```

Do not separately invoke Hidden. `execute` owns the entire Public -> Hidden sequence.

## Output roots

Formal GRPO root:

`/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/recipe-a`

Runs:

- Public: `wp9d-A-public-vllm-qkvo-active1354-seed42`
- Hidden: `wp9d-A-hidden-vllm-qkvo-active1354-seed42`

Operator evidence/logs:

`/root/sj-tmp/open-r1-code-verifier-outputs/operator/WP9-d/wp9d-recipe-a-formal/C0/`

The Public and Hidden logs are separate, while `operator-evidence.json` records the combined sequential state.
