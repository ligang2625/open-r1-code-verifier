# WP9-c C16 — offline exact response lineage + raw-VCP rejoin — CLOSED

C16 completed and was independently verified by the control plane. It must not be rerun.

## Verified result

The audit scanned the already-verified pinned `PrimeIntellect/SYNTHETIC-1-SFT-Data` provenance index and the already-local C10 raw-VCP snapshot without using SFT `score` values and without executing source solutions.

- exact DeepCoder-PrimeIntellect targets: 541
- SFT rows scanned: 894086
- raw-VCP rows scanned: 35735
- exact normalized-prompt source hits: 0
- exact response-code hits: 0
- unique `problem_id` lineage: 0
- ambiguous `problem_id` lineage: 0
- unmatched targets: 541
- raw-VCP rejoin rows: 0
- static second-oracle candidates: 0
- mathematically necessary static candidates before later attrition: at least 311
- candidate supply increment: 0
- source-solution execution: not run
- test generation: not run
- Piston: not run
- calibration / GRPO / GPU: not run

Verified report SHA256:

`0004c0cd04550b03765db39bad53d8358baa4179525f70d3b7ca1fa68ee4458e`

Verified log SHA256:

`0004c0cd04550b03765db39bad53d8358baa4179525f70d3b7ca1fa68ee4458e`

Artifact SHA256 values:

- `target_lineage.jsonl`: `abf02efaba0d79c5e700f2ad92904e9b7a78f3e8aa0d040a025f31cb32933291`
- `response_hits.jsonl`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `prompt_diagnostics.jsonl`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `raw_vcp_rejoin.jsonl`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `second_oracle_candidates.jsonl`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

Completed checkpoint:

`ai-work/executor/operator/WP9-c/wp9c-synthetic1-response-lineage-rejoin/C16/checkpoint.json`

Checkpoint status is `completed_no_exact_lineage`.

## Decision boundary

C17 source-solution transformation / project-Piston qualification is **not authorized**: C16 recovered zero rejoined second solutions, so there is nothing for C17 to qualify.

Under the frozen fixed-2505 universe, exact external-new 2275 requires at least 311 DeepCoder-PrimeIntellect successes even if every ready row and every non-PrimeIntellect under8 row succeeds. With the current frozen exact lineage contract yielding 0/541, the route is statically short by at least 311 before any Piston or other attrition.

This result proves that the frozen exact normalized-prompt + exact shared-extractor-code response-lineage contract does not recover these rows. It does **not** prove that no other deterministic provenance-only identity chain could exist. Any alternative must be a separately approved audited protocol based on stronger deterministic identity evidence; fuzzy matching, single-oracle consensus, threshold relaxation, or source expansion remain prohibited unless the user explicitly changes the protocol.
