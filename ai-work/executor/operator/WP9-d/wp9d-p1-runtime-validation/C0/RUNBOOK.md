# WP9-d C0 — P1 bounded runtime validation handoff

This checkpoint prepares the RTX 4090-only P1 systems validation for WP9-d using the frozen fresh-GRPO qkvo LoRA target set (`q_proj,k_proj,v_proj,o_proj`). It is intentionally bounded and must not be used to start Recipe A, full eval400, or any WP9-c rerun.

## Scope

Authorized target-side work is limited to:

1. Public GRPO smoke: exactly one optimizer step from frozen B.
2. Hidden GRPO smoke: exactly one optimizer step from frozen B.
3. Same-GPU Public + Hidden concurrent smoke: exactly one optimizer step per process. Start at vLLM memory utilization `0.40`; only if that pair fails because of OOM / vLLM memory initialization / unsafe headroom may `0.30` be tried, then `0.25`. Do not test intermediate fractions.
4. Eval generation systems smoke on exactly the first 8 problems of canonical eval400:
   - reference: `batch_size=4`, `parallel_generators=1`;
   - candidate: `batch_size=4`, `parallel_generators=2`.
5. Read-only postcheck/report generation from those bounded artifacts.

The checkpoint must stop after P1. It does not authorize B eval400 refresh, 1200-step Recipe A, step300/600/900/1200 eval400, Recipe B, or Recipe C.

## Frozen target roots

Expected RTX 4090 target checkout and persistent roots:

- repo: `/root/open-r1-code-verifier`
- artifact root: `/root/sj-tmp/open-r1-code-verifier-outputs`
- data root: `/root/open-r1-code-verifier-data-4090`
- parent B: `/root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42`
- C29 active pool: `/root/open-r1-code-verifier-data-4090/wp9c/final-reduced-calibration-C29`
- canonical eval400 source: `/root/open-r1-code-verifier-data-4090/wp9c/heldout-eval400-C34`
- P1 eval8 subset: `/root/open-r1-code-verifier-data-4090/wp9d/p1-eval8-C0`
- P1 artifact root: `/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/p1-runtime-validation`
- P1 operator evidence: `/root/sj-tmp/open-r1-code-verifier-outputs/operator/WP9-d/wp9d-p1-runtime-validation/C0/`

The target code must be the exact handoff commit reported after C0 is committed. Do not reset or clean unknown target-side work. If the checkout is not clean, stop and inspect.

## Required target environment

The 4090 must already have the pinned training environment and cached model. The canonical Piston reverse-forward must make `http://127.0.0.1:2000` available before GRPO reward verification starts.

Set the exact C0 Git/SHA bindings before invoking the script:

```bash
export WP9D_HANDOFF_COMMIT=<exact C0 handoff commit>
export WP9D_P1_SCRIPT_SHA256=<sha256 of run.sh>
```

The target script additionally verifies:

- clean target checkout;
- an actual RTX 4090 with `>=22528 MiB` total and `>=20000 MiB` free VRAM; if more than one GPU is visible, the script selects the 4090 explicitly and exports `CUDA_VISIBLE_DEVICES`;
- CUDA + BF16;
- pinned TRL `0.18.0` and vLLM `0.8.5.post1`;
- exact frozen B model/revision/seed;
- exact one-step WP9-d smoke config hashes, qkvo LoRA target semantics, and qkvo checkpoint readback;
- exact C29 Public/Hidden training hashes and benchmark binding;
- canonical eval400 dataset identity before accepting the 8-problem systems subset;
- target-local validation-machine pointer is exactly `READY_FOR_VALIDATION_PLANNER`, uses the current `/root` roots, and exposes only `http://127.0.0.1:2000` for Piston;
- phase-specific storage headroom and atomic operator status/evidence contracts.

The 1660 Ti has already built the deterministic transfer bundle at `/home/dzy/wp9d-p1-eval8-C0`. Its first-8 ordered ID SHA256 is:

```text
0e9d0d2f93422aa9cee4b1d66dcb56d498a6fa40b44d31270c237c7ab975324e
```

When the 4090 is online, rsync that directory to `/root/open-r1-code-verifier-data-4090/wp9d/p1-eval8-C0/` before `preflight` when practical. `preflight` will strictly verify the transferred bytes against canonical eval400 and will build the same deterministic subset only if the target copy is absent. Later eval phases use a lightweight hash/order recheck instead of rebuilding it.

## Commands after the 4090 is online

Run only the phase needed. This keeps retries minimal.

```bash
C0=ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0

bash "$C0/run.sh" preflight
bash "$C0/run.sh" single public
bash "$C0/run.sh" single hidden
```

Only after both single-arm smokes pass:

```bash
bash "$C0/run.sh" concurrent 0.40
```

If and only if the `0.40` pair fails for the allowed memory-pressure reasons, try:

```bash
bash "$C0/run.sh" concurrent 0.30
# only if 0.30 still fails for the same allowed reason:
bash "$C0/run.sh" concurrent 0.25
```

Do not run finer fractions.

Then run the one-wave generation measurements:

```bash
bash "$C0/run.sh" eval single
bash "$C0/run.sh" eval dual
```

Finally generate the read-only P1 report:

```bash
bash "$C0/run.sh" report
```

The report phase does not launch training or generation. It refuses to freeze a concurrent decision unless both single arms exist and at least one valid concurrent candidate exists. It refuses to freeze dual-b4 unless both 8-problem reference/candidate bundles exist and their problem order matches the canonical eval8 subset.

## Artifact isolation

All new artifacts are under:

```text
/root/sj-tmp/open-r1-code-verifier-outputs/wp9d/p1-runtime-validation/
```

No historical WP9-c artifact is modified or deleted. Each GRPO arm and each concurrent memory fraction has an independent output root/run name. Failed attempts are preserved; rerun only the affected phase with the explicit `WP9D_P1_RETRY_TAG` suffix after diagnosis/repair. Successful phases atomically update small `accepted/*.json` pointers, so a repair to one phase does not force unrelated one-step/8-problem smokes to rerun. The final report validates the passed operator evidence behind every accepted pointer and records all contributing handoff commits when evidence spans a narrow repair commit.

Every target invocation writes an atomic `status` plus secret-free `operator-evidence.json` containing the exact handoff commit, tracked `run.sh` SHA256, machine/runtime identity, timestamps, command/postcheck return codes, and hashes of the minimal required artifacts. `passed` is legal only when both command and postcheck succeed.

## Expected final evidence

`run.sh report` writes:

```text
.../wp9d/p1-runtime-validation/report/p1-runtime-report.json
```

It includes the bounded single-arm total/step/vLLM-generation/reward/backward/optimizer timings, GPU utilization, driver-visible and torch peak memory, checkpoint-1 readback, concurrent speedup/headroom decision, b4×1 vs b4×2 generation speedup/order integrity, and the candidate runtime-freeze mapping. If the report is regenerated after an affected-phase repair, the previous derived report is archived by content hash rather than deleted. The control plane must review that JSON and the referenced operator evidence before updating the WP9-d spec/plan/proceedings.
