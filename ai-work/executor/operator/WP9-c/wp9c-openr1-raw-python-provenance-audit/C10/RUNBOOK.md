# WP9-c C10 Open-R1 raw Python provenance/supply audit

C10 is an engineering-data audit only. It does not execute source solutions or testcase payloads, generate tests, run Piston, run calibration, run GRPO, or use RTX4090.

## Why C10 exists

C8 closed at 1276 corrected ready candidates plus 1229 under8 planning rows, for 2505 zero-attrition planning candidates. This remains 95 below the desired 2600 pre-Piston buffer and 295 below 2800; exact 2275 external-new still requires 999/1229 under8 rows to survive later gates (about 81.29%).

C9 completed the full non-reward-tested `open-r1/verifiable-coding-problems-python_decontaminated` snapshot. It scanned all 27,839 rows and found only 188 pure function-call rows, all TACO; all 188 were unparseable under the frozen positional-argument function-call contract, so C9 added zero supply. C9 also matched 0/541 DeepCoder-PrimeIntellect planning rows under the strict normalized-problem + exact-gold-solution protocol. That zero is consistent with the sources being different data families: the DeepCoder `primeintellect` projection is derived from PrimeIntellect SYNTHETIC-1, while the decontaminated Open-R1 projection is composed from APPS/CodeContests/Codeforces/TACO.

Open-R1 also publishes `open-r1/verifiable-coding-problems-python`, documented as the Python-only mirror of PrimeIntellect `verifiable-coding-problems`, with `metadata` and `verification_info` converted to dictionary form while the task data is otherwise unchanged. C10 audits this raw Python mirror directly. The mirror is not reward-tested, but its dataset-level license is not treated as sufficient for blanket formal admission; per-row upstream source/URL terms still require review.

C10 has two separate goals:

1. Recover per-row upstream provenance for the 541 retained DeepCoder-PrimeIntellect planning rows using normalized problem + exact accepted solution hash. Provenance recovery never adds supply by itself.
2. Measure any genuinely new raw function-call supply after the entire frozen C8 union. Raw mirror rows have lower priority and cannot replace/double-count C8 candidates.

## Frozen source

- dataset: `open-r1/verifiable-coding-problems-python`
- revision: `db558678436c3c1275212172746e1dd67a990059`
- split/config: `data/train-*-of-00011.parquet`
- expected rows: 35,735
- expected parquet shards: 11
- expected cache size is roughly 2.69 GB
- reward-tested/decontaminated-tested derivatives are excluded
- license status for this gate: `unresolved_upstream`

The download/audit runners fail closed if revision, shard count, row count, file SHA, schema, baseline, or protocol bindings drift.

The first C10 download attempt used the auto-generated parquet-converter commit `fd70d66a6ec418cb1c30d350ccbe08a4aec64862` and failed before publishing any manifest or audit output. The repaired gate pins the normal source-data commit `db558678436c3c1275212172746e1dd67a990059` instead. Hugging Face commit metadata shows that all 11 parquet LFS object SHA256 values and byte sizes are identical between those two commits; only the repository path/ref changes. No reported supply count or historical evidence is changed by this repair.

## Step 1 — networked pinned download

This is a long download and must be run manually rather than through the control-plane connector.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-openr1-raw-python-provenance-audit/C10/01-download-raw-python.sh
```

The runner pins the exact revision, requires exactly 11 parquet shards / 35,735 rows, hashes every parquet file, and atomically writes:

- `/home/dzy/wp9c-openr1-raw-python-download-C10/manifest.json`
- `/home/dzy/wp9c-openr1-raw-python-download-C10/manifest.sha256`
- `/home/dzy/wp9c-openr1-raw-python-download-C10-attempt2.log` (preserved on either success or failure)

## Step 2 — offline static audit

After Step 1 succeeds, use a fresh shell if convenient and do **not** source `~/.bashrc`:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-openr1-raw-python-provenance-audit/C10/02-audit-raw-python.sh
```

Step 2 forces Hugging Face/Transformers offline mode, rehashes all 11 shard contents against the manifest, reconstructs the 1229-row frozen C8 under8 union, targets exactly 541 DeepCoder-PrimeIntellect rows for provenance recovery, and applies frozen dedup/context policies to genuinely new raw function-call candidates only.

Expected atomic outputs:

- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/report.json`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/report.sha256`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/deepcoder_provenance_recovery.jsonl`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/raw_candidates.jsonl`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/dedup_decisions.jsonl`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/ready_context.jsonl`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/under8_context.jsonl`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/incremental_ready_candidates.jsonl`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10/incremental_under8_candidates.jsonl`
- `/home/dzy/wp9c-openr1-raw-python-provenance-audit-C10.log`

The audit runner verifies the final report digest and every emitted JSONL artifact digest before declaring success. It also verifies that unique + ambiguous + unmatched provenance results partition exactly the 541 DeepCoder-PrimeIntellect targets.

## Frozen boundaries

- no historical Public/Hidden reward outcome is used for source selection
- no threshold relaxation
- raw Python candidates remain below the frozen C8 union in priority
- natural >=8 new candidates use production Exact-B <=2048
- 4–7-test new candidates use the production-crosschecked pre-augmentation projection
- 1–3-test new candidates use the explicit non-formal proxy
- under8 formal context counts remain null until augmentation and final Exact-B recheck
- provenance recovery and supply admission are separate decisions
- unresolved upstream source terms block formal admission
- generation, Piston, calibration/retry, GRPO, and RTX4090 remain frozen

After both steps finish, reply only `执行完毕`. The control plane will read the manifest/report/artifacts directly and decide whether the recovered provenance and supply justify opening a separate provenance/augmentation gate.
