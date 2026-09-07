# PROJECT SPEC — WP9-d GRPO Optimization Amendment

**Status:** Active amendment v1.5
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

WP9-d therefore optimizes **systems throughput first, then coverage / scheduler / effective policy movement**. By explicit user decision on 2026-09-07, the project objective is capability improvement rather than a strict one-variable hyperparameter study. The WP9-d runtime MAY therefore adopt a better rollout/generation backend before Recipe A, provided the new runtime is frozen and used consistently for subsequent WP9-d candidates. By a later explicit user decision on the same date, the fresh GRPO adapter target set is expanded from the PEFT Qwen2 auto default (`q_proj`,`v_proj`) to explicit `q_proj`,`k_proj`,`v_proj`,`o_proj`; this qkvo target set is part of the new WP9-d frozen baseline. Learning rate, beta, LoRA rank, reward definition, active pool, and scientific sampling settings remain sequential tuning dimensions unless separately changed.

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
    lora_target_modules: [q_proj, k_proj, v_proj, o_proj]

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
  parallel_generators: 2
  verification_workers: 64
  primary_metric: eval_hidden_pass_at_1
  decode: deterministic_pass_at_1
```

Rules:

- the same 400 problem IDs/order MUST be used for every candidate/checkpoint;
- within WP9-d, the same deterministic decode, seed, logical batch `4`, parallel-generator count, verifier, and aggregation contract MUST be used after the optimized runtime is frozen;
- exact output parity with the historical WP9-c generation runtime is **not required**; throughput improvements may change deterministic outputs through backend/batching effects, and that protocol change must be disclosed;
- B remains the benchmark baseline, but after the WP9-d optimized evaluation runtime is frozen, B MUST be regenerated/re-evaluated once under that same runtime before Recipe A checkpoint deltas are interpreted;
- existing WP9-c B/C/D results remain historical controls and are not mixed numerically with the new WP9-d runtime as if the generation protocol were identical;
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

  use_vllm: true
  vllm_mode: colocate
  vllm_gpu_memory_utilization: 0.4

wp9d_recipe_A_operator_runtime:
  reward_verification_workers: 8
  eval_generation_batch_size: 4
  eval_parallel_generators: 2
```

The strict GRPO config loader also requires the arm-specific fields `run_name`, `reward_mode`, `dataset_path`, and `piston_config`. The WP9-d plan/operator MUST bind those explicitly for Public and Hidden; they are not free tuning variables and must preserve the frozen active1354/Piston identities.

Rationale:

- `1200` steps correspond to approximately `0.89` epoch under the observed WP9-c trainer accounting, compared with approximately `0.22` epoch previously;
- LR remains at the previously accepted `5e-6` after warmup, so within the **new frozen WP9-d runtime** Recipe A still tests the coverage/scheduler change without simultaneously increasing LR;
- the systems baseline itself changes before Recipe A: rollout generation uses colocated vLLM and eval generation uses two concurrent logical-b4 generators. Stochastic GRPO trajectories and deterministic eval outputs are allowed to differ from WP9-c; the project accepts this because the objective is capability improvement, not strict runtime ablation;
- `beta=0.01`, sampling, LoRA rank/alpha/dropout, batch structure, and reward definitions remain unchanged; the fresh GRPO LoRA target coverage is intentionally expanded to qkvo before P1 and is frozen for subsequent WP9-d tests;
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

`r=16 / alpha=32 / dropout=0.05` remains fixed through A/B/C, and the fresh GRPO adapter target set is fixed to `q_proj,k_proj,v_proj,o_proj`. The qkvo expansion is a pre-P1 baseline amendment, not an A/B/C search dimension. A move to `r=32 / alpha=64`, a return to q+v, or expansion into MLP projections requires a separate explicit amendment after evidence justifies changing adapter capacity/coverage again.

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

# 11. Throughput and GPU-utilization baseline

