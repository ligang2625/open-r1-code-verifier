# PROJECT SPEC — WP9-d GRPO Optimization Amendment

**Status:** Active amendment v1.2
**Effective date:** 2026-09-07
**Applies to:** WP9-d and later GRPO-optimization stages derived from the completed WP9-c active1354 experiments
**Parent specifications:** `PROJECT_SPEC_Open-R1_CodeVerifier.md`, `PROJECT_SPEC_GRPO_Refresh.md`
**Stage closeout reference:** `docs/wp9c-stage-closeout.md`

This amendment is normative for WP9-d. It does not rewrite historical WP0–WP9-c evidence. When this amendment conflicts with the older WP9-d routing text in `PROJECT_SPEC_GRPO_Refresh.md` §17.4, **this amendment controls the new WP9-d scope**. All unchanged security, hidden-test isolation, artifact provenance, target-GPU/operator, reproducibility, and Public/Hidden fairness rules from the parent specifications remain in force.

---

# 1. Stage purpose

WP9-d is a **new optimization stage**, not a continuation of the closed WP9-c recipe identity.

The primary hypothesis to test is:

> The WP9-c GRPO recipe under-updated the policy because 300 optimizer steps covered only approximately 0.2216 epoch of active1354 while the cosine learning-rate schedule decayed the full `5e-6` budget to approximately zero within those 300 steps.

WP9-d therefore optimizes **coverage / scheduler / effective policy movement first**. It MUST NOT begin by simultaneously changing learning rate, beta, LoRA rank, sampling, reward definition, data pool, and training duration.

The stage must distinguish three questions:

1. **Can the existing reward signal produce sustained learning if given approximately one epoch of coverage and non-vanishing LR?**
2. **Is policy movement still too weak after fixing coverage/schedule?**
3. **Does the resulting policy improve the canonical eval400 benchmark without destabilizing executable code generation?**

By explicit user decision on 2026-09-07, **eval400 is the canonical benchmark for all subsequent WP9-d recipe selection, checkpoint selection, and performance evaluation**. No additional functional-development dataset is required.

Because eval400 has already been observed in WP9-c and will now be reused for tuning, WP9-d and later reports MUST describe its results as **eval400-selected / reused-benchmark evidence**, not as an untouched independent held-out generalization estimate.

---

# 2. Frozen starting state

Unless a later explicit amendment changes one item, every WP9-d candidate starts from the same frozen scientific state:

```yaml
wp9d_frozen_start:
  parent_sft: B-sft-formal-seed42
  model: Qwen/Qwen2.5-Coder-1.5B-Instruct
  model_revision: 2e1fd397ee46e1388853d2af2c993145b0f1098a
  seed: 42

  active_pool:
    problem_count: 1354
    exact_order_sha256: 401f854032095cb638637dcf2d1ec000b770cd2d4c78619331f0b13746618c14
    public_dataset_sha256: 558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c
    hidden_dataset_sha256: 9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec

  sampling:
    num_generations: 8
    temperature: 0.8
    top_p: 0.95
    max_prompt_length: 2048
    max_completion_length: 512

  optimizer_structure:
    per_device_train_batch_size: 1
    gradient_accumulation_steps: 8
    bf16: true

  peft:
    lora_r: 16
    lora_alpha: 32
    lora_dropout: 0.05

  reward:
    public: visible_tests_only
    hidden: train_hidden_tests_only

  parent_construction:
    semantics: base_A -> load_completed_B_read_only -> safe_merge_B -> fresh_GRPO_LoRA
```

The old WP9-c 300-step runs remain immutable historical controls and MUST NOT be resumed into WP9-d.

---

# 3. Canonical eval400 benchmark

WP9-d reuses the exact WP9-c eval400 definition as the single tuning/evaluation benchmark:

