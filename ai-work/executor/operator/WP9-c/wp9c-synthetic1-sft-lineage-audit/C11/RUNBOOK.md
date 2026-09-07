# WP9-c C11 — SYNTHETIC-1 SFT response-lineage audit

> **PAUSED BY USER (2026-09-04): do not run the download or audit commands below.** The pre-pause prepared checkpoint is retained as historical evidence. This gate may be reopened only by a later explicit audited provenance-only decision; it must never add candidate supply.

## Purpose

C10 completed the full raw Open-R1/PrimeIntellect Python scan but recovered 0/541 DeepCoder-PrimeIntellect rows under the frozen `(normalized problem, exact solution hash)` key. That strict result remains immutable. A follow-up audit established that C8 hashes the DeepCoder `solutions` list while raw VCP exposes a separate `gold_standard_solution`; no upstream contract establishes those two solution fields as byte-equivalent lineage identifiers.

C11 therefore tests a narrower and more direct response-level lineage hypothesis. It uses `PrimeIntellect/SYNTHETIC-1-SFT-Data` only as a provenance index to ask whether each frozen DeepCoder-PrimeIntellect `problem + accepted solution` pair can be linked to one SYNTHETIC-1 `problem_id` through an exact user-prompt and exact extracted-response-code match.

C11 **does not add supply**. The effective supply baseline remains exactly `1276 ready + 1229 under8 planning = 2505`; the desired 2600/2800 pre-Piston buffer remains unmet by 95/295.

## Frozen source

- dataset: `PrimeIntellect/SYNTHETIC-1-SFT-Data`
- revision: `e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8`
- config/split: `default/train`
- files: `data/train-00000-of-00017.parquet` through `data/train-00016-of-00017.parquet`
- expected rows: 894,086
- expected parquet shards: 17
- expected download size: roughly 3.64 GB
- dataset-card license: Apache-2.0
- required task type: `verifiable_code`
- use class: `provenance_index_only`

The upstream dataset card states that the algorithmic coding component uses `PrimeIntellect/verifiable-coding-problems` as its task dataset. C11 still does not treat the SFT dataset's Apache-2.0 declaration as sufficient upstream legal adjudication for the underlying problem sources.

## Score-isolation boundary

`SYNTHETIC-1-SFT-Data` is a score-filtered derivative and contains a `score` column. C11 must never use that score for source selection, candidate ordering, supply, or lineage matching.

The audit validates that the parquet schema contains `score`, but its scan batches request only:

- `response_id`
- `problem_id`
- `task_type`
- `messages`

The `score` value is therefore never loaded into the matching loop. Any C11 match is provenance evidence only and contributes **0** incremental supply by protocol.

## Matching contract

Targets are exactly the 541 `deepcoder-primeintellect` rows in the digest-bound C8 `deepcoder_under8_candidates.jsonl` artifact.

For every target:

1. Normalize the DeepCoder problem with the project `normalize_text` contract.
2. Run the shared deterministic `extract_python_code()` parser on each accepted DeepCoder source solution and retain the exact bytes of the selected final Python fenced block. No target-function-name requirement is imposed because C11 is testing lineage identity, not implementation correctness; a preflight confirmed 541/541 frozen targets have an extractable final Python block under this contract.
3. Scan only `task_type=verifiable_code` SFT rows.
4. Require exact normalized user-prompt equality.
5. Extract the final Python block from the assistant response using the same shared parser.
6. Require exact extracted-code bytes; no fuzzy prompt or code matching is allowed.
7. Group exact response hits by upstream `problem_id`.

A target is `unique_problem_id` only if all exact response hits resolve to exactly one problem ID. Multiple response IDs for that same problem ID are allowed and reported separately. Hits resolving to multiple problem IDs are ambiguous. Prompt-only hits are diagnostic and never count as lineage admission.

## Frozen boundaries

C11 is engineering provenance evidence only. It must not:

- use SYNTHETIC-1 score values for matching, selection, or supply;
- add or replace any supply candidate;
- execute source solutions or testcase payloads;
- generate tests;
- run Piston;
- run calibration or retry calibration;
- run GRPO;
- use the RTX 4090 or any GPU gate;
- relax exact/fuzzy/dedup/context thresholds.

Even a unique C11 lineage match is not formal admission. A matched `problem_id` must still be rejoined to raw VCP source URL/upstream terms, followed later by the separately audited reference-solution execution, augmentation, final Exact-B context and Piston gates. Unmatched or ambiguous DeepCoder rows remain excluded from formal admission/augmentation.

## Step 1 — manual pinned download

This is a multi-GB network download and must be run manually rather than through the control-plane connector.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/01-download-sft-lineage.sh
```

The runner fails closed on the exact revision, exact 17-shard filename set and exact 894,086 total rows. It hashes every parquet shard and atomically publishes:

- `/home/dzy/wp9c-synthetic1-sft-lineage-download-C11/manifest.json`
- `/home/dzy/wp9c-synthetic1-sft-lineage-download-C11/manifest.sha256`
- `/home/dzy/wp9c-synthetic1-sft-lineage-download-C11.log`

## Step 2 — manual offline lineage audit

Run only after Step 1 succeeds and the manifest is reviewed.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-synthetic1-sft-lineage-audit/C11/02-audit-sft-lineage.sh
```

Do **not** source `~/.bashrc` for Step 2. The audit is offline, re-hashes every downloaded shard, validates exact source schema and the frozen C8/C10 baselines, scans only the four non-score columns, and atomically publishes:

- `/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11/report.json`
- `/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11/report.sha256`
- `/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11/target_lineage.jsonl`
- `/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11/response_hits.jsonl`
- `/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11/prompt_diagnostics.jsonl`
- `/home/dzy/wp9c-synthetic1-sft-lineage-audit-C11.log`

## Decision after C11

- If all or nearly all 541 targets resolve uniquely to one `problem_id`, the next gate is a **raw-VCP provenance/legal rejoin** using those problem IDs. Generation/Piston/calibration remain frozen until that rejoin closes.
- If a material subset remains unmatched, do not relax prompt/code matching. Investigate the exact DeepCoder transformation lineage or direct SYNTHETIC-1 raw response metadata for only those rows.
- If any rows are ambiguous across multiple problem IDs, keep them excluded unless a stronger direct identifier resolves the ambiguity.

C11 never changes the reported 2505 planning supply regardless of its match rate.
