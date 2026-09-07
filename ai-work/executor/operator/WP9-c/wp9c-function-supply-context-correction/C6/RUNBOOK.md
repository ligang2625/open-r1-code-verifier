# WP9-c C6 aggregate context-correction runbook

This is an append-only correction audit for the historical WP9-c function-supply aggregate. It does **not** overwrite `/home/dzy/wp9c-function-supply-aggregate-audit-C0`, execute candidate code/tests, generate tests, run Piston, run calibration, or start RTX4090 work.

## Why this correction exists

The historical aggregate report is preserved with its published SHA256. Review of the implementation found that its new-candidate `_context_filter` tokenized `candidate.prompt` directly. Formal calibration instead builds the fixed visible-only code prompt with `build_code_prompt` / `build_code_prompt_from_fields` (problem statement + function signature + visible examples + wrapper) before applying the Formal-B chat template/tokenizer.

A read-only cross-check on the 559 canonical incumbent inputs proved the distinction is material to the gate implementation: raw problem prompts retain 558/559 at <=2048, while the formal prompt projection retains exactly 554/559 and reproduces the historical exact-context report's mean/max token counts. Therefore the aggregate 1278-ready / 1126-under8 context-qualified counts require correction evidence rather than silent reuse.

## What the correction freezes

- seed 42;
- the published aggregate report and its sibling digest file;
- the same formal SFT/validation/project-test/HumanEvalPlus exclusion identities;
- the same ready candidate dedup decisions; any change there fails closed;
- corrected ready context protocol = `build_code_prompt_v1` followed by the cached Formal-B tokenizer/chat template, max prompt tokens 2048;
- existing 654 incumbents remain the already established exact-B incumbents;
- APPS-under8 is re-deduplicated after corrected ready context survivors because priority remains `incumbent/current-ready -> new ready -> under8`;
- under8 context remains pre-augmentation planning evidence only and must be rechecked after final augmented tests; the report deliberately leaves `under8_formal_context_eligible_count` null and reports only a pre-augmentation planning/proxy pass count;
- for APPS-under8 rows with 4-7 existing tests, the planning prompt is byte-checked against production `canonicalize_refresh_candidate(seed=42) -> build_code_prompt`; for 1-3-test rows, where production canonicalization intentionally refuses to construct invalid non-empty visible/hidden layers, the audit uses the same deterministic WP9-a shuffle and up to two existing visible tests with `build_code_prompt_from_fields` as an explicit proxy. This proxy is not a lower/upper bound on the final augmented prompt and is never formal eligibility evidence.

## Preserved failed attempt

The first manual C6 execution reached an APPS-under8 row with three tests and failed because the correction script incorrectly called the production canonicalizer for every 1-7-test planning row. Production correctly requires at least four tests before it can form non-empty visible/train-hidden/eval-hidden layers. The failure happened before atomic publication: `/home/dzy/wp9c-function-supply-context-correction-C6` was not created. The failed log `/home/dzy/wp9c-function-supply-context-correction-C6.log` is preserved and must not be overwritten or deleted. This runner revision writes a new `C6-r1` output/log pair.

## Manual offline execution

Run from the WP9-c worktree. Do **not** source `~/.bashrc`; this operator is offline and forces Hugging Face/Transformers offline mode.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-function-supply-context-correction/C6/run.sh
```

Expected outputs:

- `/home/dzy/wp9c-function-supply-context-correction-C6-r1/report.json`
- `/home/dzy/wp9c-function-supply-context-correction-C6-r1/report.sha256`
- `/home/dzy/wp9c-function-supply-context-correction-C6-r1/context/ready_new.jsonl`
- `/home/dzy/wp9c-function-supply-context-correction-C6-r1/context/under8.jsonl`
- `/home/dzy/wp9c-function-supply-context-correction-C6-r1/decisions/under8.jsonl`
- `/home/dzy/wp9c-function-supply-context-correction-C6-r1.log`

When the command finishes, reply only `执行完毕`. The control plane will read the report directly, determine the corrected exact-ready count plus the under8 pre-augmentation planning/proxy count (without treating under8 as formal context eligibility), and then re-freeze the full-TACO audit against the corrected baseline.

## Boundary

Until this correction report is reviewed, the full-TACO C6 checkpoint is blocked. Old calibration retry, fresh calibration generation/scoring, APPS test generation, Piston, GRPO, and RTX4090 remain frozen.