```yaml
wp9d_eval400:
  dataset_sha256: 770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae
  ordered_problem_ids_sha256: 2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9
  canonical_problems_sha256: d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6
  piston_config_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  eval_config_sha256: 3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3
  seed: 42
  generation_batch_size: 4
  verification_workers: 64
  primary_metric: eval_hidden_pass_at_1
  decode: deterministic_pass_at_1
```

Rules:

- the same 400 problem IDs/order MUST be used for every candidate/checkpoint;
- the same deterministic decode, seed, generation batch, verifier/runtime, and aggregation contract MUST be used unless a separately approved systems-only amendment proves exact output parity;
- B remains the fixed benchmark baseline;
- existing B/C/D results remain historical controls and are not regenerated unless required by a strict identity repair;
- eval400 results MAY be used directly to choose LR, beta, recipe, and checkpoint;
- per-problem outcomes MAY be inspected for diagnosis, but any subsequent change informed by them must be recorded as benchmark-guided tuning;
- all later scientific claims must disclose that eval400 was used for model selection and therefore is no longer an untouched held-out set.

---

# 4. First candidate: coverage/scheduler correction

The first WP9-d candidate is frozen as **Recipe A**:

```yaml
wp9d_recipe_A:
  num_generations: 8
  max_prompt_length: 2048
  max_completion_length: 512

  per_device_train_batch_size: 1
  gradient_accumulation_steps: 8
  learning_rate: 5.0e-6
  num_train_epochs: 1.0
  max_steps: 1200
  warmup_ratio: 0.05
  lr_scheduler_type: constant_with_warmup

  temperature: 0.8
  top_p: 0.95
  beta: 0.01

  bf16: true
  fp16: false
  gradient_checkpointing: true

  lora_r: 16
  lora_alpha: 32
  lora_dropout: 0.05

  logging_steps: 1
  save_steps: 100
  eval_steps: 300
  seed: 42
  min_cuda_memory_gb: 20.0

wp9d_recipe_A_operator_runtime:
  reward_verification_workers: 8
```

The strict GRPO config loader also requires the arm-specific fields `run_name`, `reward_mode`, `dataset_path`, and `piston_config`. The WP9-d plan/operator MUST bind those explicitly for Public and Hidden; they are not free tuning variables and must preserve the frozen active1354/Piston identities.

Rationale:

- `1200` steps correspond to approximately `0.89` epoch under the observed WP9-c trainer accounting, compared with approximately `0.22` epoch previously;
- LR remains at the previously accepted `5e-6` after warmup, so Recipe A isolates the **coverage/scheduler** hypothesis rather than simultaneously testing a larger step size;
- `beta=0.01`, sampling, LoRA capacity, batch structure, and reward definitions remain unchanged;
- with `per_device_train_batch_size=1` and `gradient_accumulation_steps=8`, the pinned single-GPU effective generation batch is `8` completion rows; with `num_generations=8`, this is exactly **one problem group of eight completions per optimizer step**. This mapping is what makes 1200 steps approximately 1200 active-problem groups and approximately 0.89 epoch;
- GRPO training reward verification remains at `8` workers for Recipe A, matching the completed WP9-c formal runs. Changing reward workers is a systems-only benchmark dimension, not part of the initial scientific recipe.

Recipe A is the default next experiment but **this specification does not authorize running it automatically**. A WP9-d plan/operator handoff must still be created and explicitly started under the normal stage workflow.

---

# 5. Checkpoint and measurement protocol

For Recipe A and every later recipe candidate:

- trainer metrics log every optimizer step;
- checkpoint save cadence: every `100` optimizer steps;
- mandatory eval400 measurement checkpoints for Recipe A: `300`, `600`, `900`, `1200`;
- each measured checkpoint uses the exact canonical eval400 contract from §3;
- Public and Hidden candidate arms, when both are run, must start independently from the same frozen B and use the same selected recipe/checkpoint schedule;
- no candidate may use another candidate's checkpoint as parent;
- generation runs on the 24GB worker; verification/aggregation returns to the GTX 1660 Ti/Piston control plane whenever practical.

