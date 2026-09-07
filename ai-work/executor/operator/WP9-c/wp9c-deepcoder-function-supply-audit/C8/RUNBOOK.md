# WP9-c C8 DeepCoder function-call supply audit

This checkpoint is an offline engineering-data supply audit only. It reuses the already cached pinned DeepCoder Preview snapshot and does not download data, generate tests, execute source solutions, run Piston, run calibration, run GRPO, or use RTX4090.

## Why C8 exists

C6 full-TACO >=8 contributed zero Exact-B survivors. C7 then audited TACO 1-7-test planning rows and found that almost all useful TACO-under8 rows overlap the corrected APPS-under8 baseline. The final C7 planning union is 2402: 1276 current-ready plus 1126 under8 planning rows. This is still 198 below the desired 2600 pre-Piston buffer and 398 below 2800. The current under8 union would need 999/1126 final successes to reach the exact 2275 external-new target, so entering generation now would leave too little attrition margin.

The project spec already lists DeepCoder Preview / PrimeIntellect-derived data as candidate supply. The exact pinned snapshot used by WP9-a is already local, so C8 measures its function-call supply before any expensive augmentation work.

## Frozen source identity

- dataset: `agentica-org/DeepCoder-Preview-Dataset`
- revision: the same full pinned commit used by `configs/data/refresh.yaml`
- dataset-card license: MIT, verified from the pinned snapshot
- configs, in deterministic priority order:
  1. `primeintellect/train` — 5 parquet shards, 16252 rows
  2. `taco/train` — 4 parquet shards, 7436 rows
- all nine local parquet files are frozen by exact Hugging Face blob SHA256 and byte size in the C8 config; the manual audit rehashes the actual file contents against those SHA256 values before scanning
- DeepCoder `primeintellect` has priority over DeepCoder `taco`; the latter is treated as a derived-source overlap/increment check, not as automatically independent provenance
- upstream-derived provenance still requires review before formal admission

## Frozen selection semantics

- corrected current-ready remains first priority
- DeepCoder natural `>=8` function-call candidates are deduplicated first and then screened with production `canonicalize_refresh_candidate(seed=42) -> build_code_prompt` plus Exact Formal-B `<=2048`
- DeepCoder `1-7` candidates are next priority:
  - 4-7-test rows use the existing pre-augmentation prompt projection and must byte-crosscheck production canonicalization
  - 1-3-test rows use the explicitly non-formal proxy
  - all under8 formal context-eligible counts remain null until final augmentation and Exact-B recheck
- the completed C7 TACO/APPS under8 union is then re-deduplicated against retained DeepCoder ready/under8 candidates
- token 5-gram / Jaccard 0.90 dedup remains frozen
- no threshold relaxation

## Manual run

Do not source `~/.bashrc`; no network is needed.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-deepcoder-function-supply-audit/C8/run.sh
```

This is a long local scan of roughly 23.7k rows / 2 GB of cached parquet and must be run manually rather than through the control-plane connector. The runner verifies the final report digest and every emitted JSONL artifact digest before declaring success.

Expected atomic outputs:

- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/report.json`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/report.sha256`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/deepcoder_ready_candidates.jsonl`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/deepcoder_under8_candidates.jsonl`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/ready_context.jsonl`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/under8_context.jsonl`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/ready_dedup_decisions.jsonl`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/under8_dedup_decisions.jsonl`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8/c7_under8_after_deepcoder_decisions.jsonl`
- `/home/dzy/wp9c-deepcoder-function-supply-audit-C8.log`

When it finishes, reply only `执行完毕`. The control plane will read the artifacts directly, verify all digests, and determine the new ready/under8 union, buffer status, and whether a separate augmentation/provenance checkpoint is justified.

## Frozen boundaries

Even if C8 reaches the desired planning buffer, do not automatically start generation or Piston. DeepCoder upstream provenance review, reference-solution execution policy, under8 augmentation, final context recheck, and project Piston validation remain separate audited gates. Calibration/retry, GRPO, and RTX4090 remain frozen.