WP9-c leaves substantial systems headroom. By explicit user decision, WP9-d MUST optimize the runtime **before** Recipe A and then freeze that optimized runtime for subsequent training/evaluation. Exact parity with the historical WP9-c runtime is not a gate; consistency within WP9-d and measurable capability/throughput are the priority.

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
lora_target_modules: [q_proj, k_proj, v_proj, o_proj]
reward_verification_workers: 8
```

Consequences:

- effective single-GPU rollout/generation batch = `1 * 8 = 8` completion rows;
- `8 / num_generations(8) = 1` active problem group per optimizer step;
- the fresh GRPO adapter trains LoRA deltas on all attention projections `q_proj,k_proj,v_proj,o_proj`; SFT B is loaded read-only and safe-merged first, so this does not retroactively alter the completed B adapter;
- changing the effective generation batch to `16` would process two problem groups per generation/update batch and changes optimizer noise, update frequency, epoch accounting, and the meaning of `max_steps`; it is therefore a **scientific recipe change**, not a free systems optimization;
- changing only `per_device_train_batch_size` versus gradient accumulation while keeping their product `8` may increase backward utilization, but backward is a small fraction of measured step time and is not a priority optimization.

Increasing GRPO reward verification workers above `8` MAY be benchmarked separately, but the observed verifier wall time is much smaller than generation time, so the expected end-to-end gain is limited.

WP9-d adopts the highest-potential GRPO systems direction directly: **TRL colocated vLLM** for autoregressive rollout generation while retaining `k=8`, one active problem group per optimizer step. The pinned runtime exposes `use_vllm`, `vllm_mode=colocate`, and `vllm_gpu_memory_utilization`; Recipe A fixes the initial memory fraction at `0.4`. Because rollout sampling is stochastic, vLLM may change trajectories relative to WP9-c even under the same seed/temperature/top-p. This is accepted as part of the new WP9-d runtime baseline. Before the first full Recipe A run, the target operator MUST perform a bounded startup/smoke validation that confirms vLLM initialization, B-weight synchronization, reward execution, one optimizer update, checkpointability, and safe 24GB memory headroom.

## 11.2 Canonical eval400 generation throughput

Canonical eval400 keeps **logical generation batch `4`**, but WP9-d standardizes two independent batch-4 model instances running concurrently (`parallel_generators=2`). This uses the observed memory headroom without converting each `model.generate()` call into b8.

Prior WP9-c evidence still informs the design: b4 was efficient and historically comparable, while direct b8 changed outputs. WP9-d no longer requires exact parity with the old runtime, but it preserves logical b4 because it is a good throughput/stability operating point and because two b4 model copies should still fit comfortably inside a 24GB RTX 4090.

The parallel generator MUST preserve the canonical 400 problem order in the persisted bundle even though two b4 chunks execute concurrently. Each model instance uses a dedicated CUDA stream so the two logical-b4 calls can overlap GPU work rather than merely overlap Python scheduling. A bounded pre-A systems check should record wall time, GPU utilization, peak memory, completion count, and any generation failures. Exact completion parity with the old single-generator b4 run is informative but **not an acceptance gate**.

Because the optimized runtime may change outputs, B MUST be regenerated/re-evaluated once with the same `batch_size=4 / parallel_generators=2` protocol. Recipe A and later checkpoints are then compared against that WP9-d B baseline. Historical WP9-c b4 results remain context only and must not be mixed as if they were generated by the same runtime.

## 11.3 Minimal P1 runtime-validation contract

Before any B refresh or 1200-step Recipe A run, WP9-d MUST close a bounded P1 systems-validation gate on the RTX 4090. This gate is systems evidence only and MUST NOT be interpreted as model-capability evidence.

The P1 GRPO scope is exact:

- Public: exactly one optimizer step from frozen B with fresh GRPO LoRA targets `q_proj,k_proj,v_proj,o_proj`, `num_generations=8`, train batch `1`, gradient accumulation `8`, reward workers `8`, and colocated vLLM;
- Hidden: the same exact one-step contract, independently initialized from the same frozen B;
- only after both single-arm smokes pass, one same-GPU Public/Hidden pair MAY be run with one independent process/output namespace per arm;
- same-GPU memory search MUST start at `vllm_gpu_memory_utilization=0.40`; `0.30` is authorized only after OOM/vLLM memory initialization failure or measured unsafe headroom at `0.40`, and `0.25` only after the same condition at `0.30`; no intermediate memory-fraction grid is allowed;
- same-GPU concurrency is selected only when both arms are stable, checkpointable, have safe VRAM headroom, and satisfy the parent-spec §10.2 requirement of at least 15% total-wall reduction versus the measured single-arm sequential estimate (or equivalent aggregate useful-throughput evidence). Otherwise Public/Hidden MUST remain sequential.

Each successful one-step arm MUST demonstrate the complete chain `frozen B -> fresh qkvo GRPO LoRA -> colocated vLLM init/weight sync -> 8 rollouts -> reward verification -> backward -> optimizer update -> checkpoint-1`, and MUST record at least total wall, optimizer-step wall, actual vLLM generation wall, reward verification wall, backward total, optimizer timing, GPU utilization mean/p95, driver-visible memory mean/max, torch allocated/reserved peaks, OOM/weight-sync status, and strict checkpoint-1 readback. For the pinned TRL colocated path, actual generation timing MUST instrument `trainer.llm.generate()`; the generic metric MAY mirror it, while `vllm_generation_runtime_seconds` is the explicit systems field. Backward telemetry MUST include the total across all accumulation calls contributing to the optimizer step.

The P1 eval-generation scope is also exact:

- use only the first **8** canonical eval400 problems, i.e. one complete `2 × b4` wave;
- run one `batch_size=4 / parallel_generators=1` reference and one `batch_size=4 / parallel_generators=2` candidate;
- the dual candidate MUST load two independent model instances, enable one dedicated CUDA stream per instance, complete all 8 generations without error/OOM, and persist rows in the exact canonical input order;
- record total wall, invocation generation wall, problems/s, GPU utilization mean/p95, and peak memory;
- do not expand P1 generation to eval400.

P1 execution MUST use a tracked operator handoff bound to the exact target commit and `run.sh` SHA, current READY machine-pointer roots, atomic status/evidence, and non-destructive artifacts. Failed attempts remain preserved. After a diagnosed narrow repair, only the affected minimal phase is rerun; previously passed unrelated phase evidence MAY remain accepted if its own handoff/operator identity is retained in the final P1 report. The final P1 report freezes the runtime candidate and then the invocation MUST stop; B eval400 refresh and Recipe A remain separate later actions.

As of the v1.5 amendment update, the GTX 1660 Ti control-plane implementation/handoff is prepared for the qkvo GRPO baseline, including the deterministic first-8 order SHA `0e9d0d2f93422aa9cee4b1d66dcb56d498a6fa40b44d31270c237c7ab975324e`; the RTX 4090 is offline, so **no P1 measured runtime decision has yet been made**.

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