Repeated eval400 evaluation is explicitly permitted for WP9-d tuning. Each result must retain exact checkpoint/recipe identity so later analysis can reconstruct the full tuning path rather than report only the winning checkpoint.

---

# 6. Metrics used to select or reject a recipe

## 6.1 Training diagnostics

Every candidate must report at least:

- trainer reward and reward std over time;
- all-correct / all-zero / mixed group fractions;
- zero-variance fraction;
- KL to the frozen reference policy over time;
- gradient norm;
- PPO clip-region statistics;
- completion length and max-length clipping fraction;
- learning rate;
- generated tokens and GPU-hours.

## 6.2 Canonical benchmark metrics

Primary selection metric:

- **eval400 Eval-Hidden Pass@1**.

Required secondary metrics:

- visible Pass@1;
- train-hidden Pass@1;
- average eval-hidden test pass rate;
- parse success / target-function-found rate;
- runtime-error rate;
- timeout rate;
- mean / p50 / p95 completion tokens;
- problem-paired delta versus B and, when useful, versus the prior candidate/checkpoint.

A candidate is not considered better merely because trainer reward rises. The benchmark must improve or provide a clear trade-off that is explicitly accepted.

## 6.3 KL interpretation bands

The following are **engineering diagnostic bands, not formal optimality claims**:

```yaml
wp9d_kl_diagnostics:
  likely_too_weak:
    mean_kl_below: 3.0e-4
    condition: no_eval400_improvement

  useful_search_region:
    mean_kl: 5.0e-4_to_5.0e-3

  caution:
    sustained_or_peak_kl_near_or_above: 1.0e-2
    interpretation: inspect eval400 executable stability before any stronger update
```

No candidate is selected by KL alone. KL is used to diagnose whether the policy moved enough or too aggressively.

---

# 7. Sequential parameter strategy

WP9-d uses **sequential, causal tuning**, not a large grid.

## 7.1 Recipe A — coverage/scheduler only

```yaml
steps: 1200
lr: 5e-6
beta: 0.01
lora_r: 16
scheduler: constant_with_warmup
```

A answers the highest-confidence hypothesis from WP9-c.

## 7.2 Recipe B — only if A remains under-updated

B is permitted only if Recipe A evidence shows both:

- policy movement remains weak, e.g. KL remains in the old approximately `1e-4` regime or below the diagnostic weak band; and
- eval400 does not improve despite stable execution.

Then change only:

```yaml
learning_rate: 1.0e-5
```

Everything else remains Recipe A.

## 7.3 Recipe C — only if B still appears KL-constrained

C is permitted only after B completes and remains stable but still shows insufficient policy movement or eval400 improvement. Then change only:

```yaml
beta: 0.005
```

with `lr=1e-5`, `steps=1200`, `r=16`, and all other fields unchanged.

## 7.4 LoRA rank is not an early search dimension

`r=16 / alpha=32` remains fixed through A/B/C. A move to `r=32 / alpha=64` requires a separate explicit amendment after A/B/C evidence indicates that optimization budget and KL regularization are no longer the obvious bottleneck.

## 7.5 Sampling and reward definitions stay frozen

Do not change `num_generations=8`, temperature, top-p, reward source, test-layer semantics, active problem pool, or Public/Hidden problem order during A/B/C. Those changes would create a different research question.

---

# 8. Public/Hidden fairness during optimization

Hyperparameter search MUST NOT silently privilege one reward arm and later present the resulting recipe as a neutral Public-vs-Hidden comparison.

Preferred protocol:

- each accepted recipe candidate is evaluated as a paired Public/Hidden run from the same B with identical non-reward hyperparameters;
- recipe decisions use the same eval400 metric contract for both arms;
- if compute constraints force a single mechanics-development arm, that choice and its scientific bias MUST be declared before training, and any later paired comparison must rerun both arms from B with the frozen selected recipe.

No arm-specific post-hoc LR/beta/rank/checkpoint rule is allowed in a final paired comparison unless the project explicitly changes the research question from paired Public-vs-Hidden comparison to arm-specific optimization.

