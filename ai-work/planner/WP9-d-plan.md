# WP9-d Plan — Optimized GRPO Runtime then Recipe A

## Status

Prepared on 2026-09-07 from integrated `main` commit `11d48b244ed9fa6b2556e1970755992fc6b8827a` on branch `feat/wp9-d`. P0 runtime implementation is at `69dfc35b8f9476843a8a96da51f63923b9a9b200`; the P1 control-plane handoff is now prepared on the user-selected qkvo GRPO baseline while the RTX 4090 is offline. No P1 target result or runtime-freeze decision is claimed yet.

WP9-d is capability-first. Runtime throughput is optimized before Recipe A; exact trajectory/output parity with WP9-c is not required. The GTX 1660 Ti remains the control plane; only the bounded P1 smoke phases move to the 4090 through the tracked operator handoff.

## P0 — Runtime implementation

1. GRPO rollout backend: TRL v0.18 colocated vLLM.
   - `use_vllm=true`
   - `vllm_mode=colocate`
   - `vllm_gpu_memory_utilization=0.4`
   - tensor parallel size 1
   - retain `num_generations=8`, train batch 1, grad accumulation 8, reward workers 8.
2. Eval generation: retain logical `batch_size=4`, load two independent model instances, give each a dedicated CUDA stream, execute two b4 chunks concurrently, and persist results in canonical problem order.
3. Verification remains controller/Piston with 64 workers.
4. Fresh GRPO LoRA explicitly targets `q_proj,k_proj,v_proj,o_proj` with r16 / alpha32 / dropout0.05. Frozen SFT B remains read-only and is safe-merged before the fresh qkvo adapter is created.

## P1 — 4090 bounded systems validation before full training

Do not start the 1200-step run until P1 is complete. The tracked operator checkpoint is `ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/`. It is deliberately phase-addressable and has no full-eval or Recipe-A command. Use the paired one-step systems configs `configs/grpo/wp9d-runtime-smoke-{public,hidden}.yaml`; they are systems evidence, not capability-result arms.

Control-plane preparation already completed:

- colocated-vLLM timing now instruments the actual TRL `trainer.llm.generate()` path as `vllm_generation_runtime_seconds` while preserving ordinary Transformers timing;
- per-optimizer-step backward telemetry records `backward_runtime_total_seconds` and `backward_calls`;
- paired P1 smoke configs explicitly bind the fresh GRPO adapter to qkvo, and target preflight fails closed if that target set drifts;
- deterministic canonical eval8 transfer bundle is `/home/dzy/wp9d-p1-eval8-C0`, with first-8 ordered-ID SHA256 `0e9d0d2f93422aa9cee4b1d66dcb56d498a6fa40b44d31270c237c7ab975324e`;
- target phases emit atomic status + secret-free operator evidence and successful phases update stable accepted pointers, so only an affected failed smoke is retried after repair.

Target sequence after the 4090 is online:

1. `preflight`: exact handoff commit/script SHA, clean checkout, READY machine pointer/current `/root` roots, pinned runtime, frozen B/C29/eval400 identity, CUDA/BF16, storage, Piston, and eval8 verification. No model training/generation.
2. Public single arm: exactly one optimizer step from frozen B. Record total wall, step, vLLM generation, verifier wall, backward, optimizer, GPU utilization mean/p95, driver-visible VRAM, torch allocated/reserved peak, OOM/weight-sync status, and strict checkpoint-1 readback.
3. Hidden single arm: same exact one-step contract. Do not run a second optimizer step.
4. Same-GPU pair: exactly one Public + one Hidden optimizer step in independent processes/output roots. Start with `vllm_gpu_memory_utilization=0.40`. Only memory-pressure/OOM/vLLM-init failure or <1024 MiB measured headroom may authorize `0.30`; only the same condition at `0.30` may authorize `0.25`. No intermediate grid. Same-GPU concurrency is selected only when stable/safe and total wall is at least 15% below the single-arm sequential estimate, matching the parent §10.2 contract; otherwise freeze sequential execution.
5. Eval systems wave: exactly the canonical first 8 problems. Run b4/p1 reference once and b4/p2 candidate once. p2 must load two independent model instances, enable one dedicated CUDA stream per instance, complete exactly two concurrent b4 chunks, persist all 8 rows in canonical order, and record wall/utilization/memory. Do not expand to eval400.
6. `report`: read accepted bounded evidence only, derive the runtime-freeze candidate, and stop. If a narrow repair commit changes only one affected phase, prior passed unrelated accepted evidence may remain valid and is recorded by its own handoff commit rather than being rerun mechanically.

Exact output parity with WP9-c is diagnostic only, not a gate. The current status is **P1 control-plane prepared / 4090 target validation pending**.

## P2 — Freeze WP9-d runtime and refresh benchmark baseline

After P1 succeeds:

- freeze exact handoff commit/runtime parameters;
- regenerate and verify frozen B on canonical eval400 using `batch_size=4`, `parallel_generators=2`, seed 42, deterministic Pass@1;
- this becomes the WP9-d B comparison baseline;
- historical WP9-c B/C/D remain context only.

## P3 — Recipe A

Run paired Public/Hidden arms independently from frozen B with:

- 1200 optimizer steps;
- LR `5e-6`;
- `constant_with_warmup`, warmup ratio 0.05;
- beta 0.01;
- LoRA r16 / alpha32 / dropout0.05 on explicit `q_proj,k_proj,v_proj,o_proj` targets;
- k=8, train batch1, grad accumulation8;
- vLLM colocate runtime from P0/P1;
- checkpoint every 100 steps.

Evaluate canonical eval400 at steps 300/600/900/1200 using the frozen WP9-d dual-b4 runtime. Select checkpoint by Eval-Hidden Pass@1, then average hidden-test pass, runtime error, parse error, then earlier step.

## P4 — Sequential optimization after A

Use eval400 directly for selection. If A remains weak:

1. Recipe B: LR `1e-5`, otherwise frozen A runtime/recipe.
2. Recipe C: beta `0.005` with LR `1e-5`, otherwise frozen.
3. Only after A/B/C consider LoRA rank, another target-module expansion/contraction beyond qkvo, or larger effective generation/update batches.

Every attempted recipe/checkpoint remains in the report; eval400 is explicitly a reused tuning benchmark.
