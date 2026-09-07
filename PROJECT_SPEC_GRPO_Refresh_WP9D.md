# PROJECT SPEC — WP9-d GRPO Optimization Amendment

**Status:** Active amendment v1.0
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
3. **If movement is sufficient, does it transfer to a non-eval400 functional development set without destabilizing executable code generation?**

Frozen eval400 is not a hyperparameter-development tool. It is reserved for a later formal gate after a WP9-d recipe has been selected without using eval400 outcomes.

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

# 3. First candidate: coverage/scheduler correction

The first WP9-d candidate is frozen as **Recipe A**:

```yaml
wp9d_recipe_A:
  max_steps: 1200
  learning_rate: 5.0e-6
  warmup_ratio: 0.05
  lr_scheduler_type: constant_with_warmup
  beta: 0.01

  num_generations: 8
  per_device_train_batch_size: 1
  gradient_accumulation_steps: 8

  temperature: 0.8
  top_p: 0.95
  max_prompt_length: 2048
  max_completion_length: 512

  lora_r: 16
  lora_alpha: 32
  lora_dropout: 0.05

  logging_steps: 1
  save_steps: 100
```

Rationale:

- `1200` steps correspond to approximately `0.89` epoch under the observed WP9-c trainer accounting, compared with approximately `0.22` epoch previously;
- LR remains at the previously accepted `5e-6` after warmup, so Recipe A isolates the **coverage/scheduler** hypothesis rather than simultaneously testing a larger step size;
- `beta=0.01`, sampling, LoRA capacity, batch structure, and reward definitions remain unchanged.

Recipe A is the default next experiment but **this specification does not authorize running it automatically**. A WP9-d plan/operator handoff must still be created and explicitly started under the normal stage workflow.

---

# 4. Mandatory functional development set before training

Before any WP9-d optimizer run, the stage MUST freeze a non-eval400 functional development set.

Requirements:

- target size SHOULD be `200–300` problems;
- zero problem overlap with active1354 training IDs;
- zero problem overlap with frozen eval400 IDs;
- zero use of frozen eval400 completions/results when selecting or constructing the dev set;
- every problem must have the same three-layer test contract needed to compute visible / train-hidden / dev-hidden functional metrics;
- source/difficulty mix SHOULD be reasonably representative of the code-generation domain, but source selection MUST be reward-outcome-independent;
- exact problem IDs/order, dataset hash, Piston config hash, prompt/model/decode contract, and verification concurrency MUST be frozen before the first WP9-d run.

The existing 300-problem C32 validation set MAY be reused **only if** a strict audit proves all requirements above, including the required hidden-test layers and exact zero overlap with active1354 and eval400. Otherwise WP9-d must build a new dedicated functional dev set from eligible non-held-out data.

This functional dev set is a development resource. It is not a replacement for frozen eval400. In this amendment, **dev-hidden** means the `eval_hidden_tests` layer belonging to these newly frozen development problems; it never means the separate formal eval400 problem set.

---

# 5. Checkpoint and measurement protocol

For Recipe A and every later recipe candidate:

- trainer metrics log every optimizer step;
- checkpoint save cadence: every `100` optimizer steps;
- mandatory functional-dev evaluation checkpoints: `300`, `600`, `900`, `1200`;
- B baseline MUST be evaluated on the same functional dev contract before candidate comparison;
- Public and Hidden candidate arms, when both are run, must start independently from the same frozen B and use the same selected recipe/checkpoint schedule;
- no candidate may use another candidate's checkpoint as parent.

Functional-dev generation/evaluation MUST use deterministic pass@1 and a frozen decode contract. Generation can run on the 24GB worker; verification/aggregation should return to the GTX 1660 Ti/Piston control plane as in the existing staged-evaluation workflow.

No eval400 generation may occur during recipe selection.

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

## 6.2 Functional development metrics

Primary development metric:

- **dev-hidden Pass@1** on the frozen non-eval400 functional dev set.

Required secondary metrics:

- visible Pass@1;
- train-hidden Pass@1;
- average dev-hidden test pass rate;
- parse success / target-function-found rate;
- runtime-error rate;
- timeout rate;
- mean / p50 / p95 completion tokens.

A candidate is not considered better merely because trainer reward rises. Functional transfer and executable stability are required.

