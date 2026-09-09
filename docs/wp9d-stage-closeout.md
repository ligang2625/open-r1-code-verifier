# WP9-d Stage Closeout — Verifier-Guided GRPO Recipe A

**Closeout date:** 2026-09-09  
**Status:** user-directed research closeout  
**Research scope:** all predeclared WP9-d Recipe A training, checkpoint generation, verification, scoring, and stability-adjudication stages are complete.

## 1. Final stage decision

WP9-d is closed with the following scientific result:

```text
Selected checkpoint: Recipe A / Hidden reward / step1200
Canonical eval400 Eval-Hidden Pass@1: 44.75% = 179/400
Refreshed B baseline: 37.75% = 151/400
Absolute delta: +7.00 percentage points
Paired bootstrap 95% CI: [+2.74, +11.50] percentage points
```

The paired Public endpoint is `44.25% = 177/400`, only `0.50 pp` below Hidden1200. The paired 95% CI for Hidden1200 − Public1200 is `[-3.00, +4.00] pp`. Therefore WP9-d supports the claim that Recipe A GRPO improves canonical eval400 performance, but does not establish a meaningful Hidden-reward advantage over Public reward.

The complete research report is:

- `report/wp9d_recipe_a_research_report.md`

## 2. Final evaluation adjudication

The final scientific scoring set is frozen as:

- B and seven clean Recipe A checkpoint results from `/home/dzy/wp9d-eval400-verified/evaluation`;
- Hidden300 from the full-400 C1 verification at `/home/dzy/wp9d-eval400-repair-c1/evaluation/wp9d-A-hidden-step300-eval400-b4-p1-seed42`.

C0 and C2 remain immutable failed evidence:

- C0 contained two Piston `sandbox_error` rows in Hidden300;
- C1 reran the entire Hidden300 400-problem verification and produced zero sandbox errors;
- C1 changed `apps-4392` from C0 timeout to passed;
- C2 independently reproduced the C1 `apps-4392=passed` result and otherwise matched C1 semantics on all non-infrastructure rows, but introduced an independent Piston `sandbox_error` at `taco-1609`;
- by explicit closeout decision, C2 is stability evidence only and is not substituted into the final scoring set.

No failed row is patched across runs, no historical operator evidence is overwritten, and no further full-400 verification rerun is authorized inside WP9-d.

## 3. Frozen algorithm identity

Formal Recipe A:

- parent: `B-sft-formal-seed42`;
- base: `Qwen/Qwen2.5-Coder-1.5B-Instruct` revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`;
- active pool: 1,354 problems, produced by C29 static reward-informativeness calibration from 1,602 candidates: `1123 dual_informative + 88 public_only + 143 hidden_only`, with all `248 dual_uninformative` problems removed and no backfill;
- two arms: Public=`visible_tests`, Hidden=`train_hidden_tests`;
- eval-hidden tests never enter GRPO reward;
- `num_generations=8`;
- `max_steps=1200`;
- LR `5e-6`, `constant_with_warmup`, warmup ratio `0.05`;
- `beta=0.01`;
- sampling temperature `0.8`, top-p `0.95`;
- train batch `1`, gradient accumulation `8`;
- bf16, non-reentrant gradient checkpointing;
- fresh LoRA q/k/v/o, rank 16, alpha 32, dropout 0.05;
- colocated vLLM, memory fraction 0.4;
- reward verification workers 8;
- formal checkpoint save cadence 50;
- measured checkpoints 300/600/900/1200;
- seed 42.

Reward core:

```text
total_reward
  = selected-test pass rate
  + 0.1 executable bonus
  - 0.2 timeout penalty
  - 0.1 parse/format penalty
```

Infrastructure failures are not ordinary reward outcomes and remain separately classified.

## 4. Frozen benchmark identity

Canonical eval400:

- dataset SHA256: `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`;
- ordered IDs SHA256: `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`;
- eval config SHA256: `3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3`;
- Piston SHA256: `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`;
- deterministic generation, max new tokens 512, float16;
- logical generation batch 4;
- verification workers 64 on the 1660Ti control plane;
- seed 42.

Because eval400 is reused for checkpoint/model selection, future reporting must call this an **eval400-selected benchmark improvement**, not an untouched held-out generalization estimate.

## 5. Stage-level conclusions

1. The WP9-c diagnosis was directionally correct: increasing coverage and sustaining LR produces meaningful policy movement and benchmark improvement.
2. Recipe A improves Eval-Hidden Pass@1 from `37.75%` to as high as `44.75%` without obvious parse/runtime collapse.
3. The main capability gain is established by approximately step 900; 900→1200 adds only `+0.75 pp` in each arm, indicating an emerging plateau.
4. Hidden reward is not shown to be superior to Public reward; the final difference is only `+0.50 pp` with a paired CI spanning zero.
5. Static variance/informativeness filtering has already been completed by C29; the next research stage should instead prioritize verifier reward geometry / credit-assignment ablations and KL-controlled GRPO update geometry (fixed-beta sweep followed by adaptive KL control), rather than repeating problem filtering or simply extending the same training schedule.

## 6. Provenance anchors

Training handoff:

- commit `7b5e097b448b6c42fb9faf1f27711a65e00d2075`;
- operator SHA256 `64cd1d6accf7c4a79cbcaa825540bea43d86cf43ec703dd98a5209efdd9867b4`.

Eval-generation handoff:

- commit `f17b4f607daa3bb03b08682bbbd841118d36c4af`;
- script SHA256 `59bed201d6f57025fcbfb22a0afed3a88298fabc04029af71ac23413f224aae4`.

Verification/adjudication checkpoints:

- C0 operator commit `8717f6032c27117facbd996b7bce3ba8ec328143`;
- C1 operator commit `8f54a0873c34a75c8140e3f0ddad9d1ff3f6291c`;
- C2 operator commit `514ee522c666dc3985ca691ac77e328e8c518376`.

Key evidence hashes:

- C1 Hidden300 results `60883c2b8a25c13ac6d92229fab9a74edbac95fc48241f07d48dd073bd82772e`;
- C1 Hidden300 summary `9bebd5a148c4c6a790b4c2d630d2dc3017f5d5a0b9b944082913e238b454bf28`;
- C2 Hidden300 results `6340a5612e6a86ed8e0f132a6c0bbc9cc59ee5c1d92e86429162bb997417f1cb`;
- C0 evidence `92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1`;
- C1 evidence `778b18c4f4e797598159609f79ca6444747347a48cc91feb5d0d451720fc6852`;
- C2 evidence `9e2b454c550f88ffd6ec845f9c998e8acaf1cab13b52beeb173c83e0d72df755`.

## 7. Routing after closeout

WP9-d is closed. No further Recipe A reruns, retry-only scoring passes, or checkpoint sweeps should be added under this stage.

Any new work on reward ablations, beta/KL tuning, group size, mixed reward, LoRA capacity, external benchmarks, or a new optimization recipe is a **new research-stage identity** and must start from the integrated closeout state rather than modifying WP9-d historical evidence.
