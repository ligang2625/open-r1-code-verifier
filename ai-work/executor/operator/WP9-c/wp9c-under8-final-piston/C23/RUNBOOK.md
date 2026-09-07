# WP9-c C23 — under8 final formal Piston

C22 is closed with 572/572 final Exact-B context passers. C23 is the only current manual execution gate.

## Frozen input

Exactly 572 candidates:

- BAAI/TACO: 513
- codeparrot/apps: 58
- deepcoder-taco: 1

Every job contains exactly 8 final frozen tests and exactly the two C20/C21 qualified oracle solutions.

Final Piston jobs SHA256:

`2531e7dd8ac464686526283f78e7f9560c5e9c29bcc4fc559abd3c9003689339`

## Classification contract

Both oracle members are always executed against all final frozen tests with project Piston.

- `formal_pass`: both frozen qualified oracles pass all 8 tests;
- `formal_fail`: fewer than two oracles pass all 8 tests and neither oracle has structured infrastructure failure;
- `infrastructure_blocked`: fewer than two oracles pass and at least one oracle execution has structured infrastructure failure.

A correctness failure is dropped without backfill. Infrastructure-blocked rows are not correctness failures. Correctness retry is prohibited; only the frozen safe pre-execution Piston transport retries are allowed.

## Manual command

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-under8-final-piston/C23/01-run-under8-final-piston.sh
```

The runner validates exact Python 3.10.0 Piston before candidate execution and is candidate-checkpoint resumable. If interrupted, rerun the exact same command.

## After execution

Reply `执行完毕`. The control plane must verify the report sidecar, all 572 job SHA bindings, both-oracle classification, pass/fail/infrastructure manifests, checkpoint digest, and log before final reduced-pool assembly / informativeness accounting is opened.
