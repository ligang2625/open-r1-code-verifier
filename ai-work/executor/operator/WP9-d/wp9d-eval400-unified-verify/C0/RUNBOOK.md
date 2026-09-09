# WP9-d C0 — unified eval400 verification on the 1660 Ti

This checkpoint is a **control-plane manual** operator. It consumes the already-synchronized frozen generation bundles and performs only local-Piston verification plus deterministic aggregation. It never loads model weights, never generates completions, and never needs an RTX 4090.

## Frozen inputs

- canonical eval400 dataset: `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`
- ordered problem IDs: `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`
- eval config: `3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3`
- Piston definition: `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`
- seed: `42`
- verification workers: `64`
- B bundle: `/home/dzy/wp9d-b-refresh-eval400/generation/wp9d-B-eval400-b4-p1-seed42`
- Recipe A bundles: `/home/dzy/wp9d-recipe-a-eval400-f17b4f6/generation/wp9d-A-{public,hidden}-step{300,600,900,1200}-eval400-b4-p1-seed42`
- local canonical data: `/home/dzy/wp6d-b-export/required/formal-data/prepared` (content identity, not path identity, is authoritative)

## Why two verifier checkouts are required

`verify-eval` intentionally fails closed when the verifier checkout does not match the generation bundle's project/Open-R1/dependency identity. B generation was produced at project commit `07ccc71968bedc25b1a8fd15aa0ee35a75e05389`; the eight Recipe A generation bundles were produced at `f17b4f607daa3bb03b08682bbbd841118d36c4af`. Both bind Open-R1 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563` and dependency lock `4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf`.

The operator therefore uses two detached, clean, local verifier worktrees:

- `/home/dzy/wp9d-verifier-b-07ccc719` at `07ccc719...`
- `/home/dzy/wp9d-verifier-a-f17b4f6` at `f17b4f607...`

This preserves the production identity check instead of weakening it. All nine runs still use the same eval400 dataset, eval config, Piston definition, seed and `workers=64` verification protocol.

## Execution topology

The script runs one bundle at a time to avoid over-subscribing the local Piston/CPU service. Order is B, Public 300/600/900/1200, then Hidden 300/600/900/1200. `verify-eval` retains its exact-prefix resume semantics. A completed run is safe to read back again; partial result rows are resumed rather than regenerated.

After each completed verification, `aggregate-eval --seed 42` writes the normal `summary.json` and `main_results.csv`. Existing complete aggregate artifacts are reused; a partial aggregate pair fails closed instead of being overwritten.

## Strict acceptance

Final PASS requires all nine evaluation runs to be `completed` with 400 ordered, unique results each; exact generation payload fields must match the frozen source rows; generation provenance, dataset/order/Piston/code identities must match; `verification_workers=64`; aggregate outputs must be finite and use 10,000 bootstrap resamples with seed 42; and no row may contain a Piston `sandbox_error` status or failure count.

A successful final line is:

```text
formal_postcheck=PASS bundles=9 records=3600 workers=64 sandbox_errors=0 aggregation=PASS
```

The deterministic result manifest is written to `/home/dzy/wp9d-eval400-verified/verification-manifest.json`. Operator status/log/evidence are under `/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C0/`. Prior status/evidence files are preserved before a retry; the append-only terminal log and exact-prefix verification outputs are retained.

## Manual commands

After this operator directory is committed, export the exact new checkpoint commit and exact `run.sh` SHA256 in the WP9-d worktree:

```bash
export WP9D_VERIFY_HANDOFF_COMMIT=<exact C0 operator commit>
export WP9D_VERIFY_SCRIPT_SHA256=<exact run.sh SHA256>
C0=ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C0
```

Run preflight first:

```bash
bash "$C0/run.sh" preflight
```

Only after preflight reports `WP9-d unified eval400 preflight PASS` run the formal control-plane verification manually (tmux is recommended):

```bash
bash "$C0/run.sh" verify
```

To follow progress from another 1660 Ti shell:

```bash
tail -F /home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C0/terminal.log
```

Do not run verification on a 4090 and do not regenerate any completion bundle for this gate.