---

# 9. Checkpoint selection

Default checkpoint rule for Recipe A:

1. evaluate steps `300/600/900/1200` on canonical eval400;
2. rank by Eval-Hidden Pass@1;
3. break exact ties by higher average eval-hidden test pass rate;
4. next tie-break by lower runtime-error rate;
5. next tie-break by lower parse-error rate;
6. next tie-break by earlier checkpoint.

All measured checkpoints remain in the report. Do not hide losing checkpoints after selecting the winner.

A future WP9-d plan MAY tighten numeric stability guardrails before execution. Parameter/checkpoint choices MAY use observed eval400 results, but each such decision must be logged as benchmark-guided tuning.

---

# 10. Reused-benchmark interpretation

The project explicitly accepts the cost of using eval400 for tuning because no sufficiently independent additional benchmark is available.

Therefore:

- eval400 is the authoritative performance standard for WP9-d and subsequent GRPO optimization;
- repeated eval400 use for recipe/checkpoint selection is allowed;
- the complete sequence of tried recipes/checkpoints and their eval400 results MUST be retained to avoid winner-only reporting;
- confidence intervals remain useful as uncertainty summaries for the 400 benchmark problems, but MUST NOT be described as correcting for adaptive hyperparameter selection;
- after WP9-d starts using eval400 for tuning, phrases such as “untouched held-out improvement” or “independent generalization estimate” MUST NOT be used for the selected result;
- acceptable wording includes “eval400-selected benchmark improvement”, “reused-benchmark result”, and “performance on the canonical 400-problem benchmark”.

---

# 11. Throughput and GPU-utilization guardrails

WP9-c leaves substantial systems headroom, but throughput changes MUST be separated from the initial Recipe A scientific change.

Measured formal evidence from the completed C/Public run:

- GRPO GPU utilization: mean `25.35%`, p95 `44%`;
- GRPO GPU memory used: mean approximately `7187 MiB`, max `7315 MiB` on the RTX 4090;
- representative trainer telemetry records generation at approximately `8.7–13.7 s` per step while backward is approximately `0.11–0.13 s`; reward verification is not the dominant wall-time component;
- canonical standalone eval generation at batch `4` used approximately `4214 MiB` mean / `4321 MiB` max GPU memory, with mean utilization `48.81%` and p95 `53%`.

These measurements justify later systems optimization; they do not authorize silently changing the scientific batch contract.

## 11.1 GRPO training throughput

Recipe A MUST retain:

```yaml
per_device_train_batch_size: 1
gradient_accumulation_steps: 8
num_generations: 8
reward_verification_workers: 8
```

Consequences:

- effective single-GPU rollout/generation batch = `1 * 8 = 8` completion rows;
- `8 / num_generations(8) = 1` active problem group per optimizer step;
- changing the effective generation batch to `16` would process two problem groups per generation/update batch and changes optimizer noise, update frequency, epoch accounting, and the meaning of `max_steps`; it is therefore a **scientific recipe change**, not a free systems optimization;
- changing only `per_device_train_batch_size` versus gradient accumulation while keeping their product `8` may increase backward utilization, but backward is a small fraction of measured step time and is not a priority optimization.

Increasing GRPO reward verification workers above `8` MAY be benchmarked separately, but the observed verifier wall time is much smaller than generation time, so the expected end-to-end gain is limited.

The highest-potential GRPO systems direction is faster autoregressive rollout generation while retaining `k=8` group semantics. Candidate engineering paths include an optimized generation backend such as vLLM/continuous batching, or compile/cache/attention-kernel improvements. The current project runtime pins `use_vllm=False`; changing that backend requires an explicit systems amendment and dependency/runtime validation. Because GRPO rollout sampling is stochastic, a backend change may alter sampled trajectories even when nominal decode parameters are unchanged. It MUST NOT be combined with Recipe A when the goal is to isolate the coverage/scheduler hypothesis.

