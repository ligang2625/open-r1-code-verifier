# WP9-c C25 — fresh reduced-pool calibration generation

C24 is closed with exactly 1602 formal external-new rows and 0 formally eligible SFT-reuse rows. C25 performs **fresh initial k=8 generation only**. Historical 5000-problem completions/reward outcomes are forbidden as C25 evidence.

## Status

C25 is prepared and statically reviewed, but **has not been run on the RTX 4090**. The old control-plane-path script `01-run-fresh-generation.sh` is superseded and intentionally exits 125. The only valid target-GPU entrypoint is the tracked portable-target script:

`ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/run.sh`

Do not run C25 until an actual operator-handoff commit containing the reviewed C24/C25 tracked files is created and reachable from the 4090.

## Frozen input

Control-plane source bundle:

`/home/dzy/wp9c-fresh-calibration-input-C25`

It must be copied byte-for-byte to the target machine at:

`$CODE_VERIFIER_DATA_ROOT/wp9c/fresh-calibration-input-C25`

The whole directory must be copied, including the two zero-byte exclusion manifests used by the strict loader.

Frozen identity:

- problems: 1602
- external-new: 1602
- SFT reuse: 0
- quality-gate-required: 0
- Formal-B context pass: 1602/1602
- maximum prompt tokens: 2019 / 2048
- input manifest SHA256: `bdccb68febe85f1da381ba01671fb220246dac9e74cdfacb89e4d1da7e334aff`
- inputs SHA256: `dbb6f18a472e390acbec641daab65db6d3f2cb07d3469f8e46ef2d90bf867d18`
- excluded-context SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- excluded-quality SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

## Frozen B and sampling

Target frozen B location:

`$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42`

Sampling contract:

- initial generations per problem: 8
- expected records: 12,816
- sample indices: 0..7
- seed: `calibration_problem_seed(42, problem_id, 0)`
- temperature: 0.8
- top_p: 0.95
- max_new_tokens: 512
- max_prompt_tokens: 2048
- problem batch size: 4
- local-files-only model load

## Target-machine gates

`run.sh` resolves target-local `.ai-bridge/validation-machine.json` as the machine authority and fails closed unless:

- machine status is `READY_FOR_VALIDATION_PLANNER`;
- `artifact_root`, `hf_home`, and `formal_data_root` are all under `/root`;
- no active root is under retired `/data`;
- `/root/tmp` exists and is writable;
- artifact filesystem has at least 20 GiB free and 100,000 free inodes;
- the target checkout is clean and HEAD equals `WP9C_HANDOFF_COMMIT`;
- the tracked `run.sh`, checkpoint, runner, config, C24 checkpoint and input bytes match their frozen bindings;
- the frozen B identity matches exactly;
- one RTX 4090 with at least 22,528 MiB total VRAM is visible and BF16 is supported;
- fresh/resumed generation starts only when that 4090 has at least 20,000 MiB free VRAM;
- Hugging Face/Transformers/Datasets are offline.

A completed-output reuse does not require 20,000 MiB currently free because it does not reload the model, but it still verifies the certified RTX 4090 machine identity.

## Resume semantics

C25 uses the project `run_calibration_generation` exact-prefix persistence contract.

- generation rows are appended only in complete k=8 problem groups;
- appended bytes are flushed and `fsync`ed before the progress marker advances;
- `progress.json` is written atomically;
- on restart, bytes newer than the committed `byte_count` are truncated;
- the durable prefix must contain a multiple of 8 records and match the exact `(problem_id, sample_index)` prefix;
- committed groups are never regenerated;
- an interrupted uncommitted batch is regenerated from the same deterministic per-problem seeds;
- a completed bundle is loaded with the strict loader and reused without loading the model.

Review validation includes a batch-size-4 interruption simulation: 4 problems/32 rows were committed, an invalid uncommitted tail was appended, and restart correctly removed only that tail and resumed from problem 5.

## Handoff procedure

1. Create a narrow operator-handoff commit containing the reviewed C24 checkpoint and C25 config/checkpoint/runner/runbook/scripts. Ensure `C25/run.sh` is executable in Git (`100755`).
2. Make that commit reachable from the 4090.
3. Copy the complete C25 input bundle to `$CODE_VERIFIER_DATA_ROOT/wp9c/fresh-calibration-input-C25`.
4. On the 4090, check out/detach at the exact handoff commit and confirm the checkout is clean.
5. Set the handoff identity and run in tmux/SSH:

```bash
export WP9C_HANDOFF_COMMIT=<exact-handoff-commit>
bash ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration/C25/run.sh
```

If interrupted, rerun the **same command at the same commit**. Do not delete or rename the target generation output; the durable prefix is the recovery state.

## Mandatory postcheck

A command exit code of zero is not sufficient. `run.sh` only reports `gate_status=passed` after strict postcheck confirms:

- 1602 problems / 12,816 generation records;
- exact input order;
- exactly sample indices 0..7 per problem;
- exact deterministic sample seed per problem;
- frozen input/B identity;
- generation records SHA matches `run.json`;
- progress marker byte count equals the completed JSONL size;
- strict `load_completed_calibration_generation` succeeds.

The target writes append-only terminal log, postcheck summary, atomic status, and secret-free `operator-evidence.json` under the machine `artifact_root` operator directory.

## After C25

Sync the required generation bundle plus small operator evidence/postcheck artifacts back to the control plane and reply `执行完毕`. The control plane must independently verify exact 1602 x 8 coverage before opening C26 fresh Public/Hidden scoring.

C26 scoring is not allowed to use the historical 5000-problem scores. It will score the same new completions against the C24 frozen Public/Hidden test views. Any problem that is all-zero on both arms enters a separate fresh k=8 retry generation gate (sample indices 8..15) before final informativeness classification.