## 6.3 KL interpretation bands

The following are **engineering diagnostic bands, not formal optimality claims**:

```yaml
wp9d_kl_diagnostics:
  likely_too_weak:
    mean_kl_below: 3.0e-4
    condition: no_functional_dev_improvement

  useful_search_region:
    mean_kl: 5.0e-4_to_5.0e-3

  caution:
    sustained_or_peak_kl_near_or_above: 1.0e-2
    interpretation: inspect executable stability before any stronger update
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
- no convincing functional-dev improvement appears despite stable execution.

Then change only:

```yaml
learning_rate: 1.0e-5
```

Everything else remains Recipe A.

## 7.3 Recipe C — only if B still appears KL-constrained

C is permitted only after B completes and remains stable but still shows insufficient policy movement. Then change only:

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
- recipe decisions use an arm-symmetric functional-dev summary, e.g. both-arm metrics and the mean/minimum dev-hidden improvement, plus executable-stability guards;
- if compute constraints force a single mechanics-development arm, that choice and its scientific bias MUST be declared before training, and any later formal Public/Hidden comparison must rerun both arms from B with the frozen selected recipe.

No arm-specific post-hoc LR/beta/rank/checkpoint selection is allowed in a final paired comparison.

---

# 9. Checkpoint selection

Recipe comparison and checkpoint selection must be pre-declared before observing WP9-d functional-dev results.

Default checkpoint rule for Recipe A:

1. evaluate steps `300/600/900/1200` on the frozen functional dev set;
2. rank by dev-hidden Pass@1;
3. break exact ties by higher average dev-hidden test pass rate;
4. next tie-break by lower runtime-error rate;
5. next tie-break by earlier checkpoint;
6. reject any checkpoint with a material parse/runtime stability regression that violates the stage plan's pre-registered guardrails.

The chosen checkpoint is then frozen. Eval400 may only be run after that selection is complete.

A future WP9-d plan MAY tighten numeric stability guardrails before execution, but MUST do so before seeing WP9-d candidate outcomes.

---

# 10. Eval400 firewall

Frozen eval400 has already been used for formal B/C/D and SFT1354 conclusions. To preserve its remaining value:

- MUST NOT use eval400 to choose Recipe A/B/C;
- MUST NOT use eval400 to choose checkpoint 300/600/900/1200;
- MUST NOT inspect eval400 per-problem outcomes while deciding LR/beta/rank;
- MUST NOT repeatedly run eval400 after every candidate;
- MAY run eval400 once for a recipe/checkpoint that has been frozen by the non-eval400 development protocol;
- any later recipe change after seeing that formal eval400 result is a new stage/experiment and the prior eval400 must be treated as observed evidence, not a clean development set.

---

# 11. Safety and operational contracts

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

# 12. WP9-d stage acceptance

WP9-d is not successful merely because a longer GRPO run completes.

A useful WP9-d outcome must establish one of the following with auditable evidence:

1. **coverage hypothesis supported:** Recipe A produces materially larger, stable policy movement and improved non-eval400 functional transfer;
2. **coverage hypothesis rejected:** even approximately one epoch with sustained `5e-6` fails to improve functional transfer, justifying Recipe B or a change in research direction;
3. **stronger update needed:** Recipe B/C improves functional transfer without unacceptable executable instability;
4. **optimization is not the main bottleneck:** A/B/C produce movement but functional transfer remains absent, indicating the next stage should investigate reward/data/objective design rather than further scaling LR/beta/rank.

The stage report MUST include training curves, KL/reward/length/stability diagnostics, functional-dev results, exact recipe identities, GPU-hours, and a clear statement of which hypothesis was supported or rejected.

---

# 13. Routing

After the WP9-c closeout decision, the next dependency-ready research stage is **WP9-d — GRPO coverage/scheduler optimization**.

A new conversation asked to “continue the project” MUST:

1. read `PROJECT_SPEC_Open-R1_CodeVerifier.md`;
2. read `PROJECT_SPEC_GRPO_Refresh.md` as historical/parent WP9 contract;
3. read this amendment;
4. read `docs/wp9c-stage-closeout.md` and latest `proceedings.md`;
5. create/seal a WP9-d plan before starting any new optimizer run.

No WP9-d optimizer execution is authorized solely by the existence of this specification.