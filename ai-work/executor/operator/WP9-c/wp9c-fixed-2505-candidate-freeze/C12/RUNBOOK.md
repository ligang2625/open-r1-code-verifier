# WP9-c C12 — fixed 2505 candidate-universe freeze

This gate implements the user-directed stop to source expansion. It is a short control-plane audit over already-published C6/C7/C8/C10 evidence only.

It MUST NOT download or discover sources, rescan raw source parquet, execute source solutions/tests, generate tests, run Piston/calibration/GRPO, use GPU, or relax any threshold.

The output is exactly one evidence-bound planning manifest:

- ready = 1276;
- under8 = 1229;
- total = 2505;
- under8 formal context eligibility remains null;
- 541 `deepcoder-primeintellect` rows retain an explicit unresolved-provenance formal-admission blocker;
- no row is formal-admitted by C12.

The audit binds the published context-correction, C7, C8 and C10 report digests, verifies all directly consumed artifact digests, verifies C11 is paused, and fails on duplicate candidate IDs or duplicate binding fingerprints.

Short local execution:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-fixed-2505-candidate-freeze/C12/run.sh
```

Expected final output: `/home/dzy/wp9c-fixed-2505-candidate-freeze-C12-r1/{candidates.jsonl,report.json,report.sha256}`. The earlier `/home/dzy/wp9c-fixed-2505-candidate-freeze-C12` successful control-plane attempt is preserved and not overwritten; `C12-r1` is the final digest-bound publication after static-format/type verification.

After C12, the only allowed expansion-like work is **not source expansion**: a separate audited test-augmentation gate may operate on these same frozen 1229 under8 IDs. C11 remains paused unless explicitly reopened as provenance-only work with incremental candidate supply fixed at zero.
