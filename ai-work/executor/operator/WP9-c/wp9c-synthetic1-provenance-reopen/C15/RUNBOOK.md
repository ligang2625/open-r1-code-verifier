# WP9-c C15 — provenance-only SYNTHETIC-1 download — CLOSED

C15 is completed and must **not** be rerun. Historical C11 remains `paused_by_user`; C15 never reactivated it and added zero candidate supply.

## Verified completion

The manual pinned `PrimeIntellect/SYNTHETIC-1-SFT-Data@e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8` provenance-index download was verified by the control plane:

- 17/17 exact parquet shards;
- 894086 total rows;
- 3638559349 total bytes;
- manifest SHA256 `b910233e8adf693834f122de74db440bcbd64b562f5fe24cec800c2b62210858`;
- download log SHA256 `aa545d2a625160c1070bd561d1cf7ea4be82b53b102528c6d937abc951cd1117`;
- all shard sizes, SHA256 values, and parquet row counts revalidated;
- incremental candidate supply remained 0;
- response-lineage scanning, source-solution execution, Piston, generation, calibration, GRPO, and GPU work were not run during C15.

The completed checkpoint is:

`ai-work/executor/operator/WP9-c/wp9c-synthetic1-provenance-reopen/C15/checkpoint.json`

## Next gate

The current gate is C16:

`ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/C16/RUNBOOK.md`

C16 is the manual offline exact response-lineage + exact `problem_id` raw-VCP rejoin audit. Use only the C16 runner; the C15 download runner is fail-closed because the C15 checkpoint is no longer `awaiting_operator`.