## 11.2 Canonical eval400 generation throughput

Canonical eval400 MUST continue to use logical generation batch `4` unless a separately approved benchmark-protocol amendment changes it.

Prior WP9-c systems evidence established:

- batch `4` preserved exact per-problem Pass@1 parity with the batch-1 reference on the systems benchmark;
- batch `8` was faster but changed per-problem Pass@1 and was therefore rejected;
- consequently, simply increasing formal eval generation from `4` to `8` is **not** an allowed throughput optimization under the current canonical benchmark.

Preferred eval-generation optimization work should first preserve the batch-4 logical call shape. Candidate approaches may include compile/static-cache/attention improvements or carefully controlled concurrency of independent batch-4 calls. Before adoption, the candidate path MUST prove canonical problem/order identity and exact per-problem Pass@1 parity against the existing batch-4 contract; completion-level parity SHOULD also be checked after removing latency-only metadata.

If a future decision intentionally adopts batch `>4` despite changed outputs, that is a benchmark-protocol change. At minimum B must be regenerated/re-evaluated under the new protocol before candidate deltas are interpreted; historical b4 results must not be mixed directly with the new protocol as if they were identical measurements.

---

# 12. Safety and operational contracts

All parent project requirements remain active, including:

- optimizer-based GRPO only on the 24GB-class target GPU;
- GTX 1660 Ti remains control plane for planning, data audit, Piston verification, aggregation, statistics, report generation, and operator handoff preparation;
- target roots remain under the current machine-authoritative persistent root policy; no resurrection of retired `/data` paths;
- exact handoff commit + tracked `run.sh` SHA + clean checkout before target execution;
- formal parent B strict loader and safe-merge semantics;
- trainer checkpoint resume only within the same recipe/arm identity;
- no destructive restart of completed/failed evidence;
- no `eval_hidden_tests` inside GRPO training reward payloads;
- no new dependency or `third_party/open-r1` modification unless separately justified and reviewed.

Checkpoint cadence SHOULD remain sufficiently dense to avoid losing large portions of a 1200-step run; `save_steps=100` is the starting default.

---

# 13. WP9-d stage acceptance

WP9-d is not successful merely because a longer GRPO run completes.

A useful WP9-d outcome must establish one of the following with auditable evidence:

1. **coverage hypothesis supported:** Recipe A produces materially larger, stable policy movement and improves canonical eval400;
2. **coverage hypothesis rejected:** even approximately one epoch with sustained `5e-6` fails to improve eval400, justifying Recipe B or a change in research direction;
3. **stronger update needed:** Recipe B/C improves eval400 without unacceptable executable instability;
4. **optimization is not the main bottleneck:** A/B/C produce movement but eval400 remains flat, indicating the next stage should investigate reward/data/objective design rather than further scaling LR/beta/rank.

The stage report MUST include training curves, KL/reward/length/stability diagnostics, all measured eval400 checkpoint results, exact recipe identities, GPU-hours, paired comparisons, and a clear statement of which hypothesis was supported or rejected.

---

# 14. Branch and stage routing

WP9-c must be integrated and closed before WP9-d begins. **WP9-d MUST branch from the cleaned, integrated `main` branch**, not from `feat/wp9-c`, a detached handoff commit, or an archival snapshot.

After the WP9-c closeout decision, the next dependency-ready research stage is **WP9-d — GRPO coverage/scheduler optimization**.

A new conversation asked to “continue the project” MUST:

1. read `PROJECT_SPEC_Open-R1_CodeVerifier.md`;
2. read `PROJECT_SPEC_GRPO_Refresh.md` as historical/parent WP9 contract;
3. read this amendment;
4. read `docs/wp9c-stage-closeout.md` and latest `proceedings.md`;
5. confirm `main` contains the completed WP9-c integration and is clean;
6. create/seal a WP9-d plan and branch/worktree from that `main` before starting any optimizer run.

No WP9-d optimizer execution is authorized solely by the existence of this specification.
