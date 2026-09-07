# WP9-c C7 TACO-under8 planning supply audit

This checkpoint is a static engineering-data audit only. It reuses the already pinned nine-shard BAAI/TACO download from C6 and scans function-call rows with 1-7 unique tests. It does not generate tests, execute source solutions, run Piston, run calibration, run GRPO, or use RTX4090.

## Why this checkpoint exists

C6 full-TACO >=8 audit completed successfully but contributed zero Exact-B context survivors: 715 structural >=8 direct-signature rows reduced to 2 after frozen dedup, and both retained prompts exceeded the 2048-token Formal-B cap. Corrected supply therefore remains 1276 current-ready plus 1119 APPS-under8 planning/proxy rows = 2395 zero-attrition planning candidates. That is 120 above the exact 2275 external-new target but 205 below the desired 2600 pre-Piston buffer. Augmenting only the existing APPS-under8 rows cannot increase the planning candidate count above 2395.

C7 therefore measures whether TACO 1-7-test rows can add genuinely new planning candidates before any expensive augmentation work.

## Frozen policy

- active pool exact: 2500
- SFT reuse exact: 225
- external-new exact: 2275
- desired pre-Piston external-new buffer: 2600-2800
- seed: 42
- source: BAAI/TACO pinned revision from C6; reuse the existing download manifest and nine local shard hashes
- TACO-under8 candidate: native function-call row, 1-7 unique normalized tests, nonempty accepted source solutions, conservative direct top-level function signature
- dedup priority: corrected current-ready -> TACO-under8 planning -> corrected APPS-under8 planning
- dedup thresholds remain token 5-gram / Jaccard 0.90; no threshold relaxation
- pre-augmentation context protocol is the same C6 under8 protocol: 4-7-test rows byte-crosscheck production canonicalization; 1-3-test rows use the explicit non-formal proxy
- all under8 formal context-eligible counts remain null until final augmentation and Exact-B recheck
- mixed TACO upstream provenance must be preserved and reviewed before any formal admission

## Manual run

Do not rerun the network download. Do not source `~/.bashrc`.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-taco-under8-supply-audit/C7/run.sh
```

The runner forces Hugging Face/Transformers offline mode, verifies checkpoint SHA bindings and the C6 baseline artifacts, then writes atomically to:

- `/home/dzy/wp9c-taco-under8-supply-audit-C7/report.json`
- `/home/dzy/wp9c-taco-under8-supply-audit-C7/report.sha256`
- `/home/dzy/wp9c-taco-under8-supply-audit-C7/taco_under8_candidates.jsonl`
- `/home/dzy/wp9c-taco-under8-supply-audit-C7/taco_under8_context.jsonl`
- `/home/dzy/wp9c-taco-under8-supply-audit-C7/taco_under8_dedup_decisions.jsonl`
- `/home/dzy/wp9c-taco-under8-supply-audit-C7/apps_under8_after_taco_decisions.jsonl`
- `/home/dzy/wp9c-taco-under8-supply-audit-C7.log`

When the command finishes, reply only `执行完毕`. The control plane will read the artifacts directly and decide whether the union reaches the 2600/2800 planning buffer and what augmentation checkpoint, if any, should follow.

## Frozen boundaries

Even if C7 finds enough planning supply, do not start generation or Piston automatically. TACO provenance/license review, augmentation policy, reference-solution transformation, final context recheck, and Piston validation remain separate audited gates. Calibration/retry, GRPO, and RTX4090 remain frozen.
