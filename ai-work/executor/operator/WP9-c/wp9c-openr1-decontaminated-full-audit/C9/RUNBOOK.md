# WP9-c C9 Open-R1 decontaminated full provenance/supply audit

C9 is an engineering-data audit only. It does not execute source solutions or test payloads, generate tests, run Piston, run calibration, run GRPO, or use RTX4090.

## Why C9 exists

C8 completed with 1276 corrected ready candidates and a deduplicated under8 planning union of 1229, for 2505 zero-attrition planning candidates. This is +103 versus C7 but still 95 below the desired 2600 pre-Piston buffer and 295 below 2800. Exact 2275 external-new would require 999/1229 under8 rows to survive later gates (about 81.29%).

The final C8 under8 union contains 542 DeepCoder rows and 687 C7 rows. Of the C7 survivors, 602 are TACO and 85 are APPS. The 602 TACO survivors preserve upstream source and URL hashes (599 Codewars, 1 LeetCode, 2 HackerRank). The 541 DeepCoder `primeintellect` survivors do not preserve per-row source URL/provenance in the DeepCoder projection.

A historical audit already pinned the non-reward-tested `open-r1/verifiable-coding-problems-python_decontaminated` projection at revision `0d251c23dcff7f7e525e7a4e184be5232bf63db6`. Only shards 0 and 5 were sampled then. C9 completes all six shards for two purposes:

1. Recover per-row `source`, `in_source_id`, and `problem_url` metadata for DeepCoder-PrimeIntellect planning rows using a strict normalized-problem + exact gold-solution hash match.
2. Measure any genuinely new raw function-call supply after the entire frozen C8 union. Raw Open-R1 rows have lower priority and cannot replace or double-count C8 candidates.

The source remains `license_status=unresolved_upstream`; C9 cannot make it formally admissible by itself.

## Frozen source

- dataset: `open-r1/verifiable-coding-problems-python_decontaminated`
- revision: `0d251c23dcff7f7e525e7a4e184be5232bf63db6`
- split: train
- expected rows: 27,839
- expected shards: 6 (`data/train-*-of-00006.parquet`)
- reward-tested derivative is not used
- historical sample report remains immutable evidence

## Step 1 — networked pinned download

This completes the four shards that were not present in the historical two-shard sample. Existing cached shards should be reused automatically.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-openr1-decontaminated-full-audit/C9/01-download-full-source.sh
```

The download runner pins the exact revision, requires exactly six shards / 27,839 rows, hashes every parquet file, and atomically writes:

- `/home/dzy/wp9c-openr1-decontaminated-full-download-C9/manifest.json`
- `/home/dzy/wp9c-openr1-decontaminated-full-download-C9/manifest.sha256`

## Step 2 — offline static audit

After Step 1 succeeds, use a fresh shell if convenient and do **not** source `~/.bashrc`:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-openr1-decontaminated-full-audit/C9/02-audit-full-source.sh
```

The audit forces Hugging Face/Transformers offline mode, rehashes all six shard files against the download manifest, reconstructs the frozen C8 union, performs provenance recovery, and then applies the frozen dedup/context policies to only genuinely new raw function-call candidates.

Expected atomic outputs:

- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/report.json`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/report.sha256`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/deepcoder_provenance_recovery.jsonl`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/raw_candidates.jsonl`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/dedup_decisions.jsonl`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/ready_context.jsonl`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/under8_context.jsonl`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/incremental_ready_candidates.jsonl`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9/incremental_under8_candidates.jsonl`
- `/home/dzy/wp9c-openr1-decontaminated-full-audit-C9.log`

The runner verifies the report digest and every emitted JSONL artifact digest before declaring success.

## Frozen boundaries

- no historical public/hidden reward outcomes are used for selection
- no threshold relaxation
- raw Open-R1 candidates remain below the frozen C8 union in priority
- natural >=8 new candidates use production Exact-B <=2048
- 4–7-test new candidates use the production-crosschecked pre-augmentation projection
- 1–3-test new candidates use the explicit non-formal proxy
- all under8 formal context counts remain null before final augmentation recheck
- unresolved source terms/provenance block formal admission
- generation, Piston, calibration/retry, GRPO, and RTX4090 remain frozen

After both steps finish, reply only `执行完毕`. The control plane will read the C9 artifacts directly and decide whether supply/provenance are sufficient to open an augmentation/provenance gate.
