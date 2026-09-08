# WP9-d C0 — P2 frozen-B eval400 refresh

This portable target-GPU checkpoint is the post-P1 P2 prerequisite for Recipe A. It does **not** rerun P1 and it does **not** start GRPO training.

## Frozen contract

- result-code baseline: `7a92bb587fe34e6ae80a5d703e85a0659f05f43a`
- P1 report SHA256: `5a6801024c70177e5f4f777bf524e8b263f93782f4e262ad03bbe886955d231d`
- parent B: `B-sft-formal-seed42`
- model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`
- revision: `2e1fd397ee46e1388853d2af2c993145b0f1098a`
- seed: `42`
- canonical eval400 dataset SHA256: `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`
- ordered problem IDs SHA256: `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`
- eval config SHA256: `3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3`
- P1-frozen eval topology: `batch_size=4`, `parallel_generators=1`, dedicated streams disabled, verification workers `64`.

The old pre-P1 plan text naming two concurrent b4 generators is historical default-candidate text. P1 selected the single generator because its end-to-end wall time was better; this operator binds the measured final freeze.

## Target roots

- repo: `/root/open-r1-code-verifier`
- artifacts: `/root/sj-tmp/open-r1-code-verifier-outputs`
- formal data: `/root/open-r1-code-verifier-data-4090`
- HF home: `/root/huggingface`
- B run: `/root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42`
- eval400 source: `/root/open-r1-code-verifier-data-4090/wp9c/heldout-eval400-C34`
- new P2 output: `/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/b-refresh-eval400`

## Manual target commands

After this checkpoint is committed on the 1660 Ti control plane, make that exact commit reachable on the 4090 without pushing from the workflow. On the target, detach/check out the exact handoff commit, verify a clean checkout, recompute the script SHA256, then export:

```bash
export WP9D_HANDOFF_COMMIT=<exact C0 handoff commit>
export WP9D_P2_SCRIPT_SHA256=<exact run.sh SHA256>
C0=ai-work/executor/operator/WP9-d/wp9d-b-refresh-eval400/C0
```

Run the non-generation preflight first:

```bash
bash "$C0/run.sh" preflight
```

Only after it reports `P2 preflight PASS`, run the frozen-B generation in tmux:

```bash
bash "$C0/run.sh" generate
```

`generate` uses `code-verifier generate-eval`; it never contacts Piston and it does not verify or aggregate completions. It writes a versioned operator evidence file and passes only when the command and strict postcheck both pass.

## After target PASS

Do not start Recipe A yet. Sync the P2 operator evidence plus the completed generation bundle required by `verify-eval` to the 1660 Ti control plane. Run `verify-eval` with the same canonical eval400 dataset, `workers=64`, and local Piston, then `aggregate-eval`. Freeze that verified B result as the WP9-d comparison baseline. Only after the P2 baseline is accepted should the separate Recipe A operator checkpoint be committed and Public training be manually started on the 4090.

If `generate` fails, preserve the failed run/evidence. Diagnose the failure and use `WP9D_P2_RETRY_TAG` only for the affected retry; do not delete or overwrite the failed attempt and do not rerun P1.
