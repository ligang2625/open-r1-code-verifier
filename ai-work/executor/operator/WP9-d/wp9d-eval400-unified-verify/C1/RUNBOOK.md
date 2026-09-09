# WP9-d C1 — Hidden300 full-400 verification repair

C1 repairs the single infrastructure-contaminated C0 verification result without mutating or overwriting any C0 artifact. C0 completed all nine `verify-eval` and `aggregate-eval` commands, but strict acceptance failed because `wp9d-A-hidden-step300-eval400-b4-p1-seed42` contained two Piston `sandbox_error` rows (rows 55 and 59). The other eight C0 runs are frozen clean evidence.

## Repair policy

- Preserve the complete C0 operator evidence, terminal log, status and all nine C0 evaluation directories byte-for-byte.
- Do **not** patch only the two failed rows.
- Re-run the entire 400-problem Hidden-step300 verification from the immutable frozen generation bundle in a new output namespace.
- Use the same verifier commit, canonical eval400 data, Piston definition, seed 42 and `workers=64` protocol as C0.
- Aggregate the repaired 400-row run independently.
- Require zero `sandbox_error` rows in the repaired run.
- Require exact frozen generation payload preservation for all 400 rows.
- Require the 398 non-infrastructure C0 rows to reproduce the same verifier semantics, allowing only fresh `runtime_ms` telemetry.
- Final accepted set = eight byte-frozen clean C0 runs + the new C1 Hidden300 full-400 repair.

This is a full-run repair, not a post-hoc row substitution.

## Frozen lineage

- failed C0 operator commit: `8717f6032c27117facbd996b7bce3ba8ec328143`
- C0 operator evidence SHA256: `92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1`
- C0 terminal log SHA256: `c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee`
- C0 status: `1`
- C0 failed Hidden300 results SHA256: `a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f`
- C0 failure fingerprint:
  - row 55: `leetcode-earliest-possible-day-of-full-bloom`
  - row 59: `leetcode-expressive-words`
  - both have a train-hidden `sandbox_error`
- Recipe A verifier project commit: `f17b4f607daa3bb03b08682bbbd841118d36c4af`
- Open-R1: `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`
- dependency lock: `4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf`
- canonical eval400 dataset: `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`
- ordered problem IDs: `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`
- eval config: `3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3`
- Piston definition: `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`
- Hidden300 generation run.json SHA256: `e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120`
- Hidden300 generation records SHA256: `8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c`

C1 also binds all four artifact hashes (`run.json`, `results.jsonl`, `summary.json`, `main_results.csv`) for each of the eight clean C0 runs before repair begins.

## Paths

- verifier checkout: `/home/dzy/wp9d-verifier-a-f17b4f6`
- frozen generation bundle: `/home/dzy/wp9d-recipe-a-eval400-f17b4f6/generation/wp9d-A-hidden-step300-eval400-b4-p1-seed42`
- C0 immutable results: `/home/dzy/wp9d-eval400-verified/evaluation`
- default C1 repair output: `/home/dzy/wp9d-eval400-repair-c1`
- C1 operator evidence: `/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C1`
- final accepted-set manifest: `/home/dzy/wp9d-eval400-repair-c1/final-verification-manifest.json`

If a completed C1 attempt itself contains a new infrastructure failure, preserve it and use a fresh output namespace by exporting a safe `WP9D_VERIFY_REPAIR_TAG`. Do not delete or overwrite the failed C1 output.

## Manual execution

After C1 is committed, from the WP9-d worktree export the exact C1 commit and tracked script SHA256:

```bash
export WP9D_REPAIR_HANDOFF_COMMIT=<exact C1 commit>
export WP9D_REPAIR_SCRIPT_SHA256=<exact C1 run.sh SHA256>
C1=ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C1
```

Run preflight first:

```bash
bash "$C1/run.sh" preflight
```

Expected terminal line:

```text
WP9-d C1 repair preflight PASS: run=wp9d-A-hidden-step300-eval400-b4-p1-seed42 rows=400 workers=64 output=/home/dzy/wp9d-eval400-repair-c1
```

Then manually run the full 400-problem repair, preferably in tmux:

```bash
bash "$C1/run.sh" repair
```

Follow the append-only operator log from another shell if desired:

```bash
tail -F /home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C1/terminal.log
```

A successful repair ends with:

```text
formal_repair_postcheck=PASS bundles=9 records=3600 repaired_run=hidden-step300 repaired_rows=400 sandbox_errors=0 aggregation=PASS
```

C1 never regenerates model completions, never loads model weights, and never requires an RTX 4090.
